---
name: pr-status
description: Show enriched status of your open PRs — CI checks, approvals, and unresolved review threads in one table, with transition-driven suggested next actions.
allowed-tools: "Bash(~/.claude/skills/pr-status/scripts/gh-pr-list-open.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-list-closed.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-details.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-checks.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-reviews.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-threads.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-merge-state.sh:*), Bash(gh pr list:*), Bash(gh pr checks:*), Bash(gh pr view:*), Bash(gh api:*), Bash(gh search:*), Bash(date:*)"
model-tier: standard-coding
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
model: sonnet
effort: medium
version: "1.10.2"
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

> **MUST re-fetch on every invocation.** Each `/pr-status` tick (including silent ones inside `/watch-prs`) MUST run all three fetch scripts (`gh-pr-list-open.sh`, `gh-pr-list-closed.sh`, `gh-pr-details.sh`) AND `date +%H:%M:%S` — even if the previous tick was seconds ago. NEVER reuse prior tool output and NEVER extrapolate the timestamp by adding the loop interval to the previous one. If the data looks identical, render "No changes" — but only after a real fetch confirms it. State changes (merges, approvals, CI flips) happen between ticks; reusing stale tables has caused real merges to be missed.

### 1. Get open PRs (org-wide)

```bash
~/.claude/skills/pr-status/scripts/gh-pr-list-open.sh
```

Output is one JSON object per line: `{number, title, owner, repo}`.

The script searches across the GitHub org — not just the current repo. Org is resolved in order: `PR_STATUS_ORG` env var, or extracted from the current repo's `origin` remote URL.

### 1b. Get recently closed PRs (recent window)

Default lookback is 3 days, extended to 4 on Tuesdays and kept at 3 on Mondays so the previous Friday's PRs stay visible across the weekend. Pass an explicit number of days as the second arg to override.

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

