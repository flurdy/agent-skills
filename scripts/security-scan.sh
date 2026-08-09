#!/usr/bin/env bash
# Baseline security scan for the agent-skills repository.
# Mechanical detection only. Judgment-based dimensions are documented in
# docs/security-scan.md and require a manual review pass.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

findings=0
high_findings=0

report() {
  local severity="$1" check="$2" detail="$3"
  printf '%s\t%s\t%s\n' "$severity" "$check" "$detail"
  findings=$((findings + 1))
  [ "$severity" = HIGH ] && high_findings=$((high_findings + 1))
  return 0
}

# Production scripts only. Test harnesses use deliberate sentinels and fixed
# paths; scanning them produces noise, not signal. See docs/security-scan.md.
production_shell() {
  find skills scripts -name '*.sh' -not -path '*/tests/*' -print0 2>/dev/null
}

production_python() {
  find skills scripts -name '*.py' -not -path '*/tests/*' -print0 2>/dev/null
}

# 1. Credentials in process arguments. curl -H with an auth-bearing variable
# puts the secret in argv. Readable by same-UID processes as a matter of course;
# cross-user visibility depends on /proc mount options and host policy.
check_credentials_in_argv() {
  while IFS= read -r -d '' file; do
    while IFS=: read -r line _; do
      report HIGH credentials-in-argv "$file:$line"
    done < <(grep -nE 'curl[^|]*-H[[:space:]]+"[^"]*(Token|Authorization)[^"]*\$' "$file" || true)
  done < <(production_shell)
}

# 2. curl honouring ~/.curlrc while carrying a secret. A user curlrc with
# trace-ascii or dump-header writes the auth header to disk.
check_curl_config_isolation() {
  while IFS= read -r -d '' file; do
    # Needs a real curl invocation carrying auth, not a 'command -v curl' probe
    # or a public unauthenticated fetch.
    grep -qE '(header|-H)[^\n]*(Token|Authorization)' "$file" 2>/dev/null || continue
    grep -qE '^[[:space:]]*[^#]*[|]?[[:space:]]*curl[[:space:]]+-' "$file" 2>/dev/null || continue
    grep -q -- '--disable' "$file" 2>/dev/null && continue
    report LOW curl-honours-user-config "$file"
  done < <(production_shell)
}

# 3. Untrusted text interpolated into a git pretty format string. Branch names
# may contain % placeholders, which git expands into the parsed output stream.
check_git_format_injection() {
  while IFS= read -r -d '' file; do
    while IFS=: read -r line _; do
      report MEDIUM git-format-injection "$file:$line"
    done < <(grep -nE -- "--(format|pretty)=[\"'][^\"']*\\\$\{?[A-Za-z_]" "$file" || true)
  done < <(production_shell)
}

# 4. Worktree porcelain parsed by whitespace field. Paths containing spaces are
# silently truncated. Correct form is substr($0,10).
check_worktree_field_split() {
  while IFS= read -r -d '' file; do
    while IFS=: read -r line _; do
      report MEDIUM worktree-field-split "$file:$line"
    done < <(grep -nE "\^worktree .*print \\\$2" "$file" || true)
  done < <(production_shell)
}

# 5. Fixed paths under world-writable /tmp. Predictable names are pre-claimable
# by another local user, including as a symlink.
check_fixed_temp_paths() {
  while IFS= read -r -d '' file; do
    while IFS=: read -r line _; do
      report MEDIUM fixed-temp-path "$file:$line"
    done < <(grep -nE '=["'"'"']?/tmp/[a-zA-Z]' "$file" || true)
  done < <(production_shell)
}

# 6. Shell-level dangers: eval, bash -c on a variable, curl piped to a shell.
check_shell_execution_sinks() {
  while IFS= read -r -d '' file; do
    while IFS=: read -r line _; do
      report HIGH shell-execution-sink "$file:$line"
    done < <(grep -nE '(^|[^_[:alnum:]])eval[[:space:]]+"?\$|bash -c[[:space:]]+"\$|curl[^|]*\|[[:space:]]*(ba)?sh' "$file" || true)
  done < <(production_shell)
}

