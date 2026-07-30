---
name: review-comments
description: Address PR review comments from reviewers (amazon-q-developer, copilot, humans). Use when the user wants to see and respond to feedback on their pull request.
allowed-tools: "Read,Edit,Grep,Glob,Bash(~/.agents/skills/pr-status/scripts/gh-pr-feedback.py:*),Bash(~/.agents/skills/review-comments/scripts/gh-pr-current-info.sh:*),Bash(~/.agents/skills/review-comments/scripts/gh-pr-view-reviews.sh:*),Bash(~/.agents/skills/review-comments/scripts/gh-pr-comments.sh:*),Bash(~/.agents/skills/review-comments/scripts/gh-pr-reply-comment.sh:*),Bash(gh pr view:*),Bash(gh api:*),Bash(git:*),Bash(make:*),Bash(npm:*),Bash(npx:*),Bash(sbt:*),AskUserQuestion"
model-tier: premium
model: opus
effort: high
version: "1.1.0"
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

### 2. Fetch the normalized feedback inventory

Use the same bounded read-only collector as `/pr-status`:

```bash
~/.agents/skills/pr-status/scripts/gh-pr-feedback.py {owner} {repo} {pr_number}
```

Read `records`, `partial`, and `errors`. The collector supplies stable identities and update times
for inline roots/replies, review summaries, top-level conversation, and changed-file CI annotations;
it also carries lifecycle, author kind, bounded body/gist, and response target IDs. If `partial` is
true, show the available records and failed source but do not treat absent items as resolved or
handled.

If the helper is unavailable, the existing `gh-pr-view-reviews.sh` and `gh-pr-comments.sh` wrappers
remain a compatibility fallback. Fetch check annotations only in that fallback, and keep filtering
them to changed files. Do not combine the normalized path with those ad-hoc fetches.

### 3. Categorize Comments

Group records by:
- **Author kind**: bot, human, self, or unknown
- **Source**: inline review, submitted review summary, top-level conversation, or check annotation
- **Lifecycle**: active/unresolved, resolved, outdated, or dismissed
- **Semantic type**: suggestion, question, change request, blocking/security claim, approval,
  automated status, CI annotation, or informational note

The collector's semantic type and `actionability` are triage hints. Whether a claim is valid or a
change should be made remains agent judgment against the current code, tests, and requirements.
Skip self-authored, resolved, outdated, dismissed, approval, and automated-status records by
default, but show them separately when useful. CI annotations are **fix-only** because they have no
reply or resolution endpoint.

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

For each selected candidate, retain its `identity`, `updatedAt`, and `targets` throughout the run:

1. Read the record and understand what's being asked
2. Check the referenced file/line and validate the claim independently
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
