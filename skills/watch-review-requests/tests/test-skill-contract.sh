#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL="$TEST_DIR/../SKILL.md"
REVIEW_PR="$TEST_DIR/../../review-pr/SKILL.md"

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
    local text=$1
    grep -nF -- "$text" "$SKILL" | head -1 | cut -d: -f1
}

[[ -f "$SKILL" ]] || fail "missing watch-review-requests skill"

for invariant in \
    'name: watch-review-requests' \
    'model-tier: premium' \
    'effort: xhigh' \
    'gh-pr-review-requests.py' \
    '/review-pr owner/repo#123 --automation --premium-established' \
    '--expected-head' \
    '--deadline-seconds' \
    'gh-pr-snapshot.py' \
    '--expected-base' \
    '--expected-state-key' \
    '--verify-only' \
    'one review at a time' \
    'No new actionable direct review requests.' \
    'session-local' \
    '`completedWorkKeys`' \
    '`reviewAttempts`' \
    '`review-complete`' \
    '`verified-unmarked`' \
    '`pending-capacity`' \
    '20 pending dispositions' \
    'default `3`' \
    '1 through 20' \
    'Premium route:' \
    'Stop deadline:' \
    'Review budget:' \
    '{cadence_mode}' \
    '{deadline_iso}' \
    '{review_budget}' \
    '{premium_route}' \
    'remaining review count' \
    'at least 30 seconds' \
    '`reset`' \
    '`recheck owner/repo#123`' \
    '`disposition owner/repo#123`' \
    '`status`' \
    '`tick adaptive|fixed --reviews N --stop-at ISO_8601`' \
    'same session' \
    'new session' \
    'Draft requests wait' \
    'team requests' \
    '`re_requested`' \
    '`head_changed`' \
    'failed' \
    'interrupted' \
    'partial' \
    'stale' \
    'three consecutive' \
    'report-rendered checkpoint' \
    '--mark-reviewed' \
    '`AskUserQuestion`' \
    'Keep private (Recommended)' \
    'Prepare GitHub draft' \
    'Prepare Slack draft' \
    'Defer' \
    'Approve' \
    'Comment' \
    'Request changes' \
    'Rerun current head (Recommended)' \
    'Keep draft (Recommended)' \
    'Submit now' \
    'Send now' \
    'No external action' \
    'exact destination' \
    'gh pr review' \
    '--repo OWNER/REPO' \
    '### Pi protocol v1' \
    'current harness directly exposes `watch_loop`' \
    'In Claude Code, enter this branch directly.' \
    'the shell to detect another harness or executable.' \
    'do not include Pi capability commentary' \
    'protocolVersion: 1' \
    'action: status' \
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
    'ScheduleWakeup' \
    '/loop {interval} /watch-review-requests tick fixed --reviews {N} --stop-at {deadline_iso}' \
    'Fable' \
    'next-tick:'; do
    assert_contains "$invariant"
done

report_line=$(line_of 'Render the complete review report')
verify_line=$(line_of 'Reverify after rendering')
mark_line=$(line_of 'Mark locally reviewed')
prompt_line=$(line_of 'Ask for disposition')
[[ -n "$report_line" && -n "$verify_line" && -n "$mark_line" && -n "$prompt_line" ]] || \
    fail 'missing review checkpoint headings'
((report_line < verify_line && verify_line < mark_line && mark_line < prompt_line)) || \
    fail 'report, verification, local completion, and disposition must remain ordered'

allowed_tools=$(grep -F 'allowed-tools:' "$SKILL" | head -1)
[[ "$allowed_tools" == *'Skill(review-pr)'* ]] || \
    fail 'watcher must be able to invoke only review-pr'

capacity_line=$(line_of 'dispositions are retained, do not start or mark another review')
review_line=$(line_of '### 4. Invoke the immutable review')
[[ -n "$capacity_line" && -n "$review_line" && "$capacity_line" -lt "$review_line" ]] || \
    fail 'pending capacity must gate review execution'

recover_verified_line=$(line_of '1. `verified-unmarked`')
recover_rendered_line=$(line_of '2. `report-rendered`')
recover_complete_line=$(line_of '3. `review-complete`')
recover_analyzing_line=$(line_of '4. `analyzing`')
[[ -n "$recover_verified_line" && -n "$recover_rendered_line" && \
   -n "$recover_complete_line" && -n "$recover_analyzing_line" ]] || \
    fail 'missing phase-specific interruption recovery'
