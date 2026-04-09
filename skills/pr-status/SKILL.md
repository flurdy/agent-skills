---
name: pr-status
description: Show enriched status of your open PRs — CI checks, approvals, and unresolved review threads in one table.
allowed-tools: "Bash(~/.claude/skills/pr-status/scripts/gh-pr-list-open.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-details.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-checks.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-reviews.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-threads.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-merge-state.sh:*), Bash(gh pr list:*), Bash(gh pr checks:*), Bash(gh pr view:*), Bash(gh api:*)"
version: "1.1.0"
author: "flurdy"
---

# PR Status

Show enriched status for all open PRs created by you: CI checks, approvals, and unresolved review threads.

## Usage

```
/pr-status
```

## Instructions

### 1. Get open PRs

```bash
~/.claude/skills/pr-status/scripts/gh-pr-list-open.sh
```

If the script is unavailable, fall back to:

```bash
gh pr list --author "@me" --state open \
  --json number,title,headRefName,baseRefName,headRepositoryOwner,headRepository \
  --jq '.[] | {number, title, branch: .headRefName, base: .baseRefName, owner: .headRepositoryOwner.login, repo: .headRepository.name}'
```

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
    "approvers": ["alice"],
    "unresolvedThreads": 2,
    "checksState": "SUCCESS"
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

### 3. Render as a table

Before the table, output a timestamp line: `_Checked at HH:MM:SS_` (local time, 24h).

Output a markdown table with columns:

| PR | Title | Target | Sync | CI | Approved by | Unresolved threads |
|----|-------|--------|------|----|-------------|--------------------|

- **Target**: base branch name. If not `main` or `master`, prefix with 🔗 to indicate the PR is stacked on another branch and should not be merged directly
- **Sync**: ✅ clean / ⚠️ behind (needs rebase onto base branch) / ❌ conflict
  - `CLEAN` or `UNSTABLE` → ✅
  - `BEHIND` → ⚠️ behind
  - `DIRTY` → ❌ conflict
  - other → `—`
- **CI**: ✅ passing / ❌ failing (N) / ⏳ pending
- **Approved by**: list of approver logins, or `—` if none
- **Unresolved threads**: count, or `—` if zero

Keep PR titles truncated to ~50 chars.
