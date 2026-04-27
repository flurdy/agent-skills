---
name: tracking-sweep
description: Portfolio-wide drift sweep across Jira, beads, and GitHub PRs. Cross-references your assigned Jira tickets, in_progress/ready beads, and recent PRs to flag status drift, orphan work, parent-moved beads, and stale items. Read-only — produces recommendations only. Use ad-hoc when you want a "where is everything" reconciliation, separate from /landscape's passive snapshot.
allowed-tools: "Bash(git:*), Bash(bd list:*), Bash(bd show:*), Bash(bd memories:*), Bash(bd ready:*), Bash(bd stale:*), Bash(bd orphans:*), Bash(gh:*), Bash(date:*), Bash(grep:*), Bash(awk:*), Bash(sort:*), Bash(uniq:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-list-open.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-list-closed.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-details.sh:*), mcp__jira__jira_get"
model: sonnet
effort: medium
version: "0.1.0"
author: "flurdy"
---

# Tracking Sweep — Portfolio Drift Reconciliation

Cross-reference your **assigned Jira tickets**, **beads**, and **GitHub PRs** to flag drift across the portfolio. Read-only. Recommendations only — never auto-posts comments, never moves Jira status, never closes beads.

## Relationship to other tools

- **`/landscape`** is passive display: lists everything in three sections, side-by-side. Doesn't cross-reference.
- **`tracking-auditor`** (agent) is per-branch depth: "does THIS branch's diff match its ticket?" Used as a PR-boundary gate.
- **`/tracking-sweep`** (this skill) is portfolio breadth: "across everything in flight, where's the drift?" Used ad-hoc.

If a single branch looks suspicious during the sweep, recommend invoking `tracking-auditor` for that branch — don't replicate its logic.

## Usage

```bash
/tracking-sweep              # Full sweep
/tracking-sweep quick        # Skip stale-beads + PR-detail fetches (faster)
```

## Output

A drift report. Items that match across all three systems are NOT listed — only deviations. If there's no drift, the report is short. That's the point.

## Procedure

Run sections 1–3 in parallel (independent data fetches). Sections 4+ are sequential cross-referencing.

### 1. Fetch Jira tickets

Tickets assigned to current user, not Done. Include the sprint custom field (`customfield_10020`) — the table both displays it and orders by it:

```
mcp__jira__jira_get
  path: /rest/api/3/search/jql
  queryParams:
    jql: assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC
    fields: summary,status,issuetype,priority,updated,parent,resolution,customfield_10020
    maxResults: 50
  jq: issues[*].{key: key, summary: fields.summary, status: fields.status.name, type: fields.issuetype.name, priority: fields.priority.name, updated: fields.updated, parent: fields.parent.key, sprint: fields.customfield_10020}
```

The `sprint` field is an array of sprint objects. For each ticket extract the **active** sprint's name (first entry where `state == "active"`), else the most recent. Empty/null → `—` (no sprint — usually backlog).

If the result mentions a parent epic (e.g. `GE-280`), **also fetch its other children** so beads referencing sibling tickets can be resolved:

```
jql: parent = {epic-key}
fields: summary,status,assignee
```

### 2. Fetch beads

```bash
bd list --status=in_progress
bd list --status=open
bd memories                                    # for parking notes
```

In `quick` mode skip:
```bash
bd stale                                        # >14d no activity
bd orphans                                      # broken dependencies
```

### 3. Fetch PRs

