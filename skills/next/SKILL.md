---
name: next
description: >
  Pick the next bead to work on. Globally ranks ready tasks across validated
  workspace Beads stores while preserving local single-store behavior.
allowed-tools: "Read,Bash(bd:*),Bash(~/.agents/skills/next/scripts/next-bd:*),Bash(~/.agents/skills/next/scripts/next-select:*),Bash(~/.agents/skills/handoffs/scripts/list.sh:*),AskUserQuestion,mcp__jira__jira_get"
model-tier: economy
model: haiku
effort: medium
version: "1.6.0"
author: "flurdy"
---

# Next - Pick Your Next Bead

Help select the next bead to work on based on readiness and user preferences.

## When to Use

- Starting a new work session
- Finished a task and need to pick the next one
- Want to see what's available to work on
- Need help prioritizing between multiple options

> **Deciding between resuming a handoff and starting fresh?** Run `/landscape` first — its `**Next:**` line weighs last session's live thread against fresh ready work. This skill is the "start fresh" branch of that decision; it still runs its own handoff check (see *Resume awareness*) before marking a bead in_progress.

## Usage

```bash
/next                    # Show ready beads as a ranked table (same as `list`)
/next list               # Explicitly render the full ranked table, then ask which to pick
/next safe               # Same but exclude services with in-progress beads
/next sprint             # Same, enriched with Jira sprint and sorted by sprint bucket
/next task               # Auto-pick the next most suitable task and start it
/next quick              # Auto-pick an easy win (excludes busy services)
/next bug                # Auto-pick the next most important bug and fix it
/next <bead-id>          # Start working on specific bead
/next <repo>:<bead-id>   # Start a bead whose ID exists in several workspace stores
```

## What This Skill Does

1. **Find Ready Work**
   - Run the `next-bd` collector to get open, unblocked tasks
   - At a valid project-workspace root, collect the root and every registered repository
     with a usable Beads store
   - Exclude `in_progress` beads (another session may be working on them)
   - Show current in-progress work with repository identity (for awareness, not selection)

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
# Show ready work as a ranked table
/next

# Explicitly render the full table (when a bare /next got over-interpreted)
/next list

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
## Ready to Work (3 beads)

| # | Repo     | ID         | Pri | Type    | Labels          | Title                   |
|---|----------|------------|-----|---------|-----------------|-------------------------|
| 1 | frontend | web-abc    | P1  | bug     | login           | Fix login timeout       |
| 2 | workspace | agents-def | P2 | feature | backend, orders | Add export to CSV       |
| 3 | events   | event-ghi  | P2  | task    | auth            | Update dependencies     |

In progress (other sessions):
- [frontend] `web-xyz` (P2 feature) "Implement caching layer"

