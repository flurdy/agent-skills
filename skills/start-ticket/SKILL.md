---
name: start-ticket
description: Initialize work on a Jira ticket. Creates a new branch with conventional commit prefix based on the ticket type. Use when starting work on a new ticket.
allowed-tools: "Bash(git:*),Bash(~/.agents/skills/handoffs/scripts/list.sh:*),Bash(~/.agents/skills/start-ticket/scripts/git-branch-preflight.sh:*),Read,Skill,AskUserQuestion,mcp__jira__*"
model-tier: economy
model: haiku
effort: medium
version: "2.0.0"
author: "flurdy"
---

# Start Ticket

Initialize work on a Jira ticket by looking up the ticket details and creating an appropriately named branch.

## Usage

```
/start-ticket AB-123
```

## Requirements

The shared `scripts/git-branch-preflight.sh` helper requires Bash, Git (with `git switch`), and awk.
It reports working-tree and branch facts without changing refs or files, and queries `origin` for
exact destination publication. A missing helper, failed status read, or unknown remote state is a
stop condition, not permission to assume a clean tree or absent branch. `current_worktree` is the
canonical root from `git rev-parse --show-toplevel`; invoke from any repository subdirectory.

## Instructions

### 1. Look Up the Jira Ticket

Use the `/jira-ticket` skill or the Jira MCP tools directly to fetch the ticket details:

```
mcp__jira__jira_get with:
  path: /rest/api/3/issue/{ticketNumber}
  jq: "{key: key, summary: fields.summary, type: fields.issuetype.name}"
```

### 2. Determine the Branch Prefix

Map the Jira issue type to a conventional commit prefix:

| Issue Type | Branch Prefix |
|------------|---------------|
| Story | `feat` |
| Task | `feat` |
| Bug | `fix` |
| Spike | `chore` |
| Sub-task | inherit from parent, or `feat` |
| Improvement | `feat` |
| Technical Debt | `refactor` |
| Documentation | `docs` |
| Default | `feat` |

### 3. Generate Branch Name

Format: `{prefix}/{TICKET-NUMBER}-{kebab-case-summary}`

Rules:
- Convert summary to kebab-case (lowercase, hyphens instead of spaces)
- Remove special characters except hyphens
- Truncate to reasonable length (max ~50 chars for the summary portion)
- Keep the ticket number uppercase

Example: For ticket `AB-123` with summary "Sanitize Input":
```
feat/AB-123-sanitize-input
```

### 3b. Resume awareness — check for a prior handoff

Before creating a fresh branch, check whether a previous session already worked this ticket and left a `/wrap-up` handoff. "Start ticket" is the *new-work* entry point, but the same ticket sometimes comes back — and a handoff means there's likely an existing branch plus open threads you'd otherwise re-create from scratch.

Two-step so the usual case (a genuinely new ticket) stays network-free:

1. **Cheap pass (no network):**
   ```bash
   ~/.agents/skills/handoffs/scripts/list.sh --ticket {TICKET-NUMBER}
   ```
   Read `---MATCHED-HANDOFFS---` (current-repo, supersede-filtered, newest first). **Empty → skip to step 4 and create the branch normally.** This is the usual path.
2. **Confirm live (only if step 1 matched):**
   ```bash
   ~/.agents/skills/handoffs/scripts/list.sh --check-branches --ticket {TICKET-NUMBER}
   ```
   Still empty → the earlier work shipped; create a fresh branch (step 4). Otherwise take the **newest** matched line: `{filename}|{date}|{time}|{slug}|{branch}|{exists}|{pr-state}|{pr-number}|{pr-url}`.

When a live handoff remains, ask with `AskUserQuestion`:

> 📥 You have a handoff `{slug}` ({date} {time}) for `{TICKET-NUMBER}` on branch `{branch}`. Resume it instead of creating a new branch?

- **Resume handoff (recommended)** — `Read` `~/.claude/handoffs/{filename}` and render it **verbatim** in a fenced block as resume context. Hand to `/handoffs` for its worktree-aware resume flow rather than switching blindly. **Skip the fresh-branch path in step 4** — don't create over an existing branch. If `{exists}=Y` and the recorded cwd differs from pwd, add `**Switch directory:** cd {cwd}`.
- **Start fresh** — ignore the handoff and continue to step 4 with a new branch.

If `list.sh` errors or there's no handoffs dir, proceed to step 4 silently — this is a courtesy, never a blocker.

### 4. Preflight and create the branch

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
- With no local branch and `remote_branch_exists=unknown`, report that collision safety could not be
  established and stop before creating or pushing.

For a genuinely new branch, resolve the default branch from `origin/HEAD` (falling back to local
`main`, then `master`), fetch it, and branch directly from its remote-tracking ref. Do not check out
or pull the base branch:

```bash
git fetch origin {default-branch}
git switch --no-track -c {new-branch-name} origin/{default-branch}
```

### 5. Confirm branch push

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
confirmation. If declined, keep the branch local.

### 6. Confirm to User

Output the active branch, ticket summary, and whether it remains local or now tracks `origin`.
