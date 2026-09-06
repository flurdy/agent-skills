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
  grep -Fq -- "$2" "$1" || fail "expected '$2' in $1"
}

assert_not_contains() {
  if grep -Fq -- "$2" "$1"; then
    fail "did not expect '$2' in $1"
  fi
}

assert_once() {
  [[ $(grep -Fc -- "$2" "$1") -eq 1 ]] || fail "expected exactly one '$2' in $1"
}

[[ -f "$SKILL" ]] || fail 'missing today skill'
assert_contains "$SKILL" 'name: today'
assert_contains "$SKILL" 'activity.sh --workspace --previous-workday'
assert_contains "$SKILL" 'Reject unknown arguments and repeated flags before collecting'
assert_contains "$SKILL" 'Bash(~/.agents/skills/wrap-up/scripts/activity.sh:*)'
assert_contains "$SKILL" 'model-tier: standard'
assert_contains "$SKILL" 'mcp__jira__jira_get'
assert_once "$SKILL" '/rest/api/3/myself'
assert_once "$SKILL" 'issuekey IN updatedBy("{account-id}", "{DATE}", "{DATE}")'
assert_not_contains "$SKILL" 'updatedBy = currentUser()'
assert_contains "$SKILL" 'Do not add an `updated` field bound'
assert_contains "$SKILL" 'Friday when invoked on Monday'
assert_contains "$SKILL" 'Use its `---DATE---` value; never recalculate the date'
assert_contains "$SKILL" '# Today — {DATE}'
assert_contains "$SKILL" '# Yesterday — {DATE}'
assert_contains "$SKILL" '## Objective activity today'
assert_contains "$SKILL" '| Same-day | In progress, Created today, Closed today | `BEADS-CREATED-TODAY`'
assert_contains "$SKILL" '| Previous-workday | Created, Closed | `BEADS-CREATED`'
assert_contains "$SKILL" 'Ignore `BEADS-IN-PROGRESS` in previous-workday mode'
assert_contains "$SKILL" 'Previous-workday mode must omit current-session context'
assert_contains "$SKILL" '## Current-session context'
assert_contains "$SKILL" 'From this conversation only'
assert_contains "$SKILL" 'Same-day: omit empty PR, Jira, and Beads subsections'
assert_contains "$SKILL" 'Previous-workday: retain each available source subsection'
assert_contains "$SKILL" 'No objective activity found for this source'
assert_contains "$SKILL" 'Each source is independent'
assert_contains "$SKILL" 'Never create or update a handoff'
assert_contains "$SKILL" '**Next:** Nothing required.'
for header in \
  '| Repo | Branch | SHA | Subject | When |' \
  '| Event | PR | Repo | Title |' \
  '| Key | Type | Status | Summary |' \
  '| Repo | ID | Type | Pri | Title |'; do
  assert_once "$SKILL" "$header"
done
for forbidden in 'Bash(bd update:*)' 'Write' 'AskUserQuestion' 'mcp__jira__jira_post'; do
  assert_not_contains "$SKILL" "$forbidden"
done
assert_contains "$CATALOG" '| today |'

printf 'today canonical activity contract tests passed\n'
