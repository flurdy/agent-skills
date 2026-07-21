---
name: pr-status
description: Show enriched status of your open PRs — CI checks, approvals, unresolved review threads, and linked Jira discussion, with transition-driven suggested next actions.
allowed-tools: "Bash(~/.agents/skills/pr-status/scripts/gh-pr-list-open.sh:*), Bash(~/.agents/skills/pr-status/scripts/gh-pr-list-closed.sh:*), Bash(~/.agents/skills/pr-status/scripts/gh-pr-details.sh:*), Bash(~/.agents/skills/pr-status/scripts/gh-pr-checks.sh:*), Bash(~/.agents/skills/pr-status/scripts/gh-pr-reviews.sh:*), Bash(~/.agents/skills/pr-status/scripts/gh-pr-threads.sh:*), Bash(~/.agents/skills/pr-status/scripts/gh-pr-merge-state.sh:*), Bash(gh pr list:*), Bash(gh pr checks:*), Bash(gh pr view:*), Bash(gh api:*), Bash(gh search:*), Bash(date:*), mcp__jira__jira_get"
model-tier: standard
model: sonnet
effort: medium
version: "1.12.0"
author: "flurdy"
---

# PR Status

Show enriched status for all open PRs created by you across your GitHub org: CI checks, approvals, unresolved review threads, and linked Jira discussion. Also shows recently closed PRs.

The GitHub org is auto-detected from the current repo's `origin` remote, or can be overridden via `PR_STATUS_ORG` env var.

**The output of this skill is the rendered dashboard** (steps 3–6). Fetching without rendering is not a valid run.

## Usage

```
/pr-status
```

## Instructions

Re-run the fetch scripts and `date` on every invocation, even seconds after the last one — never reuse earlier output or extrapolate the timestamp.

### 1. Fetch

Open PRs (org-wide), one JSON object per line `{number, title, owner, repo}`:

```bash
~/.agents/skills/pr-status/scripts/gh-pr-list-open.sh
```

Recently closed PRs (3-day lookback, 4 on Tuesdays; optional second arg overrides), one JSON object per line `{number, title, owner, repo, closedAt}`:

```bash
~/.agents/skills/pr-status/scripts/gh-pr-list-closed.sh
```

### 2. Fetch PR details

Group the PRs (open and closed) by `owner/repo`; one batch GraphQL call per group:

```bash
~/.agents/skills/pr-status/scripts/gh-pr-details.sh {owner} {repo} {number1} {number2} ...
```

Output is a JSON array, one object per PR:

```json
[
  {
    "number": 123,
    "base": "main",
    "isDraft": false,
    "mergeState": "CLEAN",
    "reviewDecision": "APPROVED",
    "approvers": ["alice"],
    "unresolvedThreads": 2,
    "checksState": "SUCCESS",
    "lastPush": "2026-04-15T09:30:00Z",
    "mergeCommitSha": "abc123...",
    "mergeCommitAt": "2026-04-15T10:00:00Z",
    "mainChecksState": "SUCCESS",
    "readyAt": "2026-04-14T15:32:11Z"
  }
]
```

Map `checksState` values: `SUCCESS` → ✅ / `FAILURE` or `ERROR` → ❌ / `PENDING` or `EXPECTED` → ⏳ / null → `—`

If the batch script is unavailable, the per-PR scripts in the same directory (`gh-pr-checks.sh`, `gh-pr-reviews.sh`, `gh-pr-threads.sh`, `gh-pr-merge-state.sh`) or plain `gh pr view/checks` cover the same fields.

### 3. Fetch linked Jira discussion

For every distinct Jira key found while rendering (open PRs: branch first, then title; recently closed PRs: title; using `/[A-Z]+-\d+/`), fetch its newest Jira comment. Include both open and recently closed PRs when they carry a ticket key; fetch each key once, even if multiple PRs use it. Calls may run in parallel:

```
mcp__jira__jira_get
  path: /rest/api/3/issue/{key}/comment
  queryParams:
    orderBy: -created
    maxResults: 1
  jq: '{total: .total, latest: (.comments[0] // null | if . == null then null else {author: .author.displayName, accountId: .author.accountId, created: .created} end)}'
```

For a key with comments, render `💬 {total} · {latest author first name or @accountId} · {relative age}`. Render `—` for zero comments and `?` if its lookup fails. Do not show comment bodies in this status dashboard. Jira comment failures are non-fatal: render all PR data and add `_Some linked Jira discussion could not be fetched._` beneath the affected table(s).

### 4. Render as tables

Before the tables, output a timestamp line: `_Checked at HH:MM:SS_` in **local** time, 24h (`date '+%H:%M:%S'`, not `date -u`). Relative-time math against `lastPush` / `readyAt` / `closedAt` works in UTC since those are `Z`-suffixed; only the displayed timestamp is local.

**Recently closed** — render first, one table with a **Repo** column. Skip the section if the closed list is empty.

#### Recently closed

| PR | Repo | Ticket | Jira 💬 | Title | Status | CI | Ready | Wait | Closed |
|----|------|--------|---------|-------|--------|----|-------|------|--------|

