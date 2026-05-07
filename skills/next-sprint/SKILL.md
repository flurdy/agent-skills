---
name: next-sprint
description: Pick the next bead sorted by Jira sprint. Same ranking as /next, but enriches each bead with its Jira ticket and sorts a single table by sprint bucket (active → future → no-sprint → no-Jira). Use when planning around sprint scope.
allowed-tools: "Bash(~/.claude/skills/next/scripts/next-bd:*), Bash(bd show:*), Bash(bd update:*), mcp__jira__jira_get"
model: sonnet
effort: medium
version: "0.1.0"
author: "flurdy"
---

# Next-Sprint — Pick Your Next Bead, Sprint-Aware

Like `/next`, but enriches each ready bead with its Jira ticket + sprint, and sorts a single table by sprint bucket so active-sprint work bubbles to the top.

## When to Use

- Planning work around a sprint cycle ("what's left in this sprint?")
- Picking work after sprint planning when you want to focus on the active sprint first
- Cross-checking which ready beads are sprint-scheduled vs ad-hoc

For a quick local-only view (no Jira lookup, faster), use `/next` instead.

## Usage

```bash
/next-sprint              # Show ready beads in one table, sorted by sprint bucket
/next-sprint safe         # Same but exclude services with in-progress beads
/next-sprint task         # Auto-pick top-ranked task in the active sprint
/next-sprint bug          # Auto-pick top-ranked bug in the active sprint
/next-sprint <bead-id>    # Start working on specific bead
```

## What This Skill Does

1. **Fetch ready beads** via `next-bd --json` (already ranked by the `/next` algorithm).
2. **Extract Jira keys** from each bead's title (regex `[A-Z]+-\d+`, first match).
3. **Batch-query Jira** in a single JQL call for all extracted keys, pulling sprint (`customfield_10020`), status, type, and Jira priority.
4. **Sort beads by sprint bucket**: active sprint(s) first → future sprints → no-sprint Jira tickets → beads with no Jira link. Within each bucket, preserve the `next-bd` rank order.
5. **Render** a single table with a Sprint column.
6. **Present picker** — same interaction as `/next`.

## Implementation

### Step 1 — Fetch ranked beads

```bash
~/.claude/skills/next/scripts/next-bd --json
```

For `safe` / `quick` mode add `--avoid-busy`:

```bash
~/.claude/skills/next/scripts/next-bd --json --avoid-busy
```

This returns a JSON array of beads, each with a `rank` field (lower = higher priority). Output is empty array `[]` if nothing is ready.

### Step 2 — Extract Jira keys

For each bead, scan `title` for the first match of `[A-Z]+-\d+`. That's the Jira key. If no match, the bead has no Jira link.

Note: some beads may also reference Jira via `description` (e.g., `Jira: GE-1088 |`) — only fall back to description if title yields nothing AND you want to be thorough. For the default flow, **title only** is sufficient and matches how the user has been formatting beads.

### Step 3 — Batch Jira lookup

Single JQL call for all extracted keys at once. `customfield_10020` is the Jira Cloud sprint field.

```
mcp__jira__jira_get
  path: /rest/api/3/search/jql
  queryParams:
    jql: key in ({comma-separated keys})
    fields: summary,status,issuetype,priority,customfield_10020
    maxResults: 100
  jq: issues[*].{key: key, summary: fields.summary, status: fields.status.name, type: fields.issuetype.name, jiraPriority: fields.priority.name, sprint: fields.customfield_10020}
```

If the keys list is empty, skip this call entirely.

