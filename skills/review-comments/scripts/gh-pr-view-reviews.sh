#!/usr/bin/env bash
# Usage: gh-pr-view-reviews.sh <number>
gh pr view "$1" --json reviews,comments
