#!/usr/bin/env bash
# Usage: gh-pr-reply-comment.sh <owner> <repo> <number> <comment_id> <body>
gh api "repos/$1/$2/pulls/$3/comments/$4/replies" -f body="$5"