Which would you like to work on? (1-3, or specify ID, or "task" to auto-pick)
```

The `Repo` column appears only for validated workspace aggregation. Local single-store
output keeps the original columns.

## Implementation

When invoked:

1. **Get the ranked table** using the `next-bd` script. It validates workspace topology,
   collects each usable independent store read-only, preserves owner identity, filters
   blocked work, and ranks the combined candidates. Outside a validated workspace root it
   keeps local single-store behavior. Always invoke it through the portable shared install
   path so the command prefix is stable and allowlistable across harnesses:

   ```bash
   ~/.agents/skills/next/scripts/next-bd --in-progress
   ```

   For `safe` and `quick` modes, add `--avoid-busy` to exclude beads whose labels overlap
   with in-progress beads in the same owning store:
   ```bash
   ~/.agents/skills/next/scripts/next-bd --in-progress --avoid-busy
   ```

   This outputs a globally ranked markdown table with labels, blocked filtering, and
   owner-qualified in-progress awareness. `--json` adds `repository`, `repository_path`,
   and `selector` to workspace candidates; local JSON remains backward compatible.

2. Parse command argument:
   - (none) or `list`: Render the full ranked table (see **Listing Mode** below), then ask user to pick. These are identical — `list` is just an explicit way to ask for the table when a bare `/next` has previously been over-interpreted as "auto-pick" or "summarise". Never auto-pick in this mode.
   - `safe`: Show the script output with `--avoid-busy`, ask user to pick
   - `sprint`: Run sprint enrichment (see Sprint Mode below) and ask user to pick
   - `task`: Use `next-bd --json`, auto-select the top-ranked bead, and start it through `next-select start <selector>`
   - `quick`: Use `next-bd --json --avoid-busy`, apply the quick heuristics, and start it through `next-select start <selector>`
   - `bug`: Use `next-bd --json --type=bug`, auto-select the top-ranked bug, and start it through `next-select start <selector>`
   - `<bead-id>` or `<repo>:<bead-id>`: Start that specific bead

3. If a specific bead ID is provided, resolve its owning store first (see
   **Owner-routed selection** below):

   ```bash
   ~/.agents/skills/next/scripts/next-select resolve <selector>
   ```

4. Otherwise, present the script output and ask user to choose

5. On selection:
   - Never infer ownership from a bead's ID, labels, or the current directory
   - **Run the handoff check** (see *Resume awareness* below)
   - Start the bead in its owning store:
     ```bash
     ~/.agents/skills/next/scripts/next-select start <selector>
     ```
     This marks it `in_progress` and shows its full details in that store only
   - If bead has description with steps, highlight the first step

## Resume awareness (handoff check before starting)

Run this **only when committing to start a specific bead** — `/next <bead-id>`, `task`, `quick`, `bug`, or a pick from the table — *before* `bd update --status=in_progress`. **Never** in Listing mode (`/next` / `/next list` mark nothing in_progress, so they must stay network-free and silent).

A prior session may have left a `/wrap-up` handoff that names this exact bead — its open threads and suggested next step are the warm-start context you'd otherwise resume without. Surface it, don't bury it.

Two-step so the common case (a fresh bead with no handoff) stays cheap — no network:

1. **Cheap pass (no network):**
   ```bash
   ~/.agents/skills/next/scripts/next-select handoff <selector>
   ```
   This runs the handoffs lookup inside the bead's owning repository, so a member repo's
   handoff is matched instead of the workspace root's. Handoffs match by owning repository,
   so one written from the workspace root about a member's bead will not surface here.
   Read the `---MATCHED-HANDOFFS---` section (owning-repo, supersede-filtered, newest first). **Empty → proceed straight to in_progress, say nothing.** This is the usual path.
2. **Confirm live (only if step 1 matched):** a squash-merged branch still looks live to the cheap pass. Re-run with liveness to drop shipped/merged handoffs:
   ```bash
   ~/.agents/skills/next/scripts/next-select handoff <selector> --check-branches
   ```
   If `---MATCHED-HANDOFFS---` is now empty, the work already shipped — **proceed silently**. Otherwise take the **newest** matched line.

Matched line: `{filename}|{date}|{time}|{slug}|{branch}|{exists}|{pr-state}|{pr-number}|{pr-url}`.

When a live handoff remains, ask with `AskUserQuestion` before starting:

> 📥 A handoff `{slug}` ({date} {time}) covers `{id}` — load its context before starting?

- **Load handoff (recommended)** — `Read` `~/.claude/handoffs/{filename}` and render it **verbatim** in a fenced block so it becomes resume context. If `{exists}=Y` and the recorded cwd differs from pwd, add `**Switch directory:** cd {cwd}`. If `{exists}=N` (worktree pruned) or the flow gets involved, point to `/handoffs` for the full worktree-recreation flow rather than reimplementing it here. Then mark the bead in_progress and continue.
- **Start fresh** — skip the handoff; mark in_progress and proceed.

Keep it to one prompt. If `bd`/`list.sh` errors or there's no handoffs dir, proceed silently — the check is a courtesy, never a blocker.

## Owner-routed selection

Every selection resolves through one command before anything is read or written:

```bash
~/.agents/skills/next/scripts/next-select resolve <selector>
```

`<selector>` is a table index (`3`), a bead ID (`mycode-abc`), or a repository-qualified ID
(`frontend:mycode-abc`). Pass the same `--avoid-busy` or `--type=<type>` options used to
render the table so an index resolves against the list the user actually saw. Prefer the
candidate's own `selector`; when you do pass an index, add `--expect-id <id>` so a list that
changed since it was rendered fails instead of starting a different bead.

Resolution prints JSON and never writes:

- `{"status":"resolved", ...}` (exit 0) carries `id`, `repository`, `repository_path`, and
  the absolute `directory` of the owning store. `handoff` and `start` reuse that store.
- `{"status":"ambiguous", ...}` (exit 3) means the bare ID exists in several stores. **Do
  not mutate anything.** Show the `matches[].selector` values and ask which one to start.
- `{"status":"not-found", ...}` (exit 4) means no usable store owns that selector. Show the
  ranked table again rather than guessing.
- `{"status":"stale", ...}` (exit 6) means the index no longer points at `--expect-id`.
  Re-render the table and ask again; nothing was written.

## Listing Mode (default and `list`)

`/next` with no auto-pick argument — and the explicit `/next list` — must **show the table**, not a prose summary of it. The `next-bd` output arrives inside a Bash tool result that the UI collapses to a few lines, so do not rely on the user seeing it there.

When listing:

1. Run the `next-bd` script.
2. **Reproduce the full ranked table in your own markdown reply**, every row, using the columns from the Output Format above. Do not truncate to "top 3" and do not replace the table with a narrative.
3. *After* the table, you may add a short note (1–2 sentences) on the strongest candidate(s) and any in-progress overlap — but the table comes first and stays complete.
4. End with the picker prompt: `Pick a number, a bead ID, or type task/bug/quick to auto-pick.`
5. When the user picks a number, pass that index to `next-select` with the same collector
   options so the selection resolves against the list they saw and keeps its owning store.

Listing mode never marks anything `in_progress`. It only selects work once the user replies.

## Handling Edge Cases

- **No ready beads (P0-P3)**: Show blocked beads and what's blocking them; mention P4 backlog exists if any, but don't auto-pick
- **All open beads in progress**: Warn that another session may be working on them; ask user if they want to see in_progress beads anyway (may cause conflicts)
- **User picks in_progress bead**: Warn that another session may be working on it; require explicit confirmation before starting
- **Invalid ID**: Show error and list valid options
- **ID owned by several stores**: `next-select` returns `ambiguous` and writes nothing; ask which `repo:id` to start
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
~/.agents/skills/next/scripts/next-bd --json
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

| # | Repo | ID | Pri | Type | Jira | Sprint | Status | Title |
|---|------|----|-----|------|------|--------|--------|-------|
| 1 | events | mycode-agf | P1 | task | [AB-1088](https://yourorg.atlassian.net/browse/AB-1088) | 31 (active) | In Progress | Replace event attribution wiring... |
| 2 | workspace | mycode-6ic | P2 | task | [AB-1424](https://yourorg.atlassian.net/browse/AB-1424) | 32 (future) | Backlog | Make analytics client stateless... |
| 3 | frontend | mycode-y8p | P2 | bug | — | — | — | Auth0 postLogin race... |
```

