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
assert_has 'ciProvider=<circleci|github-actions|cloud-build|none>'
assert_has 'service|unpushed|uncommitted|ci|ciBranch|gitBranch|head|deploy|tag|age|ciRevision|ciExpectedRevision'
assert_has 'ciBranch != gitBranch'
assert_has 'ciRevision != ciExpectedRevision'
assert_has 'Classify available capabilities before rendering'
assert_has 'omit the `deployed` column'
assert_has 'omit rollout-derived observations'
assert_has 'do not infer a rollout state'
assert_has 'When both `toggles` and `parked` are empty'
assert_has 'skip toggle evaluation entirely'
assert_has 'use an empty dependency map'
assert_has 'mark dependency-order evidence unavailable'
assert_has '`READY` requires valid dependency-order evidence'
assert_has 'new tag <tag>, rollout still unsettled'
assert_has 'omit contract-coverage observations'
assert_has 'never ask a question'
assert_has 'never write state'

assert_not_has 'letterbox'
assert_not_has 'AskUserQuestion'
assert_not_has 'Write,'
assert_not_has 'Edit,'
assert_not_has 'Bash(make'
assert_not_has 'CircleCI key'
assert_not_has 'paperboy'
assert_not_has 'Flux'
assert_not_has 'make feature-toggles-disabled'

printf '%s\n' 'release-status portability contract tests passed'
