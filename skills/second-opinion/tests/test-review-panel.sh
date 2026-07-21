#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$(cd "$SCRIPT_DIR/.." && pwd)/scripts/review-panel.sh"
ORIGINAL_PATH="$PATH"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

expect_failure() {
  local message="$1"
  shift
  : > "$ERROR_LOG"
  if "$@" > /dev/null 2> "$ERROR_LOG"; then
    fail "command unexpectedly succeeded: $*"
  fi
  grep -Fq "$message" "$ERROR_LOG" || {
    cat "$ERROR_LOG" >&2
    fail "missing expected error: $message"
  }
}

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/bin" "$TMP_DIR/bin-no-gemini" "$TMP_DIR/home"
AGENT_LOG="$TMP_DIR/home/agents.log"
CURL_LOG="$TMP_DIR/curl.log"
ERROR_LOG="$TMP_DIR/error.log"
WATCHDOG_SLEEP_LOG="$TMP_DIR/watchdog-sleeps.log"
export AGENT_LOG CURL_LOG WATCHDOG_SLEEP_LOG

for agent in claude codex gemini; do
  cat > "$TMP_DIR/bin/$agent" <<'FAKE_AGENT'
#!/usr/bin/env bash
set -euo pipefail
agent="$(basename "$0")"
prompt="$(cat)"
[[ -z "${SECRET_MARKER+x}" ]] || { printf 'SECRET_MARKER leaked\n' >&2; exit 70; }
[[ -z "${OPENROUTER_API_KEY+x}" ]] || { printf 'OPENROUTER_API_KEY leaked\n' >&2; exit 71; }
printf '%s|%s|%s\n' "$agent" "$*" "$(printf '%s' "$prompt" | sha256sum | awk '{print $1}')" >> "$HOME/agents.log"
mode_file="$HOME/fake-agent-mode-$agent"
mode="normal"
[[ ! -f "$mode_file" ]] || mode="$(cat "$mode_file")"
case "$mode" in
  fail)
    printf 'simulated %s failure\n' "$agent" >&2
    exit 9
    ;;
  empty)
    exit 0
    ;;
  oversized)
    head -c 5242880 /dev/zero | tr '\0' x
    exit 0
    ;;
  oversized-stderr)
    head -c 2097152 /dev/zero | tr '\0' e >&2
    exit 9
    ;;
  ignore-term)
    trap '' TERM
    sleep 30
    ;;
  descendant-ignore-term)
    trap '' TERM
    printf '%s\n' "$$" > "$HOME/route-parent-pid-$agent"
    (
      trap '' TERM
      sleep 8
    ) &
    descendant_pid=$!
    printf '%s\n' "$descendant_pid" > "$HOME/route-descendant-pid-$agent"
    wait "$descendant_pid"
    ;;
esac
printf '%s-response\n' "$agent"
FAKE_AGENT
  chmod +x "$TMP_DIR/bin/$agent"
done

REAL_SLEEP="$(command -v sleep)"
cat > "$TMP_DIR/bin/sleep" <<FAKE_SLEEP
#!/usr/bin/env bash
set -euo pipefail
if [[ -n "\${WATCHDOG_SLEEP_LOG:-}" ]]; then
  printf '%s\\n' "\$\$" >> "\$WATCHDOG_SLEEP_LOG"
fi
exec "$REAL_SLEEP" "\$@"
FAKE_SLEEP
chmod +x "$TMP_DIR/bin/sleep"

cat > "$TMP_DIR/bin/curl" <<'FAKE_CURL'
#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 2 && "$1" == "--config" ]] || exit 2
config_file="$2"
printf '%s\n' "$config_file" >> "$CURL_LOG"
request_file="$(awk -F '"' '/^data-binary = "@/{print $2}' "$config_file")"
request_file="${request_file#@}"
response_file="$(awk -F '"' '/^output = "/{print $2}' "$config_file")"
model="$(jq -r '.model' "$request_file")"
if [[ "$model" == "${FAIL_OPENROUTER_MODEL:-}" ]]; then
  jq -n --arg model "$model" '{error:{message:("simulated failure for " + $model)}}' > "$response_file"
