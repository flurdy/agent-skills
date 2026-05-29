---
name: handoffs
description: Browse handoff files saved by /wrap-up and pick one to resume. Lists this repo's handoffs in full (including ones whose worktree has been pruned) and summarises other repos by count. Companion to /wrap-up and /landscape.
allowed-tools: "Bash(~/.claude/skills/handoffs/scripts/list.sh:*), Bash(~/.claude/skills/handoffs/scripts/archive.sh:*), Bash(git worktree add:*), Bash(git rev-parse:*), Read, AskUserQuestion"
model: sonnet
effort: medium
version: "0.9.1"
author: "flurdy"
---

# Handoffs — Pick a saved session to resume

Browse handoff files written by `/wrap-up` (in `~/.claude/handoffs/`) and pick one to resume. Companion to `/wrap-up` (the writer) and `/landscape` (the morning orienter).

## When to use

- Starting a session and wanting to pick up a thread from a previous one.
- After `/landscape` flagged that recent handoffs exist for this repo.
- Searching for an older thread — `ls ~/.claude/handoffs/` is grep-friendly, but this skill renders the metadata table.

## What it does

1. List handoffs across all repos, with per-repo counts.
2. **Fully detail** handoffs in the current repo as a pickable table, flagging which are superseded by a newer handoff or stale (branch merged/gone).
3. **Summarise** handoffs in other repos (count per repo, not full listing).
4. Optionally archive superseded/stale handoffs (opt-in) to keep the picker focused.
5. Prompt you to pick one — only handoffs for the current repo are pickable.
6. On pick, render the resume block inline and surface the `cd` if the recorded worktree differs from pwd.

## Important — what this skill cannot do

- It **cannot resume** for you. It surfaces the resume block; you read it and act on the next step.
- It **cannot pick handoffs from other repos**. That is a deliberate guard — running commands against the wrong repo is the failure mode it prevents. To resume a handoff in another repo, `cd` there and run `/handoffs` again.
- It **never deletes** handoff files. The opt-in archive step (§3b) only *moves* superseded ones into `~/.claude/handoffs/archive/` — they stay on disk and greppable. Everything else you curate manually.

## Instructions

> **MUST use the helper script.** Never construct ad-hoc `ls`/`grep` pipelines against `~/.claude/handoffs/` — they bypass the per-script permission allowlist and miss the repo-matching logic.

### 1. Run the helper

```bash
~/.claude/skills/handoffs/scripts/list.sh --check-branches
```

`--check-branches` adds branch-liveness classification (the `branch-state` field) for current-repo handoffs. It runs one `git ls-remote` (network, timeout-guarded) plus local merge-base checks. It is current-repo-only — the git queries run in pwd, so handoffs in other repos always report `unknown`.

Parse the delimited output:

- `---CURRENT-REPO---` — current repo identity (origin URL preferred, falling back to realpath of git-common-dir), or `NONE` if not in a repo.
- `---CURRENT-REPO-DISPLAY---` — short label for the current repo (basename of the repo root), or `NONE`.
- `---RECENT-WINDOW-DAYS---` — days used for the "recent" filter (3 default; Mon → 3, Tue → 4 weekend buffer).
- `---HANDOFFS-DIR---` — directory scanned (`~/.claude/handoffs`).
- `---HANDOFFS---` — one pipe-delimited line per handoff, newest first: `{filename}|{date}|{slug}|{cwd}|{branch}|{repo-key}|{exists}|{superseded-by}|{supersede-reason}|{branch-state}`.
- `---CURRENT-REPO-LATEST---` — a single `{slug}|{branch}|{date}` line for the newest current-repo handoff (the "last session"), or empty. Consumed by `/landscape`'s footnote; this skill renders the full table instead and can ignore it.
- `---SUMMARY---` — `total=N`, `current_repo_total=N`, `current_repo_recent=N`, `current_repo_recent_live=N` (recent and not superseded), `current_repo_pruned=N`, `current_repo_superseded=N`, `current_repo_stale=N`, `other_repos=N`, `pruned_total=N`, `superseded_total=N`, `unresolved=N`.
- `---OTHER-REPOS---` — one line per distinct non-current repo: `{repo-key}|{count}|{display}`, sorted by count desc.

