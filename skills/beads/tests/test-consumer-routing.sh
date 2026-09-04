#!/usr/bin/env bash
# Every skill that reads or writes an existing bead must route through the shared
# resolver and qualify its bd calls with the proven owning store.
set -euo pipefail
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
# shellcheck disable=SC2088  # literal text asserted in SKILL.md, never expanded
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

# Read-only consumers handed a bead ID: resolver allowed and used, reads qualified.
for skill in delegate-work diagnose-bug; do
    file="$ROOT_DIR/skills/$skill/SKILL.md"
    frontmatter "$file" | grep -Fq -- "Bash($RESOLVER:*)" || fail "$skill: resolver not in allowed-tools"
    assert_contains "$file" "$RESOLVER resolve <id>"
    assert_contains "$file" 'bd -C <directory> show <id>'
    assert_contains "$file" 'never infer the store from the ID or the cwd'
done

# Portfolio reader: every store enumerated, every read qualified, unusable stores surfaced.
file="$ROOT_DIR/skills/tracking-sweep/SKILL.md"
frontmatter "$file" | grep -Fq -- "Bash($RESOLVER:*)" || fail "tracking-sweep: resolver not in allowed-tools"
assert_contains "$file" "$RESOLVER stores"
assert_contains "$file" 'usable: false'
if code_lines "$file" | grep -Eq '^\s*bd (list|show|memories|ready|stale|orphans)\b'; then
    fail "tracking-sweep: unqualified bd read in code; use bd -C <directory>"
fi

# Script-driven consumer: the owning store is proven and every bd call goes through it.
trello="$ROOT_DIR/skills/trello-beads"
assert_contains "$trello/SKILL.md" 'fail closed before any Trello request or `bd` call'
for script in trello-pull.sh trello-sync.sh; do
    assert_contains "$trello/scripts/$script" 'source "$SCRIPT_DIR/owning-store.sh"'
    assert_contains "$trello/scripts/$script" 'require_owning_store'
    if grep -Eq '\$\(bd ' "$trello/scripts/$script"; then
        fail "$script: bare bd call; use bd_store"
    fi
done
assert_contains "$trello/scripts/owning-store.sh" 'bd -C "$BEADS_STORE_DIR"'

printf '%s\n' 'beads consumer routing tests passed'
