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

for invariant in \
    'owner/repo#number' \
    'PR URL' \
    'current-repository shorthand' \
    'gh-pr-snapshot.py' \
    '`--expected-head`' \
    '--expected-state-key' \
    '`--automation`' \
    '`--premium-established`' \
    'must not prompt' \
    '`complete`' \
    '`partial`' \
    '`stale`' \
    '`failed`' \
    'matching checkout' \
    'HEAD exactly matches' \
    'Local repository search unavailable' \
    'No GitHub review' \
    'schemaVersion' \
    'review-pr/v1' \
    '"reason"' \
    'premium-route-unavailable' \
    'target fields are' \
    'changesOverview' \
    'checkoutReason' \
    'jiraKey' \
    'jiraSummary' \
    'Unresolved Reviewer Comments'; do
    assert_contains "$invariant"
done

if grep -Fq 'gh pr view {PR_NUMBER}' "$SKILL"; then
    fail 'review-pr must not document cwd-scoped PR fetching'
fi
if grep -Fq 'gh pr diff {PR_NUMBER}' "$SKILL"; then
    fail 'review-pr must not document cwd-scoped diff fetching'
fi
if grep -Eq '^[[:space:]]*(gh pr review|gh pr comment|git checkout|git switch|git fetch|git reset|git clean)' "$SKILL"; then
    fail 'review-pr must remain read-only'
fi

printf '%s\n' 'review-pr contract tests passed'
