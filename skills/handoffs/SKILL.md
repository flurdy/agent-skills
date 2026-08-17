---
name: handoffs
description: Browse and load current-repo or workspace-member handoffs, including pruned worktrees. Optional confirmed archiving and checkout recovery; loading alone never executes the saved task.
allowed-tools: "Bash(~/.agents/skills/handoffs/scripts/list.sh:*), Bash(~/.agents/skills/handoffs/scripts/archive.sh:*), Bash(git worktree add:*), Bash(git rev-parse:*), Bash(git status:*), Bash(git branch:*), Bash(git checkout:*), Read, AskUserQuestion, mcp__jira__jira_get"
model-tier: standard
model: sonnet
effort: medium
version: "0.22.0"
author: "flurdy"
---

# Handoffs — Pick a saved session to resume

Browse handoff files written by `/wrap-up` (in `~/.claude/handoffs/`) and pick one to resume. Companion to `/wrap-up` (the writer) and `/landscape` (the morning orienter).

## When to use

- Starting a session and wanting to pick up a thread from a previous one.
- After `/landscape` flagged that recent handoffs exist for this repo.
- Searching for an older thread — `ls ~/.claude/handoffs/` is grep-friendly, but this skill renders the metadata table.

> **Not sure whether to resume a handoff or start fresh work?** That's a morning orientation call, not a handoffs call — run `/landscape` first. Its `**Next:**` line arbitrates resume-a-handoff vs `/next safe` from the full picture (Jira, PRs, beads, working copy). Come here once you've decided to resume a thread.

## What it does

1. List handoffs across all repos, with per-repo counts.
2. **Fully detail** handoffs in the current repo as a pickable table, flagging which are superseded by a newer handoff, done (PR merged, all beads closed, or Jira ticket Done), or stale (branch gone / PR closed).
3. **Summarise** handoffs in other repos (count per repo, not full listing).
4. Optionally archive confirmed superseded, done, stale, or assisted-review handoffs to keep the picker focused, including safe and old signal-less workspace-member rows through separate confirmation flows.
5. Prompt you to pick one — only handoffs for the current repo and workspace members are pickable.
6. On pick, render the resume block inline and surface the `cd` if the recorded worktree differs from pwd.

## Important — what this skill cannot do

- It **cannot resume** for you. It surfaces the resume block; you read it and act on the next step.
- It **cannot rename the session** for you. On load it prints the active client's paste-ready command (§5): `/name {slug}` in Pi and `/rename {slug}` in Claude Code. Only you typing it triggers a rename.
- It **cannot pick handoffs from unrelated repos**. That is a deliberate guard — running commands against the wrong repo is the failure mode it prevents. To resume a handoff in an unrelated repo, `cd` there and run `/handoffs` again. **Exception:** repos in the same multi-repo workspace are listed and pickable (§2b/§4b), because from a workspace root they'd otherwise be invisible; picking one requires an explicit `cd` before any repo-scoped command runs.
- It **never deletes** handoff files. The opt-in archive steps (§3b–§3f) only *move* explicitly confirmed candidates into `~/.claude/handoffs/archive/` — they stay on disk and greppable.

## Instructions

> **MUST use the helper script.** Never construct ad-hoc `ls`/`grep` pipelines against `~/.claude/handoffs/` — they bypass the per-script permission allowlist and miss the repo-matching logic.

### 1. Run the helper

```bash
~/.agents/skills/handoffs/scripts/list.sh --check-branches [--stale-days N]
```

Forward `--stale-days N` when the user supplied it; otherwise let the script match the age-review
floor to its recent window (3 days, or 4 on Tuesday). Shorter values are clamped to that window. The
flag only controls the assisted §3d and §3f groups and never marks a row stale.

`--check-branches` adds branch-liveness + PR classification for current-repo and workspace-member handoffs. The full flag
semantics, the 22-field `---HANDOFFS---` line format, and every field's meaning (supersede,
branch-state, pr-state, archive-class, beads-done, deliverable-field, beads-progress, needs-review,
needs-age-review)
are specified once in
**`~/.agents/skills/handoffs/REFERENCE.md`** — `Read` it. Both `/handoffs` and `/handoffs-tidy` read
off the same definitions, including §Age-review, so the two never drift on classification.