The `sprint` field is an array of sprint objects. For each Jira ticket:
- Pick the **active** sprint (first object where `state == "active"`).
- If none active, pick the **earliest future** sprint (lowest `startDate` where `state == "future"`).
- If none, treat as no-sprint (the ticket isn't on a board, or sprint field is null/empty).

### Step 4 — Join and sort

Build a map `{ jira_key → { sprintName, sprintState, jiraStatus, jiraPriority } }`.

For each ranked bead, attach Jira data if available, then assign each bead a sort key based on bucket:

1. **Active sprint(s)** — sprintState=`active`. Multiple active sprints (cross-team boards) sort by sprint name / ID ascending.
2. **Future sprints** — sprintState=`future`, ordered by `startDate` ascending.
3. **No sprint (has Jira ticket)** — beads with a Jira key but no sprint association.
4. **No Jira link** — beads with no `[A-Z]+-\d+` in the title.

Within each bucket, preserve the existing rank order from `next-bd`.

### Step 5 — Render

One table for everything:

```markdown
## Ready by Sprint ({total} beads)

| # | ID | Pri | Type | Jira | Sprint | Status | Title |
|---|----|-----|------|------|--------|--------|-------|
| 1 | blc-2-agf | P1 | task | [GE-1088](https://bluelightcard.atlassian.net/browse/GE-1088) | 31 (active) | In Progress | Replace autocapture.attribution... |
| 2 | blc-2-6ic | P2 | task | [GE-1424](https://bluelightcard.atlassian.net/browse/GE-1424) | 32 (future) | Backlog | Make cms-pages Amplitude client stateless... |
| 3 | blc-2-y8p | P2 | bug | — | — | — | Auth0 postLogin Action... |
```

Notes:
- The `#` column is a continuous index for the picker prompt (`1-N`).
- The `Jira` column is a markdown link to `https://bluelightcard.atlassian.net/browse/{key}`. Show `—` for beads with no Jira key.
- The `Sprint` column shows just the **number + state** suffix (`31 (active)`, `32 (future)`). Strip the project prefix (e.g. `"GE Sprint 31"` → `"31"`). For long descriptive names that don't have an obvious number (e.g. a goal-string sprint name), keep the full name. Show `—` for no-sprint and no-Jira beads.
- The `Status` column is the Jira status. Show `—` for beads with no Jira key.
- If `next-bd` returns zero beads: render `_No ready beads. Run /triage to add work._` and stop.
- If the Jira call fails: render the table without the Sprint and Status columns and with no Jira links. Add a footnote: `_Jira unavailable: {error}. Showing beads in rank order without sprint info._`

### Step 6 — Picker

After rendering, prompt:

```
Which would you like to work on? (1-N, or specify ID, or "task"/"bug"/"quick" to auto-pick)
```

Handle the same modes as `/next`:
- `<bead-id>` — `bd show <id>` then `bd update <id> --status=in_progress`
- `task` — auto-pick the top-ranked task **in the active sprint**, fall back to the first sprint group if active is empty, then to no-sprint, then no-Jira
- `bug` — same fallback chain, type=bug
- `quick` — auto-pick a small task (use the same heuristics as `/next quick`), preferring active sprint first

For `safe` mode, do NOT auto-pick; just render the table (matching `/next safe` behavior).

## Edge cases

- **Multiple active sprints**: still one table — beads from each appear with their own sprint name in the Sprint column. Sort active-sprint groups by sprint name / ID ascending so they cluster together.
- **Ticket key found but Jira returns nothing**: treat as "no sprint" (the key may have been moved or deleted). Don't crash.
- **Sprint field not enabled on the project**: all tickets fall into "No sprint". The sort still works.
- **Bead title has multiple Jira keys** (rare — e.g., `GE-1088 + GE-1344: …`): use the first match.
- **All beads in one sprint**: still render the single table. Add a footnote: `_All ready beads in {sprint name}._`

## Why the helper script vs inline `bd list`

The `next-bd` script encapsulates the priority ranking algorithm, blocked filtering, and `--avoid-busy` logic in one place. Reusing it (rather than duplicating the jq pipeline here) keeps the ranking consistent with `/next` and ensures `/next-sprint` automatically benefits from any future ranking improvements.