# 7. Python execution sinks.
check_python_execution_sinks() {
  while IFS= read -r -d '' file; do
    while IFS=: read -r line _; do
      report HIGH python-execution-sink "$file:$line"
    done < <(grep -nE 'shell=True|os\.system|os\.popen|(^|[^_[:alnum:]])(eval|exec)\(|pickle\.loads' "$file" || true)
    while IFS=: read -r line _; do
      report HIGH python-execution-sink "$file:$line"
    done < <(grep -nE 'yaml\.load\(' "$file" | grep -v SafeLoader || true)
  done < <(production_python)
}

# 8. Agent CLI spawned non-interactively with a shell tool enabled. Pi has no
# sandbox and no tool-permission prompt, so an unattended run executes whatever
# the model emits. Note --approve grants project trust, not tool auto-approval.
check_unattended_shell_agent() {
  while IFS= read -r -d '' file; do
    grep -qE '"(pi|claude|codex|gemini)"' "$file" 2>/dev/null || continue
    grep -qE '"--tools"|"--print"|"--no-session"' "$file" 2>/dev/null || continue
    grep -qE '"[^"]*\bbash\b[^"]*"' "$file" 2>/dev/null || continue
    report MEDIUM unattended-shell-agent "$file"
  done < <(production_python)
}

# 9. Skills that ingest attacker-writable text without an untrusted-data guard.
# The convention exists in the repo; these skills do not carry it.
check_injection_guards() {
  local skill name
  for skill in skills/*/SKILL.md; do
    [ -f "$skill" ] || continue
    # Trigger on the ingest verbs themselves, not on prose mentioning a PR.
    grep -qE 'mcp__jira__|mcp__confluence__|WebFetch|gh pr (view|diff)|gh api|gh-pr-|trello-(api|pull)' "$skill" || continue
    # Either the prose guard, or the external-text fence convention that marks
    # imported text structurally (see skills/trello-beads/SKILL.md).
    grep -qiE 'untrusted|external-text' "$skill" && continue
    name="$(dirname "$skill")"
    report ADVISORY missing-injection-guard "${name#skills/}"
  done
}

# 10. Skills asserting read-only or never-publishes while holding a wildcard
# grant that permits exactly the forbidden action.
check_readonly_claim_vs_grant() {
  local skill tools
  for skill in skills/*/SKILL.md; do
    [ -f "$skill" ] || continue
    grep -qiE 'read-only|never publish|never mutat|passive' "$skill" || continue
    tools="$(grep -m1 '^allowed-tools:' "$skill" || true)"
    [ -n "$tools" ] || continue
    case "$tools" in
      *'Bash(git:*)'* | *'Bash(gh:*)'* | *'mcp__jira__*'* | *'jira_post'* | *'jira_delete'*)
        report ADVISORY readonly-claim-vs-grant "${skill%/SKILL.md}" ;;
    esac
  done
}

printf 'SEVERITY\tCHECK\tLOCATION\n'
check_credentials_in_argv
check_curl_config_isolation
check_git_format_injection
check_worktree_field_split
check_fixed_temp_paths
check_shell_execution_sinks
check_python_execution_sinks
check_unattended_shell_agent
check_injection_guards
check_readonly_claim_vs_grant

printf '\n%s finding(s), %s HIGH.\n' "$findings" "$high_findings"
printf 'Judgment-based dimensions require the manual pass in docs/security-scan.md.\n'

# Only HIGH fails the build. MEDIUM and below are reported for triage: the repo
# carries one accepted MEDIUM (the pilot runner, see docs/skill-effectiveness-pilot.md)
# and ADVISORY entries are candidate lists, not defects.
if [ "$high_findings" -gt 0 ]; then
  printf 'FAIL: %s HIGH finding(s).\n' "$high_findings" >&2
  exit 1
fi