- `#` is a continuous index for the picker.
- `Repo` appears in workspace mode and is omitted for local single-store output.
- `Jira` column: markdown link `[KEY](https://yourorg.atlassian.net/browse/KEY)`. `—` if no key.
- `Sprint` column: number + state suffix only (`31 (active)`, `32 (future)`). Strip the project prefix from sprint names like `"PROJ Sprint 31"`. For descriptive sprint names without an obvious number, keep the full name. `—` for no-sprint and no-Jira beads.
- `Status` column: Jira status. `—` for no-Jira beads.
- If the Jira call fails: render the table without Sprint/Status columns and with no Jira links. Footnote: `_Jira unavailable: {error}. Showing beads in rank order without sprint info._`
- If all beads end up in the same sprint, footnote: `_All ready beads in {sprint name}._`

### Step 6 — Picker

Same prompt as default mode (`1-N`, bead ID, or `task`/`bug`/`quick` to auto-pick). For `sprint task`/`sprint bug`/`sprint quick`, prefer the top-ranked match in the **active sprint**, falling back to the next bucket if empty.

Sprint rows are re-sorted into buckets, so their numbers no longer match `next-bd` rank
order. Resolve a sprint pick by the candidate's `selector` (or its bead ID), never by the
displayed index.

### Edge cases

- **Multiple active sprints**: still one table — beads from each appear with their own sprint name. Active-sprint groups sort by sprint name / ID ascending so they cluster.
- **Ticket key found but Jira returns nothing**: treat as no-sprint (key may have moved or been deleted).
- **Sprint field not enabled on the project**: all tickets fall into no-sprint; the sort still works.
- **Bead title has multiple Jira keys**: use the first match.

## Bug Mode

When `/next bug` is used:

1. **Filter to open bugs across the collected stores** (excluding P4 backlog):

   ```bash
   ~/.agents/skills/next/scripts/next-bd --json --type=bug
   ```

2. **Rank by priority**: P0 > P1 > P2 > P3 (highest priority bug first, P4 excluded)

3. **Auto-select and start** the top-ranked bug through `next-select start <selector>`

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
