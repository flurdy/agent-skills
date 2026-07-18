---
name: jira-ticket
description: Look up Jira ticket details including summary, type, and description. Use this to fetch ticket context for branch naming, PR creation, or understanding requirements.
allowed-tools: "mcp__jira__*,ToolSearch"
model-tier: economy
model: haiku
effort: medium
version: "1.2.0"
author: "flurdy"
---

# Jira Ticket Lookup

Fetch details about a Jira ticket.

## Requirements

This skill requires the [mcp-server-atlassian-jira](https://github.com/aashari/mcp-server-atlassian-jira) MCP server configured with the name `jira`.

## Usage

```
/jira-ticket SP-123
```

## Instructions

### 1. Look Up the Jira Ticket

Use the Jira MCP tools to fetch the ticket details:

```
mcp__jira__jira_get with:
  path: /rest/api/3/issue/{ticketNumber}
  jq: "{key: key, summary: fields.summary, type: fields.issuetype.name, description: fields.description}"
```

**If `mcp__jira__jira_get` is not yet loaded** (common on the first prompt of a session — MCP tools are deferred until first referenced), don't bail out. Instead:

1. Call `ToolSearch` with `query: "select:mcp__jira__jira_get"` to load its schema.
2. Retry the `mcp__jira__jira_get` call.
3. If `ToolSearch` returns no match — the `jira` MCP server is not configured for this project, not just lazy-loaded. Tell the user, and either:
   - Ask them to paste the ticket summary/description so you can still infer the branch prefix, or
   - Point them at the parent project's `~/.claude.json` `mcpServers.jira` block if they want to copy it across (do not edit `~/.claude.json` without explicit consent).

Treat a missing MCP server as "ask the user," not as a hard failure.

### 2. Determine Branch Prefix

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

### 3. Return Ticket Info

Provide the user with:
- Ticket key (e.g., `SP-123`)
- Summary
- Issue type
- Suggested branch prefix based on type
- Description (if available and requested)

### Example Output

```
Ticket: SP-123
Summary: Add user authentication
Type: Story
Suggested prefix: feat
Branch name: feat/SP-123-add-user-authentication
```
