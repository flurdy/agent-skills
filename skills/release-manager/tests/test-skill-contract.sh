#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
for script in release-order release-ci pact-graph; do
    [ -x "$SKILL_DIR/scripts/$script" ] || fail "missing executable $script adapter"
done
grep -Fq pact-graph "$SKILL_DIR/scripts/release-order" || fail 'order adapter must compose Pact'
skill="$SKILL_DIR/SKILL.md"
for required in 'Do not recompute' 'fresh authority result' 'exact command' 'only `READY`' 'Legacy maintenance state' 'next-tick:' 'upstream' 'malformed' 'one active manager'; do
    grep -Fq "$required" "$skill" || fail "missing manager invariant: $required"
done
if grep -Eq 'Bash\((kubectl|make k8s-sync|make feature-toggles-disabled|\./scripts/release-order)' "$skill"; then
    fail 'recurring manager retains infrastructure mutation authority'
fi
if grep -Eq 'ln -sfn|chmod \+x|resourceVersion.*moves|ageBaseline.*fresh' "$skill"; then
    fail 'recurring manager retains setup repair or heuristic restart confirmation'
fi
maintenance="$SKILL_DIR/../release-maintenance/SKILL.md"
for required in './scripts/release-order --write' 'never invoked by' 'one visible command' '--context' 'generation' 'Legacy maintenance state' 'acknowledge-rollout'; do
    grep -Fq -- "$required" "$maintenance" || fail "missing isolated maintenance invariant: $required"
done
if grep -Eq 'Bash\((kubectl --context|\./scripts/mgit:\*)' "$maintenance"; then
    fail 'maintenance must not blanket-preapprove mutating Git/Kubernetes commands'
fi
printf '%s\n' 'release action ownership contract tests passed'
