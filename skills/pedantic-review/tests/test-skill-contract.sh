#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL="$SKILL_DIR/SKILL.md"
TEXT=$(tr '\n' ' ' < "$SKILL")
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
for invariant in 'supplied scope' 'Test design' 'Not assessed here' 'verify-task' 'Do not infer test-writing chronology' 'cannot clear the overall review' 'No automatic fixes' 'read-only' 'gh-pr-snapshot.py'; do
    grep -Fq "$invariant" <<< "$TEXT" || fail "missing craft invariant: $invariant"
done
if grep -Eq 'gh pr diff|test count go up|tests written after|post-hoc|Flag specific uncovered branches|ready for `/create-pr`' "$SKILL"; then
    fail 'craft review still owns coverage chronology or publication'
fi
grep -Fq 'invalidate G2' "$SKILL_DIR/../total-review/SKILL.md" || fail 'later coverage findings must reopen earlier verification'
printf '%s\n' 'pedantic review role contract tests passed'
