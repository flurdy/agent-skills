---
name: wrap-up
description: End-of-session handoff — summarise today's commits, PRs, and beads, warn about uncommitted/unpushed work (especially in worktrees), and emit a paste-ready resume block. Run before `/exit`.
allowed-tools: "Bash(~/.claude/skills/wrap-up/scripts/header.sh:*), Bash(~/.claude/skills/wrap-up/scripts/activity.sh:*), Bash(~/.claude/skills/landscape/scripts/working-copy.sh:*), Bash(~/.claude/skills/handoffs/scripts/list.sh:*), Bash(~/.claude/skills/handoffs/scripts/archive.sh:*), Bash(mkdir:*), Bash(bd update:*), Write, AskUserQuestion, mcp__jira__jira_get"
model: sonnet
effort: medium
version: "0.7.0"
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
5. Optional: archive older handoffs this one supersedes (same branch/topic) so the picker stays focused.
6. Reminder to run `/exit` yourself — the skill cannot exit Claude Code for you.

## Important — what this skill cannot do

- It **cannot run `/exit`**. `/exit` is a built-in CLI command, not a model-invocable tool. After the summary renders, you exit manually.
- It **cannot rename the Claude Code session** for you. `/rename` is a built-in command — only you typing it triggers a rename. Step 4 prints a paste-ready `/rename {slug}` line so you *can* rename before exiting, but the handoff file (step 4) remains the durable artifact you grep for tomorrow.

## Instructions

> **MUST re-fetch on every invocation.** Each run executes the helper scripts from scratch. Never reuse output from a prior run; state has changed since.
>
> **MUST use the dedicated helper scripts.** Never construct ad-hoc `git`/`gh`/`bd` pipelines inline — those bypass the per-script permission allowlist and produce noisy permission prompts. Specifically: §0 must go through `~/.claude/skills/wrap-up/scripts/header.sh`, §1 must go through `~/.claude/skills/wrap-up/scripts/activity.sh`, and §3 must go through `~/.claude/skills/landscape/scripts/working-copy.sh` (reused — landscape and wrap-up share the same hygiene probe).

Render the sections below in order. The three helper scripts in §0, §1, and §3 can run in parallel.

### 0. Header

```bash
~/.claude/skills/wrap-up/scripts/header.sh
```

It emits delimited sections:

- `---DATE---` — `date '+%A %Y-%m-%d %H:%M'` output.
- `---CWD---` — `pwd`.
- `---BRANCH---` — current branch (empty if not in a git repo).
- `---GIT-COMMON-DIR---` / `---GIT-DIR---` — used for worktree detection (see below).
- `---REPO-ROOT---` — canonical repo root (parent of the realpath of `--git-common-dir`); empty if not in a git repo.
- `---DEFAULT-BRANCH---` — short name of the repo's default branch (`main`/`master`), empty if undetermined.
- `---WORKTREES---` — one `{path}|{branch}` line per worktree of this repo (branch `(detached)` when applicable). §4 uses it to map a feature branch back to the worktree that holds it.

If `---GIT-COMMON-DIR---` and `---GIT-DIR---` differ, the cwd is a **linked worktree** (not the main checkout). Note this — it affects the warnings in §3. (String inequality is sufficient: the main checkout returns the same value for both — typically `.git` — while a linked worktree returns `/path/to/main/.git` for common-dir vs `/path/to/main/.git/worktrees/{name}` for git-dir.)

Capture `---REPO-ROOT---` as `{repo-root}` for the resume block in §4. It's the stable identity `/handoffs` uses to group sessions per project — independent of which worktree wrote the handoff, and resilient to the worktree being pruned later.

**If `{branch}` equals `---DEFAULT-BRANCH---`, the cwd is parked on the trunk.** That branch almost never holds a session's work — the work usually lived on a feature branch in another worktree, and recording `main` would send `/handoffs` hunting for a PR that isn't on the trunk. Flag it here; §4 reconciles against today's actual activity before writing the resume block.

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
- `---BEADS-IN-PROGRESS---` — output of `bd list --status=in_progress` (state being left for tomorrow).
- `---BEADS-CREATED-TODAY---` — output of `bd list --created-after=TODAY` (open beads created today; closed-same-day beads appear in `BEADS-CLOSED` instead, no double-counting).
- `---BEADS-CLOSED---` — output of `bd list --status=closed --closed-after=TODAY`.

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

