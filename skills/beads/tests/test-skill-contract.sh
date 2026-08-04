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
assert_contains "$SKILL" 'resolves durable work ownership'
assert_contains "$SKILL" 'ephemeral execution checklist and durable tracking'
assert_contains "$SKILL" 'blockers, dependencies, follow-ups, or shared handoff memory'

assert_contains "$SKILL" 'Repository-local instructions remain authoritative'
assert_contains "$SKILL" '<!-- BEGIN BEADS INTEGRATION -->'
assert_contains "$SKILL" 'Never edit generated Beads integration blocks manually.'
assert_contains "$SKILL" 'Do not initialize Beads merely because this skill loaded.'

assert_contains "$SKILL" 'Never infer the owning store from an issue ID, label, prefix, or the current directory.'
assert_contains "$SKILL" '.agents/skills/next/scripts/next-select resolve <selector>'
assert_contains "$SKILL" 'Every later `bd` call uses `bd -C <directory>`.'
assert_contains "$SKILL" 'Cross-project work belongs in the validated workspace root store.'

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

assert_contains "$SKILL" '`bd prime`'
assert_contains "$SKILL" 'hooks may already have injected it.'
assert_contains "$SKILL" '`bd where`'
assert_contains "$SKILL" 'existing-bead ownership still requires the shared resolver.'
assert_contains "$SKILL" '`bd <command> --help`'
assert_contains "$SKILL" 'Do not turn this baseline into a version-specific command catalog.'
assert_not_contains "$SKILL" 'bd create --title='
assert_not_contains "$SKILL" 'bd close <id>'

assert_contains "$SKILL" 'A local commit never authorizes remote Beads synchronization.'
assert_contains "$SKILL" 'Ask for explicit confirmation immediately before every `bd dolt push`.'
assert_contains "$SKILL" 'Run each remote or destructive Beads action as its own visible tool call.'

assert_contains "$CATALOG" '| beads |'
assert_contains "$CATALOG" 'owning store'
assert_contains "$CATALOG" 'ephemeral checklists'
assert_contains "$MAKEFILE" 'test-beads:'

printf '%s\n' 'beads skill contract tests passed'
