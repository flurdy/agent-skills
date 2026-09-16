#!/usr/bin/env bash
set -euo pipefail

ROOT=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P)
PROMPT="$ROOT/prompts/yesterday.md"
CANONICAL="$ROOT/skills/today/SKILL.md"

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

[[ -f "$PROMPT" ]] || fail 'missing yesterday prompt'
[[ ! -e "$ROOT/skills/yesterday" && ! -L "$ROOT/skills/yesterday" ]] || fail 'retired yesterday skill remains'
assert_contains "$PROMPT" 'description:'
assert_contains "$PROMPT" 'skill named `today`'
assert_contains "$PROMPT" '--previous-workday $ARGUMENTS'
# shellcheck disable=SC2088  # Literal installed path, not a shell expansion.
assert_contains "$PROMPT" '~/.agents/skills/today/SKILL.md'
assert_contains "$PROMPT" 'If the Skill tool is unavailable'
assert_contains "$PROMPT" 'unchanged for canonical validation'
assert_contains "$PROMPT" 'missing or unreadable, stop'
assert_contains "$PROMPT" 'Never fall back to same-day mode'
assert_contains "$PROMPT" 'Perform no collection, rendering, or date selection here'

# All arguments go to today's existing validator, not a second procedure or capability set.
for forbidden in 'activity.sh' 'issuekey IN updatedBy' '/rest/api/3/' \
  '| Repo |' '| Event |' '| Key |' '---BEADS-' 'Friday' \
  'allowed-tools:' 'model-tier:' 'model:' 'effort:'; do
  assert_not_contains "$PROMPT" "$forbidden"
done
assert_contains "$CANONICAL" 'Accept no arguments (same-day mode) or exactly `--previous-workday`'
assert_contains "$CANONICAL" 'Reject unknown arguments and repeated flags before collecting'
assert_contains "$CANONICAL" 'prompt'
assert_contains "$CANONICAL" 'Codex uses'
assert_contains "$CANONICAL" '`/today --previous-workday` because this repository does not install prompt templates there.'
assert_contains "$ROOT/prompts/README.md" '[`/yesterday`](yesterday.md)'
assert_contains "$ROOT/prompts/README.md" 'Codex uses `/today --previous-workday`'
assert_not_contains "$ROOT/skills/README.md" '| yesterday |'

printf 'yesterday prompt delegation contract tests passed\n'
