#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL="$SKILL_DIR/SKILL.md"
HUMAN="$SKILL_DIR/../triage/references/human-review.md"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
for invariant in \
    'Detailed plans are working input, not current architecture documentation.' \
    'validated `workspace.json` project-context index' \
    'do not require, create, repair, regenerate, or audit it' \
    'recommend `project-workspace doctor`' \
    'Do not create Markdown solely to preserve planning reasoning.' \
    'never creates or updates tracker records' \
    '/triage --human-review <source>' \
    'Do not invoke triage automatically' \
    'must not invoke `/plan-to-backlog` automatically'; do
    grep -Fq "$invariant" "$SKILL" || fail "missing architect invariant: $invariant"
done
if grep -Eq 'may mutate Beads|mutate Beads except|Bash\(git:\*\)|mcp__jira__\*|mcp__confluence__\*' "$SKILL"; then
    fail 'architect retains a write exception or blanket permission'
fi
brief=$(grep -nF '### Decision brief' "$SKILL" | head -1 | cut -d: -f1)
tier=$(grep -nF '### Planning tier' "$SKILL" | head -1 | cut -d: -f1)
((brief < tier)) || fail 'decision brief must precede planning detail'
for invariant in 'Exactly one blocked human review owner' 'existing matching review' 'source spike/design bead' 'canonical `human` label' 'status `blocked`' 'type `decision`' 'immediately before any tracker mutation' 'partial state' 'same item' '**Approve**' '**Defer or reject**' '**Request revision**' 'No implementation children' 'instruction-level'; do
    grep -Fq "$invariant" "$HUMAN" || fail "missing triage-owned decision invariant: $invariant"
done
grep -Fq 'references/human-review.md' "$SKILL_DIR/../triage/SKILL.md" || fail 'triage must own its explicit decision mode'
for invariant in 'human_review_source' 'mandatory' 'Unknown creation outcome' 'before any recovery create' 'retain that identity across revisions'; do
    grep -Fq "$invariant" "$HUMAN" || fail "missing decision recovery invariant: $invariant"
done
if grep -Eq 'Bash\(bd (create|update|close|dep):' "$SKILL_DIR/../triage/SKILL.md"; then
    fail 'triage preapproves a store-inferring mutation'
fi
grep -Fq 'Bash(bd -C * create:*)' "$SKILL_DIR/../triage/SKILL.md" || fail 'triage writes must use the proven store'
printf '%s\n' 'architect read-only handoff contract tests passed'
