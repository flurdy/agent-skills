---
name: start-ticket
description: Initialize work on a Jira ticket. Creates a new branch with conventional commit prefix based on the ticket type. Use when starting work on a new ticket.
allowed-tools: "Bash(git:*),Bash(~/.agents/skills/handoffs/scripts/list.sh:*),Read,Skill,mcp__jira__*"
model-tier: economy
model: haiku
effort: medium
version: "1.2.0"
author: "flurdy"
---

# Start Ticket

Initialize work on a Jira ticket by looking up the ticket details and creating an appropriately named branch.

## Usage

```
/start-ticket AB-123
```

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

- **Resume handoff (recommended)** — `Read` `~/.claude/handoffs/{filename}` and render it **verbatim** in a fenced block as resume context. Then resume its branch rather than creating a new one: `git checkout {branch}` if it exists locally, else hand to `/handoffs` for the full (worktree-aware) resume flow. **Skip step 4** — don't `git checkout -b` over an existing branch. If `{exists}=Y` and the recorded cwd differs from pwd, add `**Switch directory:** cd {cwd}`.
- **Start fresh** — ignore the handoff and continue to step 4 with a new branch.

If `list.sh` errors or there's no handoffs dir, proceed to step 4 silently — this is a courtesy, never a blocker.

### 4. Create the Branch

```bash
# Ensure we're on main and up to date
git checkout main
git pull origin main

# Create and switch to new branch
git checkout -b {branch-name}
```

### 5. Confirm to User

Output the created branch name and ticket summary so the user knows they're ready to start work.
