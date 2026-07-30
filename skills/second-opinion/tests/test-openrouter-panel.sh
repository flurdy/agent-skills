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
jq -e '
  (.messages | length) == 2 and
  (.messages[0].role == "system" and
    (.messages[0].content | contains("SECOND_OPINION_COMPLETE"))) and
  (.messages[1].role == "user" and (.messages[1].content | type == "string")) and
  (has("tools") | not)
' "$request_file" >/dev/null || {
  printf 'missing fixed completion contract or unexpected tools\n' >&2
  exit 4
}

if [[ "$model" == "${FAKE_CURL_OVERSIZED_MODEL:-}" ]]; then
  head -c 2097152 /dev/zero | tr '\0' x > "$response_file"
elif [[ "$model" == "${FAKE_CURL_ERROR_MODEL:-}" ]]; then
  jq -n --arg model "$model" '{
    id: ("gen-" + $model), model: $model,
    error: {message: ("simulated failure for " + $model), metadata: {
      error_type: "provider_unavailable", provider_code: "must-not-persist"
    }},
    choices: [{finish_reason: "error", native_finish_reason: "provider_error", message: {
      content: "partial response before provider failure",
      reasoning: "hidden reasoning must not persist"
    }}]
  }' > "$response_file"
elif [[ "$model" == "${FAKE_CURL_PREAMBLE_MODEL:-}" ]]; then
  jq -n --arg model "$model" \
    --arg content "# Senior Architecture Review: Pi Watch-Loop Extension Plan

I'll first verify the plan's claims against the actual repository and installed Pi 0.82.1 documentation, then deliver the review." '{
    id: ("gen-" + $model), model: $model, provider: "fake-provider",
    choices: [{finish_reason: "stop", native_finish_reason: "stop", message: {
      content: $content,
      reasoning: "hidden reasoning must not persist"
    }}],
    usage: {prompt_tokens: 3640, completion_tokens: 302, total_tokens: 3942,
      completion_tokens_details: {reasoning_tokens: 248}}
  }' > "$response_file"
elif [[ "$model" == "${FAKE_CURL_TOOL_MODEL:-}" ]]; then
  jq -n --arg model "$model" '{
    id: ("gen-" + $model), model: $model, provider: "fake-provider",
    choices: [{finish_reason: "tool_calls", native_finish_reason: "tool_use", message: {
      content: null,
      reasoning: "hidden reasoning must not persist",
      tool_calls: [{id: "call-1", type: "function", function: {
        name: "inspect_repository", arguments: "must-not-persist"
      }}]
    }}],
    usage: {prompt_tokens: 10, completion_tokens: 3, total_tokens: 13}
  }' > "$response_file"
elif [[ "$model" == "${FAKE_CURL_LENGTH_MODEL:-}" ]]; then
  jq -n --arg model "$model" '{
    id: ("gen-" + $model), model: $model, provider: "fake-provider",
    choices: [{finish_reason: "length", native_finish_reason: "max_tokens", message: {
      content: "partial review content",
      reasoning: "hidden reasoning must not persist"
    }}],
    usage: {prompt_tokens: 10, completion_tokens: 100, total_tokens: 110}
  }' > "$response_file"
elif [[ "$model" == "${FAKE_CURL_LONG_METADATA_MODEL:-}" ]]; then
  jq -n '{
    id: ("i" * 512), model: ("m" * 512), provider: ("p" * 512),
    choices: [{finish_reason: "stop", native_finish_reason: ("n" * 512), message: {
      content: "completed response\n\n<!-- SECOND_OPINION_COMPLETE -->"
    }}],
    usage: {total_tokens: 1}
  }' > "$response_file"
else
  jq -n --arg model "$model" '{
    id: ("gen-" + $model), model: $model, provider: "fake-provider",
    choices: [{finish_reason: "stop", native_finish_reason: "stop", message: {
      content: ($model + "\n\n<!-- SECOND_OPINION_COMPLETE -->"),
      reasoning: "hidden reasoning must not persist"
    }}],
    usage: {prompt_tokens: 10, completion_tokens: 20, total_tokens: 30,
      completion_tokens_details: {reasoning_tokens: 5}}
  }' > "$response_file"
fi
FAKE_CURL
chmod +x "$TMP_DIR/bin/curl"

cat > "$TMP_DIR/bin/secret-api-key" <<'FAKE_SECRET_API_KEY'
#!/usr/bin/env bash
set -euo pipefail
[[ "$*" == "lookup openrouter flurdy" ]] || exit 2
printf '%s\n' 'test-key'
FAKE_SECRET_API_KEY
chmod +x "$TMP_DIR/bin/secret-api-key"

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
CHECK_ENV=(env -u OPENROUTER_API_KEY -u SECRET_API_KEY_PROJECT "PATH=$TMP_DIR/bin:$ORIGINAL_PATH" "HOME=$TMP_DIR/home")
KEYRING_ENV=(env -u OPENROUTER_API_KEY "PATH=$TMP_DIR/bin:$ORIGINAL_PATH" "HOME=$TMP_DIR/home" "SECRET_API_KEY_PROJECT=flurdy")