- **PR**: markdown link `[#123](https://github.com/{owner}/{repo}/pull/123)`
- **Repo**: repository name
- **Ticket**: Jira ID matched by `/[A-Z]+-\d+/` against the PR title, or `—`
- **Status**: 🔀 merged / 🗑️ closed unmerged — emoji only
- **CI**: post-merge checks on the merge commit (`mainChecksState`), only if merged and `mergeCommitAt` is within the last 2 days — otherwise `—`
- **Ready**: relative time since `readyAt` (short units: `Nm`, `Nh`, `Nd`)
- **Wait**: `closedAt - readyAt` — how long the PR waited for review/merge
- **Closed**: relative time since close

**Open PRs** — render after closed, grouped by repo: heading `#### Open — {repo}` then a table per repo that has open PRs.

| PR | Ticket | Jira 💬 | Title | Branch | Target | Ready | Push | Sync | CI | Approved | Threads | LGTM |
|----|--------|---------|-------|--------|--------|-------|------|------|----|----------|---------|------|

- **PR**: markdown link as above
- **Ticket**: Jira ID matched against branch name first, then title, or `—`
- **Branch**: head branch minus conventional-commit prefix and ticket prefix (`feat/AB-1107-cta-clicked-event` → `cta-clicked-event`); truncate past ~30 chars with `…`
- **Target**: base branch. `main`/`master` are default branches — plain text. Anything else is a stacked PR: prefix with 📌
- **Sync**: from `mergeState` when base is `main`/`master`: `CLEAN`/`UNSTABLE` → ✅, `BEHIND` → ⚠️ behind, `DIRTY` → 💥 conflict, other → `—`. Stacked PRs (📌) → `—`
- **CI**: ✅ / ❌ / ⏳ — emoji only
- **Ready**: 🚧 if `isDraft`, else relative time since `readyAt`
- **Push**: relative time since `lastPush`
- **Approved**: one ✅ per approver when `reviewDecision` is `APPROVED`. `REVIEW_REQUIRED` with approvers → stale approvals, one ☑️ each. `CHANGES_REQUESTED` → 👎. No approvers, no changes requested → 🔔 (awaiting review; `—` for drafts)
- **Threads**: `💬 N` if N > 0, else `—`
- **LGTM**: 🚀 if not draft, `APPROVED`, CI `SUCCESS`, sync ✅, zero threads, and `mergeState` `CLEAN`; else 🚧

Truncate titles: ~50 chars in the closed table, ~25 in the open table (13 columns — wide rows break Claude Code's table renderer).

### 5. Summarise changes

After the tables, list deltas since the last check in this session as bullets (e.g. `#6142 CI: ❌ → ✅`). Treat an increase in a linked ticket's comment total as a delta, e.g. `AB-649 Jira discussion: 2 → 3 (Jane, 40m)`. Do not report a count decrease as a discussion update. Otherwise say "No changes." Render both tables in full either way — the point of repeated checks is current state at a glance.

### 6. Suggest next actions (transition-driven)

Surface a **Suggested actions** bullet list — copy-pasteable commands for PRs that *just became* actionable this tick. Read-only: point at commands, never run them.

Fire on transitions, not standing state: on the first check of a session list the currently-actionable PRs as baseline; on later ticks list a PR only when it crosses into an actionable state.

| Transition this tick | Suggested command |
|---|---|
| → 🚀 LGTM (newly mergeable) | `/ready-to-merge {n}` |
| unresolved threads increased, or → 👎 changes requested | `/review-comments {n}` |
| → ⚠️ behind (fell behind base) | `/rebase-main` (on that PR's branch) |
| → 🔔 awaiting review (no longer draft, still no reviewers) | `/request-review` |

Order most actionable first (🚀 → 💬 → ⚠️ → 🔔); omit the section when no PR changed state.

For a PR whose unresolved-thread count increased this tick (only those), fetch who commented and a ~80-char gist for the bullet:

```bash
gh api graphql -f query='
query($owner:String!,$repo:String!,$pr:Int!){
  repository(owner:$owner,name:$repo){
    pullRequest(number:$pr){
      reviewThreads(last:10){
        nodes{ isResolved comments(last:1){ nodes{ author{login} body } } }
      }
    }
  }
}' -f owner="{owner}" -f repo="{repo}" -F pr={number} \
  --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false) | .comments.nodes[0] | {author: .author.login, gist: (.body | .[0:80])}]'
```

If the fetch fails, fall back to the bare count (`💬 N new`).

### 7. Next-tick recommendation

End with one cadence line for `/watch-prs` to pace from (harmless on a one-shot run):

```
next-tick: {hot|warm|cold} (~{N}s) — {reason}
```

- **hot (~180s)** — CI ⏳ on any open non-draft PR, a push in the last ~5 min, or a transition this tick
- **warm (~600s)** — open non-draft PRs awaiting review or carrying threads, nothing in flight
- **cold (1200 → 1800s)** — nothing actionable soon; escalate 1200 → 1500 → 1800 across consecutive cold ticks, reset on any non-cold tick

If the fetch failed, emit `next-tick: warm (~600s) — incomplete fetch`. Keep the reason to a few words; no other pacing commentary.

If the invoking prompt asks you to reschedule via `ScheduleWakeup`, do that only after everything above is printed — the turn ends when it returns.