else
  jq -n --arg model "$model" '{choices:[{message:{content:("response from " + $model)}}],usage:{total_tokens:1}}' > "$response_file"
fi
FAKE_CURL
chmod +x "$TMP_DIR/bin/curl"

CONFIG="$TMP_DIR/config.json"
cat > "$CONFIG" <<'JSON'
{
  "version": 1,
  "profiles": {
    "legacy": {
      "models": [
        {"model":"openrouter/qwen/legacy-a","vendor":"Qwen","role":"reasoning"},
        {"model":"openrouter/x-ai/legacy-b","vendor":"xAI","role":"critique"}
      ],
      "limits":{"maxParallel":2,"maxPromptBytes":4096,"maxOutputTokensPerModel":100,"defaultTimeoutSeconds":5}
    },
    "mixed": {
      "quorum": 2,
      "routes": [
        {"id":"claude-main","kind":"local","agent":"claude","model":"fable","effort":"high","role":"reasoning","provider":"forged","effectiveModel":"forged","modelSource":"forged","effectiveEffort":"forged","effortSource":"forged"},
        {"id":"codex-main","kind":"local","agent":"codex","role":"critique"},
        {"id":"qwen-a","kind":"openrouter","model":"openrouter/qwen/model-a","vendor":"Qwen","role":"verification"},
        {"id":"qwen-b","kind":"openrouter","model":"openrouter/QWEN/model-b","vendor":"Qwen","role":"corroboration"}
      ],
      "limits":{"maxParallel":4,"maxPromptBytes":4096,"maxOutputTokensPerModel":100,"defaultTimeoutSeconds":5}
    },
    "invalid-gemini-effort": {
      "quorum": 1,
      "routes": [{"id":"gemini","kind":"local","agent":"gemini","effort":"high","role":"review"}],
      "limits":{"maxParallel":1,"maxPromptBytes":4096,"maxOutputTokensPerModel":100,"defaultTimeoutSeconds":5}
    },
    "local-legacy": {
      "quorum": 1,
      "routes": [{"id":"metered","kind":"openrouter","model":"openrouter/qwen/must-not-run","vendor":"Qwen","role":"review"}],
      "limits":{"maxParallel":1,"maxPromptBytes":4096,"maxOutputTokensPerModel":100,"defaultTimeoutSeconds":5}
    }
  }
}
JSON

PROMPT="$TMP_DIR/prompt.txt"
printf '%s\n' 'identical private panel prompt' > "$PROMPT"
ln -s "$TMP_DIR/bin/claude" "$TMP_DIR/bin-no-gemini/claude"
ln -s "$TMP_DIR/bin/codex" "$TMP_DIR/bin-no-gemini/codex"
RUN_ENV=(env "PATH=$TMP_DIR/bin:$ORIGINAL_PATH" "HOME=$TMP_DIR/home" "OPENROUTER_API_KEY=test-key" "SECRET_MARKER=must-not-leak" "WATCHDOG_SLEEP_LOG=$WATCHDOG_SLEEP_LOG")
NO_SETSID_RUN_ENV=(env "PATH=$TMP_DIR/bin:$ORIGINAL_PATH" "HOME=$TMP_DIR/home" "OPENROUTER_API_KEY=test-key" "SECRET_MARKER=must-not-leak" "WATCHDOG_SLEEP_LOG=$WATCHDOG_SLEEP_LOG" "REVIEW_PANEL_FORCE_NO_SETSID=1")
NO_GEMINI_ENV=(env "PATH=$TMP_DIR/bin-no-gemini:/usr/bin:/bin" "HOME=$TMP_DIR/home")