check_json="$("${CHECK_ENV[@]}" "$HELPER" check --config "$CONFIG" --profile test)"
jq -e '
  .ready == false and
  .auth == "missing" and
  (.models | length == 4) and
  (.profile_sha256 | test("^[a-f0-9]{64}$")) and
  .hard_limits.max_response_bytes == 1048576 and
  .hard_limits.max_timeout_seconds == 1800 and
  .completion_contract.bytes > 0 and
  (.completion_contract.sha256 | test("^[a-f0-9]{64}$")) and
  .problems == ["OpenRouter API key is not configured"]
' <<< "$check_json" >/dev/null || fail "local check output was incorrect"
assert_no_requests
profile_sha256="$(jq -r '.profile_sha256' <<< "$check_json")"
contract_bytes="$("$HELPER" completion-contract-bytes)"
(( contract_bytes > 0 && contract_bytes < 512 )) || fail "completion contract size was invalid"

keyring_json="$("${KEYRING_ENV[@]}" "$HELPER" check --config "$CONFIG" --profile test)"
jq -e '
  .ready == true and
  .auth == "configured (not network-verified)" and
  .problems == []
' <<< "$keyring_json" >/dev/null || fail "keyring authentication was not detected"
assert_no_requests

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
  .problems == ["OpenRouter API key is not configured"]
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

IMPOSSIBLE_PROMPT_CONFIG="$TMP_DIR/impossible-prompt.json"
jq --argjson bytes "$contract_bytes" '.profiles.test.limits.maxPromptBytes = $bytes' \
  "$CONFIG" > "$IMPOSSIBLE_PROMPT_CONFIG"
invalid_json="$("${CHECK_ENV[@]}" "$HELPER" check \
  --config "$IMPOSSIBLE_PROMPT_CONFIG" --profile test)"
jq -e '
  .ready == false and
  any(.problems[]; contains("must exceed the fixed completion contract"))
' <<< "$invalid_json" >/dev/null || fail "a profile with no user-prompt capacity was accepted"
assert_no_requests

MAX_TIMEOUT_CONFIG="$TMP_DIR/max-timeout.json"
jq '.profiles.test.limits.defaultTimeoutSeconds = 1800' "$CONFIG" > "$MAX_TIMEOUT_CONFIG"
max_timeout_json="$("${CHECK_ENV[@]}" "$HELPER" check \
  --config "$MAX_TIMEOUT_CONFIG" --profile test)"
jq -e '
  .ready == false and
  .profile_limits.defaultTimeoutSeconds == 1800 and
  .problems == ["OpenRouter API key is not configured"]
' <<< "$max_timeout_json" >/dev/null || fail "the maximum timeout was rejected"
assert_no_requests

OVER_TIMEOUT_CONFIG="$TMP_DIR/over-timeout.json"
jq '.profiles.test.limits.defaultTimeoutSeconds = 1801' "$CONFIG" > "$OVER_TIMEOUT_CONFIG"
invalid_json="$("${CHECK_ENV[@]}" "$HELPER" check \
  --config "$OVER_TIMEOUT_CONFIG" --profile test)"
jq -e '
  .ready == false and
  (.models | length == 0) and
  any(.problems[]; contains("compiled safety ceilings"))
' <<< "$invalid_json" >/dev/null || fail "an over-limit timeout was accepted"
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

CONTRACT_OVERHEAD_PROMPT="$TMP_DIR/contract-overhead.txt"
head -c $((513 - contract_bytes)) /dev/zero | tr '\0' x > "$CONTRACT_OVERHEAD_PROMPT"
expect_failure 'prompt plus completion contract is 513 bytes; profile maximum is 512' \
  "${RUN_ENV[@]}" "$HELPER" run --confirmed --config "$CONFIG" --profile test \
  --profile-sha256 "$profile_sha256" --prompt-file "$CONTRACT_OVERHEAD_PROMPT"
assert_no_requests

: > "$FAKE_CURL_LOG"
result_json="$(FAKE_CURL_DELAY=0.1 "${RUN_ENV[@]}" "$HELPER" run --confirmed \
  --config "$CONFIG" --profile test --profile-sha256 "$profile_sha256" \
  --prompt-file "$PROMPT")"
jq -e '
  length == 4 and
  all(.[];
    .status == "ok" and
    (.response == (.model | sub("^openrouter/"; ""))) and
    .termination.finishReason == "stop" and
    .termination.reportedFinishReason == "stop" and
    .termination.nativeFinishReason == "stop" and
    .termination.responseId == ("gen-" + (.model | sub("^openrouter/"; ""))) and
    .termination.responseModel == (.model | sub("^openrouter/"; "")) and
    .termination.responseProvider == "fake-provider" and
    .termination.toolCallCount == 0 and
    .usage.completion_tokens_details.reasoning_tokens == 5 and
    ((tostring | contains("hidden reasoning must not persist")) | not) and
    ((tostring | contains("SECOND_OPINION_COMPLETE")) | not)
  )
