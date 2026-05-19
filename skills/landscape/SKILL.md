---
name: landscape
description: Morning catch-up view — assigned Jira tickets, open PRs, current working copy state, and (if present) in-progress and ready beads in one glance. Run at session start to orient.
allowed-tools: "Bash(git:*), Bash(gh:*), Bash(date:*), Bash(~/.claude/skills/landscape/scripts/working-copy.sh:*), Bash(~/.claude/skills/landscape/scripts/beads.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-list-open.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-list-closed.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-details.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-checks.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-reviews.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-threads.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-merge-state.sh:*), mcp__jira__jira_get, mcp__jira__jira_post"
model: sonnet
effort: medium
version: "0.5.2"
author: "flurdy"
---

# Landscape — Morning Catch-up

Show a consolidated landscape of where you are and what to do next, pulling from multiple sources at once. Designed for the start of a work session (especially Monday mornings) to quickly orient.

## Usage

```bash
/landscape          # Full landscape
/landscape quick    # Skip PR details (faster, Jira + working-copy + beads-if-present only)
```

## What It Shows

Separate blocks, rendered from broadest context to most immediate. Order matters — the last block is the most load-bearing for "what am I doing right now":

1. **📋 Jira** — tickets assigned to you, not Done (with sprint)
2. **🔀 PRs** — org-wide open PRs, recently closed, unresolved threads
3. **🎯 Beads** — in-progress and top ready beads in this repo (skipped if `bd` not installed)
4. **📍 Working copy** — current branch, uncommitted/unpushed work
5. **Next** — single-sentence suggestion for the most load-bearing action

Each block is independent — if one source fails, the others still render.

## Instructions

> **MUST re-fetch on every invocation.** Each `/landscape` run MUST execute every fetch from scratch — `date`, the Jira MCP query, the `gh-pr-list-*` and `gh-pr-details.sh` scripts, `beads.sh`, and `working-copy.sh`. NEVER reuse output from a previous run in the same session and NEVER extrapolate timestamps. State changes (PR merges, new approvals, ticket transitions) happen between runs; reusing stale tables has caused real merges to be missed in `/pr-status` and the same risk applies here.
>
> **MUST use the dedicated helper scripts.** Never construct ad-hoc `bd …` or `git …` shell pipelines for this skill. Specifically: do NOT chain `command -v bd` probes with `bd list … && …` or `… || bd list --ready` inside a single Bash call. Always invoke `~/.claude/skills/landscape/scripts/beads.sh` instead — it handles probing, repo gating, and listing internally. Inline chaining bypasses the per-script permission allowlist and produces noisy permission prompts.

Render the blocks in the order listed below. Some data fetches can run in parallel at the top.

### 0. Header

```bash
date '+%A %Y-%m-%d %H:%M'
```

Output:

```markdown
## Landscape — {Weekday} {YYYY-MM-DD} {HH:MM}
```

If the weekday is Monday, add a subtitle: `_Monday — extra catch-up across the weekend._`

### 1. 📋 Jira — assigned to you

Query Jira for open tickets assigned to the current user, including sprint membership. The sprint field is the Jira Cloud default custom field `customfield_10020`. Use the MCP tool:

```
mcp__jira__jira_get
  path: /rest/api/3/search/jql
  queryParams:
    jql: assignee = currentUser() AND statusCategory != Done ORDER BY cf[10020] ASC, priority DESC, updated DESC
    fields: summary,status,priority,issuetype,updated,customfield_10020
    maxResults: 20
  jq: issues[*].{key: key, summary: fields.summary, type: fields.issuetype.name, status: fields.status.name, priority: fields.priority.name, updated: fields.updated, sprint: fields.customfield_10020}
```

The `sprint` field is an array of sprint objects. Extract the **active** sprint's name (first sprint where `state == "active"`), or the most recent if none are active. If the array is empty or null, show `—` (ticket not in a sprint — possibly backlog).

**Sort the rows before rendering.** JQL's `cf[10020]` sort is unreliable across sprint states, so re-sort client-side:

1. Bucket by sprint state: **active** sprints first, then **future** sprints (by `startDate` ascending), then **no-sprint / backlog** last.
2. Within each bucket, sort by priority `P1 → P2 → P3 → P4 → P5` (treat missing/unknown priority as lowest).
3. Within equal priority, preserve the JQL `updated DESC` order.

Keep it as a single table — the Sprint column makes the group boundary visible without subheadings.

Render:

