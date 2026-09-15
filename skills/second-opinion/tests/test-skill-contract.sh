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
for file in "$SKILL" "$README" "$REFERENCE"; do
  for setting in 'reasoning.effort' 'maxOutputTokens' '16,000'; do
    grep -Fq "$setting" "$file" || fail "missing OpenRouter setting $setting in $file"
  done
done
for setting in effectiveMaxOutputTokens effectiveEffort maxOutputTokensTotal; do
  grep -Fq "$setting" "$SKILL" || fail "consent disclosure omits $setting"
done
for invariant in 'review-subscription-policy' 'claude auth status --json' 'Logged in using ChatGPT' 'API override' 'billing prompt'; do
  grep -Fq -- "$invariant" "$SKILL" || fail "missing stable subscription policy invariant: $invariant"
done
for brittle in 'direct-route.py' 'cliPath' 'cliVersion' 'allowedModelUsage'; do
  ! grep -Fq -- "$brittle" "$SKILL" || fail "skill retains brittle route binding: $brittle"
done
PLAN_CONTRACT="$ROOT/skills/second-opinion/references/guarded-plan.md"
[[ -f "$PLAN_CONTRACT" ]] || fail 'missing guarded-plan support matrix'
for invariant in 'unsupported' 'file-only' 'before creating' 'Do not emulate' 'inherited cwd' 'async-only' 'billing' 'incomplete' '0.85.1' '0.67.0'; do
  grep -Fq -- "$invariant" "$PLAN_CONTRACT" || fail "missing guarded-plan invariant: $invariant"
done
python3 - "$SKILL" <<'PY'
import pathlib
import sys
text = pathlib.Path(sys.argv[1]).read_text()
preflight = text.index('## Guarded-session preflight')
assert preflight < text.index('## 2. Gather and sanitize context')
assert 'references/guarded-plan.md' in text[preflight:text.index('## 2. Gather and sanitize context')]
PY
printf 'second-opinion skill contract tests passed\n'
