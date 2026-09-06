---
name: complete-task
description: "Complete an in-progress task by running clean-code, staging, and committing. Close the bead on trunk, leave it open for PR creation, and protect detached commits. Use after /verify-task."
allowed-tools: "Read,Bash(~/.agents/skills/next/scripts/next-select:*),Bash(bd close:*),Bash(bd list:*),Bash(bd show:*),Bash(bd update:*),Bash(make:*),Bash(git:*),Bash(npm:*),Grep,Glob,Skill,AskUserQuestion"
model-tier: standard
model: sonnet
effort: medium
version: "2.0.0"
author: "flurdy"
---

# Complete Task

Run clean-code, stage, and commit an in-progress task — the finalization phase of the development workflow. Whether the bead is closed here depends on the workflow: in a **trunk / direct-commit** repo the commit is the deliverable, so the bead closes now; in a **PR-based** repo the bead stays open until `/create-pr`; on a **detached HEAD** the commit is not safely owned by a branch, so the bead stays open.

## When to Use

- Code changes are verified and ready to commit
- After `/verify-task` has passed (or verification is not needed)
- Replacing manual Phase 3 (Commit and Close) steps

## Prerequisites

Run `/verify-task` before this skill to confirm requirements are met and test coverage is adequate. If you haven't verified yet, do that first.

## Usage

```
/complete-task              # Auto-detect in-progress bead
/complete-task <bead-id>    # Complete a specific bead
```

## Instructions

### 1. Identify the Task

Determine which bead is being completed, then prove which store owns it before reading or
closing anything. Never infer the owning store from the bead ID or the current directory: at a
workspace root the cwd store is the workspace store, not the repository that owns the work.

```bash
# Otherwise, find candidate in-progress beads in the active store
bd list --status=in_progress

# Resolve the chosen bead to its owning store (read-only)
~/.agents/skills/next/scripts/next-select resolve <bead-id>
```

If multiple beads are in progress, ask the user which one to complete.
If no beads are in progress, ask the user what to do.

Act on the resolver `status`:

| status | action |
|---|---|
| `resolved` | take `directory`; every later `bd` call in this skill uses `bd -C <directory>` |
| `ambiguous` | show `matches[].selector`, ask which `<repo>:<id>` is meant; close nothing |
| `unavailable` | report `failures`; commit as normal but leave the bead untouched and say why |
| `not-found` | ask the user for the right ID; never guess another store or create a bead |

Then read it in its owning store:

```bash
bd -C <directory> show <bead-id>
```

### 2. Run Clean Code

```bash
make clean-code
```

If clean-code fails:

- Fix auto-fixable issues
- Re-run to confirm zero warnings and zero errors
- If issues remain that change behavior, ask the user before fixing

### 3. Select new work or an existing verified commit

Inspect `git status --porcelain=v1 --untracked-files=all` first. Stop if the status command fails.
With task changes, HEAD may be unborn: stage and create the initial commit normally.

Only on the existing-commit path, require `git rev-parse HEAD` to succeed; stop if it does not.
If there is nothing to commit, do not create an empty commit. This includes a rerun after preserving
an earlier detached commit on a branch. Confirm that HEAD is the exact task commit, the working tree
is clean, and verification evidence applies to that commit; rerun `/verify-task` if evidence is
missing or HEAD changed. Show the SHA and ask **Finalize this verified commit** or **Stop**.
Only after confirmation, skip staging and committing and continue to §5. If HEAD or task identity is
uncertain, leave the bead open; an empty diff is not proof that the task is complete.

#### Stage changes for a new commit

Stage only the files changed for this task:

```bash
git add <specific-files>
```

**Rules:**

- Never use `git add -A` or `git add .`
- Never stage root folders only (e.g., `git add src/`)
- Stage specific files or small subdirectories
- Exclude unrelated changes — if unrelated changes exist, leave them unstaged
- Exclude files that likely contain secrets (.env, credentials, etc.)

### 4. Commit

For staged task changes only, create a commit using conventional commit format:

```bash
git commit -m "$(cat <<'EOF'
<type>: <concise description>
EOF
)"
```

**Commit message rules:**

- Use conventional commit prefix: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `perf:`, `test:`
- Infer the type from the bead type (feature → `feat:`, bug → `fix:`, task → contextual)
- Keep the message concise (1-2 sentences) focused on the "why"
- Do not push to remote

