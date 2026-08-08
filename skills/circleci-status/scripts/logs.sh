#!/usr/bin/env bash
set -euo pipefail

load_circleci_token() {
  [[ -z "${CIRCLECI_TOKEN:-}" ]] || return 0
  [[ -n "${SECRET_API_KEY_PROJECT:-}" ]] || return 0
  command -v secret-api-key >/dev/null 2>&1 || return 0
  CIRCLECI_TOKEN="$(secret-api-key lookup circleci "$SECRET_API_KEY_PROJECT" 2>/dev/null || true)"
}

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
load_circleci_token
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
# Token goes to curl on stdin, never in argv where ps would expose it.
# --disable stops a user ~/.curlrc from tracing the header to disk.
[[ "$CIRCLECI_TOKEN" != *['"\\'$'\n\r']* ]] \
  || { echo "---STATUS---"; echo "BAD_TOKEN"; exit 0; }

circleci_api() {
  printf 'header = "Circle-Token: %s"\n' "$CIRCLECI_TOKEN" \
    | curl --disable --config - --silent --show-error --fail --max-time 30 "$@"
}

pipelines_json="$(circleci_api "https://circleci.com/api/v2/project/$project_slug/pipeline?branch=$encoded_branch")"
pipeline_id="$(jq -r '.items[0].id // empty' <<<"$pipelines_json")"
if [[ -z "$pipeline_id" ]]; then
  echo "---STATUS---"
  echo "NO_PIPELINE"
  exit 0
fi

workflows_json="$(circleci_api "https://circleci.com/api/v2/pipeline/$pipeline_id/workflow")"
workflow_id="$(jq -r '.items[0].id // empty' <<<"$workflows_json")"
if [[ -z "$workflow_id" ]]; then
  echo "---STATUS---"
  echo "NO_WORKFLOW"
  exit 0
fi

jobs_json="$(circleci_api "https://circleci.com/api/v2/workflow/$workflow_id/job")"
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
if [[ -z "$job_number" ]]; then
  echo 'No jobs found.'
  exit 0
fi

v2_output="$(circleci_api "https://circleci.com/api/v2/project/$project_slug/$job_number/output" 2>/dev/null || true)"
if [[ -n "$v2_output" && "$(jq -r 'type' <<<"$v2_output" 2>/dev/null || true)" == "array" ]]; then
  jq -r '.[] | "### " + ((.step // "step") | tostring) + " / " + (.name // "output") + "\n" + (.message // "")' <<<"$v2_output"
  exit 0
fi

# CircleCI v2 occasionally returns 404 for output while v1.1 exposes
# presigned step output URLs. Fetch the failed action first, else first action.
v1_job_json="$(circleci_api "https://circleci.com/api/v1.1/project/github/$owner/$name/$job_number" 2>/dev/null || true)"
if [[ -z "$v1_job_json" ]]; then
  echo 'No job output available.'
  exit 0
fi

output_url="$(jq -r '.steps[]?.actions[]? | select(.failed == true) | .output_url // empty' <<<"$v1_job_json" | head -1)"
if [[ -z "$output_url" ]]; then
  output_url="$(jq -r '.steps[]?.actions[]? | .output_url // empty' <<<"$v1_job_json" | head -1)"
fi

if [[ -n "$output_url" ]]; then
  curl --disable --silent --show-error --fail --max-time 30 "$output_url" | jq -r '.[] | .message // empty'
else
  echo 'No job output available.'
fi
