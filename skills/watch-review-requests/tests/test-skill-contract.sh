#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL="$TEST_DIR/../SKILL.md"
SUMMARY="$TEST_DIR/../../pr-review-requests/SKILL.md"

python3 - "$SKILL" "$SUMMARY" <<'PY'
from pathlib import Path
import sys

watch = Path(sys.argv[1]).read_text()
for invariant in (
    'name: watch-review-requests', 'model-tier: economy', 'effort: medium',
    'Skill(pr-review-requests)', '### Pi protocol v1', 'protocolVersion: 1',
    'action: status', 'action: start', 'action: complete',
    '`armed`, `running`, or `paused`', 'mode: adaptive', 'mode: fixed',
    'initialDelaySeconds: 60', 'intervalSeconds', 'missedCompletionPolicy: pause',
    'stopAt', '60–3600 seconds', '/watch-status', '/watch-stop', '/watch-resume',
    'Load and follow the skill named `pr-review-requests` now.',
    'Do not execute any suggested action.', '### Claude Code fallback',
    'ScheduleWakeup', '/loop {interval} When already permitted',
    '/loop When already permitted', 'Fable', 'default `18`', 'at or past',
    'session-local', 'state is lost', 'stop rather than', 'next-tick:',
    'sole local-write exception', 'never stores feedback, queue state, or review content',
    'Reject legacy scheduled prompts', 'request-dashboard-v1', 'watchId/generation',
    'pending display', 'commit comparison state only after rendering',
):
    assert invariant in watch, f'missing watcher invariant: {invariant}'
for forbidden in ('Skill(review-pr)', 'gh pr review', 'AskUserQuestion', '--reviews',
                  'Premium route:', 'reviewAttempts', 'pending dispositions',
                  '--mark-reviewed', 'gh-pr-snapshot.py', 'allowIndefinite: true',
                  'Bash(git', 'Bash(gh', 'missedCompletionPolicy: retry'):
    assert forbidden not in watch, f'unexpected watcher authority: {forbidden}'
assert watch.index('### Pi protocol v1') < watch.index('### Claude Code fallback')
summary_path = Path(sys.argv[2])
assert summary_path.is_file(), 'missing standalone request dashboard'
summary = summary_path.read_text()
for invariant in (
    'name: pr-review-requests', 'model-tier: economy', 'effort: medium',
    'gh-pr-review-requests.py', 'gh-pr-feedback.py', 'Python 3.10+',
    'current repository plus registered workspace repositories',
    'No account-wide fallback', 'requests', 'available', 'changedFields',
    '| PR | Title | Author | Requested | Updated | CI | Merge | Reviews | Feedback | Next |',
    'updatedAt', 'requestEvent', 'ciHeadSha', 'headSha', 'reviewDecision',
    'otherReviews', 'priorReview', 'identity', 'updatedAt', 'stateKey',
    'partial', 'failedRepositories', 'unknown', 'Never infer',
    'full current table', 'unchanged', 'ready for review', 'not safe to approve',
    're_requested', 'head_changed', 'status_changed', 'team', 'draft', 'merged',
    'closed', 'request_removed', 'session-local', '200', 'stop rather than',
    '/review-pr owner/repo#123', 'next-tick:', '1200', '1500', '1800',
    '✅ Approved', '☑️ Stale approval', '👎 Changes requested', '💬 Commented',
    '🔔 Awaiting review', '🔀 Merged', '🗑️ Closed', '🚧 Blocked',
    '🔎 Review', '⏳ Wait for CI', '✍️ Await author', '🚀 Await merge',
):
    assert invariant in summary, f'missing dashboard invariant: {invariant}'
for invariant in ('schemaVersion 2', '--state-stdin', 'pending display', 'legacy state',
                  'only after rendering', 'terminal controls'):
    assert invariant in summary, f'missing retained upstream safeguard: {invariant}'
tools = summary.split('---', 2)[1]
for forbidden in ('Skill(review-pr)', 'AskUserQuestion', 'Bash(gh', 'Bash(git'):
    assert forbidden not in tools, f'unexpected summary authority: {forbidden}'
assert '--mark-reviewed' not in summary, 'rendering must not mark code reviewed'
assert 'gh-pr-list-open.sh' not in summary, 'inbound scope must not use own-PR search'
print('inbound dashboard and thin watcher contracts passed')
PY
