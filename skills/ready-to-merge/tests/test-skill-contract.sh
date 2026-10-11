#!/usr/bin/env bash
set -euo pipefail

skill_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
skill_file="$skill_dir/SKILL.md"
wrapper="$skill_dir/scripts/git-unpushed.sh"
grant='Bash(~/.agents/skills/ready-to-merge/scripts/git-unpushed.sh:*)'

[[ -x "$wrapper" ]] || { echo "git-unpushed wrapper must be executable" >&2; exit 1; }
[[ $(grep -F -- 'allowed-tools:' "$skill_file" | grep -Fo -- "$grant" | wc -l) -eq 1 ]] || {
  echo "ready-to-merge must grant exactly its git-unpushed wrapper" >&2
  exit 1
}

for script in gh-branch-view.py gh-branch-delete.py merge-timing.py; do
  [[ -x "$skill_dir/scripts/$script" ]] || { echo "$script must be executable" >&2; exit 1; }
  grant="Bash(~/.agents/skills/ready-to-merge/scripts/$script:*)"
  grep -F -- 'allowed-tools:' "$skill_file" | grep -Fq -- "$grant" || {
    echo "missing narrow grant for $script" >&2
    exit 1
  }
done

for forbidden in 'Bash(gh:*)' 'Bash(gh api:*)' 'gh api '; do
  if grep -Fq -- "$forbidden" "$skill_file"; then
    echo "unexpected raw API access: $forbidden" >&2
    exit 1
  fi
done

for invariant in \
  'fresh confirmation' \
  'Never infer deletion permission from merge approval' \
  'defaultBranchRef' \
  'headRefOid' \
  'fork' \
  'dependent PRs' \
  '404 does not prove auto-deletion' \
  'does not provide atomic compare-and-delete' \
  'standalone tool call' \
  'github.com only'; do
  grep -Fq -- "$invariant" "$skill_file" || { echo "missing cleanup invariant: $invariant" >&2; exit 1; }
done

for invariant in \
  'without a policy, timing is never checked or rendered' \
  'PR cannot relax its own restriction' \
  'never clear' \
  'never pass it here' \
  'still reports applicable timing' \
  'If timing is `required` or `unknown`, stop here: do not offer the merge' \
  'Do not wait, sleep, schedule or retry' \
  'Recheck timing immediately before merging' \
  'timing change, and a recheck never merges, waits or schedules' \
  'No override bypasses a `required` restriction'; do
  grep -Fq -- "$invariant" "$skill_file" || { echo "missing timing invariant: $invariant" >&2; exit 1; }
done

echo "ready-to-merge skill contract tests passed"
