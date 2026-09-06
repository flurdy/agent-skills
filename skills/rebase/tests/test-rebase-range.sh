#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL_DIR=$(dirname -- "$TEST_DIR")
RANGE="$SKILL_DIR/scripts/rebase-range.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
export GIT_AUTHOR_NAME=Test GIT_AUTHOR_EMAIL=test@example.com
export GIT_COMMITTER_NAME=Test GIT_COMMITTER_EMAIL=test@example.com

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_line() {
    local output=$1 expected=$2
    grep -Fxq -- "$expected" <<<"$output" || fail "expected '$expected' in output:"$'\n'"$output"
}

assert_line_contains() {
    local output=$1 expected=$2
    grep -Fq -- "$expected" <<<"$output" || fail "expected fragment '$expected' in output:"$'\n'"$output"
}

value_of() {
    local output=$1 key=$2
    sed -n "s/^$key=//p" <<<"$output"
}

commit_file() {
    local repo=$1 name=$2
    printf '%s\n' "$name" >"$repo/$name.txt"
    git -C "$repo" add "$name.txt"
    git -C "$repo" commit -qm "$name"
    git -C "$repo" rev-parse HEAD
}

# Every scenario starts from a bare remote with `main` at one commit, a `dev`
# clone that owns the child branch, and an `other` clone that plays the
# colleague who moves main or the parent.
scenario() {
    local name=$1
    S="$TMP/$name"
    REMOTE="$S/remote.git"
    DEV="$S/dev"
    OTHER="$S/other"
    mkdir -p "$S"
    git init -q --bare --initial-branch=main "$REMOTE"
    git init -q --initial-branch=main "$DEV"
    commit_file "$DEV" m1 >/dev/null
    git -C "$DEV" remote add origin "$REMOTE"
    git -C "$DEV" push -qu origin main
    git clone -q "$REMOTE" "$OTHER"
}

# Pushes a parent branch with p1 and a child branch with c1, c2 from `dev`.
stack_fixture() {
    git -C "$DEV" switch -qc feature/parent
    P1=$(commit_file "$DEV" p1)
    git -C "$DEV" push -qu origin feature/parent
    git -C "$DEV" switch -qc feature/child
    commit_file "$DEV" c1 >/dev/null
    commit_file "$DEV" c2 >/dev/null
    git -C "$DEV" push -qu origin feature/child
}

run_range() {
    (cd "$DEV" && "$RANGE" "$@")
}

# Runs the printed command in `dev` and proves the result is child-only.
apply_and_prove() {
    local output=$1 target=$2
    local command
    command=$(value_of "$output" command)
    [[ "$command" == "git rebase --onto $target "* ]] || fail "unexpected command '$command'"
    (cd "$DEV" && eval "$command" >/dev/null 2>&1) || fail "rebase command failed: $command"
    [[ "$(git -C "$DEV" rev-list --count "$target..HEAD")" == 2 ]] || fail "expected 2 child commits above $target"
    [[ "$(git -C "$DEV" log --format=%s "$target..HEAD" | tr '\n' ' ')" == 'c2 c1 ' ]] || fail 'child commits were not the only commits replayed'
    git -C "$DEV" merge-base --is-ancestor "$target" HEAD || fail "$target is not an ancestor after rebase"
    [[ -f "$DEV/c1.txt" && -f "$DEV/c2.txt" ]] || fail 'child files missing after rebase'
}

# --- main mode -------------------------------------------------------------
scenario main
git -C "$DEV" switch -qc feature/child
commit_file "$DEV" c1 >/dev/null
commit_file "$DEV" c2 >/dev/null
fresh=$(run_range main)
assert_line "$fresh" 'status=up-to-date'
assert_line "$fresh" 'behind=0'
assert_line "$fresh" 'command='

commit_file "$OTHER" m2 >/dev/null
git -C "$OTHER" push -q origin main
git -C "$DEV" fetch -q origin
head_before=$(git -C "$DEV" rev-parse HEAD)
main_out=$(run_range main)
assert_line "$main_out" 'mode=main'
assert_line "$main_out" 'upstream_source=merge-base'
assert_line "$main_out" 'child_commits=2'
assert_line "$main_out" 'already_applied=0'
assert_line "$main_out" 'behind=1'
assert_line "$main_out" 'status=ok'
[[ "$head_before" == "$(git -C "$DEV" rev-parse HEAD)" ]] || fail 'range helper moved HEAD'
apply_and_prove "$main_out" origin/main
[[ -f "$DEV/m2.txt" ]] || fail 'main commit missing after rebase'
assert_line "$(run_range main)" 'status=up-to-date'