focused_json="$("${RUN_ENV[@]}" "$HELPER" check --config "$CONFIG" --panel focused --prompt-file "$PROMPT")"
jq -e '
  .ready and .source == "built-in" and .quorum == 2 and
  [.routes[].id] == ["claude","codex"] and .openrouter.requestCount == 0 and
  (.promptSha256 | test("^[a-f0-9]{64}$"))
' <<< "$focused_json" >/dev/null || fail "focused built-in was not normalized"

reserved_json="$("${RUN_ENV[@]}" "$HELPER" check --config "$CONFIG" --panel local-legacy --prompt-file "$PROMPT")"
jq -e '
  .ready and .source == "reserved-built-in" and .quorum == 2 and
  [.routes[].id] == ["claude","codex","gemini"] and .openrouter.requestCount == 0
' <<< "$reserved_json" >/dev/null || fail "local-legacy config override was not ignored"

legacy_json="$("${RUN_ENV[@]}" "$HELPER" check --config "$CONFIG" --panel legacy --prompt-file "$PROMPT")"
jq -e '
  .legacy and .quorum == 2 and .openrouter.requestCount == 2 and
  [.routes[].id] == ["openrouter-1","openrouter-2"]
' <<< "$legacy_json" >/dev/null || fail "legacy profile was not normalized"
printf '%s\n' "$legacy_json" > "$TMP_DIR/legacy-check.json"
"$HELPER" evaluate --policy consensus --check-file "$TMP_DIR/legacy-check.json" > "$TMP_DIR/missing-eval.json"
jq -e '
  (.quorumMet | not) and (.consensusEligible | not) and
  (.unavailableRoutes | length) == 2 and all(.unavailableRoutes[]; .status == "missing")
' "$TMP_DIR/missing-eval.json" >/dev/null || fail "an entirely unavailable panel could not be evaluated"

legacy_panel_sha="$(jq -r '.panelSha256' <<< "$legacy_json")"
legacy_openrouter_sha="$(jq -r '.openrouterSha256' <<< "$legacy_json")"
legacy_prompt_sha="$(jq -r '.promptSha256' <<< "$legacy_json")"
"${RUN_ENV[@]}" "$HELPER" run-openrouter --confirmed --config "$CONFIG" --panel legacy \
  --prompt-file "$PROMPT" --panel-sha256 "$legacy_panel_sha" \
  --openrouter-sha256 "$legacy_openrouter_sha" --prompt-sha256 "$legacy_prompt_sha" \
  > "$TMP_DIR/legacy-results.json"
"$HELPER" evaluate --policy quorum --check-file "$TMP_DIR/legacy-check.json" \
  --results-file "$TMP_DIR/legacy-results.json" > "$TMP_DIR/legacy-eval.json"
jq -e --arg prompt "$legacy_prompt_sha" '
  .quorumMet and .successfulProviderCount == 2 and
  [.results[].id] == ["openrouter-1","openrouter-2"] and
  all(.results[]; .status == "ok" and .promptSha256 == $prompt)
' "$TMP_DIR/legacy-eval.json" >/dev/null || \
  fail "legacy models coordinator execution failed"

unoverridden_json="$("${RUN_ENV[@]}" "$HELPER" check --config "$CONFIG" --panel mixed --prompt-file "$PROMPT")"
jq -e '
  (.routes[] | select(.id == "claude-main") |
    .provider == "anthropic" and .effectiveModel == "fable" and .modelSource == "panel" and
    .effectiveEffort == "high" and .effortSource == "panel")
' <<< "$unoverridden_json" >/dev/null || fail "reserved derived route fields influenced normalization"

mixed_json="$("${RUN_ENV[@]}" "$HELPER" check --config "$CONFIG" --panel mixed --prompt-file "$PROMPT" \
  --route-model claude-main=opus --route-effort claude-main=xhigh \
  --route-model codex-main=gpt-test --route-effort codex-main=high)"
