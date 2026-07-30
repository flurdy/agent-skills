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

[[ -f "$SKILL" ]] || fail "missing watch-prs skill"

for invariant in \
    'default `18`' \
    'at or past' \
    '### Pi protocol v1' \
    '`watch_loop` is available' \
    'protocolVersion: 1' \
    'action: status' \
    'action: start' \
    '`armed`, `running`, or `paused`' \
    '`watch_loop complete`' \
    'action: complete' \
    '`watch_loop stop`' \
    'action: stop' \
    'mode: adaptive' \
    'mode: fixed' \
    'initialDelaySeconds: 60' \
    'intervalSeconds' \
    'delaySeconds' \
    'missedCompletionPolicy: retry' \
    'stopAt' \
    '60–3600 seconds' \
    'Load and follow the skill named `pr-status` now.' \
    'Do not execute any suggested action.' \
    '`next-tick:`' \
    '/watch-status' \
    '/watch-stop' \
    '### Claude Code fallback' \
    'ScheduleWakeup' \
    '/loop {interval} /pr-status' \
    'Fable'; do
    assert_contains "$invariant"
done

pi_line=$(line_of '### Pi protocol v1')
claude_line=$(line_of '### Claude Code fallback')
guard_line=$(line_of '**Session-model guard (adaptive mode only).**')
[[ -n "$pi_line" && -n "$claude_line" && -n "$guard_line" ]] || \
    fail "Pi, Claude, and Fable-guard sections must exist"
((pi_line < claude_line && claude_line < guard_line)) || \
    fail "capability probe must precede the Claude-only Fable guard"

assert_not_contains '/skill:pr-status'
assert_not_contains 'allowIndefinite: true'

printf '%s\n' 'watch-prs protocol contract tests passed'
