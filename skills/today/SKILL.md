---
name: today
description: Read-only activity recap for today, the previous workday, or an explicit date/range across commits, PRs, Jira touches, and Beads; same-day mode adds current-session context.
allowed-tools: "Read,Bash(~/.agents/skills/wrap-up/scripts/activity.sh:*),mcp__jira__jira_get"
model-tier: economy
model: sonnet
effort: high
version: "0.3.0"
author: "flurdy"
---

# Today — Activity recap

The single collection-and-rendering procedure for `/today` and the `/yesterday` prompt. The existing
`/wrap-up` activity helper owns collection; this skill owns report layout and mode rules.
Use it for a catch-up or stand-up recap without ending the session or creating a handoff.

## Usage and mode

```text
/today                         # Same-day catch-up with current-session context
/today --previous-workday       # Objective previous-workday recap
/today --date 2026-10-26        # One explicit local day
/today --since 2026-10-23 --until 2026-10-26  # Inclusive range
/today --since 2026-10-23       # Through today
/yesterday                     # Pi/Claude prompt for previous-workday mode
```

Accept no arguments (same-day mode), exactly `--previous-workday`, or one explicit selector:
`--date YYYY-MM-DD` or `--since YYYY-MM-DD [--until YYYY-MM-DD]`.
The end defaults to today; both endpoints are inclusive, at most 31 inclusive local days.
Reject invalid calendar dates, non-ISO dates, future dates, inverted ranges, and `--until` alone.
Conflicting selectors are rejected; explicit dates/ranges never add current-session context,
even if they include today. `--include-weekend` is not supported: select the Friday–Sunday range.
Reject unknown arguments and repeated flags before collecting.
The `/yesterday` prompt prepends `--previous-workday` and forwards any supplied arguments unchanged
for this validation; never infer the mode from conversation text. Codex uses
`/today --previous-workday` because this repository does not install prompt templates there.

## Read-only boundary

Never create or update a handoff. Never change Git state, Beads, Jira, settings, files, or remote
state. Do not commit, stash, push, sync, rename or exit the session, transition, comment, update
tracker status, or prompt for a mutation. This skill reports evidence only.

## Collect once, freshly on every invocation

The helper requires Bash 4+, Python 3.10+ (standard library only), and Git 2.37+ for
`--since-as-filter`. GitHub CLI `gh` supplies PRs and optional account email identities;
missing/failed identity lookup falls back to local identities with a coverage note.
Missing `bd` skips Beads; source failures remain isolated. Run the installed command for the
selected mode once, in the invoking repository or workspace:

| Mode | Command | Report header |
|---|---|---|
| Same-day | `~/.agents/skills/wrap-up/scripts/activity.sh --workspace` | `# Today — {DATE-LABEL}` |
| Previous-workday | `~/.agents/skills/wrap-up/scripts/activity.sh --workspace --previous-workday` | `# Yesterday — {DATE-LABEL}` |
| Explicit date/range | `~/.agents/skills/wrap-up/scripts/activity.sh --workspace {validated selector arguments}` | `# Activity — {DATE-LABEL}` |

The helper owns date selection, local-day boundaries, UTC conversion, and validated repository
resolution. Previous-workday means Friday when invoked on Monday and the preceding calendar day
otherwise. Use its `---DATE---` value; never recalculate the date in either entry point.

Read these helper sections:

- `---DATE---` / `---DATE-END---` — inclusive local `YYYY-MM-DD` endpoints for Jira.
- `---DATE-LABEL---` — weekday-labelled day or range for the header, e.g.
  `Mon 2026-10-26` or `Fri 2026-10-23 – Mon 2026-10-26`; use this verbatim, not a guessed weekday.
- `---WINDOW-START---` / `---WINDOW-END---` — exclusive-end local interval for commits and Beads.
- `---STATUS---`, `---SCOPE---`, `---REPOSITORIES---`, `---DIAGNOSTICS---` — Git availability,
  `WORKSPACE` or `CURRENT_REPO` scope, `{repository}|{absolute_path}` rows, and bounded omissions.