jq -e '
  .quorum == 2 and .openrouter.requestCount == 2 and
  [.routes[].id] == ["claude-main","codex-main","qwen-a","qwen-b"] and
  (.routes[] | select(.id == "claude-main") | .effectiveModel == "opus" and .modelSource == "override" and .effectiveEffort == "xhigh") and
  (.routes[] | select(.id == "codex-main") | .effectiveModel == "gpt-test" and .effectiveEffort == "high") and
  ([.routes[].provider] | unique | sort) == ["anthropic","openai","qwen"]
' <<< "$mixed_json" >/dev/null || fail "mixed profile or route overrides were incorrect"

panel_sha="$(jq -r '.panelSha256' <<< "$mixed_json")"
openrouter_sha="$(jq -r '.openrouterSha256' <<< "$mixed_json")"
prompt_sha="$(jq -r '.promptSha256' <<< "$mixed_json")"
COMMON=(--config "$CONFIG" --panel mixed --prompt-file "$PROMPT" \
  --route-model claude-main=opus --route-effort claude-main=xhigh \
  --route-model codex-main=gpt-test --route-effort codex-main=high \
  --panel-sha256 "$panel_sha" --prompt-sha256 "$prompt_sha")

: > "$AGENT_LOG"
local_results="$TMP_DIR/local-results.json"
"${RUN_ENV[@]}" "$HELPER" run-local "${COMMON[@]}" > "$local_results"
jq -e --arg prompt "$prompt_sha" '
  [.[] | .id] == ["claude-main","codex-main"] and all(.[]; .status == "ok") and
  all(.[]; .promptSha256 == $prompt) and
  (.[0].effectiveModel == "opus" and .[0].effectiveEffort == "xhigh" and .[0].modelSource == "override") and
  (.[1].effectiveModel == "gpt-test" and .[1].effectiveEffort == "high")
' "$local_results" >/dev/null || fail "local results lost order, binding, or provenance"
expected_prompt_sha="$(printf '%s' 'identical private panel prompt' | sha256sum | awk '{print $1}')"
[[ "$(wc -l < "$AGENT_LOG" | tr -d '[:space:]')" -eq 2 ]] || fail "local routes were not called exactly once"
[[ "$(cut -d'|' -f3 "$AGENT_LOG" | sort -u)" == "$expected_prompt_sha" ]] || fail "local routes received different prompts"
grep -Fq 'claude|-p --tools Read,Grep,Glob --model opus --effort xhigh|' "$AGENT_LOG" || fail "Claude native flags were incorrect"
grep -Fq 'codex|exec --sandbox read-only --model gpt-test -c model_reasoning_effort="high" -|' "$AGENT_LOG" || fail "Codex native flags were incorrect"

# Fast routes cancel their watchdogs and reap each timer child before returning.
: > "$WATCHDOG_SLEEP_LOG"
"${RUN_ENV[@]}" "$HELPER" run-local "${COMMON[@]}" > "$TMP_DIR/watchdog-fast.json"
[[ -s "$WATCHDOG_SLEEP_LOG" ]] || fail "watchdog timer PIDs were not recorded"
while IFS= read -r timer_pid; do
  [[ -n "$timer_pid" ]] || continue
  if kill -0 "$timer_pid" >/dev/null 2>&1; then
    fail "watchdog timer process remained after fast route completion: $timer_pid"
  fi
done < "$WATCHDOG_SLEEP_LOG"

: > "$CURL_LOG"
declined_results="$TMP_DIR/declined-results.json"
"${RUN_ENV[@]}" "$HELPER" decline-openrouter "${COMMON[@]}" --openrouter-sha256 "$openrouter_sha" > "$declined_results"
jq -e 'length == 2 and all(.[]; .status == "declined")' "$declined_results" >/dev/null || fail "declined routes were not represented"
[[ ! -s "$CURL_LOG" ]] || fail "declining OpenRouter invoked curl"

declined_eval="$TMP_DIR/declined-eval.json"
printf '%s\n' "$mixed_json" > "$TMP_DIR/mixed-check.json"
"$HELPER" evaluate --policy consensus --check-file "$TMP_DIR/mixed-check.json" \
  --results-file "$local_results" --results-file "$declined_results" > "$declined_eval"
