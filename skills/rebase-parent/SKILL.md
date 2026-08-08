---
name: rebase-parent
description: Rebase the current branch onto an updated parent PR branch. Use when you have stacked PRs and the parent branch has been updated (force-pushed after its own rebase or new commits added).
allowed-tools: "Read,Edit,Bash(git:*),Bash(~/.agents/skills/rebase-parent/scripts/gh-pr-base-branch.sh:*),Bash(~/.agents/skills/rebase-parent/scripts/gh-pr-edit-base.sh:*),Bash(gh pr view:*),Bash(gh pr edit:*),Bash(make:*),Bash(npm:*),Bash(npx:*),Bash(sbt:*),AskUserQuestion"
model-tier: premium
model: opus
effort: high
version: "1.0.0"
author: "flurdy"
---

# Rebase onto Updated Parent Branch

Rebase the current branch onto a parent branch that has been updated.

## Usage

```
/rebase-parent
/rebase-parent feature/parent-branch    # Explicit parent branch
```

## Instructions

### 1. Identify Parent Branch

If not provided, try to determine the parent:

```bash
# Get current branch
git branch --show-current
```

Check PR base branch:

```bash
~/.agents/skills/rebase-parent/scripts/gh-pr-base-branch.sh
```

If the script is unavailable, fall back to:

```bash
gh pr view --json baseRefName --jq '.baseRefName'
```

If the base is `main`, this skill doesn't apply - use `/rebase-main` instead.

Ask the user to confirm the parent branch if uncertain.

### 2. Check Current State

```bash
# Check for uncommitted changes
git status --porcelain

# Get current branch
git branch --show-current
```

Stash or commit uncommitted changes before proceeding.

### 3. Fetch Latest Parent

```bash
git fetch origin {parent-branch}
```

### 4. Find the Fork Point

The tricky part with rebasing onto an updated parent is finding where your branch originally diverged. If the parent was rebased, the old base commits are gone.

```bash
# Get the merge base (may be outdated if parent was rebased)
git merge-base HEAD origin/{parent-branch}

# Count commits unique to your branch
git rev-list --count origin/{parent-branch}..HEAD
```

### 5. Perform the Rebase

Use `--onto` to rebase only your commits onto the new parent:

```bash
# Find how many commits are yours (after the original fork point)
# Then rebase those commits onto the updated parent

git rebase --onto origin/{parent-branch} $(git merge-base HEAD origin/{parent-branch}) HEAD
```

If that doesn't work cleanly (merge-base is stale), try:

```bash
# Interactive rebase to select only your commits
git rebase -i origin/{parent-branch}
```

### 6. Handle Conflicts

If conflicts occur:

1. List conflicting files: `git diff --name-only --diff-filter=U`
2. Resolve each conflict
3. Stage resolved files: `git add {file}`
4. Continue: `git rebase --continue`

If stuck, abort and ask for guidance: `git rebase --abort`

### 7. Verify With Tests

After the rebase completes (especially if conflicts were resolved), run the project's tests to confirm nothing was broken by the rebase or conflict resolution.

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

### 8. Force Push

Gather the evidence the user needs to answer, and show it:

```bash
git log --oneline @{upstream}..HEAD   # commits that will replace the remote branch
git log --oneline HEAD..@{upstream}   # remote commits that will be discarded
```

A force-push rewrites published history, and this branch is stacked — anyone who has
fetched it, or any branch stacked on top of it, is orphaned by the rewrite. Use
`AskUserQuestion` to request explicit permission **immediately before** the push, showing
the branch, its upstream, both commit lists above, and the exact command.

- **Force-push (Recommended)** — on this answer, make the standalone
  `git push --force-with-lease` invocation as the next tool call. Do not hide it in a
  script or command chain.
- **Not now** — leave the rebase local and say so plainly in step 10.
- **Stop** — perform no remote action.

A successful rebase, passing tests, or the user having invoked this skill are **not**
permission to push. Only the answer to this question is. Never use bare `--force`.

If the push is rejected because the branch moved, stop and report. Do not retry and do not
escalate to `--force`.

### 9. Update PR Base (if needed)

Retargeting a PR's base is a **separate remote mutation** and needs its own gate — the
force-push answer does not cover it. It is visible to reviewers, detaches in-flight review
comments, and changes the diff they were reviewing.

If the PR base branch needs updating, use `AskUserQuestion` showing the PR number, its
current base, the proposed base, and the command. Only on explicit approval:

```bash
~/.agents/skills/rebase-parent/scripts/gh-pr-edit-base.sh {parent-branch}
```

If the script is unavailable, fall back to:

```bash
gh pr edit --base {parent-branch}
```

If the base is already correct, render `PR base: unchanged` and ask nothing.

### 10. Report Result

Inform the user:
- Successfully rebased X commits onto {parent-branch}
- Conflicts resolved (if any)
- Whether the force push happened. If it was declined, say the rebase is local only and
  the remote branch still holds the old history — never report a push that did not run
- Whether the PR base was retargeted, or left unchanged
