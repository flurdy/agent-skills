#!/usr/bin/env bash
set -euo pipefail

target_branch="${1:-}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf '%s\n' 'ERROR: not a Git working tree' >&2
    exit 1
fi

current_worktree=$(git rev-parse --show-toplevel)
current_worktree=$(CDPATH='' cd -- "$current_worktree" && pwd -P)
current_branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)
if [[ -z "$current_branch" ]]; then
    detached=true
else
    detached=false
fi

if ! status_output=$(git status --porcelain=v1 --untracked-files=all); then
    printf '%s\n' 'ERROR: unable to inspect working tree status' >&2
    exit 1
fi
tracked_changes=false
untracked_changes=false
while IFS= read -r status_line; do
    case "$status_line" in
        '') ;;
        '?? '*) untracked_changes=true ;;
        *) tracked_changes=true ;;
    esac
done <<<"$status_output"

local_branch_exists=false
remote_branch_exists=unknown
target_published=unknown
worktree_path=''
if [[ -n "$target_branch" ]]; then
    if git show-ref --verify --quiet "refs/heads/$target_branch"; then
        local_branch_exists=true
    fi

    if git remote get-url origin >/dev/null 2>&1; then
        set +e
        remote_output=$(GIT_TERMINAL_PROMPT=0 git ls-remote --exit-code --heads origin "refs/heads/$target_branch" 2>/dev/null)
        remote_status=$?
        set -e
        case "$remote_status" in
            0)
                remote_branch_exists=true
                head_sha=$(git rev-parse --verify HEAD)
                target_published=false
                if [[ "$remote_output" == "$head_sha"$'\t'"refs/heads/$target_branch" ]]; then
                    target_published=true
                fi
                ;;
            2) remote_branch_exists=false; target_published=false ;;
            *) remote_branch_exists=unknown ;;
        esac
    fi

    worktree_path=$(
        git worktree list --porcelain | awk -v target="refs/heads/$target_branch" '
            $1 == "worktree" { path = substr($0, 10) }
            $1 == "branch" && $2 == target { print path; exit }
        '
    )
fi

printf '%s\n' \
    '---GIT-BRANCH-PREFLIGHT---' \
    "current_worktree=$current_worktree" \
    "current_branch=$current_branch" \
    "detached=$detached" \
    "tracked_changes=$tracked_changes" \
    "untracked_changes=$untracked_changes" \
    "target_branch=$target_branch" \
    "local_branch_exists=$local_branch_exists" \
    "remote_branch_exists=$remote_branch_exists" \
    "target_published=$target_published" \
    "worktree_path=$worktree_path"
