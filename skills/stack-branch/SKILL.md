---
name: stack-branch
description: Create a new branch stacked on another PR. Use when you want to start work that depends on an existing PR that hasn't been merged yet.
allowed-tools: "Read,Bash(git:*),Bash(~/.agents/skills/start-ticket/scripts/git-branch-preflight.sh:*),Skill,AskUserQuestion,mcp__jira__*"
model-tier: standard
model: sonnet
effort: medium
version: "2.0.0"
author: "flurdy"
---

# Create Stacked Branch

Create a new branch based on an existing PR branch (not main) for dependent work.

## Usage

```
/stack-branch AB-456
/stack-branch AB-456 feature/parent-branch    # Explicit parent
```

## Instructions

### 1. Get the Jira Ticket

The first argument is the Jira ticket number for the new work.

Use the `/jira-ticket` skill or the Jira MCP tools directly to get ticket details:

```
mcp__jira__jira_get with:
  path: /rest/api/3/issue/{ticketNumber}
  jq: "{key: key, summary: fields.summary, issuetype: fields.issuetype.name}"
```

### 2. Identify Parent Branch

If parent branch not specified:

```bash
# Check if currently on a feature branch
git branch --show-current
```

If attached to a non-default branch, offer to use it as the parent. If detached or on the repository
default branch, ask which PR branch to stack on.

### 3. Resolve the parent ref

Fetch the parent branch read-only and require its remote-tracking ref to exist. The parent is an
existing PR branch, so `origin/{parent-branch}` is the authoritative base. Do not check out or pull
the parent branch:

```bash
git fetch origin {parent-branch}
git rev-parse --verify origin/{parent-branch}
```

### 4. Create Branch Name

Map the Jira issue type to conventional commit prefix:

| Issue Type | Prefix |
|------------|--------|
| Story | `feat` |
| Task | `feat` |
| Bug | `fix` |
| Improvement | `feat` |
| Spike | `chore` |
| Sub-task | inherit from parent |

Create branch name:
```
{prefix}/{TICKET}-{summary-in-kebab-case}
```

Example: `feat/AB-456-add-caching-layer`

### 5. Preflight the new branch

Run the shared read-only branch preflight before changing checkout state:

```bash
~/.agents/skills/start-ticket/scripts/git-branch-preflight.sh {new-branch-name}
```

#### Working tree gate

If `tracked_changes=true` or `untracked_changes=true`, stop before switching or creating a branch.
Use `AskUserQuestion` to offer **Commit first**, **Stash and continue**, or **Abort**. Never stash,
discard, or carry changes to another branch without that choice. If HEAD is detached, stop and ask
the user to preserve it on a branch before switching away.

#### Existing branch gate

- A non-empty `worktree_path` that differs from `current_worktree` means another worktree owns
  the target: do not switch or create; report the path and offer to continue there. Compare canonical
  worktree roots, not the invocation directory (which may be a subdirectory).
- `local_branch_exists=true`: offer **Resume existing branch** or **Abort**. Resume with
  `git switch {new-branch-name}` and skip creation.
- Remote-only (`remote_branch_exists=true`): offer **Track remote branch** or **Abort**. If chosen,
  fetch it and run `git switch --track -c {new-branch-name} origin/{new-branch-name}`.
- With no local branch and `remote_branch_exists=unknown`, stop before creating or pushing because
  collision safety is unresolved.

### 6. Create the branch

For a genuinely new branch, branch directly from the fetched parent ref:

```bash
git switch --no-track -c {new-branch-name} origin/{parent-branch}
```

After creating or resuming the branch, record the parent using GitHub CLI's supported per-branch
merge-base configuration so `/create-pr` can target it later:

```bash
git config branch.{new-branch-name}.gh-merge-base {parent-branch}
```

### 7. Confirm branch push

Rerun the preflight for `{new-branch-name}` after creating or resuming it. Skip this phase only when
`target_published=true`: HEAD matches the exact `origin/{new-branch-name}` destination, not a parent
upstream. On `unknown` or a preflight error, stop; on `false`, offer to publish the branch.
Show the exact branch and remote, then use `AskUserQuestion`
**immediately before** the command. If approved, the command must be the next tool call, standalone
and unchained:

```bash
git push -u origin {new-branch-name}
```

Approval applies only to that one command. A retry or any later remote mutation requires fresh
confirmation. If declined, keep the branch local and do not attempt PR creation.

### 8. Inform user

Tell the user:
- Created or resumed branch `{new-branch-name}` based on `{parent-branch}`
- `/create-pr` will read the recorded parent and target `{parent-branch}`, not `main`
- When `{parent-branch}` is merged, use `/rebase-merged-parent` to rebase onto main

### 9. Offer draft PR handoff

Only offer this when the branch exists on `origin`. Ask whether to continue with:

```text
/create-pr --draft {parent-branch}
```

This choice authorizes only the handoff. `/create-pr` owns the complete draft, the immediate PR
creation confirmation, the remote command, and closing the associated bead. Approval of the earlier
branch push never carries into PR creation.
