---
name: rebase
description: Rebase the current branch onto an updated main, an updated stacked parent, or main after the parent PR merged. Proves the child-only commit range before rewriting anything; explicit gates for dirty trees, tests, force-push, and PR retargeting.
allowed-tools: "Read,Edit,Bash(git:*),Bash(~/.agents/skills/rebase/scripts/rebase-range.sh:*),Bash(~/.agents/skills/rebase/scripts/gh-pr-base-branch.sh:*),Bash(~/.agents/skills/rebase/scripts/gh-pr-edit-base.sh:*),Bash(gh pr view:*),Bash(gh pr edit:*),Bash(make:*),Bash(npm:*),Bash(npx:*),Bash(sbt:*),AskUserQuestion"
model-tier: premium
model: opus
effort: high
version: "1.0.0"
author: "flurdy"
---

# Rebase

One target-aware workflow for the three rebase situations. The commit range is always
resolved by a read-only helper that refuses to guess; the rebase command is the one it
prints, verbatim.

## Usage

```
/rebase                                   # Infer the target from the recorded parent / PR base
/rebase main                              # Main moved; replay this branch on top
/rebase parent {parent-branch}            # Stacked parent was updated or force-pushed
/rebase merged {old-parent} [--old-tip {sha}]   # Parent PR merged; move onto main, child commits only
```

`/rebase-main`, `/rebase-parent`, and `/rebase-merged-parent` remain as aliases for the three
explicit forms.

## Requirements

- `git`; `gh` only for target inference, old-tip recovery, and PR retargeting. Without `gh`,
  pass the target explicitly and skip step 9 with `PR base: not checked (gh unavailable)`.
- The helpers under `~/.agents/skills/rebase/scripts/` are read-only except
  `gh-pr-edit-base.sh`, which is only ever run behind the step 9 gate.

## Instructions

### 1. Working tree gate

```bash
git branch --show-current
git status --porcelain
```

A detached HEAD stops the workflow. If the tree is dirty, use `AskUserQuestion` before
anything else: **Stash**, **Commit first**, or **Stop**. Never rebase over uncommitted work.

### 2. Determine the target

An explicit argument wins. Otherwise infer, in this order:

```bash
git config --get branch.$(git branch --show-current).gh-merge-base   # recorded by /stack-branch
~/.agents/skills/rebase/scripts/gh-pr-base-branch.sh                 # PR base, if a PR exists
```

| Evidence | Mode |
|---|---|
| No recorded parent, and PR base is `main` or there is no PR | `main` |
| Parent recorded or PR base is not `main`, parent PR still open | `parent {parent}` |
| Parent recorded or PR base is not `main`, parent PR merged (`gh pr view {parent} --json state`) | `merged {parent}` |

If the evidence conflicts, `gh` is unavailable, or the parent PR state is unknown, ask once
with `AskUserQuestion` showing the evidence and the three modes. Do not guess a mode.

### 3. Fetch

```bash
git fetch origin main                 # main and merged modes
git fetch origin {parent-branch}      # parent mode
```

In merged mode also run `git fetch origin {old-parent}` and ignore failure: a deleted branch
is expected, and a still-present one refreshes the old tip.

### 4. Resolve the child-only range

```bash
~/.agents/skills/rebase/scripts/rebase-range.sh main
~/.agents/skills/rebase/scripts/rebase-range.sh parent {parent-branch}
~/.agents/skills/rebase/scripts/rebase-range.sh merged {old-parent} [--old-tip {sha}]
```

The helper prints `key=value` facts. Show `upstream_source`, `child_commits`,
`already_applied`, `behind`, and `command` to the user, then act on `status`:

- `status=up-to-date` — report that the branch already contains the target and stop.
- `status=ok` — continue to step 5 with the printed `command`.
- `status=refuse` — the old base could not be proven. Print `reason`. In merged mode recover
  the old tip from the parent PR's head, never its merge commit:

  ```bash
  gh pr view {old-parent} --json headRefOid --jq '.headRefOid'
  ```

  Re-run the helper with `--old-tip {sha}`. If it still refuses, or the SHA is not an
  ancestor of HEAD, stop and ask the user for the old parent tip. In parent mode a
  `stale merge-base` refusal means the parent was rewritten and the reflog no longer holds
  the old tip; ask the user for it rather than replaying parent commits.

Never build the range by hand, never fall back to `git merge-base` when the helper refused,
and never use `git rebase -i`, which blocks the session.

### 5. Rebase

Run the `command` line from step 4 exactly as printed:

```bash
git rebase --onto {target} {upstream} {current-branch}
```

### 6. Handle conflicts

```bash
git diff --name-only --diff-filter=U
```

Read each conflicting file, resolve it, `git add {file}`, then `git rebase --continue`. If a
conflict is not resolvable with confidence, `git rebase --abort` and report; do not guess.

### 7. Verify with tests

Run the project's standard test command, first match wins:

```bash
make test
npm test
npx <test-runner>
sbt test
```

If tests fail, **stop and report** before any push. Do not force-push a broken rebase. The
user may explicitly skip tests for a conflict-free rebase, but default to running them.

### 8. Force-push gate

```bash
git rev-parse --abbrev-ref @{upstream} 2>/dev/null
```

No upstream means nothing to push: render `Force push: not applicable` and go to step 9.
Otherwise gather and show the evidence:

```bash
git log --oneline @{upstream}..HEAD   # commits that will replace the remote branch
git log --oneline HEAD..@{upstream}   # remote commits that will be discarded
```

A force-push rewrites published history. Anyone who has fetched this branch, or any branch
stacked on it, is orphaned by the rewrite. Use `AskUserQuestion` **immediately before** the
push, showing the branch, its upstream, both commit lists, and the exact command.

- **Force-push (Recommended)** — make the standalone `git push --force-with-lease`
  invocation the next tool call. Do not hide it in a script or command chain.
- **Not now** — leave the rebase local and say so plainly in step 10.
- **Stop** — perform no remote action.

A clean rebase, passing tests, an existing upstream, a merged parent, or the user having
invoked this skill are **not** permission to push. Only the answer is. Never use bare
`--force`. If the push is rejected because the branch moved, stop and report; do not retry,
re-fetch, or escalate.

### 9. PR retarget gate

Retargeting a PR is a **separate remote mutation** with its own gate; the force-push answer
does not cover it. It is visible to reviewers, detaches in-flight review comments, and
changes the diff they were reviewing.

Compare the PR base from step 2 with the target branch (`main` in main and merged modes,
`{parent-branch}` in parent mode). If they match, or there is no PR, render
`PR base: unchanged` and ask nothing. Otherwise use `AskUserQuestion` showing the PR
number, its current base, the proposed base, and the command. Only on explicit approval:

```bash
~/.agents/skills/rebase/scripts/gh-pr-edit-base.sh {target-branch}
```

### 10. Report

- Mode, target, and how the old base was proven (`upstream_source`)
- How many commits were replayed and any that were skipped as already applied
- Conflicts resolved, and whether tests ran and passed
- Whether the force-push happened. If declined or not applicable, say the rebase is local
  only and the remote branch still holds the old history; never report a push that did not
  run
- Whether the PR base was retargeted or left unchanged
