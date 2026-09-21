#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
SKILL="$ROOT_DIR/skills/beads/SKILL.md"
CATALOG="$ROOT_DIR/skills/README.md"
MAKEFILE="$ROOT_DIR/Makefile"

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

assert_contains() {
    local file=$1
    local expected=$2
    grep -Fq -- "$expected" "$file" || fail "$file missing: $expected"
}

assert_not_contains() {
    local file=$1
    local unexpected=$2
    if grep -Fq -- "$unexpected" "$file"; then
        fail "$file unexpectedly contains: $unexpected"
    fi
}

assert_contains "$SKILL" 'name: beads'
assert_contains "$SKILL" 'whenever an agent uses `bd`'
assert_contains "$SKILL" 'resolves work ownership'
assert_contains "$SKILL" 'ephemeral checklist and durable tracking'
assert_contains "$SKILL" 'manages durable tasks, blockers, or handoffs'

assert_contains "$SKILL" 'Repository-local instructions remain authoritative'
assert_contains "$SKILL" '<!-- BEGIN BEADS INTEGRATION -->'
assert_contains "$SKILL" 'Never edit generated Beads integration blocks manually during ordinary work.'
assert_contains "$SKILL" 'cleanup-only, marker-bounded native edit'
assert_contains "$SKILL" 'Do not initialize Beads merely because this skill loaded.'

assert_contains "$SKILL" 'Never infer the owning store from an issue ID, label, prefix, or the current directory.'
assert_contains "$SKILL" '.agents/skills/next/scripts/next-select resolve <selector>'
assert_contains "$SKILL" 'Every later `bd` call uses `bd -C <directory>`.'
assert_contains "$SKILL" 'Cross-project work belongs in the validated workspace root store.'
assert_contains "$SKILL" 'Local means a mutation in the resolver-proven owning store, not only the invoking cwd.'
assert_contains "$SKILL" 'without `/implement` or a source worktree lease'
assert_contains "$SKILL" 'Beads writes never acquire a source lease'
assert_contains "$SKILL" 'configured Dolt remote alone does not turn a local comment into synchronization'
assert_contains "$SKILL" 'Verify effective export, backup and synchronization settings and actual side effects'
assert_contains "$SKILL" '`/implement` alone does not authorize remote or destructive actions.'

assert_contains "$SKILL" 'Use `todo` only as an ephemeral execution checklist for the active tracked item.'
assert_contains "$SKILL" 'Never duplicate a durable backlog item into `todo`.'
assert_contains "$SKILL" 'Keep blockers, dependencies, and follow-ups in Beads.'

for route in next triage plan-to-backlog backlog-groom tracking-sweep trello-beads beads-check-dolt-migration beads-migrate-to-dolt; do
    assert_contains "$SKILL" "/$route"
    assert_contains "$SKILL" "Skill($route)"
done
assert_contains "$SKILL" 'Dispatch to the focused skill instead of reproducing its procedure.'
assert_contains "$SKILL" 'If a focused skill has no owner-routing input and the selected store is not the current active store, do not invoke it there.'
assert_contains "$SKILL" 'render a switch-directory and focused-invocation handoff, then stop'

assert_contains "$SKILL" 'Do not use `bd edit`; it opens an interactive editor.'
assert_contains "$SKILL" 'prefer `--json` when parsing output programmatically.'
assert_contains "$SKILL" 'Discovery does not authorize mutation.'
assert_contains "$SKILL" 'close only when the tracked outcome is actually complete.'
assert_contains "$SKILL" 'Do not infer assignment, a claim or session activity from the issue `owner`.'
assert_contains "$SKILL" 'accountable human and may be set while `assignee` is empty'
assert_contains "$SKILL" 'owner value as an assignment.'
assert_contains "$SKILL" 'Every agent-driven transition to `in_progress` records one claim-attribution comment'
assert_contains "$SKILL" 'available harness session ID, a UTC timestamp, and the proven owning store'
assert_contains "$SKILL" 'session activity is unverified'
assert_contains "$SKILL" 'retries and no-op claim'
assert_contains "$SKILL" 'attempts do not create duplicate comments'
assert_contains "$SKILL" '`next-select start` enforce'

assert_contains "$SKILL" '`bd prime`'
assert_contains "$SKILL" 'no hook injects it'
assert_contains "$SKILL" 'add the `human` label'
assert_contains "$SKILL" '`bd human list`'
assert_contains "$SKILL" '`bd supersede`'
assert_contains "$SKILL" '`bd defer --until`'
assert_contains "$SKILL" 'Do not use `bd remember`'
assert_contains "$SKILL" '`bd where`'
assert_contains "$SKILL" 'existing-bead ownership still requires the shared resolver.'
assert_contains "$SKILL" '`bd <command> --help`'
assert_contains "$SKILL" 'Do not turn this baseline into a version-specific command catalog.'
assert_not_contains "$SKILL" 'bd create --title='
assert_not_contains "$SKILL" 'bd close <id>'

assert_contains "$SKILL" 'A local commit never authorizes remote Beads synchronization.'
assert_contains "$SKILL" 'Ask for explicit confirmation immediately before every raw `bd dolt push`.'
assert_contains "$SKILL" 'unique'
assert_contains "$SKILL" 'store set with `make beads-sync-check`'
assert_contains "$SKILL" 'Obtain fresh explicit confirmation for the complete'
assert_contains "$SKILL" '`make beads-sync` invocation, then run it as one visible command.'
assert_contains "$SKILL" 'Report per-store failures and the overall non-zero result'
assert_contains "$SKILL" 'do not retry automatically'
assert_contains "$SKILL" 'Stricter repository policy still wins'
assert_not_contains "$SKILL" 'enroll'
assert_contains "$SKILL" 'Never invoke synchronization during a read-only list, resolver probe or local triage operation.'
assert_contains "$SKILL" 'Run each remote or destructive Beads action as its own visible tool call.'

assert_contains "$CATALOG" '| beads |'
assert_contains "$CATALOG" 'owning store'
assert_contains "$CATALOG" 'ephemeral checklists'
assert_contains "$MAKEFILE" 'test-beads:'

CLEANUP="$ROOT_DIR/skills/beads/references/integration-cleanup.md"
assert_contains "$SKILL" 'references/integration-cleanup.md'
assert_contains "$CLEANUP" '--skip-agents --skip-hooks'
assert_contains "$CLEANUP" 'Never rerun init as cleanup'
assert_contains "$CLEANUP" '--expect'
assert_contains "$CLEANUP" 'immediately before each destructive command'
assert_contains "$CLEANUP" 'No automatic rollback'
assert_contains "$CLEANUP" 'ignored and untracked'
assert_contains "$CLEANUP" 'symlink'
assert_contains "$CLEANUP" '`agents-blocks`'
assert_contains "$CLEANUP" '`codex-generated`'
assert_contains "$CLEANUP" '`interactions-ignore`'
assert_contains "$CLEANUP" 'sole reviewed exception'
assert_contains "$CLEANUP" 'git rm --cached'
assert_contains "$CLEANUP" 'env --chdir=/absolute/repository'
assert_contains "$CLEANUP" 'check-ignore -v --no-index'
assert_contains "$ROOT_DIR/skills/beads-migrate-to-dolt/references/aftercare.md" '../../beads/references/integration-cleanup.md'

printf '%s\n' 'beads skill contract tests passed'
