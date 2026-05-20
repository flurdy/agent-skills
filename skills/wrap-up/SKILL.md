---
name: wrap-up
description: End-of-session handoff — summarise today's commits, PRs, and beads, warn about uncommitted/unpushed work (especially in worktrees), and emit a paste-ready resume block. Run before `/exit`.
allowed-tools: "Bash(~/.claude/skills/wrap-up/scripts/activity.sh:*), Bash(~/.claude/skills/landscape/scripts/working-copy.sh:*), Bash(date:*), Bash(pwd:*), Bash(mkdir:*), Bash(git rev-parse:*), Bash(git config:*), Write, AskUserQuestion, mcp__jira__jira_get"
model: sonnet
effort: medium
version: "0.1.0"
author: "flurdy"
---

# Wrap-up — End-of-session handoff

Produce a tidy end-of-day snapshot so the next session can resume from a paste, even if this one was mostly admin/planning and the worktree is about to be discarded. Pair with `/landscape` (which orients at the *start* of a session) — `/wrap-up` is its bookend.

## When to use

- Before running `/exit`, especially in worktree sessions.
- After a planning- or discussion-only session that produced no code but valuable context (Jira refinement, bead triage, design exchanges).
- Before pruning a worktree where you might otherwise lose the thread.

## What it does

1. Activity roundup for today (commits, PRs created/merged, beads closed).
2. Working-copy hygiene — flag uncommitted, unpushed, or worktree-only state.
3. Paste-ready **Resume block** capturing topic, decisions, open threads, and where to pick up.
4. Optional: save the resume block to `~/.claude/handoffs/YYYY-MM-DD-{slug}.md` for later.
5. Reminder to run `/exit` yourself — the skill cannot exit Claude Code for you.

## Important — what this skill cannot do

- It **cannot run `/exit`**. `/exit` is a built-in CLI command, not a model-invocable tool. After the summary renders, you exit manually.
- It **cannot rename the Claude Code session**. Session names are managed by the harness. The handoff file (step 4) is the durable artifact you grep for tomorrow.

## Instructions

> **MUST re-fetch on every invocation.** Each run executes the helper scripts from scratch. Never reuse output from a prior run; state has changed since.
>
> **MUST use the dedicated helper scripts.** Never construct ad-hoc `git`/`gh`/`bd` pipelines inline — those bypass the per-script permission allowlist and produce noisy permission prompts. Specifically: §1 must go through `~/.claude/skills/wrap-up/scripts/activity.sh`, and §3 must go through `~/.claude/skills/landscape/scripts/working-copy.sh` (reused — landscape and wrap-up share the same hygiene probe).

Render the sections below in order. The two helper scripts in §1 and §3 can run in parallel.

### 0. Header

```bash
date '+%A %Y-%m-%d %H:%M'
pwd
git rev-parse --abbrev-ref HEAD 2>/dev/null
git rev-parse --git-common-dir 2>/dev/null
git rev-parse --git-dir 2>/dev/null
```

If `--git-common-dir` and `--git-dir` differ, the cwd is a **linked worktree** (not the main checkout). Note this — it affects the warnings in §3.

Render:

```markdown
## Wrap-up — {Weekday} {YYYY-MM-DD} {HH:MM}

**Where:** `{pwd}` on `{branch}`{worktree-suffix}
```

`{worktree-suffix}` is ` _(linked worktree)_` when applicable, else empty.

### 1. 🧾 Today's activity

Run the helper:

```bash
~/.claude/skills/wrap-up/scripts/activity.sh
```

It emits delimited sections:

- `---STATUS---` — `OK` or `NO_GIT`. If `NO_GIT`, skip the Commits sub-section.
- `---DATE---` — today's `YYYY-MM-DD` (the script's window).
- `---AUTHOR---` — `git config user.email` for the commit filter.
- `---COMMITS---` — one pipe-delimited line per commit: `{worktree_basename}|{branch}|{sha}|{subject}|{when}`. Empty if no commits today.
- `---GH-STATUS---` — `OK` or `UNAVAILABLE` (gh missing or not authenticated).
- `---PRS-CREATED---` / `---PRS-MERGED---` / `---PRS-CLOSED-UNMERGED---` — JSON arrays (always `[]` when empty) from `gh search prs --author=@me`.
- `---BEADS-STATUS---` — `OK` / `NO_BD` / `NO_BEADS_IN_REPO`.
- `---BEADS-CLOSED---` — output of `bd list --status=closed --closed-after=TODAY` (only when `BEADS-STATUS=OK`).

#### Commits

Render as a table only if `---COMMITS---` is non-empty:

```markdown
### 🧾 Commits today

| Worktree | Branch | SHA | Subject | When |
|----------|--------|-----|---------|------|
```

- Truncate Subject to ~50 chars.

If empty: `_No commits today._` (Still useful — confirms admin-only session.)

#### PRs created / merged / closed today

If `---GH-STATUS---` is `UNAVAILABLE`, render `_GitHub CLI not authenticated — PR roundup skipped._` and skip the sub-section.

Otherwise, parse the three JSON arrays. De-duplicate (a PR may appear in created + merged on the same day — merged wins). Render a single table if anything remains:

```markdown
### 🔀 PRs today

| Event | PR | Repo | Title |
|-------|----|------|-------|
```

- **Event**: 🆕 created / 🚀 merged / 🗑️ closed-unmerged / 📝 draft (created and still draft).
- **PR**: markdown link `[#{number}]({url})`.

Skip the section entirely if all three arrays are empty.

#### Beads closed today

If `---BEADS-STATUS---` is `NO_BD` or `NO_BEADS_IN_REPO`, skip silently.

If `OK` and `---BEADS-CLOSED---` is non-empty, render:

```markdown
### 🎯 Beads closed today

| ID | Type | Pri | Title |
|----|------|-----|-------|
```

Skip if empty.

### 2. 🧠 Today's threads (model-summarised)

This is the *qualitative* part — what `git log` cannot tell you. Looking at the current session's actual conversation history, summarise in 3–6 bullets:

- **Topic(s)**: one-line description of what we were working on.
- **Decisions made**: anything settled (approach picked, scope cut, deferral, ticket transition).
- **Open threads**: unresolved questions, things parked for tomorrow, blockers.
- **Surprises**: anything discovered that changes the plan or contradicts an earlier assumption.

Keep each bullet to one sentence. If the session was purely mechanical (e.g. just ran `/landscape` and `/pr-status`), say so in one line and skip the bullets — there's nothing worth restating.

### 3. 📍 Working copy hygiene

Reuse landscape's helper (same probe — don't duplicate it here):

```bash
~/.claude/skills/landscape/scripts/working-copy.sh
```

Parse its `---BRANCH---`, `---STATUS---`, `---AHEAD-BEHIND---`, `---STASHES-ON-BRANCH---`, and `---OTHER-WORKTREES-UNSAFE---` sections.

Render a small status block + appropriate warning:

```markdown
### 📍 Working copy

- Branch: `{branch}`{worktree-suffix}
- Uncommitted: {clean | N modified / M untracked}
- Unpushed: {0 | N commits ahead of @{u} | no upstream}
- Stashes on this branch: {0 | N}
```

Then exactly one of the warnings below (pick the first matching rule):

1. **Uncommitted changes** → `⚠️ Uncommitted work — commit, stash, or discard before `/exit`. The resume block does not preserve file diffs.`
2. **Unpushed commits** → `⚠️ {N} unpushed commit(s) — push before `/exit` if the branch survives in a remote PR, or accept that this branch lives only locally.`
3. **Linked worktree, clean, no unpushed, no stashes** → `ℹ️ Linked worktree with no code to preserve. If you prune this worktree (`git worktree remove`), only the conversation context is lost — the resume block below is your only recovery path. Save it (step 5).`
4. **Main checkout, clean** → no warning.

Also surface **other worktrees with unsaved work** from `---OTHER-WORKTREES-UNSAFE---` as a footnote if any exist — easy to forget those after closing the session.

### 4. 🧷 Resume block

A self-contained paste that, dropped into a fresh session tomorrow, lets the next instance pick up without re-discovering context. Fenced as markdown so it copies cleanly.

```markdown
### Resume block

```markdown
# Resume: {topic-slug} — {YYYY-MM-DD}

**Where to pick up:** `{cwd}` on branch `{branch}`{worktree-note}

**Context:**
- {one-line framing of what we're doing and why}

**Decisions so far:**
- {bullet}

**Open threads:**
- {bullet}

**Suggested next step:**
- {one concrete action — file to open, command to run, person to ask, ticket to read}

**Pointers:**
- Jira: {key(s) or —}
- Beads: {id(s) or —}
- PR(s): {link(s) or —}
- Related files touched: {paths or —}
```
```

Guidance for the model when filling this in:

- Keep it short. A resume block longer than ~30 lines is a signal to split the work into multiple beads instead.
- `{topic-slug}` is kebab-case, ≤4 words. Pick the most specific noun phrase — `ge-1107-cta-event` beats `cta-stuff`.
- `{worktree-note}` is ` (worktree at {path})` for linked worktrees, else empty.
- Prefer **paths and IDs** over prose summaries — they're greppable next session.
- If the session was admin-only (no code), the resume block is *more* valuable, not less. Capture the Jira/bead context exchanged in chat.

### 5. 💾 Save the resume block (offer, don't force)

Ask the user whether to persist the resume block:

> Save resume block to `~/.claude/handoffs/{YYYY-MM-DD}-{slug}.md`?

Use `AskUserQuestion` with options: **Save**, **Don't save**, **Save with different name**. (If `AskUserQuestion` isn't appropriate in the current flow, just print the path and ask in plain text.)

On Save:

```bash
mkdir -p ~/.claude/handoffs
```

Then write the file with `Write`. **Never overwrite** — if a file with that name already exists, append `-2`, `-3`, … until unique. Confirm with the path written.

The directory naming convention (`~/.claude/handoffs/YYYY-MM-DD-slug.md`) means `ls ~/.claude/handoffs/` is a chronological log of session topics — easy to grep for "what was I doing about X last week."

### 6. Footer

```markdown
---
**Next:** run `/exit` to close this session. Resume tomorrow with `cat ~/.claude/handoffs/{file}.md` (or paste the block above).
```

If no handoff file was saved, drop the `cat` half and keep just the paste reminder.

## Failure modes

Each section is independent — fail soft, don't block the rest.

- **Not in a git repo**: skip §0 worktree detection, §1 commits, §3 hygiene. Still produce §2 threads and §4 resume block — they're the load-bearing parts.
- **gh not authenticated**: skip the PRs sub-section, print `_GitHub CLI not authenticated — PR roundup skipped._`
- **No Jira MCP**: omit Jira pointers from the resume block; do not fail.
- **No `bd` / no `.beads/`**: skip the beads sub-section silently.

## Notes

- This skill is intentionally *generative* in §2 and §4 — the model writes the threads and resume block from the current conversation history. The Bash fetches in §1 and §3 are mechanical guardrails so the qualitative parts are anchored in real activity rather than vibes.
- Don't suggest `git stash` as a way to "preserve" work for tomorrow without committing — stashes evaporate from memory faster than commits, and worktree pruning takes them with it. Prefer a WIP commit on a throwaway branch if there's something to save.
