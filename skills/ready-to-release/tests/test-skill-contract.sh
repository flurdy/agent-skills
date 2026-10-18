#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
[ -x "$SKILL_DIR/scripts/release-gates" ] || fail 'missing executable readiness authority'
for consumer in ready-to-release release-status release-manager; do
    skill="$SKILL_DIR/../$consumer/SKILL.md"
    grep -Fq '/skills/ready-to-release/scripts/release-gates' "$skill" || fail "$consumer must call the shared authority"
    grep -Fq 'Do not recompute' "$skill" || fail "$consumer must not duplicate verdict policy"
    grep -Fq 'RELEASE CHECK INCOMPLETE' "$skill" || fail "$consumer must render collection failures prominently"
    if grep -Eq 'Bash\(\./scripts/(release-digest|release-order|contract-check):' "$skill"; then
        fail "$consumer still collects release evidence independently"
    fi
done
grep -Fq 'false' "$SKILL_DIR/references/evidence-contract.md" || fail 'toggle policy undocumented'
grep -Fq 'non-deploying' "$SKILL_DIR/references/evidence-contract.md" || fail 'non-deploying boundary undocumented'
grep -Fq 'never prompt' "$SKILL_DIR/SKILL.md" || fail 'deep gate must remain passive'
contract="$SKILL_DIR/references/evidence-contract.md"
for required in 'config_uptake' 'release-config-uptake' 'adds no gate, never' 'never an action' 'resourceVersion movement' 'legacy digest'; do
    grep -Fq "$required" "$contract" || fail "config uptake undocumented: $required"
done
for consumer in ready-to-release release-status release-manager release-maintenance; do
    grep -Fq 'configUptake' "$SKILL_DIR/../$consumer/SKILL.md" || fail "$consumer must treat configUptake as advisory"
done
for consumer in ready-to-release release-status release-manager; do
    grep -Eq 'restart[^.]*(handoff|not an action|never dispatched)' "$SKILL_DIR/../$consumer/SKILL.md" || fail "$consumer must not act on restart recommendations"
done
printf '%s\n' 'release readiness authority contract tests passed'
