#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
[ -x "$SKILL_DIR/scripts/release-gates" ] || fail 'missing executable readiness authority'
for consumer in ready-to-release release-status release-manager; do
    skill="$SKILL_DIR/../$consumer/SKILL.md"
    grep -Fq '/skills/ready-to-release/scripts/release-gates' "$skill" || fail "$consumer must call the shared authority"
    grep -Fq 'Do not recompute' "$skill" || fail "$consumer must not duplicate verdict policy"
    if grep -Eq 'Bash\(\./scripts/(release-digest|release-order|contract-check):' "$skill"; then
        fail "$consumer still collects release evidence independently"
    fi
done
grep -Fq 'false' "$SKILL_DIR/references/evidence-contract.md" || fail 'toggle policy undocumented'
grep -Fq 'non-deploying' "$SKILL_DIR/references/evidence-contract.md" || fail 'non-deploying boundary undocumented'
grep -Fq 'never prompt' "$SKILL_DIR/SKILL.md" || fail 'deep gate must remain passive'
printf '%s\n' 'release readiness authority contract tests passed'
