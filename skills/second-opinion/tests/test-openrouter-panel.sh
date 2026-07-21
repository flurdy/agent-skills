#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$(cd "$SCRIPT_DIR/.." && pwd)/scripts/openrouter-panel.sh"
ORIGINAL_PATH="$PATH"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_no_requests() {
  [[ ! -s "$FAKE_CURL_LOG" ]] || fail "a rejected run invoked curl"
}

expect_failure() {
  local expected_message="$1"
  shift
  : > "$ERROR_LOG"
  if "$@" 2> "$ERROR_LOG"; then
    fail "command unexpectedly succeeded: $*"
  fi
  grep -Fq "$expected_message" "$ERROR_LOG" || {
    printf '%s\n' 'Unexpected error output:' >&2
    cat "$ERROR_LOG" >&2
    fail "missing expected error: $expected_message"
  }
}

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/bin" "$TMP_DIR/home"
FAKE_CURL_LOG="$TMP_DIR/curl.log"
ERROR_LOG="$TMP_DIR/error.log"
export FAKE_CURL_LOG

cat > "$TMP_DIR/bin/curl" <<'FAKE_CURL'
#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 2 && "$1" == "--config" ]] || {
  printf 'unexpected fake curl arguments: %s\n' "$*" >&2
  exit 2
}

config_file="$2"
printf '%s\n' "$config_file" >> "$FAKE_CURL_LOG"
grep -Fq 'max-filesize = 1048576' "$config_file" || {
  printf 'missing OpenRouter response transport cap\n' >&2
  exit 3
}
# Give concurrent calls time to expose accidental sharing of one config path.
sleep "${FAKE_CURL_DELAY:-0.05}"

request_file="$(awk -F '"' '/^data-binary = "@/{print $2}' "$config_file")"
request_file="${request_file#@}"
response_file="$(awk -F '"' '/^output = "/{print $2}' "$config_file")"
model="$(jq -r '.model' "$request_file")"

if [[ "$model" == "${FAKE_CURL_OVERSIZED_MODEL:-}" ]]; then
  head -c 2097152 /dev/zero | tr '\0' x > "$response_file"
elif [[ "$model" == "${FAKE_CURL_ERROR_MODEL:-}" ]]; then
  jq -n --arg model "$model" '{error: {message: ("simulated failure for " + $model)}}' \
    > "$response_file"
else
  jq -n --arg model "$model" \
    '{choices: [{message: {content: $model}}], usage: {total_tokens: 1}}' \
    > "$response_file"
fi
FAKE_CURL
chmod +x "$TMP_DIR/bin/curl"

CONFIG="$TMP_DIR/config.json"
cat > "$CONFIG" <<'JSON'
{
  "version": 1,
  "profiles": {
    "test": {
      "models": [
        {"model": "openrouter/qwen/test-a", "vendor": "Qwen", "role": "reasoning"},
        {"model": "openrouter/x-ai/test-b", "vendor": "xAI", "role": "critique"},
        {"model": "openrouter/deepseek/test-c", "vendor": "DeepSeek", "role": "verification"},
        {"model": "openrouter/moonshotai/test-d", "vendor": "Moonshot", "role": "context"}
      ],
      "limits": {
        "maxParallel": 4,
        "maxPromptBytes": 512,
        "maxOutputTokensPerModel": 100,
        "defaultTimeoutSeconds": 5
      }
    }
  }
}
JSON

RUN_ENV=(env "PATH=$TMP_DIR/bin:$ORIGINAL_PATH" "HOME=$TMP_DIR/home" "OPENROUTER_API_KEY=test-key")
CHECK_ENV=(env -u OPENROUTER_API_KEY "PATH=$TMP_DIR/bin:$ORIGINAL_PATH" "HOME=$TMP_DIR/home")

check_json="$("${CHECK_ENV[@]}" "$HELPER" check --config "$CONFIG" --profile test)"
jq -e '
  .ready == false and
  .auth == "missing" and
  (.models | length == 4) and
  (.profile_sha256 | test("^[a-f0-9]{64}$")) and
  .hard_limits.max_response_bytes == 1048576 and
  .problems == ["OPENROUTER_API_KEY is not set"]
' <<< "$check_json" >/dev/null || fail "local check output was incorrect"
assert_no_requests
profile_sha256="$(jq -r '.profile_sha256' <<< "$check_json")"

DUPLICATE_MODEL_CONFIG="$TMP_DIR/duplicate-model.json"
jq '.profiles.test.models[1].model = "openrouter/qwen/test-a"' "$CONFIG" \
  > "$DUPLICATE_MODEL_CONFIG"
invalid_json="$("${CHECK_ENV[@]}" "$HELPER" check \
  --config "$DUPLICATE_MODEL_CONFIG" --profile test)"
jq -e '
  .ready == false and
  (.models | length == 0) and
  any(.problems[]; contains("unique model IDs"))
' <<< "$invalid_json" >/dev/null || fail "duplicate model IDs were accepted"
assert_no_requests

REPEATED_PROVIDER_CONFIG="$TMP_DIR/repeated-provider.json"
jq '.profiles.test.models[1].model = "openrouter/qwen/test-b"' "$CONFIG" \
  > "$REPEATED_PROVIDER_CONFIG"
