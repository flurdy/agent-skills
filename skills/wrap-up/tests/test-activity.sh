#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SCRIPT="$TEST_DIR/../scripts/activity.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_contains() {
  local text=$1
  grep -Fq -- "$text" "$TMP/output" || fail "expected '$text' in output"
}

make_repo() {
  local dir=$1
  local message=$2
  git init -q "$dir"
  git -C "$dir" config user.name Tester
  git -C "$dir" config user.email tester@example.com
  printf '%s\n' "$message" >"$dir/file.txt"
  git -C "$dir" add file.txt
  git -C "$dir" commit -qm "$message"
}

mkdir -p "$TMP/bin" "$TMP/workspace/repos"
make_repo "$TMP/workspace" "workspace commit"
make_repo "$TMP/workspace/repos/service" "service commit"
make_repo "$TMP/workspace/repos/no-author" "unattributed commit"
git -C "$TMP/workspace/repos/no-author" config user.email ''
mkdir -p "$TMP/workspace/.beads" "$TMP/workspace/repos/service/.beads" \
  "$TMP/workspace/repos/no-author/.beads"
printf 'services=repos/service,repos/no-author,repos/missing\n' >"$TMP/workspace/.mgit.conf"

cat >"$TMP/bin/gh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "auth" ]]; then
  exit 0
fi
printf 'search\n' >>"$GH_CALLS"
if [[ "${GH_FAIL:-}" == "1" && " $* " == *" --merged-at="* ]]; then
  exit 7
fi
printf '[]\n'
EOF
chmod +x "$TMP/bin/gh"

cat >"$TMP/bin/bd" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
dir=""
if [[ "${1:-}" == "-C" ]]; then
  dir=$2
  shift 2
fi
readonly=0
for arg in "$@"; do
  [[ "$arg" == "--readonly" ]] && readonly=1
done
[[ $readonly -eq 1 ]] || { printf 'missing --readonly\n' >&2; exit 9; }
id=$(basename "$dir")
if [[ "$id" == "no-author" ]]; then
  printf 'not-json\n'
else
  printf '[{"id":"%s-today","title":"Activity in %s"}]\n' "$id" "$id"
fi
EOF
chmod +x "$TMP/bin/bd"

export GH_CALLS="$TMP/gh-calls"
(
  cd "$TMP/workspace/repos/service"
  PATH="$TMP/bin:$PATH" MGIT_ROOT="$TMP/workspace" "$SCRIPT" --workspace >"$TMP/output"
)

assert_contains '---SCOPE---'
assert_contains 'WORKSPACE'
assert_contains '---REPOSITORIES---'
assert_contains "workspace|$TMP/workspace"
assert_contains "repos/service|$TMP/workspace/repos/service"
assert_contains "repos/no-author|$TMP/workspace/repos/no-author"
assert_contains 'Unavailable configured workspace member: repos/missing'
assert_contains 'repos/no-author|NO_AUTHOR'
assert_contains 'workspace|workspace|'
assert_contains 'repos/service|service|'
assert_contains 'workspace|[{"id":"workspace-today"'
assert_contains 'repos/service|[{"id":"service-today"'
assert_contains 'repos/no-author|ERROR'
[[ $(wc -l <"$GH_CALLS") -eq 3 ]] || fail "expected one global three-query GitHub collection"

(
  cd "$TMP/workspace/repos/service"
  PATH="$TMP/bin:$PATH" MGIT_ROOT="$TMP/workspace" GH_FAIL=1 \
    "$SCRIPT" --workspace >"$TMP/output"
)
assert_contains 'ERROR'
assert_contains 'Merged-PR query failed.'

make_repo "$TMP/solo" "solo commit"
(
  cd "$TMP/solo"
  PATH="$TMP/bin:$PATH" MGIT_ROOT='' "$SCRIPT" --workspace >"$TMP/output"
)
assert_contains 'CURRENT_REPO'
assert_contains "solo|$TMP/solo"
assert_contains 'solo|solo|'

(
  cd "$TMP/solo"
  PATH="$TMP/bin:$PATH" "$SCRIPT" >"$TMP/output"
)
if grep -Fq -- '---SCOPE---' "$TMP/output"; then
  fail 'default activity schema must not gain workspace-only sections'
fi
assert_contains '---BEADS-STALE-CANDIDATES---'

mkdir "$TMP/no-git"
(
  cd "$TMP/no-git"
  PATH="$TMP/bin:$PATH" MGIT_ROOT='' "$SCRIPT" --workspace >"$TMP/output"
)
assert_contains 'NO_GIT'
assert_contains 'CURRENT_REPO'
assert_contains '---PRS-CREATED---'

printf 'wrap-up activity tests passed\n'
