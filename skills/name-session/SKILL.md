---
name: name-session
description: Derive a conventional session name from the branch ticket, active bead, open PR, and current work, then print the paste-ready rename command for the active client. Use when a session's auto-name is generic.
allowed-tools: "Read,Bash(git rev-parse:*),Bash(~/.agents/skills/next/scripts/next-select resolve:*),Bash(bd -C * show:*),Bash(gh pr view:*)"
model-tier: standard
model: sonnet
effort: low
version: "0.2.0"
author: "flurdy"
---

# Name session — propose a conventional session name

Build a `<scope>-<descriptive>` name from the current context and emit the active client's ready-to-paste rename command.

## Important — client command and limitation

Harness selection comes from the current tool surface.
Never use the shell, PATH, filesystem, process list, or installed binaries to detect another client.
Treat the client as unknown when that surface does not conclusively identify Pi or Claude Code.
These rules are shared with `/wrap-up` and `/handoffs`; command printing is a proposal, not execution.

- It **cannot rename the session for you.** Slash commands emitted in model output are inert text; the user must enter the command in the client's command input.
- **Pi:** use `/name {session-name}`. Never suggest `/rename` or `/settings name` in Pi.
- **Claude Code:** use `/rename {session-name}`.
- If the client is unknown, state both commands rather than guessing.

## Convention

```
<scope>-<descriptive>
```

- **scope** — the most specific identifier available, in priority order:
  1. Jira ticket from the branch name (e.g. `AB-1505`) — keep its natural Jira case.
  2. Active bead ID (e.g. `bd-123`) if no ticket.
  3. PR number (e.g. `pr-6563`) if neither.
  4. Omit the scope entirely if none apply — just use the descriptive part.
- **descriptive** — kebab-case, ≤4 words, the most specific noun phrase for what *this* session is doing. `rebase-pr-status` beats `git-stuff`. Derive it from the conversation, not the branch (the branch already gives the scope).

Examples: `AB-1505-rebase-pr-status`, `bd-412-flaky-test-hunt`, `pr-6563-review-comments`, `auth0-logout-investigation`.

## Instructions

### 1. Gather scope signals

Read the current branch with `git rev-parse --abbrev-ref HEAD`, using the repository wrapper where
required. Extract a ticket with `[A-Z]+-\d+`; detached HEAD is not a branch/ticket signal.

Without a ticket, prefer the bead explicitly identified as this session's work. If tracker validation
is needed, run `~/.agents/skills/next/scripts/next-select resolve <selector>` and use the returned
owner for `bd -C <directory> show <id>`. Unavailable/ambiguous ownership drops that signal; do not scan
all in-progress claims and assume one belongs here. Existing known session context needs no fetch.
If neither applies and a PR is clearly this session's topic, use its known identity or a scoped
`gh pr view --json number,title`. No speculative PR request.

Fail soft: unknown evidence stays unknown. Outside Git, known session context can still name the
work; otherwise use the descriptive part alone. No tracker, Git, or client state is changed.

### 2. Derive the descriptive half

From the **current conversation**, pick the ≤4-word kebab phrase that best names what this session is for. Prefer the concrete task over the topic — `rebase-pr-status` over `maintenance`. If the session genuinely spans several unrelated things, name the dominant one; don't try to cram them all in.

### 3. Emit the rename command

Compute `{session-name}` first: `{scope}-{descriptive}` when scope exists, otherwise just
`{descriptive}` with no leading hyphen. For Pi, render exactly:

```markdown
**Proposed session name** — scope from {where the scope came from}, descriptive from this session:

```
/name {session-name}
```

Paste it into Pi's command input and press Enter.
```

For Claude Code, substitute `/rename` for `/name`. If the client is unknown, provide both commands and label them by client.

Keep the derivation note to one short clause. If you had to fall back (no ticket, no bead), say which fallback you used so the user can override.

## Notes

- Pairs with `/wrap-up` and `/handoffs`, which should emit the same client-specific rename command for end-of-session and resume respectively. This skill is the mid-session, on-demand version.
- Don't ask the user to confirm the name before printing it — printing *is* the proposal, and they can edit the line before pasting.
