#!/usr/bin/env bash
# Read-only. Resolves the child-only commit range for a rebase and prints the
# exact `git rebase --onto` command, or refuses when the old base cannot be proven.
set -euo pipefail

usage() {
    cat >&2 <<'EOF'
Usage:
  rebase-range.sh main
  rebase-range.sh parent <parent-branch> [--old-tip <sha>]
  rebase-range.sh merged <old-parent-branch> [--old-tip <sha>]
EOF
    exit 2
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

mode="${1:-}"
[[ -n "$mode" ]] || usage
shift

branch_arg=''
old_tip_arg=''
case "$mode" in
    main) ;;
    parent|merged)
        branch_arg="${1:-}"
        [[ -n "$branch_arg" ]] || usage
        shift
        ;;
    *) usage ;;
esac
while (($# > 0)); do
    case "$1" in
        --old-tip)
            old_tip_arg="${2:-}"
            [[ -n "$old_tip_arg" ]] || usage
            shift 2
            ;;
        *) usage ;;
    esac
done

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die 'not a Git working tree'
current_branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)
[[ -n "$current_branch" ]] || die 'detached HEAD: check out the branch to rebase first'
head_sha=$(git rev-parse --verify HEAD)

case "$mode" in
    main|merged) target="origin/main" ;;
    parent) target="origin/$branch_arg" ;;
esac
target_sha=$(git rev-parse --verify --quiet "refs/remotes/$target^{commit}" 2>/dev/null || true)
[[ -n "$target_sha" ]] || die "$target is unknown: run 'git fetch origin ${target#origin/}' first"
[[ "$current_branch" != "${target#origin/}" ]] || die "already on ${target#origin/}; check out the branch to rebase"
if [[ -n "$branch_arg" && "$current_branch" == "$branch_arg" ]]; then
    die "current branch is $branch_arg itself; check out the child branch"
fi

is_ancestor_of_head() {
    git merge-base --is-ancestor "$1" HEAD 2>/dev/null
}

upstream=''
upstream_source=''
consider() {
    local source=$1 ref=$2 sha
    [[ -z "$upstream" ]] || return 0
    sha=$(git rev-parse --verify --quiet "$ref^{commit}" 2>/dev/null) || return 0
    is_ancestor_of_head "$sha" || return 0
    upstream=$sha
    upstream_source=$source
}

consider_reflog() {
    local ref=$1 sha
    [[ -z "$upstream" ]] || return 0
    while IFS= read -r sha; do
        [[ -n "$sha" ]] || continue
        if is_ancestor_of_head "$sha"; then
            upstream=$sha
            upstream_source=reflog
            return 0
        fi
    done < <(git reflog show --format=%H "$ref" 2>/dev/null || true)
}

if [[ -n "$old_tip_arg" ]]; then
    explicit_sha=$(git rev-parse --verify --quiet "$old_tip_arg^{commit}" 2>/dev/null || true)
    [[ -n "$explicit_sha" ]] || die "--old-tip $old_tip_arg is not a commit in this repository"
    is_ancestor_of_head "$explicit_sha" || die "--old-tip $old_tip_arg is not an ancestor of HEAD"
    upstream=$explicit_sha
    upstream_source=explicit
fi

case "$mode" in
    main)
        consider merge-base "$(git merge-base HEAD "$target_sha" 2>/dev/null || true)"
        ;;
    parent)
        consider local-branch "refs/heads/$branch_arg"
        consider_reflog "refs/remotes/origin/$branch_arg"
        consider merge-base "$(git merge-base HEAD "$target_sha" 2>/dev/null || true)"
        ;;
    merged)
        consider local-branch "refs/heads/$branch_arg"
        consider remote-branch "refs/remotes/origin/$branch_arg"
        consider_reflog "refs/remotes/origin/$branch_arg"
        ;;
esac

child_commits=''
already_applied=''
status=''
reason=''
command=''
behind=$(git rev-list --count "HEAD..$target_sha")

if git merge-base --is-ancestor "$target_sha" HEAD; then
    status=up-to-date
    reason="$current_branch already contains $target"
    if [[ -n "$upstream" ]]; then
        child_commits=$(git rev-list --count "$upstream..HEAD")
    fi
elif [[ -z "$upstream" ]]; then
    status=refuse
    reason="old tip of $branch_arg not found: not a local branch, not on origin, and not in the reflog. Pass --old-tip <sha> (the parent PR's headRefOid: gh pr view <pr> --json headRefOid); never use the merge commit or a merge-base guess"
else
    child_commits=$(git rev-list --count "$upstream..HEAD")
    already_applied=$(git cherry "$target_sha" HEAD "$upstream" | grep -c '^-' || true)
    if [[ "$upstream_source" == merge-base && "$mode" == parent && "$already_applied" -gt 0 ]]; then
        status=refuse
        reason="stale merge-base: $already_applied commit(s) in the range already exist on $target, so the parent was rewritten. Pass --old-tip <sha> with the parent tip the branch was created from"
    else
        status=ok
        command="git rebase --onto $target $upstream $current_branch"
    fi
fi

printf '%s\n' \
    '---REBASE-RANGE---' \
    "mode=$mode" \
    "current_branch=$current_branch" \
    "head=$head_sha" \
    "target=$target" \
    "target_sha=$target_sha" \
    "upstream=$upstream" \
    "upstream_source=$upstream_source" \
    "child_commits=$child_commits" \
    "already_applied=$already_applied" \
    "behind=$behind" \
    "status=$status" \
    "reason=$reason" \
    "command=$command"
