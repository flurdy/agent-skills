#!/usr/bin/env bash
# Usage: gh-pr-conversation-comment.sh <owner> <repo> <number> <body>
set -euo pipefail

if [[ $# -ne 4 ]]; then
    printf 'Usage: %s <owner> <repo> <number> <body>\n' "${0##*/}" >&2
    exit 2
fi

gh api "repos/$1/$2/issues/$3/comments" -f body="$4"
