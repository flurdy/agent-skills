#!/usr/bin/env bash
# Usage: gh-pr-diff.sh <number> | <owner> <repo> <number>
set -euo pipefail

if (($# == 1)); then
  gh pr diff "$1"
elif (($# == 3)); then
  gh pr diff "$3" --repo "$1/$2"
else
  echo "usage: gh-pr-diff.sh <number> | <owner> <repo> <number>" >&2
  exit 2
fi
