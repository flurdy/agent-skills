#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SCRIPT="$TEST_DIR/../scripts/handoff-path.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

run_path() {
  HOME="$TMP/home" bash "$SCRIPT" "$@"
}

assert_rejected() {
  local label=$1
  shift
  local output status=0
  output=$(run_path "$@" 2>&1) || status=$?
  [[ "$status" -eq 2 ]] || fail "$label: expected exit 2, got $status"
  case "$output" in
    /*) fail "$label: emitted a path instead of refusing: $output" ;;
  esac
}

mkdir -p "$TMP/home/.claude/handoffs"
HANDOFFS="$TMP/home/.claude/handoffs"

# Happy path and the -N collision family the /handoffs picker relies on.
[[ "$(run_path 2026-08-09 my-slug)" == "$HANDOFFS/2026-08-09-my-slug.md" ]] \
  || fail "valid arguments did not produce the expected path"

touch "$HANDOFFS/2026-08-09-my-slug.md"
[[ "$(run_path 2026-08-09 my-slug)" == "$HANDOFFS/2026-08-09-my-slug-2.md" ]] \
  || fail "first collision did not append -2"

touch "$HANDOFFS/2026-08-09-my-slug-2.md"
[[ "$(run_path 2026-08-09 my-slug)" == "$HANDOFFS/2026-08-09-my-slug-3.md" ]] \
  || fail "second collision did not append -3"

# The printed path is written to verbatim by the wrap-up skill, and both
# arguments are model-generated, so neither may escape the handoffs directory.
assert_rejected 'relative traversal'  2026-08-09 '../../../../tmp/pwn'
assert_rejected 'absolute slug'       2026-08-09 '/tmp/pwn'
assert_rejected 'single traversal'    2026-08-09 '../x'
assert_rejected 'bare dot-dot'        2026-08-09 '..'
assert_rejected 'shell metacharacter' 2026-08-09 'a;id|b'
assert_rejected 'command substitution' 2026-08-09 'a$(id)b'
assert_rejected 'newline in slug'     2026-08-09 'a
b'
assert_rejected 'uppercase slug'      2026-08-09 'MySlug'
assert_rejected 'leading hyphen'      2026-08-09 '-leading'
assert_rejected 'double hyphen'       2026-08-09 'a--b'
assert_rejected 'malformed date'      nope my-slug
assert_rejected 'traversal in date'   '../../etc' my-slug
assert_rejected 'empty slug'          2026-08-09 ''
assert_rejected 'missing arguments'

# A traversal attempt must not leave anything behind outside the handoffs dir.
run_path 2026-08-09 '../../../../tmp/pwn' >/dev/null 2>&1 || true
[[ ! -e "$TMP/tmp/pwn-2026-08-09.md" ]] || fail "traversal created a file outside the handoffs dir"

printf 'handoff-path tests passed\n'
