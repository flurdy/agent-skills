#!/usr/bin/env bash
# Usage: gh-pr-details.sh <owner> <repo> <number> [<number>...]
# Fetches all PR status data in a single GraphQL call.
# Outputs a JSON array, one object per PR.
set -euo pipefail

OWNER="$1"
REPO="$2"
shift 2

ALIASES=""
for PR in "$@"; do
  ALIASES="${ALIASES}
    pr${PR}: pullRequest(number: ${PR}) {
      number
      baseRefName
      mergeStateStatus
      reviews(first: 50, states: [APPROVED]) {
        nodes { author { login } }
      }
      reviewThreads(first: 100) {
        nodes { isResolved }
      }
      commits(last: 1) {
        nodes { commit { statusCheckRollup { state } } }
      }
    }"
done

QUERY="query(\$owner: String!, \$repo: String!) {
  repository(owner: \$owner, name: \$repo) {
    ${ALIASES}
  }
}"

gh api graphql \
  -f query="$QUERY" \
  -f owner="$OWNER" \
  -f repo="$REPO" \
  --jq '[.data.repository | to_entries[] | .value | {
    number: .number,
    base: .baseRefName,
    mergeState: .mergeStateStatus,
    approvers: ([.reviews.nodes[].author.login] | unique),
    unresolvedThreads: ([.reviewThreads.nodes[] | select(.isResolved == false)] | length),
    checksState: .commits.nodes[0].commit.statusCheckRollup.state
  }]'
