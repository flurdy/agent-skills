#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL_DIR=$(dirname -- "$TEST_DIR")
SKILL="$SKILL_DIR/SKILL.md"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_contains() {
    local expected=$1
    grep -Fq -- "$expected" "$SKILL" || fail "expected '$expected' in $SKILL"
}

assert_not_contains() {
    local unexpected=$1
    if grep -Fq -- "$unexpected" "$SKILL"; then
        fail "did not expect '$unexpected' in $SKILL"
    fi
}

line_of() {
    local heading=$1
    grep -nF -- "$heading" "$SKILL" | head -1 | cut -d: -f1
}

[[ -f "$SKILL" ]] || fail "missing watch-rollout skill"

for invariant in \
    '### Pi protocol v1' \
    '`watch_loop` is available' \
    'protocolVersion: 1' \
    'action: status' \
    'action: start' \
    '`armed`, `running`, or `paused`' \
    '/watch-status' \
    '/watch-stop' \
    '/watch-resume' \
    'action: complete' \
    'action: stop' \
    'mode: fixed' \
    'initialDelaySeconds: 60' \
    'intervalSeconds: 240' \
    'missedCompletionPolicy: retry' \
    'maxTicks: 30' \
    'outcome: continue' \
    'outcome: stop' \
    'in_progress, waiting, queued, or not yet started' \
    'Load and follow the skill named `watch-rollout` now.' \
    'run-jobs.sh {run_id}' \
    '### Claude Code fallback' \
    '/loop Watch GitHub Actions run {run_id}' \
    'If neither `watch_loop` nor `/loop` is available' \
    'Never re-trigger, cancel, re-run, or approve a workflow; never deploy.'; do
    assert_contains "$invariant"
done

smoke_line=$(line_of '### Phase 3 — Derive the smoke test (derive + confirm)')
pi_line=$(line_of '### Pi protocol v1')
claude_line=$(line_of '### Claude Code fallback')
[[ -n "$smoke_line" && -n "$pi_line" && -n "$claude_line" ]] || \
    fail "smoke confirmation, Pi, and Claude sections must exist"
((smoke_line < pi_line && pi_line < claude_line)) || \
    fail "smoke confirmation must precede the Pi and Claude scheduling branches"

assert_not_contains '/skill:watch-rollout'
assert_not_contains 'allowIndefinite: true'

printf '%s\n' 'watch-rollout protocol contract tests passed'
