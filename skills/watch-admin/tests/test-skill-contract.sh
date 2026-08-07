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

assert_not_contains() {
    if grep -Fq -- "$1" "$SKILL"; then
        fail "did not expect '$1' in $SKILL"
    fi
}

[[ -f "$SKILL" ]] || fail 'missing watch-admin skill'

for invariant in \
    'name: watch-admin' \
    'status: no-go' \
    'UAT candidate gate' \
    'remains no-go for ordinary use' \
    'WATCH_ADMIN_UAT=1' \
    'WATCH_ADMIN_UAT_WORKSPACE' \
    '/home/ivar/Code/blc/workspace' \
    'fresh dedicated Pi session' \
    '/skill:watch-admin' \
    '--require-stable-route' \
    'route changed' \
    'Pi-only' \
    '/skill:watch-admin --ticks N' \
    '/skill:watch-admin --until HH:MM' \
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
    'Do not load or read a skill, invoke another skill, or change the provider, model, or thinking level during this tick.' \
    '/rest/api/3/search/jql' \
    '{issues: issues[*].{id: id, key: key, self: self, fields: fields}, nextPageToken: nextPageToken}' \
    'mixed or null assignees' \
    'complete`, `partial`, or `error`' \
    'An absent not-due source must be omitted' \
    '--due-sources' \
    '1,800-second Jira cadence' \
    'nextProbeAt' \
    'assignee = currentUser() AND statusCategory != Done ORDER BY key ASC' \
    'status,priority,assignee,customfield_10020,duedate' \
    'maxResults: "100"' \
    'outputFormat: json' \
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

assert_not_contains 'Load and follow the skill named `watch-admin` now in tick mode.'

tick_prompt=$(awk '
    /^## Tick prompt$/ { found = 1; next }
    found && /^```text$/ { inside = 1; next }
    inside && /^```$/ { exit }
    inside { print }
' "$SKILL")
for invariant in \
    'Do not load or read a skill' \
    'invoke another skill' \
    'change the provider, model, or thinking level' \
    'mcp__jira__jira_get' \
    'JIRA_TOOL_ARGS_JSON=' \
    'watch_loop complete'; do
    grep -Fq -- "$invariant" <<<"$tick_prompt" || fail "tick prompt missing '$invariant'"
done

jira_args_line=$(grep -E '^JIRA_TOOL_ARGS_JSON=' <<<"$tick_prompt")
[[ $(grep -Ec '^JIRA_TOOL_ARGS_JSON=' <<<"$tick_prompt") -eq 1 ]] || fail 'tick prompt must contain one Jira argument object'
python3 - "$jira_args_line" <<'PY' || fail 'tick prompt Jira argument object is not exact JSON'
import json
import sys

actual = json.loads(sys.argv[1].split("=", 1)[1])
expected = {
    "path": "/rest/api/3/search/jql",
    "queryParams": {
        "jql": "assignee = currentUser() AND statusCategory != Done ORDER BY key ASC",
        "fields": "status,priority,assignee,customfield_10020,duedate",
        "maxResults": "100",
    },
    "jq": "{issues: issues[*].{id: id, key: key, self: self, fields: fields}, nextPageToken: nextPageToken}",
    "outputFormat": "json",
}
if actual != expected:
    raise SystemExit(f"unexpected Jira arguments: {actual!r}")
PY

frontmatter=$(head -n 13 "$SKILL")
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
