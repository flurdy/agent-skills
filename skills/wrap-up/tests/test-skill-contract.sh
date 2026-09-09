#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL="$TEST_DIR/../SKILL.md"
CATALOG="$TEST_DIR/../../README.md"
NAMING="$TEST_DIR/../../name-session/SKILL.md"

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

[[ -f "$SKILL" ]] || fail "missing wrap-up skill"

assert_contains "$SKILL" 'Follow `/name-session`'"'"'s client-selection convention.'
assert_contains "$NAMING" 'Harness selection comes from the current tool surface.'
assert_contains "$NAMING" 'Never use the shell, PATH, filesystem, process list, or installed binaries to detect another client.'
assert_contains "$NAMING" 'Treat the client as unknown when that surface does not conclusively identify Pi or Claude Code.'
assert_contains "$SKILL" '**Pi:** use `/quit`.'
assert_contains "$SKILL" 'Never recommend `/exit` in Pi.'
assert_contains "$SKILL" '**Claude Code:** use `/exit`.'
assert_contains "$SKILL" '**Unknown client:** label both commands — Pi: `/quit`; Claude Code: `/exit` — rather than guessing.'
assert_contains "$SKILL" '⚠️ Uncommitted work — the resume block does not preserve file diffs. Review in a separate preservation task before removing this checkout.'
assert_contains "$SKILL" '⚠️ {N} unpushed commit(s) remain local. A handoff does not publish them or authorize a push.'
assert_contains "$SKILL" '**Pi footer:**'
assert_contains "$SKILL" '**Next:** run `/quit` to close this session.'
assert_contains "$SKILL" '**Claude Code footer:**'
assert_contains "$SKILL" '**Next:** run `/exit` to close this session.'
assert_contains "$SKILL" '**Unknown-client footer:**'
assert_contains "$SKILL" '**Next:** close this session manually — Pi: `/quit`; Claude Code: `/exit`.'
assert_not_contains "$SKILL" 'Run before `/exit`.'
assert_not_contains "$SKILL" 'Before running `/exit`'
assert_contains "$CATALOG" '| wrap-up |'
assert_contains "$SKILL" 'Bash(~/.agents/skills/artifact-hygiene/scripts/artifact_hygiene.py:*)'
assert_contains "$SKILL" '### 3d. 🔐 Artifact hygiene'
assert_contains "$SKILL" 'artifact-hygiene/scripts/artifact_hygiene.py --pretty'
assert_contains "$SKILL" '../artifact-hygiene/SKILL.md#report'
assert_contains "$SKILL" 'coverage before findings'
assert_contains "$SKILL" 'partial is never clean'
assert_contains "$SKILL" 'Exit `0` alone is not clearance'
assert_contains "$SKILL" 'Never recover raw evidence'
assert_contains "$SKILL" 'Remediation is a separate explicitly approved task'
assert_contains "$SKILL" '**Working-copy risks:**'
assert_contains "$SKILL" 'Artifact hygiene ({audited-cwd}): {status}/{verdict}'
assert_contains "$SKILL" 'Audit failure never blocks saving the handoff'
assert_contains "$SKILL" 'Other repositories in §3b remain unaudited'

printf 'wrap-up client command contract tests passed\n'
