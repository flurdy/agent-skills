#!/usr/bin/env bash
# Usage: gh-pr-view.sh <number>
gh pr view "$1" --json title,body,additions,deletions,changedFiles,files,state,author,baseRefName,headRefName
