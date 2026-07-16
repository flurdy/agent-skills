#!/usr/bin/env bash
# Query a configured OpenRouter consensus profile with bounded input/output.
# The caller must obtain explicit per-run consent before passing --confirmed.
set -euo pipefail

readonly API_URL="https://openrouter.ai/api/v1/chat/completions"
readonly DEFAULT_CONFIG_PATH="${HOME}/.agents/second-opinion/config.json"
readonly DEFAULT_PROFILE="extreme"
readonly HARD_MAX_MODELS=8
readonly HARD_MAX_PARALLEL=4
readonly HARD_MAX_PROMPT_BYTES=65536
readonly HARD_MAX_OUTPUT_TOKENS=2000
readonly HARD_MAX_TIMEOUT_SECONDS=600

usage() {
  cat <<'USAGE'
Usage:
  openrouter-panel.sh check [--profile NAME] [--config FILE]
  openrouter-panel.sh run --confirmed --prompt-file FILE --profile-sha256 DIGEST
                          [--profile NAME] [--config FILE] [--timeout SECONDS]

Configuration defaults to ~/.agents/second-opinion/config.json. A profile contains
1-8 unique-provider OpenRouter models and limits no greater than the compiled safety
ceilings: 4 concurrent requests, 65,536 prompt bytes, 2,000 output tokens per
model, and 600 seconds per request.

OPENROUTER_API_KEY is required only for run. Its presence is checked without
printing it. The config contains model identities and limits, never credentials.
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required"
}

append_problem() {
  local message="$1"
  PROBLEMS_JSON="$(jq -c --arg message "$message" '. + [$message]' <<< "$PROBLEMS_JSON")"
}

