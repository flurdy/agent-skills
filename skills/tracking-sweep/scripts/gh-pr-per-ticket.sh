#!/usr/bin/env bash
# For each Jira ticket key, search all PRs filed against it across the org.
# No time-window — captures old PRs that the 28-day org-wide list misses.
#
# Usage: gh-pr-per-ticket.sh KEY1 KEY2 ...
#        echo -e "GE-649\nGE-1121" | gh-pr-per-ticket.sh
#
# Org resolution: $PR_STATUS_ORG > extracted from git remote origin
#
# Output: one JSON object per line: {"key":"GE-649","open":1,"merged":7,"prs":[...]}
set -euo pipefail

if [ -n "${PR_STATUS_ORG:-}" ]; then
  ORG="$PR_STATUS_ORG"
else
  ORG=$(git remote get-url origin 2>/dev/null | sed -E 's#.*(github\.com[:/])##; s#/.*##')
fi

# Read keys from args or stdin
if [ $# -gt 0 ]; then
  KEYS=("$@")
else
  mapfile -t KEYS
fi

for KEY in "${KEYS[@]}"; do
  RESULT=$(gh search prs --owner "$ORG" "$KEY" --limit 20 \
    --json number,title,state,closedAt,repository,url 2>/dev/null || echo "[]")

  OPEN=$(echo "$RESULT" | jq '[.[] | select(.state=="open")] | length')
  MERGED=$(echo "$RESULT" | jq '[.[] | select(.state=="merged")] | length')

  echo "$RESULT" | jq -c --arg key "$KEY" --argjson open "$OPEN" --argjson merged "$MERGED" \
    '{key: $key, open: $open, merged: $merged, prs: .}'
done
