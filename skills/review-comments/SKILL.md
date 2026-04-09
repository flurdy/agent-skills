---
name: review-comments
description: Address PR review comments from reviewers (amazon-q-developer, copilot, humans). Use when the user wants to see and respond to feedback on their pull request.
allowed-tools: "Read,Edit,Grep,Glob,Bash(~/.claude/skills/review-comments/scripts/gh-pr-current-info.sh:*),Bash(~/.claude/skills/review-comments/scripts/gh-pr-view-reviews.sh:*),Bash(~/.claude/skills/review-comments/scripts/gh-pr-comments.sh:*),Bash(~/.claude/skills/review-comments/scripts/gh-pr-reply-comment.sh:*),Bash(gh pr view:*),Bash(gh api:*),Bash(git:*),Bash(make:*),Bash(npm:*),Bash(npx:*),Bash(sbt:*),AskUserQuestion"
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
SCRIPT=~/.claude/skills/review-comments/scripts/gh-pr-current-info.sh
if [ -x "$SCRIPT" ]; then
  "$SCRIPT"
else
  gh pr view --json number,url,title,headRepositoryOwner,headRepository \
    --jq '{number, url, title, owner: .headRepositoryOwner.login, repo: .headRepository.name}'
fi
```

### 2. Fetch Review Comments

Get all review comments on the PR:

```bash
# Get PR reviews and comments
SCRIPT=~/.claude/skills/review-comments/scripts/gh-pr-view-reviews.sh
if [ -x "$SCRIPT" ]; then
  "$SCRIPT" {pr_number}
else
  gh pr view {pr_number} --json reviews,comments
fi

# Get inline code review comments
SCRIPT=~/.claude/skills/review-comments/scripts/gh-pr-comments.sh
if [ -x "$SCRIPT" ]; then
  "$SCRIPT" {owner} {repo} {pr_number}
else
  gh api "repos/{owner}/{repo}/pulls/{pr_number}/comments"
fi
```

### 3. Categorize Comments

Group comments by:
- **Reviewer**: amazon-q-developer[bot], copilot[bot], human reviewers
- **Status**: Pending, Resolved, Outdated
- **Type**: Code suggestion, question, blocking issue

### 4. Present Summary

Show a summary of comments:

```
PR #123: feat(offers-cms): add caching

Reviews:
- amazon-q-developer: 3 comments (2 suggestions, 1 security concern)
- copilot: 1 comment (style suggestion)
- @username: 2 comments (1 question, 1 blocking)

Unresolved comments: 6
```

### 5. Address Comments

For each unresolved comment:

1. Read the comment and understand what's being asked
2. Check the file and line being referenced
3. Either:
   - Make the suggested change if appropriate, including an initially failing test if needed
   - Explain why the current code is correct
   - Ask the user for guidance on ambiguous feedback

### 6. After Making Changes

```bash
# Stage and commit fixes
git add {files_changed}
git commit -m "address review feedback"

# Push updates
git push
```

### 7. Respond to Comments (Optional)

If the user wants to reply to comments:

```bash
SCRIPT=~/.claude/skills/review-comments/scripts/gh-pr-reply-comment.sh
if [ -x "$SCRIPT" ]; then
  "$SCRIPT" {owner} {repo} {pr_number} {comment_id} "Done - fixed in latest commit"
else
  gh api "repos/{owner}/{repo}/pulls/{pr_number}/comments/{comment_id}/replies" \
    -f body="Done - fixed in latest commit"
fi
```
