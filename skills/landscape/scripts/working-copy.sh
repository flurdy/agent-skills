#!/usr/bin/env bash
# Emit working-copy state for the landscape skill.
# Sections are delimited by `---<NAME>---` markers for easy parsing.
set -uo pipefail

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

echo "---BRANCH---"
echo "$BRANCH"

echo "---STATUS---"
git status --porcelain 2>/dev/null

echo "---AHEAD-BEHIND---"
git rev-list --left-right --count '@{u}...HEAD' 2>/dev/null || echo "no-upstream"

echo "---LASTCOMMIT---"
git log -1 --format='%h %s (%ar)' 2>/dev/null

echo "---STASHES-ON-BRANCH---"
git stash list --format='%gs' 2>/dev/null | grep -c "on ${BRANCH}:" || echo 0
