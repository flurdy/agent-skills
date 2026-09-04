#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
ROOT_DIR=$(CDPATH='' cd -- "$TEST_DIR/../../.." && pwd -P)
DISPATCHER="$ROOT_DIR/skills/watch-rollout/SKILL.md"
ACTIONS="$ROOT_DIR/skills/watch-actions-rollout/SKILL.md"
FLUX="$ROOT_DIR/skills/watch-flux-rollout/SKILL.md"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_contains() {
    local file=$1
    local expected=$2
    grep -Fq -- "$expected" "$file" || fail "expected '$expected' in $file"
}

assert_not_contains() {
    local file=$1
    local unexpected=$2
    if grep -Fq -- "$unexpected" "$file"; then
        fail "did not expect '$unexpected' in $file"
    fi
}

[[ -f "$DISPATCHER" ]] || fail "missing watch-rollout dispatcher"
[[ -f "$ACTIONS" ]] || fail "missing watch-actions-rollout implementation"
[[ -f "$FLUX" ]] || fail "missing watch-flux-rollout implementation"

for invariant in \
    'name: watch-rollout' \
    'AskUserQuestion' \
    'Skill(watch-actions-rollout)' \
    'Skill(watch-flux-rollout)' \
    '/watch-rollout actions' \
    '/watch-rollout github' \
    '/watch-rollout flux' \
    '| `actions`, `github`, `github-actions` | `watch-actions-rollout` |' \
    '| `flux`, `circleci-flux` | `watch-flux-rollout` |' \
    'Always ask when no explicit stack selector is supplied.' \
    'Forward all remaining arguments unchanged.' \
    'Invoke the mapped skill immediately without prompting.'; do
    assert_contains "$DISPATCHER" "$invariant"
done

assert_not_contains "$DISPATCHER" 'watch_loop'
assert_not_contains "$DISPATCHER" 'Bash('
assert_contains "$ACTIONS" 'name: watch-actions-rollout'
assert_contains "$FLUX" 'name: watch-flux-rollout'

printf '%s\n' 'watch-rollout dispatcher contract tests passed'