#### Jira tickets you touched today

Query for tickets the current user updated since midnight (status transitions, comments, edits):

```
mcp__jira__jira_get
  path: /rest/api/3/search/jql
  queryParams:
    jql: updatedBy = currentUser() AND updated >= startOfDay() ORDER BY updated DESC
    fields: summary,status,issuetype,updated
    maxResults: 20
  jq: issues[*].{key: key, summary: fields.summary, status: fields.status.name, type: fields.issuetype.name, updated: fields.updated}
```

Render as a table only if non-empty:

```markdown
### 📋 Jira touched today

| Key | Type | Status | Summary |
|-----|------|--------|---------|
```

- **Key**: markdown link to the issue (`[KEY](https://.../browse/KEY)`).
- Truncate Summary to ~50 chars.

Skip the section entirely if the result is empty. If the Jira MCP errors or isn't configured, render `_Jira unavailable — skipped._` and move on (do not fail the skill).

Note: `updatedBy` catches the obvious cases (status changes, comments, field edits). It won't catch tickets you only *read* during the session — that's intentional. The conversation chat in §2 captures what you *thought about* but didn't change.

#### Beads — in-progress, created today, closed today

If `---BEADS-STATUS---` is `NO_BD` or `NO_BEADS_IN_REPO`, skip the whole sub-section silently.

Render each of the three lists only when non-empty. Combine into compact tables (the same column shape works for all three):

```markdown
### 🎯 Beads

**In progress ({count})**
| ID | Type | Pri | Title |
|----|------|-----|-------|

**Created today ({count})**
| ID | Type | Pri | Title |
|----|------|-----|-------|

**Closed today ({count})**
| ID | Type | Pri | Title |
|----|------|-----|-------|
```

Notes:
- The default `bd list` output already filters out closed beads, so `BEADS-CREATED-TODAY` naturally excludes ones that were closed the same day. Those appear under "Closed today" instead — no de-duplication needed.
- **In-progress** is the most load-bearing for resume — it's the answer to "what was I in the middle of?" Always render it first when non-empty.
- If all three are empty, skip the whole `### 🎯 Beads` heading. If only some are non-empty, render just the populated tables and skip the empty ones (don't show `_No created today._` placeholders — silence is shorter).

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

### 3a. 🧹 Stale in-progress beads

Skip this whole section if `---BEADS-STATUS---` was `NO_BD`/`NO_BEADS_IN_REPO` or if `---BEADS-IN-PROGRESS---` was empty.

For each in-progress bead, check whether its ID (e.g. `bd-123`) appears in any of today's signals:

- Commit subjects (§1 Commits)
- Branch names from the worktree list (§1 Commits, second column)
- PR titles (§1 PRs today)
- The current branch (§0)

A bead with **no match in any of those** is "stale in_progress" — moved to `in_progress` at some point but saw no work today. Tomorrow's `/landscape` will misreport it as live WIP.

If any stale beads exist, render:

```markdown
### 🧹 Stale in-progress

These beads are in_progress but had no commits, PRs, or branch references today:

| ID | Type | Pri | Title |
|----|------|-----|-------|
```

Then prompt with `AskUserQuestion` (multiSelect, options are the bead IDs):

> Demote selected beads back to `ready` so tomorrow's WIP list is honest? Skip any you genuinely intend to keep open (e.g. design work in chat only).

For each selected bead:

```bash
bd update {id} --status=ready
```

After any demotions, recompute the **Beads** header field in §4 so demoted IDs don't reappear as in-progress in the resume block. (Demoted beads are still worth mentioning in the open-threads bullets if relevant — they're just no longer claimed as WIP.)

### 4. 🧷 Resume block

A self-contained paste that, dropped into a fresh session tomorrow, lets the next instance pick up without re-discovering context. Fenced as markdown so it copies cleanly.

