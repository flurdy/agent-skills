#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
skill="$SKILL_DIR/SKILL.md"
for required in 'Do not recompute' 'never prompt' 'read-only' 'NOT READY' 'activation' 'errors' 'full-project'; do
    grep -Fq "$required" "$skill" || fail "missing passive dashboard invariant: $required"
done
if grep -Eq 'Bash\((make|kubectl|bd)|Write|AskUserQuestion' "$skill"; then
    fail 'passive dashboard has mutation or prompt tools'
fi
printf '%s\n' 'release status delegation contract tests passed'
