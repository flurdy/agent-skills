#!/usr/bin/env bash
# Usage: run-jobs.sh <run_id>
# Emits a GitHub Actions run's overall status/conclusion plus per-job state as one
# JSON object. The jq shaping (pipes/braces) lives here so the call site stays a
# clean, allowlistable prefix — important for the /watch-rollout poll loop.
set -euo pipefail

gh run view "$1" --json status,conclusion,jobs \
  --jq '{status, conclusion, jobs: [.jobs[] | {name, status, conclusion}]}'
