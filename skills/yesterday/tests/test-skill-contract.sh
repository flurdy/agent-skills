#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL="$TEST_DIR/../SKILL.md"
CANONICAL="$TEST_DIR/../../today/SKILL.md"
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

[[ -f "$SKILL" && -f "$CANONICAL" ]] || fail 'missing activity entry point'
assert_contains "$SKILL" 'name: yesterday'
assert_contains "$SKILL" 'Read,Skill(today)'
assert_contains "$SKILL" 'Bash(~/.agents/skills/wrap-up/scripts/activity.sh:*)'
assert_contains "$SKILL" 'mcp__jira__jira_get'
assert_contains "$SKILL" 'model-tier: standard'
assert_contains "$SKILL" 'model: sonnet'
assert_contains "$SKILL" 'effort: medium'
assert_contains "$SKILL" '--previous-workday {args}'
# shellcheck disable=SC2088  # Literal installed path in skill prose, not a shell expansion.
assert_contains "$SKILL" '~/.agents/skills/today/SKILL.md'
assert_contains "$SKILL" 'If the Skill tool is unavailable'
assert_contains "$SKILL" 'missing or unreadable, stop'
assert_contains "$SKILL" 'Perform no collection or rendering here'
assert_contains "$SKILL" 'Never fall back to same-day mode'
assert_contains "$CANONICAL" 'Friday when invoked on Monday'
assert_contains "$CANONICAL" 'activity.sh --workspace --previous-workday'
assert_contains "$CANONICAL" 'Previous-workday mode must omit current-session context'

# The alias retains delegate capabilities for read-and-follow clients, not a second workflow.
body=$(awk 'BEGIN { boundaries=0 } /^---$/ && boundaries<2 { boundaries++; next } boundaries==2' "$SKILL")
for forbidden in 'activity.sh' 'issuekey IN updatedBy' '/rest/api/3/' \
  'Each source is independent' '| Repo |' '| Event |' '| Key |' \
  '## Current-session context' '---BEADS-'; do
  if grep -Fq -- "$forbidden" <<< "$body"; then
    fail "alias duplicates canonical workflow: $forbidden"
  fi
done
for forbidden in 'Bash(bd update:*)' 'Write' 'AskUserQuestion' 'mcp__jira__jira_post'; do
  assert_not_contains "$SKILL" "$forbidden"
done
assert_contains "$CATALOG" '| today |'
assert_contains "$CATALOG" '| yesterday | Alias for `/today --previous-workday`'

printf 'yesterday alias contract tests passed\n'
