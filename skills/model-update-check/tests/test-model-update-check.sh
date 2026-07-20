#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$(cd "$SCRIPT_DIR/.." && pwd)/scripts/model-update-check.sh"
ORIGINAL_PATH="$PATH"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/bin" "$TMP_DIR/home"
PI_LOG="$TMP_DIR/pi.log"
CURL_LOG="$TMP_DIR/curl.log"
BREW_LOG="$TMP_DIR/brew.log"
export PI_LOG CURL_LOG BREW_LOG

cat > "$TMP_DIR/bin/pi" <<'FAKE_PI'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$PI_LOG"
case "$*" in
  --version)
    printf '%s\n' '0.80.0'
    ;;
  --list-models|--offline\ --list-models)
    cat <<'MODELS'
provider      model                 context  max-out  thinking  images
anthropic     claude-sonnet-5       1M       128K     yes       yes
openai-codex  gpt-5.6-terra         372K     128K     yes       yes
google        gemini-3.5-flash      1M       64K      yes       yes
openrouter    qwen/current-reasoner 262K     32K      yes       no
MODELS
    ;;
  *)
    printf 'unexpected fake pi arguments: %s\n' "$*" >&2
    exit 2
    ;;
esac
FAKE_PI
chmod +x "$TMP_DIR/bin/pi"

cat > "$TMP_DIR/bin/brew" <<'FAKE_BREW'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$BREW_LOG"
[[ "$1" == "info" && "$2" == "--json=v2" && "$3" == "pi-coding-agent" ]] || exit 2
outdated="${BREW_OUTDATED:-true}"
cat <<JSON
{"formulae":[{"name":"pi-coding-agent","installed":[{"version":"0.80.0"}],"versions":{"stable":"0.81.0"},"outdated":$outdated}]}
JSON
FAKE_BREW
chmod +x "$TMP_DIR/bin/brew"

cat > "$TMP_DIR/models-dev.json" <<'JSON'
{
  "anthropic": {
    "models": {
      "claude-sonnet-5": {
        "name": "Claude Sonnet 5",
        "release_date": "2026-06-29",
        "reasoning": true,
        "limit": {"context": 1000000, "output": 128000}
      }
    }
  },
  "openai": {
    "models": {
      "gpt-5.6-terra": {
        "name": "GPT-5.6 Terra",
        "release_date": "2026-07-09",
        "reasoning": true,
        "limit": {"context": 372000, "output": 128000}
      }
    }
  },
  "google": {
    "models": {
      "gemini-3.5-flash": {
        "name": "Gemini 3.5 Flash",
        "release_date": "2026-05-19",
        "reasoning": true
      }
    }
  },
  "openrouter": {
    "models": {
      "qwen/new-reasoner": {
        "name": "New Qwen Reasoner",
        "release_date": "2026-07-01",
        "reasoning": true
      },
      "x-ai/current-critic": {
        "name": "Current xAI Critic",
        "release_date": "2026-07-08",
        "reasoning": true
      }
    }
  }
}
JSON

cat > "$TMP_DIR/bin/curl" <<'FAKE_CURL'
#!/usr/bin/env bash
set -euo pipefail
url=""
output=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      output="$2"
      shift 2
      ;;
    http://*|https://*)
      url="$1"
      shift
      ;;
    *)
      shift
      ;;
  esac
done
[[ -n "$url" && -n "$output" ]] || exit 2
printf '%s\n' "$url" >> "$CURL_LOG"
case "$url" in
  https://fixture.test/models)
    cp "$FIXTURE_MODELS_DEV" "$output"
    ;;
  https://fixture.test/openrouter)
    cat > "$output" <<'JSON'
{"data":[
  {"id":"qwen/current-reasoner","name":"Current Qwen","created":1,"context_length":262144,"pricing":{},"expiration_date":null},
  {"id":"x-ai/current-critic","name":"Current xAI","created":2,"context_length":500000,"pricing":{},"expiration_date":null}
]}
JSON
    ;;
  https://fixture.test/pi-latest)
    printf '%s\n' '{"version":"0.81.0"}' > "$output"
    ;;
  *)
    exit 22
    ;;
esac
FAKE_CURL
chmod +x "$TMP_DIR/bin/curl"

ROUTER_CONFIG="$TMP_DIR/router.json"
cat > "$ROUTER_CONFIG" <<'JSON'
{
  "enabled": true,
  "tiers": {
    "standard": {
      "candidates": [
        {"model": "openai-codex/gpt-5.6-terra", "metered": false},
        {"model": "anthropic/claude-sonnet-5", "metered": true}
      ]
    },
    "economy": {
      "candidates": [
        {"model": "google/gemini-3.5-flash", "metered": true},
        {"model": "custom/example-model", "metered": true}
      ]
    }
  }
}
JSON

CONSENSUS_CONFIG="$TMP_DIR/consensus.json"
cat > "$CONSENSUS_CONFIG" <<'JSON'
{
  "version": 1,
  "profiles": {
    "test": {
      "models": [
        {"model": "openrouter/qwen/current-reasoner", "vendor": "Qwen", "role": "reasoning"},
        {"model": "openrouter/x-ai/current-critic", "vendor": "xAI", "role": "critique"}
      ],
      "limits": {
        "maxParallel": 2,
        "maxPromptBytes": 1024,
        "maxOutputTokensPerModel": 100,
        "defaultTimeoutSeconds": 5
      }
    }
  }
}
JSON

