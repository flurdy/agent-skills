#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL_DIR=$(dirname -- "$TEST_DIR")
REPO_ROOT=$(CDPATH='' cd -- "$SKILL_DIR/../.." && pwd -P)
SKILL="$SKILL_DIR/SKILL.md"
ARCHITECT="$REPO_ROOT/skills/architect/SKILL.md"
TRIAGE="$REPO_ROOT/skills/triage/SKILL.md"
CATALOG="$REPO_ROOT/skills/README.md"
MAKEFILE="$REPO_ROOT/Makefile"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_contains() {
    local file=$1 expected=$2
    grep -Fq -- "$expected" "$file" || fail "expected '$expected' in $file"
}

assert_not_contains() {
    local file=$1 unexpected=$2
    if grep -Fq -- "$unexpected" "$file"; then
        fail "did not expect '$unexpected' in $file"
    fi
}

line_of() {
    local file=$1 heading=$2
    grep -nF -- "$heading" "$file" | head -1 | cut -d: -f1
}

[[ -f "$SKILL" ]] || fail "missing plan-to-backlog skill"

assert_contains "$SKILL" 'disable-model-invocation: true'
assert_contains "$SKILL" 'Proposal-first. May recommend no backlog change. Never writes without confirmation.'

frontmatter=$(awk 'NR == 1 { next } /^---$/ { exit } { print }' "$SKILL")
for permission in \
    'Bash(bd status:*)' \
    'Bash(bd list:*)' \
    'Bash(bd search:*)' \
    'Bash(bd show:*)' \
    'Bash(bd children:*)' \
    'Bash(~/.agents/skills/plan-to-backlog/scripts/utc-now.sh:*)' \
    'Bash(~/.agents/skills/plan-to-backlog/scripts/sha256-stdin.sh:*)' \
    'Bash(~/.agents/skills/plan-to-backlog/scripts/confirmed-bd.sh:*)'; do
    grep -Fq -- "$permission" <<<"$frontmatter" || fail "missing permission $permission"
done
for forbidden in \
    'Write' \
    'Bash(rm:*)' \
    'Bash(chmod:*)' \
    'Bash(date:*)' \
    'Bash(bd:*)' \
    'Bash(bd create:*)' \
    'Bash(bd update:*)' \
    'Bash(bd dep add:*)' \
    'Bash(bd close:*)' \
    'Bash(bd delete:*)' \
    'Bash(bd supersede:*)' \
    'Bash(bd promote:*)'; do
    if grep -Fq -- "$forbidden" <<<"$frontmatter"; then
        fail "unsafe or overly broad permission $forbidden"
    fi
done

proposal_line=$(line_of "$SKILL" '## Render the proposal')
confirmation_line=$(line_of "$SKILL" '## Confirm the exact proposal')
apply_line=$(line_of "$SKILL" '## Apply the confirmed proposal')
[[ -n "$proposal_line" && -n "$confirmation_line" && -n "$apply_line" ]] || \
    fail "proposal, confirmation, and apply sections must exist"
((proposal_line < confirmation_line && confirmation_line < apply_line)) || \
    fail "proposal and confirmation must precede apply"

for invariant in \
    'Never create one bead per plan step.' \
    'readiness: ready | needs-clarification' \
    'disposition: no-item | single-item | epic' \
    'proposalVersion' \
    'generatedAt' \
    'utf8-lf-final-newline-v1' \
    'stable proposal refs' \
    'ledger-based reference resolution' \
    'Nothing has been changed.' \
    'proposal fingerprint' \
    'bd create --dry-run' \
    'bd update --type epic' \
    'rerun every source, locator, outcome, owner, and duplicate query' \
    'Run each preflight only immediately before' \
    'Declining, abandoning, or answering ambiguously performs no writes.' \
    'stop before operations that depend on the failed result' \
    'must never create a second tree'; do
    assert_contains "$SKILL" "$invariant"
done

assert_not_contains "$SKILL" 'plan_proposal_sha256'
assert_contains "$ARCHITECT" '/plan-to-backlog <plan-source>'
assert_contains "$ARCHITECT" 'must not invoke `/plan-to-backlog` automatically'
assert_not_contains "$TRIAGE" 'Skill(plan-to-backlog)'
assert_contains "$TRIAGE" 'paste-ready `/plan-to-backlog <plan-source>` handoff'
assert_contains "$TRIAGE" 'Do not classify plan children or create beads first.'
assert_not_contains "$TRIAGE" '/triage plan'
assert_contains "$CATALOG" '| plan-to-backlog |'
assert_contains "$CATALOG" 'approved plan'
assert_contains "$CATALOG" 'no-item/single-item/epic'
assert_contains "$CATALOG" 'explicit confirmation before writes'
assert_contains "$MAKEFILE" 'test-plan-to-backlog:'

printf '%s\n' 'plan-to-backlog contract tests passed'
