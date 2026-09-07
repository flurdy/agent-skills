#!/bin/bash
# contract-check.sh — Audit health of pact contract tests across project services
# Performs mechanical checks: staleness, uncommitted files, sync coverage, relationship matrix

set -euo pipefail

# Find project root (look for .mgit.conf)
find_project_root() {
    local dir="$PWD"
    while [[ "$dir" != "/" ]]; do
        [[ -f "$dir/.mgit.conf" ]] && echo "$dir" && return
        dir="$(dirname "$dir")"
    done
    echo "ERROR: Could not find .mgit.conf (run from within the project)" >&2
    exit 1
}

if [[ -n "${RELEASE_PROJECT_ROOT:-}" ]]; then
    [[ "$RELEASE_PROJECT_ROOT" = /* && -d "$RELEASE_PROJECT_ROOT" ]] || {
        echo "ERROR: RELEASE_PROJECT_ROOT must be an existing absolute directory" >&2
        exit 1
    }
    PROJECT_ROOT="$RELEASE_PROJECT_ROOT"
else
    PROJECT_ROOT="$(find_project_root)"
fi
cd "$PROJECT_ROOT"

MGIT="./scripts/mgit"

# Provider pact directories — two layouts coexist:
#   Play services:    test/resources/pacts/
#   http4s/Scala 3:   src/test/resources/pacts/
# Detect dynamically (which dir actually holds the provider's pacts) rather than
# maintaining a hardcoded service list — robust to new http4s services.
pact_dir_for_provider() {
    local provider=$1 d
    for d in "test/resources/pacts" "src/test/resources/pacts"; do
        if compgen -G "$provider/$d/*-provider.json" > /dev/null 2>&1; then
            echo "$d"; return
        fi
    done
    # No synced pacts yet — fall back to whichever layout the service uses.
    [[ -d "$provider/src/test/resources/pacts" ]] && echo "src/test/resources/pacts" || echo "test/resources/pacts"
}

# ─── STALE CHECK ─────────────────────────────────────────────────────────────

check_stale() {
    echo "## Staleness Report"
    echo ""

    local stale=0 ok=0 missing_provider=0 total=0

    # Find all consumer-generated pact files
    for consumer_file in */target/pacts/*-consumer-*-provider.json; do
        [[ -f "$consumer_file" ]] || continue
        total=$((total + 1))

        local filename
        filename="$(basename "$consumer_file")"

        # Extract provider name from filename: <consumer>-consumer-<provider>-provider.json
        local provider
        provider="$(echo "$filename" | sed 's/.*-consumer-//' | sed 's/-provider\.json//')"

        local consumer
        consumer="$(echo "$filename" | sed 's/-consumer-.*//')"

        local pact_dir
        pact_dir="$(pact_dir_for_provider "$provider")"
        local provider_file="$provider/$pact_dir/$filename"

        if [[ ! -f "$provider_file" ]]; then
            echo "MISSING_PROVIDER  $consumer -> $provider  (provider file not found: $provider_file)"
            missing_provider=$((missing_provider + 1))
        elif cmp -s "$consumer_file" "$provider_file"; then
            echo "OK  $consumer -> $provider"
            ok=$((ok + 1))
        else
            local consumer_ts provider_ts
            consumer_ts="$(stat -c %Y "$consumer_file" 2>/dev/null || echo 0)"
            provider_ts="$(stat -c %Y "$provider_file" 2>/dev/null || echo 0)"

            if [[ "$consumer_ts" -gt "$provider_ts" ]]; then
                local consumer_date provider_date delta_days
                consumer_date="$(date -d "@$consumer_ts" '+%Y-%m-%d')"
                provider_date="$(date -d "@$provider_ts" '+%Y-%m-%d')"
                delta_days=$(( (consumer_ts - provider_ts) / 86400 ))
                echo "STALE  $consumer -> $provider  (consumer: $consumer_date, provider: $provider_date, delta: ${delta_days}d)"
                stale=$((stale + 1))
            else
                echo "DIFFERS  $consumer -> $provider  (content differs; consumer not newer)"
                stale=$((stale + 1))
            fi
        fi
    done

    if [[ "$total" -eq 0 ]]; then
        echo "NO_DATA  No consumer pact files found in */target/pacts/"
        echo "         Generation is a separate /contract-test consumer request using inspected project commands"
    fi

    echo ""
    echo "SUMMARY  stale=$stale ok=$ok missing_provider=$missing_provider total=$total"
}

# ─── UNCOMMITTED CHECK ───────────────────────────────────────────────────────

check_uncommitted() {
    echo "## Uncommitted Pact Files"
    echo ""

    local uncommitted=0 services_checked=0 failed=0

    # Check provider services for uncommitted pact files
    for provider_dir in */test/resources/pacts */src/test/resources/pacts; do
        [[ -d "$provider_dir" ]] || continue

        local service
        service="$(echo "$provider_dir" | cut -d'/' -f1)"
        services_checked=$((services_checked + 1))

        # Get relative pact path within the service
        local pact_rel
        pact_rel="${provider_dir#$service/}"

        # Use mgit to check status
        local status_output
        if ! status_output="$(GIT_OPTIONAL_LOCKS=0 "$MGIT" status "$service" --porcelain=v1 --untracked-files=all -- "$pact_rel/" 2>/dev/null)"; then
            echo "NO_DATA  $service Git status unavailable; uncommitted pacts are UNKNOWN"
            failed=$((failed + 1))
            continue
        fi

        while IFS= read -r line; do
            [[ -z "$line" ]] && continue
            printf 'UNCOMMITTED  %s  %s\n' "$service" "$line"
            uncommitted=$((uncommitted + 1))
        done <<< "$status_output"
    done

    if [[ "$failed" -gt 0 ]]; then
        echo "SUMMARY  uncommitted=$uncommitted services_checked=$services_checked status=error"
        return
    fi
    if [[ "$uncommitted" -eq 0 ]]; then
        echo "CLEAN  All pact files are committed across $services_checked provider services"
    else
        echo ""
        echo "NOTE  Inspect changes before overwriting; generated-looking values are not proof of harmless noise."
    fi

    echo ""
    echo "SUMMARY  uncommitted=$uncommitted services_checked=$services_checked"
}

# ─── SYNC COVERAGE ───────────────────────────────────────────────────────────

# Intended consumer→provider edges (from consumer test files) as "consumer->provider".
# Convention and filtering live in scripts/pact-pairs (the single source of truth).
intended_edges() {
    ./scripts/pact-pairs intended | awk -F'\t' '{print $1 "->" $2}'
}

# An unusable collector is reported as an error, never as zero gaps.
sync_collector_failed() {
    echo "NO_DATA  scripts/pact-pairs $1 failed; sync coverage cannot be determined"
    echo "         Sync gaps are UNKNOWN — do not read this as all-clear"
    echo ""
    echo "SUMMARY  ok=0 not_built=0 not_synced=0 total=0 status=error"
}

check_sync_gaps() {
    echo "## Sync Coverage (consumer test → built pact → provider)"
    echo ""

    # Three convention-derived sets (all from scripts/pact-pairs), no registry:
    # each intended edge is traced through its lifecycle test → built → synced.
    local -A built synced_edges
    local c p
    # Capture each collector's output and exit status before parsing. set -e does
    # not see a failure inside a process substitution, so a missing or dying
    # pact-pairs would otherwise fall through to an all-clear total=0 summary.
    local built_raw synced_raw intended_raw
    if ! built_raw="$(./scripts/pact-pairs built)"; then
        sync_collector_failed built
        return
    fi
    if ! synced_raw="$(./scripts/pact-pairs synced)"; then
        sync_collector_failed synced
        return
    fi
    if ! intended_raw="$(intended_edges | sort -u)"; then
        sync_collector_failed intended
        return
    fi

    while IFS=$'\t' read -r c p _; do [[ -n "$c" ]] && built["$c->$p"]=1; done <<<"$built_raw"
    while IFS=$'\t' read -r c p _; do [[ -n "$c" ]] && synced_edges["$c->$p"]=1; done <<<"$synced_raw"

    local ok=0 not_built=0 not_synced=0 total=0 key
    while IFS= read -r key; do
        [[ -n "$key" ]] || continue
        total=$((total + 1))
        if [[ -z "${built[$key]:-}" ]]; then
            echo "NOT_BUILT   ${key/->/ -> }  (consumer test present but no pact in target/ — tests not run?)"
            not_built=$((not_built + 1))
        elif [[ -z "${synced_edges[$key]:-}" ]]; then
            echo "NOT_SYNCED  ${key/->/ -> }  (built but not copied to provider; /contract-test sync is a separate request)"
            not_synced=$((not_synced + 1))
        else
            echo "OK          ${key/->/ -> }"
            ok=$((ok + 1))
        fi
    done <<<"$intended_raw"

    echo ""
    echo "SUMMARY  ok=$ok not_built=$not_built not_synced=$not_synced total=$total"
}

# ─── RELATIONSHIP MATRIX ─────────────────────────────────────────────────────

check_matrix() {
    echo "## Contract Relationship Matrix"
    echo ""

    # Gather all relationships from both consumer output and provider input
    local -A relationships

    # From consumer target/pacts/
    for f in */target/pacts/*-consumer-*-provider.json; do
        [[ -f "$f" ]] || continue
        local filename
        filename="$(basename "$f")"
        local consumer provider
        consumer="$(echo "$filename" | sed 's/-consumer-.*//')"
        provider="$(echo "$filename" | sed 's/.*-consumer-//' | sed 's/-provider\.json//')"
        relationships["$consumer->$provider"]="${relationships["$consumer->$provider"]:-} consumer"
    done

    # From provider test/resources/pacts/ and src/test/resources/pacts/
    for f in */test/resources/pacts/*-consumer-*-provider.json */src/test/resources/pacts/*-consumer-*-provider.json; do
        [[ -f "$f" ]] || continue
        local filename
        filename="$(basename "$f")"
        local consumer provider
        consumer="$(echo "$filename" | sed 's/-consumer-.*//')"
        provider="$(echo "$filename" | sed 's/.*-consumer-//' | sed 's/-provider\.json//')"
        relationships["$consumer->$provider"]="${relationships["$consumer->$provider"]:-} provider"
    done

    # Output sorted
    echo "| Consumer | Provider | Sources |"
    echo "|----------|----------|---------|"
    for key in $(echo "${!relationships[@]}" | tr ' ' '\n' | sort); do
        local consumer="${key%%->*}"
        local provider="${key##*->}"
        local sources="${relationships[$key]}"
        # Trim and format sources
        sources="$(echo "$sources" | xargs)"
        echo "| $consumer | $provider | $sources |"
    done

    echo ""
    echo "TOTAL  ${#relationships[@]} relationships"
}

# ─── CI VERIFICATION COVERAGE ────────────────────────────────────────────────
# Bounded static CircleCI text conventions, not YAML/workflow execution analysis.
# Enum literals name consumers; a tag-driven sbt command names an all-pacts selector.
# See references/project-setup.md for assumptions and unsupported shapes.

check_coverage() {
    echo "## CI Verification Coverage"
    echo "NOTE  static configuration text only; does not prove jobs are enabled, reachable, or passing"
    echo ""
    local gaps=0 ok=0 providers=0

    for pact_dir in */test/resources/pacts */src/test/resources/pacts; do
        [[ -d "$pact_dir" ]] || continue
        local provider
        provider="$(echo "$pact_dir" | cut -d'/' -f1)"

        # Consumers whose pact is synced into this provider's source tree.
        local -a synced_consumers=()
        for f in "$pact_dir"/*-consumer-"$provider"-provider.json; do
            [[ -f "$f" ]] || continue
            synced_consumers+=("$(basename "$f" | sed 's/-consumer-.*//')")
        done
        [[ ${#synced_consumers[@]} -eq 0 ]] && continue
        providers=$((providers + 1))

        local cfg="$provider/.circleci/config.yml"
        if [[ ! -f "$cfg" ]]; then
            echo "GAP  $provider  style=unsupported synced=${#synced_consumers[@]} evidence=unavailable (no supported .circleci/config.yml)"
            gaps=$((gaps + 1))
            continue
        fi

        local active_cfg
        if ! active_cfg="$(sed 's/#.*//' "$cfg")"; then
            echo "GAP  $provider  style=unsupported synced=${#synced_consumers[@]} evidence=unavailable (unreadable CI configuration)"
            gaps=$((gaps + 1))
            continue
        fi
        local -a active=()
        local val invalid=false
        while IFS= read -r val; do
            val="$(printf '%s' "$val" | sed -E "s/^[[:space:]]+//; s/[[:space:]]+$//; s/^\"(.*)\"$/\\1/; s/^'(.*)'$/\\1/")"
            if [[ "$val" =~ ^[A-Za-z0-9_][A-Za-z0-9_-]*$ ]]; then
                active+=("${val%-consumer}")
            else
                invalid=true
            fi
        done < <(grep -E '^[[:space:]]*PACTCONSUMER[0-9]*:' <<< "$active_cfg" \
                 | sed -E 's/.*PACTCONSUMER[0-9]*:[[:space:]]*//')

        local style="" ; local -a unverified=()
        local tag_selector='testOnly[[:space:]]+--[[:space:]]+-n[[:space:]]+tags\.ContractVerifyTest'
        if $invalid; then
            style="unsupported"
        elif [[ ${#active[@]} -gt 0 ]]; then
            style="enum"
            local c a found
            for c in "${synced_consumers[@]}"; do
                found=false
                for a in "${active[@]}"; do [[ "$a" == "$c" ]] && found=true && break; done
                $found || unverified+=("$c")
            done
        elif grep -Eq "^[[:space:]]*((-[[:space:]]*)?(run|command):[[:space:]]*)?sbt[[:space:]]+(\"$tag_selector\"|'$tag_selector'|$tag_selector)[[:space:]]*$" <<< "$active_cfg"; then
            style="tag"
        else
            style="unsupported"
        fi

        if [[ "$style" == unsupported ]]; then
            echo "GAP  $provider  style=unsupported synced=${#synced_consumers[@]} evidence=unavailable (no supported literal verification evidence)"
            gaps=$((gaps + 1))
        elif [[ ${#unverified[@]} -gt 0 ]]; then
            local list; list="$(IFS=,; echo "${unverified[*]}")"
            echo "GAP  $provider  style=$style synced=${#synced_consumers[@]} not-verified=$list"
            gaps=$((gaps + 1))
        else
            echo "OK   $provider  style=$style synced=${#synced_consumers[@]} (static configuration names verification)"
            ok=$((ok + 1))
        fi
    done

    echo ""
    echo "SUMMARY  ok=$ok gaps=$gaps providers=$providers"
}

# ─── MAIN DISPATCHER ─────────────────────────────────────────────────────────

usage() {
    echo "Usage: contract-check <command>"
    echo ""
    echo "Commands:"
    echo "  all          Run all mechanical checks"
    echo "  stale        Check for stale provider pact files"
    echo "  uncommitted  Check for uncommitted pact files"
    echo "  sync-gaps    Trace each intended edge: consumer test -> built pact -> synced to provider"
    echo "  coverage     Inspect supported static CI verification evidence (not live CI results)"
    echo "  matrix       Show full relationship matrix"
    echo ""
}

case "${1:-all}" in
    stale)
        check_stale
        ;;
    uncommitted)
        check_uncommitted
        ;;
    sync-gaps|sync)
        check_sync_gaps
        ;;
    coverage)
        check_coverage
        ;;
    matrix)
        check_matrix
        ;;
    all)
        check_stale
        echo ""
        check_uncommitted
        echo ""
        check_sync_gaps
        echo ""
        check_coverage
        echo ""
        check_matrix
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        echo "Unknown command: $1" >&2
        usage
        exit 1
        ;;
esac
