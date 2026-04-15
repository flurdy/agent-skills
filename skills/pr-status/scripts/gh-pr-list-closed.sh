#!/usr/bin/env bash
# List recently closed/merged PRs by the current user across a GitHub org.
# Org resolution: $PR_STATUS_ORG > arg $1 > extracted from git remote origin
# Usage: gh-pr-list-closed.sh [org] [days]
set -euo pipefail

if [ -n "${PR_STATUS_ORG:-}" ]; then
  ORG="$PR_STATUS_ORG"
elif [ -n "${1:-}" ]; then
  ORG="$1"
else
  ORG=$(git remote get-url origin 2>/dev/null | sed -E 's#.*(github\.com[:/])##; s#/.*##')
fi

DAYS="${2:-7}"
SINCE=$(date -u -d "${DAYS} days ago" +%Y-%m-%d 2>/dev/null || date -u -v-${DAYS}d +%Y-%m-%d)

# Get closed PRs from search API
SEARCH=$(gh search prs --author @me --state closed --owner "$ORG" --limit 30 \
  --json repository,number,title,closedAt \
  | jq -c --arg since "$SINCE" '[.[] | select(.closedAt >= $since)]')

# If no results, exit
[ "$SEARCH" = "[]" ] && exit 0

# Check merged status per PR
echo "$SEARCH" | jq -r '.[] | "\(.repository.name)\t\(.number)"' | sort -t$'\t' -k1,1 | \
while IFS=$'\t' read -r REPO PR_NUM; do
  MERGED=$(gh api "repos/$ORG/$REPO/pulls/$PR_NUM" --jq '.merged' 2>/dev/null || echo "false")
  echo "$SEARCH" | jq -c --arg num "$PR_NUM" --arg merged "$MERGED" --arg org "$ORG" \
    '.[] | select(.number == ($num | tonumber)) | {number, title, owner: $org, repo: .repository.name, closedAt: .closedAt, merged: ($merged == "true")}'
done