Reuse pr-status scripts (don't re-implement):

```bash
~/.claude/skills/pr-status/scripts/gh-pr-list-open.sh
~/.claude/skills/pr-status/scripts/gh-pr-list-closed.sh "" 14   # last 14 days
```

In `quick` mode, skip per-PR detail fetches.

### 4. Extract ticket keys

For each PR (title + branch name) and each bead (title + description), extract Jira keys with regex `[A-Z]+-[0-9]+`. Build three maps:

- `pr_by_key`: ticket-key → list of PRs (open + recently merged)
- `bead_by_key`: ticket-key → list of beads
- `jira_by_key`: ticket-key → ticket (your assigned set + sibling-epic children fetched in step 1)

Beads or PRs with no extractable key go into `orphans`.

### 5. Read parking notes

Run `bd memories` and look for entries that mention parked work (keywords: `park`, `paused`, `behind`, `waiting on`, `intentional hold`). Build a `parked_keys` set of ticket keys mentioned in parking memories. These suppress drift findings — see the "Parking" rule below.

### 6. Detect drift

Apply each rule. For each finding, record severity (❌ blocker / ⚠️ warning / ℹ️ info) and a concrete recommendation.

#### Rule A — Status mismatch (Jira ↔ reality)

For each Jira ticket assigned to you:

- Status is **In Progress** but **all** linked PRs are merged AND **no** in_progress bead references it AND **no** open bead references remaining work → ⚠️ "Likely complete; transition to Test/Review or Done."
- Status is **In Progress** but no PRs and no in_progress beads reference it → ⚠️ "Marked In Progress but no active work — start, reassign, or move back to Ready."
- Status is **Backlog / Ready to Work** but a bead is `in_progress` for it OR a PR is open for it → ⚠️ "Move to In Progress."
- Status is **Code Review** but no PR is open AND no PR was recently merged for it → ⚠️ "Code Review without an open PR — was it merged? May need transition."
- Status is **Code Review / Test/Review** with all PRs merged AND no follow-up beads open → ⚠️ "Ready for Done?"
- Status is **Done** but a bead is still `in_progress` or `open` for it → ⚠️ "Jira closed but bead still active — close bead or split off the remainder."

#### Rule B — Orphan PRs

PRs (open OR recently merged) with no extractable Jira key in title/branch → ❌ "Untracked PR — link to a ticket or document why it's unticketed."

PRs with a Jira key that isn't in your assigned set or your epic's siblings → ℹ️ "PR references {key} which isn't yours — may be cross-team work, OK if intentional."

#### Rule C — Orphan beads

Open beads with no extractable Jira key → ⚠️ "Bead has no Jira link — add one or document intentional local-only scope."

Open beads referencing a Jira key that resolves to **Done** → ⚠️ "Parent {key} is Done; close this bead or re-link to a follow-up ticket."

Open beads referencing a Jira key that doesn't exist (404) → ❌ "Bead references {key} which doesn't exist — fix or close."

#### Rule D — Stale work (skipped in quick mode)

`bd stale` output → ℹ️ "Bead has had no activity in N days — close, defer, or progress."

`bd orphans` output → ❌ "Bead has a broken dependency — fix or close."

#### Rule E — Parking suppression

Before emitting any Status-mismatch finding from Rule A: check `parked_keys` from step 5. If the ticket key appears in a parking memory, **suppress** the finding and instead list it under "✅ Honoured parking" with a one-line note quoting the memory.

Be conservative: only suppress if the parking note clearly names the ticket. If the memory is vague, still emit the finding but mark severity as ℹ️ and add "_Possibly parked — check memory_".

### 7. Render report

Keep it tight. Skip empty sections. Order by severity.

Always render the **assigned-tickets reference table first**, then the drift sections. The table is a baseline so the user can sanity-check what was scoped and visually correlate drift findings against their full ticket list.

```markdown
## Tracking Sweep — {YYYY-MM-DD HH:MM}

**Scope:** {N} Jira tickets · {M} beads (in_progress/open) · {K} PRs (open + last 14d)

### 📋 Assigned Jira tickets

Mirror the column style of `/landscape`'s Jira table, extended with two cross-reference columns — **PRs** and **Beads** — which are the unique value of this skill.

| Sprint | Key | Type | Pri | Status | Updated | PRs (open/merged) | Beads (in_p/open) | Summary |
|--------|-----|------|-----|--------|---------|-------------------|-------------------|---------|
| Sprint 42 | [GE-649](…) | Task | P3 | Code Review | 2h | 1 / 9 | 0 / 0 | FE \| Ensure Session Id… |
| Sprint 42 | [GE-1107](…) | Task | P1 | In Progress | 3h | 0 / 3 | 0 / 0 | FE \| Add Amplitude events… |
| Sprint 41 | [GE-1121](…) | Task | P2 | Code Review | 7d | 0 / 0 | 0 / 0 | FE \| Send Device ID & Session ID… |
| — | [GE-678](…) | Task | P2 | Ready to Work | 4d | 0 / 0 | 0 / 0 | BE \| Update API Headers |
```

Table rules:
- **Sprint**: active sprint name. Truncate purely-numeric names to `S{N}` if the column gets wide. `—` if none.
- **Key**: markdown link to Jira (e.g. `https://bluelightcard.atlassian.net/browse/{key}`).
- **Type**: Jira issuetype name (Task / Story / Bug / Sub-task).
- **Pri**: shortened — `P1 Critical` → `P1`, `P2 High` → `P2`, etc.
- **Updated**: relative time (`2h`, `4d`).
- **PRs (open/merged)**: PRs whose title or branch references this key (open PRs + merged in last 14d).
- **Beads (in_p/open)**: beads referencing this key.
- **Summary**: truncated to ~50 chars.
- Rows whose counts are all zero are still listed — often where drift hides.

**Ordering** (primary → secondary):

1. **Sprint group**: current/active sprint first, then older sprints in descending order, then `—` (no sprint) last. Older-sprint rows are themselves a drift signal — carryover work.
2. **Within each sprint, by status group**: In Progress → Code Review → Test/Review → Backlog → Ready to Work.
3. **Within status, by priority** (P0 → P4), then by `updated` descending.

After the table, add a one-line sprint summary like `/landscape` does: `_All 6 in Sprint 42._` or `_Spans 2 sprints: Sprint 42 (4), Sprint 41 (2), no-sprint (1)._` — answers "is this portfolio focused or scattered?" at a glance.

After the table, render drift findings:

```markdown
---

### ❌ Blockers ({count})
- **{KEY}** — {one-line description}
  → _Recommendation:_ {concrete action}

### ⚠️ Drift ({count})
Group by category if more than 3 items:

**Status mismatches**
- **GE-1107** (In Progress) — all 3 linked PRs merged ≥10d ago, no in_progress bead.
  → _Recommendation:_ comment summarising shipped scope, transition to Test/Review (or confirm parking).

**Orphan beads**
- `blc-2-xyz` — no Jira link.
  → _Recommendation:_ link to a ticket or document local-only scope.

**Parent moved**
- `blc-2-abc` → GE-999 (Done).
  → _Recommendation:_ close bead.

### ℹ️ Info ({count})
- {Lower-priority observations.}

### ✅ Honoured parking
- **GE-1107, GE-1344** — parked behind GE-649 cookie work (per memory `regularly-cross-check-jira-ticket-status-against-beads`).

---

**Summary:** {N drift items} · {N blockers} · {N parked correctly}
**Suggested next step:** {one concrete action — usually the highest-severity item or a /tracking-auditor invocation for a suspicious branch}
```

Drift findings should reference the table by key (e.g. "GE-1121"), letting the user glance up to see the full row rather than restating context.

If there's no drift at all:

```markdown
## Tracking Sweep — {YYYY-MM-DD HH:MM}

✅ No drift. Jira, beads, and PRs are aligned across {N} tickets, {M} beads, {K} PRs.
```

## Operating rules

- **Read-only.** Never call `mcp__jira__jira_post`, `bd close`, `bd update`, or `gh pr edit`. The skill recommends; the user acts.
- **Don't restate matches.** A ticket whose status matches its beads/PRs is uninteresting. Skip it.
- **Don't speculate beyond the data.** "Marked In Progress but no work" is fine. "User abandoned this" is not.
- **Honour parking.** Always check `bd memories` for parking notes before flagging status drift on a ticket. If parked, list under "Honoured parking" instead of "Drift."
- **Defer to tracking-auditor for branch-level depth.** If a single branch looks suspicious (e.g. an open PR with significant scope concerns), suggest invoking `tracking-auditor` rather than analysing the diff here.
- **Be fast.** This is a sweep, not an investigation. If a check needs >30s of digging (e.g. fetching every PR's individual reviews), defer it to `/pr-status`.
- **Each section is independent.** A failed Jira fetch must not break the beads or PR sections. Render `_Jira unavailable_` and continue.

## Failure modes

- **No Jira MCP**: skip Rules A and the parking-suppression check that depends on it. Render `_Jira MCP not configured — skipping Jira drift checks._`. Beads and PR drift checks still run.
- **No beads (`bd` missing or no `.beads/` dir)**: skip Rules C, D, and the parking-suppression memory lookup. Run Rules A and B only.
- **Not in a git repo / no `gh`**: skip Rule B and PR-related parts of Rule A. Run Jira+beads checks only.
