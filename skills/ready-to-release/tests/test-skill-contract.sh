#!/usr/bin/env bash
set -euo pipefail

SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/SKILL.md"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_has() {
    local text="$1"
    grep -Fq -- "$text" "$SKILL" || fail "expected '$text' in $SKILL"
}

assert_not_has() {
    local text="$1"
    if grep -Fq -- "$text" "$SKILL"; then
        fail "did not expect '$text' in $SKILL"
    fi
}

assert_has 'allowed-tools: "Read,Bash(./scripts/release-digest:*),Bash(./scripts/release-order:*),Bash(./scripts/contract-check:*)"'
assert_has 'service|unpushed|uncommitted|ci|ciBranch|gitBranch|head|deploy|tag|age|ciRevision|ciExpectedRevision'
assert_has '`Gate | Result | Evidence`'
assert_has '`➖ N/A`'
assert_has 'An N/A row is never a blocker by itself'
assert_has 'ciBranch == gitBranch'
assert_has 'both revisions must be non-`-`'
assert_has 'ciRevision == ciExpectedRevision'
assert_has 'Exact `success` → `✅ pass`; exact `failed`/`error` → `❌ block`; exact `running` → `⚠️ hold`'
assert_has '`provider=none` with an empty graph is valid'
assert_has '`non_deploying` service → `➖ N/A` with no verdict impact'
assert_has 'order evidence is unavailable'
assert_has 'no contract relationship applies'
assert_has 'no toggle policy applies'
assert_has 'deployment evidence is unavailable'
assert_has 'unavailable safety-critical evidence produces `HOLD ⚠️`'
assert_has 'Hard blockers take precedence over holds'
assert_has 'never prompt and never mutate state'

assert_not_has 'letterbox'
assert_not_has 'CircleCI'
assert_not_has 'AskUserQuestion'
assert_not_has 'Write,'
assert_not_has 'Edit,'
assert_not_has 'Bash(make'
assert_not_has 'make ci-status'
assert_not_has 'make deploy-status'
assert_not_has 'make feature-toggles'

printf '%s\n' 'ready-to-release portability contract tests passed'
