#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL_DIR=$(dirname -- "$TEST_DIR")
SKILL="$SKILL_DIR/SKILL.md"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_contains() {
    local expected=$1
    grep -Fq -- "$expected" "$SKILL" || fail "expected '$expected' in $SKILL"
}

line_of() {
    local heading=$1
    grep -nF -- "$heading" "$SKILL" | head -1 | cut -d: -f1 || true
}

[[ -f "$SKILL" ]] || fail "missing architect skill"

brief_line=$(line_of '### Decision brief')
tier_line=$(line_of '### Planning tier')
[[ -n "$brief_line" && -n "$tier_line" ]] || fail "decision brief and planning tier must exist"
((brief_line < tier_line)) || fail "decision brief must precede detailed planning output"

for invariant in \
    'Detailed plans are working input, not current architecture documentation.' \
    'Do not create Markdown solely to preserve planning reasoning.' \
    'Exactly one blocked human review owner' \
    'An existing matching review is the sole owner' \
    'Only when no separate review exists, prefer the source spike/design bead' \
    'Whether reusing the source or using a dedicated decision, apply both:' \
    'add the canonical `human` label' \
    'set status `blocked`' \
    'bd list --status open,in_progress,blocked --label human' \
    'source_bead=<source-id>' \
    'Never create a second review item' \
    'Create at most one dedicated review' \
    'do not create a shadow Beads decision' \
    'type `decision`' \
    'canonical `human` label' \
    'status `blocked`' \
    'configured human assignee when one is available' \
    '**Approve**' \
    '**Defer or reject**' \
    '**Request revision**' \
    '/plan-to-backlog <plan-source>' \
    'Do not create implementation children' \
    'Ask for explicit confirmation immediately before any tracker mutation.'; do
    assert_contains "$invariant"
done

printf '%s\n' 'architect contract tests passed'