repeated_json="$("${CHECK_ENV[@]}" "$HELPER" check \
  --config "$REPEATED_PROVIDER_CONFIG" --profile test)"
jq -e '
  .ready == false and
  (.models | length == 4) and
  .problems == ["OPENROUTER_API_KEY is not set"]
' <<< "$repeated_json" >/dev/null || fail "same-provider routes were rejected"
assert_no_requests

OVER_LIMIT_CONFIG="$TMP_DIR/over-limit.json"
jq '.profiles.test.limits.maxParallel = 5' "$CONFIG" > "$OVER_LIMIT_CONFIG"
invalid_json="$("${CHECK_ENV[@]}" "$HELPER" check \
  --config "$OVER_LIMIT_CONFIG" --profile test)"
jq -e '
  .ready == false and
  (.models | length == 0) and
  any(.problems[]; contains("compiled safety ceilings"))
' <<< "$invalid_json" >/dev/null || fail "an over-limit profile was accepted"
assert_no_requests

PROMPT="$TMP_DIR/prompt.txt"
printf '%s\n' 'bounded panel test' > "$PROMPT"
EMPTY_PROMPT="$TMP_DIR/empty.txt"
: > "$EMPTY_PROMPT"

expect_failure 'refusing metered requests without --confirmed' \
  "${RUN_ENV[@]}" "$HELPER" run --config "$CONFIG" --profile test \
  --profile-sha256 "$profile_sha256" --prompt-file "$PROMPT"
assert_no_requests

expect_failure 'prompt file is empty; refusing metered requests' \
  "${RUN_ENV[@]}" "$HELPER" run --confirmed --config "$CONFIG" --profile test \
  --profile-sha256 "$profile_sha256" --prompt-file "$EMPTY_PROMPT"
assert_no_requests

wrong_sha256="$(printf '0%.0s' {1..64})"
expect_failure 'profile changed since check; rerun check and obtain fresh consent' \
  "${RUN_ENV[@]}" "$HELPER" run --confirmed --config "$CONFIG" --profile test \
  --profile-sha256 "$wrong_sha256" --prompt-file "$PROMPT"
assert_no_requests

OVERSIZED_PROMPT="$TMP_DIR/oversized.txt"
head -c 513 /dev/zero | tr '\0' x > "$OVERSIZED_PROMPT"
expect_failure 'profile maximum is 512' \
  "${RUN_ENV[@]}" "$HELPER" run --confirmed --config "$CONFIG" --profile test \
  --profile-sha256 "$profile_sha256" --prompt-file "$OVERSIZED_PROMPT"
assert_no_requests

: > "$FAKE_CURL_LOG"
result_json="$(FAKE_CURL_DELAY=0.1 "${RUN_ENV[@]}" "$HELPER" run --confirmed \
  --config "$CONFIG" --profile test --profile-sha256 "$profile_sha256" \
  --prompt-file "$PROMPT")"
jq -e '
  length == 4 and
  all(.[]; .status == "ok" and (.response == (.model | sub("^openrouter/"; ""))))
' <<< "$result_json" >/dev/null || fail "concurrent success results were mismatched"
[[ "$(wc -l < "$FAKE_CURL_LOG" | tr -d '[:space:]')" -eq 4 ]] || \
  fail "success run did not make exactly four calls"
[[ "$(sort -u "$FAKE_CURL_LOG" | wc -l | tr -d '[:space:]')" -eq 4 ]] || \
  fail "concurrent calls shared a curl config path"

: > "$FAKE_CURL_LOG"
result_json="$(FAKE_CURL_ERROR_MODEL=x-ai/test-b "${RUN_ENV[@]}" "$HELPER" run --confirmed \
  --config "$CONFIG" --profile test --profile-sha256 "$profile_sha256" \
  --prompt-file "$PROMPT")"
jq -e '
  length == 4 and
  ([.[] | select(.status == "ok")] | length == 3) and
  ([.[] | select(.status == "error" and .provider == "x-ai" and
    .error == "simulated failure for x-ai/test-b")] | length == 1)
' <<< "$result_json" >/dev/null || fail "per-model failure was not preserved"
[[ "$(wc -l < "$FAKE_CURL_LOG" | tr -d '[:space:]')" -eq 4 ]] || \
  fail "failure run did not preserve all four calls"

: > "$FAKE_CURL_LOG"
result_json="$(FAKE_CURL_OVERSIZED_MODEL=qwen/test-a "${RUN_ENV[@]}" "$HELPER" run --confirmed \
  --config "$CONFIG" --profile test --profile-sha256 "$profile_sha256" \
  --prompt-file "$PROMPT")"
jq -e '
  length == 4 and
  (.[0].status == "error" and .[0].provider == "qwen" and .[0].curl_exit_code == 63 and
    (.[0].error | contains("1048576-byte transport cap"))) and
  ([.[] | select(.status == "ok")] | length == 3)
' <<< "$result_json" >/dev/null || fail "oversized OpenRouter response was not a bounded model error"
(( ${#result_json} < 100000 )) || fail "oversized OpenRouter response leaked into result data"
[[ "$(wc -l < "$FAKE_CURL_LOG" | tr -d '[:space:]')" -eq 4 ]] || \
  fail "oversized response run did not preserve all four calls"

printf '%s\n' 'openrouter-panel tests passed'
