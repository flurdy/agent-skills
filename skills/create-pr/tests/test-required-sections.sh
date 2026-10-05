#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
FINDER="$TEST_DIR/../scripts/pr-required-sections.sh"
SKILL="$TEST_DIR/../SKILL.md"
RELATIVE_CONFIG=".agents/create-pr/required-sections.md"
SANDBOX=$(mktemp -d)
trap 'rm -rf "$SANDBOX"' EXIT

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_finds() {
    local expected=$1 cwd=$2 actual
    actual=$(cd "$cwd" && HOME="$SANDBOX/home" "$FINDER")
    [[ $actual == "$expected" ]] || fail "from $cwd expected '$expected', got '$actual'"
}

config() {
    mkdir -p "$1/.agents/create-pr"
    printf '## Related documents\n' >"$1/.agents/create-pr/required-sections.md"
    printf '%s\n' "$1/.agents/create-pr/required-sections.md"
}

home="$SANDBOX/home"
code="$home/Code/org"
mkdir -p "$code/workspace/repos" "$code/service/src" "$code/plain/src"
git -C "$code/service" init -q
git -C "$code/plain" init -q
ln -s ../../service "$code/workspace/repos/service"

assert_finds "" "$code/plain/src"

config "$home" >/dev/null
assert_finds "" "$code/plain/src"

workspace_config=$(config "$code/workspace")
assert_finds "$workspace_config" "$code/workspace/repos/service/src"
assert_finds "" "$code/service/src"

parent_config=$(config "$code")
assert_finds "$parent_config" "$code/service/src"

repository_config=$(config "$code/service")
assert_finds "$repository_config" "$code/service/src"
assert_finds "$code/workspace/repos/service/$RELATIVE_CONFIG" "$code/workspace/repos/service/src"

for invariant in \
    'pr-required-sections.sh' \
    '.agents/create-pr/required-sections.md' \
    'never leave a `<…>` placeholder'; do
    grep -Fq -- "$invariant" "$SKILL" || fail "expected '$invariant' in $SKILL"
done

printf '%s\n' 'create-pr required-sections tests passed'
