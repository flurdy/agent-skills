#!/usr/bin/env bash
# Usage: gh-pr-comments.sh <number>
# Emits reviews (with state), issue-level comments, and inline review threads
# with their resolution / outdated state. Use to surface unresolved feedback
# from other reviewers before producing a review summary.
set -euo pipefail
NUM="${1:?PR number required}"
REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
OWNER="${REPO%/*}"; NAME="${REPO#*/}"

echo "=== Reviews & Issue Comments ==="
gh pr view "$NUM" --json reviews,comments --jq '{
  reviews: [.reviews[] | {author: .author.login, state: .state, body: .body, submittedAt: .submittedAt}],
  issueComments: [.comments[] | {author: .author.login, body: .body, createdAt: .createdAt}]
}'

echo
echo "=== Inline Review Threads (with isResolved / isOutdated) ==="
gh api graphql \
  -F owner="$OWNER" -F repo="$NAME" -F num="$NUM" \
  -f query='
query($owner: String!, $repo: String!, $num: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $num) {
      reviewThreads(first: 100) {
        nodes {
          isResolved
          isOutdated
          path
          line
          comments(first: 20) {
            nodes { author { login } body createdAt }
          }
        }
      }
    }
  }
}' --jq '.data.repository.pullRequest.reviewThreads.nodes'
