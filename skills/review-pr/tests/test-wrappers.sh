#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SCRIPTS="$TEST_DIR/../scripts"
TEMP=$(mktemp -d)
trap 'rm -rf "$TEMP"' EXIT
LOG="$TEMP/commands.log"

cat >"$TEMP/gh" <<'GH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$COMMAND_LOG"
if [[ "$1 $2" == "repo view" ]]; then
  printf '%s\n' 'cwd/repository'
elif [[ "$1 $2" == "pr view" && "$*" == *"number"* ]]; then
  printf '%s\n' '42'
elif [[ "$1 $2" == "pr checks" ]]; then
  if [[ ${GH_CHECKS_EMPTY:-0} != 1 ]]; then
    printf 'build\tpass\n'
    printf 'lint\tfail\n'
  fi
  exit "${GH_CHECKS_EXIT:-0}"
else
  printf '%s\n' '[]'
fi
GH
chmod 0755 "$TEMP/gh"
export COMMAND_LOG="$LOG"
export PATH="$TEMP:$PATH"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_logged() {
  local expected=$1
  grep -Fq -- "$expected" "$LOG" || fail "expected '$expected' in command log"
}

"$SCRIPTS/gh-pr-view.sh" acme widgets 42 >/dev/null
"$SCRIPTS/gh-pr-diff.sh" acme widgets 42 >/dev/null
checks_output=$(GH_CHECKS_EXIT=1 "$SCRIPTS/gh-pr-checks.sh" acme widgets 42)
pending_output=$(GH_CHECKS_EXIT=8 "$SCRIPTS/gh-pr-checks.sh" acme widgets 42)
"$SCRIPTS/gh-pr-comments.sh" acme widgets 42 >/dev/null
for output in "$checks_output" "$pending_output"; do
  [[ $output == *"1 fail"* ]] || fail 'missing legacy failing-check count'
  [[ $output == *"1 pass"* ]] || fail 'missing legacy passing-check count'
done
if GH_CHECKS_EMPTY=1 "$SCRIPTS/gh-pr-checks.sh" acme widgets 42 >/dev/null 2>&1; then
  fail 'empty check output must fail'
fi

assert_logged 'pr view 42 --repo acme/widgets'
assert_logged 'pr diff 42 --repo acme/widgets'
assert_logged 'pr checks 42 --repo acme/widgets'
assert_logged 'api graphql'
assert_logged 'owner=acme'
assert_logged 'repo=widgets'
assert_logged 'api --paginate /repos/acme/widgets/pulls/42/comments'

: >"$LOG"
"$SCRIPTS/gh-pr-comments.sh" 42 >/dev/null
assert_logged 'repo view --json nameWithOwner'
assert_logged 'pr view 42 --repo cwd/repository'
assert_logged 'api --paginate /repos/cwd/repository/pulls/42/comments'

printf '%s\n' 'review-pr wrapper tests passed'
