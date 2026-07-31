#!/usr/bin/env bash
# Usage: gh-pr-resolve-thread.sh <thread_id>
set -euo pipefail

if [[ $# -ne 1 ]]; then
    printf 'Usage: %s <thread_id>\n' "${0##*/}" >&2
    exit 2
fi

gh api graphql \
  -f query='mutation($threadId:ID!){
    resolveReviewThread(input:{threadId:$threadId}){ thread{ isResolved } }
  }' \
  -f threadId="$1"
