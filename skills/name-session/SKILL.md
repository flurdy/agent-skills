---
name: name-session
description: Derive a conventional Claude Code session name from the branch ticket, active bead, open PR, and what the session is actually doing — then print a paste-ready `/rename` line. Use when a session's auto-name is generic and you want it legible in the session list.
allowed-tools: "Bash(git rev-parse:*), Bash(git branch:*), Bash(bd list:*), Bash(gh pr view:*)"
model-tier: standard
model: sonnet
effort: low
version: "0.1.0"
author: "flurdy"
---

# Name session — propose a conventional `/rename`

Build a `<scope>-<descriptive>` name from the current context and emit it as a ready-to-paste `/rename` line.

## Important — what this skill cannot do

- It **cannot rename the session for you.** `/rename` is a built-in CLI command; only the user typing it triggers a rename. Slash commands emitted in model output are inert text, and there is no hook or settings mechanism for mid-session rename. So the deliverable is a single paste-ready line — you press enter.

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

### 1. Gather scope signals (parallel)

```bash
git rev-parse --abbrev-ref HEAD
bd list --status=in_progress 2>/dev/null
```

- Extract a Jira ticket from the branch by matching `/[A-Z]+-\d+/`.
- If no ticket and exactly one bead is in progress, use its ID.
- If neither and there's an obvious PR in play this session, run `gh pr view --json number,title` to grab the number. Don't fetch a PR speculatively — only if the session is clearly about one.

Fail soft: any missing signal just drops to the next priority. Not in a git repo → skip straight to a descriptive-only name.

### 2. Derive the descriptive half

From the **current conversation**, pick the ≤4-word kebab phrase that best names what this session is for. Prefer the concrete task over the topic — `rebase-pr-status` over `maintenance`. If the session genuinely spans several unrelated things, name the dominant one; don't try to cram them all in.

### 3. Emit the rename line

Render exactly:

```markdown
**Proposed session name** — scope from {where the scope came from}, descriptive from this session:

```
/rename {scope}-{descriptive}
```

Paste it (the rename only fires when you run it).
```

Keep the derivation note to one short clause. If you had to fall back (no ticket, no bead), say which fallback you used so the user can override.

## Notes

- Pairs with `/wrap-up` and `/handoffs`, which emit the same kind of `/rename` line for end-of-session and resume respectively. This skill is the mid-session, on-demand version.
- Don't ask the user to confirm the name before printing it — printing *is* the proposal, and they can edit the line before pasting.
