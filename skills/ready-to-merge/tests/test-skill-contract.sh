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

echo "ready-to-merge skill contract tests passed"
