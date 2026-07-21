#!/usr/bin/env bash
# Read-only audit of configured Pi/router and second-opinion panel model IDs.
set -euo pipefail

readonly DEFAULT_ROUTER_CONFIG="${HOME}/.pi/agent/model-tier-router.json"
readonly DEFAULT_CONSENSUS_CONFIG="${HOME}/.agents/second-opinion/config.json"
readonly MODELS_DEV_URL="${MODELS_DEV_URL:-https://models.dev/api.json}"
readonly OPENROUTER_MODELS_URL="${OPENROUTER_MODELS_URL:-https://openrouter.ai/api/v1/models}"
readonly PI_PACKAGE_URL="${PI_PACKAGE_URL:-https://registry.npmjs.org/@earendil-works%2Fpi-coding-agent/latest}"
readonly PI_BREW_FORMULA="${PI_BREW_FORMULA:-pi-coding-agent}"

router_config="$DEFAULT_ROUTER_CONFIG"
consensus_config="$DEFAULT_CONSENSUS_CONFIG"
offline=false

usage() {
  cat <<'USAGE'
Usage: model-update-check.sh [--offline]
                             [--router-config FILE]
                             [--consensus-config FILE]

Compares configured model IDs with the active Pi model catalog and, unless
--offline is set, public models.dev and npm metadata. Emits JSON only. It never
reads provider credentials, calls inference APIs, or edits configuration.
USAGE
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --offline)
      offline=true
      shift
      ;;
    --router-config)
      [[ $# -ge 2 ]] || die "--router-config requires a path"
      router_config="$2"
      shift 2
      ;;
    --consensus-config)
      [[ $# -ge 2 ]] || die "--consensus-config requires a path"
      consensus_config="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

command -v jq >/dev/null 2>&1 || die "jq is required"

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

router_entries="$work_dir/router-entries.json"
consensus_entries="$work_dir/consensus-entries.json"
configured_entries="$work_dir/configured-entries.json"
pi_models="$work_dir/pi-models.json"
live_catalog="$work_dir/models-dev.json"
openrouter_catalog="$work_dir/openrouter-models.json"
pi_package="$work_dir/pi-package.json"
brew_info="$work_dir/brew-info.json"

printf '[]\n' > "$router_entries"
printf '[]\n' > "$consensus_entries"
printf '[]\n' > "$pi_models"
printf '{}\n' > "$live_catalog"
printf '{"data":[]}\n' > "$openrouter_catalog"
printf '{}\n' > "$pi_package"
printf '{}\n' > "$brew_info"

router_status="ok"
if [[ ! -f "$router_config" ]]; then
  router_status="missing"
elif ! jq -e '
  (.tiers | type == "object") and
  all(.tiers | to_entries[];
    (.value.candidates | type == "array") and
    all(.value.candidates[]; (.model | type == "string") and (.model | contains("/")))
  )
' "$router_config" >/dev/null 2>&1; then
  router_status="invalid"
else
  jq -c --arg config "$router_config" '
    [
      .tiers | to_entries[] as $tier |
      $tier.value.candidates[] |
      (.model | split("/")) as $parts |
      ($parts[0]) as $pi_provider |
      {
        source: "model-tier-router",
        config: $config,
        usage: $tier.key,
        model: .model,
        metered: (.metered // null),
        piProvider: $pi_provider,
        catalogProvider: (
          if $pi_provider == "openai-codex" then "openai"
          elif $pi_provider == "google-gemini-cli" then "google"
          else $pi_provider
          end
        ),
        catalogModel: ($parts[1:] | join("/"))
      }
    ]
  ' "$router_config" > "$router_entries"
fi

consensus_status="ok"
if [[ ! -f "$consensus_config" ]]; then
  consensus_status="missing"
elif ! jq -e \
  --argjson max_routes 8 \
  --argjson max_parallel 4 \
  --argjson max_prompt 65536 \
  --argjson max_output 2000 \
  --argjson max_timeout 600 '
  def canonical_openrouter:
    type == "string" and test("^openrouter/[A-Za-z0-9][A-Za-z0-9._-]*/.+$");
  def valid_limits:
    type == "object" and
    (.maxParallel | type == "number" and floor == . and . >= 1 and . <= $max_parallel) and
    (.maxPromptBytes | type == "number" and floor == . and . >= 1 and . <= $max_prompt) and
    (.maxOutputTokensPerModel | type == "number" and floor == . and . >= 1 and . <= $max_output) and
    (.defaultTimeoutSeconds | type == "number" and floor == . and . >= 1 and . <= $max_timeout);
  def valid_quorum($providers):
    type == "number" and floor == . and . >= 1 and . <= $providers;
  def route_provider:
    if .kind == "local" then ({claude:"anthropic",codex:"openai",gemini:"google"}[.agent])
    else (.model | sub("^openrouter/"; "") | split("/")[0] | ascii_downcase)
    end;
  def valid_route:
    (.id | type == "string" and test("^[A-Za-z0-9][A-Za-z0-9._-]*$")) and
    (.role | type == "string" and length > 0) and
    ((.kind == "local" and
      (.agent == "claude" or .agent == "codex" or .agent == "gemini") and
      ((has("model") | not) or (.model | type == "string" and length > 0)) and
      ((has("effort") | not) or
       (.agent == "claude" and (.effort | test("^(low|medium|high|xhigh|max)$"))) or
       (.agent == "codex" and (.effort | test("^(minimal|low|medium|high|xhigh)$"))))) or
     (.kind == "openrouter" and
      (.model | canonical_openrouter) and
      (.vendor | type == "string" and length > 0) and
      (has("agent") | not) and (has("effort") | not)));
  def valid_legacy:
    (.models | length >= 1 and length <= $max_routes) and
    all(.models[];
      (.model | canonical_openrouter) and
      (.vendor | type == "string" and length > 0) and
      (.role | type == "string" and length > 0)) and
    ([.models[].model] | unique | length) == (.models | length) and
    (([.models[].model | sub("^openrouter/"; "") | split("/")[0] | ascii_downcase] | unique | length) as $providers |
      ((.quorum // ([2, $providers] | min)) | valid_quorum($providers)));
  def valid_routes:
    (.routes | length >= 1 and length <= $max_routes) and
    all(.routes[]; valid_route) and
    ([.routes[].id] | unique | length) == (.routes | length) and
    ([.routes[] | if .kind == "local" then ("local/" + .agent + "/" + (.model // "native-default")) else .model end] | unique | length) == (.routes | length) and
    (([.routes[] | route_provider] | unique | length) as $providers |
      (.quorum | valid_quorum($providers)));
  def valid_profile:
    ((((.models | type) == "array") and (has("routes") | not)) or
     (((.routes | type) == "array") and (has("models") | not))) and
    (.limits | valid_limits) and
    (if has("models") then valid_legacy else valid_routes end);
  (.version == 1) and
  (.profiles | type == "object") and
  all(.profiles[]; valid_profile)
' "$consensus_config" >/dev/null 2>&1; then
  consensus_status="invalid"
else
  jq -c --arg config "$consensus_config" '
    [
      .profiles | to_entries[] as $profile |
      (if $profile.value | has("models") then
        $profile.value.models[]
      else
        $profile.value.routes[] | select(.kind == "openrouter")
      end) as $entry |
      {
        source: "second-opinion",
        config: $config,
        usage: $profile.key,
        model: $entry.model,
        vendor: $entry.vendor,
        role: $entry.role,
        metered: true,
        piProvider: "openrouter",
        catalogProvider: "openrouter",
        catalogModel: ($entry.model | sub("^openrouter/"; ""))
      }
    ]
  ' "$consensus_config" > "$consensus_entries"
fi

jq -s 'add | unique_by([.source, .usage, .model])' \
  "$router_entries" "$consensus_entries" > "$configured_entries"

pi_status="ok"
pi_version=""
if ! command -v pi >/dev/null 2>&1; then
  pi_status="missing"
else
  pi_version="$(pi --version 2>/dev/null || true)"
  pi_output="$work_dir/pi-models.txt"
  if [[ "$offline" == true ]]; then
    if ! pi --offline --list-models > "$pi_output" 2>/dev/null; then
      pi_status="error"
    fi
  elif ! pi --list-models > "$pi_output" 2>/dev/null; then
    pi_status="error"
  fi

  if [[ "$pi_status" == "ok" ]]; then
    awk 'NR > 1 && NF >= 2 { print $1 "\t" $2 }' "$pi_output" |
      jq -Rsc '
        split("\n") |
        map(select(length > 0) | split("\t") | {provider: .[0], model: .[1]}) |
        unique_by([.provider, .model])
      ' > "$pi_models"
  fi
fi

brew_status="missing"
brew_formula=""
brew_installed_version=""
brew_latest_version=""
brew_update_available=false
if command -v brew >/dev/null 2>&1; then
  brew_status="ok"
  if ! brew info --json=v2 "$PI_BREW_FORMULA" > "$brew_info" 2>/dev/null ||
    ! jq -e '.formulae | type == "array" and length == 1' "$brew_info" >/dev/null 2>&1; then
    brew_status="error"
    printf '{}\n' > "$brew_info"
  else
    brew_formula="$(jq -r '.formulae[0].name // ""' "$brew_info")"
    brew_installed_version="$(jq -r '(.formulae[0].installed // [] | map(.version) | last) // ""' "$brew_info")"
    brew_latest_version="$(jq -r '.formulae[0].versions.stable // ""' "$brew_info")"
    if [[ -z "$brew_installed_version" ]]; then
      brew_status="not-installed"
    else
      brew_update_available="$(jq -r '.formulae[0].outdated // false' "$brew_info")"
    fi
  fi
fi

models_dev_status="skipped"
openrouter_status="skipped"
pi_release_status="skipped"
if [[ "$offline" == false ]]; then
  if ! command -v curl >/dev/null 2>&1; then
    models_dev_status="missing-curl"
    openrouter_status="missing-curl"
    pi_release_status="missing-curl"
  else
    models_dev_status="ok"
    if ! curl --fail --silent --show-error --location --max-time 30 \
      "$MODELS_DEV_URL" --output "$live_catalog" 2>/dev/null ||
      ! jq -e 'type == "object"' "$live_catalog" >/dev/null 2>&1; then
      models_dev_status="error"
      printf '{}\n' > "$live_catalog"
    fi

    openrouter_status="ok"
    if ! curl --fail --silent --show-error --location --max-time 30 \
      "$OPENROUTER_MODELS_URL" --output "$openrouter_catalog" 2>/dev/null ||
      ! jq -e '.data | type == "array"' "$openrouter_catalog" >/dev/null 2>&1; then
      openrouter_status="error"
      printf '{"data":[]}\n' > "$openrouter_catalog"
    fi

    pi_release_status="ok"
    if ! curl --fail --silent --show-error --location --max-time 15 \
      "$PI_PACKAGE_URL" --output "$pi_package" 2>/dev/null ||
      ! jq -e '.version | type == "string"' "$pi_package" >/dev/null 2>&1; then
      pi_release_status="error"
      printf '{}\n' > "$pi_package"
    fi
  fi
fi

latest_pi_version="$(jq -r '.version // ""' "$pi_package")"
generated_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

jq -n \
  --arg generated_at "$generated_at" \
  --argjson offline "$offline" \
  --arg router_path "$router_config" \
  --arg router_status "$router_status" \
  --arg consensus_path "$consensus_config" \
  --arg consensus_status "$consensus_status" \
  --arg pi_status "$pi_status" \
  --arg pi_version "$pi_version" \
  --arg models_dev_status "$models_dev_status" \
  --arg models_dev_url "$MODELS_DEV_URL" \
  --arg openrouter_status "$openrouter_status" \
  --arg openrouter_url "$OPENROUTER_MODELS_URL" \
  --arg pi_release_status "$pi_release_status" \
  --arg latest_pi_version "$latest_pi_version" \
  --arg brew_status "$brew_status" \
  --arg brew_formula "$brew_formula" \
  --arg brew_installed_version "$brew_installed_version" \
  --arg brew_latest_version "$brew_latest_version" \
  --argjson brew_update_available "$brew_update_available" \
  --slurpfile configured "$configured_entries" \
  --slurpfile pi_models "$pi_models" \
  --slurpfile catalog "$live_catalog" \
  --slurpfile openrouter_catalog "$openrouter_catalog" '
  def version_parts:
    split("-")[0] | split(".") | map(tonumber? // 0);
  def recent($models; $count):
    ($models // {}) | to_entries |
    map({
      model: .key,
      name: (.value.name // .key),
      releaseDate: (.value.release_date // null),
      lastUpdated: (.value.last_updated // null),
      reasoning: (.value.reasoning // false),
      context: (.value.limit.context // null),
      output: (.value.limit.output // null),
      cost: (.value.cost // null)
    }) |
    sort_by(.releaseDate // "") | reverse | .[0:$count];

  ($configured[0]) as $configured_models |
  ($pi_models[0]) as $available_models |
  ($catalog[0]) as $live |
  ($openrouter_catalog[0].data // []) as $openrouter_models |
  ($configured_models | map(
    . as $entry |
    ($live[$entry.catalogProvider] // null) as $provider_metadata |
    ($provider_metadata.models[$entry.catalogModel] // null) as $metadata |
    . + {
      piAvailable: (
        if $pi_status != "ok" then null
        else any($available_models[];
          .provider == $entry.piProvider and .model == $entry.catalogModel)
        end
      ),
      catalogProviderFound: (
        if $models_dev_status != "ok" then null else ($provider_metadata != null) end
      ),
      liveFound: (
        if $models_dev_status != "ok" or $provider_metadata == null then null
        else ($metadata != null)
        end
      ),
      liveMetadata: (
        if $metadata == null then null else {
          name: ($metadata.name // $entry.catalogModel),
          releaseDate: ($metadata.release_date // null),
          lastUpdated: ($metadata.last_updated // null),
          reasoning: ($metadata.reasoning // false),
          toolCall: ($metadata.tool_call // null),
          modalities: ($metadata.modalities // null),
          limit: ($metadata.limit // null),
          cost: ($metadata.cost // null)
        } end
      ),
      openRouterFound: (
        if $entry.catalogProvider != "openrouter" or $openrouter_status != "ok" then null
        else any($openrouter_models[]; .id == $entry.catalogModel)
        end
      ),
      openRouterMetadata: (
        if $entry.catalogProvider != "openrouter" then null
        else (
          [$openrouter_models[] | select(.id == $entry.catalogModel)][0] // null |
          if . == null then null else {
            name: (.name // $entry.catalogModel),
            created: (.created // null),
            contextLength: (.context_length // null),
            pricing: (.pricing // null),
            expirationDate: (.expiration_date // null)
          } end
        ) end
      )
    }
  )) as $audited |
  ($audited | map(.catalogProvider) | unique) as $providers |
  ($audited | map(select(.catalogProvider == "openrouter") |
    .catalogModel | split("/")[0]) | unique) as $openrouter_namespaces |
  (($pi_version != "" and $latest_pi_version != "") and
    (($latest_pi_version | version_parts) > ($pi_version | version_parts))) as $npm_update_available |
  (if $brew_status == "ok" then $brew_update_available else $npm_update_available end) as $pi_update_available |

  {
    generatedAt: $generated_at,
    mode: (if $offline then "offline" else "hybrid" end),
    readOnly: true,
    sources: {
      routerConfig: {path: $router_path, status: $router_status},
      consensusConfig: {path: $consensus_path, status: $consensus_status},
      piCatalog: {status: $pi_status, installedVersion: (if $pi_version == "" then null else $pi_version end)},
      modelsDev: {status: $models_dev_status, url: $models_dev_url},
      openRouter: {status: $openrouter_status, url: $openrouter_url},
      piRelease: {status: $pi_release_status, latestVersion: (if $latest_pi_version == "" then null else $latest_pi_version end)},
      homebrew: {
        status: $brew_status,
        formula: (if $brew_formula == "" then null else $brew_formula end),
        installedVersion: (if $brew_installed_version == "" then null else $brew_installed_version end),
        latestVersion: (if $brew_latest_version == "" then null else $brew_latest_version end)
      }
    },
    piUpdateAvailable: $pi_update_available,
    piNpmUpdateAvailable: $npm_update_available,
    piHomebrewUpdateAvailable: (if $brew_status == "ok" then $brew_update_available else null end),
    configuredModels: $audited,
    recentByProvider: (reduce $providers[] as $provider ({};
      .[$provider] = recent($live[$provider].models; 8)
    )),
    recentOpenRouterByNamespace: (reduce $openrouter_namespaces[] as $namespace ({};
      .[$namespace] = recent(
        ($live.openrouter.models // {} | with_entries(select(.key | startswith($namespace + "/"))));
        8
      )
    )),
    findings: (
      [
        if $router_status != "ok" then
          {severity: "error", kind: "config", source: "model-tier-router", message: ("router config is " + $router_status)}
        else empty end,
        if $consensus_status != "ok" then
          {severity: "error", kind: "config", source: "second-opinion", message: ("panel config is " + $consensus_status)}
        else empty end,
        if $brew_status == "ok" and $brew_update_available then
          {severity: "review", kind: "pi-update", manager: "homebrew", current: $brew_installed_version, candidate: $brew_latest_version, message: "a newer Pi version is available from the installed Homebrew formula"}
        elif $brew_status != "ok" and $npm_update_available then
          {severity: "review", kind: "pi-update", manager: "npm", current: $pi_version, candidate: $latest_pi_version, message: "a newer Pi npm release may contain fresher built-in model metadata"}
        elif $brew_status == "ok" and $npm_update_available then
          {severity: "review", kind: "pi-npm-ahead-of-homebrew", manager: "homebrew", current: $brew_installed_version, candidate: $latest_pi_version, message: "a newer Pi npm release exists, but Homebrew currently reports no formula update"}
        else empty end
      ] +
      [
        $audited[] |
        select(.piAvailable == false) |
        {severity: "warning", kind: "pi-unavailable", model: .model, usage: .usage, message: "configured model is not available in the active Pi catalog/auth scope"}
      ] +
      [
        $audited[] |
        select(.liveFound == false) |
        {severity: "warning", kind: "live-missing", model: .model, usage: .usage, message: "configured model is absent from the mapped live models.dev catalog"}
      ] +
      [
        $audited[] |
        select(.openRouterFound == false) |
        {severity: "warning", kind: "openrouter-missing", model: .model, usage: .usage, message: "configured model is absent from the live public OpenRouter model catalog"}
      ] +
      [
        $audited[] |
        select(.openRouterMetadata.expirationDate != null) |
        {severity: "review", kind: "openrouter-expiration", model: .model, usage: .usage, expirationDate: .openRouterMetadata.expirationDate, message: "OpenRouter reports an expiration date for this model"}
      ]
    )
  }
'