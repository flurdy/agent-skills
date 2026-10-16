#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
for script in release-order release-ci pact-graph release-state; do
    [ -x "$SKILL_DIR/scripts/$script" ] || fail "missing executable $script adapter"
done
grep -Fq pact-graph "$SKILL_DIR/scripts/release-order" || fail 'order adapter must compose Pact'
skill="$SKILL_DIR/SKILL.md"
for required in 'Do not recompute' 'fresh authority result' 'exact command' 'only `READY`' 'Legacy maintenance state' 'next-tick:' 'upstream' 'malformed' 'one active manager'; do
    grep -Fq "$required" "$skill" || fail "missing manager invariant: $required"
done
for required in 'away from keyboard' '"reason": "unanswered"' 'is not an answer' 'ask no further push question this tick' 'push <service>' '| Response | Executed |' 'Before the blocking question' 'explicit current answer'; do
    grep -Fq -- "$required" "$skill" || fail "missing unanswered-prompt invariant: $required"
done
unanswered_line=$(grep -nF -- '**Unanswered:**' "$skill" | head -1 | cut -d: -f1)
table_line=$(grep -nF -- '| Response | Executed |' "$skill" | head -1 | cut -d: -f1)
[ -n "$unanswered_line" ] && [ -n "$table_line" ] && [ "$table_line" -lt "$unanswered_line" ] \
    || fail 'permission-request table must precede the unanswered outcome rules'
if grep -Eiq 'preselected[^.]*(counts|authoriz)' "$skill"; then
    fail 'a preselected option must never count as an answer'
fi
if grep -Eq 'Bash\((kubectl|make k8s-sync|make feature-toggles-disabled|\./scripts/release-order)' "$skill"; then
    fail 'recurring manager retains infrastructure mutation authority'
fi
if grep -Eq 'ln -sfn|chmod \+x|resourceVersion.*moves|ageBaseline.*fresh' "$skill"; then
    fail 'recurring manager retains setup repair or heuristic restart confirmation'
fi
maintenance="$SKILL_DIR/../release-maintenance/SKILL.md"
for file in "$skill" "$maintenance"; do
    allowed=$(grep -m1 '^allowed-tools:' "$file")
    if printf '%s' "$allowed" | grep -Eq '"Write,|,Write,|,Write"'; then
        fail "$(basename "$(dirname "$file")") must write release state only through release-state"
    fi
    printf '%s' "$allowed" | grep -Fq 'Bash(~/.agents/skills/release-manager/scripts/release-state:*)' \
        || fail "$(basename "$(dirname "$file")") must allow the release-state helper"
done
for required in 'release-state update --owner manager' 'publishing' 'conflict' 'begin-publication' 'finish-publication' 'publish_commit' 'token' 'ask for `/implement`' 'make git-push'; do
    grep -Fq -- "$required" "$skill" || fail "missing coordinated state invariant: $required"
done
for required in 'release-state update --owner maintenance' 'resolve-publication'; do
    grep -Fq -- "$required" "$maintenance" || fail "missing maintenance state invariant: $required"
done
for required in './scripts/release-order --write' 'never invoked by' 'one visible command' '--context' 'generation' 'Legacy maintenance state' 'acknowledge-rollout'; do
    grep -Fq -- "$required" "$maintenance" || fail "missing isolated maintenance invariant: $required"
done
if grep -Eq 'Bash\((kubectl --context|\./scripts/mgit:\*)' "$maintenance"; then
    fail 'maintenance must not blanket-preapprove mutating Git/Kubernetes commands'
fi
printf '%s\n' 'release action ownership contract tests passed'
