#!/usr/bin/env bash
set -euo pipefail

ref="${1:-}"

remote_url() {
  git config --get remote.origin.url 2>/dev/null || true
}

repo_from_remote() {
  local remote="$1"
  if [[ "$remote" =~ github.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
    printf '%s/%s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
  fi
}

repo="$(repo_from_remote "$(remote_url)")"
if [[ -z "$repo" ]]; then
  echo "---STATUS---"
  echo "NO_GIT_REPO"
  exit 0
fi
owner="${repo%%/*}"
name="${repo#*/}"
branch="${ref:-$(git branch --show-current 2>/dev/null || true)}"
sha="$(git rev-parse --verify HEAD 2>/dev/null || true)"
lookup_ref="${ref:-${sha:-HEAD}}"

printf '%s\n' '---STATUS---' 'OK'
printf '%s\n' '---REPO---' "$repo"
printf '%s\n' '---BRANCH---' "${branch:-}"
printf '%s\n' '---SHA---' "${sha:-}"
printf '%s\n' '---LOOKUP-REF---' "$lookup_ref"

printf '%s\n' '---GITHUB-STATUS---'
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  gh api "repos/$owner/$name/commits/$lookup_ref/status" \
    --jq '{state, statuses: [.statuses[] | {context, state, description, target_url}]}' 2>/dev/null \
    || echo '{"error":"github-status-unavailable"}'
else
  echo '{"error":"gh-unavailable"}'
fi

printf '%s\n' '---GITHUB-CHECK-RUNS---'
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  gh api "repos/$owner/$name/commits/$lookup_ref/check-runs" \
    -H 'Accept: application/vnd.github+json' \
    --jq '{total_count, check_runs: [.check_runs[] | {name, status, conclusion, html_url}]}' 2>/dev/null \
    || echo '{"error":"github-check-runs-unavailable"}'
else
  echo '{"error":"gh-unavailable"}'
fi

printf '%s\n' '---CIRCLECI-STATUS---'
if [[ -z "${CIRCLECI_TOKEN:-}" ]]; then
  echo 'NO_TOKEN'
  exit 0
fi

api=(curl -fsS -H "Circle-Token: ${CIRCLECI_TOKEN}")
project_slug="gh/$owner/$name"
encoded_branch="${branch// /%20}"

pipelines_json="$("${api[@]}" "https://circleci.com/api/v2/project/$project_slug/pipeline?branch=$encoded_branch" 2>/dev/null || true)"
if [[ -z "$pipelines_json" || "$(jq -r '.message? // empty' <<<"$pipelines_json")" == "Project not found" ]]; then
  echo '{"error":"circleci-pipelines-unavailable"}'
  exit 0
fi

pipeline_id="$(jq -r '.items[0].id // empty' <<<"$pipelines_json")"
if [[ -z "$pipeline_id" ]]; then
  echo '{"pipeline":null,"workflows":[]}'
  exit 0
fi

workflows_json="$("${api[@]}" "https://circleci.com/api/v2/pipeline/$pipeline_id/workflow" 2>/dev/null || echo '{"items":[]}')"

jq -n \
  --arg project "$project_slug" \
  --arg pipeline "$pipeline_id" \
  --arg branch "$branch" \
  --argjson pipelines "$pipelines_json" \
  --argjson workflows "$workflows_json" \
  '{project, branch, pipeline: ($pipelines.items[0] // null), workflows: ($workflows.items // [])}'
