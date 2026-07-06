---
name: wrap-up
description: End-of-session handoff — summarise today's commits, PRs, and beads, warn about uncommitted/unpushed work (across all repos in a multi-repo workspace, and in worktrees), and emit a paste-ready resume block. Run before `/exit`.
allowed-tools: "Bash(~/.claude/skills/wrap-up/scripts/header.sh:*), Bash(~/.claude/skills/wrap-up/scripts/activity.sh:*), Bash(~/.claude/skills/wrap-up/scripts/multirepo.sh:*), Bash(~/.claude/skills/wrap-up/scripts/handoff-path.sh:*), Bash(~/.claude/skills/landscape/scripts/working-copy.sh:*), Bash(bd update:*), Write, AskUserQuestion, Skill(tidy-settings), mcp__jira__jira_get"
model: sonnet
effort: medium
version: "0.11.0"
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
3. Settings drift — flag permissions living only in a worktree's `.claude` settings (lost on prune) and offer `/tidy-settings` to promote them.
4. Paste-ready **Resume block** capturing topic, decisions, open threads, and where to pick up.
5. Auto-save the resume block to `~/.claude/handoffs/YYYY-MM-DD-{slug}.md` when that file is free; prompt only on collision/overwrite or when choosing a different name.
6. Optional: archive older handoffs this one supersedes (same branch/topic) so the picker stays focused.
7. Reminder to run `/exit` yourself — the skill cannot exit Claude Code for you.

## Important — what this skill cannot do

- It **cannot run `/exit`**. `/exit` is a built-in CLI command, not a model-invocable tool. After the summary renders, you exit manually.
- It **cannot rename the Claude Code session** for you. `/rename` is a built-in command — only you typing it triggers a rename. Step 4 prints a paste-ready `/rename {slug}` line so you *can* rename before exiting, but the handoff file (step 4) remains the durable artifact you grep for tomorrow.

## Instructions

> **MUST re-fetch on every invocation.** Each run executes the helper scripts from scratch. Never reuse output from a prior run; state has changed since.
>
> **MUST use the dedicated helper scripts.** Never construct ad-hoc `git`/`gh`/`bd` pipelines inline — those bypass the per-script permission allowlist and produce noisy permission prompts. Specifically: §0 must go through `~/.claude/skills/wrap-up/scripts/header.sh`, §1 must go through `~/.claude/skills/wrap-up/scripts/activity.sh`, §3 must go through `~/.claude/skills/landscape/scripts/working-copy.sh` (reused — landscape and wrap-up share the same hygiene probe), and §3b must go through `~/.claude/skills/wrap-up/scripts/multirepo.sh`.

