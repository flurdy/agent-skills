#!/usr/bin/env bash
# Usage: gh-pr-view.sh <number> | <owner> <repo> <number>
set -euo pipefail

if (($# == 1)); then
  number=$1
  repository=()
elif (($# == 3)); then
  number=$3
  repository=(--repo "$1/$2")
else
  echo "usage: gh-pr-view.sh <number> | <owner> <repo> <number>" >&2
  exit 2
fi

gh pr view "$number" "${repository[@]}" \
  --json number,id,url,title,body,additions,deletions,changedFiles,files,state,isDraft,author,baseRefName,baseRefOid,headRefName,headRefOid,headRepository
