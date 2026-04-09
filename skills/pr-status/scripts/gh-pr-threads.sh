#!/usr/bin/env bash
# Usage: gh-pr-threads.sh <owner> <repo> <number>
gh api graphql \
  -f query='query($owner:String!,$repo:String!,$pr:Int!){ repository(owner:$owner,name:$repo){ pullRequest(number:$pr){ reviewThreads(first:100){ nodes{ isResolved } } } } }' \
  -f owner="$1" -f repo="$2" -F pr="$3" \
  --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false)] | length'
