#!/usr/bin/env bash
# Emit header info for the wrap-up skill: date, cwd, branch, worktree detection,
# and the canonical repo root (parent of realpath of --git-common-dir).
# Sections are delimited by `---<NAME>---` markers for easy parsing.
set -uo pipefail

echo "---DATE---"
date '+%A %Y-%m-%d %H:%M'

echo "---CWD---"
pwd

echo "---BRANCH---"
git rev-parse --abbrev-ref HEAD 2>/dev/null

echo "---GIT-COMMON-DIR---"
git rev-parse --git-common-dir 2>/dev/null

echo "---GIT-DIR---"
git rev-parse --git-dir 2>/dev/null

echo "---REPO-ROOT---"
git rev-parse --git-common-dir 2>/dev/null | xargs -I {} realpath {} 2>/dev/null | xargs -r dirname

# Short name of the repo's default branch (main/master). Lets §4 detect when the
# cwd is parked on the trunk — a branch that almost never holds the session's
# work, so recording it would send /handoffs hunting for a PR that isn't there.
echo "---DEFAULT-BRANCH---"
def_ref=$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null)
if [ -n "$def_ref" ]; then
    echo "${def_ref##*/}"
else
    for cand in main master; do
        if git rev-parse --verify --quiet "$cand" >/dev/null 2>&1 \
            || git rev-parse --verify --quiet "origin/$cand" >/dev/null 2>&1; then
            echo "$cand"; break
        fi
    done
fi

# Every worktree of this repo as `{path}|{branch}` (branch `(detached)` if so).
# §4 maps a feature branch found in today's activity back to the worktree that
# holds it, so the resume block can point at where the work actually lives.
echo "---WORKTREES---"
git worktree list --porcelain 2>/dev/null | awk '
    /^worktree /{ path=$2 }
    /^branch /{ b=$2; sub(/^refs\/heads\//,"",b); print path "|" b }
    /^detached$/{ print path "|(detached)" }
'
