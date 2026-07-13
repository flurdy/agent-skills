---
name: complete-task
description: "Complete an in-progress task by running clean-code, staging, and committing. In trunk repos it also closes the bead; in PR repos it leaves the bead open and offers /create-pr. Use after /verify-task."
allowed-tools: "Read,Bash(bd:*),Bash(make:*),Bash(git:*),Bash(npm:*),Grep,Glob,Skill,AskUserQuestion"
model-tier: standard-coding
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
model: sonnet
effort: medium
version: "1.2.0"
author: "flurdy"
---

# Complete Task

Run clean-code, stage, and commit an in-progress task — the finalization phase of the development workflow. Whether the bead is closed here depends on the workflow: in a **trunk / direct-commit** repo the commit is the deliverable, so the bead closes now; in a **PR-based** repo the deliverable is a merged PR, so the bead is left open and closed later at the `/create-pr` stage.

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

Determine which bead is being completed:

```bash
# If bead ID provided, use it directly
bd show <bead-id>

# Otherwise, find the in-progress bead
bd list --status=in_progress
```

If multiple beads are in progress, ask the user which one to complete.
If no beads are in progress, ask the user what to do.

### 2. Run Clean Code

```bash
make clean-code
```

If clean-code fails:

- Fix auto-fixable issues
- Re-run to confirm zero warnings and zero errors
- If issues remain that change behavior, ask the user before fixing

### 3. Stage Changes

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

Create a commit using conventional commit format:

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

Only after the commit succeeds, detect whether this repo/branch uses a PR-based workflow — it decides whether the bead closes now or later.

```bash
# Default branch (origin/HEAD, falling back to local main/master)
default_branch=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
if [ -z "$default_branch" ]; then
  for c in main master; do git show-ref --verify --quiet "refs/heads/$c" && default_branch=$c && break; done
fi
current_branch=$(git branch --show-current)
git remote   # empty output = no remote
```

Classify:

- **Trunk / direct-commit mode** — `current_branch` equals `default_branch`, **or** there is no remote, **or** HEAD is detached. The commit itself is the deliverable.
- **PR mode** — on a feature branch (`current_branch` ≠ `default_branch`) **with** a remote. The deliverable is a reviewed, merged PR; this commit is only the first step.

### 6. Finalize the Bead

Never close a bead if the commit failed or changes are still uncommitted.

**Trunk mode** — close the bead now (the commit is the whole deliverable):

```bash
bd close <bead-id> --reason="<brief summary of what was done>"
```

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

- Workflow mode (trunk or PR) and the resulting bead state — **closed** (trunk / close-anyway) or **left `in_progress`** (PR mode, to be closed at `/create-pr`)
- If a PR was created via the handoff, its URL
- Commit hash and message
- Files changed count
- Any follow-up items noted

## Handling Edge Cases

- **No in-progress beads**: Ask user if they want to complete uncommitted work without a bead, or create one first
- **Multiple in-progress beads**: List them and ask user to pick
- **Clean-code fails repeatedly**: After 2 attempts, ask user for guidance
- **No changes to commit**: Inform user there's nothing to commit; ask if the bead should still be closed
- **Unrelated unstaged changes**: Warn user about them; suggest creating a separate bead/commit
- **Commit hook fails**: Investigate the hook failure, fix the underlying issue, and create a new commit (never amend, never skip hooks)
- **Feature branch but non-PR repo**: detection assumes PR mode on any feature branch with a remote. If the user knows the repo is trunk-based, use the **Close the bead anyway** option in §6.
- **PR already exists for this branch**: still leave the bead open; `/create-pr` (or the user) handles the existing PR. Don't open a duplicate.

## Rules

- Never use `--no-verify` or skip git hooks
- Never push to remote yourself — pushing happens via the `/create-pr` handoff, not in this skill
- Never amend existing commits
- Never close a bead with uncommitted changes
- In PR mode, do not close the bead — that happens at `/create-pr` (reopen later if review demands major changes)
- Always stage specific files, never bulk-add
- If any step fails, stop and inform the user rather than forcing through
