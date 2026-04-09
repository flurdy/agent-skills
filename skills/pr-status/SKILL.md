---
name: pr-status
description: Show enriched status of your open PRs — CI checks, approvals, and unresolved review threads in one table.
allowed-tools: "Bash(gh:*)"
version: "1.0.0"
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
gh pr list --author "@me" --state open --json number,title,headRefName,baseRefName,headRepositoryOwner,headRepository \
  --jq '.[] | {number, title, branch: .headRefName, base: .baseRefName, owner: .headRepositoryOwner.login, repo: .headRepository.name}'
```

### 2. For each PR, fetch in parallel:

**CI status** (pass / failing / pending):
```bash
gh pr checks <number> 2>/dev/null | awk '{print $2}' | sort | uniq -c
```

**Approvals** (count + who):
```bash
gh api repos/{owner}/{repo}/pulls/{number}/reviews \
  --jq '[.[] | select(.state == "APPROVED") | .user.login] | unique | join(", ")'
```

**Unresolved review threads** (count):
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
gh pr view <number> --repo {owner}/{repo} --json mergeStateStatus --jq '.mergeStateStatus'
```

### 3. Render as a table

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