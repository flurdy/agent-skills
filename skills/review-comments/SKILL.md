---
name: review-comments
description: Address PR review comments from reviewers (amazon-q-developer, copilot, humans). Use when the user wants to see and respond to feedback on their pull request.
allowed-tools: "Read,Edit,Grep,Glob,Bash(~/.agents/skills/review-comments/scripts/gh-pr-current-info.sh:*),Bash(~/.agents/skills/review-comments/scripts/gh-pr-view-reviews.sh:*),Bash(~/.agents/skills/review-comments/scripts/gh-pr-comments.sh:*),Bash(~/.agents/skills/review-comments/scripts/gh-pr-reply-comment.sh:*),Bash(gh pr view:*),Bash(gh api:*),Bash(git:*),Bash(make:*),Bash(npm:*),Bash(npx:*),Bash(sbt:*),AskUserQuestion"
model-tier: premium
model: opus
effort: high
version: "1.0.0"
author: "flurdy"
---

# Address Review Comments

Fetch and address review comments on the current PR.

## Usage

```
/review-comments
/review-comments 123    # Specific PR number
```

## Instructions

### 1. Find the PR

If no PR number provided, get it from the current branch:

```bash
~/.agents/skills/review-comments/scripts/gh-pr-current-info.sh
```

If the script is unavailable, fall back to:

```bash
gh pr view --json number,url,title,headRepositoryOwner,headRepository \
  --jq '{number, url, title, owner: .headRepositoryOwner.login, repo: .headRepository.name}'
```

### 2. Fetch Review Comments

Get PR reviews and comments:

```bash
~/.agents/skills/review-comments/scripts/gh-pr-view-reviews.sh {pr_number}
```

If the script is unavailable, fall back to:

```bash
gh pr view {pr_number} --json reviews,comments
```

Get inline code review comments:

```bash
~/.agents/skills/review-comments/scripts/gh-pr-comments.sh {owner} {repo} {pr_number}
```

If the script is unavailable, fall back to:

```bash
gh api "repos/{owner}/{repo}/pulls/{pr_number}/comments"
```

### 2b. Fetch CI Check Annotations

Lint/typecheck jobs often attach inline annotations to the PR's checks — these surface in the GitHub UI alongside review comments but are NOT review threads, so the comment endpoints above never return them.

```bash
# List completed check runs on the PR head, then pull annotations per run
gh pr view {pr_number} --json headRefOid --jq .headRefOid
gh api "repos/{owner}/{repo}/commits/{head_sha}/check-runs" \
  --jq '.check_runs[] | select(.output.annotations_count > 0) | {id, name}'
gh api "repos/{owner}/{repo}/check-runs/{check_run_id}/annotations" \
  --jq '.[] | {path, line: .start_line, level: .annotation_level, message}'
```

Filter to annotations whose `path` is in the PR's changed files — drop repo-wide noise (e.g. deprecated-runner warnings on `.github`). Skip this step silently if no check run has annotations.

### 3. Categorize Comments

Group comments by:
- **Reviewer**: amazon-q-developer[bot], copilot[bot], human reviewers
- **Status**: Pending, Resolved, Outdated
- **Type**: Code suggestion, question, blocking issue

CI annotations are their own category — **fix-only**: there is no thread to reply to or resolve, so they are addressed in code (or consciously left, e.g. a passing warning) and never appear in the `/reply-comments` step.

### 4. Present Summary

Show a summary of comments:

```
PR #123: feat(offers-cms): add caching

Reviews:
- amazon-q-developer: 3 comments (2 suggestions, 1 security concern)
- copilot: 1 comment (style suggestion)
- @username: 2 comments (1 question, 1 blocking)

CI annotations (fix-only, no thread):
- Linting: warning at src/foo.tsx:21 — missing useEffect dependency

Unresolved comments: 6
```

Omit the CI annotations block when there are none.

### 5. Ask the User

After presenting the summary, ask the user how they'd like to proceed:

- **Address** — make code changes to fix the feedback
- **Reply only** — just reply to the comments without code changes
- **Skip** — dismiss specific comments
- Or the user may give specific instructions per comment

Do NOT start making changes or replying without user confirmation.

### 6. Address Comments (if requested)

For each unresolved comment the user wants addressed:

1. Read the comment and understand what's being asked
2. Check the file and line being referenced
3. Either:
   - Make the suggested change if appropriate, including an initially failing test if needed
   - Explain why the current code is correct
   - Ask the user for guidance on ambiguous feedback

### 7. After Making Changes

```bash
# Stage and commit fixes
git add {files_changed}
git commit -m "address review feedback"

# Push updates
git push
```

### 8. Reply to Comments

After addressing and pushing, ask the user if they'd like to reply. If yes, use `/reply-comments` to post replies and resolve threads.
