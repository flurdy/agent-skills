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

echo "---OTHER-WORKTREES-UNSAFE---"
# Emit only other worktrees (not the current one) that have uncommitted changes
# or unpushed commits. Format: path|branch|dirty_count|ahead_count
CURRENT_WT=$(git rev-parse --show-toplevel 2>/dev/null)
git worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2}' | while IFS= read -r WT; do
    [ "$WT" = "$CURRENT_WT" ] && continue
    DIRTY=$(git -C "$WT" status --porcelain 2>/dev/null | wc -l)
    AHEAD=$(git -C "$WT" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)
    WT_BRANCH=$(git -C "$WT" rev-parse --abbrev-ref HEAD 2>/dev/null)
    if [ "$DIRTY" -gt 0 ] || [ "$AHEAD" -gt 0 ]; then
        echo "$WT|$WT_BRANCH|$DIRTY|$AHEAD"
    fi
done