profile_sha256() {
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

parse_location_args() {
  CONFIG_PATH="$DEFAULT_CONFIG_PATH"
  PROFILE_NAME="$DEFAULT_PROFILE"
  REMAINING_ARGS=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --config)
        [[ $# -ge 2 ]] || die "--config requires a path"
        CONFIG_PATH="$2"
        shift 2
        ;;
      --profile)
        [[ $# -ge 2 ]] || die "--profile requires a name"
        PROFILE_NAME="$2"
        shift 2
        ;;
      *)
        REMAINING_ARGS+=("$1")
        shift
        ;;
    esac
  done
}

validate_profile() {
  PROFILE_JSON=""

  if [[ ! -f "$CONFIG_PATH" ]]; then
    PROFILE_ERROR="config file not found: $CONFIG_PATH"
    return 1
  fi
  if ! jq -e . "$CONFIG_PATH" >/dev/null 2>&1; then
    PROFILE_ERROR="config is not valid JSON: $CONFIG_PATH"
    return 1
  fi
  if ! jq -e '.version == 1 and (.profiles | type == "object")' "$CONFIG_PATH" >/dev/null 2>&1; then
    PROFILE_ERROR="config must declare version 1 and a profiles object"
    return 1
  fi

  PROFILE_JSON="$(jq -c --arg profile "$PROFILE_NAME" '.profiles[$profile] // empty' "$CONFIG_PATH")"
  if [[ -z "$PROFILE_JSON" ]]; then
    PROFILE_ERROR="profile not found: $PROFILE_NAME"
    return 1
  fi

  if ! jq -e '
    (.models | type == "array") and
    (.models | length >= 1) and
    (.models | length <= 8) and
    (all(.models[];
      (.model | type == "string") and
      (.model | test("^openrouter/[A-Za-z0-9][A-Za-z0-9._-]*/.+$")) and
      (.vendor | type == "string") and (.vendor | length > 0) and
      (.role | type == "string") and (.role | length > 0)
    )) and
    ([.models[].model] | unique | length) == (.models | length) and
    ([.models[].model | sub("^openrouter/"; "") | split("/")[0] | ascii_downcase] | unique | length) == (.models | length)
  ' <<< "$PROFILE_JSON" >/dev/null 2>&1; then
    PROFILE_ERROR="profile models must contain 1-$HARD_MAX_MODELS unique model IDs and unique OpenRouter provider namespaces; each model must use openrouter/<provider>/<model-id>"
    return 1
  fi

  if ! jq -e \
    --argjson hard_parallel "$HARD_MAX_PARALLEL" \
    --argjson hard_prompt "$HARD_MAX_PROMPT_BYTES" \
    --argjson hard_output "$HARD_MAX_OUTPUT_TOKENS" \
    --argjson hard_timeout "$HARD_MAX_TIMEOUT_SECONDS" '
      (.limits | type == "object") and
      (.limits.maxParallel | type == "number" and floor == . and . >= 1 and . <= $hard_parallel) and
      (.limits.maxPromptBytes | type == "number" and floor == . and . >= 1 and . <= $hard_prompt) and
      (.limits.maxOutputTokensPerModel | type == "number" and floor == . and . >= 1 and . <= $hard_output) and
      (.limits.defaultTimeoutSeconds | type == "number" and floor == . and . >= 1 and . <= $hard_timeout)
    ' <<< "$PROFILE_JSON" >/dev/null 2>&1; then
    PROFILE_ERROR="profile limits must be positive integers within compiled safety ceilings"
    return 1
  fi

  PROFILE_ERROR=""
  return 0
}

check_configuration() {
  parse_location_args "$@"
  [[ ${#REMAINING_ARGS[@]} -eq 0 ]] || die "unknown check argument: ${REMAINING_ARGS[0]}"

  if ! command -v jq >/dev/null 2>&1; then
    printf '%s\n' '{"ready":false,"problems":["jq is not installed; config cannot be parsed"],"auth":"unknown","curl":"unknown","models":[]}'
    return
  fi

  PROBLEMS_JSON='[]'
  local auth_status="missing"
  local curl_status="available"

  command -v curl >/dev/null 2>&1 || {
    curl_status="missing"
    append_problem "curl is not installed"
  }
  if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    auth_status="configured (not network-verified)"
  else
    append_problem "OPENROUTER_API_KEY is not set"
  fi

  if ! validate_profile; then
    append_problem "$PROFILE_ERROR"
    PROFILE_JSON='{"models":[],"limits":null}'
  fi

  local digest=""
  if ! digest="$(printf '%s' "$PROFILE_JSON" | profile_sha256)"; then
    append_problem "a SHA-256 command is required (sha256sum, shasum, or openssl)"
  fi

  jq -n \
    --arg auth "$auth_status" \
    --arg curl "$curl_status" \
    --arg config "$CONFIG_PATH" \
    --arg profile "$PROFILE_NAME" \
    --argjson profile_data "$PROFILE_JSON" \
    --arg profile_sha256 "$digest" \
    --argjson problems "$PROBLEMS_JSON" \
    --argjson hard_max_models "$HARD_MAX_MODELS" \
    --argjson hard_max_parallel "$HARD_MAX_PARALLEL" \
    --argjson hard_max_prompt_bytes "$HARD_MAX_PROMPT_BYTES" \
    --argjson hard_max_output_tokens "$HARD_MAX_OUTPUT_TOKENS" \
    --argjson hard_max_timeout_seconds "$HARD_MAX_TIMEOUT_SECONDS" '
    {
      ready: ($problems | length == 0),
      auth: $auth,
      curl: $curl,
      config: $config,
      profile: $profile,
      profile_sha256: $profile_sha256,
      models: ($profile_data.models | map(. + {provider: (.model | sub("^openrouter/"; "") | split("/")[0])})),
      profile_limits: $profile_data.limits,
      hard_limits: {
        max_models: $hard_max_models,
        max_parallel: $hard_max_parallel,
        max_prompt_bytes: $hard_max_prompt_bytes,
        max_output_tokens_per_model: $hard_max_output_tokens,
        max_timeout_seconds: $hard_max_timeout_seconds
      },
      problems: $problems
    }'
}

write_result() {
  local canonical_model="$1"
  local vendor="$2"
  local provider="$3"
  local role="$4"
  local response_file="$5"
  local curl_status="$6"
  local result_file="$7"

  if [[ "$curl_status" -eq 0 ]] && jq -e '.choices[0].message.content | type == "string"' "$response_file" >/dev/null 2>&1; then
    jq -n \
      --arg model "$canonical_model" \
      --arg vendor "$vendor" \
      --arg provider "$provider" \
      --arg role "$role" \
      --slurpfile response "$response_file" '
      {
        model: $model,
        vendor: $vendor,
        provider: $provider,
        role: $role,
        status: "ok",
        response: $response[0].choices[0].message.content,
        usage: ($response[0].usage // null)
      }' > "$result_file"
    return
  fi

  local message="OpenRouter request failed"
  if jq -e . "$response_file" >/dev/null 2>&1; then
    message="$(jq -r '.error.message // .message // "OpenRouter request failed"' "$response_file")"
  elif [[ -s "$response_file" ]]; then
    message="OpenRouter returned a non-JSON error response"
  fi

  jq -n \
    --arg model "$canonical_model" \
    --arg vendor "$vendor" \
    --arg provider "$provider" \
    --arg role "$role" \
    --arg message "$message" \
    --argjson exit_code "$curl_status" \
    '{model: $model, vendor: $vendor, provider: $provider, role: $role, status: "error", error: $message, curl_exit_code: $exit_code}' \
    > "$result_file"
}

call_model() {
  local canonical_model="$1"
  local vendor="$2"
  local role="$3"
  local prompt_file="$4"
  local timeout_seconds="$5"
  local max_output_tokens="$6"
  local work_dir="$7"
  local index="$8"
  local api_model="${canonical_model#openrouter/}"
  local provider="${api_model%%/*}"
  local request_file
  local response_file
  local result_file
  request_file="$(printf '%s/request-%03d.json' "$work_dir" "$index")"
  response_file="$(printf '%s/response-%03d.json' "$work_dir" "$index")"
  result_file="$(printf '%s/result-%03d.json' "$work_dir" "$index")"

  jq -n \
    --arg model "$api_model" \
    --rawfile prompt "$prompt_file" \
    --argjson max_tokens "$max_output_tokens" '
    {
      model: $model,
      messages: [{role: "user", content: $prompt}],
      max_tokens: $max_tokens,
      temperature: 0.2
    }' > "$request_file"

  : > "$response_file"
  local curl_status=0
  # A curl config file keeps the bearer token out of argv and works on versions
  # older than --header @file (introduced in curl 7.55). HTTP error bodies are
  # parsed below, while transport failures still produce a nonzero exit code.
  {
    printf 'silent\nshow-error\nmax-time = %s\n' "$timeout_seconds"
    printf 'header = "Authorization: Bearer %s"\n' "$OPENROUTER_API_KEY"
    printf 'header = "Content-Type: application/json"\n'
    printf 'data-binary = "@%s"\noutput = "%s"\nurl = "%s"\n' \
      "$request_file" "$response_file" "$API_URL"
  } > "$work_dir/curl.config"
  curl --config "$work_dir/curl.config" || curl_status=$?

  write_result "$canonical_model" "$vendor" "$provider" "$role" "$response_file" "$curl_status" "$result_file"
}

run_panel() {
  local confirmed=false
  local prompt_file=""
  local timeout_override=""
  local expected_profile_sha256=""

  parse_location_args "$@"
  if [[ ${#REMAINING_ARGS[@]} -gt 0 ]]; then
    set -- "${REMAINING_ARGS[@]}"
  else
    set --
  fi
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --confirmed)
        confirmed=true
        shift
        ;;
      --prompt-file)
        [[ $# -ge 2 ]] || die "--prompt-file requires a path"
        prompt_file="$2"
        shift 2
        ;;
      --timeout)
        [[ $# -ge 2 ]] || die "--timeout requires seconds"
        timeout_override="$2"
        shift 2
        ;;
      --profile-sha256)
        [[ $# -ge 2 ]] || die "--profile-sha256 requires a digest"
        expected_profile_sha256="$2"
        shift 2
        ;;
      *)
        die "unknown run argument: $1"
        ;;
    esac
  done

  [[ "$confirmed" == true ]] || die "refusing metered requests without --confirmed"
  [[ -n "$prompt_file" ]] || die "--prompt-file is required"
  [[ -f "$prompt_file" ]] || die "prompt file not found: $prompt_file"
  [[ -s "$prompt_file" ]] || die "prompt file is empty; refusing metered requests"
  [[ "$expected_profile_sha256" =~ ^[a-f0-9]{64}$ ]] || die "--profile-sha256 must be the SHA-256 digest from check"

  require_command curl
  require_command jq
  validate_profile || die "$PROFILE_ERROR"
  local actual_profile_sha256
  actual_profile_sha256="$(printf '%s' "$PROFILE_JSON" | profile_sha256)" || \
    die "a SHA-256 command is required (sha256sum, shasum, or openssl)"
  [[ "$actual_profile_sha256" == "$expected_profile_sha256" ]] || \
    die "profile changed since check; rerun check and obtain fresh consent"
  [[ -n "${OPENROUTER_API_KEY:-}" ]] || die "OPENROUTER_API_KEY is not set"
  case "$OPENROUTER_API_KEY" in
    *$'\n'*|*$'\r'*|*\"*|*\\*) die "OPENROUTER_API_KEY contains unsupported characters" ;;
  esac

  local max_parallel
  local max_prompt_bytes
  local max_output_tokens
  local timeout_seconds
  local model_count
  max_parallel="$(jq -r '.limits.maxParallel' <<< "$PROFILE_JSON")"
  max_prompt_bytes="$(jq -r '.limits.maxPromptBytes' <<< "$PROFILE_JSON")"
  max_output_tokens="$(jq -r '.limits.maxOutputTokensPerModel' <<< "$PROFILE_JSON")"
  timeout_seconds="$(jq -r '.limits.defaultTimeoutSeconds' <<< "$PROFILE_JSON")"
  model_count="$(jq -r '.models | length' <<< "$PROFILE_JSON")"

  if [[ -n "$timeout_override" ]]; then
    [[ "$timeout_override" =~ ^[0-9]+$ ]] || die "timeout must be an integer number of seconds"
    (( timeout_override >= 1 && timeout_override <= HARD_MAX_TIMEOUT_SECONDS )) || \
      die "timeout must be between 1 and $HARD_MAX_TIMEOUT_SECONDS seconds"
    timeout_seconds="$timeout_override"
  fi

  local prompt_bytes
  prompt_bytes="$(wc -c < "$prompt_file" | tr -d '[:space:]')"
  (( prompt_bytes <= max_prompt_bytes )) || \
    die "prompt is $prompt_bytes bytes; profile maximum is $max_prompt_bytes (summarize before retrying)"

  WORK_DIR="$(mktemp -d)"
  chmod 700 "$WORK_DIR"
  trap 'rm -rf "$WORK_DIR"' EXIT

  # Keep the bearer token out of argv/process listings and curl's config private.
  umask 077

  local index=0
  while (( index < model_count )); do
    local -a pids=()
    local launched=0
    while (( index < model_count && launched < max_parallel )); do
      local canonical_model
      local vendor
      local role
      canonical_model="$(jq -r --argjson index "$index" '.models[$index].model' <<< "$PROFILE_JSON")"
      vendor="$(jq -r --argjson index "$index" '.models[$index].vendor' <<< "$PROFILE_JSON")"
      role="$(jq -r --argjson index "$index" '.models[$index].role' <<< "$PROFILE_JSON")"

      call_model "$canonical_model" "$vendor" "$role" "$prompt_file" "$timeout_seconds" \
        "$max_output_tokens" "$WORK_DIR" "$index" &
      pids+=("$!")
      index=$((index + 1))
      launched=$((launched + 1))
    done

    local pid
    for pid in "${pids[@]}"; do
      wait "$pid"
    done
  done

  jq -s '.' "$WORK_DIR"/result-*.json
}

command_name="${1:-help}"
shift || true

case "$command_name" in
  check)
    check_configuration "$@"
    ;;
  run)
    run_panel "$@"
    ;;
  help|--help|-h)
    usage
    ;;
  *)
    die "unknown command: $command_name"
    ;;
esac