export FIXTURE_MODELS_DEV="$TMP_DIR/models-dev.json"
RUN_ENV=(env \
  "PATH=$TMP_DIR/bin:$ORIGINAL_PATH" \
  "HOME=$TMP_DIR/home" \
  "MODELS_DEV_URL=https://fixture.test/models" \
  "OPENROUTER_MODELS_URL=https://fixture.test/openrouter" \
  "PI_PACKAGE_URL=https://fixture.test/pi-latest")
COMMON_ARGS=(--router-config "$ROUTER_CONFIG" --consensus-config "$CONSENSUS_CONFIG")

result_json="$("${RUN_ENV[@]}" "$HELPER" "${COMMON_ARGS[@]}")"
jq -e '
  .mode == "hybrid" and
  .readOnly == true and
  .sources.routerConfig.status == "ok" and
  .sources.consensusConfig.status == "ok" and
  .sources.piCatalog.installedVersion == "0.80.0" and
  .sources.piRelease.latestVersion == "0.81.0" and
  .sources.homebrew.status == "ok" and
  .sources.homebrew.formula == "pi-coding-agent" and
  .sources.homebrew.installedVersion == "0.80.0" and
  .sources.homebrew.latestVersion == "0.81.0" and
  .piUpdateAvailable == true and
  .piNpmUpdateAvailable == true and
  .piHomebrewUpdateAvailable == true and
  (.configuredModels | length == 6) and
  any(.configuredModels[];
    .model == "openai-codex/gpt-5.6-terra" and
    .catalogProvider == "openai" and .piAvailable == true and .liveFound == true) and
  any(.configuredModels[];
    .model == "custom/example-model" and
    .catalogProviderFound == false and .liveFound == null) and
  any(.configuredModels[];
    .model == "openrouter/x-ai/current-critic" and
    .piAvailable == false and .liveFound == true and .openRouterFound == true) and
  any(.configuredModels[];
    .model == "openrouter/qwen/current-reasoner" and
    .piAvailable == true and .liveFound == false) and
  any(.findings[]; .kind == "pi-update" and .manager == "homebrew") and
  any(.findings[]; .kind == "pi-unavailable" and .model == "openrouter/x-ai/current-critic") and
  any(.findings[]; .kind == "live-missing" and .model == "openrouter/qwen/current-reasoner") and
  (.recentOpenRouterByNamespace.qwen[0].model == "qwen/new-reasoner")
' <<< "$result_json" >/dev/null || fail "hybrid audit output was incorrect"
[[ "$(wc -l < "$CURL_LOG" | tr -d '[:space:]')" -eq 3 ]] || \
  fail "hybrid mode did not make exactly three public metadata requests"
grep -Fqx -- 'info --json=v2 pi-coding-agent' "$BREW_LOG" || \
  fail "hybrid mode did not inspect Homebrew formula metadata"

result_json="$(BREW_OUTDATED=false "${RUN_ENV[@]}" "$HELPER" "${COMMON_ARGS[@]}")"
jq -e '
  .sources.homebrew.status == "ok" and
  .piNpmUpdateAvailable == true and
  .piHomebrewUpdateAvailable == false and
  .piUpdateAvailable == false and
  any(.findings[]; .kind == "pi-npm-ahead-of-homebrew") and
  all(.findings[]; .kind != "pi-update")
' <<< "$result_json" >/dev/null || fail "Homebrew state did not override npm update availability"

: > "$CURL_LOG"
: > "$PI_LOG"
result_json="$("${RUN_ENV[@]}" "$HELPER" --offline "${COMMON_ARGS[@]}")"
jq -e '
  .mode == "offline" and
  .sources.modelsDev.status == "skipped" and
  .sources.openRouter.status == "skipped" and
  .sources.piRelease.status == "skipped" and
  .sources.homebrew.status == "ok" and
  .piUpdateAvailable == true and
  .piNpmUpdateAvailable == false and
  .piHomebrewUpdateAvailable == true and
  all(.configuredModels[]; .liveFound == null)
' <<< "$result_json" >/dev/null || fail "offline audit output was incorrect"
[[ ! -s "$CURL_LOG" ]] || fail "offline mode invoked curl"
grep -Fqx -- '--offline --list-models' "$PI_LOG" || \
  fail "offline mode did not constrain Pi startup"

INVALID_ROUTER="$TMP_DIR/invalid-router.json"
printf '%s\n' '{}' > "$INVALID_ROUTER"
result_json="$("${RUN_ENV[@]}" "$HELPER" --offline \
  --router-config "$INVALID_ROUTER" --consensus-config "$CONSENSUS_CONFIG")"
jq -e '
  .sources.routerConfig.status == "invalid" and
  (.configuredModels | length == 2) and
  any(.findings[]; .kind == "config" and .source == "model-tier-router")
' <<< "$result_json" >/dev/null || fail "invalid config did not degrade independently"

printf '%s\n' 'model-update-check tests passed'
