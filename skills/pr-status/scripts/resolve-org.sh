#!/usr/bin/env bash
# Shared GitHub-org resolution for the pr-status scripts. Source it, then call
# `resolve_org "${1:-}"`.
#
# Resolution order (first hit wins):
#   1. $PR_STATUS_ORG
#   2. explicit argument
#   3. origin remote of the cwd repo
#   4. most common org across a multi-repo workspace's member repos
#   5. nothing -> stderr message, non-zero exit
#
# Step 4 exists because a multi-repo workspace root is often deliberately local-only
# (personal tooling, nothing to push). There, step 3 yields an empty string and
# `gh search prs --owner ""` exits 2 writing nothing to stdout or stderr — which the
# caller cannot distinguish from "no open PRs". The member repos do have remotes, so
# ask them instead.
#
# Members need not agree: a workspace can mix orgs, and can hold repos on non-GitHub
# remotes entirely. Non-GitHub remotes are skipped and the most common org wins.

org_from_url() {   # $1 = remote URL; prints the org, or fails for non-GitHub remotes
  case "$1" in
    *github.com[:/]*) printf '%s\n' "$1" | sed -E 's#.*github\.com[:/]##; s#/.*##' ;;
    *) return 1 ;;
  esac
}

workspace_orgs() {   # prints one org per member repo that has a GitHub origin
  local script root line name url org section
  script="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../wrap-up/scripts" 2>/dev/null && pwd)/multirepo.sh"
  [ -x "$script" ] || return 1
  root=""
  section=""
  while IFS= read -r line; do
    case "$line" in
      ---ROOT---)  section="root";  continue ;;
      ---REPOS---) section="repos"; continue ;;
      ---*---)     section="";      continue ;;
    esac
    case "$section" in
      root)  root="$line"; section="" ;;
      repos)
        [ -n "$root" ] || continue
        name="${line%%|*}"
        url="$(git -C "$root/$name" remote get-url origin 2>/dev/null || true)"
        [ -n "$url" ] || continue
        org="$(org_from_url "$url")" || continue
        [ -n "$org" ] && printf '%s\n' "$org"
        ;;
    esac
  done < <("$script")
}

resolve_org() {   # $1 = optional explicit org
  local url org
  if [ -n "${PR_STATUS_ORG:-}" ]; then
    printf '%s\n' "$PR_STATUS_ORG"; return 0
  fi
  if [ -n "${1:-}" ]; then
    printf '%s\n' "$1"; return 0
  fi

  url="$(git remote get-url origin 2>/dev/null || true)"
  if [ -n "$url" ] && org="$(org_from_url "$url")" && [ -n "$org" ]; then
    printf '%s\n' "$org"; return 0
  fi

  org="$(workspace_orgs 2>/dev/null | sort | uniq -c | sort -rn | head -1 | awk '{print $2}')"
  if [ -n "$org" ]; then
    printf '%s\n' "$org"; return 0
  fi

  echo "$(basename "${0}"): cannot resolve a GitHub org — the cwd repo has no GitHub origin remote and no workspace member supplied one. Pass the org as an argument or set \$PR_STATUS_ORG." >&2
  return 1
}
