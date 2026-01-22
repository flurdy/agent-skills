---
name: stack-branch
description: Create a new branch stacked on another PR. Use when you want to start work that depends on an existing PR that hasn't been merged yet.
---

# Create Stacked Branch

Create a new branch based on an existing PR branch (not main) for dependent work.

## Usage

```
/stack-branch GE-456
/stack-branch GE-456 feature/parent-branch    # Explicit parent
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

If on a feature branch (not main), offer to use it as the parent.
Otherwise, ask the user which branch to stack on.

### 3. Ensure Parent is Up to Date

```bash
# Fetch the parent branch
git fetch origin {parent-branch}

# Check out and update local copy
git checkout {parent-branch}
git pull origin {parent-branch}
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

Example: `feat/GE-456-add-caching-layer`

### 5. Create the Branch

```bash
git checkout -b {new-branch-name}
```

### 6. Push and Set Upstream

```bash
git push -u origin {new-branch-name}
```

### 7. Inform User

Tell the user:
- Created branch `{new-branch-name}` based on `{parent-branch}`
- When creating a PR, target `{parent-branch}` not `main`
- When `{parent-branch}` is merged, use `/rebase-merged-parent` to rebase onto main

### 8. Optional: Create Draft PR

Ask if the user wants to create a draft PR now:

```bash
gh pr create --draft --base {parent-branch} --title "{type}({scope}): {description}" --body "$(cat <<'EOF'
## What does this PR do?

WIP - Stacked on #{parent-pr-number}

## Jira ticket number?

{TICKET}

## Checklist before merging

- [ ] I have performed a self-review of my own code
- [ ] I have added tests for my changes (if applicable)
- [ ] I have updated documentation (if applicable)
EOF
)"
```