### 5. Detect the Workflow Mode

Require either a successful new commit or an explicitly confirmed existing verified commit from §3.
Then classify the current checkout to decide whether the bead closes now or later; neither path
bypasses detached-HEAD protection or the PR handoff.

```bash
# Default branch (origin/HEAD, falling back to local main/master)
default_branch=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
if [ -z "$default_branch" ]; then
  for c in main master; do git show-ref --verify --quiet "refs/heads/$c" && default_branch=$c && break; done
fi
current_branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)
head_sha=$(git rev-parse HEAD)
git remote   # empty output = no remote
```

Classify in this order:

- **Detached mode** — `current_branch` is empty. The commit exists at `head_sha` but no branch owns
  it, regardless of remotes or default-branch detection.
- **Trunk / direct-commit mode** — attached `current_branch` equals `default_branch`, or there is no
  remote. The commit itself is the deliverable.
- **PR mode** — attached feature branch (`current_branch` differs from `default_branch`) with a
  remote. The PR is the next lifecycle step.

### 6. Finalize the Bead

Never close a bead if the commit failed or changes are still uncommitted.

**Trunk mode** — close the bead now (the commit is the whole deliverable):

```bash
bd -C <directory> close <bead-id> --reason="<brief summary of what was done>"
```

**Detached mode** — never close the bead. Report the detached commit SHA, leave the bead `in_progress`,
and offer the exact preservation command without running it automatically:

```bash
git switch -c {branch-name}
```

After the user creates an attached branch, `/complete-task` may be rerun to classify the workflow
and finalize the bead.

**PR mode** — do **not** close the bead here. By convention the bead is closed one step later, at the `/create-pr` stage (and reopened if review demands major changes); closing at commit time would be premature, before the PR even exists. Instead, tell the user a PR workflow was detected (on branch `{current_branch}`) and the bead is being left `in_progress`, then offer the next step with `AskUserQuestion`:

- **Create the PR now (recommended)** — invoke the `/create-pr` skill via `Skill`. It pushes, opens the PR, and closes the bead.
- **Not yet** — leave the branch committed and the bead `in_progress`; remind the user to run `/create-pr` when ready.
- **Close the bead anyway** — escape hatch for a repo that is actually trunk-based despite the feature branch; close it as in trunk mode.

### 7. Check for Follow-Up Work

After finalizing:

- If implementation revealed new issues or TODOs, mention them to the user
- Suggest creating follow-up beads if appropriate (but don't auto-create)

### 8. Report

Summarize what was done:

- Workflow mode (trunk, PR, or detached) and resulting bead state — **closed** (trunk / close-anyway) or **left `in_progress`** (PR or detached)
- If a PR was created via the handoff, its URL
- Commit hash and message
- Files changed count
- Any follow-up items noted

## Handling Edge Cases

- **No in-progress beads**: Ask user if they want to complete uncommitted work without a bead, or create one first
- **Multiple in-progress beads**: List them and ask user to pick
- **Clean-code fails repeatedly**: After 2 attempts, ask user for guidance
- **No changes to commit**: use the existing-commit path in §3, then the same classification in §5 and finalization in §6; never close directly from an empty diff.
- **Unrelated unstaged changes**: Warn user about them; suggest creating a separate bead/commit
- **Commit hook fails**: Investigate the hook failure, fix the underlying issue, and create a new commit (never amend, never skip hooks)
- **Feature branch but non-PR repo**: detection assumes PR mode on any feature branch with a remote. If the user knows the repo is trunk-based, use the **Close the bead anyway** option in §6.
- **Detached HEAD**: preserve the reported commit with `git switch -c {branch-name}`; never close the bead while no branch owns the commit.
- **PR already exists for this branch**: still leave the bead open; `/create-pr` (or the user) handles the existing PR. Don't open a duplicate.

## Rules

- Never use `--no-verify` or skip git hooks
- Never push to remote yourself — pushing happens via the `/create-pr` handoff, not in this skill
- Never amend existing commits
- Never close a bead with uncommitted changes
- Never close a bead from a detached HEAD
- In PR mode, do not close the bead — that happens at `/create-pr` (reopen later if review demands major changes)
- Always stage specific files, never bulk-add
- If any step fails, stop and inform the user rather than forcing through
