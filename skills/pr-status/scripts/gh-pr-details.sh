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
      headRefName
      baseRefName
      mergeStateStatus
      reviewDecision
      reviews(first: 50, states: [APPROVED]) {
        nodes { author { login } }
      }
      reviewThreads(first: 100) {
        nodes { isResolved }
      }
      createdAt
      commits(last: 1) {
        nodes { commit { committedDate, statusCheckRollup { state } } }
      }
      mergeCommit {
        oid
        committedDate
        statusCheckRollup { state }
      }
      timelineItems(itemTypes: [READY_FOR_REVIEW_EVENT], last: 1) {
        nodes {
          ... on ReadyForReviewEvent { createdAt }
        }
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
    branch: .headRefName,
    base: .baseRefName,
    mergeState: .mergeStateStatus,
    reviewDecision: .reviewDecision,
    approvers: ([.reviews.nodes[].author.login] | unique),
    unresolvedThreads: ([.reviewThreads.nodes[] | select(.isResolved == false)] | length),
    checksState: .commits.nodes[0].commit.statusCheckRollup.state,
    lastPush: .commits.nodes[0].commit.committedDate,
    mergeCommitSha: .mergeCommit.oid,
    mergeCommitAt: .mergeCommit.committedDate,
    mainChecksState: .mergeCommit.statusCheckRollup.state,
    readyAt: (.timelineItems.nodes[0].createdAt // .createdAt)
  }]'
