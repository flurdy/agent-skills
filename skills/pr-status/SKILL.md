---
name: pr-status
description: Show enriched status of your open PRs — CI checks, approvals, and unresolved review threads in one table.
allowed-tools: "Bash(~/.claude/skills/pr-status/scripts/gh-pr-list-open.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-checks.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-reviews.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-threads.sh:*), Bash(~/.claude/skills/pr-status/scripts/gh-pr-merge-state.sh:*), Bash(gh pr list:*), Bash(gh pr checks:*), Bash(gh pr view:*), Bash(gh api:*)"
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
SCRIPT=~/.claude/skills/pr-status/scripts/gh-pr-list-open.sh
if [ -x "$SCRIPT" ]; then
  "$SCRIPT"
else
  gh pr list --author "@me" --state open \
    --json number,title,headRefName,baseRefName,headRepositoryOwner,headRepository \
    --jq '.[] | {number, title, branch: .headRefName, base: .baseRefName, owner: .headRepositoryOwner.login, repo: .headRepository.name}'
fi
```

### 2. For each PR, fetch in parallel:

**CI status** (pass / failing / pending):
```bash
SCRIPT=~/.claude/skills/pr-status/scripts/gh-pr-checks.sh
if [ -x "$SCRIPT" ]; then
  "$SCRIPT" <number>
else
  gh pr checks <number> 2>/dev/null | awk '{print $2}' | sort | uniq -c
fi
```

**Approvals** (count + who):
```bash
SCRIPT=~/.claude/skills/pr-status/scripts/gh-pr-reviews.sh
if [ -x "$SCRIPT" ]; then
  "$SCRIPT" {owner} {repo} {number}
else
  gh api "repos/{owner}/{repo}/pulls/{number}/reviews" \
    --jq '[.[] | select(.state == "APPROVED") | .user.login] | unique | join(", ")'
fi
```

**Unresolved review threads** (count):
```bash
SCRIPT=~/.claude/skills/pr-status/scripts/gh-pr-threads.sh
if [ -x "$SCRIPT" ]; then
  "$SCRIPT" {owner} {repo} {number}
else
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
fi
```

**Merge state** (behind / conflict / clean):
```bash
SCRIPT=~/.claude/skills/pr-status/scripts/gh-pr-merge-state.sh
if [ -x "$SCRIPT" ]; then
  "$SCRIPT" {number} {owner} {repo}
else
  gh pr view {number} --repo {owner}/{repo} --json mergeStateStatus --jq '.mergeStateStatus'
fi
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