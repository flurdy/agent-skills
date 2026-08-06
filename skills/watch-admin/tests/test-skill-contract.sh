#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL="$TEST_DIR/../SKILL.md"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_contains() {
    grep -Fq -- "$1" "$SKILL" || fail "expected '$1' in $SKILL"
}

[[ -f "$SKILL" ]] || fail 'missing watch-admin skill'

for invariant in \
    'name: watch-admin' \
    'status: no-go' \
    'Rollout gate — no-go' \
    'Do not start this watcher.' \
    '54,771 uncached input' \
    'before tick 1' \
    'Report this measured no-go and stop' \
    'Beads, and Pi configuration captures were identical.' \
    'calling a helper, Jira, or `watch_loop`' \
    'Pi-only' \
    '/watch-admin --ticks N' \
    '/watch-admin --until HH:MM' \
    'at most 10 ticks' \
    '1 through 96' \
    'There is no unbounded mode' \
    'exact read-only Jira search tool is unavailable' \
    'stop before scheduling' \
    'structurally read-only' \
    'never runs that workflow' \
    'Never edit files' \
    'Never improvise shell' \
    'State stays in the conversation' \
    'protocolVersion: 1' \
    'action: status' \
    'action: start' \
    'mode: adaptive' \
    'initialDelaySeconds: 60' \
    'missedCompletionPolicy: retry' \
    'maxTicks:' \
    'stopAt:' \
    'Load and follow the skill named `watch-admin` now in tick mode.' \
    'complete`, `partial`, or `error`' \
    'An absent not-due source must be omitted' \
    '--due-sources' \
    '1,800-second Jira cadence' \
    'nextProbeAt' \
    'assignee = currentUser() AND statusCategory != Done ORDER BY key ASC' \
    'status,priority,assignee,customfield_10020,duedate' \
    'maxResults `100`' \
    'no activity event' \
    'Quiet tick — no material workspace or assigned Jira changes.' \
    'below 512 UTF-8 bytes' \
    'render at most 20 events' \
    'At most one attended recommendation' \
    '/tracking-sweep quick' \
    '/project-brief' \
    '/backlog-groom' \
    '/triage ID' \
    'correctly shell-quoted argument' \
    'escaped inline code' \
    '[A-Za-z0-9._:-]+' \
    'Never execute it' \
    'next-tick: warm (~300s)' \
    'next-tick: quiet (~900s)' \
    'watch_loop complete' \
    'outcome: continue' \
    'outcome: stop' \
    '64 KiB' \
    '128 KiB' \
    'A→B→A→B' \
    'degrades that source' \
    'hourly' \
    'at most 256 UTF-8 bytes' \
    'retry identities 128' \
    'events 50' \
    'control characters' \
    'invalid enums' \
    'before collection'; do
    assert_contains "$invariant"
done

frontmatter=$(head -n 12 "$SKILL")
for helper in collect.py jira_adapter.py reducer.py; do
    grep -Fq -- "Bash(~/.agents/skills/watch-admin/scripts/$helper:*)" <<<"$frontmatter" \
        || fail "missing narrow helper allowance for $helper"
done

grep -Fq -- 'mcp__jira__jira_get' <<<"$frontmatter" || fail 'missing read-only Jira tool'
for forbidden in 'AskUserQuestion' 'Skill(' 'Task' 'Bash(git' 'Bash(bd' 'Write' 'Edit'; do
    if grep -Fq -- "$forbidden" <<<"$frontmatter"; then
        fail "forbidden tool surface: $forbidden"
    fi
done

for script in collect.py jira_adapter.py reducer.py; do
    [[ -x "$TEST_DIR/../scripts/$script" ]] || fail "$script is not executable"
done

printf '%s\n' 'watch-admin contract tests passed'