Before the tables, output a timestamp line: `_Checked at HH:MM:SS_` in **local** time, 24h. Run `date '+%H:%M:%S'` (do NOT use `date -u` — that's UTC). Note: relative-time math against `lastPush` / `readyAt` / `closedAt` still works in UTC since those fields are `Z`-suffixed; only the displayed timestamp needs to be local.

**Recently closed** — render first. Show in a single table with a **Repo** column. Skip this section entirely if the closed list is empty. Fetch details for closed PRs too (same `gh-pr-details.sh` script) to get `readyAt`.

#### Recently closed

| PR | Repo | Ticket | Title | Status | CI | Ready | Wait | Closed |
|----|------|--------|-------|--------|----|-------|------|--------|

- **PR**: render as a markdown link: `[#123](https://github.com/{owner}/{repo}/pull/123)`
- **Repo**: repository name
- **Ticket**: extract Jira ticket ID by matching `/[A-Z]+-\d+/` against the PR title. Show as plain text or `—`
- **Status**: 🔀 (merged) or 🗑️ (closed unmerged) — emoji only, no text (from `merged` field in closed list output)
- **CI**: post-merge check status on the merge commit (from `mainChecksState`). Only check if merged and `mergeCommitAt` is within the last 2 days — otherwise show `—`. Map: `SUCCESS` → ✅ / `FAILURE` or `ERROR` → ❌ / `PENDING` or `EXPECTED` → ⏳ / null or unmerged → `—`
- **Ready**: relative time since PR became ready for review (from `readyAt`). Same short units
- **Wait**: time between ready and closed (`closedAt - readyAt`). Shows how long the PR waited for review/merge
- **Closed**: relative time since close, e.g. `2h`, `1d`, `5d`

**Open PRs** — render after closed. Group by repo. For each repo that has open PRs, output a heading `#### Open — {repo}` followed by a table. Only show repos that have PRs — don't list empty repos.

| PR | Ticket | Title | Branch | Target | Ready | Push | Sync | CI | Approved | Threads | LGTM |
|----|--------|-------|--------|--------|-------|------|------|----|----------|---------|------|

- **PR**: render as a markdown link: `[#123](https://github.com/{owner}/{repo}/pull/123)`
- **Ticket**: extract Jira ticket ID (e.g. `AB-1107`) by matching `/[A-Z]+-\d+/` against the branch name first, then the PR title. Show as plain text. If no match, show `—`
- **Branch**: the head branch name. Strip both the conventional-commit prefix (`feat/`, `fix/`, etc.) and the Jira ticket prefix (already shown in the Ticket column), e.g. `feat/AB-1107-cta-clicked-event` → `cta-clicked-event`. If still over ~30 chars after stripping, truncate with `…`.
- **Target**: base branch name. **Both `main` AND `master` are default branches** — render them as plain text with no prefix. Only prefix with 📌 when the base is something other than `main`/`master`, indicating the PR is stacked on another branch and should not be merged directly.
  - `main` → `main` (no 📌)
  - `master` → `master` (no 📌)
  - `feat/parent-pr` → `📌 feat/parent-pr`
- **Sync**: ✅ clean / ⚠️ behind (needs rebase onto base branch) / 💥 conflict. Only meaningful when base is `main` or `master` (both are default branches); for stacked PRs (base is something else, i.e. Target has 📌) show `—` since the PR can't merge directly anyway.
  - base is `main` or `master` → use mergeState below
  - base is anything else → `—`
  - `CLEAN` or `UNSTABLE` → ✅
  - `BEHIND` → ⚠️ behind
  - `DIRTY` → 💥 conflict
  - other → `—`
- **CI**: ✅ / ❌ / ⏳ — emoji only, no text
- **Ready**: 🚧 if `isDraft` is true (PR is in draft, not yet ready for review). Otherwise relative time since PR became ready for review (from `readyAt` — uses `ReadyForReviewEvent` or PR `createdAt` as fallback). Same short units
- **Push**: relative time since last commit (from `lastPush` in details output), e.g. `2h`, `1d`, `3d`. Use short units: `Nm` for minutes, `Nh` for hours, `Nd` for days
- **Approved**: one ✅ per approver when `reviewDecision` is `APPROVED` (e.g. two approvers → `✅✅`). If `reviewDecision` is `REVIEW_REQUIRED` but approvers exist, the approvals are stale (invalidated by a newer push) — render one `☑️` per stale approver. If `reviewDecision` is `CHANGES_REQUESTED`, show 👎 (ignore stale approvals). If there are no approvers and no changes requested, show 🔔 to flag that the PR is awaiting review and needs pinging — unless `isDraft` is true, in which case show `—` (no point chasing a draft).
- **Threads**: `💬 N` if N > 0, or `—` if zero
- **LGTM**: 🚀 if all of: `isDraft` is false, `reviewDecision` is `APPROVED`, CI is `SUCCESS`, sync is `CLEAN` or `UNSTABLE`, threads is 0, and `mergeState` is `CLEAN`. Otherwise 🚧 (still under construction — something's blocking the merge).

Keep PR titles truncated:
- Closed table: ~50 chars
- Open table: ~30 chars (the open table has 12 columns — wide rows cause Claude Code's renderer to fall back to a key-value list instead of a table, so trim aggressively up front)

### 4. Summarise changes

After the tables, if anything changed since the last check in this session, list the deltas as a bullet list, e.g.:

- #6142 CI: ❌ → ✅
- #6138 closed/merged (removed from list)
- #6141 new unresolved thread (0 → 1)

If nothing changed, say "No changes."

**Always render both the Open and Recently closed tables in full**, even on unchanged ticks. The point of repeated checks (via `/watch-prs` or otherwise) is to see current state at a glance — collapsing to "No changes." or omitting the closed section forces scrolling back to find prior state, which defeats the glance. With the narrow closed-PR window (3–4 days) there's not much to render anyway.

### 5. Suggest next actions (transition-driven)

After the deltas, surface a short **Suggested actions** list — copy-pasteable commands for PRs that *just became* actionable this tick. This stays read-only: it never runs the commands and never prompts (so it's safe inside the unattended `/watch-prs` loop), it only points.

**Fire on transitions, not standing state.** Compare each PR's actionable signals (LGTM, unresolved threads, sync, review-decision, draft) against the previous tick in this session:

- **First check of a session** (no prior tick to diff against) — treat the currently-actionable PRs as the baseline and list them once.
- **Later ticks** — list a PR only when it *crosses into* an actionable state. A PR that has been 🚀 for an hour is not re-suggested every tick; you're nudged once, when it changes.

Map each transition to its command:

| Transition this tick | Suggested command |
|---|---|
| → 🚀 LGTM (newly mergeable) | `/ready-to-merge {n}` |
| unresolved threads increased, or → 👎 changes requested | `/review-comments {n}` |
| → ⚠️ behind (fell behind base) | `/rebase-main` (on that PR's branch) |
| → 🔔 awaiting review (no longer draft, still no reviewers) | `/request-review` |

Render as a flat bullet list, most actionable first (🚀 → 💬 → ⚠️ → 🔔). Omit the section entirely when no PR changed state. Example:

```markdown
**Suggested actions**
- 🚀 #6142 ready — `/ready-to-merge 6142`
- 💬 #6141 new comment from @alice — `/review-comments 6141`
```

#### Thread enrichment

For any PR whose unresolved-thread count *increased* this tick, fetch the new threads so the bullet names who commented and a one-line gist — the read-only slice of `/review-comments`, without touching code or prompting:

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

Only run this for PRs with a thread increase — **never** for every PR every tick. Trim each gist to ~80 chars. If the fetch fails, fall back to the bare count (`💬 N new`).

### 6. Next-tick recommendation

Emit, as the **very last line** of every tick, a cadence recommendation for `/watch-prs` to pace from.
It comes *after* the rendered tables, never instead of them — a tick that emits only this line (or
nothing at all) has failed step 3:

```
next-tick: {hot|warm|cold} (~{N}s) — {reason}
```

Pick the bucket from current PR state (most urgent wins):

- **hot (~180s)** — something is mid-flight you'll likely act on shortly: any open non-draft PR has CI ⏳ pending, was pushed in the last ~5 min (CI about to report), or *transitioned* this tick (→ 🚀, → 👎, thread increase). Check again soon to catch the result.
- **warm (~600s)** — open non-draft PRs exist and are awaiting review or carry unresolved threads, but nothing is in flight. Reviewer-paced — no point checking hard.
- **cold (1200 → 1800s)** — nothing actionable soon: no open PRs, or every open PR is a draft / stacked on another PR / blocked, or it's outside working hours. Escalate the back-off across consecutive cold ticks (1200 → 1500 → 1800) via a `quietStreak` counter held in session memory; reset to 1200 on any non-cold tick.

This line is primarily consumed by `/watch-prs` in adaptive mode — it's harmless to ignore on a one-shot `/pr-status` run. If a tick can't compute a bucket (e.g. a fetch failed), emit `next-tick: warm (~600s) — incomplete fetch` so the loop still has something to pace from.

**Print this line and nothing more about pacing.** Keep the reason to a few words and do NOT wrap it in a prose sentence explaining the cadence — `/watch-prs` and the dynamic loop narrate the wake themselves, so any extra commentary here just triples the same fact.