' <<< "$result_json" >/dev/null || fail "concurrent success results lost completion diagnostics or privacy"
[[ "$(wc -l < "$FAKE_CURL_LOG" | tr -d '[:space:]')" -eq 4 ]] || \
  fail "success run did not make exactly four calls"
[[ "$(sort -u "$FAKE_CURL_LOG" | wc -l | tr -d '[:space:]')" -eq 4 ]] || \
  fail "concurrent calls shared a curl config path"

: > "$FAKE_CURL_LOG"
result_json="$(FAKE_CURL_PREAMBLE_MODEL=qwen/test-a "${RUN_ENV[@]}" "$HELPER" run --confirmed \
  --config "$CONFIG" --profile test --profile-sha256 "$profile_sha256" \
  --prompt-file "$PROMPT")"
jq -e '
  length == 4 and
  (.[0].status == "incomplete" and
    (.[0].error | contains("completion marker")) and
    (.[0].response | startswith("# Senior Architecture Review")) and
    .[0].termination.finishReason == "stop" and
    .[0].termination.nativeFinishReason == "stop") and
  ([.[] | select(.status == "ok")] | length == 3) and
  ((tostring | contains("hidden reasoning must not persist")) | not)
' <<< "$result_json" >/dev/null || fail "Kimi-style preamble counted as a completed response"

: > "$FAKE_CURL_LOG"
result_json="$(FAKE_CURL_TOOL_MODEL=x-ai/test-b "${RUN_ENV[@]}" "$HELPER" run --confirmed \
  --config "$CONFIG" --profile test --profile-sha256 "$profile_sha256" \
  --prompt-file "$PROMPT")"
jq -e '
  length == 4 and
  (.[1].status == "incomplete" and
    (.[1].error | contains("tool call")) and
    .[1].response == null and
    .[1].termination.finishReason == "tool_calls" and
    .[1].termination.nativeFinishReason == "tool_use" and
    .[1].termination.toolCallCount == 1) and
  ([.[] | select(.status == "ok")] | length == 3) and
  ((tostring | contains("must-not-persist")) | not) and
  ((tostring | contains("hidden reasoning must not persist")) | not)
' <<< "$result_json" >/dev/null || fail "tool-call termination was accepted or leaked tool data"

: > "$FAKE_CURL_LOG"
result_json="$(FAKE_CURL_LENGTH_MODEL=deepseek/test-c "${RUN_ENV[@]}" "$HELPER" run --confirmed \
  --config "$CONFIG" --profile test --profile-sha256 "$profile_sha256" \
  --prompt-file "$PROMPT")"
jq -e '
  length == 4 and
  (.[2].status == "incomplete" and
    (.[2].error | contains("finish reason: length")) and
    .[2].response == "partial review content" and
    .[2].termination.finishReason == "length" and
    .[2].termination.nativeFinishReason == "max_tokens") and
  ([.[] | select(.status == "ok")] | length == 3)
' <<< "$result_json" >/dev/null || fail "non-stop termination was accepted as completed"

: > "$FAKE_CURL_LOG"
result_json="$(FAKE_CURL_LONG_METADATA_MODEL=moonshotai/test-d "${RUN_ENV[@]}" "$HELPER" run --confirmed \
  --config "$CONFIG" --profile test --profile-sha256 "$profile_sha256" \
  --prompt-file "$PROMPT")"
jq -e '
  length == 4 and
  (.[3].status == "ok" and .[3].response == "completed response" and
    (.[3].termination.responseId | length) == 128 and
    (.[3].termination.responseModel | length) == 256 and
    (.[3].termination.responseProvider | length) == 128 and
    (.[3].termination.nativeFinishReason | length) == 128)
' <<< "$result_json" >/dev/null || fail "termination diagnostics were not bounded"

: > "$FAKE_CURL_LOG"
result_json="$(FAKE_CURL_ERROR_MODEL=x-ai/test-b "${RUN_ENV[@]}" "$HELPER" run --confirmed \
  --config "$CONFIG" --profile test --profile-sha256 "$profile_sha256" \
  --prompt-file "$PROMPT")"
jq -e '
  length == 4 and
  ([.[] | select(.status == "ok")] | length == 3) and
  ([.[] | select(.status == "error" and .provider == "x-ai" and
    .error == "simulated failure for x-ai/test-b" and
    .response == "partial response before provider failure" and
    .curl_exit_code == 0 and
    .termination.finishReason == "error" and
    .termination.reportedFinishReason == "error" and
    .termination.nativeFinishReason == "provider_error" and
    .termination.errorType == "provider_unavailable")] | length == 1) and
  ((tostring | contains("must-not-persist")) | not) and
  ((tostring | contains("hidden reasoning must not persist")) | not)
' <<< "$result_json" >/dev/null || fail "per-model failure diagnostics or privacy were not preserved"
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
