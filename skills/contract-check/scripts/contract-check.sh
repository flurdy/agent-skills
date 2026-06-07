#!/bin/bash
# contract-check.sh — Audit health of pact contract tests across letterbox services
# Performs mechanical checks: staleness, uncommitted files, sync coverage, relationship matrix

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Find project root (look for .mgit.conf)
find_project_root() {
    local dir="$PWD"
    while [[ "$dir" != "/" ]]; do
        [[ -f "$dir/.mgit.conf" ]] && echo "$dir" && return
        dir="$(dirname "$dir")"
    done
    echo "ERROR: Could not find .mgit.conf (run from within the letterbox project)" >&2
    exit 1
}

PROJECT_ROOT="$(find_project_root)"
cd "$PROJECT_ROOT"

MGIT="./scripts/mgit"
SYNC_SCRIPT="./scripts/sync-pacts.sh"

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

    local stale=0 ok=0 missing_consumer=0 missing_provider=0 total=0

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
                # Check content equality too
                if ! cmp -s "$consumer_file" "$provider_file"; then
                    echo "DIFFERS  $consumer -> $provider  (same age but content differs)"
                    stale=$((stale + 1))
                else
                    echo "OK  $consumer -> $provider"
                    ok=$((ok + 1))
                fi
            fi
        fi
    done

    if [[ "$total" -eq 0 ]]; then
        echo "NO_DATA  No consumer pact files found in */target/pacts/"
        echo "         Run consumer tests first (make test-contract in consumer services)"
    fi

    echo ""
    echo "SUMMARY  stale=$stale ok=$ok missing_provider=$missing_provider total=$total"
}

# ─── UNCOMMITTED CHECK ───────────────────────────────────────────────────────

check_uncommitted() {
    echo "## Uncommitted Pact Files"
    echo ""

    local uncommitted=0 services_checked=0

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
        status_output="$($MGIT status "$service" -- "$pact_rel/" 2>/dev/null)" || continue

        # Filter for actual file status lines (modified:, new file:, deleted:, ??)
        while IFS= read -r line; do
            [[ -z "$line" ]] && continue

            local trimmed
            trimmed="$(echo "$line" | sed 's/^[[:space:]]*//')"
            [[ -z "$trimmed" ]] && continue

            # Only keep lines that are actual file statuses
            [[ "$trimmed" =~ ^(modified:|new\ file:|deleted:|renamed:|copied:|\?\?) ]] || continue

            echo "UNCOMMITTED  $service  $trimmed"
            uncommitted=$((uncommitted + 1))
        done <<< "$status_output"
    done

    if [[ "$uncommitted" -eq 0 ]]; then
        echo "CLEAN  All pact files are committed across $services_checked provider services"
    else
        echo ""
        echo "HINT  Some diffs may be UUID/date noise. Run 'make normalize-pacts' first to reduce noise."
    fi

    echo ""
    echo "SUMMARY  uncommitted=$uncommitted services_checked=$services_checked"
}

# ─── SYNC COVERAGE ───────────────────────────────────────────────────────────

