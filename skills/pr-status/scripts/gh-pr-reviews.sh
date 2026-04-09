#!/usr/bin/env bash
# Usage: gh-pr-reviews.sh <owner> <repo> <number>
gh api "repos/$1/$2/pulls/$3/reviews" \
  --jq '[.[] | select(.state == "APPROVED") | .user.login] | unique | join(", ")'