jq -e '
  .quorumMet and .consensusEligible and .successfulProviderCount == 2 and
  (.unavailableRoutes | length) == 2 and (.sameProviderCorroboration | length) == 0
' "$declined_eval" >/dev/null || fail "local-only quorum after decline was incorrect"

: > "$CURL_LOG"
openrouter_results="$TMP_DIR/openrouter-results.json"
"${RUN_ENV[@]}" "$HELPER" run-openrouter --confirmed "${COMMON[@]}" \
  --openrouter-sha256 "$openrouter_sha" > "$openrouter_results"
jq -e --arg prompt "$prompt_sha" '
  [.[] | .id] == ["qwen-a","qwen-b"] and all(.[]; .status == "ok" and .provider == "qwen") and
  all(.[]; .modelSource == "panel" and .effortSource == "native-default" and .promptSha256 == $prompt)
' "$openrouter_results" >/dev/null || fail "OpenRouter subset results lost order, binding, or normalized identity"
[[ "$(wc -l < "$CURL_LOG" | tr -d '[:space:]')" -eq 2 ]] || fail "OpenRouter subset was not invoked exactly once per route"

: > "$CURL_LOG"
wrong_openrouter_sha="$(printf '0%.0s' {1..64})"
expect_failure 'OpenRouter subset changed since check' "${RUN_ENV[@]}" "$HELPER" run-openrouter --confirmed \
  "${COMMON[@]}" --openrouter-sha256 "$wrong_openrouter_sha"
[[ ! -s "$CURL_LOG" ]] || fail "OpenRouter subset digest mismatch invoked curl"

approved_eval="$TMP_DIR/approved-eval.json"
"$HELPER" evaluate --policy quorum --check-file "$TMP_DIR/mixed-check.json" \
  --results-file "$local_results" --results-file "$openrouter_results" > "$approved_eval"
jq -e '
  .quorumMet and (.consensusEligible | not) and .successfulProviderCount == 3 and
  .sameProviderCorroboration == [{"provider":"qwen","routeIds":["qwen-a","qwen-b"]}]
' "$approved_eval" >/dev/null || fail "provider quorum or same-provider corroboration was incorrect"

# Different successful response text never changes mechanical quorum.
jq '.[0].response = "contradicts every other route"' "$openrouter_results" > "$TMP_DIR/contradictory.json"
"$HELPER" evaluate --policy consensus --check-file "$TMP_DIR/mixed-check.json" \
  --results-file "$local_results" --results-file "$TMP_DIR/contradictory.json" > "$TMP_DIR/contradictory-eval.json"
jq -e '.quorumMet and .consensusEligible and .interpretationRequired' "$TMP_DIR/contradictory-eval.json" >/dev/null || fail "mechanical evaluator attempted semantic consensus"

# Cross-prompt/stale results are rejected before quorum evaluation.
jq --arg wrong "$wrong_openrouter_sha" '.[0].promptSha256 = $wrong' "$local_results" > "$TMP_DIR/stale-local.json"
expect_failure 'result panel or prompt digest mismatch' "$HELPER" evaluate --policy quorum \
  --check-file "$TMP_DIR/mixed-check.json" --results-file "$TMP_DIR/stale-local.json"
jq 'del(.[0].promptSha256)' "$local_results" > "$TMP_DIR/unbound-local.json"
expect_failure 'result panel or prompt digest mismatch' "$HELPER" evaluate --policy quorum \
  --check-file "$TMP_DIR/mixed-check.json" --results-file "$TMP_DIR/unbound-local.json"

# A failing route is preserved without substitution.
printf '%s\n' fail > "$TMP_DIR/home/fake-agent-mode-codex"
"${RUN_ENV[@]}" "$HELPER" run-local "${COMMON[@]}" > "$TMP_DIR/failing-local.json"
rm -f "$TMP_DIR/home/fake-agent-mode-codex"
jq -e 'length == 2 and (.[1].status == "error" and .[1].exitCode == 9)' "$TMP_DIR/failing-local.json" >/dev/null || fail "local failure was not preserved"

