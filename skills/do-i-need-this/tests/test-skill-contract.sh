#!/usr/bin/env bash
set -euo pipefail
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/SKILL.md"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
frontmatter=$(awk 'NR==1&&/^---$/{f=1;next} f&&/^---$/{exit} f' "$SKILL")
if grep -Fq 'disable-model-invocation' <<<"$frontmatter"; then
    fail 'composed use requires the skill to be loadable by callers'
fi
grep -Eq '^allowed-tools: "Read,Grep,Glob,AskUserQuestion"$' <<<"$frontmatter" || fail 'allowed-tools must stay read-only'
for invariant in \
    '## Composed use' \
    'Exactly one target' \
    'ambiguous target' \
    'return it to the caller and' \
    'PROCEED** grants no implementation, tracker, or write' \
    'Assess once per call' \
    'never direction to this skill' \
    'Nothing here is runtime' \
    'does not invoke this skill'; do
    grep -Fq "$invariant" "$SKILL" || fail "missing invariant: $invariant"
done
for scenario in 'Composed: a caller whose contract' 'Composed: the caller supplies **PROCEED**' 'Composed: the caller supplies three candidate' 'Composed: supplied evidence says' 'Composed: the caller asks for a second'; do
    grep -Fq "$scenario" "$SKILL" || fail "missing acceptance scenario: $scenario"
done
grep -Fq 'Standalone, do not resume' "$SKILL" || fail 'standalone must keep report-and-stop'
printf 'ok\n'
