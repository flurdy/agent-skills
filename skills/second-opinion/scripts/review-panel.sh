#!/usr/bin/env bash
# Resolve and execute configurable second-opinion review panels.
# OpenRouter requests remain delegated to the hardened openrouter-panel.sh helper.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly OPENROUTER_HELPER="$SCRIPT_DIR/openrouter-panel.sh"
readonly DEFAULT_CONFIG_PATH="${HOME}/.agents/second-opinion/config.json"
readonly DEFAULT_PANEL="focused"
readonly HARD_MAX_ROUTES=8
readonly HARD_MAX_PARALLEL=4
readonly HARD_MAX_PROMPT_BYTES=65536
readonly HARD_MAX_OUTPUT_TOKENS=2000
readonly HARD_MAX_LOCAL_OUTPUT_BYTES=65536
readonly HARD_MAX_TIMEOUT_SECONDS=600

usage() {
  cat <<'USAGE'
Usage:
  review-panel.sh check [--panel NAME] [--config FILE] [--prompt-file FILE]
                        [--route-model ID=MODEL] [--route-effort ID=EFFORT]...
  review-panel.sh run-local --prompt-file FILE --panel-sha256 DIGEST --prompt-sha256 DIGEST
                            [panel and route override options] [--timeout SECONDS]
  review-panel.sh run-openrouter --confirmed --prompt-file FILE --panel-sha256 DIGEST
                                 --openrouter-sha256 DIGEST --prompt-sha256 DIGEST
                                 [panel and route override options] [--timeout SECONDS]
  review-panel.sh decline-openrouter --prompt-file FILE --panel-sha256 DIGEST
                                     --openrouter-sha256 DIGEST --prompt-sha256 DIGEST
                                     [panel and route override options]
  review-panel.sh evaluate --policy quorum|consensus --check-file FILE --results-file FILE...

Profiles live under version-1 config "profiles". A profile contains either legacy
OpenRouter "models" or policy-neutral "routes", never both. Built-in focused is
used when absent from config. The local-only local-legacy panel is reserved and
cannot be overridden. Local response and error capture are bounded while streaming.
USAGE
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required"
}

sha256_stream() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 | awk '{print $1}'
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 | awk '{print $NF}'
  else
    return 1
  fi
}

sha256_file() {
  sha256_stream < "$1"
}

built_in_panel() {
  case "$1" in
    focused)
      cat <<'JSON'
{"quorum":2,"routes":[{"id":"claude","kind":"local","agent":"claude","role":"independent review"},{"id":"codex","kind":"local","agent":"codex","role":"independent review"}],"limits":{"maxParallel":2,"maxPromptBytes":65536,"maxOutputTokensPerModel":2000,"defaultTimeoutSeconds":180}}
JSON
      ;;
    local-legacy)
      cat <<'JSON'
{"quorum":2,"routes":[{"id":"claude","kind":"local","agent":"claude","role":"independent review"},{"id":"codex","kind":"local","agent":"codex","role":"independent review"},{"id":"gemini","kind":"local","agent":"gemini","role":"long-context review"}],"limits":{"maxParallel":3,"maxPromptBytes":65536,"maxOutputTokensPerModel":2000,"defaultTimeoutSeconds":180}}
JSON
      ;;
    *) return 1 ;;
  esac
}

