#!/usr/bin/env bash
set -euo pipefail

skill_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
skill_file="$skill_dir/SKILL.md"
script="$skill_dir/scripts/artifact_hygiene.py"
config="$skill_dir/references/gitleaks.toml"

[[ -f "$skill_file" ]] || { echo "missing SKILL.md" >&2; exit 1; }
[[ -x "$script" ]] || { echo "artifact_hygiene.py must be executable" >&2; exit 1; }
[[ -f "$config" ]] || { echo "missing audit-owned gitleaks config" >&2; exit 1; }

for required in \
  'local-only' \
  'read-only' \
  'publishable working tree' \
  'unpublished branch history' \
  'partial' \
  'never fetches' \
  'never mutates' \
  'raw candidate content' \
  'GitHub pull requests' \
  'Jira'; do
  grep -Fq "$required" "$skill_file" || {
    echo "SKILL.md missing contract text: $required" >&2
    exit 1
  }
done

for forbidden in 'mcp__jira' 'mcp__github' 'WebFetch' 'WebSearch'; do
  if grep -F -- 'allowed-tools:' "$skill_file" | grep -Fq "$forbidden"; then
    echo "SKILL.md permits forbidden remote tool: $forbidden" >&2
    exit 1
  fi
done

grep -Fq 'scanner_capability_probe' "$script" || {
  echo "helper must gate complete coverage on a scanner capability probe" >&2
  exit 1
}
if grep -Fq 'ARTIFACT_HYGIENE_TEST' "$script"; then
  echo "production helper must not expose a test scanner override" >&2
  exit 1
fi

python3 -m py_compile "$script"
echo "artifact-hygiene skill contract: PASS"