**Before rendering the block, surface the topic slug and a paste-ready rename** so the user sees what this session is being filed under and can name the session to match before exiting:

```markdown
**Topic slug:** `{slug}` — used as the Resume title and the handoff filename.

**Rename this session to match:**

```
/rename {slug}
```

(Paste it — `/rename` is a built-in command, so it only fires when you run it. Optional; skip if the session is already named for this slug.)
```

This is the explicit "what should we call this session" cue — without it, the slug is buried inside the fenced block and easy to miss.

#### Reconcile the branch when parked on the trunk

The resume block's `{branch}` and `{cwd}` default to §0's current cwd and branch. But when §0 flagged that `{branch}` equals `---DEFAULT-BRANCH---` (the cwd is parked on `main`/`master`), that branch is almost never where the session's work lived — recording it sends `/handoffs` looking for a PR on the trunk (there is none) and leaves liveness detection blind to the real feature branch.

When parked on the trunk, pick a better resume target from the data already gathered, in priority order:

1. **Today's commits on a feature branch** — a non-default branch in §1's Commits table with commits today. Map it to its worktree path via §0's `---WORKTREES---`.
2. **A PR created/merged today** (§1 PRs) whose head branch is a feature branch.
3. **The topic ticket** — a branch in `---WORKTREES---` whose name contains the topic slug's ticket (e.g. slug `ge-1505-…` → branch `fix/GE-1505-…`).

Then:

- **Exactly one feature branch stands out** → record *that* branch as `{branch}` and its worktree path as `{cwd}` (set `{worktree-note}` to `(worktree at {path})` if it's a linked worktree). Surface the swap so it's visible, not silent:

  `> Wrapped from `{cwd-on-trunk}` (on `{default-branch}`), but today's work is on `{feature-branch}` in `{feature-worktree}` — recording that as the resume location.`

- **Several feature branches are in play, or it's ambiguous** → ask with `AskUserQuestion` which branch/worktree the next session should resume in. Options: each candidate `{branch} — {worktree basename}`, plus `Stay on {default-branch}`.
- **No feature branch at all** (the session committed directly to the trunk, or did no code) → keep the trunk. That's correct, not the bug — don't invent a branch.

`{repo-root}` is unaffected — it's the same repo regardless of which worktree you record.

```markdown
### Resume block

```markdown
# Resume: {topic-slug} — {YYYY-MM-DD}

**Where to pick up:** `{cwd}` on branch `{branch}`{worktree-note}
**Repo root:** `{repo-root}`
**Jira:** {jira-field}
**Beads:** {beads-field}
**PRs:** {prs-field}

**Context:**
- {one-line framing of what we're doing and why}

**Decisions so far:**
- {bullet}

**Open threads:**
- {bullet}

**Suggested next step:**
- {one concrete action — file to open, command to run, person to ask, ticket to read}

**Pointers:**
- {free-form ancillary refs: dashboards, commits worth re-reading, people to ask — or omit the section entirely if nothing to add}
```
```

Guidance for the model when filling this in:

- Keep it short. A resume block longer than ~30 lines is a signal to split the work into multiple beads instead.
- `{topic-slug}` is kebab-case, ≤4 words. Pick the most specific noun phrase — `ab-1107-cta-event` beats `cta-stuff`.
- `{worktree-note}` is ` (worktree at {path})` for linked worktrees, else empty.
- `{cwd}` should be an **absolute path** when possible — not a relative path like `packages/web/`. The `/handoffs` skill matches handoffs to repos via the recorded location, and relative paths can't be resolved later.
- `{repo-root}` is the value captured in §0 (canonical repo root — parent dir of the realpath of `--git-common-dir`). Omit the line entirely (don't render an empty value) if the session wasn't in a git repo.

#### Header fields: Jira / Beads / PRs

These are **structured top-level fields** (one per line, right under `Repo root:`) so future tooling can grep them cleanly. Multiple values per field are common — use comma-separated backtick-quoted tokens. Use `—` when there are none for that field. Never omit a field; if empty, render `—`.

Auto-populate from the data already gathered in §§1–2; do not ask the user. Sources, in priority order:

- **Jira**: tickets touched today (from §1's "Jira touched today" table) + any Jira keys extracted from the current branch name (e.g. `fix/AB-649-…` → `AB-649`) + any keys the chat referenced. De-duplicate. Format: `` `AB-649`, `AB-651` ``.
- **Beads**: in-progress beads (load-bearing for "what was I doing") plus any beads closed or created during this session. Format: `` `bd-123`, `bd-124` ``. Don't list every closed bead from §1 if there were many — prefer the in-progress set as the primary signal.
- **PRs**: PRs created, updated, or referenced this session (from §1's PRs-today table). Format: `` `[#42](url)`, `[#43](url)` `` — keep the markdown link form so the next session can click through. Use just `` `#42` `` if no URL is available.

If a field has more than ~4 items, keep the most relevant 4 and add ` (+N more)` after the last item rather than wrapping to a second line.

- Prefer **paths and IDs** over prose summaries — they're greppable next session.
- If the session was admin-only (no code), the resume block is *more* valuable, not less. Capture the Jira/bead context exchanged in chat — those header fields stay populated even when no code changed.

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

### 5a. 🗂️ Archive handoffs this one supersedes

Skip this step entirely if no file was saved in §5 (nothing new to supersede with).

The handoff you just wrote may continue a thread captured by an older handoff — same branch, same topic slug, or a same-day collision. Now is the moment to retire those: the supersede relationship is unambiguous because you just wrote the continuation. Archiving keeps tomorrow's `/handoffs` picker focused on the live thread without losing anything (archived files move to `~/.claude/handoffs/archive/`, still greppable).

Run the lister — it classifies supersede across all handoffs and resolves the current repo:

```bash
~/.claude/skills/handoffs/scripts/list.sh
```

Parse the `---HANDOFFS---` lines (pipe-delimited):
`{filename}|{date}|{slug}|{cwd}|{branch}|{repo-key}|{exists}|{superseded-by}|{supersede-reason}`

Select the rows where **`superseded-by` equals the filename you just saved**. Those are the older handoffs this session retires. (The lister recomputes from disk, so it already accounts for the file you just wrote.) If none match, skip silently — say nothing.

If one or more match, render:

```markdown
### 🗂️ Superseded by this handoff

Your new handoff `{new-filename}` continues these older ones:

| Date | Slug | Branch | Why |
|------|------|--------|-----|
```

- **Why**: humanise `supersede-reason` — `branch` → "same branch", `slug` → "same topic", `collision` → "same-day re-wrap".

Then prompt with `AskUserQuestion` (multiSelect, one option per superseded filename, plus the choices being which to archive):

> Archive the selected superseded handoffs to `~/.claude/handoffs/archive/`? They stay on disk (greppable) but drop out of the `/handoffs` picker. Leave any you still want surfaced.

For the selected filenames, archive them in one call:

```bash
~/.claude/skills/handoffs/scripts/archive.sh {file1} {file2} …
```

Parse the script's `---ARCHIVED---` / `---SKIPPED---` sections and confirm:

```markdown
✅ Archived {N} superseded handoff(s) to `~/.claude/handoffs/archive/`.
```

Report any `---SKIPPED---` lines verbatim (with their reason) rather than silently dropping them. Never delete — `archive.sh` only moves. If the user selects none, render nothing and move on.

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
- **No `bd` / no `.beads/`**: skip the beads sub-section and §3a silently.
- **`bd update` fails** for a selected bead: report the error inline, keep going with the rest. Don't abort the skill — the resume block is still the primary artifact.
- **§5a `list.sh`/`archive.sh` missing or erroring** (e.g. handoffs skill not installed): skip §5a silently. It's an opt-in tidy step, not load-bearing — the saved handoff is the artifact that matters.

## Notes

- This skill is intentionally *generative* in §2 and §4 — the model writes the threads and resume block from the current conversation history. The Bash fetches in §1 and §3 are mechanical guardrails so the qualitative parts are anchored in real activity rather than vibes.
- Don't suggest `git stash` as a way to "preserve" work for tomorrow without committing — stashes evaporate from memory faster than commits, and worktree pruning takes them with it. Prefer a WIP commit on a throwaway branch if there's something to save.
