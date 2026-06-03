---
name: handoffs
description: Browse handoff files saved by /wrap-up and pick one to resume. Lists this repo's handoffs in full (including ones whose worktree has been pruned) and summarises other repos by count. Companion to /wrap-up and /landscape.
allowed-tools: "Bash(~/.claude/skills/handoffs/scripts/list.sh:*), Bash(~/.claude/skills/handoffs/scripts/archive.sh:*), Bash(git worktree add:*), Bash(git rev-parse:*), Bash(git status:*), Bash(git branch:*), Bash(git checkout:*), Read, AskUserQuestion"
model: sonnet
effort: medium
version: "0.12.0"
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
2. **Fully detail** handoffs in the current repo as a pickable table, flagging which are superseded by a newer handoff, shipped (PR merged), or stale (branch gone / PR closed).
3. **Summarise** handoffs in other repos (count per repo, not full listing).
4. Optionally archive superseded/stale handoffs (opt-in) to keep the picker focused.
5. Prompt you to pick one — only handoffs for the current repo are pickable.
6. On pick, render the resume block inline and surface the `cd` if the recorded worktree differs from pwd.

## Important — what this skill cannot do

- It **cannot resume** for you. It surfaces the resume block; you read it and act on the next step.
- It **cannot rename the session** for you. On load it prints a paste-ready `/rename {slug}` line (§5), but `/rename` is a built-in command — only you typing it triggers a rename.
- It **cannot pick handoffs from other repos**. That is a deliberate guard — running commands against the wrong repo is the failure mode it prevents. To resume a handoff in another repo, `cd` there and run `/handoffs` again.
- It **never deletes** handoff files. The opt-in archive step (§3b) only *moves* superseded ones into `~/.claude/handoffs/archive/` — they stay on disk and greppable. Everything else you curate manually.

## Instructions

> **MUST use the helper script.** Never construct ad-hoc `ls`/`grep` pipelines against `~/.claude/handoffs/` — they bypass the per-script permission allowlist and miss the repo-matching logic.

### 1. Run the helper

```bash
~/.claude/skills/handoffs/scripts/list.sh --check-branches
```

`--check-branches` adds branch-liveness classification (the `branch-state` field) for current-repo handoffs. It runs one `git ls-remote` (network, timeout-guarded) plus local merge-base checks. It is current-repo-only — the git queries run in pwd, so handoffs in other repos always report `unknown`.

**PR detection auto-enables** (no separate flag) whenever `--check-branches` is active **and** `gh` is on `PATH`. It adds one batched, timeout-guarded `gh pr list` (mapped to branches locally) and fills the `pr-state`/`pr-number`/`pr-url` fields. It's tied to `--check-branches` so that `/landscape` (`--summary-only`) and `/wrap-up` (no flags) stay network-free. If `gh` is missing, unauthenticated, or times out, every row reports `pr-state=unknown` and the local branch-state heuristic stands.

Parse the delimited output:

- `---CURRENT-REPO---` — current repo identity (origin URL preferred, falling back to realpath of git-common-dir), or `NONE` if not in a repo.
- `---CURRENT-REPO-DISPLAY---` — short label for the current repo (basename of the repo root), or `NONE`.
- `---RECENT-WINDOW-DAYS---` — days used for the "recent" filter (3 default; Mon → 3, Tue → 4 weekend buffer).
- `---HANDOFFS-DIR---` — directory scanned (`~/.claude/handoffs`).
- `---HANDOFFS---` — one pipe-delimited line per handoff, newest first: `{filename}|{date}|{slug}|{cwd}|{branch}|{repo-key}|{exists}|{superseded-by}|{supersede-reason}|{branch-state}|{pr-state}|{pr-number}|{pr-url}|{archive-class}`.
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
- **Trunk co-residence never supersedes.** The `branch` reason excludes the default branch (`main`/`master`): two distinct threads both recorded on the trunk (the wrap-up trunk-parking case) are *not* the same thread, so they only supersede each other on an exact slug or same-day collision — never on sharing `main`. This mirrors the `branch-state` trunk guard; both stem from the trunk being a meaningless thread/liveness signal.
- A superseded handoff is still pickable; the field just flags that a newer continuation exists, so the picker can steer you to it and the archive step can offer to retire it.

