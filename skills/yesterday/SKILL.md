---
name: yesterday
description: Read-only previous-workday recap. Alias for `/today --previous-workday`; the shared workflow selects Friday when run on Monday.
allowed-tools: "Read,Skill(today),Bash(~/.agents/skills/wrap-up/scripts/activity.sh:*),mcp__jira__jira_get"
model-tier: standard
model: sonnet
effort: medium
version: "0.2.0"
author: "flurdy"
---

# Yesterday (alias)

Retained entry point for the previous-workday recap. The full read-only workflow lives in
[today](../today/SKILL.md); this alias only fixes its mode.

## Instructions

Invoke the `today` skill with `--previous-workday {args}`, forwarding any supplied arguments
unchanged for the canonical skill to validate. If the Skill tool is unavailable, read
`~/.agents/skills/today/SKILL.md` and follow it with the same arguments using the exposed read-only
tools. Reading the skill grants no new capabilities; missing tools follow its unavailable-source
rules. Keep standard routing because this fallback also renders the report.

If the canonical skill is missing or unreadable, stop and report it as unavailable.
Never fall back to same-day mode or reconstruct a private copy of its procedure.

Perform no collection or rendering here before delegation. The canonical skill owns date
selection through its helper, queries, report layout, and all failure handling.