((recover_verified_line < recover_rendered_line && \
  recover_rendered_line < recover_complete_line && \
  recover_complete_line < recover_analyzing_line)) || \
    fail 'in-flight phases must recover without duplicate analysis'

accepted_line=$(line_of 'Immediately after accepting a complete automation result')
render_heading_line=$(line_of '### 5. Render the complete review report')
[[ -n "$accepted_line" && -n "$render_heading_line" && "$accepted_line" -lt "$render_heading_line" ]] || \
    fail 'complete automation result must persist before rendering'

pending_line=$(line_of 'Before collector marking, create or replace')
reducer_line=$(line_of 'Run the local state reducer')
completed_line=$(line_of 'add `workKey` to `completedWorkKeys`')
[[ -n "$pending_line" && -n "$reducer_line" && -n "$completed_line" ]] || \
    fail 'missing idempotent local-completion transaction'
((pending_line < reducer_line && reducer_line < completed_line)) || \
    fail 'pending record, reducer mark, and completed key must remain ordered'

answer_verify_line=$(line_of 'When the answer returns')
github_kind_line=$(line_of 'ask a second single-select question with **Approve**')
[[ -n "$answer_verify_line" && -n "$github_kind_line" ]] || \
    fail 'missing stale-before-disposition gate'
((answer_verify_line < github_kind_line)) || \
    fail 'immutable state must be checked after the open prompt and before GitHub kinds'

submit_verify_line=$(line_of 'Submit now answer returns')
github_send_line=$(line_of 'gh pr review PR_NUMBER --repo OWNER/REPO')
[[ -n "$submit_verify_line" && -n "$github_send_line" ]] || \
    fail 'missing post-final-prompt GitHub verification'
((submit_verify_line < github_send_line)) || \
    fail 'final confirmation answer must be reverified immediately before GitHub submission'

stale_retire_line=$(line_of 'retire the old pending record')
stale_repeat_line=$(line_of 'repeat the serial flow against its new exact head')
[[ -n "$stale_retire_line" && -n "$stale_repeat_line" ]] || \
    fail 'missing stale-rerun pending retirement'
((stale_retire_line < stale_repeat_line)) || \
    fail 'stale pending record must retire before same-PR rerun'

for review_field in \
    '"reason"' \
    '"changesOverview"' \
    '"checkoutReason"' \
    '"jiraKey"' \
    '"jiraSummary"'; do
    grep -Fq -- "$review_field" "$REVIEW_PR" || \
        fail "review-pr automation contract missing $review_field"
done

assert_contains 'a per-run `completedWorkKeys` set for exactly-once successful reports, reset with'
assert_contains 'capped by the 1–20 attempt budget'
assert_contains 'increment `reviewAttempts` immediately before invoking'
assert_contains 'Every premium invocation consumes one attempt'
assert_contains 'Zero remaining attempts blocks only a'
assert_contains 'new `Skill(review-pr)` invocation: a retained or newly returned complete result'
assert_contains 'review budget exhaustion after the current complete result and disposition finish'
assert_contains 'retains its exact kind, body, quoted heredoc command'
assert_contains 'reopening resumes at **Verify for submission**'
assert_contains 'reopening shows Keep private or Keep draft only'
assert_contains 'not automatically prompted on later ticks'
assert_contains 'removes the pending record; a failed attempt retains it as `github-draft`'
assert_contains 'quoted high-entropy heredoc delimiter absent from the body'
assert_contains '`--body-file -` preserves the shown body as one value'
assert_contains 'has no Slack send tool or Skill permission and never sends'
assert_contains 'a draft remains non-actionable'
assert_contains 'Never attempt to unmark collector state.'

assert_not_contains 'missedCompletionPolicy: retry'
assert_not_contains 'allowIndefinite: true'
assert_not_contains 'gh pr checkout'
assert_not_contains 'git push'
assert_not_contains 'git commit'
assert_not_contains 'resolveReviewThread'
assert_not_contains 'command -v pi'
assert_not_contains "--body 'EXACT_SHOWN_BODY'"
assert_not_contains 'mcp__jira__'
assert_not_contains 'unless selected by an explicit qualified recheck'

printf '%s\n' 'watch-review-requests scenario contract tests passed'