Branch-state field (only populated with `--check-branches`, current-repo rows only):
- `live` — branch exists and isn't merged into the default branch.
- `merged` — branch tip is an ancestor of the default branch (its PR likely landed).
- `gone` — branch exists neither locally nor on the remote (deleted after merge, or abandoned).
- `unknown` — couldn't determine (other repo, branch `?`, offline with no local ref, **or the handoff's branch is the default branch itself**). **Never treated as stale** — absence of evidence isn't evidence of deadness.
- `merged` and `gone` are the two "stale" states. Offline runs degrade safely: a branch with no local ref reports `unknown`, never a false `gone`.
- **Default-branch guard:** a handoff recorded on the trunk (`main`/`master`) reports `unknown`, never `merged`. The trunk tip is trivially an ancestor of itself, so the merge-base check would always fire — but being on the trunk says nothing about whether the handoff's work shipped (it usually means wrap-up captured a worktree sitting on `main` while the real work lived on a feature branch elsewhere). PR detection still applies on top.

PR fields (`pr-state`/`pr-number`/`pr-url`, only populated when `--check-branches` is active and `gh` is available, current-repo rows only):
- `merged` — a PR for this branch was merged. **Ground truth that beats `branch-state`** — local ancestry can't see a squash-merge (the branch is never an ancestor of the default tip), so a squash-merged branch shows `branch-state=live`/`gone` but `pr-state=merged`.
- `open` — a PR is open. This is *active* work — it overrides everything except supersede and is **never** an archive candidate.
- `closed` — a PR was closed without merging (abandoned).
- `none` — `gh` ran but found no PR for this branch.
- `unknown` — `gh` wasn't consulted (no flag, no `gh`, offline, or branch `?`). Falls back to `branch-state`.
- `pr-number`/`pr-url` are the PR number and URL when one was found, else empty.

Archive-class field (last column; current-repo rows only):
- The script's per-row archive recommendation, so the table and §3b read straight off it instead of re-deriving:
  - `safe` — superseded, or `pr-state=merged`, or `branch-state=merged`. Low regret.
  - `keep` — `pr-state=closed`, or `branch-state=gone` with no merged evidence. Higher regret — may be the only record.
  - empty — live work (incl. an open PR) or `unknown`. Not an archive candidate.
- Precedence: supersede > open PR > merged PR > closed PR > local `merged` > `gone`. `current_repo_stale` counts the `keep`/`safe` rows that are **not** superseded (the §3b "stale" group); superseded rows are counted by `current_repo_superseded`.

### 2. Render the current-repo table

If `current_repo_total > 0`:

```markdown
### 🧷 Handoffs — this repo ({count})

| Date | Slug | Branch | Where | Worktree | Status | Archive |
|------|------|--------|-------|----------|--------|---------|
```

