#!/usr/bin/env bash
set -euo pipefail

ROOT=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P)
REBASE="$ROOT/skills/rebase/SKILL.md"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_contains() {
    local file=$1 expected=$2
    grep -Fq -- "$expected" "$file" || fail "expected '$expected' in $file"
}

assert_not_contains() {
    local file=$1 unexpected=$2
    if grep -Fq -- "$unexpected" "$file"; then
        fail "did not expect '$unexpected' in $file"
    fi
}

line_of() {
    local file=$1 text=$2
    grep -nF -- "$text" "$file" | head -1 | cut -d: -f1
}

assert_order() {
    local file=$1
    shift
    local previous=0 current text
    for text in "$@"; do
        current=$(line_of "$file" "$text")
        [[ -n "$current" ]] || fail "missing '$text' in $file"
        ((current > previous)) || fail "expected '$text' after prior invariant in $file"
        previous=$current
    done
}

# One workflow covers all three targets and drives the rebase from the helper.
for mode in 'rebase-range.sh main' 'rebase-range.sh parent {parent-branch}' 'rebase-range.sh merged {old-parent}'; do
    assert_contains "$REBASE" "$mode"
done
assert_contains "$REBASE" 'Bash(~/.agents/skills/rebase/scripts/rebase-range.sh:*)'
assert_contains "$REBASE" 'branch.$(git branch --show-current).gh-merge-base'
assert_contains "$REBASE" 'status=up-to-date'
assert_contains "$REBASE" 'status=refuse'
assert_contains "$REBASE" '--old-tip {sha}'
assert_contains "$REBASE" 'headRefOid'
assert_contains "$REBASE" 'never its merge commit'
assert_contains "$REBASE" 'git rebase --onto {target} {upstream} {current-branch}'
assert_not_contains "$REBASE" 'git rebase -i '
assert_not_contains "$REBASE" 'mergeCommit'
assert_not_contains "$REBASE" '$(git merge-base'

# The four gates stay explicit and in order.
assert_contains "$REBASE" 'Working tree gate'
assert_contains "$REBASE" 'Never rebase over uncommitted work'
assert_contains "$REBASE" 'Verify with tests'
assert_contains "$REBASE" 'Do not force-push a broken rebase'
assert_contains "$REBASE" 'Force-push (Recommended)'
assert_contains "$REBASE" 'git push --force-with-lease'
assert_contains "$REBASE" 'Never use bare'
assert_contains "$REBASE" 'PR retarget gate'
assert_contains "$REBASE" 'PR base: unchanged'
assert_contains "$REBASE" 'gh-pr-edit-base.sh {target-branch}'
assert_order "$REBASE" 'Working tree gate' 'Resolve the child-only range' '### 5. Rebase' 'Verify with tests' 'Force-push gate' 'PR retarget gate' '### 10. Report'

# Retained entry points delegate and never rebase on their own.
for alias in rebase-main:main rebase-parent:parent rebase-merged-parent:merged; do
    name=${alias%%:*}
    mode=${alias##*:}
    file="$ROOT/skills/$name/SKILL.md"
    assert_contains "$file" "Alias for \`/rebase $mode"
    assert_contains "$file" "the arguments \`$mode {args}\`"
    assert_contains "$file" 'agents/skills/rebase/SKILL.md'
    assert_not_contains "$file" 'git rebase'
    assert_not_contains "$file" 'git push'
    assert_not_contains "$file" 'Bash('
done

# Callers point at the consolidated entry point.
for file in stack-branch pr-status ready-to-merge landscape; do
    assert_not_contains "$ROOT/skills/$file/SKILL.md" '/rebase-main'
    assert_not_contains "$ROOT/skills/$file/SKILL.md" '/rebase-merged-parent'
    assert_not_contains "$ROOT/skills/$file/SKILL.md" '/rebase-parent'
done
assert_contains "$ROOT/skills/stack-branch/SKILL.md" '/rebase merged {parent-branch}'
assert_contains "$ROOT/skills/README.md" '| rebase |'

printf '%s\n' 'rebase skill contract tests passed'
