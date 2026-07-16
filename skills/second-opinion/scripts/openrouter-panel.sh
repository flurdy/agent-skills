#!/usr/bin/env bash
# Query the two configured OpenRouter panel models with bounded input/output.
# The caller must obtain explicit per-run consent before passing --confirmed.
set -euo pipefail

readonly API_URL="https://openrouter.ai/api/v1/chat/completions"
readonly MAX_PROMPT_BYTES=65536
readonly MAX_OUTPUT_TOKENS=2000
readonly MAX_TIMEOUT_SECONDS=600

usage() {
  cat <<'USAGE'
Usage:
  openrouter-panel.sh check
  openrouter-panel.sh run --confirmed --prompt-file FILE [--timeout SECONDS]

Environment:
  OPENROUTER_API_KEY           Required for run; presence is checked without printing it.
  OPENROUTER_PANEL_QWEN_MODEL  Required OpenRouter model ID with qwen/ prefix.
  OPENROUTER_PANEL_XAI_MODEL   Required OpenRouter model ID with x-ai/ prefix.

The run command makes exactly two requests, with at most two in flight. Input is
capped at 65,536 bytes, output at 2,000 tokens per model, and timeout at 600
seconds per model. It emits a JSON array and does not give models any tools.
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required"
}

load_models() {
  QWEN_MODEL="${OPENROUTER_PANEL_QWEN_MODEL:-}"
  XAI_MODEL="${OPENROUTER_PANEL_XAI_MODEL:-}"

  [[ -n "$QWEN_MODEL" ]] || die "OPENROUTER_PANEL_QWEN_MODEL is not set"
  [[ -n "$XAI_MODEL" ]] || die "OPENROUTER_PANEL_XAI_MODEL is not set"
  [[ "$QWEN_MODEL" == qwen/* ]] || die "OPENROUTER_PANEL_QWEN_MODEL must use the qwen/ vendor prefix"
  [[ "$XAI_MODEL" == x-ai/* ]] || die "OPENROUTER_PANEL_XAI_MODEL must use the x-ai/ vendor prefix"
  [[ "$QWEN_MODEL" != "$XAI_MODEL" ]] || die "panel model IDs must be distinct"
}

check_configuration() {
  require_command jq

  local -a problems=()
  local qwen_model="${OPENROUTER_PANEL_QWEN_MODEL:-}"
  local xai_model="${OPENROUTER_PANEL_XAI_MODEL:-}"
  local auth_status="missing"
  local curl_status="available"

  command -v curl >/dev/null 2>&1 || {
    curl_status="missing"
    problems+=("curl is not installed")
  }
  [[ -n "${OPENROUTER_API_KEY:-}" ]] && auth_status="configured (not network-verified)" || \
    problems+=("OPENROUTER_API_KEY is not set")
  [[ -n "$qwen_model" ]] || problems+=("OPENROUTER_PANEL_QWEN_MODEL is not set")
  [[ -n "$xai_model" ]] || problems+=("OPENROUTER_PANEL_XAI_MODEL is not set")
  [[ -z "$qwen_model" || "$qwen_model" == qwen/* ]] || \
    problems+=("OPENROUTER_PANEL_QWEN_MODEL must use the qwen/ vendor prefix")
  [[ -z "$xai_model" || "$xai_model" == x-ai/* ]] || \
    problems+=("OPENROUTER_PANEL_XAI_MODEL must use the x-ai/ vendor prefix")
  [[ -z "$qwen_model" || -z "$xai_model" || "$qwen_model" != "$xai_model" ]] || \
    problems+=("panel model IDs must be distinct")

  jq -n \
    --arg auth "$auth_status" \
    --arg curl "$curl_status" \
    --arg qwen "$qwen_model" \
    --arg xai "$xai_model" \
    --argjson max_prompt_bytes "$MAX_PROMPT_BYTES" \
    --argjson max_output_tokens "$MAX_OUTPUT_TOKENS" \
    --argjson max_parallel 2 \
    '{
      ready: ($ARGS.positional | length == 0),
      auth: $auth,
      curl: $curl,
      models: [
        {role: "qwen-reasoning", vendor: "Qwen", id: (if $qwen == "" then null else $qwen end)},
        {role: "xai-reasoning", vendor: "xAI", id: (if $xai == "" then null else $xai end)}
      ],
      problems: $ARGS.positional,
      limits: {
        max_prompt_bytes: $max_prompt_bytes,
        max_output_tokens_per_model: $max_output_tokens,
        max_parallel: $max_parallel
      }
    }' \
    --args "${problems[@]}"
}

write_result() {
  local model="$1"
  local vendor="$2"
  local response_file="$3"
  local curl_status="$4"
  local result_file="$5"

  if [[ "$curl_status" -eq 0 ]] && jq -e '.choices[0].message.content | type == "string"' "$response_file" >/dev/null 2>&1; then
    jq -n \
      --arg model "$model" \
      --arg vendor "$vendor" \
      --slurpfile response "$response_file" \
      '{
        model: $model,
        vendor: $vendor,
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
    --arg model "$model" \
    --arg vendor "$vendor" \
    --arg message "$message" \
    --argjson exit_code "$curl_status" \
    '{model: $model, vendor: $vendor, status: "error", error: $message, curl_exit_code: $exit_code}' \
    > "$result_file"
}

call_model() {
  local model="$1"
  local vendor="$2"
  local prompt_file="$3"
  local timeout_seconds="$4"
  local work_dir="$5"
  local index="$6"
  local request_file="$work_dir/request-$index.json"
  local response_file="$work_dir/response-$index.json"
  local result_file="$work_dir/result-$index.json"

  jq -n \
    --arg model "$model" \
    --rawfile prompt "$prompt_file" \
    --argjson max_tokens "$MAX_OUTPUT_TOKENS" \
    '{
      model: $model,
      messages: [{role: "user", content: $prompt}],
      max_tokens: $max_tokens,
      temperature: 0.2
    }' > "$request_file"

  local curl_status=0
  curl --silent --show-error --fail-with-body \
    --max-time "$timeout_seconds" \
    --header "@$work_dir/headers" \
    --data-binary "@$request_file" \
    --output "$response_file" \
    "$API_URL" || curl_status=$?

  write_result "$model" "$vendor" "$response_file" "$curl_status" "$result_file"
}

run_panel() {
  local confirmed=false
  local prompt_file=""
  local timeout_seconds=180

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
        timeout_seconds="$2"
        shift 2
        ;;
      *)
        die "unknown argument: $1"
        ;;
    esac
  done

  [[ "$confirmed" == true ]] || die "refusing metered requests without --confirmed"
  [[ -n "$prompt_file" ]] || die "--prompt-file is required"
  [[ -f "$prompt_file" ]] || die "prompt file not found: $prompt_file"
  [[ "$timeout_seconds" =~ ^[0-9]+$ ]] || die "timeout must be an integer number of seconds"
  (( timeout_seconds >= 1 && timeout_seconds <= MAX_TIMEOUT_SECONDS )) || \
    die "timeout must be between 1 and $MAX_TIMEOUT_SECONDS seconds"

  require_command curl
  require_command jq
  load_models
  [[ -n "${OPENROUTER_API_KEY:-}" ]] || die "OPENROUTER_API_KEY is not set"

  local prompt_bytes
  prompt_bytes="$(wc -c < "$prompt_file" | tr -d '[:space:]')"
  (( prompt_bytes <= MAX_PROMPT_BYTES )) || \
    die "prompt is $prompt_bytes bytes; maximum is $MAX_PROMPT_BYTES (summarize before retrying)"

  WORK_DIR="$(mktemp -d)"
  chmod 700 "$WORK_DIR"
  trap 'rm -rf "$WORK_DIR"' EXIT

  # Keep the bearer token out of argv/process listings.
  umask 077
  printf 'Authorization: Bearer %s\nContent-Type: application/json\n' "$OPENROUTER_API_KEY" \
    > "$WORK_DIR/headers"

  call_model "$QWEN_MODEL" "Qwen" "$prompt_file" "$timeout_seconds" "$WORK_DIR" 0 &
  local qwen_pid=$!
  call_model "$XAI_MODEL" "xAI" "$prompt_file" "$timeout_seconds" "$WORK_DIR" 1 &
  local xai_pid=$!

  wait "$qwen_pid"
  wait "$xai_pid"

  jq -s '.' "$WORK_DIR/result-0.json" "$WORK_DIR/result-1.json"
}

command_name="${1:-help}"
shift || true

case "$command_name" in
  check)
    [[ $# -eq 0 ]] || die "check takes no arguments"
    check_configuration
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