```markdown
### 📋 Jira — assigned to you

| Key | Sprint | Type | Pri | Status | Updated | Summary |
|-----|--------|------|-----|--------|---------|---------|
| [GE-649](https://.../browse/GE-649) | Sprint 42 | Task | P1 | In Progress | 2h | Stabilise identity cookies |
```

- **Key**: markdown link to the Jira issue. Use the Jira base URL from the issue's `self` field, or a site-configured base (e.g. `https://bluelightcard.atlassian.net/browse/{key}`).
- **Sprint**: active sprint name. Truncate numeric-only names to `S{N}` if the column gets wide. `—` if none.
- **Type**: issuetype name (Task / Story / Bug / Sub-task).
- **Pri**: shorten long names — `P1 Critical` → `P1`, `P2 High` → `P2`, etc.
- **Status**: status name (In Progress / Code Review / Ready for QA / …).
- **Updated**: relative time since `updated` (e.g. `2h`, `4d`).
- **Summary**: truncate to ~50 chars.

If no tickets are assigned, show `_No open Jira tickets assigned to you._`

If the Jira API returns an error, show `_Jira unavailable: {error}_` and move on — do not fail the whole skill.

After the table, note whether the tickets span one sprint or multiple. Example: `_All 6 in Sprint 42._` or `_Spans 2 sprints: Sprint 42 (4), Sprint 43 (2)._` This answers "am I focused or scattered?" at a glance.

### 2. 🔀 PRs — delegate to pr-status logic

**If `/landscape quick` was invoked, skip this section entirely** and add a one-line note: `_PR section skipped (quick mode). Run /pr-status for full view._`

Otherwise, follow the `pr-status` skill's instructions as-is (see `~/.claude/skills/pr-status/SKILL.md`). Reuse its scripts directly — do NOT re-invoke the slash command:

1. List open PRs org-wide via `gh-pr-list-open.sh`
2. List recently closed via `gh-pr-list-closed.sh`
3. Fetch details via `gh-pr-details.sh` (grouped by owner/repo)
4. Render the same tables

Head this section `### 🔀 PRs` instead of pr-status's own headings.

### 3. 🎯 Beads — in-progress + ready work

Run the `beads.sh` helper. It probes for `bd`, checks for `.beads/` in the repo, and emits in-progress + ready listings as delimited sections. **Do not call `bd` directly from this skill** — always go through this script:

```bash
~/.claude/skills/landscape/scripts/beads.sh
```

Output sections (delimited by `---<NAME>---`):
- `---STATUS---` — `OK`, `NO_BD` (bd not installed), or `NO_BEADS_IN_REPO` (no `.beads/` here)
- `---IN-PROGRESS---` — output of `bd list --status=in_progress` (only if `STATUS=OK`)
- `---READY---` — JSON array from `next-bd --json` (or plain text from `bd list --ready` fallback) (only if `STATUS=OK`)

If `STATUS` is `NO_BD`, render `_Beads not installed — skipping._` and stop.
If `STATUS` is `NO_BEADS_IN_REPO`, render `_No beads in this repo._` and stop.
Otherwise render the tables below.

#### In-progress beads

```markdown
**In progress ({count})**
| ID | Pri | Type | Labels | Title |
|----|-----|------|--------|-------|
```

- Include a **Labels** column. Show `—` if none.
- If no in-progress beads: show `_No in-progress beads._`

#### Ready beads — sorted by sprint

The `---READY---` section is a JSON array (from `next-bd --json`). Each item has `id`, `title`, `priority`, `issue_type`, and `rank`.

**Step 1 — Extract Jira keys.** For each bead, scan `title` for the first match of `[A-Z]+-\d+`. If no match, the bead has no Jira link.

**Step 2 — Batch Jira sprint lookup.** If any keys were found, call:

```
mcp__jira__jira_get
  path: /rest/api/3/search/jql
  queryParams:
    jql: key in ({comma-separated keys})
    fields: summary,status,issuetype,priority,customfield_10020
    maxResults: 50
  jq: issues[*].{key: key, status: fields.status.name, sprint: fields.customfield_10020}
```

For each ticket's `sprint` array, pick the **active** sprint (first with `state=="active"`). If none active, pick the earliest **future** sprint (lowest `startDate` with `state=="future"`). If neither, treat as no-sprint.

