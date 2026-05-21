---
name: next
description: >
  Pick the next bead to work on. Shows ready tasks (no blockers), applies user
  preferences for ordering (priority, type, recency), and helps select work.
allowed-tools: "Read,Bash(bd:*),Bash(~/.claude/skills/next/scripts/next-bd:*),AskUserQuestion,mcp__jira__jira_get"
model: haiku
effort: low
version: "1.2.0"
author: "flurdy"
---

# Next - Pick Your Next Bead

Help select the next bead to work on based on readiness and user preferences.

## When to Use

- Starting a new work session
- Finished a task and need to pick the next one
- Want to see what's available to work on
- Need help prioritizing between multiple options

## Usage

```bash
/next                    # Show ready beads, ranked by suitability
/next safe               # Same but exclude services with in-progress beads
/next sprint             # Same, enriched with Jira sprint and sorted by sprint bucket
/next task               # Auto-pick the next most suitable task and start it
/next quick              # Auto-pick an easy win (excludes busy services)
/next bug                # Auto-pick the next most important bug and fix it
/next <bead-id>          # Start working on specific bead
```

## What This Skill Does

1. **Find Ready Work**
   - Run `bd list --ready` to get open, unblocked tasks
   - Excludes `in_progress` beads (another session may be working on them)
   - Show current in-progress work if any (for awareness, not selection)

2. **Rank by Suitability**
   - Apply priority ranking algorithm (see below)
   - Bugs generally rank higher than features at same priority
   - Epics rank lower (they represent larger work)

3. **Present Options**
   - Show top 5 candidates with key details
   - Include: ID, title, priority, type, labels (services/tags), age
   - Ask user to pick or provide different criteria

4. **Start Work**
   - Mark selected bead as in_progress
   - Show full bead details
   - Suggest first steps if description includes them

## Examples

```bash
# Show ready work ranked by suitability
/next

# Show ready work, excluding services with in-progress beads
/next safe

# Show ready work, sorted by Jira sprint (active → future → no-sprint → no-Jira)
/next sprint

# Auto-pick and start the next most suitable task
/next task

# Auto-pick an easy win (excludes busy services)
/next quick

# Auto-pick the next most important bug and start fixing
/next bug

# Start a specific bead
/next mycode-abc
```

## Output Format

```plaintext
## Ready to Work (5 of 12 open)

| # | ID         | Pri | Type    | Labels              | Title                          |
|---|------------|-----|---------|---------------------|--------------------------------|
| 1 | mycode-abc | P1  | bug     | frontend            | Fix login timeout issue        |
| 2 | mycode-def | P2  | feature | backend, orders     | Add export to CSV              |
| 3 | mycode-ghi | P2  | task    | auth                | Update dependencies            |
| 4 | mycode-jkl | P3  | feature | frontend, css       | Dark mode toggle               |
| 5 | mycode-mno | P3  | task    | events, auth        | Refactor auth service          |

Currently in progress: mycode-xyz "Implement caching layer"

Which would you like to work on? (1-5, or specify ID, or "task" to auto-pick)
```

## Implementation

When invoked:

1. **Get the ranked table** using the `next-bd` script (handles ready list, blocked filtering, label fetching, and ranking in one command). Always invoke it by its full install path so the command prefix is stable and allowlistable in `.claude/settings.json`. For Claude Code:

   ```bash
   ~/.claude/skills/next/scripts/next-bd --in-progress
   ```

   For Codex, substitute the Codex skills path — pick one path per harness; do not combine with a conditional or env-var expansion, as compound shell expressions cannot be granted a stable permission prefix:

   ```bash
   ~/.codex/skills/next/scripts/next-bd --in-progress
   ```

   For `safe` and `quick` modes, add `--avoid-busy` to exclude beads whose labels overlap with in-progress beads:
   ```bash
   ~/.claude/skills/next/scripts/next-bd --in-progress --avoid-busy
   ```

   This outputs a markdown table ranked by the priority algorithm, with labels included, blocked beads filtered out, and in-progress beads shown for awareness.

2. Parse command argument:
   - (none): Show the script output, ask user to pick
   - `safe`: Show the script output with `--avoid-busy`, ask user to pick
   - `sprint`: Run sprint enrichment (see Sprint Mode below) and ask user to pick
   - `task`: Auto-select top-ranked bead and start it
   - `quick`: Auto-select an easy win task and start it (uses `--avoid-busy`)
   - `bug`: Auto-select top-ranked bug and start it (see Bug Mode below)
   - `<bead-id>`: Start that specific bead

3. If specific bead ID provided:

   ```bash
   bd show <id>
   bd update <id> --status=in_progress
   ```

4. Otherwise, present the script output and ask user to choose

5. On selection:
   - Mark as in_progress
   - Show full details with `bd show`
   - If bead has description with steps, highlight first step

## Handling Edge Cases

- **No ready beads (P0-P3)**: Show blocked beads and what's blocking them; mention P4 backlog exists if any, but don't auto-pick
- **All open beads in progress**: Warn that another session may be working on them; ask user if they want to see in_progress beads anyway (may cause conflicts)
- **User picks in_progress bead**: Warn that another session may be working on it; require explicit confirmation before starting
- **Invalid ID**: Show error and list valid options
- **User says "skip"**: Show next 5 options

## Priority Ranking Algorithm

Rank ready beads in this order (first match wins):

| Rank | Criteria                        |
|------|---------------------------------|
| 1    | Any P0 issue (any type)         |
| 2    | P1 bug                          |
| 3    | P2 bug                          |
| 4    | P1 feature or task              |
| 5    | P1 epic                         |
| 6    | P2 feature or task              |
| 7    | P3 bug, feature, or task        |
| 8    | P2 epic                         |
| 9    | P3 epic                         |
| 10   | Any other non-P4 issue          |