- **Slug**: from the filename (e.g. `ab-1107-cta-event`).
- **Branch**: from the parsed line; `?` if unknown.
- **Where**: basename of the recorded cwd. Append ` (current)` if it matches pwd. Special cases: empty cwd → `—`; cwd ending in `/` → use the next-up segment, e.g. `worktrees/` → `(worktrees root)`.
- **Worktree**: ✅ if `exists=Y`; ✂️ (icon only, no word) if `exists=N`. The ✂️ reads as "pruned" and the footnote legend below spells it out; everything in the current-repo table is pickable by definition (handoffs that couldn't be matched to a repo never reach this table), so no separate Pickable column.
  - Emit emoji glyphs **exactly as written here**, including the variation selector on `✂️` and `⚠️` (the wide colored forms, not the narrow text `✂︎`/`⚠︎`). Mixing the two presentations across rows makes column widths jump — keep one form so the cells line up.
- **Status**: pick the first that applies, in this order:
  1. `superseded-by` non-empty → `⏩ superseded` with the newer handoff's slug and reason, e.g. `⏩ by ge-1470-complete (same branch)`. Humanise the reason: `branch` → "same branch", `slug` → "same topic", `collision` → "same-day re-wrap". Derive the newer slug from the `superseded-by` filename (strip the `YYYY-MM-DD-` prefix and `.md`).
  2. `pr-state` = `open` → `🔀 PR #{pr-number} open` (active work — link `pr-url` if rendering allows).
  3. `pr-state` = `merged` → `✅ PR #{pr-number} merged` (definitive — survives squash-merge).
  4. `pr-state` = `closed` → `🚫 PR #{pr-number} closed` (abandoned).
  5. `branch-state` = `merged` → `🔵 merged` (branch landed; no PR data).
  6. `branch-state` = `gone` → `⚪ branch gone`.
  7. otherwise → `🟢 live` (treat `unknown` as live — we have no evidence it's dead).
  Supersede wins because "a newer handoff continues this" is the most actionable signal. PR state beats `branch-state` because it's ground truth (and the only thing that catches a squash-merge); an open PR specifically means *don't archive*.
- **Archive**: render directly from the `archive-class` field — `safe` → `🗄️ safe`, `keep` → `⚠️ keep?`, empty → `—`. This is the at-a-glance candidate flag §3b reads off; `safe` is low-regret (superseded / merged), `keep?` is higher-regret (abandoned / branch gone with no merge evidence).

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
_⚠️ {unresolved} handoff(s) could not be matched to any repo (recorded path is invalid or its parent tree is gone):_
- `~/.claude/handoffs/{filename}`
- `~/.claude/handoffs/{filename}`
```

Pull the filenames straight from the `---HANDOFFS---` section where `repo-key=UNRESOLVED`. Render in the same newest-first order the script emits.

`unresolved > 5`:

```markdown
_⚠️ {unresolved} handoff(s) could not be matched to any repo (recorded path is invalid or its parent tree is gone). Run `grep -L "Repo root:" ~/.claude/handoffs/*.md` to find them._
```

**Do not add a global pruned-count footnote.** The Worktree column in the current-repo table already makes pruning visible per-row. Add a one-time pickability hint immediately under the current-repo table (when `current_repo_pruned > 0`):

```markdown
_✂️ = original worktree was pruned (no longer exists); still pickable — you'll resume in your current checkout or a fresh worktree._
```

This is a tooltip-style explainer keyed to the column legend, not a count. Skip it when `current_repo_pruned == 0`.

### 3b. 🗂️ Archive cleanup candidates (opt-in)

Skip this step if `current_repo_superseded == 0` **and** `current_repo_stale == 0`.

Some current-repo handoffs clutter the picker without pointing at live work. Offer to retire them — archiving **moves** them to `~/.claude/handoffs/archive/` (still on disk, still greppable; just out of the active listing). This is opt-in and never automatic — the rows stay pickable until the user says so.

The candidates split by regret — the `archive-class` field already encodes which is which. Present them as **distinct groups** and be honest about the difference:

- **Superseded** (`archive-class=safe`, `superseded-by` non-empty) — a newer handoff in this repo continues the thread. Low regret: the context lives on in the newer file.
- **Merged** (`archive-class=safe`, not superseded — Status `✅ PR merged` or `🔵 merged`) — the PR landed (or the branch tip is in the default branch). Low regret: the work shipped.
- **Stale** (`archive-class=keep` — Status `🚫 PR closed` or `⚪ branch gone`) — abandoned, and *no newer handoff supersedes it*. Higher regret: this may be the **only** record of that thread. Default to leaving these unless the user is sure.

A row is **never** a candidate while its PR is open (`🔀`) — that's live work. A row that is both superseded and otherwise archivable belongs in the Superseded group (supersede is the safest reason to archive).

Prompt with `AskUserQuestion` (multiSelect). One option per candidate, labelled `{date} {slug}`, described by its group:
- superseded → `⏩ superseded by {newer-slug}`
- merged → `✅ PR #{pr-number} merged` / `🔵 branch merged`
- stale → `🚫 PR #{pr-number} closed — no newer handoff` / `⚪ branch gone — no newer handoff`

> Archive these to `~/.claude/handoffs/archive/`? They stay on disk (greppable), just out of the picker. **Superseded** and **merged** ones are safe — the context lives on or the work shipped. **Stale** ones may be the only record of an abandoned thread, so leave any you might still want.

For the selected filenames, archive them in one call:

```bash
~/.claude/skills/handoffs/scripts/archive.sh {file1} {file2} …
```

Parse the script's `---ARCHIVED---` / `---SKIPPED---` sections and confirm:

```markdown
✅ Archived {N} handoff(s) to `~/.claude/handoffs/archive/`.
```

Surface any `---SKIPPED---` lines verbatim with their reason. After archiving, **drop the archived rows** from the current-repo table for the rest of this run (and subtract them from `current_repo_total`) so §4's picker doesn't offer them. Only offer rows with a non-empty `archive-class` (`safe` or `keep`); never a `🟢 live`, `🔀 PR open`, or `unknown` row. Never delete — `archive.sh` only moves. If the user selects none, render nothing and continue to §4.

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

Then surface a paste-ready rename so the resumed session is legible in the session list. Derive the slug from the filename (strip the `YYYY-MM-DD-` prefix and `.md` suffix):

```markdown
**Rename this session to match:**

```
/rename {slug}
```

(Paste it — `/rename` only fires when you run it.)
```

Skip the rename line only if the current session is already named for this slug.

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

**Second, assess this checkout as a landing spot.** The original worktree is gone, so you'll resume either *here* (the current checkout) or in a *fresh worktree*. Gather the facts in one call:

```bash
git rev-parse --abbrev-ref HEAD && git status --porcelain && git branch --list "{branch}"
```

Read four signals from the output:
- **on-branch** — `HEAD` (line 1) already equals `{branch}`.
- **clean** — `git status --porcelain` printed nothing (no uncommitted work to disrupt by switching branches).
- **branch-exists-locally** — `git branch --list` printed a line for `{branch}`.
- **fresh worktree** — `HEAD` matches `worktree-*`, the auto-generated name `claude -` gives a throwaway worktree. This is the strong signal that the user spun up *this* checkout specifically to host the resume.

Then branch on them:

**on-branch** → already on a viable spot. Render and skip to §6, no prompt:

```markdown
**Already on `{branch}` here** (`{pwd}`). No worktree action needed — resume from this checkout.
```

**clean + fresh worktree** (the `claude -` case) → the user opened this worktree *for* this handoff, so adopting the branch in place is the whole point — don't push a nested worktree. The adopt command depends on `branch-exists-locally`:
- missing → `git checkout -b {branch}` (create it here — the usual case when wrap-up predated the branch or it was deleted).
- exists → `git checkout {branch}`.

Ask via `AskUserQuestion`:

> Original worktree `{cwd}` is gone, but `{pwd}` looks like a fresh worktree (`{HEAD}`) you opened to resume here. Adopt `{branch}` in this checkout?

Options:
- **Adopt here (recommended)** — runs `git checkout -b {branch}` (or `git checkout {branch}` if it already exists). No second worktree.
- **Separate worktree** — fall through to the worktree-creation flow below.
- **Stay as-is** — leave the branch alone; just resume reading from here.

On **Adopt here**, run the adopt command. On success render and skip to §6:

```markdown
✅ Now on `{branch}` in `{pwd}`. Resume from this checkout.
```

If it fails (e.g. the branch is checked out in another live worktree), surface the stderr and offer the **Separate worktree** flow instead.

**otherwise** (dirty tree, or a real branch you'd disrupt by switching) → adopting in place would clobber existing work, so offer a fresh worktree. Fall through to the worktree-creation flow below.

---

Offer to recreate the worktree. Compute the proposed values:

- `{worktree-path}` = the recorded cwd if its parent directory still exists on disk; otherwise `{pwd}/../worktrees/{basename of recorded cwd}`. If the basename is empty or generic (`worktrees`, `.`), use `{topic-slug}` from the filename instead.
- `{branch}` = the branch parsed from the handoff (Branch column).
- The `git worktree add` form depends on `branch-exists-locally` (from the assessment above): an existing branch is *checked out* into the new worktree (`git worktree add {path} {branch}`); a missing branch must be *created* with it (`git worktree add -b {branch} {path}`). Plain `git worktree add {path} {missing-branch}` errors — that's the failure to avoid.

Ask via `AskUserQuestion`:

> Original worktree `{cwd}` is gone. Recreate it?

Options:
- **Create worktree** — runs the `git worktree add` form matching the branch's existence (see above) in the current repo.
- **Resume here** — stay in the current checkout (`{pwd}`); user can adopt the branch themselves (`git checkout -b {branch}` if it doesn't exist yet, else `git checkout {branch}`).
- **Show command** — prints the `git worktree add` invocation without running.

On **Create worktree**, pick the form by `branch-exists-locally`:

```bash
git worktree add "{worktree-path}" "{branch}"        # branch exists locally — check it out
git worktree add -b "{branch}" "{worktree-path}"     # branch missing locally — create it with the worktree
```

If the command succeeds, render:

```markdown
✅ Worktree created at `{worktree-path}`.

**Switch directory:** `cd {worktree-path}`
```

If it fails (path already exists, dirty index, …), surface the stderr and fall back to **Show command** behaviour. Do not retry, do not delete anything, do not `--force`.

On **Resume here**:

```markdown
**Resuming in current checkout** (`{pwd}`). If you need the branch, run `git checkout -b {branch}` (or `git checkout {branch}` if it already exists) — the pruned worktree's commits are still in the repo.
```

On **Show command**, print both forms and say which to run:

```markdown
**Worktree pruned.** Original location `{cwd}` no longer exists. To recreate it yourself:

```bash
git worktree add -b {branch} {worktree-path}   # if {branch} doesn't exist locally yet — create it
git worktree add {worktree-path} {branch}      # if {branch} already exists — check it out
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
- **`gh` missing, unauthenticated, or timed out**: PR detection degrades — every `pr-state` reports `unknown` and the Status/Archive columns fall back to `branch-state`. No error, no retry. The cost: squash-merged branches reappear as `⚪ branch gone` (`keep?`) rather than `✅ merged` (`safe`), so the §3b regret split is coarser but never wrong.

## Notes

- Handoffs are written by `/wrap-up`. If a session ends without `/wrap-up`, there is nothing here to recover. That's intentional — the index lists `/wrap-up` next to `/handoffs` for a reason.
- File naming convention: `~/.claude/handoffs/YYYY-MM-DD-{slug}.md`. Collision suffixes from wrap-up (`-2`, `-3`, …) are preserved as part of the slug.
- Picking a handoff does **not** clean it up. Old handoffs accumulate by design — they're cheap and grep-friendly. The §3b archive step only offers *superseded*, *merged*, or *stale* rows (and only on request); it never touches live or open-PR rows, and sweeps nothing by itself.
- Supersede classification comes from `list.sh`, not the model — same source `/wrap-up` uses for its at-save archive offer, so both skills agree on what supersedes what. Reasons: `branch` > `slug` > `collision`; ticket/cwd overlap is intentionally excluded.
- Liveness (branch-state + PR) is **current-repo-only** and opt-in via `--check-branches` — the queries run in pwd, so other repos always report `unknown`. PR state (from `gh`, auto-enabled when present) is ground truth and overrides the local branch-state heuristic; crucially it's the only signal that catches a **squash-merge**, where the feature branch is never an ancestor of the default tip. Liveness is deliberately separate from supersede: superseded = "a newer handoff continues this" (low-regret); merged-PR = "the work shipped" (low-regret); stale = "the branch is dead/abandoned and nothing supersedes it" (may be the only record — higher regret).
- Repo matching uses `remote.origin.url` first, then realpath of git-common-dir. Linked worktrees of one repo share the same key. Two independent clones with the same origin URL collapse to one row.
- **`.claude` symlink unification** has two flavours:
  - **Non-bare** — A's `.claude` symlinks to B's `.claude` subdir. A defers to B's identity. Display is B's basename.
  - **Bare** — A's `.claude` symlinks to B's repo root itself (B is just a scratch state-holder, not a working project). A keeps its own identity (and display); when B resolves on its own (e.g. via a handoff whose cwd lands inside B), a one-level sibling scan finds A's bare link pointing at B and defers up. Net effect: both ends group under A, the "real" repo. The follow is one-hop in either direction, so reciprocal links don't cycle.
- Pruned-worktree handoffs are pickable: the script walks up the recorded path to find the parent repo, so even after `git worktree remove` the handoff still groups correctly. When picked, the user resumes from their current checkout (or creates a fresh worktree).
