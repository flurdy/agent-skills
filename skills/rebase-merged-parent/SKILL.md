---
name: rebase-merged-parent
description: Rebase after a parent PR has been merged to main. Use when your branch was stacked on another PR that has now been merged, and you need to rebase onto main while keeping only your commits.
allowed-tools: "Read,Edit,Bash(git:*),Bash(~/.claude/skills/rebase-merged-parent/scripts/gh-pr-base-branch.sh:*),Bash(~/.claude/skills/rebase-merged-parent/scripts/gh-pr-edit-base.sh:*),Bash(gh pr view:*),Bash(gh pr edit:*),Bash(make:*),Bash(npm:*),Bash(npx:*),Bash(sbt:*),AskUserQuestion"
version: "1.1.0"
author: "flurdy"
---

# Rebase After Parent Merged to Main

Rebase your branch onto main after the parent PR it was based on has been merged.

## Usage

```
/rebase-merged-parent
/rebase-merged-parent feature/old-parent    # Specify the old parent branch
```

## Instructions

### 1. Understand the Situation

Your branch was based on a parent branch (not main). That parent PR has now been merged to main. You need to:
- Rebase onto main
- Keep only YOUR commits (not the parent's commits, which are now in main)
- Update the PR to target main instead of the old parent

### 2. Identify the Old Parent Branch

If not provided:

```bash
~/.claude/skills/rebase-merged-parent/scripts/gh-pr-base-branch.sh
```

If the script is unavailable, fall back to:

```bash
gh pr view --json baseRefName --jq '.baseRefName'
```

If the base is already `main`, ask the user which branch was the old parent.

### 3. Check Current State

```bash
git status --porcelain
git branch --show-current
```

Stash or commit uncommitted changes.

### 4. Fetch Latest Main

```bash
git fetch origin main
```

### 5. Find Your Commits

Identify which commits are uniquely yours (not from the merged parent):

```bash
# List commits on your branch not in main
git log origin/main..HEAD --oneline

# These should only be YOUR commits if parent was merged properly
# If you see parent's commits too, we need to be more selective
```

### 6. Rebase onto Main with --onto

Use `git rebase --onto` to take only the commits between the old parent tip and HEAD, and replay them onto main. This is robust to squash-merges (where patch-id dedup fails because the squashed commit on main doesn't match the original parent commits).

Pick the ref for the old parent's tip, in this order of preference:

```bash
# If the local parent branch still exists
git rebase --onto origin/main <old-parent>

# Otherwise, if origin still has it
git rebase --onto origin/main origin/<old-parent>
```

If both are gone (branch was deleted after merge), find the old parent tip from the reflog or the PR's merge commit on main:

```bash
# Inspect the merge commit on main for the parent PR to find its tip SHA
gh pr view <parent-pr-number> --json mergeCommit --jq '.mergeCommit.oid'
# Then use that SHA as the upstream
git rebase --onto origin/main <sha>
```

### 7. Handle Conflicts

`--onto` only replays your commits, so "already applied" skips should be rare. If you do hit conflicts:

1. Resolve each conflict
2. `git add {file}`
3. `git rebase --continue`

### 8. Verify With Tests

After the rebase completes (especially if conflicts were resolved or commits were skipped as already-applied), run the project's tests to confirm nothing was broken.

Try the project's standard test command in this order:

```bash
# Prefer Makefile target if present
make test

# Otherwise the project's package manager
npm test
# or
npx <test-runner>
# or
sbt test
```

If tests fail, **stop and report to the user** before pushing. Do not force-push a broken rebase.

### 9. Force Push

```bash
git push --force-with-lease
```

### 10. Update PR Base to Main

```bash
~/.claude/skills/rebase-merged-parent/scripts/gh-pr-edit-base.sh main
```

If the script is unavailable, fall back to:

```bash
gh pr edit --base main
```

### 11. Report Result

Inform the user:
- Rebased onto main (parent was merged)
- Updated PR to target main
- X commits remain after rebase
- Force pushed to origin