Render the sections below in order. The four helper scripts in §0, §1, §3, and §3b can run in parallel.

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
- `---SETTINGS-DRIFT---` — one `{worktree}|{file}|{count}` line per worktree settings file holding permission entries the canonical (main-worktree) copy lacks (`parse-error` instead of a count when the file isn't valid JSON). §3c renders these.

If `---GIT-COMMON-DIR---` and `---GIT-DIR---` differ, the cwd is a **linked worktree** (not the main checkout). Note this — it affects the warnings in §3. (String inequality is sufficient: the main checkout returns the same value for both — typically `.git` — while a linked worktree returns `/path/to/main/.git` for common-dir vs `/path/to/main/.git/worktrees/{name}` for git-dir.)

Capture `---REPO-ROOT---` as `{repo-root}` for the resume block in §4. It's the stable identity `/handoffs` uses to group sessions per project — independent of which worktree wrote the handoff, and resilient to the worktree being pruned later.

**If `{branch}` equals `---DEFAULT-BRANCH---` _and_ the repo has linked worktrees (>1 `---WORKTREES---` entry), the cwd is parked on the trunk.** That branch almost never holds the session's work — it usually lived on a feature branch in another worktree, and recording `main` would send `/handoffs` hunting for a PR that isn't on the trunk. Flag it here; §4 reconciles against today's actual activity before writing the resume block. **On a single-checkout repo (no linked worktrees), committing to the trunk is normal — skip the reconciliation entirely.**

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
- `---BEADS-STALE-DAYS---` — the idle grace period in days (`WRAP_UP_STALE_DAYS`, default 7). §3a names it in the prompt.
- `---BEADS-STALE-CANDIDATES---` — `bd list --status=in_progress --updated-before={today − STALE_DAYS}`: in-progress beads idle for the **whole grace period**, not merely "not touched today". This is §3a's candidate set. Windowing on a multi-day cutoff (rather than midnight) means a bead a parallel session set `in_progress` today, a bead you've worked over several days without committing, and a bead you touched earlier on a day of repeated wrap-ups all stay out of the candidate set — only genuinely-idle WIP surfaces.
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
- **Epic context.** If today's beads belong to a parent epic (multi-session work), add one line after the tables: `_Epic {id}: {closed}/{total} closed — path to goal: {a} → {b} → … → closes {goal-bead}._` Derive the chain from the blocking deps (`bd show {epic}`). When one epic dominates the session, this is far more resume-useful than three flat lists — it's the "how far are we and what unblocks the finish" view. Skip it for ad-hoc, non-epic beads.
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
3. **Linked worktree, clean, no unpushed, no stashes** → `ℹ️ Linked worktree with no code to preserve. If you prune this worktree (`git worktree remove`), only the conversation context is lost — the auto-saved resume block below is your durable recovery path.`
4. **Main checkout, clean** → no warning.

Also surface **other worktrees with unsaved work** from `---OTHER-WORKTREES-UNSAFE---` as a footnote if any exist — easy to forget those after closing the session.

**Not-yours changes.** If the working copy holds uncommitted changes you did **not** make this session — e.g. a forked or parallel session is editing the same checkout — call them out as *belonging to another session* and do **not** commit or stash them in the wrap-up. The §1 commit-author filter and your own conversation history tell you what was yours; anything else in `git status` is someone else's WIP to leave alone.

### 3b. 🗂️ Multi-repo roll-up

The §3 probe only inspects the **cwd repo**. In a multi-repo workspace (mgit services or git submodules) that silently misses unpushed/uncommitted state in sibling repos — the single most common wrap-up blind spot. Run the roll-up:

```bash
~/.claude/skills/wrap-up/scripts/multirepo.sh
```

It emits `---MARKER---` (`mgit` | `submodules` | `none`), `---ROOT---`, and `---REPOS---` lines:
`{name}|{branch}|{ahead}|{behind}|{upstream}|{modified}|{untracked}` (ahead/behind are `-` with no upstream; the root repo appears as its own row).

- **`---MARKER---` is `none`** → single repo; skip this whole section silently (§3 already covered it).
- Otherwise render only the members with something to report (ahead>0, behind>0, or modified+untracked>0); a clean+pushed member is noise. Skip the table entirely if every member is clean.

```markdown
### 🗂️ Other repos in this workspace

| Repo | Branch | Unpushed | Behind | Uncommitted |
|------|--------|----------|--------|-------------|
```

- **Unpushed**: `{ahead}`, or `no upstream` when upstream=no (local-only, never pushed).
- **Behind**: show only when >0. A member that's **diverged** (ahead>0 AND behind>0) needs a rebase/pull before it can push — flag it explicitly: `⚠️ diverged — N ahead / M behind`.
- **Uncommitted**: `{modified} modified / {untracked} untracked` (omit zero parts).

Load-bearing for resume: a service repo left ahead-but-unpushed, or a deploy/config repo left diverged, is exactly what tomorrow forgets. Feed any unpushed/diverged members into the resume block's **Open threads** or **Blocked on you** field (§4).

### 3c. ⚙️ Worktree settings drift

Skip this section silently if §0's `---SETTINGS-DRIFT---` was empty (not a git repo, no linked worktrees, no drift — or no `python3`, in which case `/tidy-settings` remains the manual path).

Each line is `{worktree}|{file}|{count}`: `{count}` permission entries that live **only** in that worktree's `.claude/{file}` and not in the canonical main-worktree copy. For `settings.local.json` (gitignored, per-worktree) those entries are deleted forever when the worktree is pruned — that's the high-stakes case, and exactly the loss this check exists to prevent. For `settings.json` (git-tracked) the drift is an uncommitted edit; committing it is the fix, and §3's hygiene warnings already cover uncommitted files.

Render one line per drifting file:

```markdown
### ⚙️ Worktree settings drift

⚙️ {count} permission(s) in `{worktree}/.claude/{file}` exist only in that worktree — pruning it loses them.
```

(For a `parse-error` count, render `` `{file}` does not parse — `/tidy-settings` will diagnose `` instead.)

Then offer to fix it now with `AskUserQuestion` — options: **Run /tidy-settings**, **Skip — note in resume block**.

- **Run /tidy-settings** → invoke the `tidy-settings` skill via the Skill tool, then resume the wrap-up at §3a. Its worktree-promotion triage is the authoritative flow — do **not** reimplement the diff or copy entries between settings files yourself.
- **Skip** → add a bullet to §4's **Open threads**: `{count} worktree-only permission(s) in {worktree} — run /tidy-settings before pruning`.

### 3a. 🧹 Stale in-progress beads

Skip this whole section if `---BEADS-STATUS---` was `NO_BD`/`NO_BEADS_IN_REPO` or if `---BEADS-STALE-CANDIDATES---` was empty.

Work from `---BEADS-STALE-CANDIDATES---`, **not** the full `---BEADS-IN-PROGRESS---` list — it's already pre-filtered to beads idle for the whole grace period (`---BEADS-STALE-DAYS---`, default 7 days), so a bead updated within that window — actively worked by a parallel session, carried over several days, or touched earlier on a day of repeated wrap-ups — won't appear. For each candidate bead, check whether its ID (e.g. `bd-123`) appears in any of today's signals:

- Commit subjects (§1 Commits)
- Branch names from the worktree list (§1 Commits, second column)
- PR titles (§1 PRs today)
- The current branch (§0)

A bead with **no match in any of those** is "stale in_progress" — moved to `in_progress` and idle for `---BEADS-STALE-DAYS---`+ days since, with no commit/branch/PR trace today. Tomorrow's `/landscape` will misreport it as live WIP. Bead hygiene matters: always flag these — don't quietly skip the section.

If any stale beads exist, render (substitute the actual `{stale-days}` from `---BEADS-STALE-DAYS---`):

```markdown
### 🧹 Stale in-progress

These beads are in_progress but have been idle for {stale-days}+ days, with no commits, PRs, or branch references today:

| ID | Type | Pri | Title |
|----|------|-----|-------|
```

Then prompt with `AskUserQuestion` (multiSelect, options are the bead IDs):

> Demote selected beads back to `ready` so tomorrow's WIP list is honest? Skip any you genuinely intend to keep open — e.g. design work in chat only, or a long-running task still live in a parallel session.

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

> **Gate — skip this whole sub-section unless the repo has linked worktrees** (more than one `---WORKTREES---` entry from §0). With only the main checkout there is no other-worktree feature branch to recover, so just record the current branch as-is (even the trunk). The reconciliation below is worktree-specific machinery and pure noise for projects that don't use worktrees — don't run it for them.

The resume block's `{branch}` and `{cwd}` default to §0's current cwd and branch. But when §0 flagged that `{branch}` equals `---DEFAULT-BRANCH---` (the cwd is parked on `main`/`master`), that branch is almost never where the session's work lived — recording it sends `/handoffs` looking for a PR on the trunk (there is none) and leaves liveness detection blind to the real feature branch.

When parked on the trunk, pick a better resume target from the data already gathered, in priority order:

1. **Today's commits on a feature branch** — a non-default branch in §1's Commits table with commits today. Map it to its worktree path via §0's `---WORKTREES---`.
2. **A PR created/merged today** (§1 PRs) whose head branch is a feature branch.
3. **The topic ticket** — a branch in `---WORKTREES---` whose name contains the topic slug's ticket (e.g. slug `ab-1505-…` → branch `fix/AB-1505-…`).

Then:

- **Exactly one feature branch stands out** → record *that* branch as `{branch}` and its worktree path as `{cwd}` (set `{worktree-note}` to `(worktree at {path})` if it's a linked worktree). Surface the swap so it's visible, not silent:

  `> Wrapped from `{cwd-on-trunk}` (on `{default-branch}`), but today's work is on `{feature-branch}` in `{feature-worktree}` — recording that as the resume location.`

- **Several feature branches are in play, or it's ambiguous** → ask with `AskUserQuestion` which branch/worktree the next session should resume in. Options: each candidate `{branch} — {worktree basename}`, plus `Stay on {default-branch}`.
- **No feature branch at all** (the session committed directly to the trunk, or did no code) → keep the trunk. That's correct, not the bug — don't invent a branch.

`{repo-root}` is unaffected — it's the same repo regardless of which worktree you record.

```markdown
### Resume block

```markdown
# Resume: {topic-slug} — {YYYY-MM-DD} {HH:MM}

**Where to pick up:** `{cwd}` on branch `{branch}`{worktree-note}
**Repo root:** `{repo-root}`
**Jira:** {jira-field}
**Beads:** {beads-field}
**Deliverable:** {deliverable-field}
**PRs:** {prs-field}

**Context:**
- {one-line framing of what we're doing and why}

**Decisions so far:**
- {bullet}

**Open threads:**
- {bullet}

**Blocked on you (manual ops):**
- {human-only action the agent could not do — secret to seal, deploy/sync to run, push reserved by the permission classifier, access to grant — omit the whole section if none}

**Suggested next step:**
- {one concrete action — file to open, command to run, person to ask, ticket to read}

**Pointers:**
- {free-form ancillary refs: dashboards, commits worth re-reading, people to ask — or omit the section entirely if nothing to add}
```
```

Guidance for the model when filling this in:

- Keep it short. A resume block longer than ~30 lines is a signal to split the work into multiple beads instead.
- `{YYYY-MM-DD}` and `{HH:MM}` both come from the header script's `---DATE---` field (`date '+%A %Y-%m-%d %H:%M'`). The time disambiguates several same-day handoffs in the `/handoffs` picker — `list.sh` reads it back from this header line (falling back to file mtime for older handoffs), so keep the `{YYYY-MM-DD} {HH:MM}` shape on the `# Resume:` line intact.
- **Blocked on you (manual ops)** is for actions only the human can take — sealing secrets, running deploys / `make …-sync`, pushes the permission classifier reserved, granting access. Keep these out of "Suggested next step" (which is the *agent's* next move). Omit the field entirely when there are none — most sessions have none.
- `{topic-slug}` is kebab-case, ≤4 words. Pick the most specific noun phrase — `ab-1107-cta-event` beats `cta-stuff`.
- `{worktree-note}` is ` (worktree at {path})` for linked worktrees, else empty.
- `{cwd}` should be an **absolute path** when possible — not a relative path like `packages/web/`. The `/handoffs` skill matches handoffs to repos via the recorded location, and relative paths can't be resolved later.
- `{repo-root}` is the value captured in §0 (canonical repo root — parent dir of the realpath of `--git-common-dir`). Omit the line entirely (don't render an empty value) if the session wasn't in a git repo.

#### Header fields: Jira / Beads / PRs

These are **structured top-level fields** (one per line, right under `Repo root:`) so future tooling can grep them cleanly. Multiple values per field are common — use comma-separated backtick-quoted tokens. Use `—` when there are none for that field. Never omit a field; if empty, render `—`.

Auto-populate from the data already gathered in §§1–2; do not ask the user. Sources, in priority order:

- **Jira**: tickets touched today (from §1's "Jira touched today" table) + any Jira keys extracted from the current branch name (e.g. `fix/AB-649-…` → `AB-649`) + any keys the chat referenced. De-duplicate. Format: `` `AB-649`, `AB-651` ``.
- **Beads**: in-progress beads (load-bearing for "what was I doing") plus any beads closed or created during this session. Format: `` `bd-123`, `bd-124` ``. Don't list every closed bead from §1 if there were many — prefer the in-progress set as the primary signal. This is the **full context** list — own work *and* recurring "in-progress elsewhere" / parent-epic beads.
- **Deliverable**: the subset of `Beads` that is **this session's own work** — the bead(s) whose closure means *this handoff is finished*. Derive it from the beads referenced in **today's commits in this repo** (§1's activity) and/or the bead the session actively worked, in_progress or just closed. **Exclude** context beads (recurring "in-progress elsewhere", another session's WIP) and parent epics — they appear in `Beads` only. Format: `` `bd-123` ``. This is what `/handoffs` and `/handoffs-tidy` key their "done" check on for trunk repos (where everything commits to `master`, so there's no branch/PR signal). **When unsure, include rather than omit** — an extra bead only delays the handoff being marked done (safe); omitting an own-work bead can make it look done while live work remains. Use `—` when the session delivered nothing of its own (pure context/triage/discussion) — then the handoff stays live until something else marks it done.
- **PRs**: PRs created, updated, or referenced this session (from §1's PRs-today table). Format: `` `[#42](url)`, `[#43](url)` `` — keep the markdown link form so the next session can click through. Use just `` `#42` `` if no URL is available.

If a field has more than ~4 items, keep the most relevant 4 and add ` (+N more)` after the last item rather than wrapping to a second line. (For `Deliverable`, a `(+N more)` truncation makes the bead-closure check un-verifiable — so keep that field complete; it's own-work only and should rarely exceed a couple of beads.)

- Prefer **paths and IDs** over prose summaries — they're greppable next session.
- If the session was admin-only (no code), the resume block is *more* valuable, not less. Capture the Jira/bead context exchanged in chat — those header fields stay populated even when no code changed.

### 5. 💾 Save the resume block (auto-save unless collision)

Persisting the resume block is the point of `/wrap-up`: `/handoffs`, `/landscape`, and launchers such as `pl` consume the file under `~/.claude/handoffs/`. Do **not** require an extra confirmation for the normal new-file case.

First compute the canonical target path and the next-free path:

- `{target-path}` = the expanded absolute path `$HOME/.claude/handoffs/{YYYY-MM-DD}-{slug}.md` (display it as `~/.claude/...` if you like, but compare/write the absolute path)
- `{chosen-path}` comes from the helper:

```bash
~/.claude/skills/wrap-up/scripts/handoff-path.sh {YYYY-MM-DD} {slug}
```

The helper `mkdir -p`s the handoffs dir and prints an absolute `{target-path}` when that file does not exist; otherwise it prints the first free collision suffix (`…-2.md`, `…-3.md`, …).

#### No collision — auto-save

If `{chosen-path}` is exactly `{target-path}`, write the resume block to `{target-path}` immediately with `Write` and print:

```markdown
Saved to `{target-path}`.
```

Do not ask **Save / Don't save** in this case — Pi users can miss the prompt and accidentally leave only a transient chat/clipboard note.

#### Collision — prompt before writing

If `{chosen-path}` differs from `{target-path}`, then `{target-path}` already exists. Prompt with `AskUserQuestion` (or plain text if needed):

> `~/.claude/handoffs/{YYYY-MM-DD}-{slug}.md` already exists. Save this handoff how?

Options:

- **Save with different name** — ask for a replacement slug (default suggestion: `{slug}-2` or a more specific topic slug), then run the helper again with that slug and write to exactly the path it prints.
- **Overwrite** — write to `{target-path}` only after the user explicitly chooses overwrite.
- **Don't save** — leave no file; keep the resume block visible in the transcript.

The `-N` collision suffix is a first-class convention `/handoffs` understands: `list.sh` strips it for grouping but folds it into recency rank, so suffixed files sort correctly and read each file's real time from its `# Resume:` header. If the user chooses a different name, still use the helper so uniqueness is mechanical.

#### Save failure

If writing fails for any reason, do **not** lose the handoff. Print the resume block again, followed by:

```markdown
⚠️ Failed to save handoff to `{attempted-path}`: {error}
```

The directory naming convention (`~/.claude/handoffs/YYYY-MM-DD-slug.md`) means `ls ~/.claude/handoffs/` is a chronological log of session topics — easy to grep for "what was I doing about X last week."

### 5a. 🗂️ Tidy superseded handoffs → `/handoffs-tidy`

The supersede-detection + archive flow has been **moved out to its own `/handoffs-tidy` command** — it was heavy to carry on every wrap-up, and pruning is a distinct intent from handing off. After saving (§5), if this handoff continues an older thread you want to retire, run **`/handoffs-tidy`** (it reuses the same `handoffs/scripts/list.sh` + `archive.sh`). Wrap-up itself no longer touches `~/.claude/handoffs/archive/`.

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
- **Multi-repo roll-up (§3b) errors or finds nothing**: skip the section silently — single-repo sessions hit this normally; it's additive, not load-bearing.
- **Settings-drift probe (§3c) empty or `python3` missing**: skip the section silently. `/tidy-settings` run by hand covers the same ground.
- **`/tidy-settings` invocation fails from §3c**: fall back to the Skip path (note the drift in the resume block's open threads) and continue the wrap-up.
- **Handoff save fails (§5)**: keep the resume block visible, print the attempted path and error, and continue to the footer. The generated block is still the recovery artifact even if the durable file write failed.

## Notes

- This skill is intentionally *generative* in §2 and §4 — the model writes the threads and resume block from the current conversation history. The Bash fetches in §1 and §3 are mechanical guardrails so the qualitative parts are anchored in real activity rather than vibes.
- **Stale-bead grace period.** §3a only flags in-progress beads idle for `WRAP_UP_STALE_DAYS` days (default 7), not merely "untouched today". This is what stops repeated same-day wrap-ups — and multi-day work-in-chat — from nagging you to demote beads that are still live. Tighten it (`export WRAP_UP_STALE_DAYS=3`) if you want drift caught sooner, or loosen it further if even weekly prompts are too eager. A non-numeric value falls back to 7.
- Don't suggest `git stash` as a way to "preserve" work for tomorrow without committing — stashes evaporate from memory faster than commits, and worktree pruning takes them with it. Prefer a WIP commit on a throwaway branch if there's something to save.
