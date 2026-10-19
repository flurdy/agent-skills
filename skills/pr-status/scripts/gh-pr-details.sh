#!/usr/bin/env bash
# Usage: gh-pr-details.sh <owner> <repo> <number> [<number>...]
# Fetches all PR status data in one GraphQL call, then each open same-repository PR's
# behind count against its actual base in a second batched call. Requires gh and jq.
# Outputs a JSON array, one object per PR. An unavailable behind count stays null.
set -euo pipefail

OWNER="$1"
REPO="$2"
shift 2

ALIASES=""
for PR in "$@"; do
  ALIASES="${ALIASES}
    pr${PR}: pullRequest(number: ${PR}) {
      number
      state
      headRefName
      baseRefName
      isCrossRepository
      isDraft
      mergeable
      mergeStateStatus
      reviewDecision
      reviews(first: 50, states: [APPROVED]) {
        nodes { author { login } }
      }
      reviewRequests { totalCount }
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

ROWS=$(gh api graphql \
  -f query="$QUERY" \
  -f owner="$OWNER" \
  -f repo="$REPO" \
  --jq '[.data.repository | to_entries[] | .value | {
    number: .number,
    branch: .headRefName,
    base: .baseRefName,
    isDraft: .isDraft,
    mergeable: .mergeable,
    mergeState: .mergeStateStatus,
    reviewDecision: .reviewDecision,
    approvers: ([.reviews.nodes[].author.login] | unique),
    reviewRequestCount: .reviewRequests.totalCount,
    unresolvedThreads: ([.reviewThreads.nodes[] | select(.isResolved == false)] | length),
    checksState: .commits.nodes[0].commit.statusCheckRollup.state,
    lastPush: .commits.nodes[0].commit.committedDate,
    mergeCommitSha: .mergeCommit.oid,
    mergeCommitAt: .mergeCommit.committedDate,
    mainChecksState: .mergeCommit.statusCheckRollup.state,
    readyAt: (.timelineItems.nodes[0].createdAt // .createdAt),
    compare: (if .state == "OPEN" and .isCrossRepository == false and .baseRefName and .headRefName
              then {base: .baseRefName, head: .headRefName} else null end)
  }]')

# Branch names travel only as GraphQL variables, never as query text.
COMPARE_VARIABLES=""
COMPARE_ALIASES=""
COMPARE_ARGS=()
while IFS=$'\t' read -r NUMBER BASE HEAD; do
  COMPARE_VARIABLES="${COMPARE_VARIABLES}, \$base${NUMBER}: String!, \$head${NUMBER}: String!"
  COMPARE_ALIASES="${COMPARE_ALIASES}
    pr${NUMBER}: ref(qualifiedName: \$base${NUMBER}) { compare(headRef: \$head${NUMBER}) { behindBy } }"
  COMPARE_ARGS+=(-f "base${NUMBER}=refs/heads/${BASE}" -f "head${NUMBER}=${HEAD}")
done < <(jq -r '.[] | select(.compare) | [.number, .compare.base, .compare.head] | @tsv' <<<"$ROWS")

COUNTS='{}'
if [[ -n $COMPARE_ALIASES ]]; then
  COMPARE_QUERY="query(\$owner: String!, \$repo: String!${COMPARE_VARIABLES}) {
  repository(owner: \$owner, name: \$repo) {${COMPARE_ALIASES}
  }
}"
  # Partial GraphQL errors (e.g. a deleted head branch) still return the resolved counts.
  if ! RESPONSE=$(gh api graphql -f query="$COMPARE_QUERY" -f owner="$OWNER" -f repo="$REPO" \
      "${COMPARE_ARGS[@]}" 2>/dev/null); then
    echo "gh-pr-details: some behind counts are unavailable; they are null" >&2
  fi
  COUNTS=$(jq -c '.data.repository | if type == "object" then map_values(
      (try .compare.behindBy catch null) | if type == "number" then . else null end) else {} end' \
    <<<"${RESPONSE:-}" 2>/dev/null) || COUNTS='{}'
  [[ -n $COUNTS ]] || COUNTS='{}'
fi

jq -c --argjson counts "$COUNTS" \
  '[.[] | .behindBy = (if .compare then $counts["pr\(.number)"] // null else null end) | del(.compare)]' \
  <<<"$ROWS"
