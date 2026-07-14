---
name: create-pr
description: Create a pull request from the current branch following project conventions. Uses the branch name to find the Jira ticket, generates a PR with the standard template, pushes to origin, and closes the associated bead.
allowed-tools: "Read,Bash(git:*),Bash(bd:*),Bash(~/.claude/skills/create-pr/scripts/gh-pr-create.sh:*),Bash(gh pr create:*),Skill,AskUserQuestion,mcp__jira__*"
model-tier: standard-workflow
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
model: sonnet
effort: medium
version: "1.1.0"
author: "flurdy"
---

# Create Pull Request

Create a pull request from the current branch using project conventions.

## Usage

```
/create-pr
```

## Instructions

### 1. Gather Context

Run these commands to understand the current state:

```bash
# Get current branch name
git branch --show-current

# Check if branch needs pushing
git status -sb

# Get commits on this branch not on main
git log main..HEAD --oneline

# Get diff summary against main
git diff main...HEAD --stat
```

### 2. Extract Jira Ticket from Branch Name

Parse the branch name to find the ticket number:

- Pattern: `{type}/{TICKET-NUMBER}-{description}`
- Example: `feat/AB-123-sanitize-input` → `AB-123`
- Ticket format: 2-4 uppercase letters, dash, numbers (e.g., `AB-123`, `SSP-456`)

If no ticket found, ask the user.

### 3. Look Up Jira Ticket

Use the `/jira-ticket` skill or the Jira MCP tools directly to get ticket details for the PR description:

```
mcp__jira__jira_get with:
  path: /rest/api/3/issue/{ticketNumber}
  jq: "{key: key, summary: fields.summary, description: fields.description}"
```

### 4. Generate PR Title

Use conventional commit format based on branch prefix:

| Branch Prefix | PR Title Format |
|---------------|-----------------|
| `feat/` | `feat(<scope>): <description>` |
| `fix/` | `fix(<scope>): <description>` |
| `refactor/` | `refactor(<scope>): <description>` |
| `chore/` | `chore(<scope>): <description>` |
| `docs/` | `docs(<scope>): <description>` |
| `perf/` | `perf(<scope>): <description>` |

Infer the scope from changed files (e.g., `offers-cms`, `web`, `api`).

### 5. Generate PR Body

Analyze the actual code changes (use `git diff main...HEAD`) to write a meaningful description.

Check for a repo-specific PR template at `.github/pull-request-template.md` or `.github/pull_request_template.md`. If found, use that format. If not, ask user for confirmation on generating the body ourselves.


### 6. Push and Create PR

```bash
# Push branch with upstream tracking
git push -u origin {branch-name}
```

Create the PR targeting main:

```bash
~/.claude/skills/create-pr/scripts/gh-pr-create.sh --base main --title "{title}" --body "$(cat <<'EOF'
{body}
EOF
)"
```

If the script is unavailable, fall back to:

```bash
gh pr create --base main --title "{title}" --body "$(cat <<'EOF'
{body}
EOF
)"
```

### 7. Close the Associated Bead

Once the PR is created, close the bead for this work — this is the preferred close point in a PR workflow (the commit was done in `/complete-task`, which deliberately left the bead open for this step). Reopen later if review demands major changes.

Skip this whole step silently if `bd` is unavailable or the repo has no beads database.

1. Find the in-progress bead for this work:

   ```bash
   bd list --status=in_progress
   ```

   Match by the Jira key from §2 appearing in the bead title/description, or an obvious 1:1 correspondence to the branch.

2. If exactly one bead matches, close it, referencing the PR:

   ```bash
   bd close <bead-id> --reason="PR #<number> created: <pr-title>"
   ```

3. If multiple beads plausibly match, ask the user which (if any) to close with `AskUserQuestion`. If none match, skip silently — don't invent one.

4. Tell the user the bead was closed and how to reopen it if review requires major changes:

   ```bash
   bd update <bead-id> --status=in_progress
   ```

Note: `/ready-to-merge` already closes a bead only "if still in_progress" post-merge, so closing here is compatible — by merge time it's normally already closed and that step no-ops.

### 8. Return Result

Output the PR URL so the user can view it, and note the bead that was closed (or left open, if none matched).
