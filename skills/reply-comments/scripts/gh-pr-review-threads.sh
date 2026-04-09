#!/usr/bin/env bash
# Usage: gh-pr-review-threads.sh <owner> <repo> <number>
# Returns thread IDs, resolution status, and first comment databaseId + body
gh api graphql \
  -f query='query($owner:String!,$repo:String!,$pr:Int!){
    repository(owner:$owner,name:$repo){
      pullRequest(number:$pr){
        reviewThreads(first:100){
          nodes{ id isResolved comments(first:1){ nodes{ databaseId body } } }
        }
      }
    }
  }' \
  -f owner="$1" -f repo="$2" -F pr="$3" \
  --jq '.data.repository.pullRequest.reviewThreads.nodes'
