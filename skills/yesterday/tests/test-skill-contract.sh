#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL="$TEST_DIR/../SKILL.md"
CATALOG="$TEST_DIR/../../README.md"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_contains() {
  local file=$1
  local text=$2
  grep -Fq -- "$text" "$file" || fail "expected '$text' in $file"
}

assert_not_contains() {
  local file=$1
  local text=$2
  if grep -Fq -- "$text" "$file"; then
    fail "did not expect '$text' in $file"
  fi
}

[[ -f "$SKILL" ]] || fail 'missing yesterday skill'
assert_contains "$SKILL" 'name: yesterday'
assert_contains "$SKILL" 'Bash(~/.agents/skills/wrap-up/scripts/activity.sh:*)'
assert_contains "$SKILL" 'activity.sh --workspace --previous-workday'
assert_contains "$SKILL" 'mcp__jira__jira_get'
assert_contains "$SKILL" '/rest/api/3/myself'
assert_contains "$SKILL" 'issuekey IN updatedBy("{account-id}", "{selected-date}", "{selected-date}")'
assert_not_contains "$SKILL" 'updatedBy = currentUser()'
assert_contains "$SKILL" 'Friday when invoked on Monday'
assert_contains "$SKILL" 'Each source is independent'
assert_contains "$SKILL" 'Never create or update a handoff'
assert_contains "$SKILL" 'No objective activity found for this source'
assert_not_contains "$SKILL" '## Current-session context'
assert_not_contains "$SKILL" 'Bash(bd update:*)'
assert_not_contains "$SKILL" 'Write'
assert_not_contains "$SKILL" 'AskUserQuestion'
assert_not_contains "$SKILL" 'mcp__jira__jira_post'
assert_contains "$CATALOG" '| yesterday |'

printf 'yesterday skill contract tests passed\n'
