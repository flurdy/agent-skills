---
name: today
description: Read-only activity recap for today or the previous workday across commits, PRs, Jira touches, and Beads in validated repositories; same-day mode adds current-session context.
allowed-tools: "Read,Bash(~/.agents/skills/wrap-up/scripts/activity.sh:*),mcp__jira__jira_get"
model-tier: standard
model: sonnet
effort: medium
version: "0.2.0"
author: "flurdy"
---

# Today — Activity recap

The single collection-and-rendering procedure for `/today` and its `/yesterday` alias. The
existing `/wrap-up` activity helper owns collection; this skill owns report layout and mode rules.
Use it for a catch-up or stand-up recap without ending the session or creating a handoff.

## Usage and mode

```text
/today                         # Same-day catch-up with current-session context
/today --previous-workday       # Objective previous-workday recap
/yesterday                     # Retained alias for the previous-workday mode
```

Accept no arguments (same-day mode) or exactly `--previous-workday`.
Reject unknown arguments and repeated flags before collecting.
The alias fixes the mode; do not infer it from conversation text.

## Read-only boundary

Never create or update a handoff. Never change Git state, Beads, Jira, settings, files, or remote
state. Do not commit, stash, push, sync, rename or exit the session, transition, comment, update
tracker status, or prompt for a mutation. This skill reports evidence only.

## Collect once, freshly on every invocation

The helper requires Python 3.10+ for date and JSON processing. Run the installed command for the
selected mode once, in the invoking repository or workspace:

| Mode | Command | Report header |
|---|---|---|
| Same-day | `~/.agents/skills/wrap-up/scripts/activity.sh --workspace` | `# Today — {DATE}` |
| Previous-workday | `~/.agents/skills/wrap-up/scripts/activity.sh --workspace --previous-workday` | `# Yesterday — {DATE}` |

The helper owns date selection, local-day boundaries, UTC conversion, and validated repository
resolution. Previous-workday means Friday when invoked on Monday and the preceding calendar day
otherwise. Use its `---DATE---` value; never recalculate the date in either entry point.

Read these helper sections:

- `---DATE---` — selected local `YYYY-MM-DD` used for the header and Jira query.
- `---WINDOW-START---` / `---WINDOW-END---` — exclusive-end local interval for commits and Beads.
- `---STATUS---`, `---SCOPE---`, `---REPOSITORIES---`, `---DIAGNOSTICS---` — Git availability,
  `WORKSPACE` or `CURRENT_REPO` scope, `{repository}|{absolute_path}` rows, and bounded omissions.
- `---COMMIT-STATUS---` — `{repository}|OK|NO_AUTHOR|ERROR`.
- `---COMMITS---` — `{repository}|{worktree}|{branch}|{sha}|{subject}|{when}`.
- `---GH-STATUS---`, `---GH-DIAGNOSTICS---`, `---PRS-CREATED---`, `---PRS-MERGED---`, and
  `---PRS-CLOSED-UNMERGED---` — status plus the three PR JSON arrays.
- `---BEADS-STATUS---` — `{repository}|OK|NO_BD|NO_BEADS_IN_REPO|ERROR`.
- `---BEADS-IN-PROGRESS---`, `---BEADS-CREATED-TODAY---`, `---BEADS-CREATED---`, and
  `---BEADS-CLOSED---` — `{repository}|{JSON array}` rows; select categories by mode below.

If the helper fails, report collection as unavailable. Do not invent a date/window or query Jira
without a valid `DATE`; same-day current-session context can still render.

### Jira

Use the exposed read-only Jira tool (`mcp__jira__jira_get` where available):

1. Fetch `/rest/api/3/myself` and project only `accountId`.
2. Query `/rest/api/3/search/jql` using the helper's selected date:

```text
issuekey IN updatedBy("{account-id}", "{DATE}", "{DATE}") ORDER BY updated DESC
```