- `---COMMIT-STATUS---` — `{repository}|OK|NO_AUTHOR|ERROR`.
- `---COMMIT-DIAGNOSTICS---` — identity gaps, ref failures and cached-history coverage limits.
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
issuekey IN updatedBy("{account-id}", "{DATE}", "{DATE-END}") ORDER BY updated DESC
```

Request fields `summary,status,issuetype,updated`, `maxResults: 100`, and project key, summary,
status, type, and updated. Follow every `nextPageToken` with the same query until `isLast: true`
or no next token; deduplicate by issue key. A repeated token or failed later page means partial
coverage: keep earlier rows and report the gap, never call them complete.
`updatedBy` supports day precision and an inclusive end date; equal endpoints select one day.
Do not add an `updated` field bound: it represents only the latest update and can discard an issue
touched during the selected range. Jira calendar days use the Jira account timezone, which may
differ from the helper's local timezone; disclose that coverage distinction.
This query covers changes, comments, and transitions, not issues that were only read.
A missing tool or failed identity/first-page call makes Jira unavailable; continue with other sources.

## Render

Use the mode's report header, then one scope line:

- Workspace: `_Scope: {N} validated repositories — {names}._`
- Current repository: `_Scope: current repository — {name}._`
- No Git repository: `_Git unavailable — commit and repository activity skipped._`

Same-day mode uses `## Objective activity today` before the objective subsections below.
Previous-workday and explicit-selector modes go directly to those subsections. Render them in this order, using each
table shape only for populated rows.

### Commits

```markdown
| Repo | Branch | SHA | Subject | When |
|------|--------|-----|---------|------|
```

Preserve repository ownership and the helper's SHA deduplication within each repository. Add the
worktree name to Branch only when it distinguishes worktrees of the same repository. Keep the
absolute local `When` value, including weekday and offset; never replace it with relative ages.
For multi-day ranges, group commits by local day with headers such as `### Mon 2026-10-26`;
every date in headers and day groups includes its weekday. For `NO_AUTHOR` or `ERROR`, retain
successful rows and render one bounded coverage note naming that repository.

Collection scans all local branches, linked worktree HEADs (including detached HEADs), and the
cached `origin/HEAD` default ref; absent that pointer, cached `origin/main` and `origin/master`
are fallback candidates, not proven defaults. Match exact author emails from effective `user.email`,
repeatable Git config `activity.authorEmail`, and the authenticated GitHub account's public email,
verified private email aliases and noreply identities. No regex/name matching and no configuration writes are performed.
Email identity is attribution evidence, not proof of who physically wrote a change.

Use **committer date**, not author date: a squash appears on its merge day even when authored
earlier. Read cached refs only: no fetch or network freshness check. The helper reports when a
local default branch is behind its cached origin ref, but cannot know whether origin itself has
advanced. Unfetched commits and commits no longer reachable from scanned refs may be missing.
Render `COMMIT-DIAGNOSTICS` concisely; never claim exhaustive remote history.

### Pull requests

De-duplicate PRs across created, merged, and closed arrays; merged wins over created or closed.

```markdown
| Event | PR | Repo | Title |
|-------|----|------|-------|
```

For `UNAVAILABLE`, render `_GitHub unavailable — PR activity skipped._` For `ERROR`, retain
successful rows and render `_GitHub query failed — PR activity may be incomplete._` plus bounded
`GH-DIAGNOSTICS` entries. Queries allow up to 1,000 results each; reaching that cap is
reported as potentially incomplete, even if timestamp filtering leaves fewer rows.

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
| Explicit date/range | Created, Closed | `BEADS-CREATED` (includes rows since closed) |

Both modes use `BEADS-CLOSED` for closed items. Same-day mode ignores the generic `BEADS-CREATED`
section. Ignore `BEADS-IN-PROGRESS` in previous-workday mode: current state is not historical
activity. Explicit-selector mode also ignores current in-progress state.
Same-day **In progress** is also current state, not proof of work today or an achievement.

```markdown
| Repo | ID | Type | Pri | Title |
|------|----|------|-----|-------|
```

Skip repositories with `NO_BD` or `NO_BEADS_IN_REPO` silently. For `ERROR`, retain successful rows
and render one bounded coverage note naming the repository.

### Empty sources and coverage

- Same-day: omit empty PR, Jira, and Beads subsections when their sources are available.
- Previous-workday: retain each available source subsection with no matching rows. Explicit
  date/range mode does the same. Do not render current in-progress Beads in either mode.
- For empty commits in any mode, if at least one repository was searched successfully, render
  `_No matching commits by committer date on {DATE-LABEL} in {N} successfully searched repositories._`
  Count only `OK` repositories; failures/identity gaps need separate coverage notes.
- Other empty sources name the search and dates: `_No authored PR creation/merge/closure events
  on {DATE-LABEL}._`, `_No Jira issues touched by this account on {DATE-LABEL} (Jira timezone)._`,
  or `_No Beads created/closed on {DATE-LABEL} in {N} successfully searched stores._`
  Use “during” rather than “on” for ranges. Empty available sources are not unavailable sources.

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
Explicit-selector mode must also omit it; session context is never historical evidence.
Keep either report concise and descriptive, without prescribing more work. End with:

```markdown
**Next:** Nothing required.
```
