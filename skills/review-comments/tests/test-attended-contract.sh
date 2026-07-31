#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL="$TEST_DIR/../SKILL.md"

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
    grep -nF -- "$heading" "$SKILL" | head -1 | cut -d: -f1
}

[[ -f "$SKILL" ]] || fail "missing review-comments skill"

for invariant in \
    'version: "1.2.0"' \
    '`owner/repo#number`' \
    'matching checkout' \
    'stable `identity`' \
    '`updateKey`' \
    '`stateKey`' \
    '`targets`' \
    '### 4. Select Items' \
    'No code change occurs before explicit item selection' \
    '### 5. Validate Selected Items' \
    'confirmed defect' \
    'valid improvement' \
    'question needing an answer' \
    'subjective/trade-off decision' \
    'false positive/already handled' \
    'stale/outdated' \
    'out of scope' \
    'unable to validate' \
    '### 6. Choose a Local Action' \
    'Fix and verify' \
    'Prepare reply' \
    'Acknowledge only' \
    'Defer / skip with rationale' \
    'Security' \
    'architecture' \
    'scope-changing' \
    'low-confidence' \
    'happy path' \
    'sad path' \
    'edge case' \
    'Stage explicit paths' \
    'commit locally' \
    'Never publishes' \
    '`/reply-comments`' \
    'Feedback ID' \
    'Validation' \
    'Files/tests/commit' \
    'Push state' \
    'Reply' \
    'Resolution'; do
    assert_contains "$invariant"
done

select_line=$(line_of '### 4. Select Items')
validate_line=$(line_of '### 5. Validate Selected Items')
action_line=$(line_of '### 6. Choose a Local Action')
[[ -n "$select_line" && -n "$validate_line" && -n "$action_line" ]] || fail 'selection, validation, and action sections must exist'
((select_line < validate_line && validate_line < action_line)) || fail 'selection must precede validation and local action'

if grep -Eq '^[[:space:]]*git push([[:space:]]|$)' "$SKILL"; then
    fail 'review-comments must not execute a push'
fi
if grep -Eq -- '--force(-with-lease)?' "$SKILL"; then
    fail 'review-comments must not introduce force push'
fi

printf '%s\n' 'review-comments attended contract tests passed'
