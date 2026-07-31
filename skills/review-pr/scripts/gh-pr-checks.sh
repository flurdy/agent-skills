#!/usr/bin/env bash
# Usage: gh-pr-checks.sh <number> | <owner> <repo> <number>
set -euo pipefail

if (($# == 1)); then
  number=$1
  repository=()
elif (($# == 3)); then
  number=$3
  repository=(--repo "$1/$2")
else
  echo "usage: gh-pr-checks.sh <number> | <owner> <repo> <number>" >&2
  exit 2
fi

error_file=$(mktemp)
trap 'rm -f "$error_file"' EXIT
set +e
checks=$(gh pr checks "$number" "${repository[@]}" 2>"$error_file")
status=$?
set -e

if ((status != 0 && status != 1 && status != 8)); then
  cat "$error_file" >&2
  exit "$status"
fi
if [[ -z $checks ]] || ! awk -F'\t' 'NF < 2 || $2 == "" { exit 1 }' <<<"$checks"; then
  cat "$error_file" >&2
  echo "gh-pr-checks.sh: gh returned no structured check data" >&2
  exit 1
fi

printf '%s\n' "$checks" \
  | awk -F'\t' '{print $2}' \
  | sort \
  | uniq -c
