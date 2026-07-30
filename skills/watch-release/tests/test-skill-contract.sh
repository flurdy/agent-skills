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

[[ -f "$SKILL" ]] || fail "missing watch-release skill"

for invariant in \
    'positive interval matching `\d+m`' \
    'stop hour from `0` through `23`' \
    'Default: `18`' \
    'at or past' \
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
    'mode: adaptive' \
    'mode: fixed' \
    'initialDelaySeconds: 60' \
    'intervalSeconds' \
    'missedCompletionPolicy: pause' \
    'stopAt' \
    'delaySeconds' \
    '600' \
    'Load and follow the skill named `release-manager` now.' \
    'blocks the active tick until the user answers' \
    'Never push, sync config, or restart a deployment without the explicit answer' \
    '`next-tick:`' \
    '### Claude Code fallback' \
    'ScheduleWakeup' \
    '/loop {interval} /release-manager' \
    'If neither `watch_loop` nor the required' \
    'Claude scheduling capability is available'; do
    assert_contains "$invariant"
done

pi_line=$(line_of '### Pi protocol v1')
claude_line=$(line_of '### Claude Code fallback')
[[ -n "$pi_line" && -n "$claude_line" ]] || fail "Pi and Claude sections must exist"
((pi_line < claude_line)) || fail "Pi capability branch must precede the Claude fallback"

assert_not_contains '/skill:release-manager'
assert_not_contains 'missedCompletionPolicy: retry'
assert_not_contains 'allowIndefinite: true'

printf '%s\n' 'watch-release protocol contract tests passed'
