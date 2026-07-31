#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL="$TEST_DIR/../SKILL.md"

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

[[ -f "$SKILL" ]] || fail "missing watch-pr-feedback skill"

for invariant in \
    'name: watch-pr-feedback' \
    'Default read-only mode' \
    'Attended mode' \
    '## Tick mode' \
    'gh-pr-list-open.sh' \
    'gh-pr-feedback.py' \
    'gh-pr-feedback.py OWNER REPO PR_NUMBER' \
    '--identity IDENTITY --expected-update-key UPDATE_KEY' \
    '`selection.status` is `matched`' \
    'never invoke `gh api` directly' \
    'gh-pr-checkout.py OWNER/REPO HEAD_SHA' \
    'The helper alone may enumerate registered workspace members and Git worktrees.' \
    'Never run ad-hoc shell/workspace probes' \
    'one call per `owner/repo` group' \
    '`repository`, PR number, and `identity`' \
    '`updateKey`' \
    '`stateKey`' \
    '500 identities' \
    '`state-capacity` partial' \
    'first tick' \
    'same session' \
    '`reset`' \
    '`recheck`' \
    'new session' \
    'context loss' \
    'no-change' \
    'Quiet tick — checked {N} PRs; {M} tracked feedback records unchanged.' \
    'Do not render empty **Decision queue**' \
    'internal ledger terminology' \
    'Omit normal identity counts, acknowledgment totals, healthy limits' \
    'silent ledger updates' \
    'only for a lifecycle-only transition' \
    'Show partial status only when data is partial' \
    'do not print healthy defaults' \
    '`inventories complete`, `partial: false`, or empty errors' \
    'summary** only for pending attended feedback' \
    'a non-zero failure streak' \
    'lost ledger continuity' \
    'final visible text' \
    'do not follow' \
    'decision recap' \
    'Keep healthy internal ledger and fetch state silent' \
    'Only a non-baseline, non-recheck tick with complete inventories' \
    'exclusively unchanged duplicate records' \
    'no lifecycle transitions, pending candidates, capacity/pruning notices, or failures' \
    'lifecycle transitions,' \
    'capacity/pruning notices remain.' \
    'non-baseline cold tick that meets the stricter quiet predicate' \
    'materially edited' \
    'lifecycle-only' \
    'resolved' \
    'outdated' \
    'self-authored' \
    'automated-status' \
    'confirmed defect' \
    'valid improvement' \
    'question needing an answer' \
    'subjective/trade-off decision' \
    'false positive/already handled' \
    'stale/outdated' \
    'materially distinct sub-claim' \
    'mixed — see claim breakdown' \
    'Never label the whole record `stale/outdated` unless' \
    'more than five distinct claims' \
    'out of scope' \
    'unable to validate' \
    'confidence' \
    'evidence' \
    'recommended response' \
    'matching clean checkout' \
    'PR diff' \
    'requirements' \
    'existing tests' \
    'CI' \
    'partial' \
    'Do not mark absent records' \
    'three consecutive' \
    'multiple repositories' \
    'never prompts' \
    'asks exactly once' \
    '`AskUserQuestion`' \
    'Open attended workflow (Recommended)' \
    '/review-comments owner/repo#number' \
    'Acknowledge' \
    'Recheck next tick' \
    'Stop watcher' \
    '### Pi protocol v1' \
    'current harness directly exposes `watch_loop`' \
    'In Claude Code, enter this branch directly' \
    'the shell to detect another harness or executable.' \
    'capability probes or commentary' \
    'protocolVersion: 1' \
    'action: status' \
    'action: start' \
    'action: complete' \
    '`armed`, `running`, or `paused`' \
    'mode: adaptive' \
    'mode: fixed' \
    'initialDelaySeconds: 60' \
    'intervalSeconds' \
    'missedCompletionPolicy: retry' \
    'missedCompletionPolicy: pause' \
    'stopAt' \
    '60–3600 seconds' \
    '### Claude Code fallback' \
    'ScheduleWakeup' \
    'final tool action with N' \
    'sole post-tool text and ends immediately' \
    'Fixed ticks ignore `next-tick:` for scheduling' \
    'Fable' \
    '/loop' \
    'next-tick:'; do
    assert_contains "$invariant"
done

tick_prompt=$(grep -F -- 'Load and follow the skill named `watch-pr-feedback`' "$SKILL")
for prompt_invariant in \
    'two to five materially distinct sub-claims' \
    'validate each claim' \
    'use `mixed — see claim breakdown` only when outcomes differ' \
    'never mark the whole record stale unless every actionable claim is stale' \
    'For more than five claims, use `unable to validate`' \
    'recommend the attended workflow' \
    'keep routine suppressions silent' \
    'only user-relevant lifecycle/disposition suppressions and actual failures' \
    'mention partial status only when partial' \
    'State summary only for pending attended feedback' \
    'non-zero failure streak, or lost ledger continuity' \
    'Keep healthy internal ledger and fetch state silent' \
    'do not print `inventories complete`, `partial: false`, or empty errors' \
    'Never add a prose recap after the final cadence line'; do
    grep -Fq -- "$prompt_invariant" <<<"$tick_prompt" \
        || fail "tick prompt missing output invariant: $prompt_invariant"
done
[[ "$tick_prompt" != *'suppression/failure summary'* ]] \
    || fail 'tick prompt retains obsolete broad suppression-summary instruction'

pi_line=$(line_of '### Pi protocol v1')
claude_line=$(line_of '### Claude Code fallback')
[[ -n "$pi_line" && -n "$claude_line" ]] || fail 'Pi and Claude capability sections must exist'
((pi_line < claude_line)) || fail 'Pi capability branch must precede Claude fallback'

assert_not_contains 'allowIndefinite: true'
assert_not_contains 'gh pr checkout'
assert_not_contains 'git push'
assert_not_contains 'git commit'
assert_not_contains 'resolveReviewThread'
assert_not_contains 'command -v pi'
head -n 12 "$SKILL" | grep -Fq -- 'Bash(gh api' \
    && fail 'watch-pr-feedback must not allow direct gh api access'
assert_not_contains 'Bash(git'
assert_not_contains 'for d in'

printf '%s\n' 'watch-pr-feedback contract tests passed'
