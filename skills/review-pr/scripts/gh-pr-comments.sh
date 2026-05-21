#!/usr/bin/env bash
# Usage: gh-pr-comments.sh <number>
# Emits, in order:
#   1. Reviews & issue-level comments (review states + body)
#   2. Inline review threads via gh api graphql (with isResolved/isOutdated)
#   3. Inline comments grouped per-file (REST pulls/{num}/comments)
# Use to surface unresolved feedback from other reviewers before producing
# a review summary.
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

echo
echo "=== Inline Comments Per-File ==="
# REST review comments grouped by file path so each file's feedback reads as
# a unit. Threading state (resolved/outdated) lives in the GraphQL section
# above; this view is for "what was said on each file."
gh api --paginate "/repos/$OWNER/$NAME/pulls/$NUM/comments" --jq '
  group_by(.path)
  | map({
      path: .[0].path,
      comments: (
        sort_by(.created_at)
        | map({
            author: .user.login,
            line: (.line // .original_line),
            side: .side,
            in_reply_to_id: .in_reply_to_id,
            createdAt: .created_at,
            body: .body
          })
      )
    })'
