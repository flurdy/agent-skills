#!/usr/bin/env bash
set -euo pipefail

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
if [[ -z "${CIRCLECI_TOKEN:-}" ]]; then
  echo "---STATUS---"
  echo "NO_TOKEN"
  exit 0
fi

owner="${repo%%/*}"
name="${repo#*/}"
branch="${1:-$(git branch --show-current 2>/dev/null || true)}"
project_slug="gh/$owner/$name"
encoded_branch="${branch// /%20}"
api=(curl -fsS -H "Circle-Token: ${CIRCLECI_TOKEN}")

pipelines_json="$("${api[@]}" "https://circleci.com/api/v2/project/$project_slug/pipeline?branch=$encoded_branch")"
pipeline_id="$(jq -r '.items[0].id // empty' <<<"$pipelines_json")"
if [[ -z "$pipeline_id" ]]; then
  echo "---STATUS---"
  echo "NO_PIPELINE"
  exit 0
fi

workflows_json="$("${api[@]}" "https://circleci.com/api/v2/pipeline/$pipeline_id/workflow")"
workflow_id="$(jq -r '.items[0].id // empty' <<<"$workflows_json")"
if [[ -z "$workflow_id" ]]; then
  echo "---STATUS---"
  echo "NO_WORKFLOW"
  exit 0
fi

jobs_json="$("${api[@]}" "https://circleci.com/api/v2/workflow/$workflow_id/job")"
job_number="$(jq -r '.items[] | select(.status == "failed" or .status == "failing" or .status == "blocked" or .status == "canceled" or .status == "unauthorized") | .job_number' <<<"$jobs_json" | head -1)"
if [[ -z "$job_number" ]]; then
  job_number="$(jq -r '.items[0].job_number // empty' <<<"$jobs_json")"
fi

printf '%s\n' '---STATUS---' 'OK'
printf '%s\n' '---REPO---' "$repo"
printf '%s\n' '---BRANCH---' "$branch"
printf '%s\n' '---PIPELINE---' "$pipeline_id"
printf '%s\n' '---WORKFLOW---' "$workflow_id"
printf '%s\n' '---JOBS---'
jq '{items: [.items[] | {name, status, job_number, stopped_at}]}' <<<"$jobs_json"
printf '%s\n' '---LOGS---'
if [[ -n "$job_number" ]]; then
  "${api[@]}" "https://circleci.com/api/v2/project/$project_slug/$job_number/output" \
    | jq -r '.[] | "### " + (.step // "step") + " / " + (.name // "output") + "\n" + (.message // "")'
else
  echo 'No jobs found.'
fi