Request fields `summary,status,issuetype,updated`, `maxResults: 20`, and project key, summary,
status, type, and updated. `updatedBy` supports day precision and an inclusive end date; repeating
`DATE` selects exactly that Jira calendar day. Do not add an `updated` field bound: it represents
only the latest update and can discard an issue touched during the selected day. This query covers
changes, comments, and transitions, not issues that were only read. A missing tool or either failed
call makes Jira unavailable; continue with other sources.

## Render

Use the mode's report header, then one scope line:

- Workspace: `_Scope: {N} validated repositories — {names}._`
- Current repository: `_Scope: current repository — {name}._`
- No Git repository: `_Git unavailable — commit and repository activity skipped._`

Same-day mode uses `## Objective activity today` before the objective subsections below.
Previous-workday mode goes directly to those subsections. Render them in this order, using each
table shape only for populated rows.

### Commits

```markdown
| Repo | Branch | SHA | Subject | When |
|------|--------|-----|---------|------|
```

Preserve repository ownership. Add the worktree name to Branch only when it distinguishes
worktrees of the same repository. For `NO_AUTHOR` or `ERROR`, retain successful rows and render one
bounded coverage note naming that repository.

### Pull requests

De-duplicate PRs across created, merged, and closed arrays; merged wins over created or closed.

```markdown
| Event | PR | Repo | Title |
|-------|----|------|-------|
```

For `UNAVAILABLE`, render `_GitHub unavailable — PR activity skipped._` For `ERROR`, retain
successful rows and render `_GitHub query failed — PR activity may be incomplete._` plus bounded
`GH-DIAGNOSTICS` entries.

### Jira touched

```markdown
| Key | Type | Status | Summary |
|-----|------|--------|---------|
```

For a failed or unavailable Jira query, render `_Jira unavailable — ticket activity skipped._`
Do not let that failure suppress other sources or same-day current-session context.

### Beads

Use repository-qualified rows in separate compact tables for populated categories:

| Mode | Categories in order | Created source |
|---|---|---|
| Same-day | In progress, Created today, Closed today | `BEADS-CREATED-TODAY` (excludes currently closed rows) |
| Previous-workday | Created, Closed | `BEADS-CREATED` (includes rows since closed) |

Both modes use `BEADS-CLOSED` for closed items. Same-day mode ignores the generic `BEADS-CREATED`
section. Ignore `BEADS-IN-PROGRESS` in previous-workday mode: current state is not historical
activity. Same-day **In progress** is also current state, not proof of work today or an achievement.

```markdown
| Repo | ID | Type | Pri | Title |
|------|----|------|-----|-------|
```

Skip repositories with `NO_BD` or `NO_BEADS_IN_REPO` silently. For `ERROR`, retain successful rows
and render one bounded coverage note naming the repository.

### Empty sources and coverage

- Same-day: omit empty PR, Jira, and Beads subsections when their sources are available. If no
  commits came from repositories with `OK` status, render `_No authored commits found today._`
- Previous-workday: retain each available source subsection with no matching rows and render
  `_No objective activity found for this source._` Do not render current in-progress Beads.

Never turn an unavailable source into an empty-success assertion or generalise one empty source
into a claim that the selected day was inactive. Render non-empty `DIAGNOSTICS` lines as concise
coverage notes. Use the helper's current-repository fallback when workspace discovery fails, and
show its diagnostic. No Git repository still permits GitHub, Jira, and same-day session context.
Each source is independent; a failure must not suppress successful evidence from the others.

## Current-session context

Same-day mode only: render this section after objective activity, beginning with
`_From this conversation only._` Summarise useful topics, decisions, completed work, discoveries,
and open threads from this conversation in 2–5 concise bullets. Do not attribute other sessions'
objective activity to this conversation. For a fresh or purely mechanical session, render
`_No substantive current-session context to add._`

Previous-workday mode must omit current-session context, even when invoked from a long session.
Keep either report concise and descriptive, without prescribing more work. End with:

```markdown
**Next:** Nothing required.
```