# Empty output is an error and cannot satisfy provider quorum.
printf '%s\n' empty > "$TMP_DIR/home/fake-agent-mode-codex"
"${RUN_ENV[@]}" "$HELPER" run-local "${COMMON[@]}" > "$TMP_DIR/empty-local.json"
rm -f "$TMP_DIR/home/fake-agent-mode-codex"
jq -e '.[1].status == "error" and .[1].exitCode == 65 and (.[] | select(.id == "codex-main") | .error | contains("empty response"))' \
  "$TMP_DIR/empty-local.json" >/dev/null || fail "empty local output was not rejected"
"$HELPER" evaluate --policy quorum --check-file "$TMP_DIR/mixed-check.json" \
  --results-file "$TMP_DIR/empty-local.json" --results-file "$declined_results" > "$TMP_DIR/empty-eval.json"
jq -e '(.quorumMet | not) and .successfulProviderCount == 1' "$TMP_DIR/empty-eval.json" >/dev/null || \
  fail "empty local output satisfied quorum"

# Multi-megabyte local output is capped while streaming and becomes a small route error.
printf '%s\n' oversized > "$TMP_DIR/home/fake-agent-mode-claude"
"${RUN_ENV[@]}" "$HELPER" run-local "${COMMON[@]}" > "$TMP_DIR/oversized-local.json"
rm -f "$TMP_DIR/home/fake-agent-mode-claude"
jq -e '.[0].status == "error" and .[0].exitCode == 66 and .[0].response == null and (.[] | select(.id == "claude-main") | .error | contains("65536-byte"))' \
  "$TMP_DIR/oversized-local.json" >/dev/null || fail "oversized local output was not bounded"
(( $(wc -c < "$TMP_DIR/oversized-local.json") < 70000 )) || fail "oversized stdout leaked into result data"

# Multi-megabyte stderr is capped while streaming as well.
printf '%s\n' oversized-stderr > "$TMP_DIR/home/fake-agent-mode-codex"
"${RUN_ENV[@]}" "$HELPER" run-local "${COMMON[@]}" > "$TMP_DIR/oversized-stderr-local.json"
rm -f "$TMP_DIR/home/fake-agent-mode-codex"
jq -e '.[1].status == "error" and .[1].exitCode == 67 and ((.[1].error | length) == 8192)' \
  "$TMP_DIR/oversized-stderr-local.json" >/dev/null || fail "oversized local stderr was not bounded"
(( $(wc -c < "$TMP_DIR/oversized-stderr-local.json") < 20000 )) || fail "oversized stderr leaked into result data"

# A TERM-ignoring local route is forcibly killed after the timeout grace period.
printf '%s\n' ignore-term > "$TMP_DIR/home/fake-agent-mode-codex"
"${RUN_ENV[@]}" "$HELPER" run-local "${COMMON[@]}" --timeout 1 > "$TMP_DIR/timeout-local.json"
rm -f "$TMP_DIR/home/fake-agent-mode-codex"
jq -e '.[1].status == "error" and .[1].exitCode == 124 and (.[] | select(.id == "codex-main") | .error | contains("timed out"))' \
  "$TMP_DIR/timeout-local.json" >/dev/null || fail "TERM-ignoring route was not forcibly timed out"

# The no-setsid path creates a process group, kills descendants that retain FIFO descriptors,
# and returns within the timeout plus the one-second kill grace.
printf '%s\n' descendant-ignore-term > "$TMP_DIR/home/fake-agent-mode-codex"
SECONDS=0
"${NO_SETSID_RUN_ENV[@]}" "$HELPER" run-local "${COMMON[@]}" --timeout 1 > "$TMP_DIR/no-setsid-timeout.json"
elapsed=$SECONDS
rm -f "$TMP_DIR/home/fake-agent-mode-codex"
(( elapsed <= 4 )) || fail "no-setsid timeout took ${elapsed}s"
jq -e '.[1].status == "error" and .[1].exitCode == 124 and (.[] | select(.id == "codex-main") | .error | contains("timed out"))' \
  "$TMP_DIR/no-setsid-timeout.json" >/dev/null || fail "no-setsid descendant route was not timed out"
