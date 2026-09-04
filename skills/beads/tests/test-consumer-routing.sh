#!/usr/bin/env bash
# Every skill that reads or writes an existing bead must route through the shared
# resolver and qualify its bd calls with the proven owning store.
set -euo pipefail
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
RESOLVER='~/.agents/skills/next/scripts/next-select'

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

frontmatter() {
    awk 'NR == 1 { next } /^---$/ { exit } { print }' "$1"
}

# Fenced code lines only: prose may mention `bd close` when explaining the rule.
code_lines() {
    awk '/^ *```/ { fenced = !fenced; next } fenced { print }' "$1"
}

assert_contains() {
    grep -Fq -- "$2" "$1" || fail "$1 missing: $2"
}

# Skills that mutate an existing bead: resolver allowed, resolver used, every mutating bd
# call in code qualified with -C, and the four resolver outcomes handled.
for skill in complete-task create-pr; do
    file="$ROOT_DIR/skills/$skill/SKILL.md"
    frontmatter "$file" | grep -Fq -- "Bash($RESOLVER:*)" || fail "$skill: resolver not in allowed-tools"
    assert_contains "$file" "$RESOLVER resolve <bead-id>"
    for outcome in '`resolved`' '`ambiguous`' '`unavailable`' '`not-found`'; do
        assert_contains "$file" "$outcome"
    done
    if code_lines "$file" | grep -Eq '^\s*bd (close|update|create|dep) '; then
        fail "$skill: unqualified mutating bd call in code; use bd -C <directory>"
    fi
    code_lines "$file" | grep -Eq '^\s*bd -C <directory> close ' || fail "$skill: close must use bd -C <directory>"
done

# Skills that create new work: store listing used and every create/dep in code qualified.
for skill in triage plan-to-backlog; do
    file="$ROOT_DIR/skills/$skill/SKILL.md"
    frontmatter "$file" | grep -Fq -- "Bash($RESOLVER:*)" || fail "$skill: resolver not in allowed-tools"
    assert_contains "$file" "$RESOLVER stores"
    assert_contains "$file" 'usable: false'
    if code_lines "$file" | grep -Eq '^\s*bd (close|update|create|dep|list|search) '; then
        fail "$skill: unqualified bd call in code; use bd -C <directory>"
    fi
done
assert_contains "$ROOT_DIR/skills/triage/SKILL.md" "$RESOLVER resolve <selector>"
assert_contains "$ROOT_DIR/skills/plan-to-backlog/SKILL.md" "$RESOLVER resolve <id>"

printf '%s\n' 'beads consumer routing tests passed'
