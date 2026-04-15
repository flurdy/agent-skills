#!/usr/bin/env bash
# List all open PRs by the current user across a GitHub org.
# Org resolution: $PR_STATUS_ORG > arg $1 > extracted from git remote origin
set -euo pipefail

if [ -n "${PR_STATUS_ORG:-}" ]; then
  ORG="$PR_STATUS_ORG"
elif [ -n "${1:-}" ]; then
  ORG="$1"
else
  ORG=$(git remote get-url origin 2>/dev/null | sed -E 's#.*(github\.com[:/])##; s#/.*##')
fi

gh search prs --author @me --state open --owner "$ORG" --limit 50 \
  --json repository,number,title \
  --jq '.[] | {number, title, owner: "'"$ORG"'", repo: .repository.name}'
