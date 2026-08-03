---
name: today
description: Read-only same-day catch-up — current-session context plus objective commits, PRs, Jira touches, and Beads activity across the current repository or validated workspace repositories.
allowed-tools: "Bash(~/.agents/skills/wrap-up/scripts/activity.sh:*), mcp__jira__jira_get"
model-tier: standard
model: sonnet
effort: medium
version: "0.1.0"
author: "flurdy"
---

# Today — Same-day catch-up

Show what happened today without ending the session or creating a handoff. `/today` is the
lightweight, anytime complement to `/wrap-up`: it combines objective activity that may come
from several AI sessions with qualitative context from this conversation only.

## When to use

- You want a reminder of today's progress without running the end-of-session workflow.
- Several sessions or repositories may have contributed work today.
- You need a concise status recap with no mutation or required follow-up.

## Read-only boundary

Never create or update a handoff. Never change Git state, Beads, Jira, settings, files, or
remote state. Do not commit, stash, push, rename or exit the session, update tracker status,
or prompt for a mutation. This skill reports evidence only.

## Instructions

Re-fetch on every invocation. Run the activity helper in workspace mode:

```bash
~/.agents/skills/wrap-up/scripts/activity.sh --workspace
```

It reuses `/wrap-up`'s local-day filtering and GitHub queries, plus its authoritative
multi-repository resolver. It emits:

- `---DATE---` — local calendar date used by every same-day filter.
- `---WINDOW-START---` / `---WINDOW-END---` — the local, exclusive-end interval applied to commits and Beads records.
- `---SCOPE---` — `WORKSPACE` or `CURRENT_REPO`.
- `---REPOSITORIES---` — `{repository}|{absolute_path}` for validated repositories.
- `---DIAGNOSTICS---` — bounded discovery or member failures.
- `---COMMIT-STATUS---` — `{repository}|OK|NO_AUTHOR|ERROR`.
- `---COMMITS---` — `{repository}|{worktree}|{branch}|{sha}|{subject}|{when}`.
- `---GH-STATUS---`, `---GH-DIAGNOSTICS---`, and the three PR JSON sections used by `/wrap-up`.
- `---BEADS-STATUS---` — `{repository}|OK|NO_BD|NO_BEADS_IN_REPO|ERROR`.
- The three Beads sections — `{repository}|{JSON array}` for in-progress, open items
  created today (`BEADS-CREATED-TODAY`), and items closed today. The generic
  `BEADS-CREATED` section includes closed rows for historical consumers; ignore it here.

At the same time, query Jira for issues the current user changed today:

1. Fetch `/rest/api/3/myself` and project only `accountId`.
2. Query `/rest/api/3/search/jql` with:

```text
issuekey IN updatedBy("{account-id}", "{DATE}", "{DATE}") ORDER BY updated DESC
```

Request fields `summary,status,issuetype,updated`, `maxResults: 20`, and project key, summary,
status, type, and updated. `updatedBy` supports day precision and an inclusive end date; repeating
`DATE` selects exactly that Jira calendar day. It deliberately means changed, commented on, or
transitioned and does not claim to find tickets that were only read. If either Jira call fails,
render Jira as unavailable and continue.

Render the following sections in order.

## Header

```markdown
# Today — {YYYY-MM-DD}
```

## Objective activity today

Start with one scope line:

- Workspace: `_Scope: {N} validated repositories — {names}._`
- Current repository: `_Scope: current repository — {name}._`
- No Git repository: `_Git unavailable — commit and repository activity skipped._`

### Commits

If commits exist, render:

```markdown
### Commits

| Repo | Branch | SHA | Subject | When |
|------|--------|-----|---------|------|
```

Use the repository field to preserve ownership. Add the worktree name to Branch only when it
clarifies two worktrees of the same repository. For `NO_AUTHOR` or `ERROR`, render one bounded
coverage note naming that repository. If no commits were found from repositories with `OK`
status, render `_No authored commits found today._` Do not infer that the whole day was inactive.

### Pull requests

Use the same rules as `/wrap-up`: parse created, merged, and closed arrays; de-duplicate a PR
that appears in several arrays; merged wins over created or closed. Render only populated rows:

```markdown
### Pull requests

| Event | PR | Repo | Title |
|-------|----|------|-------|
```

If `GH-STATUS` is `UNAVAILABLE`, render `_GitHub unavailable — PR activity skipped._` If it is
`ERROR`, retain any successful rows and render `_GitHub query failed — PR activity may be
incomplete._` plus the bounded `GH-DIAGNOSTICS` entries. If GitHub is `OK` but all arrays are
empty, omit this subsection.

### Jira

Render Jira results only when populated:

```markdown
### Jira touched

| Key | Type | Status | Summary |
|-----|------|--------|---------|
```

If the Jira call fails or is unavailable, render `_Jira unavailable — ticket activity skipped._`
Do not let that failure suppress Git, GitHub, Beads, or current-session context.

### Beads

Beads evidence is repository-qualified. Render compact tables for populated categories in this
order: **In progress**, **Created today**, **Closed today**. Each table uses:

```markdown
| Repo | ID | Type | Pri | Title |
|------|----|------|-----|-------|
```

“In progress” is current state, not proof that the item changed today; label it exactly and do
not count it as an achievement. Skip repositories with `NO_BD` or `NO_BEADS_IN_REPO` silently.
For `ERROR`, render one bounded note naming the repository.

After the objective subsections, render each non-empty `DIAGNOSTICS` line as a concise coverage
note. Never turn an unavailable source into an assertion that no activity occurred.

## Current-session context

Render this heading exactly:

```markdown
## Current-session context

_From this conversation only._
```

Summarise the current conversation in 2–5 concise bullets covering only useful topics,
decisions, completed work, discoveries, and open threads. This section may explain work that has
not produced a commit or tracker change, but it must not attribute other sessions' objective
activity to this conversation. If this is a fresh or purely mechanical session, say
`_No substantive current-session context to add._`

Each source is independent. A failure or empty result in one source never prevents the remaining
sections from rendering. Keep the complete output concise and descriptive rather than prescribing
more work. End with:

```markdown
**Next:** Nothing required.
```

## Failure modes

- Workspace discovery fails or is incomplete: use the helper's current-repository fallback and
  show its diagnostic.
- One repository cannot be read: show successful repositories and one bounded omission note.
- GitHub, Jira, or Beads is unavailable or errors: show the source-specific note and continue.
- No Git repository: still show GitHub, Jira, and current-session context when available.
