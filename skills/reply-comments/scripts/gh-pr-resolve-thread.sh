#!/usr/bin/env bash
# Usage: gh-pr-resolve-thread.sh <thread_id>
gh api graphql \
  -f query='mutation($threadId:ID!){
    resolveReviewThread(input:{threadId:$threadId}){ thread{ isResolved } }
  }' \
  -f threadId="$1"
