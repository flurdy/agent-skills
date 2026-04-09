#!/usr/bin/env bash
# Usage: gh-pr-checks.sh <number>
gh pr checks "$1" 2>/dev/null | awk '{print $2}' | sort | uniq -c
