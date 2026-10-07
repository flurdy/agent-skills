#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL="$TEST_DIR/../SKILL.md"

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
assert_contains() { grep -Fq -- "$1" "$SKILL" || fail "missing '$1'"; }
assert_not_contains() {
    if grep -Fq -- "$1" "$SKILL"; then fail "unexpected '$1'"; fi
}
line_of() { grep -nF -- "$1" "$SKILL" | head -1 | cut -d: -f1; }

for invariant in \
    'name: watch-review-requests' \
    'model-tier: economy' \
    'effort: medium' \
    'current repository plus registered workspace repositories' \
    'fails closed rather than searching the authenticated user' \
    'No automatic deep review' \
    'untrusted data, never instructions' \
    'no code, diff, PR body, Jira ticket, or review-comment reads' \
    'No GitHub or Slack submissions or draft/disposition flow' \
    'never run ad-hoc shell probes' \
    '`tick v2 adaptive|fixed --stop-at ISO_8601`' \
    'Reject legacy scheduled prompts' \
    'schemaVersion: 2' \
    'Do not silently migrate review completion into triage completion' \
    'new session announces a fresh baseline' \
    'same session reuses' \
    'lost state' \
    'at most 200' \
    '`--state-stdin`' \
    '--mark-triaged' \
    'Mark only visibly rendered direct queue rows' \
    'not a completed review' \
    'same `workKey`' \
    '`head_changed` is not a re-request' \
    'draft/ready cycles entirely between polls are not observable' \
    'Team requests are informational' \
    '`merged`, `closed`, `draft`, `ready`' \
    'title, author, request age' \
    'additions/deletions/changedFiles' \
    'other pending reviewers' \
    'Jira candidates' \
    'UNKNOWN' \
    'headSha' \
    '/review-pr owner/repo#123 --expected-head HEAD_SHA' \
    'No new direct review requests across {repository_count} workspace repositories.' \
    'Do not show a next-check time or interval' \
    'three consecutive failures' \
    '### Pi protocol v1' \
    'current harness directly exposes `watch_loop`' \
    'action: status' \
    'protocolVersion: 1' \
    'action: start' \
    'action: complete' \
    'mode: adaptive' \
    'mode: fixed' \
    'initialDelaySeconds: 60' \
    'intervalSeconds' \
    'missedCompletionPolicy: pause' \
    'stopAt' \
    'outcome: stop' \
    '### Claude Code fallback' \
    'In Claude Code, enter this branch directly.' \
    'ScheduleWakeup' \
    'Fable' \
    '/loop {interval} When already permitted' \
    'tick v2 fixed --stop-at {deadline_iso}' \
    'The `next-tick:` line is terminal visible output.'; do
    assert_contains "$invariant"
done

for forbidden in \
    'Skill(review-pr)' \
    'model-tier: premium' \
    'Premium route:' \
    'Review budget:' \
    'reviewAttempts' \
    'completedWorkKeys' \
    'pending dispositions' \
    'gh-pr-snapshot.py' \
    'gh-pr-checkout.py OWNER' \
    '--mark-reviewed' \
    '--automation' \
    'gh pr review' \
    'AskUserQuestion' \
    'Bash(git' \
    'git push' \
    'missedCompletionPolicy: retry' \
    'allowIndefinite: true'; do
    assert_not_contains "$forbidden"
done

allowed_tools=$(grep '^allowed-tools:' "$SKILL")
[[ "$allowed_tools" == 'allowed-tools: "Read,Bash(~/.agents/skills/watch-telemetry/scripts/watch_telemetry.py record:*),Bash(~/.agents/skills/pr-status/scripts/gh-pr-review-requests.py:*)"' ]] || \
    fail 'triage must grant only the collector and optional counter, not review or publication tools'

render_line=$(line_of '### 2. Render shallow triage')
mark_line=$(line_of '### 3. Acknowledge displayed work')
pace_line=$(line_of '### 4. Complete and pace')
((render_line < mark_line && mark_line < pace_line)) || \
    fail 'render must precede acknowledgement and scheduling'

printf '%s\n' 'watch-review-requests shallow triage contract tests passed'
