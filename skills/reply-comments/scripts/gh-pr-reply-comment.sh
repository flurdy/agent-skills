#!/usr/bin/env bash
# Usage: gh-pr-reply-comment.sh <owner> <repo> <number> <comment_id> <body>
set -euo pipefail

if [[ $# -ne 5 ]]; then
    printf 'Usage: %s <owner> <repo> <number> <comment_id> <body>\n' "${0##*/}" >&2
    exit 2
fi

gh api "repos/$1/$2/pulls/$3/comments/$4/replies" -f body="$5"