The sections you parse here: `---CURRENT-REPO---` / `---CURRENT-REPO-DISPLAY---` /
`---CURRENT-REPO-KIND---` (identity + label + `repo`/`dir`/`NONE` — outside a git repo the directory
itself is the identity, so handoffs written from it still match), `---HANDOFFS---` (one row per handoff, newest first), `---SUMMARY---`
(the counts, incl. `current_repo_total`, `current_repo_superseded`, `current_repo_stale`,
`current_repo_age_review`, `workspace_member_age_review`, `unresolved`), and `---OTHER-REPOS---` (`{repo-key}|{count}|{display}`, count desc). The
`---CURRENT-REPO-LATEST---` / `---CURRENT-REPO-LIVE---` sections are for `/landscape`; this skill
renders the full table instead and can ignore them.

> See REFERENCE §Fields for repo-identity resolution (`Repo root:` → cwd walk-up, origin-URL keying,
> `.claude`-symlink unification, `UNRESOLVED`), the supersede rules, and the branch-state / pr-state /
> archive-class semantics this skill renders below.

### 1a. Resolve Jira-Done for still-live rows (skill layer)

`list.sh` can read PR and bead state but **cannot call the Jira MCP** — so a handoff whose only
"finished" signal is its ticket being closed in Jira still arrives with `archive-class` empty
(`🟢 live`). Close that gap here, model-side, per **REFERENCE §Jira-Done**: same gate (only under
`--check-branches`, only for rows without another done/stale/supersede signal that name a ticket),
same batched JQL query, and the same recent-retention rule. Skip silently if the Jira MCP errors or
isn't configured.

### 2. Render the current-repo table

If `current_repo_total > 0`:

```markdown
### 🧷 Handoffs — this repo ({count})

| Date | Slug | Branch | Where | Worktree | Status | Archive |
|------|------|--------|-------|----------|--------|---------|
```

