#!/usr/bin/env bash
# Emit today's activity for the wrap-up skill: commits across worktrees,
# PRs (created/merged/closed today), and beads closed today.
# Sections are delimited by `---<NAME>---` markers for easy parsing.
set -uo pipefail

TODAY=$(date -I)
SINCE="${TODAY}T00:00:00"

echo "---STATUS---"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "OK"
else
    echo "NO_GIT"
fi

echo "---DATE---"
echo "$TODAY"

echo "---AUTHOR---"
git config user.email 2>/dev/null

# --- Commits across all worktrees of this repo ---
echo "---COMMITS---"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    AUTHOR=$(git config user.email 2>/dev/null)
    if [ -n "$AUTHOR" ]; then
        git worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2}' | while IFS= read -r WT; do
            WT_BRANCH=$(git -C "$WT" rev-parse --abbrev-ref HEAD 2>/dev/null)
            WT_BASE=$(basename "$WT")
            git -C "$WT" log --since="$SINCE" --author="$AUTHOR" \
                --format="${WT_BASE}|${WT_BRANCH}|%h|%s|%ar" --no-merges 2>/dev/null
        done
    fi
fi

# --- PRs created / merged / closed today ---
echo "---GH-STATUS---"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    echo "OK"
else
    echo "UNAVAILABLE"
fi

echo "---PRS-CREATED---"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    OUT=$(gh search prs --author=@me --created="$TODAY" \
        --json number,title,url,repository,state,isDraft \
        --limit 30 2>/dev/null)
    echo "${OUT:-[]}"
fi

echo "---PRS-MERGED---"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    OUT=$(gh search prs --author=@me --merged="$TODAY" \
        --json number,title,url,repository \
        --limit 30 2>/dev/null)
    echo "${OUT:-[]}"
fi

echo "---PRS-CLOSED-UNMERGED---"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    # state=closed includes merged; caller dedupes against the merged list.
    OUT=$(gh search prs --author=@me --closed="$TODAY" --state=closed \
        --json number,title,url,repository \
        --limit 30 2>/dev/null)
    echo "${OUT:-[]}"
fi

# --- Beads closed today ---
echo "---BEADS-STATUS---"
if ! command -v bd >/dev/null 2>&1; then
    echo "NO_BD"
elif [ ! -d .beads ]; then
    echo "NO_BEADS_IN_REPO"
else
    echo "OK"
fi

echo "---BEADS-IN-PROGRESS---"
if command -v bd >/dev/null 2>&1 && [ -d .beads ]; then
    bd list --status=in_progress --limit=50 --no-pager 2>/dev/null
fi

# In-progress beads NOT touched today — the candidate set for §3a's stale check.
# A bead a parallel session is actively working got set in_progress today
# (updated_at = today) and so is excluded here, which kills the false positives
# where cross-session WIP read as "stale" just because *this* session left no
# commit/branch trace for it.
echo "---BEADS-STALE-CANDIDATES---"
if command -v bd >/dev/null 2>&1 && [ -d .beads ]; then
    bd list --status=in_progress --updated-before="$TODAY" --limit=50 --no-pager 2>/dev/null
fi

echo "---BEADS-CREATED-TODAY---"
if command -v bd >/dev/null 2>&1 && [ -d .beads ]; then
    # Default filter excludes closed — beads created and closed the same day
    # already appear in CLOSED, so this lists only ones left open.
    bd list --created-after="$TODAY" --limit=50 --no-pager 2>/dev/null
fi

echo "---BEADS-CLOSED---"
if command -v bd >/dev/null 2>&1 && [ -d .beads ]; then
    bd list --status=closed --closed-after="$TODAY" --limit=50 --no-pager 2>/dev/null
fi
