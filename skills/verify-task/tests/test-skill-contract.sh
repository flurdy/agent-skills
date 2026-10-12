#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL="$SKILL_DIR/SKILL.md"
TEXT=$(tr '\n' ' ' < "$SKILL")
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
for invariant in 'next-select resolve' 'bd -C <directory>' 'supplied scope' 'repository-native gates' 'CI' 'manifest' 'peer tests' 'inspect the recipe' 'generated output' 'stale' 'unavailable' 'not-run' 'na' 'No automatic fixes' 'not a requirements source'; do
    grep -Fq "$invariant" <<< "$TEXT" || fail "missing verification invariant: $invariant"
done
if grep -Eq 'Bash\((make|npm|npx|git):\*\)|^make test$|^bd (show|list)|__tests__|TypeScript|Use the title and infer intent' "$SKILL"; then
    fail 'verification retains a guessed runner, layout, requirement, or blanket grant'
fi
grep -Fq 'references/evidence.md' "$SKILL" || fail 'verification must reuse the existing exact-scope evidence contract'
for invariant in 'unavailable-pending-<event>' 'reason `pending-event`' 'Incomplete evidence' 'only missing evidence' 'failed, stale, not-run' 'still blocks finalization' 'deferred-verification tracking handoff' 'Never create, defer or close' '../beads/SKILL.md#deferred-verification'; do
    grep -Fq -- "$invariant" <<< "$TEXT" || fail "missing pending-event verification invariant: $invariant"
done
metadata=$(awk 'NR == 1 { next } /^---$/ { exit } { print }' "$SKILL")
if grep -Eq 'Bash\(bd[^)]* (create|defer|close|update)|Skill\(complete-task\)' <<< "$metadata"; then
    fail 'pending-event handoff must not grant tracker writes or automatic finalization'
fi
printf '%s\n' 'verify task native evidence contract tests passed'
