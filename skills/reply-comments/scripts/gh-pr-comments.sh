#!/usr/bin/env bash
# Usage: gh-pr-comments.sh <owner> <repo> <number>
gh api "repos/$1/$2/pulls/$3/comments" \
  --jq '.[] | {id, path, line, body, user: .user.login, in_reply_to_id, created_at}'
