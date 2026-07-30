#!/usr/bin/env bash
set -euo pipefail

ROOT=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P)
TILDE='~'
COLLECTOR="${TILDE}/.agents/skills/pr-status/scripts/gh-pr-feedback.py"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

for skill in pr-status review-comments reply-comments watch-prs; do
    file="$ROOT/skills/$skill/SKILL.md"
    [[ -f "$file" ]] || fail "missing $file"
    grep -Fq -- "$COLLECTOR" "$file" || fail "$skill does not use the shared feedback inventory"
done

for invariant in \
    'stable `identity` plus `updatedAt`' \
    'new or materially edited' \
    'partial' \
    'read-only'; do
    grep -Fq -- "$invariant" "$ROOT/skills/pr-status/SKILL.md" \
        || fail "pr-status missing inventory invariant: $invariant"
done

grep -Fq -- 'Pending draft review comments are not observable' "$ROOT/skills/pr-status/SKILL.md" \
    || fail 'pending review visibility boundary is undocumented'
grep -Fq -- 'reply or resolution endpoint' "$ROOT/skills/reply-comments/SKILL.md" \
    || fail 'reply-comments does not preserve endpoint identity'
grep -Fq -- 'agent judgment' "$ROOT/skills/review-comments/SKILL.md" \
    || fail 'review-comments does not separate API classification from semantic judgment'

printf '%s\n' 'PR feedback inventory consumer contract passed'