# --- parent mode: parent fast-forwarded -------------------------------------
scenario parent-ff
stack_fixture
git -C "$OTHER" fetch -q origin
git -C "$OTHER" switch -qc feature/parent origin/feature/parent
commit_file "$OTHER" p2 >/dev/null
git -C "$OTHER" push -q origin feature/parent
git -C "$DEV" fetch -q origin

ff_local=$(run_range parent feature/parent)
assert_line "$ff_local" 'mode=parent'
assert_line "$ff_local" 'target=origin/feature/parent'
assert_line "$ff_local" "upstream=$P1"
assert_line "$ff_local" 'upstream_source=local-branch'
assert_line "$ff_local" 'child_commits=2'
assert_line "$ff_local" 'status=ok'

git -C "$DEV" branch -qD feature/parent
ff_reflog=$(run_range parent feature/parent)
assert_line "$ff_reflog" "upstream=$P1"
assert_line "$ff_reflog" 'upstream_source=reflog'
assert_line "$ff_reflog" 'status=ok'
apply_and_prove "$ff_reflog" origin/feature/parent
[[ -f "$DEV/p2.txt" ]] || fail 'updated parent commit missing after rebase'
assert_line "$(run_range parent feature/parent)" 'status=up-to-date'

# --- parent mode: parent rebased and force-pushed ---------------------------
scenario parent-rewritten
stack_fixture
commit_file "$OTHER" m2 >/dev/null
git -C "$OTHER" push -q origin main
git -C "$OTHER" fetch -q origin
git -C "$OTHER" switch -qc feature/parent origin/feature/parent
git -C "$OTHER" rebase -q origin/main
git -C "$OTHER" push -q --force-with-lease origin feature/parent
git -C "$DEV" fetch -q origin
git -C "$DEV" branch -qD feature/parent
[[ "$(git -C "$DEV" rev-parse origin/feature/parent)" != "$P1" ]] || fail 'fixture did not rewrite the parent'

rewritten=$(run_range parent feature/parent)
assert_line "$rewritten" "upstream=$P1"
assert_line "$rewritten" 'upstream_source=reflog'
assert_line "$rewritten" 'already_applied=0'
assert_line "$rewritten" 'status=ok'

# Without the reflog the merge-base guess would replay the old parent commit.
rm -f "$DEV/.git/logs/refs/remotes/origin/feature/parent"
stale=$(run_range parent feature/parent)
assert_line "$stale" 'upstream_source=merge-base'
assert_line "$stale" 'already_applied=1'
assert_line "$stale" 'status=refuse'
assert_line "$stale" 'command='
assert_line_contains "$stale" 'reason=stale merge-base'
assert_line_contains "$stale" '--old-tip'

explicit=$(run_range parent feature/parent --old-tip "$P1")
assert_line "$explicit" 'upstream_source=explicit'
assert_line "$explicit" 'status=ok'
apply_and_prove "$explicit" origin/feature/parent
[[ -z "$(git -C "$DEV" cherry origin/feature/parent HEAD | grep '^-' || true)" ]] || fail 'old parent commit was replayed onto the rewritten parent'

# --- merged mode: parent squash-merged, branch deleted ----------------------
scenario merged-squash
stack_fixture
git -C "$OTHER" fetch -q origin
git -C "$OTHER" merge -q --squash origin/feature/parent >/dev/null
git -C "$OTHER" commit -qm 'squash parent'
git -C "$OTHER" push -q origin main
git -C "$OTHER" push -q origin --delete feature/parent
git -C "$DEV" fetch -q origin

squash_local=$(run_range merged feature/parent)
assert_line "$squash_local" 'mode=merged'
assert_line "$squash_local" 'target=origin/main'
assert_line "$squash_local" "upstream=$P1"
assert_line "$squash_local" 'upstream_source=local-branch'
assert_line "$squash_local" 'child_commits=2'
assert_line "$squash_local" 'status=ok'

git -C "$DEV" branch -qD feature/parent
squash_remote=$(run_range merged feature/parent)
assert_line "$squash_remote" "upstream=$P1"
assert_line "$squash_remote" 'upstream_source=remote-branch'
assert_line "$squash_remote" 'status=ok'