for pid_file in "$TMP_DIR/home/route-parent-pid-codex" "$TMP_DIR/home/route-descendant-pid-codex"; do
  [[ -s "$pid_file" ]] || fail "route process PID was not recorded: $pid_file"
  route_pid="$(cat "$pid_file")"
  if kill -0 "$route_pid" >/dev/null 2>&1; then
    fail "no-setsid route process remained after timeout: $route_pid"
  fi
done
rm -f "$TMP_DIR/home/route-parent-pid-codex" "$TMP_DIR/home/route-descendant-pid-codex"

# Missing Gemini is unavailable, not substituted.
local_legacy_json="$("${NO_GEMINI_ENV[@]}" "$HELPER" check --config "$TMP_DIR/no-config.json" --panel local-legacy --prompt-file "$PROMPT")"
legacy_local_sha="$(jq -r '.panelSha256' <<< "$local_legacy_json")"
"${NO_GEMINI_ENV[@]}" "$HELPER" run-local --config "$TMP_DIR/no-config.json" --panel local-legacy \
  --prompt-file "$PROMPT" --panel-sha256 "$legacy_local_sha" --prompt-sha256 "$prompt_sha" > "$TMP_DIR/missing-local.json"
jq -e 'length == 3 and (.[2].id == "gemini" and .[2].status == "unavailable")' "$TMP_DIR/missing-local.json" >/dev/null || fail "missing local route was not preserved"

expect_failure 'prompt changed since check' bash -c '
  printf changed >> "$1"
  shift
  "$@"
' _ "$PROMPT" "${RUN_ENV[@]}" "$HELPER" run-openrouter --confirmed "${COMMON[@]}" --openrouter-sha256 "$openrouter_sha"
printf '%s\n' 'identical private panel prompt' > "$PROMPT"

MUTATED_CONFIG="$TMP_DIR/mutated.json"
jq '.profiles.mixed.routes[2].model = "openrouter/qwen/mutated"' "$CONFIG" > "$MUTATED_CONFIG"
expect_failure 'panel changed since check' "${RUN_ENV[@]}" "$HELPER" run-local \
  --config "$MUTATED_CONFIG" --panel mixed --prompt-file "$PROMPT" \
  --route-model claude-main=opus --route-effort claude-main=xhigh \
  --route-model codex-main=gpt-test --route-effort codex-main=high \
  --panel-sha256 "$panel_sha" --prompt-sha256 "$prompt_sha"

expect_failure 'OpenRouter route models come from the selected panel' "${RUN_ENV[@]}" "$HELPER" check \
  --config "$CONFIG" --panel mixed --route-model qwen-a=other
expect_failure 'panel routes or limits are invalid' "${RUN_ENV[@]}" "$HELPER" check \
  --config "$CONFIG" --panel invalid-gemini-effort
expect_failure 'unsupported Claude effort' "${RUN_ENV[@]}" "$HELPER" check \
  --config "$CONFIG" --panel mixed --route-effort claude-main=minimal
expect_failure 'unknown route override id' "${RUN_ENV[@]}" "$HELPER" check \
  --config "$CONFIG" --panel mixed --route-model absent=model

BOTH_CONFIG="$TMP_DIR/both.json"
jq '.profiles.mixed.models = .profiles.legacy.models' "$CONFIG" > "$BOTH_CONFIG"
expect_failure 'exactly one of models or routes' "${RUN_ENV[@]}" "$HELPER" check --config "$BOTH_CONFIG" --panel mixed

printf '%s\n' 'review-panel tests passed'
