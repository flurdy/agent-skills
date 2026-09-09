#!/usr/bin/env bash
# List all open PRs by the current user across a GitHub org.
# Org resolution: see resolve-org.sh
#
# Two sources, run concurrently and unioned:
#   1. `gh search prs` org-wide — catches repos outside the workspace, but reads the
#      search index, which can lag a freshly opened PR by several minutes.
#   2. `gh pr list --repo` for the cwd repo and every workspace member in the org —
#      authoritative, so a PR opened seconds ago still shows up.
set -euo pipefail

# shellcheck source=resolve-org.sh
source "$(dirname "${BASH_SOURCE[0]}")/resolve-org.sh"
ORG="$(resolve_org "${1:-}")"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

direct_repos() {
  local url
  url="$(git remote get-url origin 2>/dev/null || true)"
  [ -n "$url" ] && repo_from_url "$url" || true
  workspace_repos 2>/dev/null || true
}

gh search prs --author @me --state open --owner "$ORG" --limit 50 \
  --json repository,number,title \
  --jq '.[] | {number, title, owner: "'"$ORG"'", repo: .repository.name}' \
  >"$TMP/search" 2>"$TMP/search.err" || echo "search" >>"$TMP/failed" &

i=0
while IFS= read -r repo; do
  [ -n "$repo" ] || continue
  case "$repo" in "$ORG"/*) ;; *) continue ;; esac
  i=$((i + 1))
  gh pr list --repo "$repo" --author @me --state open --limit 50 \
    --json number,title \
    --jq '.[] | {number, title, owner: "'"$ORG"'", repo: "'"${repo#*/}"'"}' \
    >"$TMP/direct.$i" 2>"$TMP/direct.$i.err" || echo "$repo" >>"$TMP/failed" &
done < <(direct_repos | sort -u)
wait

if [ -s "$TMP/failed" ]; then
  while IFS= read -r src; do
    echo "$(basename "$0"): source failed: $src" >&2
  done <"$TMP/failed"
  [ "$(wc -l <"$TMP/failed")" -lt $((i + 1)) ] || exit 1
fi

cat "$TMP"/search "$TMP"/direct.* 2>/dev/null | jq -c -s 'unique_by([.repo, .number]) | .[]'