git -C "$DEV" fetch -q --prune origin
rm -f "$DEV/.git/logs/refs/remotes/origin/feature/parent"
squash_gone=$(run_range merged feature/parent)
assert_line "$squash_gone" 'upstream='
assert_line "$squash_gone" 'upstream_source='
assert_line "$squash_gone" 'status=refuse'
assert_line "$squash_gone" 'command='
assert_line_contains "$squash_gone" 'headRefOid'
assert_line_contains "$squash_gone" '--old-tip'
grep -q 'upstream_source=merge-base' <<<"$squash_gone" && fail 'merged mode must never fall back to a merge-base guess'

if run_range merged feature/parent --old-tip "$(git -C "$DEV" rev-parse origin/main)" >/dev/null 2>"$TMP/merge-commit.err"; then
    fail 'the squash merge commit must be rejected as an old tip'
fi
grep -Fq 'not an ancestor of HEAD' "$TMP/merge-commit.err" || fail 'missing non-ancestor diagnostic'

squash_explicit=$(run_range merged feature/parent --old-tip "$P1")
assert_line "$squash_explicit" 'upstream_source=explicit'
assert_line "$squash_explicit" 'status=ok'
apply_and_prove "$squash_explicit" origin/main
[[ -f "$DEV/p1.txt" ]] || fail 'squashed parent content missing from main'
assert_line "$(run_range merged feature/parent)" 'status=up-to-date'

# --- merged mode: parent rewritten, then merged with a merge commit ---------
scenario merged-rewritten
stack_fixture
commit_file "$OTHER" m2 >/dev/null
git -C "$OTHER" push -q origin main
git -C "$OTHER" fetch -q origin
git -C "$OTHER" switch -qc feature/parent origin/feature/parent
git -C "$OTHER" rebase -q origin/main
git -C "$OTHER" push -q --force-with-lease origin feature/parent
git -C "$DEV" fetch -q origin
git -C "$OTHER" switch -q main
git -C "$OTHER" merge -q --no-ff feature/parent -m 'merge parent'
git -C "$OTHER" push -q origin main
git -C "$DEV" fetch -q origin
git -C "$DEV" branch -qD feature/parent

merged_reflog=$(run_range merged feature/parent)
assert_line "$merged_reflog" "upstream=$P1"
assert_line "$merged_reflog" 'upstream_source=reflog'
assert_line "$merged_reflog" 'status=ok'
apply_and_prove "$merged_reflog" origin/main

# --- errors ----------------------------------------------------------------
scenario errors
git -C "$DEV" switch -qc feature/child
commit_file "$DEV" c1 >/dev/null

if run_range bogus >/dev/null 2>&1; then fail 'unknown mode must fail'; fi
if run_range parent >/dev/null 2>&1; then fail 'parent mode without a branch must fail'; fi
if run_range parent feature/nope >"$TMP/no-target.out" 2>"$TMP/no-target.err"; then
    fail 'unknown target must fail'
fi
[[ ! -s "$TMP/no-target.out" ]] || fail 'unknown target emitted facts'
grep -Fq 'git fetch origin feature/nope' "$TMP/no-target.err" || fail 'missing fetch hint'
if run_range main --old-tip deadbeef >/dev/null 2>"$TMP/bad-tip.err"; then fail 'unknown --old-tip must fail'; fi
grep -Fq 'not a commit' "$TMP/bad-tip.err" || fail 'missing bad --old-tip diagnostic'

git -C "$DEV" switch -q main
if run_range main >/dev/null 2>"$TMP/on-main.err"; then fail 'running on main must fail'; fi
grep -Fq 'already on main' "$TMP/on-main.err" || fail 'missing on-main diagnostic'

git -C "$DEV" switch -q --detach
if run_range main >/dev/null 2>"$TMP/detached.err"; then fail 'detached HEAD must fail'; fi
grep -Fq 'detached HEAD' "$TMP/detached.err" || fail 'missing detached diagnostic'

if (cd "$TMP" && "$RANGE" main) >/dev/null 2>"$TMP/not-repo.err"; then fail 'must fail outside a repository'; fi
grep -Fq 'not a Git working tree' "$TMP/not-repo.err" || fail 'missing non-repository error'

if grep -Eq '\bgit (push|checkout|switch|reset|clean|stash|update-ref|branch -[dD])\b' "$RANGE"; then
    fail 'range helper contains a mutating Git command'
fi

printf '%s\n' 'rebase range tests passed'
