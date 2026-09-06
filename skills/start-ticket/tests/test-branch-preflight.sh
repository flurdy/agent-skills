#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL_DIR=$(dirname -- "$TEST_DIR")
PREFLIGHT="$SKILL_DIR/scripts/git-branch-preflight.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_line() {
    local output=$1 expected=$2
    grep -Fxq -- "$expected" <<<"$output" || fail "expected '$expected' in output"
}

setup_repo() {
    local repo=$1 remote=$2
    git init -q --bare "$remote"
    git init -q --initial-branch=main "$repo"
    git -C "$repo" config user.email test@example.com
    git -C "$repo" config user.name Test
    printf '%s\n' initial >"$repo/tracked.txt"
    git -C "$repo" add tracked.txt
    git -C "$repo" commit -qm initial
    git -C "$repo" remote add origin "$remote"
    git -C "$repo" push -qu origin main
}

REPO="$TMP/repo"
REMOTE="$TMP/remote.git"
setup_repo "$REPO" "$REMOTE"

# A parent upstream is not publication of the new destination branch.
git -C "$REPO" config branch.autoSetupMerge true
git -C "$REPO" switch -qc feature/implicit origin/main
[[ "$(git -C "$REPO" rev-parse --abbrev-ref '@{upstream}')" == origin/main ]] || fail 'fixture did not reproduce implicit parent tracking'
implicit=$(cd "$REPO" && "$PREFLIGHT" feature/implicit)
assert_line "$implicit" 'remote_branch_exists=false'
assert_line "$implicit" 'target_published=false'
git -C "$REPO" switch -q main

git -C "$REPO" switch -q --no-track -c feature/publish origin/main
if git -C "$REPO" rev-parse --verify '@{upstream}' >/dev/null 2>&1; then
    fail 'new branch must not track the parent'
fi
unpublished=$(cd "$REPO" && "$PREFLIGHT" feature/publish)
assert_line "$unpublished" 'target_published=false'
git -C "$REPO" push -qu origin feature/publish
published=$(cd "$REPO" && "$PREFLIGHT" feature/publish)
assert_line "$published" 'target_published=true'
git -C "$REPO" commit --allow-empty -qm 'unpublished change'
ahead=$(cd "$REPO" && "$PREFLIGHT" feature/publish)
assert_line "$ahead" 'target_published=false'
git -C "$REPO" switch -q main

clean=$(cd "$REPO" && "$PREFLIGHT" feature/new)
assert_line "$clean" 'current_branch=main'
assert_line "$clean" 'detached=false'
assert_line "$clean" 'tracked_changes=false'
assert_line "$clean" 'untracked_changes=false'
assert_line "$clean" 'local_branch_exists=false'
assert_line "$clean" 'remote_branch_exists=false'

printf '%s\n' changed >>"$REPO/tracked.txt"
tracked=$(cd "$REPO" && "$PREFLIGHT" feature/new)
assert_line "$tracked" 'tracked_changes=true'
git -C "$REPO" restore tracked.txt

printf '%s\n' staged >>"$REPO/tracked.txt"
git -C "$REPO" add tracked.txt
staged=$(cd "$REPO" && "$PREFLIGHT" feature/new)
assert_line "$staged" 'tracked_changes=true'
git -C "$REPO" restore --staged tracked.txt
git -C "$REPO" restore tracked.txt

printf '%s\n' untracked >"$REPO/untracked.txt"
untracked=$(cd "$REPO" && "$PREFLIGHT" feature/new)
assert_line "$untracked" 'tracked_changes=false'
assert_line "$untracked" 'untracked_changes=true'
rm -f "$REPO/untracked.txt"

current_target=$(cd "$REPO" && "$PREFLIGHT" main)
assert_line "$current_target" "worktree_path=$REPO"
assert_line "$current_target" "current_worktree=$REPO"
mkdir -p "$REPO/subdir"
subdir=$(cd "$REPO/subdir" && "$PREFLIGHT" main)
assert_line "$subdir" "current_worktree=$REPO"
assert_line "$subdir" "worktree_path=$REPO"
ln -s "$REPO" "$TMP/repo-link"
linked=$(cd "$TMP/repo-link/subdir" && "$PREFLIGHT" main)
assert_line "$linked" "current_worktree=$REPO"
assert_line "$linked" "worktree_path=$REPO"

git -C "$REPO" branch feature/local
local_branch=$(cd "$REPO" && "$PREFLIGHT" feature/local)
assert_line "$local_branch" 'local_branch_exists=true'

