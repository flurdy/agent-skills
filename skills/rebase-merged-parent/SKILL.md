---
name: rebase-merged-parent
description: Rebase after a parent PR has been merged to main. Use when your branch was stacked on another PR that has now been merged, and you need to rebase onto main while keeping only your commits.
allowed-tools: "Read,Edit,Bash(git:*),Bash(~/.agents/skills/rebase-merged-parent/scripts/gh-pr-base-branch.sh:*),Bash(~/.agents/skills/rebase-merged-parent/scripts/gh-pr-edit-base.sh:*),Bash(gh pr view:*),Bash(gh pr edit:*),Bash(make:*),Bash(npm:*),Bash(npx:*),Bash(sbt:*),AskUserQuestion"
model-tier: premium
model: opus
effort: high
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
~/.agents/skills/rebase-merged-parent/scripts/gh-pr-base-branch.sh
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

Gather the evidence the user needs to answer, and show it:

```bash
git log --oneline @{upstream}..HEAD   # commits that will replace the remote branch
git log --oneline HEAD..@{upstream}   # remote commits that will be discarded
```

A force-push rewrites published history. Anyone who has fetched this branch, or has a
branch stacked on it, is orphaned by the rewrite. Use `AskUserQuestion` to request explicit
permission **immediately before** the push, showing the branch, its upstream, both commit
lists above, and the exact command.

- **Force-push (Recommended)** — on this answer, make the standalone
  `git push --force-with-lease` invocation as the next tool call. Do not hide it in a
  script or command chain.
- **Not now** — leave the rebase local and say so plainly in step 11.
- **Stop** — perform no remote action.

A successful rebase, passing tests, the parent having been merged, or the user having
invoked this skill are **not** permission to push. Only the answer to this question is.
Never use bare `--force`.

If the push is rejected because the branch moved, stop and report. Do not retry and do not
escalate to `--force`.

### 10. Update PR Base to Main

Retargeting a PR's base is a **separate remote mutation** and needs its own gate — the
force-push answer does not cover it. It is visible to reviewers, detaches in-flight review
comments, and changes the diff they were reviewing.

Use `AskUserQuestion` showing the PR number, its current base, `main` as the proposed base,
and the command. Only on explicit approval:

```bash
~/.agents/skills/rebase-merged-parent/scripts/gh-pr-edit-base.sh main
```

If the script is unavailable, fall back to:

```bash
gh pr edit --base main
```

If the base is already `main`, render `PR base: unchanged` and ask nothing.

### 11. Report Result

Inform the user:
- Rebased onto main (parent was merged)
- X commits remain after rebase
- Whether the force push happened. If it was declined, say the rebase is local only and
  the remote branch still holds the old history — never report a push that did not run
- Whether the PR was retargeted to main, or left on its old base
