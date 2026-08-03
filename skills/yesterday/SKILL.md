---
name: yesterday
description: Read-only previous-workday stand-up recap across objective commits, PRs, Jira touches, and Beads activity in validated workspace repositories; selects Friday when run on Monday.
allowed-tools: "Bash(~/.agents/skills/wrap-up/scripts/activity.sh:*), mcp__jira__jira_get"
model-tier: standard
model: sonnet
effort: medium
version: "0.1.0"
author: "flurdy"
---

# Yesterday — Previous-workday stand-up recap

Summarise objective activity from the previous workday. This is the morning stand-up companion to
`/today`: it reports recorded activity without ending the session, creating a handoff, or adding
current-session narrative.

## Date rule

The selected local date is Friday when invoked on Monday and the preceding calendar day otherwise.
The activity helper owns this calculation and the bounded interval used by every source. It converts
that local interval to UTC when filtering GitHub and Beads timestamps.

## Read-only boundary

Never create or update a handoff. Never change Git state, Beads, Jira, settings, files, or remote
state. Do not commit, stash, push, sync, transition, comment, or prompt for a mutation. This skill
reports evidence only.

## Collect activity

The helper requires Python 3.10+ for date and JSON processing. GitHub and Beads remain optional
sources and degrade independently when their CLIs or repositories are unavailable.

Run:

```bash
~/.agents/skills/wrap-up/scripts/activity.sh --workspace --previous-workday
```

Read these sections:

- `---DATE---` — selected local `YYYY-MM-DD`.
- `---WINDOW-START---` / `---WINDOW-END---` — exclusive-end local interval applied to commits and
  Beads records.
- `---SCOPE---`, `---REPOSITORIES---`, and `---DIAGNOSTICS---` — validated repository coverage.
- `---COMMIT-STATUS---` and `---COMMITS---` — authored commits within the interval.
- `---GH-STATUS---`, `---GH-DIAGNOSTICS---`, and the three PR JSON sections — PRs created, merged,
  or closed on the selected date.
- `---BEADS-STATUS---`, `---BEADS-CREATED---`, and `---BEADS-CLOSED---` — repository-qualified Beads
  records bounded to the selected date. Ignore `BEADS-IN-PROGRESS`; current state is not evidence
  of previous-workday activity.

At the same time, query Jira for issues changed by the current user on `DATE`:

1. Call `mcp__jira__jira_get` with `/rest/api/3/myself` and project only `accountId`.
2. Use that account ID in the supported `updatedBy` function:

```text
issuekey IN updatedBy("{account-id}", "{selected-date}", "{selected-date}")
ORDER BY updated DESC
```

`updatedBy` supports day precision and an inclusive end date, so the repeated selected date means
exactly that Jira calendar day. Do not add an `updated` field bound: that field is only the issue's
latest update and can incorrectly discard an issue the user touched during the selected day.

Call `/rest/api/3/search/jql` with fields `summary,status,issuetype,updated`, `maxResults: 20`, and
project the result to key, summary, status, type, and updated. `updatedBy` includes changes,
comments, and transitions; do not claim it finds issues that were only read. If `/myself` or the
search fails, render Jira as unavailable and continue with the other sources.

Each source is independent. A GitHub, Jira, Beads, repository, or discovery failure must not
suppress successful evidence from other sources.

## Render

Start with:

```markdown
# Yesterday — {YYYY-MM-DD}

_Scope: {N} validated repositories — {names}._
```

Use the same fallback scope wording as `/today` when workspace or Git discovery is unavailable.
Then render these subsections in order.

### Commits

For populated commits:

```markdown
| Repo | Branch | SHA | Subject | When |
|------|--------|-----|---------|------|
```

Preserve repository ownership. Add the worktree name to Branch only when it distinguishes multiple
worktrees of one repository. Render bounded coverage notes for `NO_AUTHOR` or `ERROR` repositories.

### Pull requests

De-duplicate PRs found in several arrays; merged wins over created or closed.

```markdown
| Event | PR | Repo | Title |
|-------|----|------|-------|
```

For `UNAVAILABLE`, say GitHub was unavailable. For `ERROR`, retain successful rows and include the
bounded diagnostics.

### Jira touched

```markdown
| Key | Type | Status | Summary |
|-----|------|--------|---------|
```

If Jira fails, say it was unavailable and continue.

### Beads

Render separate **Created** and **Closed** tables when populated:

```markdown
| Repo | ID | Type | Pri | Title |
|------|----|------|-----|-------|
```

Skip `NO_BD` and `NO_BEADS_IN_REPO` silently. Name repositories with `ERROR` in one bounded note.
Do not render current in-progress Beads.

If an available source has no matching rows, retain its subsection and render
`_No objective activity found for this source._` Never generalise one empty source into a claim
that the selected workday was inactive. Render non-empty discovery diagnostics as concise coverage
notes.

Do not add a current-session section or prescribe follow-up work. End with:

```markdown
**Next:** Nothing required.
```
