#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SKILL="$ROOT/skills/second-opinion/SKILL.md"
README="$ROOT/skills/second-opinion/README.md"
REFERENCE="$ROOT/skills/second-opinion/references/external-model-resolution.md"
FABLE_PROMPT="$ROOT/prompts/ask-fable.md"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

for file in "$SKILL" "$README" "$REFERENCE" "$FABLE_PROMPT"; do
  [[ -f "$file" ]] || fail "missing $file"
done

grep -Fq '/second-opinion ask "..." --agent claude --effort xhigh' "$SKILL" || \
  fail "skill does not document direct Claude effort"
grep -Fq 'accept direct `--effort low|medium|high|xhigh|max` only for the Claude route' "$SKILL" || \
  fail "skill does not validate direct Claude effort"
grep -Fq 'pass it through to Claude Code' "$SKILL" || \
  fail "skill does not execute direct Claude effort"
grep -Fq 'Direct Claude routes accept `--effort low|medium|high|xhigh|max`' "$README" || \
  fail "readme does not document direct Claude effort"
grep -Fq 'Explicit `--effort <level>` is supported only for a direct Claude route' "$REFERENCE" || \
  fail "model resolution reference does not define direct effort"
grep -Fq -- '--agent claude --model fable --effort xhigh' "$FABLE_PROMPT" || \
  fail "ask-fable does not request xhigh effort"

PR_CONTRACT="$ROOT/skills/second-opinion/references/pr-evidence.md"
for invariant in 'gh-pr-snapshot.py' 'reviewReady' 'headSha' 'baseSha' 'stateKey' 'nodeId' '--verify-only' '--expected-head' '--expected-base' '--expected-state-key' 'pwd -P' 'checkout.available' 'already matches' 'full collection' 'stale/unvalidated' 'partial' 'same sanitized packet' 'not OS-level isolation' 'Do not retry'; do
  grep -Fq -- "$invariant" "$PR_CONTRACT" || fail "missing immutable PR invariant: $invariant"
done
if grep -Eq 'gh pr (view|diff)|codex review --base' "$SKILL"; then
  fail 'second-opinion still assembles a mutable PR packet'
fi
grep -Fq 'references/pr-evidence.md' "$SKILL" || fail 'PR context contract must be mandatory'
grep -Fq 'All modes, including PR review' "$SKILL" || fail 'Codex must receive the actual packet'
grep -Fq 'no current PR assessment' "$SKILL" || fail 'stale external claims must not authorize a current assessment'
grep -Fq 'final revalidation **before** this section' "$SKILL" || fail 'PR stability must gate panel synthesis, not only the final assessment'
printf 'second-opinion skill contract tests passed\n'
