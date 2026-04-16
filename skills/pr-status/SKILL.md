---
name: pr-status
description: Show enriched status of your open PRs — CI checks, approvals, and unresolved review threads in one table.
allowed-tools: "Bash(~/.claude/skills/pr-status/scripts/gh-pr-list-open.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-list-closed.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-details.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-checks.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-reviews.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-threads.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-merge-state.sh:*), Bash(gh pr list:*), Bash(gh pr checks:*), Bash(gh pr view:*), Bash(gh api:*), Bash(gh search:*)"
version: "1.2.0"
author: "flurdy"
---

# PR Status

Show enriched status for all open PRs created by you across your GitHub org: CI checks, approvals, and unresolved review threads. Also shows recently closed PRs.

The GitHub org is auto-detected from the current repo's `origin` remote, or can be overridden via `PR_STATUS_ORG` env var.

## Usage

```
/pr-status
```

## Instructions

### 1. Get open PRs (org-wide)

```bash
~/.claude/skills/pr-status/scripts/gh-pr-list-open.sh
```

Output is one JSON object per line: `{number, title, owner, repo}`.

The script searches across the GitHub org — not just the current repo. Org is resolved in order: `PR_STATUS_ORG` env var, or extracted from the current repo's `origin` remote URL.

### 1b. Get recently closed PRs (last 7 days)

```bash
~/.claude/skills/pr-status/scripts/gh-pr-list-closed.sh
```

Output is one JSON object per line: `{number, title, owner, repo, closedAt}`.

### 2. Fetch PR details

Group the PRs by `owner/repo`. For each group, fetch all data in a single GraphQL call:

```bash
~/.claude/skills/pr-status/scripts/gh-pr-details.sh {owner} {repo} {number1} {number2} ...
```

Output is a JSON array, one object per PR:

```json
[
  {
    "number": 123,
    "base": "main",
    "mergeState": "CLEAN",
    "reviewDecision": "APPROVED",
    "approvers": ["alice"],
    "unresolvedThreads": 2,
    "checksState": "SUCCESS",
    "lastPush": "2026-04-15T09:30:00Z",
    "readyAt": "2026-04-14T15:32:11Z"
  }
]
```

Map `checksState` values: `SUCCESS` → ✅ / `FAILURE` or `ERROR` → ❌ / `PENDING` or `EXPECTED` → ⏳ / null → `—`

#### Fallback (if batch script unavailable): fetch per PR in parallel

**CI status** (pass / failing / pending):

```bash
~/.claude/skills/pr-status/scripts/gh-pr-checks.sh {number}
```

If the script is unavailable, fall back to:

```bash
gh pr checks {number} 2>/dev/null | awk -F'\t' '{print $2}' | sort | uniq -c
```

**Approvals** (count + who):

```bash
~/.claude/skills/pr-status/scripts/gh-pr-reviews.sh {owner} {repo} {number}
```

If the script is unavailable, fall back to:

```bash
gh api "repos/{owner}/{repo}/pulls/{number}/reviews" \
  --jq '[.[] | select(.state == "APPROVED") | .user.login] | unique | join(", ")'
```

**Unresolved review threads** (count):

```bash
~/.claude/skills/pr-status/scripts/gh-pr-threads.sh {owner} {repo} {number}
```

If the script is unavailable, fall back to:

```bash
gh api graphql -f query='
query($owner:String!,$repo:String!,$pr:Int!){
  repository(owner:$owner,name:$repo){
    pullRequest(number:$pr){
      reviewThreads(first:100){
        nodes{ isResolved }
      }
    }
  }
}' -f owner="{owner}" -f repo="{repo}" -F pr={number} \
  --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false)] | length'
```

**Merge state** (behind / conflict / clean):

```bash
~/.claude/skills/pr-status/scripts/gh-pr-merge-state.sh {number} {owner} {repo}
```

If the script is unavailable, fall back to:

```bash
gh pr view {number} --repo {owner}/{repo} --json mergeStateStatus --jq '.mergeStateStatus'
```

### 3. Render as tables

Before the tables, output a timestamp line: `_Checked at HH:MM:SS_` (local time, 24h).

**Recently closed (last 7 days)** — render first. Show in a single table with a **Repo** column. Skip this section entirely if no PRs were closed in the last 7 days. Fetch details for closed PRs too (same `gh-pr-details.sh` script) to get `readyAt`.

#### Recently closed

| PR | Repo | Ticket | Title | Status | Ready | Wait | Closed |
|----|------|--------|-------|--------|-------|------|--------|

- **PR**: render as a markdown link: `[#123](https://github.com/{owner}/{repo}/pull/123)`
- **Repo**: repository name
- **Ticket**: extract Jira ticket ID by matching `/[A-Z]+-\d+/` against the PR title. Show as plain text or `—`
- **Status**: 🔀 or ❌ — emoji only, no text (from `merged` field in closed list output)
- **Ready**: relative time since PR became ready for review (from `readyAt`). Same short units
- **Wait**: time between ready and closed (`closedAt - readyAt`). Shows how long the PR waited for review/merge
- **Closed**: relative time since close, e.g. `2h`, `1d`, `5d`

**Open PRs** — render after closed. Group by repo. For each repo that has open PRs, output a heading `#### Open — {repo}` followed by a table. Only show repos that have PRs — don't list empty repos.

| PR | Ticket | Title | Branch | Target | Ready | Push | Sync | CI | Approved | Threads |
|----|--------|-------|--------|--------|-------|------|------|----|----------|---------|

- **PR**: render as a markdown link: `[#123](https://github.com/{owner}/{repo}/pull/123)`
- **Ticket**: extract Jira ticket ID (e.g. `GE-1107`) by matching `/[A-Z]+-\d+/` against the branch name first, then the PR title. Show as plain text. If no match, show `—`
- **Branch**: the head branch name (truncate long prefixes, e.g. `feat/GE-1107-cta-clicked-event` → `GE-1107-cta-clicked-event`)
- **Target**: base branch name. If not `main` or `master`, prefix with 🔗 to indicate the PR is stacked on another branch and should not be merged directly
- **Sync**: ✅ clean / ⚠️ behind (needs rebase onto base branch) / ❌ conflict
  - `CLEAN` or `UNSTABLE` → ✅
  - `BEHIND` → ⚠️ behind
  - `DIRTY` → ❌ conflict
  - other → `—`
- **CI**: ✅ / ❌ / ⏳ — emoji only, no text
- **Ready**: relative time since PR became ready for review (from `readyAt` — uses `ReadyForReviewEvent` or PR `createdAt` as fallback). Same short units
- **Push**: relative time since last commit (from `lastPush` in details output), e.g. `2h`, `1d`, `3d`. Use short units: `Nm` for minutes, `Nh` for hours, `Nd` for days
- **Approved**: list of approver logins, or `—` if none. If `reviewDecision` is `REVIEW_REQUIRED` but approvers exist, the approvals are stale (invalidated by a newer push) — render each name with strikethrough (`~~name~~`). If `reviewDecision` is `CHANGES_REQUESTED`, show `—` (ignore stale approvals). Only show plain names when `reviewDecision` is `APPROVED`.
- **Threads**: count, or `—` if zero

Keep PR titles truncated to ~50 chars.

### 4. Summarise changes

After the tables, if anything changed since the last check in this session, list the deltas as a bullet list, e.g.:

- #6142 CI: ❌ → ✅
- #6138 closed/merged (removed from list)
- #6141 new unresolved thread (0 → 1)

If nothing changed, say "No changes."