parse_panel_options() {
  CONFIG_PATH="$DEFAULT_CONFIG_PATH"
  PANEL_NAME="$DEFAULT_PANEL"
  PROMPT_FILE=""
  ROUTE_MODELS=()
  ROUTE_EFFORTS=()
  REMAINING_ARGS=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --config)
        [[ $# -ge 2 ]] || die "--config requires a path"
        CONFIG_PATH="$2"
        shift 2
        ;;
      --panel)
        [[ $# -ge 2 ]] || die "--panel requires a name"
        PANEL_NAME="$2"
        shift 2
        ;;
      --prompt-file)
        [[ $# -ge 2 ]] || die "--prompt-file requires a path"
        PROMPT_FILE="$2"
        shift 2
        ;;
      --route-model)
        [[ $# -ge 2 ]] || die "--route-model requires ID=MODEL"
        ROUTE_MODELS+=("$2")
        shift 2
        ;;
      --route-effort)
        [[ $# -ge 2 ]] || die "--route-effort requires ID=EFFORT"
        ROUTE_EFFORTS+=("$2")
        shift 2
        ;;
      *)
        REMAINING_ARGS+=("$1")
        shift
        ;;
    esac
  done
}

load_raw_profile() {
  local configured=""
  if [[ -f "$CONFIG_PATH" ]]; then
    jq -e '.version == 1 and (.profiles | type == "object")' "$CONFIG_PATH" >/dev/null 2>&1 || \
      die "config must be valid JSON with version 1 and a profiles object: $CONFIG_PATH"
  fi

  if [[ "$PANEL_NAME" == "local-legacy" ]]; then
    RAW_PROFILE="$(built_in_panel "$PANEL_NAME")"
    PROFILE_SOURCE="reserved-built-in"
    return
  fi

  if [[ -f "$CONFIG_PATH" ]]; then
    configured="$(jq -c --arg panel "$PANEL_NAME" '.profiles[$panel] // empty' "$CONFIG_PATH")"
  fi

  if [[ -n "$configured" ]]; then
    RAW_PROFILE="$configured"
    PROFILE_SOURCE="config"
    return
  fi
  RAW_PROFILE="$(built_in_panel "$PANEL_NAME")" || {
    [[ -f "$CONFIG_PATH" ]] || die "config file not found: $CONFIG_PATH"
    die "panel not found: $PANEL_NAME"
  }
  PROFILE_SOURCE="built-in"
}

normalize_profile() {
  load_raw_profile

  if ! jq -e '
    (type == "object") and
    (((.models | type == "array") and (has("routes") | not)) or
     ((.routes | type == "array") and (has("models") | not)))
  ' <<< "$RAW_PROFILE" >/dev/null 2>&1; then
    die "panel must contain exactly one of models or routes"
  fi

  if jq -e 'has("models")' <<< "$RAW_PROFILE" >/dev/null; then
    if ! jq -e '
      (.models | length >= 1 and length <= 8) and
      all(.models[];
        (.model | type == "string" and test("^openrouter/[A-Za-z0-9][A-Za-z0-9._-]*/.+$")) and
        (.vendor | type == "string" and length > 0) and
        (.role | type == "string" and length > 0)
      )
    ' <<< "$RAW_PROFILE" >/dev/null 2>&1; then
      die "legacy models must contain 1-$HARD_MAX_ROUTES canonical OpenRouter entries"
    fi
    PANEL_JSON="$(jq -c '
      (.models | map(.model | sub("^openrouter/"; "") | split("/")[0] | ascii_downcase) | unique | length) as $providers |
      {
        quorum: (.quorum // ([2, $providers] | min)),
        routes: [.models | to_entries[] | {
          id: ("openrouter-" + ((.key + 1) | tostring)),
          kind: "openrouter",
          model: .value.model,
          vendor: .value.vendor,
          role: .value.role
        }],
        limits: .limits
      }
    ' <<< "$RAW_PROFILE")"
    LEGACY_PROFILE=true
  else
    PANEL_JSON="$(jq -c '{quorum, routes, limits}' <<< "$RAW_PROFILE")"
    LEGACY_PROFILE=false
  fi

  validate_and_apply_overrides
}

validate_limits_and_routes() {
  if ! jq -e \
    --argjson max_routes "$HARD_MAX_ROUTES" \
    --argjson max_parallel "$HARD_MAX_PARALLEL" \
    --argjson max_prompt "$HARD_MAX_PROMPT_BYTES" \
    --argjson max_output "$HARD_MAX_OUTPUT_TOKENS" \
    --argjson max_timeout "$HARD_MAX_TIMEOUT_SECONDS" '
    (.routes | type == "array" and length >= 1 and length <= $max_routes) and
    (.limits | type == "object") and
    (.limits.maxParallel | type == "number" and floor == . and . >= 1 and . <= $max_parallel) and
    (.limits.maxPromptBytes | type == "number" and floor == . and . >= 1 and . <= $max_prompt) and
    (.limits.maxOutputTokensPerModel | type == "number" and floor == . and . >= 1 and . <= $max_output) and
    (.limits.defaultTimeoutSeconds | type == "number" and floor == . and . >= 1 and . <= $max_timeout) and
    all(.routes[];
      (.id | type == "string" and test("^[A-Za-z0-9][A-Za-z0-9._-]*$")) and
      (.role | type == "string" and length > 0) and
      (
        (.kind == "local" and (.agent == "claude" or .agent == "codex" or .agent == "gemini") and
          ((has("model") | not) or (.model | type == "string" and length > 0)) and
          (
            (has("effort") | not) or
            (.agent == "claude" and (.effort | test("^(low|medium|high|xhigh|max)$"))) or
            (.agent == "codex" and (.effort | test("^(minimal|low|medium|high|xhigh)$")))
          ))
        or
        (.kind == "openrouter" and
          (.model | type == "string" and test("^openrouter/[A-Za-z0-9][A-Za-z0-9._-]*/.+$")) and
          (.vendor | type == "string" and length > 0) and
          (has("agent") | not) and (has("effort") | not))
      )
    ) and
    ([.routes[].id] | unique | length) == (.routes | length) and
    ([.routes[] | if .kind == "local" then ("local/" + .agent + "/" + (.model // "native-default")) else .model end] | unique | length) == (.routes | length)
  ' <<< "$PANEL_JSON" >/dev/null 2>&1; then
    die "panel routes or limits are invalid, duplicated, or exceed compiled ceilings"
  fi

  PANEL_JSON="$(jq -c '
    .routes |= map(
      . + {
        provider: (if .kind == "local" then ({claude:"anthropic",codex:"openai",gemini:"google"}[.agent]) else (.model | sub("^openrouter/"; "") | split("/")[0] | ascii_downcase) end),
        effectiveModel: (.model // "native-default"),
        modelSource: (if has("model") then "panel" else "native-default" end),
        effectiveEffort: (.effort // "native-default"),
        effortSource: (if has("effort") then "panel" else "native-default" end)
      }
    )
  ' <<< "$PANEL_JSON")"

  local provider_count
  provider_count="$(jq -r '[.routes[].provider] | unique | length' <<< "$PANEL_JSON")"
  if ! jq -e --argjson providers "$provider_count" '
    (.quorum | type == "number" and floor == . and . >= 1 and . <= $providers)
  ' <<< "$PANEL_JSON" >/dev/null 2>&1; then
    die "panel quorum must be an integer between 1 and the unique provider count ($provider_count)"
  fi
}

apply_model_override() {
  local override="$1"
  [[ "$override" == *=* ]] || die "--route-model requires ID=MODEL"
  local id="${override%%=*}"
  local value="${override#*=}"
  [[ -n "$id" && -n "$value" ]] || die "--route-model requires non-empty ID and MODEL"
  jq -e --arg id "$id" 'any(.routes[]; .id == $id)' <<< "$PANEL_JSON" >/dev/null || \
    die "unknown route override id: $id"
  jq -e --arg id "$id" 'any(.routes[]; .id == $id and .kind == "local")' <<< "$PANEL_JSON" >/dev/null || \
    die "OpenRouter route models come from the selected panel and cannot be overridden: $id"
  PANEL_JSON="$(jq -c --arg id "$id" --arg value "$value" '
    .routes |= map(if .id == $id then .model = $value | .effectiveModel = $value | .modelSource = "override" else . end)
  ' <<< "$PANEL_JSON")"
}

apply_effort_override() {
  local override="$1"
  [[ "$override" == *=* ]] || die "--route-effort requires ID=EFFORT"
  local id="${override%%=*}"
  local value="${override#*=}"
  [[ -n "$id" && -n "$value" ]] || die "--route-effort requires non-empty ID and EFFORT"
  local agent
  agent="$(jq -r --arg id "$id" '.routes[] | select(.id == $id) | .agent // empty' <<< "$PANEL_JSON")"
  [[ -n "$agent" ]] || {
    jq -e --arg id "$id" 'any(.routes[]; .id == $id)' <<< "$PANEL_JSON" >/dev/null || die "unknown route override id: $id"
    die "effort is unsupported for OpenRouter routes: $id"
  }
  case "$agent" in
    claude)
      [[ "$value" =~ ^(low|medium|high|xhigh|max)$ ]] || die "unsupported Claude effort for $id: $value"
      ;;
    codex)
      [[ "$value" =~ ^(minimal|low|medium|high|xhigh)$ ]] || die "unsupported Codex effort for $id: $value"
      ;;
    gemini)
      die "effort is unsupported for Gemini routes: $id"
      ;;
  esac
  PANEL_JSON="$(jq -c --arg id "$id" --arg value "$value" '
    .routes |= map(if .id == $id then .effort = $value | .effectiveEffort = $value | .effortSource = "override" else . end)
  ' <<< "$PANEL_JSON")"
}

validate_and_apply_overrides() {
  validate_limits_and_routes
  local override
  for override in "${ROUTE_MODELS[@]}"; do
    apply_model_override "$override"
  done
  for override in "${ROUTE_EFFORTS[@]}"; do
    apply_effort_override "$override"
  done
  validate_limits_and_routes
  for override in "${ROUTE_MODELS[@]}"; do
    apply_model_override "$override"
  done
  for override in "${ROUTE_EFFORTS[@]}"; do
    apply_effort_override "$override"
  done

  PANEL_CANONICAL="$(jq -cS . <<< "$PANEL_JSON")"
  PANEL_SHA256="$(printf '%s' "$PANEL_CANONICAL" | sha256_stream)" || die "a SHA-256 command is required"
  OPENROUTER_JSON="$(jq -cS '{routes: [.routes[] | select(.kind == "openrouter")], limits}' <<< "$PANEL_JSON")"
  OPENROUTER_SHA256="$(printf '%s' "$OPENROUTER_JSON" | sha256_stream)" || die "a SHA-256 command is required"
}

prompt_digest() {
  if [[ -z "$PROMPT_FILE" ]]; then
    printf ''
    return
  fi
  [[ -f "$PROMPT_FILE" ]] || die "prompt file not found: $PROMPT_FILE"
  [[ -s "$PROMPT_FILE" ]] || die "prompt file is empty"
  local bytes
  bytes="$(wc -c < "$PROMPT_FILE" | tr -d '[:space:]')"
  local max_bytes
  max_bytes="$(jq -r '.limits.maxPromptBytes' <<< "$PANEL_JSON")"
  (( bytes <= max_bytes )) || die "prompt is $bytes bytes; panel maximum is $max_bytes"
  sha256_file "$PROMPT_FILE" || die "a SHA-256 command is required"
}

snapshot_prompt() {
  local destination="$1"
  cat "$PROMPT_FILE" > "$destination"
  chmod 600 "$destination"
  local snapshot_sha
  snapshot_sha="$(sha256_file "$destination")" || die "a SHA-256 command is required"
  [[ "$snapshot_sha" == "$EXPECTED_PROMPT_SHA" ]] || \
    die "prompt changed while being snapshotted; reassemble and obtain fresh approval"
}

check_panel() {
  parse_panel_options "$@"
  [[ ${#REMAINING_ARGS[@]} -eq 0 ]] || die "unknown check argument: ${REMAINING_ARGS[0]}"
  require_command jq
  normalize_profile
  local prompt_sha
  prompt_sha="$(prompt_digest)"

  local openrouter_auth="missing" openrouter_curl="missing" openrouter_availability="unavailable"
  [[ -n "${OPENROUTER_API_KEY:-}" ]] && openrouter_auth="configured (not network-verified)"
  command -v curl >/dev/null 2>&1 && openrouter_curl="available"
  if [[ "$openrouter_auth" != "missing" && "$openrouter_curl" == "available" ]]; then
    openrouter_availability="requires-consent"
  fi

  local routes
  routes="$(jq -c --arg openrouter_availability "$openrouter_availability" '
    [.routes[] | . + {
      availability: (if .kind == "openrouter" then $openrouter_availability else "unchecked" end)
    }]
  ' <<< "$PANEL_JSON")"
  local local_routes openrouter_routes
  local_routes="$(jq '[.[] | select(.kind == "local")]' <<< "$routes")"
  openrouter_routes="$(jq '[.[] | select(.kind == "openrouter")]' <<< "$routes")"

  local route_count
  route_count="$(jq 'length' <<< "$local_routes")"
  if (( route_count > 0 )); then
    local index agent availability
    for ((index=0; index<route_count; index++)); do
      agent="$(jq -r --argjson i "$index" '.[$i].agent' <<< "$local_routes")"
      if command -v "$agent" >/dev/null 2>&1; then availability="installed (auth-unverified)"; else availability="unavailable"; fi
      local_routes="$(jq -c --argjson i "$index" --arg availability "$availability" '.[$i].availability = $availability' <<< "$local_routes")"
    done
  fi

  jq -n \
    --arg panel "$PANEL_NAME" \
    --arg source "$PROFILE_SOURCE" \
    --argjson legacy "$LEGACY_PROFILE" \
    --arg panel_sha256 "$PANEL_SHA256" \
    --arg openrouter_sha256 "$OPENROUTER_SHA256" \
    --arg prompt_sha256 "$prompt_sha" \
    --argjson panel_data "$PANEL_JSON" \
    --argjson local_routes "$local_routes" \
    --argjson openrouter_routes "$openrouter_routes" \
    --arg openrouter_auth "$openrouter_auth" \
    --arg openrouter_curl "$openrouter_curl" \
    --arg openrouter_availability "$openrouter_availability" '
    {
      ready: true,
      panel: $panel,
      source: $source,
      legacy: $legacy,
      quorum: $panel_data.quorum,
      limits: $panel_data.limits,
      panelSha256: $panel_sha256,
      openrouterSha256: $openrouter_sha256,
      promptSha256: (if $prompt_sha256 == "" then null else $prompt_sha256 end),
      routes: ($panel_data.routes | map(. as $route |
        (($local_routes + $openrouter_routes)[] | select(.id == $route.id))
      )),
      localRoutes: $local_routes,
      openrouterRoutes: $openrouter_routes,
      openrouter: {
        requestCount: ($openrouter_routes | length),
        auth: (if ($openrouter_routes | length) == 0 then "not-required" else $openrouter_auth end),
        curl: (if ($openrouter_routes | length) == 0 then "not-required" else $openrouter_curl end),
        runnable: (($openrouter_routes | length) == 0 or $openrouter_availability == "requires-consent"),
        consentRequired: (($openrouter_routes | length) > 0)
      }
    }'
}

parse_run_args() {
  local require_openrouter_digest="$1"
  shift
  CONFIRMED=false
  EXPECTED_PANEL_SHA=""
  EXPECTED_OPENROUTER_SHA=""
  EXPECTED_PROMPT_SHA=""
  TIMEOUT_OVERRIDE=""

  parse_panel_options "$@"
  if [[ ${#REMAINING_ARGS[@]} -gt 0 ]]; then set -- "${REMAINING_ARGS[@]}"; else set --; fi
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --confirmed) CONFIRMED=true; shift ;;
      --panel-sha256) [[ $# -ge 2 ]] || die "--panel-sha256 requires a digest"; EXPECTED_PANEL_SHA="$2"; shift 2 ;;
      --openrouter-sha256) [[ $# -ge 2 ]] || die "--openrouter-sha256 requires a digest"; EXPECTED_OPENROUTER_SHA="$2"; shift 2 ;;
      --prompt-sha256) [[ $# -ge 2 ]] || die "--prompt-sha256 requires a digest"; EXPECTED_PROMPT_SHA="$2"; shift 2 ;;
      --timeout) [[ $# -ge 2 ]] || die "--timeout requires seconds"; TIMEOUT_OVERRIDE="$2"; shift 2 ;;
      *) die "unknown run argument: $1" ;;
    esac
  done

  [[ -n "$PROMPT_FILE" ]] || die "--prompt-file is required"
  [[ "$EXPECTED_PANEL_SHA" =~ ^[a-f0-9]{64}$ ]] || die "--panel-sha256 must be the digest from check"
  [[ "$EXPECTED_PROMPT_SHA" =~ ^[a-f0-9]{64}$ ]] || die "--prompt-sha256 must be the digest from check"
  if [[ "$require_openrouter_digest" == true ]]; then
    [[ "$EXPECTED_OPENROUTER_SHA" =~ ^[a-f0-9]{64}$ ]] || die "--openrouter-sha256 must be the digest from check"
  fi
  require_command jq
  normalize_profile
  local actual_prompt_sha
  actual_prompt_sha="$(prompt_digest)"
  [[ "$PANEL_SHA256" == "$EXPECTED_PANEL_SHA" ]] || die "panel changed since check; rerun check"
  [[ "$actual_prompt_sha" == "$EXPECTED_PROMPT_SHA" ]] || die "prompt changed since check; reassemble and obtain fresh approval"
  if [[ "$require_openrouter_digest" == true ]]; then
    [[ "$OPENROUTER_SHA256" == "$EXPECTED_OPENROUTER_SHA" ]] || die "OpenRouter subset changed since check; obtain fresh consent"
  fi
  if [[ -n "$TIMEOUT_OVERRIDE" ]]; then
    [[ "$TIMEOUT_OVERRIDE" =~ ^[0-9]+$ ]] || die "timeout must be an integer number of seconds"
    (( TIMEOUT_OVERRIDE >= 1 && TIMEOUT_OVERRIDE <= HARD_MAX_TIMEOUT_SECONDS )) || die "timeout must be between 1 and $HARD_MAX_TIMEOUT_SECONDS seconds"
  fi
}

write_local_result() {
  local route_json="$1"
  local status="$2"
  local response_file="$3"
  local error_file="$4"
  local exit_code="$5"
  local result_file="$6"
  jq -n \
    --argjson route "$route_json" \
    --arg status "$status" \
    --rawfile response "$response_file" \
    --rawfile error "$error_file" \
    --argjson exit_code "$exit_code" \
    --arg panel_sha256 "$PANEL_SHA256" \
    --arg prompt_sha256 "$EXPECTED_PROMPT_SHA" '
    $route + {
      status: $status,
      response: (if $status == "ok" then $response else null end),
      error: (if $status == "ok" then null elif $error == "" then "route unavailable or failed" else $error end),
      exitCode: $exit_code,
      panelSha256: $panel_sha256,
      promptSha256: $prompt_sha256
    }' > "$result_file"
}

truncate_file() {
  local file="$1"
  local maximum="$2"
  local temporary="$file.bounded"
  head -c "$maximum" "$file" > "$temporary"
  mv "$temporary" "$file"
}

run_local_route() {
  local route_json="$1"
  local index="$2"
  local work_dir="$3"
  local timeout_seconds="$4"
  local prompt_snapshot="$5"
  local agent model effort
  agent="$(jq -r '.agent' <<< "$route_json")"
  model="$(jq -r '.effectiveModel' <<< "$route_json")"
  effort="$(jq -r '.effectiveEffort' <<< "$route_json")"
  local response_file="$work_dir/response-$index.txt"
  local error_file="$work_dir/error-$index.txt"
  local result_file="$work_dir/result-$index.json"
  : > "$response_file"
  : > "$error_file"

  if ! command -v "$agent" >/dev/null 2>&1; then
    printf '%s is not installed' "$agent" > "$error_file"
    write_local_result "$route_json" "unavailable" "$response_file" "$error_file" 127 "$result_file"
    return
  fi

  local -a command=(env -i)
  local environment_name environment_value
  for environment_name in HOME PATH USER LOGNAME SHELL TERM TMPDIR \
    XDG_CONFIG_HOME XDG_CACHE_HOME XDG_DATA_HOME XDG_STATE_HOME \
    CLAUDE_CONFIG_DIR CODEX_HOME GEMINI_CLI_HOME LANG LC_ALL; do
    if environment_value="$(printenv "$environment_name" 2>/dev/null)"; then
      command+=("$environment_name=$environment_value")
    fi
  done
  case "$agent" in
    claude)
      command+=(claude -p --tools "Read,Grep,Glob")
      [[ "$model" == "native-default" ]] || command+=(--model "$model")
      [[ "$effort" == "native-default" ]] || command+=(--effort "$effort")
      ;;
    codex)
      command+=(codex exec --sandbox read-only)
      [[ "$model" == "native-default" ]] || command+=(--model "$model")
      [[ "$effort" == "native-default" ]] || command+=(-c "model_reasoning_effort=\"$effort\"")
      command+=(-)
      ;;
    gemini)
      command+=(gemini --sandbox -o text)
      [[ "$model" == "native-default" ]] || command+=(-m "$model")
      ;;
    *) die "unsupported local agent: $agent" ;;
  esac

  local exit_code=0 status="ok"
  local timeout_marker="$work_dir/timeout-$index"
  local response_pipe="$work_dir/response-$index.pipe"
  local error_pipe="$work_dir/error-$index.pipe"
  local error_limit=8192
  mkfifo "$response_pipe" "$error_pipe"
  head -c $((HARD_MAX_LOCAL_OUTPUT_BYTES + 1)) < "$response_pipe" > "$response_file" &
  local response_reader_pid=$!
  head -c $((error_limit + 1)) < "$error_pipe" > "$error_file" &
  local error_reader_pid=$!

  local signal_target
  if [[ "${REVIEW_PANEL_FORCE_NO_SETSID:-}" != "1" ]] && command -v setsid >/dev/null 2>&1; then
    setsid "${command[@]}" < "$prompt_snapshot" > "$response_pipe" 2> "$error_pipe" &
    signal_target="-$!"
  else
    set -m
    "${command[@]}" < "$prompt_snapshot" > "$response_pipe" 2> "$error_pipe" &
    signal_target="-$!"
    set +m
  fi
  local command_pid=$!
  (
    timer_pid=""
    cleanup_timer() {
      local pid="$timer_pid"
      timer_pid=""
      if [[ -n "$pid" ]]; then
        kill "$pid" >/dev/null 2>&1 || true
        wait "$pid" 2>/dev/null || true
      fi
    }
    trap 'cleanup_timer; exit 0' TERM INT
    trap cleanup_timer EXIT

    sleep "$timeout_seconds" &
    timer_pid=$!
    wait "$timer_pid" 2>/dev/null || exit 0
    timer_pid=""

    if kill -0 "$command_pid" >/dev/null 2>&1; then
      : > "$timeout_marker"
      kill -TERM -- "$signal_target" >/dev/null 2>&1 || true
      sleep 1 &
      timer_pid=$!
      wait "$timer_pid" 2>/dev/null || exit 0
      timer_pid=""
      kill -KILL -- "$signal_target" >/dev/null 2>&1 || true
    fi
  ) &
  local watchdog_pid=$!
  wait "$command_pid" 2>/dev/null || exit_code=$?
  if [[ -f "$timeout_marker" ]]; then
    wait "$watchdog_pid" 2>/dev/null || true
    kill "$response_reader_pid" "$error_reader_pid" >/dev/null 2>&1 || true
  else
    kill -TERM "$watchdog_pid" >/dev/null 2>&1 || true
    wait "$watchdog_pid" 2>/dev/null || true
  fi
  wait "$response_reader_pid" 2>/dev/null || true
  wait "$error_reader_pid" 2>/dev/null || true

  local response_bytes error_bytes
  response_bytes="$(wc -c < "$response_file" | tr -d '[:space:]')"
  error_bytes="$(wc -c < "$error_file" | tr -d '[:space:]')"
  if [[ -f "$timeout_marker" ]]; then
    status="error"
    exit_code=124
    printf 'route timed out after %s seconds' "$timeout_seconds" > "$error_file"
  elif (( response_bytes > HARD_MAX_LOCAL_OUTPUT_BYTES )); then
    status="error"
    exit_code=66
    : > "$response_file"
    printf 'route output exceeded the %s-byte local capture limit' "$HARD_MAX_LOCAL_OUTPUT_BYTES" > "$error_file"
  elif (( error_bytes > error_limit )); then
    status="error"
    exit_code=67
    truncate_file "$error_file" "$error_limit"
  elif (( exit_code != 0 )); then
    status="error"
  elif [[ ! -s "$response_file" ]]; then
    status="error"
    exit_code=65
    printf 'route returned an empty response' > "$error_file"
  fi
  write_local_result "$route_json" "$status" "$response_file" "$error_file" "$exit_code" "$result_file"
}

run_local() {
  parse_run_args false "$@"
  local timeout_seconds
  timeout_seconds="${TIMEOUT_OVERRIDE:-$(jq -r '.limits.defaultTimeoutSeconds' <<< "$PANEL_JSON")}"
  local max_parallel
  max_parallel="$(jq -r '.limits.maxParallel' <<< "$PANEL_JSON")"
  local routes_json count
  routes_json="$(jq -c '[.routes[] | select(.kind == "local")]' <<< "$PANEL_JSON")"
  count="$(jq 'length' <<< "$routes_json")"
  [[ "$count" -gt 0 ]] || { printf '[]\n'; return; }

  WORK_DIR="$(mktemp -d)"
  chmod 700 "$WORK_DIR"
  trap 'rm -rf "$WORK_DIR"' EXIT
  umask 077
  local prompt_snapshot="$WORK_DIR/prompt"
  snapshot_prompt "$prompt_snapshot"

  local index=0
  while (( index < count )); do
    local -a pids=()
    local launched=0
    while (( index < count && launched < max_parallel )); do
      run_local_route "$(jq -c --argjson i "$index" '.[$i]' <<< "$routes_json")" "$index" "$WORK_DIR" "$timeout_seconds" "$prompt_snapshot" &
      pids+=("$!")
      index=$((index + 1))
      launched=$((launched + 1))
    done
    local pid
    for pid in "${pids[@]}"; do wait "$pid"; done
  done
  jq -s --argjson order "$(jq 'to_entries | map({key:.value.id,value:.key}) | from_entries' <<< "$routes_json")" 'sort_by(.id as $id | $order[$id])' "$WORK_DIR"/result-*.json
}

openrouter_config() {
  jq -n --argjson subset "$OPENROUTER_JSON" '
    {version: 1, profiles: {selected: {
      models: [$subset.routes[] | {model, vendor, role}],
      limits: $subset.limits
    }}}
  '
}

run_openrouter() {
  parse_run_args true "$@"
  [[ "$CONFIRMED" == true ]] || die "refusing metered OpenRouter requests without --confirmed"
  local count
  count="$(jq '.routes | length' <<< "$OPENROUTER_JSON")"
  [[ "$count" -gt 0 ]] || { printf '[]\n'; return; }

  local config_file check_json subset_profile_sha timeout_seconds
  local prompt_snapshot routes_file raw_results_file
  WORK_DIR="$(mktemp -d)"
  chmod 700 "$WORK_DIR"
  trap 'rm -rf "$WORK_DIR"' EXIT
  umask 077
  prompt_snapshot="$WORK_DIR/prompt"
  snapshot_prompt "$prompt_snapshot"
  config_file="$WORK_DIR/openrouter-config.json"
  routes_file="$WORK_DIR/routes.json"
  raw_results_file="$WORK_DIR/openrouter-results.json"
  openrouter_config > "$config_file"
  jq '.routes' <<< "$OPENROUTER_JSON" > "$routes_file"
  check_json="$($OPENROUTER_HELPER check --config "$config_file" --profile selected)"
  jq -e '.ready == true' <<< "$check_json" >/dev/null || die "OpenRouter subset is not runnable: $(jq -c '.problems' <<< "$check_json")"
  subset_profile_sha="$(jq -r '.profile_sha256' <<< "$check_json")"
  timeout_seconds="${TIMEOUT_OVERRIDE:-$(jq -r '.limits.defaultTimeoutSeconds' <<< "$PANEL_JSON")}"
  "$OPENROUTER_HELPER" run --confirmed --config "$config_file" --profile selected \
    --profile-sha256 "$subset_profile_sha" --prompt-file "$prompt_snapshot" --timeout "$timeout_seconds" \
    > "$raw_results_file"

  jq -n \
    --slurpfile routes "$routes_file" \
    --slurpfile results "$raw_results_file" \
    --arg panel_sha256 "$PANEL_SHA256" \
    --arg prompt_sha256 "$EXPECTED_PROMPT_SHA" '
    ($routes[0]) as $panel_routes |
    ($results[0]) as $raw_results |
    [range(0; $panel_routes | length) as $i |
      $raw_results[$i] + $panel_routes[$i] + {
        id: $panel_routes[$i].id,
        kind: "openrouter",
        agent: null,
        provider: $panel_routes[$i].provider,
        effectiveModel: $panel_routes[$i].model,
        modelSource: "panel",
        effectiveEffort: "native-default",
        effortSource: "native-default",
        panelSha256: $panel_sha256,
        promptSha256: $prompt_sha256
      }
    ]'
}

decline_openrouter() {
  parse_run_args true "$@"
  jq --arg panel_sha256 "$PANEL_SHA256" --arg prompt_sha256 "$EXPECTED_PROMPT_SHA" '[.routes[] | . + {
    status: "declined",
    response: null,
    error: "OpenRouter subset declined",
    effectiveModel: .model,
    modelSource: "panel",
    effectiveEffort: "native-default",
    effortSource: "native-default",
    panelSha256: $panel_sha256,
    promptSha256: $prompt_sha256
  }]' <<< "$OPENROUTER_JSON"
}

evaluate_results() {
  local policy="" check_file=""
  local -a result_files=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --policy) [[ $# -ge 2 ]] || die "--policy requires quorum or consensus"; policy="$2"; shift 2 ;;
      --check-file) [[ $# -ge 2 ]] || die "--check-file requires a path"; check_file="$2"; shift 2 ;;
      --results-file) [[ $# -ge 2 ]] || die "--results-file requires a path"; result_files+=("$2"); shift 2 ;;
      *) die "unknown evaluate argument: $1" ;;
    esac
  done
  [[ "$policy" == "quorum" || "$policy" == "consensus" ]] || die "--policy must be quorum or consensus"
  [[ -f "$check_file" ]] || die "check file not found: $check_file"
  jq -e '
    .ready == true and (.routes | type == "array") and
    (.panelSha256 | type == "string" and test("^[a-f0-9]{64}$")) and
    (.promptSha256 | type == "string" and test("^[a-f0-9]{64}$"))
  ' "$check_file" >/dev/null || die "invalid check file"

  COMBINED_FILE="$(mktemp)"
  trap 'rm -f "$COMBINED_FILE"' EXIT
  if [[ ${#result_files[@]} -eq 0 ]]; then
    printf '[]\n' > "$COMBINED_FILE"
  else
    jq -s 'add' "${result_files[@]}" > "$COMBINED_FILE"
  fi
  local panel_sha prompt_sha
  panel_sha="$(jq -r '.panelSha256' "$check_file")"
  prompt_sha="$(jq -r '.promptSha256' "$check_file")"
  jq -e --arg panel_sha "$panel_sha" --arg prompt_sha "$prompt_sha" '
    all(.[]; .panelSha256 == $panel_sha and .promptSha256 == $prompt_sha)
  ' "$COMBINED_FILE" >/dev/null || die "result panel or prompt digest mismatch"
  jq -e '([.[].id] | unique | length) == length' "$COMBINED_FILE" >/dev/null || die "duplicate route results"

  jq -n \
    --arg policy "$policy" \
    --slurpfile check "$check_file" \
    --slurpfile returned "$COMBINED_FILE" '
    ($check[0]) as $panel |
    ($returned[0]) as $results |
    ([$panel.routes[] | . as $route |
      (($results[] | select(.id == $route.id)) // null) as $result |
      if $result == null then
        $route + {
          status:"missing", response:null, error:"route returned no result",
          panelSha256:$panel.panelSha256, promptSha256:$panel.promptSha256
        }
      else
        $result + $route + {
          status:$result.status,
          response:($result.response // null),
          error:($result.error // null),
          exitCode:($result.exitCode // null),
          usage:($result.usage // null),
          panelSha256:$panel.panelSha256,
          promptSha256:$panel.promptSha256
        }
      end
    ]) as $ordered |
    ([$ordered[] | select(.status == "ok") | .provider] | unique) as $successful_providers |
    ([$ordered[] | select(.status != "ok") | {id, provider, status, error}]) as $unavailable |
    ([$successful_providers[] as $provider |
      [$ordered[] | select(.status == "ok" and .provider == $provider) | .id] as $ids |
      select(($ids | length) > 1) | {provider:$provider, routeIds:$ids}
    ]) as $same_provider |
    {
      policy: $policy,
      panel: $panel.panel,
      panelSha256: $panel.panelSha256,
      promptSha256: $panel.promptSha256,
      quorumRequired: $panel.quorum,
      successfulProviderCount: ($successful_providers | length),
      successfulProviders: $successful_providers,
      quorumMet: (($successful_providers | length) >= $panel.quorum),
      consensusEligible: ($policy == "consensus" and (($successful_providers | length) >= $panel.quorum)),
      results: $ordered,
      unavailableRoutes: $unavailable,
      sameProviderCorroboration: $same_provider,
      interpretationRequired: true
    }'
}

command_name="${1:-help}"
shift || true
case "$command_name" in
  check) check_panel "$@" ;;
  run-local) run_local "$@" ;;
  run-openrouter) run_openrouter "$@" ;;
  decline-openrouter) decline_openrouter "$@" ;;
  evaluate) evaluate_results "$@" ;;
  help|--help|-h) usage ;;
  *) die "unknown command: $command_name" ;;
esac