check_sync_gaps() {
    echo "## Sync Coverage (sync-pacts.sh)"
    echo ""

    # Parse sync-pacts.sh for covered pairs
    local -A covered_pairs
    if [[ -f "$SYNC_SCRIPT" ]]; then
        while IFS= read -r line; do
            # Match: copy_pact "consumer" "provider"
            if [[ "$line" =~ copy_pact[[:space:]]+\"([^\"]+)\"[[:space:]]+\"([^\"]+)\" ]]; then
                local consumer="${BASH_REMATCH[1]}"
                local provider="${BASH_REMATCH[2]}"
                covered_pairs["$consumer->$provider"]=1
            fi
        done < "$SYNC_SCRIPT"
    else
        echo "WARNING  sync-pacts.sh not found at $SYNC_SCRIPT"
    fi

    local covered=0 not_synced=0 total=0

    # Find all consumer-generated pact files and check sync coverage
    for consumer_file in */target/pacts/*-consumer-*-provider.json; do
        [[ -f "$consumer_file" ]] || continue
        total=$((total + 1))

        local filename
        filename="$(basename "$consumer_file")"

        local consumer provider
        consumer="$(echo "$filename" | sed 's/-consumer-.*//')"
        provider="$(echo "$filename" | sed 's/.*-consumer-//' | sed 's/-provider\.json//')"

        local key="$consumer->$provider"

        if [[ -n "${covered_pairs[$key]:-}" ]]; then
            echo "COVERED     $consumer -> $provider"
            covered=$((covered + 1))
        else
            echo "NOT_SYNCED  $consumer -> $provider  (has pact in target/ but not in sync-pacts.sh)"
            not_synced=$((not_synced + 1))
        fi
    done

    # Also check: pairs in sync-pacts.sh that have no consumer pact file
    for key in "${!covered_pairs[@]}"; do
        local consumer="${key%%->*}"
        local provider="${key##*->}"
        local found=false
        for f in "$consumer/target/pacts/"*"-consumer-$provider-provider.json"; do
            [[ -f "$f" ]] && found=true && break
        done
        if ! $found; then
            echo "STALE_SYNC  $consumer -> $provider  (in sync-pacts.sh but no consumer pact file — tests not run?)"
        fi
    done

    echo ""
    echo "SUMMARY  covered=$covered not_synced=$not_synced total=$total"
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
# Does each provider's CI actually VERIFY the consumer pacts synced into it?
# This is distinct from sync-gaps (is the pact registered for sync?): a pact can
# be synced into the provider yet never verified by the provider's CI.
# Two CI styles in letterbox:
#   tag  -> `sbt testOnly -- -n tags.ContractVerifyTest` auto-verifies EVERY
#           synced pact (good — nothing to enumerate).
#   enum -> PACTCONSUMER env vars enumerate consumers explicitly; any consumer
#           that is commented out (or simply not listed) is NOT verified — a
#           silent coverage hole where the provider can break that consumer.

check_coverage() {
    echo "## CI Verification Coverage"
    echo ""
    local gaps=0 ok=0 providers=0

    for pact_dir in */test/resources/pacts */src/test/resources/pacts; do
        [[ -d "$pact_dir" ]] || continue
        local provider
        provider="$(echo "$pact_dir" | cut -d'/' -f1)"

        # Consumers whose pact is synced into this provider's source tree.
        local -a synced=()
        for f in "$pact_dir"/*-consumer-"$provider"-provider.json; do
            [[ -f "$f" ]] || continue
            synced+=("$(basename "$f" | sed 's/-consumer-.*//')")
        done
        [[ ${#synced[@]} -eq 0 ]] && continue
        providers=$((providers + 1))

        local cfg="$provider/.circleci/config.yml"
        if [[ ! -f "$cfg" ]]; then
            echo "GAP  $provider  no .circleci/config.yml (cannot verify ${#synced[@]} consumer(s))"
            gaps=$((gaps + 1))
            continue
        fi

        # Active (uncommented) PACTCONSUMER entries, normalised to the bare name.
        local -a active=()
        while IFS= read -r val; do
            [[ -z "$val" ]] && continue
            active+=("$(echo "$val" | sed 's/-consumer//')")
        done < <(grep -E '^[[:space:]]*PACTCONSUMER[0-9]*:' "$cfg" 2>/dev/null \
                 | sed -E 's/.*PACTCONSUMER[0-9]*:[[:space:]]*//')

        local style="" ; local -a unverified=()
        if [[ ${#active[@]} -gt 0 ]]; then
            style="enum"
            local c a found
            for c in "${synced[@]}"; do
                found=false
                for a in "${active[@]}"; do [[ "$a" == "$c" ]] && found=true && break; done
                $found || unverified+=("$c")
            done
        elif grep -q "ContractVerifyTest" "$cfg" 2>/dev/null; then
            style="tag"   # verifies every synced pact — no enumeration to miss
        else
            style="none"
            unverified=("${synced[@]}")
        fi

        if [[ ${#unverified[@]} -gt 0 ]]; then
            local list; list="$(IFS=,; echo "${unverified[*]}")"
            echo "GAP  $provider  style=$style synced=${#synced[@]} not-verified=$list"
            gaps=$((gaps + 1))
        else
            echo "OK   $provider  style=$style synced=${#synced[@]} verified"
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
    echo "  sync-gaps    Check sync-pacts.sh coverage (is the pact registered for sync?)"
    echo "  coverage     Check CI verification coverage (does the provider verify each synced pact?)"
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
