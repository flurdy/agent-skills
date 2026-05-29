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