Repo identity rules:
- Resolution order per handoff: (1) the **`Repo root:`** line if the handoff was written by wrap-up v0.2.0+, then (2) walking up the `Where to pick up:` cwd to find a parent repo.
- Identity prefers `remote.origin.url` so independent clones of the same upstream collapse to one row; falls back to realpath of git-common-dir for local-only repos.
- `.claude`-symlink unification: if a repo root's `.claude` is a symlink whose target lives inside another git repo, that other repo's identity wins (one hop, no cycles).
- Pruned worktrees still resolve — the walk-up climbs out of the deleted directory to a still-existing parent.
- `repo-key` is `UNRESOLVED` only when neither the `Repo root:` field nor the cwd walk-up finds a repo. Older handoffs that recorded a relative path may end up here.
- `exists=Y` means the original recorded cwd still exists on disk. `exists=N` means it was pruned — the handoff is still pickable (you'll resume in your current checkout or a fresh worktree).

Supersede fields:
- `superseded-by` is the filename of the **newest** handoff in the same repo that continues this thread, or empty if this is the live tip. `supersede-reason` is `branch` (same branch), `slug` (same exact topic slug), or `collision` (same-day re-wrap of the same topic). Ticket/cwd overlap is deliberately *not* a supersede signal — a ticket legitimately spans many handoffs.
- A superseded handoff is still pickable; the field just flags that a newer continuation exists, so the picker can steer you to it and the archive step can offer to retire it.

Branch-state field (only populated with `--check-branches`, current-repo rows only):
- `live` — branch exists and isn't merged into the default branch.
- `merged` — branch tip is an ancestor of the default branch (its PR likely landed).
- `gone` — branch exists neither locally nor on the remote (deleted after merge, or abandoned).
- `unknown` — couldn't determine (other repo, branch `?`, or offline with no local ref). **Never treated as stale** — absence of evidence isn't evidence of deadness.
- `merged` and `gone` are the two "stale" states. Offline runs degrade safely: a branch with no local ref reports `unknown`, never a false `gone`.

### 2. Render the current-repo table

If `current_repo_total > 0`:

```markdown
### 🧷 Handoffs — this repo ({count})

| Date | Slug | Branch | Where | Worktree | Status |
|------|------|--------|-------|----------|--------|
```

- **Slug**: from the filename (e.g. `ab-1107-cta-event`).
- **Branch**: from the parsed line; `?` if unknown.
- **Where**: basename of the recorded cwd. Append ` (current)` if it matches pwd. Special cases: empty cwd → `—`; cwd ending in `/` → use the next-up segment, e.g. `worktrees/` → `(worktrees root)`.
- **Worktree**: ✅ if `exists=Y`; ⚠ `pruned` if `exists=N`. Everything in the current-repo table is pickable by definition (handoffs that couldn't be matched to a repo never reach this table), so no separate Pickable column.
- **Status**: pick the first that applies, in this order:
  1. `superseded-by` non-empty → `↩ superseded` with the newer handoff's slug and reason, e.g. `↩ by ge-1470-complete (same branch)`. Humanise the reason: `branch` → "same branch", `slug` → "same topic", `collision` → "same-day re-wrap". Derive the newer slug from the `superseded-by` filename (strip the `YYYY-MM-DD-` prefix and `.md`).
  2. `branch-state` = `merged` → `🔵 merged` (branch landed).
  3. `branch-state` = `gone` → `⚪ branch gone`.
  4. otherwise → `🟢 live` (treat `unknown` as live — we have no evidence it's dead).
  Supersede wins over branch-state because "a newer handoff continues this" is the more actionable signal; the branch-state of a superseded row is moot.

If `current_repo_total == 0` and `CURRENT-REPO != NONE`:
`_No handoffs for this repo ({CURRENT-REPO-DISPLAY})._`

If `CURRENT-REPO == NONE`:
`_Not in a git repo — handoffs cannot be matched to a current repo. Showing global counts only._`

**Render this section exactly once, in this position.** Do not repeat the "No handoffs for this repo" sentence later (e.g. after §3's other-repos table) — once is enough. If `current_repo_total == 0` but other repos exist, the next section's table provides the rest of the context.

### 3. Render the other-repos summary

If `other_repos > 0`:

```markdown
### 🗂️ Handoffs — other repos ({other_repos})

| Repo | Handoffs |
|------|----------|
```

- **Repo**: use the `{display}` field from each `---OTHER-REPOS---` line (the script has already stripped `.git` and taken the basename).
- Rows already arrive sorted by count desc — render in that order.
- Do **not** list individual files — that's the point of "summarise."

Otherwise skip the whole section.

If `unresolved > 0`, surface them. When `unresolved ≤ 5`, list each one by filename so the user can `cat` it directly — a bare count is unactionable. When `unresolved > 5`, fall back to a count footnote to avoid clutter.

`unresolved ≤ 5`:

```markdown
_⚠ {unresolved} handoff(s) could not be matched to any repo (recorded path is invalid or its parent tree is gone):_
- `~/.claude/handoffs/{filename}`
- `~/.claude/handoffs/{filename}`
```

Pull the filenames straight from the `---HANDOFFS---` section where `repo-key=UNRESOLVED`. Render in the same newest-first order the script emits.

`unresolved > 5`:

```markdown
_⚠ {unresolved} handoff(s) could not be matched to any repo (recorded path is invalid or its parent tree is gone). Run `grep -L "Repo root:" ~/.claude/handoffs/*.md` to find them._
```

**Do not add a global pruned-count footnote.** The Worktree column in the current-repo table already makes pruning visible per-row. Add a one-time pickability hint immediately under the current-repo table (when `current_repo_pruned > 0`):

```markdown
_⚠ pruned = original worktree no longer exists; still pickable — you'll resume in your current checkout or a fresh worktree._
```

This is a tooltip-style explainer keyed to the column legend, not a count. Skip it when `current_repo_pruned == 0`.

### 3b. 🗂️ Archive cleanup candidates (opt-in)

Skip this step if `current_repo_superseded == 0` **and** `current_repo_stale == 0`.

Two kinds of current-repo handoff clutter the picker without pointing at live work. Offer to retire them — archiving **moves** them to `~/.claude/handoffs/archive/` (still on disk, still greppable; just out of the active listing). This is opt-in and never automatic — the rows stay pickable until the user says so.

The two kinds differ in regret, so present them as **distinct groups** and be honest about the difference:

- **Superseded** (Status `↩`) — a newer handoff in this repo continues the thread. Low regret: the context lives on in the newer file.
- **Stale** (Status `🔵 merged` / `⚪ branch gone`) — the branch landed or was deleted, and *no newer handoff supersedes it*. Higher regret: this may be the **only** record of that thread. Default to leaving these unless the user is sure. (A row that is both superseded and stale belongs in the Superseded group — supersede is the safer reason to archive.)

Prompt with `AskUserQuestion` (multiSelect). One option per candidate, labelled `{date} {slug}`, described by its group:
- superseded → `↩ superseded by {newer-slug}`
- stale → `🔵 merged — no newer handoff` / `⚪ branch gone — no newer handoff`

> Archive these to `~/.claude/handoffs/archive/`? They stay on disk (greppable), just out of the picker. **Superseded** ones are safe — a newer handoff carries the context. **Stale** ones may be the only record of that thread, so leave any you might still want.

For the selected filenames, archive them in one call:

```bash
~/.claude/skills/handoffs/scripts/archive.sh {file1} {file2} …
```

Parse the script's `---ARCHIVED---` / `---SKIPPED---` sections and confirm:

```markdown
✅ Archived {N} handoff(s) to `~/.claude/handoffs/archive/`.
```

Surface any `---SKIPPED---` lines verbatim with their reason. After archiving, **drop the archived rows** from the current-repo table for the rest of this run (and subtract them from `current_repo_total`) so §4's picker doesn't offer them. Only offer rows marked superseded or stale (`merged`/`gone`); never a `🟢 live` or `unknown` row. Never delete — `archive.sh` only moves. If the user selects none, render nothing and continue to §4.

### 4. Pick a handoff (current repo only)

If `current_repo_total == 0`, skip this step.

If `current_repo_total` is between 1 and 4, use `AskUserQuestion`:

- Option label: `{date} {slug}` (truncate slug if needed to stay under the chip width).
- Option description: `Branch: {branch} | Where: {basename of cwd}`.

If `current_repo_total > 4`, do **not** force the picker (the option cap is 4). Instead, print:

```markdown
**Pick one to load:** reply with the slug or filename (e.g. `ge-1344-login-state-decision` or `2026-05-21-ge-1344-login-state-decision.md`).
```

Only pickable rows (✅) are valid choices. Pruned-worktree handoffs are pickable — they just resume in a different checkout. If the user picks an unresolved one, point them at `cat ~/.claude/handoffs/{filename}` for read-only access.

### 5. Load the picked handoff

Use the `Read` tool on the absolute path `{HANDOFFS-DIR}/{filename}`.

Render the file content **verbatim** inside a fenced block so the rest of the session treats it as resume context:

````markdown
### 📥 Loaded: `{filename}`

```markdown
{file contents}
```
````

Then offer the right follow-up based on `exists`:

#### `exists=Y` — worktree still on disk

If recorded cwd differs from pwd:

```markdown
**Switch directory:** `cd {cwd}` _(handoff was recorded in a different worktree of this repo)_
```

If recorded cwd matches pwd: no extra note.

(Don't run `cd` yourself — shell state doesn't persist across Bash calls.)

#### `exists=N` — worktree was pruned

**First, check whether this handoff is superseded.** If the picked row's `superseded-by` field is non-empty, a newer handoff already continues this thread (same branch, topic, or same-day re-wrap — see `supersede-reason`). Look up that newer row by filename; if it has `exists=Y`, the work likely moved to a live worktree — surface it as the recommended option *before* asking about recreation:

> Original worktree `{cwd}` is gone. A newer handoff `{newer-slug}` ({humanised reason}) continues this thread in `{newer-where}` (still on disk). What would you like to do?

Options (use `AskUserQuestion`):
- **Load the newer handoff instead** — `Open {newer-filename} from {newer-where} (recommended)`. Treat as if the user had picked that filename in §4 — go back to the top of §5 with the new file.
- **Recreate this worktree** — proceed with the regular worktree-creation flow below.
- **Resume here** — stay in the current checkout.

If `superseded-by` is empty (or the newer handoff is itself pruned, `exists=N`), skip this prompt.

**Second, check whether pwd is already on the handoff's branch.** Run:

```bash
git rev-parse --abbrev-ref HEAD
```

If the output equals the handoff's `{branch}`, the user is already on a viable landing spot (likely a fresh worktree they prepared). Don't prompt for worktree creation — just render:

```markdown
**Already on `{branch}` here** (`{pwd}`). No worktree action needed — resume from this checkout.
```

Then skip to §6. Only fall through to the worktree-creation prompt when pwd's branch differs from the handoff's branch.

---

Offer to recreate the worktree. Compute the proposed values:

- `{worktree-path}` = the recorded cwd if its parent directory still exists on disk; otherwise `{pwd}/../worktrees/{basename of recorded cwd}`. If the basename is empty or generic (`worktrees`, `.`), use `{topic-slug}` from the filename instead.
- `{branch}` = the branch parsed from the handoff (Branch column).

Ask via `AskUserQuestion`:

> Original worktree `{cwd}` is gone. Recreate it?

Options:
- **Create worktree** — runs `git worktree add {worktree-path} {branch}` in the current repo.
- **Resume here** — stay in the current checkout (`{pwd}`); user can `git checkout {branch}` themselves if they want.
- **Show command** — prints the `git worktree add` invocation without running.

On **Create worktree**:

```bash
git worktree add "{worktree-path}" "{branch}"
```

If the command succeeds, render:

```markdown
✅ Worktree created at `{worktree-path}`.

**Switch directory:** `cd {worktree-path}`
```

If it fails (path already exists, branch missing locally, dirty index, …), surface the stderr and fall back to **Show command** behaviour. Do not retry, do not delete anything, do not `--force`.

On **Resume here**:

```markdown
**Resuming in current checkout** (`{pwd}`). If you need the branch, run `git checkout {branch}` (the pruned worktree's commits are still in the repo).
```

On **Show command**:

```markdown
**Worktree pruned.** Original location `{cwd}` no longer exists. To recreate it yourself:

```bash
git worktree add {worktree-path} {branch}
```
```

### 6. Footer

```markdown
---
**Next:** act on the resume block's *Suggested next step*. Run `/landscape` for a fresh orientation if more than a day has passed since the handoff was written.
```

## Failure modes

Each step is independent — a failure in one should not block the others.

- **`~/.claude/handoffs/` missing**: render `_No handoffs directory yet. Run /wrap-up at the end of a session to create one._` and stop.
- **Empty directory**: render `_No handoffs saved yet._` and stop.
- **Not in a git repo**: render the other-repos summary (everything is "other"); skip the pickable table and step 4.
- **Picked handoff is unreadable**: report the path and suggest `cat` — don't fabricate content.
- **Offline / remote unreachable** (`git ls-remote` fails or times out): branch-state degrades to local-only — `merged` is still detected against the local default tip, but branches with no local ref report `unknown` rather than a false `gone`. The skill keeps working; the stale group in §3b just shrinks. Don't retry the network call.

## Notes

- Handoffs are written by `/wrap-up`. If a session ends without `/wrap-up`, there is nothing here to recover. That's intentional — the index lists `/wrap-up` next to `/handoffs` for a reason.
- File naming convention: `~/.claude/handoffs/YYYY-MM-DD-{slug}.md`. Collision suffixes from wrap-up (`-2`, `-3`, …) are preserved as part of the slug.
- Picking a handoff does **not** clean it up. Old handoffs accumulate by design — they're cheap and grep-friendly. The §3b archive step retires only *superseded* ones (and only on request); sweep the rest by hand.
- Supersede classification comes from `list.sh`, not the model — same source `/wrap-up` uses for its at-save archive offer, so both skills agree on what supersedes what. Reasons: `branch` > `slug` > `collision`; ticket/cwd overlap is intentionally excluded.
- Stale (branch-liveness) is **current-repo-only** and opt-in via `--check-branches` — the git queries run in pwd, so other repos always report `unknown`. It's deliberately separate from supersede: superseded = "a newer handoff continues this" (low-regret archive); stale = "the branch is dead and nothing supersedes it" (may be the only record — higher regret).
- Repo matching uses `remote.origin.url` first, then realpath of git-common-dir. Linked worktrees of one repo share the same key. Two independent clones with the same origin URL collapse to one row.
- **`.claude` symlink unification** has two flavours:
  - **Non-bare** — A's `.claude` symlinks to B's `.claude` subdir. A defers to B's identity. Display is B's basename.
  - **Bare** — A's `.claude` symlinks to B's repo root itself (B is just a scratch state-holder, not a working project). A keeps its own identity (and display); when B resolves on its own (e.g. via a handoff whose cwd lands inside B), a one-level sibling scan finds A's bare link pointing at B and defers up. Net effect: both ends group under A, the "real" repo. The follow is one-hop in either direction, so reciprocal links don't cycle.
- Pruned-worktree handoffs are pickable: the script walks up the recorded path to find the parent repo, so even after `git worktree remove` the handoff still groups correctly. When picked, the user resumes from their current checkout (or creates a fresh worktree).