**Step 3 — Sort and cap.** Bucket order: active sprint(s) → future sprints (by `startDate`) → no-sprint (has Jira key) → no Jira link. Within each bucket preserve the rank order from `next-bd`. Cap the total at **5 beads**. If more exist: `_+{N} more — run /next sprint to see all._`

**Step 4 — Render.** One table:

```markdown
**Ready ({shown} of {total})**
| # | ID | Pri | Type | Jira | Sprint | Status | Title |
|---|----|-----|------|------|--------|--------|-------|
```

- `#` is the picker index `1-N`.
- `Jira` column: markdown link `[KEY](https://bluelightcard.atlassian.net/browse/KEY)`. Show `—` if no Jira key.
- `Sprint` column: number + state suffix only (`31 (active)`, `32 (future)`) — strip the project prefix from sprint names like `"GE Sprint 31"`. Show `—` if no sprint or no Jira.
- `Status` column: Jira status. Show `—` if no Jira.
- If no ready beads at all: `_No ready beads. Run /triage to add work._`
- If the `---READY---` section is not valid JSON (fallback plain text): render it as-is, capped at 5 lines.
- If the Jira call fails: render the table without Jira/Sprint/Status columns; add a footnote `_Jira unavailable._`

### 4. 📍 Working copy — current branch

Rendered LAST because it's the most immediate context — the branch you're sitting on right now, what needs committing/pushing, and whether it's in sync.

Run the `working-copy.sh` helper, which emits delimited sections for branch, dirty status, ahead/behind, last commit, and on-branch stash count:

```bash
~/.claude/skills/landscape/scripts/working-copy.sh
```

Output is grouped by `---SECTION---` markers. Parse and render from that.

Render:

```markdown
### 📍 Working copy

| Field | Value |
|-------|-------|
| Branch | fix/GE-649-device-cookie-combined |
| Dirty | clean _(or: 3 modified, 1 untracked)_ |
| vs upstream | ✅ in sync _(or: ⬆ 2 ahead, ⬇ 1 behind)_ |
| Last commit | `abc1234` commit subject (2h ago) |
```

Notes:
- If `@{u}` fails (no upstream), show `no upstream tracking`.
- If output is empty for dirty, show `clean`.
- **Stashes**: do NOT include a stash row in the table. Only surface stashes if there are stashes *on the current branch*. If non-empty, add a one-line footnote below the table:
  ```
  ⚠️ {N} stash(es) on this branch — run `git stash list` to review.
  ```
  Global stash count is not interesting — omit it.
- **Other worktrees**: the `OTHER-WORKTREES-UNSAFE` section lists only worktrees (excluding the current one) that have uncommitted changes or unpushed commits. If empty, render nothing — worktrees that are clean and pushed are not interesting. If non-empty, add a footnote below the table:
  ```
  ⚠️ Other worktrees with unsaved work:
  - `/path/to/other` on `fix/X` — 3 modified, 2 unpushed
  ```
  Omit the dirty/unpushed parts that are zero (e.g. `3 modified` alone, or `2 unpushed` alone).

### 5. Next step suggestion

After all blocks render, add a short footer with a concrete next step, picked from what's visible. Prefer the most load-bearing single action:

- If the current branch's PR is **approved, CI green, 0 threads, clean merge state** → suggest merging it (this unblocks stacked PRs).
- If the current branch's PR has **unresolved review threads** → suggest `/review-comments`.
- If the current branch's PR is **behind main** → suggest `/rebase-main`.
- If there is uncommitted work → suggest committing or stashing.
- If exactly one in-progress bead → suggest resuming it (show the ID).
- If nothing in progress and ready beads exist → suggest `/next`.
- Otherwise → suggest `/triage` or pulling a Jira ticket.

Format as one line:

```markdown
---
**Next:** _{suggestion}_
```

Single sentence. Don't list multiple options — pick one.

## Failure modes

Each block is independent — a failure in one must not prevent the others from rendering.

- **Not in a git repo**: skip the Working-copy block, print `_Not in a git repository._` in its place.
- **No Jira MCP configured**: skip the Jira block, print `_Jira MCP not configured._`.
- **gh not authenticated**: skip the PR block, print `_GitHub CLI not authenticated (run \`gh auth login\`)._`.
- **No beads in repo**: skip the Beads block, print `_No beads in this repo._`.

## Performance notes

- Run the git commands in parallel (single Bash call, or parallel tool calls).
- The PR section dominates runtime — that's why `/landscape quick` skips it.
- Don't re-render pr-status's "deltas since last check" — landscape is a snapshot, not a diff.
