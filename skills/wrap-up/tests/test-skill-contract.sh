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

[[ -f "$SKILL" ]] || fail "missing wrap-up skill"

assert_contains "$SKILL" 'version: "0.12.0"'
assert_contains "$SKILL" 'Follow `/name-session`'"'"'s client-selection convention.'
assert_contains "$SKILL" 'Harness selection comes from the current tool surface.'
assert_contains "$SKILL" 'Never use the shell, PATH, filesystem, process list, or installed binaries to detect another client.'
assert_contains "$SKILL" 'Treat the client as unknown when that surface does not conclusively identify Pi or Claude Code.'
assert_contains "$SKILL" '**Pi:** use `/quit`.'
assert_contains "$SKILL" 'Never recommend `/exit` in Pi.'
assert_contains "$SKILL" '**Claude Code:** use `/exit`.'
assert_contains "$SKILL" '**Unknown client:** label both commands — Pi: `/quit`; Claude Code: `/exit` — rather than guessing.'
assert_contains "$SKILL" '⚠️ Uncommitted work — commit, stash, or discard before leaving this client. The resume block does not preserve file diffs.'
assert_contains "$SKILL" '⚠️ {N} unpushed commit(s) — push before leaving this client if the branch survives in a remote PR, or accept that this branch lives only locally.'
assert_contains "$SKILL" '**Pi footer:**'
assert_contains "$SKILL" '**Next:** run `/quit` to close this session.'
assert_contains "$SKILL" '**Claude Code footer:**'
assert_contains "$SKILL" '**Next:** run `/exit` to close this session.'
assert_contains "$SKILL" '**Unknown-client footer:**'
assert_contains "$SKILL" '**Next:** close this session manually — Pi: `/quit`; Claude Code: `/exit`.'
assert_not_contains "$SKILL" 'Run before `/exit`.'
assert_not_contains "$SKILL" 'Before running `/exit`'
assert_contains "$CATALOG" '| wrap-up |'

printf 'wrap-up client command contract tests passed\n'
