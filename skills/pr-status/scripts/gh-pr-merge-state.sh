#!/usr/bin/env bash
# Usage: gh-pr-merge-state.sh <number> <owner> <repo>
gh pr view "$1" --repo "$2/$3" --json mergeStateStatus --jq '.mergeStateStatus'