**Important**: P4 items are backlog/future work and must NEVER be auto-picked. Always use `--priority-max=3` to exclude them. Only show P4 items if user explicitly requests them.

## Quick Task Heuristics

When `/next quick` is used, prefer:
1. Type: task > bug > feature (tasks are usually smaller)
2. Priority: P3 > P2 > P1 (lower priority = less complex)
3. Exclude epics (too large for quick wins)
4. Title keywords: "fix", "update", "add" > "implement", "refactor", "redesign"

## Sprint Mode

When `/next sprint` is used, enrich each ready bead with its Jira ticket + sprint, then render one table sorted by sprint bucket.

### Step 1 — Fetch ranked beads as JSON

```bash
~/.claude/skills/next/scripts/next-bd --json
```

Empty array `[]` means nothing ready — render `_No ready beads. Run /triage to add work._` and stop.

### Step 2 — Extract Jira keys

For each bead, scan `title` for the first match of `[A-Z]+-\d+`. If no match, the bead has no Jira link. Title-only is sufficient for the default flow.

### Step 3 — Batch Jira lookup

If any keys were found, single JQL call. `customfield_10020` is Jira Cloud's sprint field.

```
mcp__jira__jira_get
  path: /rest/api/3/search/jql
  queryParams:
    jql: key in ({comma-separated keys})
    fields: summary,status,issuetype,priority,customfield_10020
    maxResults: 100
  jq: issues[*].{key: key, status: fields.status.name, type: fields.issuetype.name, jiraPriority: fields.priority.name, sprint: fields.customfield_10020}
```

For each ticket's `sprint` array, pick the **active** sprint (first with `state=="active"`); else the earliest **future** sprint (lowest `startDate` with `state=="future"`); else treat as no-sprint.

### Step 4 — Sort by bucket

1. **Active sprint(s)** — `state=="active"`. Multiple active sprints (cross-team boards) sort by sprint name / ID ascending.
2. **Future sprints** — `state=="future"`, ordered by `startDate` ascending.
3. **No sprint (has Jira ticket)** — bead has a Jira key but the ticket has no sprint.
4. **No Jira link** — no `[A-Z]+-\d+` in title.

Within each bucket, preserve the `next-bd` rank order.

### Step 5 — Render

```markdown
## Ready by Sprint ({total} beads)

| # | ID | Pri | Type | Jira | Sprint | Status | Title |
|---|----|-----|------|------|--------|--------|-------|
| 1 | mycode-agf | P1 | task | [AB-1088](https://yourorg.atlassian.net/browse/AB-1088) | 31 (active) | In Progress | Replace event attribution wiring... |
| 2 | mycode-6ic | P2 | task | [AB-1424](https://yourorg.atlassian.net/browse/AB-1424) | 32 (future) | Backlog | Make analytics client stateless... |
| 3 | mycode-y8p | P2 | bug | — | — | — | Auth0 postLogin race... |
```

- `#` is a continuous index for the picker.
- `Jira` column: markdown link `[KEY](https://yourorg.atlassian.net/browse/KEY)`. `—` if no key.
- `Sprint` column: number + state suffix only (`31 (active)`, `32 (future)`). Strip the project prefix from sprint names like `"PROJ Sprint 31"`. For descriptive sprint names without an obvious number, keep the full name. `—` for no-sprint and no-Jira beads.
- `Status` column: Jira status. `—` for no-Jira beads.
- If the Jira call fails: render the table without Sprint/Status columns and with no Jira links. Footnote: `_Jira unavailable: {error}. Showing beads in rank order without sprint info._`
- If all beads end up in the same sprint, footnote: `_All ready beads in {sprint name}._`

### Step 6 — Picker

Same prompt as default mode (`1-N`, bead ID, or `task`/`bug`/`quick` to auto-pick). For `sprint task`/`sprint bug`/`sprint quick`, prefer the top-ranked match in the **active sprint**, falling back to the next bucket if empty.

### Edge cases

- **Multiple active sprints**: still one table — beads from each appear with their own sprint name. Active-sprint groups sort by sprint name / ID ascending so they cluster.
- **Ticket key found but Jira returns nothing**: treat as no-sprint (key may have moved or been deleted).
- **Sprint field not enabled on the project**: all tickets fall into no-sprint; the sort still works.
- **Bead title has multiple Jira keys**: use the first match.

## Bug Mode

When `/next bug` is used:

1. **Filter to open bugs only** (excluding P4 backlog):

   ```bash
   bd list --ready --type=bug --priority-max=3
   ```

2. **Rank by priority**: P0 > P1 > P2 > P3 (highest priority bug first, P4 excluded)

3. **Auto-select and start** the top-ranked bug

4. **Continue fixing bugs** if the completed bug was minor:
   - After completing a bug fix, assess if it was minor (small change, localized fix)
   - If minor AND there's remaining context (related code still fresh), auto-pick the next bug
   - Continue this loop until:
     - A bug requires significant work (not minor)
     - No more ready bugs remain
     - Context would be lost (unrelated area of codebase)

### Minor Bug Criteria

A bug is considered **minor** if:

- Fix touches ≤ 3 files
- Change is ≤ 50 lines total
- No architectural changes required
- Fix is localized (single component/module)

### Context Continuity

Continue to next bug automatically when:

- Next bug is in same or adjacent files
- Next bug is in same module/component
- Fix for previous bug provides context for next bug

Stop and ask user when:

- Next bug is in completely different area of codebase
- Next bug appears complex (P0/P1 with unclear scope)
- 3+ bugs have been fixed in sequence (natural checkpoint)