- **Date**: render `{date} {time}` (e.g. `2026-06-03 14:32`) so same-day handoffs are distinguishable at a glance. Drop the time and show just `{date}` when `{time}` is `?` (neither header time nor mtime was available).
- **Slug**: from the filename (e.g. `ab-1107-cta-event`).
- **Branch**: from the parsed line; `?` if unknown.
- **Where**: basename of the recorded cwd. Append ` (current)` if it matches pwd. Special cases: empty cwd → `—`; cwd ending in `/` → use the next-up segment, e.g. `worktrees/` → `(worktrees root)`.
- **Worktree**: ✅ if `exists=Y`; ✂️ (icon only, no word) if `exists=N`. The ✂️ reads as "pruned" and the footnote legend below spells it out; everything in the current-repo table is pickable by definition (handoffs that couldn't be matched to a repo never reach this table), so no separate Pickable column.
  - Emit emoji glyphs **exactly as written here**, including the variation selector on `✂️` and `⚠️` (the wide colored forms, not the narrow text `✂︎`/`⚠︎`). Mixing the two presentations across rows makes column widths jump — keep one form so the cells line up.
- **Status**: classify the row per **REFERENCE §Status** (the 9-step precedence: supersede → open PR → merged PR → beads-done → Jira-Done → closed PR → merged → gone → live). Emit the glyphs exactly as written there.
- **Archive**: render the candidate flag per **REFERENCE §Archive-glyph** — `safe` → `🗄️ safe`, `keep` → `⚠️ keep?`, empty → `—`. Recent non-superseded rows stay `—` even when Status says merged/done/stale; a §1a Jira-Done promotion counts as `safe` only outside the recent window.

If `current_repo_total == 0` and `CURRENT-REPO != NONE`:
`_No handoffs for this repo ({CURRENT-REPO-DISPLAY})._`

If `CURRENT-REPO-KIND == dir`, add one line under the table (or in place of it when
`current_repo_total == 0`):
`_Not in a git repo — matched by directory (`{CURRENT-REPO-DISPLAY}`); branch/PR liveness and archive candidates are unavailable here._`
Rows then carry `branch-state=unknown` — render them `🟢 live` (or superseded) per REFERENCE §Status; never call them stale.

If `CURRENT-REPO == NONE`:
`_Current directory could not be identified — handoffs cannot be matched. Showing global counts only._`

**Render this section exactly once, in this position.** Do not repeat the "No handoffs for this repo" sentence later (e.g. after §3's other-repos table) — once is enough. If `current_repo_total == 0` but other repos exist, the next section's table provides the rest of the context.

### 2b. 🧱 Render the workspace-members table

Skip this section entirely when `workspace_member_handoffs == 0`.

In a multi-repo workspace the root aggregates independent member repos, so handoffs recorded in a
member key to the member — not the root. Without this section they'd sit in §3's other-repos summary
as a bare count, unpickable from the directory you orient in. See **REFERENCE §Workspace-members**.

Render from `---WORKSPACE-MEMBER-HANDOFFS---` (24 fields: the usual 22 plus
`{member-display}|{member-path}`):

```markdown
### 🧱 Handoffs — workspace members ({workspace_member_handoffs})

| Date | Repo | Slug | Branch | Worktree | Status | Archive |
|------|------|------|--------|----------|--------|---------|
```

- Same column semantics as §2, plus **Repo** = `{member-display}`.
- **Status** and **Archive**: classify exactly as §2 (REFERENCE §Status / §Archive-glyph). Member
  rows are classified against their own repo, so `✅ PR merged` / `⚪ branch gone` are meaningful here.
- Sort newest-first (the emitted order); group visually by repo only if it aids scanning.
- Cap at 10 rows. When more exist, render the 10 newest and add
  `_+{N − 10} more — `cd` into the member repo and run `/handoffs` for its full list._`
- When `workspace_classified == 0` (ran without `--check-branches`), add:
  `_Status unclassified — member liveness needs `--check-branches`._`

Then subtract these repos from §3's other-repos table so the same handoffs aren't counted twice —
a member repo listed here must not also appear as an "other repo".

Member rows are listed and pickable here. Archive their `safe` rows through the separate §3e
per-member confirmation flow (REFERENCE §Archive-flow-members), and offer old signal-less rows
unchecked through §3f (REFERENCE §Age-review-members); `keep` rows still need inspection from the
member repo. When members hold archivable or reviewable rows, say so once under this table:
`_{N} member handoff(s) look finished or old enough to review — separate confirmation follows._`

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
_⚠️ {unresolved} handoff(s) could not be matched to any repo or directory (recorded path is invalid or gone):_
- `~/.claude/handoffs/{filename}`
- `~/.claude/handoffs/{filename}`
```

Pull the filenames straight from the `---HANDOFFS---` section where `repo-key=UNRESOLVED`. Render in the same newest-first order the script emits.

`unresolved > 5`:

```markdown
_⚠️ {unresolved} handoff(s) could not be matched to any repo or directory (recorded path is invalid or gone). Run `grep -L "Repo root:" ~/.claude/handoffs/*.md` to find them._
```

**Do not add a global pruned-count footnote.** The Worktree column in the current-repo table already makes pruning visible per-row. Add a one-time pickability hint immediately under the current-repo table (when `current_repo_pruned > 0`):

```markdown
_✂️ = original worktree was pruned (no longer exists); still pickable — you'll resume in your current checkout or a fresh worktree._
```

This is a tooltip-style explainer keyed to the column legend, not a count. Skip it when `current_repo_pruned == 0`.

### 3b. 🗂️ Archive cleanup candidates (opt-in)

Run the archive flow exactly as **REFERENCE §Archive-flow** specifies: skip only if
`current_repo_superseded == 0`, `current_repo_stale == 0`, **and** §1a produced no older Jira-Done
promotions; otherwise present the effective candidates in
the three regret-ordered groups (Superseded / Done / Stale), prompt with `AskUserQuestion`
(multiSelect, labelled and described per that section), archive the selected filenames in one
`archive.sh` call, and parse `---ARCHIVED---` / `---SKIPPED---`. Never offer a `🟢 live`, `🟠 PR open`,
or `unknown` row; `archive.sh` only moves, never deletes.

When the flow says to drop archived rows from "any subsequent listing or picker", that is **this
skill's current-repo table and §4 picker** — remove the archived rows and subtract them from
`current_repo_total` so §4 doesn't offer them. If the user selects none, render nothing and continue to §4.

(`/handoffs-tidy` is the standalone twin of this step: same flow, no table or picker around it.)

### 3c. 🔍 Trunk handoffs worth a look (opt-in)

If any current-repo row has `needs-review=Y`, run the assisted prompt per **REFERENCE §Trunk-review**
*after* §3b — a separate, clearly-labelled prompt for legacy trunk-parked handoffs the script
couldn't auto-classify (partial bead closure, no `**Deliverable:**` marker). Drop any the user
archives from the table and §4 picker, same as §3b. Skip the step entirely when no row is flagged.

### 3d. 🕰️ Old handoffs with no completion signal (opt-in)

If any current-repo row still has `needs-age-review=Y` after §1a Jira-Done promotion, run the
assisted prompt exactly as **REFERENCE §Age-review** specifies. This is a separate, clearly-labelled
judgement group for old rows with unknown branch liveness and no usable PR signal or resolvable beads. Age is not a
done signal: leave every option unselected, archive only explicit choices, and never fold these rows
into §3b's automatic candidate classes. Drop confirmed archives from the table and picker as in §3b.
Skip entirely when no row is flagged.

### 3e. 🧱 Workspace-member archive candidates (opt-in)

After the current-repo flows, run **REFERENCE §Archive-flow-members**. It is a separate explicit
confirmation per member repo: offer only `safe` rows, never sweep `keep` rows, and archive every
confirmed selection in one `archive.sh` call. Drop archived member rows from the table and picker.

### 3f. 🕰️ Old workspace-member handoffs worth a look (opt-in)

After the evidence-backed member flow, run **REFERENCE §Age-review-members** when
`workspace_member_age_review > 0`. Offer each old signal-less member row unchecked, grouped by member
repo, and archive only explicit selections. These rows retain an empty `archive-class` and must never
be included in §3e's bulk-safe choice. Drop archived member rows from the table and picker.

### 4. Pick a handoff (current repo and displayed workspace members)

Count the remaining displayed current-repo and workspace-member rows after confirmed archives.
With zero rows, skip only this picker. With one row, ask in plain text to load its filename or skip;
do not construct a one-option questionnaire. With 2–4 rows, use `AskUserQuestion`:

- Option label: `{date} {slug}` (truncate slug if needed to stay under the chip width).
- Option description: `{time} · Branch: {branch} | Where: {basename of cwd}` (lead with the `HH:MM` so several same-day handoffs are distinguishable here; omit the `{time} · ` prefix when `{time}` is `?`).

With more than four remaining displayed rows, do **not** force the picker. Instead, print:

```markdown
**Pick one to load:** reply with the slug or filename (e.g. `ab-1344-login-state-decision` or `2026-05-21-ab-1344-login-state-decision.md`).
```

Every remaining displayed row in §2/§2b is pickable; Worktree ✅/✂️ describes path existence only.
Pruned-worktree handoffs are pickable — they just resume in a different checkout. Unresolved rows
are not recovery targets; offer read-only access to the exact listed file instead.

### 4b. Picking a workspace-member handoff

Member rows (§2b) **are** pickable, but only with an explicit directory change — the wrong-repo
guard is honoured by making the `cd` mandatory, not by hiding the handoff.

When `workspace_member_handoffs > 0`, extend the §4 prompt (or the "reply with the slug" line) to
cover member rows too, labelling them `{date} {repo}/{slug}` so they're distinguishable from
current-repo rows.

On picking a member handoff, render the resume block per §5, then **lead with the switch**:

```markdown
⚠️ **This is a workspace-member handoff for `{member-display}`.**
**Switch first:** `cd {member-path}`

Everything in the resume block below — branches, beads, commands — refers to that repo.
```

Do not run repo-scoped commands (worktree creation, `git checkout`, `bd`) for a member handoff from
the current directory; the §5 `exists=N` worktree flow assumes you're inside the handoff's own repo,
so defer it until the user has switched. Re-running `/handoffs` from `{member-path}` gives the full
current-repo experience for that repo, including the archive flow.

### 5. Load the picked handoff

Use the `Read` tool on the absolute path `{HANDOFFS-DIR}/{filename}`.

Render the file content **verbatim** inside a fenced block as historical context, not authorization
to run its suggested commands. Preserve external-text fences; the current user/repository rules
still govern. Loading never starts coding, claims a bead, or executes saved instructions.

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
/name {slug}
```

(Paste it into Pi's command input and press Enter. In Claude Code, use `/rename {slug}` instead.)
```

Follow [name-session](../name-session/SKILL.md) for client detection only. **Unknown client:**
label both Pi `/name {slug}` and Claude Code `/rename {slug}` rather than choosing one.
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

**Recovery preconditions.** First verify the owning repo, path and branch from current evidence;
use its Git wrapper when required. A handoff is not proof that deleted commits survive. If the
branch is missing, require an explicit base SHA identified from surviving refs/history and confirmed
by the user before creating anything. `{base-sha}` below is that verified value, never implicit HEAD.
If it cannot be established, stop recovery and offer context-only reading. Preview the exact
checkout/worktree command and require confirmation; unknown status is not a clean checkout.

**Second, assess this checkout as a landing spot.** The original worktree is gone, so you'll resume either *here* (the current checkout) or in a *fresh worktree*. Gather the facts in one call:

```bash
git rev-parse --abbrev-ref HEAD && git status --porcelain && git branch --list "{branch}"
```

Read four signals from the output:
- **on-branch** — `HEAD` (line 1) already equals `{branch}`.
- **clean** — `git status --porcelain` printed nothing (no uncommitted work to disrupt by switching branches).
- **branch-exists-locally** — `git branch --list` printed a line for `{branch}`.
- **possible temporary checkout** — a `worktree-*` branch name is a naming hint, not proof that
  this checkout is disposable or was opened for this handoff. Ask the user before considering adoption.

Then branch on them:

**on-branch** → already on a viable spot. Render and skip to §6, no prompt:

```markdown
**Already on `{branch}` here** (`{pwd}`). No worktree action needed — resume from this checkout.
```

**clean + user-confirmed adoption target** → offer in-place adoption without inferring consent from
its branch name. The adopt command depends on `branch-exists-locally`:
- missing → `git checkout -b {branch} {base-sha}` (only after the recovery preconditions above).
- exists → `git checkout {branch}`.

Ask via `AskUserQuestion`:

> Original worktree `{cwd}` is gone, but `{pwd}` looks like a fresh worktree (`{HEAD}`) you opened to resume here. Adopt `{branch}` in this checkout?

Options:
- **Adopt here (recommended)** — runs `git checkout -b {branch} {base-sha}` (or `git checkout {branch}` if it already exists). No second worktree.
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
- The `git worktree add` form depends on `branch-exists-locally` (from the assessment above): an existing branch is *checked out* into the new worktree (`git worktree add {path} {branch}`); a missing branch must be created from the verified explicit base (`git worktree add -b {branch} {path} {base-sha}`). Plain `git worktree add {path} {missing-branch}` errors — that's the failure to avoid.

Ask via `AskUserQuestion`:

> Original worktree `{cwd}` is gone. Recreate it?

Options:
- **Create worktree** — runs the `git worktree add` form matching the branch's existence (see above) in the current repo.
- **Resume here** — stay in the current checkout (`{pwd}`) for context only; no branch mutation.
- **Show command** — prints the `git worktree add` invocation without running.

On **Create worktree**, pick the form by `branch-exists-locally`:

```bash
git worktree add "{worktree-path}" "{branch}"        # branch exists locally — check it out
git worktree add -b "{branch}" "{worktree-path}" "{base-sha}" # missing branch — verified explicit base
```

If the command succeeds, render:

```markdown
✅ Worktree created at `{worktree-path}`.

**Switch directory:** `cd {worktree-path}`
```

If it fails (path already exists, dirty index, …), surface the stderr and fall back to **Show command** behaviour. Do not retry, do not delete anything, do not `--force`.

On **Resume here**:

```markdown
**Reading context in current checkout** (`{pwd}`). No branch was changed; recovery of the original
work requires surviving ref/base evidence, not just recreation of its old name.
```

On **Show command**, print both forms and say which to run:

```markdown
**Worktree pruned.** Original location `{cwd}` no longer exists. To recreate it yourself:

```bash
git worktree add -b {branch} {worktree-path} {base-sha} # missing branch; verified explicit base
git worktree add {worktree-path} {branch}      # if {branch} already exists — check it out
```
```

### 6. Footer

```markdown
---
**Next:** confirm the saved task is still current before acting on its suggested step; use `/landscape resume` for fresh orientation.
```

## Failure modes

Each step is independent — a failure in one should not block the others.

- **`~/.claude/handoffs/` missing**: render `_No handoffs directory yet. Run /wrap-up at the end of a session to create one._` and stop.
- **Empty directory**: render `_No handoffs saved yet._` and stop.
- **Not in a git repo**: retain directory-matched rows when `CURRENT-REPO-KIND == dir`; they remain
  loadable. Skip Git recovery, not the picker. Only `CURRENT-REPO == NONE` prevents matching.
- **Picked handoff is unreadable**: report the path and suggest `cat` — don't fabricate content.
- **Offline / remote unreachable** (`git ls-remote` fails or times out): branch-state degrades to local-only — `merged` is still detected against the local default tip, but branches with no local ref report `unknown` rather than a false `gone`. The skill keeps working; the stale group in §3b just shrinks. Don't retry the network call.
- **`gh` missing, unauthenticated, or timed out**: PR detection degrades — every `pr-state` reports `unknown` and the Status/Archive columns fall back to `branch-state`, plus `beads-done` (which is local and unaffected). No error, no retry. The cost: squash-merged branches reappear as `⚪ branch gone` (`keep?`) rather than `✅ merged` (`safe`), unless a closed bead or §1a Jira-Done still marks them done.
- **`bd` missing or no `.beads/`**: `beads-done` is always empty — no error. Finished work then relies on PR/branch/supersede (and §1a Jira) signals alone.
- **Jira MCP missing or errors**: §1a is skipped silently; PR/bead/supersede classification stands. A handoff whose *only* finished signal was a closed ticket will show `🟢 live` — acceptable degradation, never a failure.

## Notes

- Handoffs are written by `/wrap-up`. If a session ends without `/wrap-up`, there is nothing here to recover. That's intentional — the index lists `/wrap-up` next to `/handoffs` for a reason.
- File naming convention: `~/.claude/handoffs/YYYY-MM-DD-{slug}.md`. Collision suffixes from wrap-up (`-2`, `-3`, …) are preserved as part of the slug.
- Picking a handoff does **not** clean it up. Old handoffs accumulate by design — they're cheap and grep-friendly. The §3b archive step only offers *superseded*, *done*, or *stale* current-repo rows after the recent grace window (superseded rows are the sole immediate exception); §3d separately offers older signal-less current-repo rows for explicit judgement, §3e offers eligible `safe` workspace-member rows, and §3f offers old signal-less member rows unchecked. No flow touches live/open-PR work automatically or sweeps anything by itself.
- **"Done" detection** has three independent sources, each ground truth in its own domain: a **merged PR** (matched by branch *or* by a number recorded in the body — the latter rescues trunk-parked handoffs that recorded `main`), **all referenced beads closed** (local `bd`, works even on trunk repos with no PR), and a **Jira ticket in the Done category** (§1a, skill-resolved). Any one is enough; together they cover the cases — trunk-based completion, post-merge wrap-ups on `main`, ticket-only closure — that the old branch/PR-only check reported as `🟢 live`.
- Supersede classification comes from `list.sh`, shared with `/handoffs-tidy`; wrap-up does not
  perform an at-save archive sweep. Reasons: `branch` > `slug` > `collision`; ticket/cwd overlap is excluded.
- Liveness (branch-state + PR) is opt-in via `--check-branches` and runs in the current repo plus each discovered workspace member; unrelated repos remain `unknown`. PR state (from `gh`, auto-enabled when present) is ground truth and overrides the local branch-state heuristic; crucially it's the only signal that catches a **squash-merge**, where the feature branch is never an ancestor of the default tip. Liveness is deliberately separate from supersede: superseded = "a newer handoff continues this" (low-regret); merged-PR = "the work shipped" (low-regret); stale = "the branch is dead/abandoned and nothing supersedes it" (may be the only record — higher regret).
- Repo matching uses `remote.origin.url` first, then realpath of git-common-dir. Linked worktrees of one repo share the same key. Two independent clones with the same origin URL collapse to one row.
- **`.claude` symlink unification** has two flavours:
  - **Non-bare** — A's `.claude` symlinks to B's `.claude` subdir. A defers to B's identity. Display is B's basename.
  - **Bare** — A's `.claude` symlinks to B's repo root itself (B is just a scratch state-holder, not a working project). A keeps its own identity (and display); when B resolves on its own (e.g. via a handoff whose cwd lands inside B), a one-level sibling scan finds A's bare link pointing at B and defers up. Net effect: both ends group under A, the "real" repo. The follow is one-hop in either direction, so reciprocal links don't cycle.
- Pruned-worktree handoffs are pickable: the script walks up the recorded path to find the parent repo, so even after `git worktree remove` the handoff still groups correctly. When picked, the user resumes from their current checkout (or creates a fresh worktree).
- **`list.sh --bead <id>` / `--ticket <key>`** (consumed by `/next` and `/start-ticket`, not by this skill) emit an extra `---MATCHED-HANDOFFS---` section: current-repo, active handoffs whose `**Beads:**` / `**Jira:**` header field contains that exact token. It reuses the same supersede + bead-closure + (with `--check-branches`) PR liveness machinery, so a bead/ticket resume surfaces only the *live tip*, never a superseded or shipped handoff — even when recent retention keeps that shipped row in the picker. Matching is exact-token and case-insensitive (`bd-12` never matches `bd-123`). The flags leave every other section byte-identical, so this skill, `/wrap-up`, and `/landscape` are unaffected.