git -C "$REPO" branch feature/remote
git -C "$REPO" push -qu origin feature/remote
git -C "$REPO" branch -D feature/remote >/dev/null
remote_branch=$(cd "$REPO" && "$PREFLIGHT" feature/remote)
assert_line "$remote_branch" 'local_branch_exists=false'
assert_line "$remote_branch" 'remote_branch_exists=true'

git -C "$REPO" branch feature/worktree
git -C "$REPO" worktree add -q "$TMP/worktree" feature/worktree
worktree=$(cd "$REPO" && "$PREFLIGHT" feature/worktree)
assert_line "$worktree" "worktree_path=$TMP/worktree"

git -C "$REPO" switch -q --detach
printf '%s\n' 'detached task change' >>"$REPO/tracked.txt"
git -C "$REPO" add tracked.txt
git -C "$REPO" commit -qm 'verified detached task'
head_before=$(git -C "$REPO" rev-parse HEAD)
status_before=$(git -C "$REPO" status --porcelain=v1 --untracked-files=all)
detached=$(cd "$REPO" && "$PREFLIGHT" feature/new)
assert_line "$detached" 'detached=true'
assert_line "$detached" 'current_branch='
[[ "$head_before" == "$(git -C "$REPO" rev-parse HEAD)" ]] || fail 'preflight changed HEAD'
[[ "$status_before" == "$(git -C "$REPO" status --porcelain=v1 --untracked-files=all)" ]] || fail 'preflight changed working tree'

# Preserving the detached commit leaves no new changes to commit on a rerun.
git -C "$REPO" switch -qc feature/recovered
recovered=$(cd "$REPO" && "$PREFLIGHT" feature/recovered)
assert_line "$recovered" 'detached=false'
assert_line "$recovered" 'tracked_changes=false'
assert_line "$recovered" 'untracked_changes=false'
[[ "$head_before" == "$(git -C "$REPO" rev-parse HEAD)" ]] || fail 'recovery must retain the verified commit without another commit'

NO_REMOTE="$TMP/no-remote"
git init -q --initial-branch=main "$NO_REMOTE"
no_remote=$(cd "$NO_REMOTE" && "$PREFLIGHT" feature/new)
assert_line "$no_remote" 'remote_branch_exists=unknown'
assert_line "$no_remote" 'target_published=unknown'
if git -C "$NO_REMOTE" rev-parse --verify HEAD >/dev/null 2>&1; then
    fail 'initial-task fixture must have unborn HEAD'
fi
printf '%s\n' 'initial task' >"$NO_REMOTE/initial.txt"
git -C "$NO_REMOTE" add initial.txt
unborn=$(cd "$NO_REMOTE" && "$PREFLIGHT" feature/initial)
assert_line "$unborn" 'tracked_changes=true'
assert_line "$unborn" 'detached=false'
git -C "$NO_REMOTE" -c user.name=Test -c user.email=test@example.com commit -qm 'initial task'
git -C "$NO_REMOTE" rev-parse --verify HEAD >/dev/null || fail 'initial task could not be committed'

if (cd "$TMP" && "$PREFLIGHT" feature/new) >"$TMP/not-repo.out" 2>&1; then
    fail 'preflight should fail outside a Git repository'
fi
grep -Fq 'not a Git working tree' "$TMP/not-repo.out" || fail 'missing non-repository error'

# Repository discovery succeeds, but status fails: never report a clean tree.
REAL_GIT=$(command -v git)
export REAL_GIT
mkdir -p "$TMP/bin"
cat >"$TMP/bin/git" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == status ]]; then
    printf '%s\n' 'fixture: status unavailable' >&2
    exit 128
fi
exec "$REAL_GIT" "$@"
EOF
chmod +x "$TMP/bin/git"
if (cd "$REPO" && PATH="$TMP/bin:$PATH" "$PREFLIGHT" feature/new) >"$TMP/status-error.out" 2>"$TMP/status-error.err"; then
    fail 'status error must fail preflight, not report clean'
fi
[[ ! -s "$TMP/status-error.out" ]] || fail 'status error emitted misleading preflight facts'
grep -Fq 'unable to inspect working tree status' "$TMP/status-error.err" || fail 'missing status failure diagnostic'

if grep -Eq '\bgit (push|checkout|switch|reset|clean|stash)\b' "$PREFLIGHT"; then
    fail 'preflight helper contains a mutating Git command'
fi

printf '%s\n' 'branch preflight tests passed'
