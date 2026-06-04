---
name: handoffs-tidy
description: Prune superseded session handoffs — find handoffs that a newer one continues (same branch / topic / same-day re-wrap) and archive the stale ones so the /handoffs picker stays focused. Extracted from /wrap-up §5a. Read-only until you confirm; archives (never deletes).
allowed-tools: "Bash(~/.claude/skills/handoffs/scripts/list.sh:*), Bash(~/.claude/skills/handoffs/scripts/archive.sh:*), AskUserQuestion"
model: sonnet
effort: low
version: "0.1.0"
author: "flurdy"
---

# Handoffs-tidy — retire superseded handoffs

Keep `~/.claude/handoffs/` focused on **live** threads. Over time, newer handoffs continue
older ones (same branch, same topic slug, or a same-day re-wrap); the stale predecessors clutter
tomorrow's `/handoffs` picker. This command finds those supersede relationships and archives the
older files on your confirmation. Nothing is deleted — archived files move to
`~/.claude/handoffs/archive/` and stay greppable.

Split out of `/wrap-up` (which used to do this inline as §5a) so a handoff doesn't carry the
tidy machinery on every run. Run this **ad-hoc** whenever the picker feels noisy, or right after
a `/wrap-up` that continued an older thread.

## When to use

- After a `/wrap-up` whose handoff continues an earlier session's thread.
- Periodically, when `/handoffs` shows stale entries you've moved past.
- Not needed if you only ever have one handoff per topic — there's nothing to supersede.

## Instructions

### 1. Classify

Run the lister — it scans every handoff, resolves the current repo, and computes supersede
relationships from disk:

```bash
~/.claude/skills/handoffs/scripts/list.sh
```

Parse the `---HANDOFFS---` lines (pipe-delimited):
`{filename}|{date}|{slug}|{cwd}|{branch}|{repo-key}|{exists}|{superseded-by}|{supersede-reason}`

Select every row with a **non-empty `superseded-by`** — those are older handoffs a newer one
continues. If none, render `_No superseded handoffs — the picker is already tidy._` and stop.

### 2. Present

Render the candidates, grouped so it's obvious what supersedes what:

```markdown
## 🗂️ Superseded handoffs ({count})

| Archive? | Date | Slug | Branch | Superseded by | Why |
|----------|------|------|--------|---------------|-----|
```

- **Superseded by**: the `{superseded-by}` filename (the newer handoff that continues it).
- **Why**: humanise `{supersede-reason}` — `branch` → "same branch", `slug` → "same topic",
  `collision` → "same-day re-wrap".

### 3. Confirm + archive

Prompt with `AskUserQuestion` (multiSelect, one option per superseded filename):

> Archive the selected handoffs to `~/.claude/handoffs/archive/`? They stay on disk (greppable)
> but drop out of the `/handoffs` picker. Leave any you still want surfaced.

Archive the selected filenames in one call:

```bash
~/.claude/skills/handoffs/scripts/archive.sh {file1} {file2} …
```

Parse the script's `---ARCHIVED---` / `---SKIPPED---` sections and confirm:

```markdown
✅ Archived {N} handoff(s) to `~/.claude/handoffs/archive/`.
```

Report any `---SKIPPED---` lines verbatim with their reason — never drop them silently.
`archive.sh` only moves files; it never deletes. If the user selects none, render nothing and stop.

## Failure modes

- **`list.sh` / `archive.sh` missing** (handoffs skill not installed): say so plainly and stop —
  this command is purely a thin driver over those two scripts.
- **No `~/.claude/handoffs/` directory**: nothing to tidy; say so and stop.
