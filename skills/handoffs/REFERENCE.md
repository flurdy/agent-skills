# Handoffs — shared classification & archive spec

Normative reference for **`/handoffs`** (the picker) and **`/handoffs-tidy`** (the pruner). Both
skills run `list.sh` and `Read` this file; it is the single source of truth for **how to read the
script's output, classify each handoff, and run the archive flow**. The *signals* themselves come
from `list.sh` (the `archive-class` field already encodes the safe/keep verdict after recent-retention) — this file is the
single source for how to render and act on them, so the two skills can never drift on classification.

Cite sections by anchor: §Run, §Fields, §Jira-Done, §Status, §Archive-glyph, §Archive-flow, §Trunk-review, §Age-review.

---

## §Run — invoking `list.sh`

```bash
~/.agents/skills/handoffs/scripts/list.sh --check-branches [--stale-days N]
```

`--stale-days` sets the positive-integer age floor for §Age-review. By default it matches the recent
window (3 days, or 4 on Tuesday), so signal-less rows become reviewable only after the same grace
period that protects completed rows. An explicit value can extend that floor; shorter values are
clamped to the recent window so assisted review cannot bypass retention. It never changes
`archive-class`.

`--check-branches` adds branch-liveness classification (the `branch-state` field) for current-repo
and discovered workspace-member handoffs. It runs one `git ls-remote` (network, timeout-guarded) plus
local merge-base checks in each classified repo. Unrelated-repo rows remain `unknown`.

**PR detection auto-enables** (no separate flag) whenever `--check-branches` is active **and** `gh`
is on `PATH`. It adds one batched, timeout-guarded `gh pr list` (mapped to branches locally) and
fills the `pr-state`/`pr-number`/`pr-url` fields. If `gh` is missing, unauthenticated, or times out,
every row reports `pr-state=unknown` and the local branch-state heuristic stands.

Both finished-work signals that don't need the network — **bead-closure** (`beads-done`, local `bd`)
and **supersede** — are computed on every call regardless of `--check-branches`.

---

## §Fields — reading the output

Delimited sections:

- `---CURRENT-REPO---` — current repo identity (origin URL preferred, falling back to realpath of git-common-dir), or `NONE` if not in a repo.
- `---CURRENT-REPO-DISPLAY---` — short label for the current repo (basename of the repo root), or `NONE`.
- `---RECENT-WINDOW-DAYS---` — days used for the "recent" filter (3 default; Mon → 3, Tue → 4 weekend buffer).
- `---STALE-DAYS---` — configured age floor for assisted age review (the recent-window size by default).
- `---HANDOFFS-DIR---` — directory scanned (`~/.claude/handoffs`).
- `---HANDOFFS---` — one pipe-delimited line per handoff, newest first (see line format below).
- `---CURRENT-REPO-LATEST---` — a single `{slug}|{branch}|{date}` line for the newest current-repo handoff, or empty. (Consumed by `/landscape`; the picker and tidy render the full table instead and can ignore it.)
- `---CURRENT-REPO-LIVE---` — one `{slug}|{branch}|{date}|{time}` line per recent active current-repo handoff; completed, stale, and superseded rows are excluded. (Consumed by `/landscape`; ignore here.)
- `---SUMMARY---` — `total=N`, `current_repo_total=N`, `current_repo_recent=N`, `current_repo_recent_live=N`, `current_repo_pruned=N`, `current_repo_superseded=N`, `current_repo_stale=N`, `current_repo_age_review=N`, `other_repos=N`, `pruned_total=N`, `superseded_total=N`, `unresolved=N`, `workspace_members=N`, `workspace_member_handoffs=N`, `workspace_member_stale=N`, `workspace_classified=N`.
- `---OTHER-REPOS---` — one line per distinct non-current repo: `{repo-key}|{count}|{display}`, sorted by count desc. **Workspace members are still counted here** — the section is deliberately unfiltered so existing parsers see no change; a caller rendering the workspace sections below should subtract them (see §Workspace-members).
- `---WORKSPACE-MEMBER-REPOS---` — one line per member repo of the multi-repo workspace the cwd belongs to: `{repo-key}|{display}|{path}|{handoff-count}`, in `.mgit.conf` order. Empty when the cwd isn't in a workspace. The current repo is excluded.
- `---WORKSPACE-MEMBER-HANDOFFS---` — one line per handoff owned by a member, newest first. The **same 22 fields** as `---HANDOFFS---` plus `{member-display}|{member-path}` appended (24 total), so an existing parser can be reused unchanged. Suppressed by `--summary-only`.

Field values never contain the `|` delimiter or a newline: `list.sh` replaces both
with a space when it builds a record. Handoff text is author-controlled, and these
records are read by position, so an unescaped delimiter would shift every later
field and change what a row appears to say. Parsers can rely on the field count.

**`---HANDOFFS---` line — 22 pipe-delimited fields, in order:**

```
{filename}|{date}|{slug}|{cwd}|{branch}|{repo-key}|{exists}|{superseded-by}|{supersede-reason}|{branch-state}|{pr-state}|{pr-number}|{pr-url}|{archive-class}|{time}|{beads-field}|{jira-field}|{beads-done}|{deliverable-field}|{beads-progress}|{needs-review}|{needs-age-review}
```

`{time}` (field 15) is the `HH:MM` the handoff was written — from the `# Resume:` header
(wrap-up v0.8.0+), falling back to the file's mtime; `?` only when neither is available. Fields after
`{time}` were **appended** so older positional parsers keep working.

### Repo identity (`repo-key`, `exists`)

- Resolution order per handoff: (1) the **`Repo root:`** line (wrap-up v0.2.0+), then (2) walking up the `Where to pick up:` cwd to find a parent repo.
- Identity prefers `remote.origin.url` so independent clones of the same upstream collapse to one row; falls back to realpath of git-common-dir for local-only repos.
- `.claude`-symlink unification: if a repo root's `.claude` is a symlink whose target lives inside another git repo, that other repo's identity wins (one hop, no cycles).
- Pruned worktrees still resolve — the walk-up climbs out of the deleted directory to a still-existing parent.
- `repo-key` is `UNRESOLVED` only when neither the `Repo root:` field nor the cwd walk-up finds a repo.
- `exists=Y` means the recorded cwd still exists on disk; `exists=N` means it was pruned (still pickable — resume in your current checkout or a fresh worktree).

### Supersede (`superseded-by`, `supersede-reason`)

- `superseded-by` is the filename of the **newest** handoff in the same repo that continues this thread, or empty if this is the live tip. `supersede-reason` is `branch` (same branch), `slug` (same exact topic slug), or `collision` (same-day re-wrap). Ticket/cwd overlap is deliberately *not* a supersede signal — a ticket legitimately spans many handoffs.
- Recency is date first, then the `# Resume:` time when both records have one. Equal or unknown same-day times are conservatively unordered, except an established filename collision family (`topic` → `topic-2` → `topic-3`): higher collision suffixes are newer. A trailing numeric topic component such as `GE-1869` is never a global recency signal unless an unsuffixed `GE` handoff establishes that exact collision family.
- **Trunk co-residence never supersedes.** The `branch` reason excludes the default branch (`main`/`master`): two distinct threads both recorded on the trunk (the wrap-up trunk-parking case) are *not* the same thread — they only supersede on an exact slug or same-day collision.

### Branch-state (`branch-state`) — only populated with `--check-branches`, current-repo **and workspace-member** rows

- `live` — branch exists and isn't merged into the default branch.
- `merged` — branch tip is an ancestor of the default branch (its PR likely landed).
- `gone` — branch exists neither locally nor on the remote (deleted after merge, or abandoned).
- `unknown` — couldn't determine (other repo, branch `?`, offline with no local ref, **or the handoff's branch is the default branch itself**). **Never treated as stale.**
- `merged` and `gone` are the two "stale" states. Offline runs degrade safely: a branch with no local ref reports `unknown`, never a false `gone`.
- **Default-branch guard:** a handoff recorded on the trunk reports `unknown`, never `merged` — being on the trunk says nothing about whether the work shipped. PR detection still applies on top.

### PR fields (`pr-state`/`pr-number`/`pr-url`) — only with `--check-branches` + `gh`, current-repo **and workspace-member** rows

A PR matches a handoff either by branch (headRefName) **or by a number recorded in the handoff's
`**PRs:**` field** — the number fallback rescues the **trunk-parking** case (wrap-up recorded `main`
because the feature branch was already gone after merge; a branch-only lookup matches nothing and the
row wrongly shows `🟢 live`, but the merged PR's number is still in the body).

- `merged` — a PR for this branch (or recorded number) was merged. **Ground truth that beats `branch-state`** — local ancestry can't see a squash-merge (the branch is never an ancestor of the default tip).
- `open` — a PR is open. *Active* work — overrides everything except supersede; **never** an archive candidate.
- `closed` — a PR was closed without merging (abandoned).
- `none` — `gh` ran but found no PR for this branch.
- `unknown` — `gh` wasn't consulted (no flag, no `gh`, offline, or branch `?`). Falls back to `branch-state`.

### Beads / Jira (`beads-field`, `jira-field`, `beads-done`, `deliverable-field`, `beads-progress`, `needs-review`, `needs-age-review`)

- `{beads-field}` — raw `**Beads:**` token list (own-work **and** context/epic beads); empty unless beads exist locally or a `--bead`/`--ticket` filter is active.
- `{jira-field}` — raw `**Jira:**` token list; populated under `--check-branches` (and filters). Bash can't call the Jira MCP, so the script never sets a jira-done flag — it only hands you the keys (see §Jira-Done).
- `{deliverable-field}` — raw `**Deliverable:**` token list: just the **own-work** beads this handoff was advancing (wrap-up v0.10.0+), the subset whose closure means the handoff is finished. Empty for older handoffs that predate the field.
- `{beads-done}` — `Y` when **every** bead in the **closure-check set** is closed (all resolve to `status=closed`), else empty. The closure-check set is the **`**Deliverable:**` field when present**, else the full `**Beads:**` field (legacy fallback). Computed locally via `bd` for current-repo rows whenever beads exist — **independent of `--check-branches`**. A field truncated with `(+N more)` can't be fully verified and stays empty (conservative).
  - **Why Deliverable matters:** in trunk repos all work commits to `master`, so wrap-up records every handoff with `branch: master` → `branch-state=unknown` (the default-branch guard) and no PR. The bead is then the only "done" signal — but the `**Beads:**` list mixes own work with recurring "in-progress elsewhere" context beads and parent epics that never close, so an all-`**Beads:**`-closed rule can never fire. Keying off `**Deliverable:**` (own work only) fixes that. Safety: over-including a bead in Deliverable only ever *under*-detects (a never-closing bead keeps the row live); **omitting** an own-work bead is the only way to false-positive, so wrap-up errs toward including.
- `{beads-progress}` — `{closed}/{total}` over the closure-check set (Deliverable if present, else Beads), or empty when there are no resolvable beads. Lets a caller distinguish *partial* closure (something shipped, something open) from all-open (nothing done) and all-closed (done).
- `{needs-review}` — `Y` for a current-repo row outside the recent window that **can't be auto-classified** and warrants the assisted prompt (see §Trunk-review): it renders `🟢 live` (`archive-class` empty), is **trunk-parked** (branch is `main`/`master`/the default), has **no `**Deliverable:**` field** (a legacy handoff), and shows **partial** bead closure (`beads-progress` with closed ≥ 1). Rows with a Deliverable field never set this — they classify cleanly. All-closed rows are already `safe`; all-open rows are genuinely live.
- `{needs-age-review}` — `Y` for an old current-repo row that has no usable completion or liveness signal and warrants §Age-review: `--check-branches` was used, the row is older than `---STALE-DAYS---`, `branch-state=unknown`, it has no usable PR signal (`pr-state=none`, or `unknown` with no recorded PR number), and it has no resolvable beads (`beads-progress` empty). Age is not evidence of doneness, so this flag never changes `archive-class` or stale counts. Rows with an open/merged/closed PR, a known-live branch, or an unknown lookup plus a recorded PR number are not flagged.

### Archive-class (`archive-class`) — current-repo and workspace-member rows

The script's per-row archive recommendation, so callers read straight off it instead of re-deriving:

- `safe` — superseded, or an **older-than-recent** row with `pr-state=merged`, `beads-done=Y`, or `branch-state=merged`. Low regret — the context lives on, or the work demonstrably shipped.
- `keep` — an **older-than-recent** row with `pr-state=closed`, or `branch-state=gone` with no merged/done evidence. Higher regret — may be the only record.
- empty — live/unknown work, or a recent non-superseded row retained by the grace window. **Not an archive candidate.** Status still comes from §Status, so a retained row can truthfully show `✅ merged` while its Archive column stays `—`.

Precedence before retention: supersede > open PR > merged PR > **beads-done** > closed PR > local `merged` > `gone`.
Supersede remains immediately `safe`; every other non-empty result is cleared while `{date}` is inside
`---RECENT-WINDOW-DAYS---` (inclusive). This applies identically to current-repo and workspace-member rows.
Beads-done (keyed off `**Deliverable:**` when present, else the full `**Beads:**` field) sits just
under a merged PR (the finished-work signal when there's no live branch/PR — the trunk case) but
**below** an open PR. Jira-Done is *not* in this list — the script can't query Jira; the skill folds
it in at §Jira-Done. `current_repo_stale` counts the `keep`/`safe` rows that are **not** superseded;
superseded rows are counted by `current_repo_superseded`. Rows that can't be auto-classified may set
`needs-review` (§Trunk-review) or `needs-age-review` (§Age-review) instead — neither is counted in
`current_repo_stale`.

---

## §Workspace-members — handoffs in sibling repos of a multi-repo workspace

An mgit (`.mgit.conf`) or submodule workspace **root aggregates member repos that are
independent git repos with their own identities**. A handoff recorded inside a member therefore
keys to the member, not the root — so from the workspace root, the directory you actually orient
in, every member handoff lands in `---OTHER-REPOS---`: invisible and unpickable. In a real
workspace that can hide the majority of your handoffs behind a root that has almost none.

`list.sh` discovers the members (one `multirepo.sh --members-only` call — no per-member status
sweep) and emits them in the two sections above. Members are resolved through the same
`resolve_repo_info` path as the current repo, so symlinked members and `.claude` unification behave
identically.

**Classification.** Member rows are classified by the *same* rules as current-repo rows (§Status,
§Archive-glyph) — branch-state, PR state and bead closure are all re-run **inside the member repo**
(`git -C`, `gh` in the member's cwd, `bd -C`). This is gated on `--check-branches`, matching the
current-repo contract: a caller asking for a cheap offline listing must not silently pay N repos'
network calls. Without the flag, member rows carry `unknown` branch/PR state and empty
`archive-class`, and `workspace_classified` is `0`.

Because members are classified, member rows in `---HANDOFFS---` now also carry real state rather
than the blanket `unknown` older revisions emitted. No existing consumer reads them (all filter to
`repo-key == CURRENT-REPO`), so this is additive information, not a contract change.

**Stale accounting is kept separate.** Member rows feed `workspace_member_stale`, never
`current_repo_stale` — so §Archive-flow's candidate set stays strictly current-repo and a member
handoff can never be swept up by an archive prompt aimed at the repo you're standing in.

**Picking is `cd`-gated.** Member rows are pickable, but a caller MUST surface the member path as a
required `cd` before acting on the resume block. The wrong-repo guard is honoured by making the
directory change explicit, not by hiding the handoff.

---

## §Jira-Done — resolve ticket closure for still-live rows (skill layer)

`list.sh` can read PR and bead state but **cannot call the Jira MCP** — so a handoff whose only
"finished" signal is its ticket being closed in Jira still arrives with `archive-class` empty
(`🟢 live`). Close that gap here, model-side. This step is **optional**: a skill that wants to stay
network-/tool-light may skip it and let the PR/bead/supersede classification stand.

**Gate — skip entirely unless _all_ of:** you ran with `--check-branches`, the Jira MCP is
configured, and there is at least one current-repo row with no existing done/stale/supersede signal
**and** a non-`—` `{jira-field}`. A recent completed row can also have empty `archive-class`, so do not
use that field alone as the live-row test. If none qualify, do nothing.

For the qualifying rows, collect the distinct Jira keys and resolve their status in **one batched** query:

```
mcp__jira__jira_get
  path: /rest/api/3/search/jql
  queryParams:
    jql: key in (KEY-1, KEY-2, …) AND statusCategory = Done
    fields: status
  jq: issues[*].key
```

Any key the query returns is **Done** (Jira's `Done` status *category* covers Done / Closed /
Resolved / Won't Do across workflow variants). For each live row whose ticket is in that set,
**promote it to done**: render the Jira-Done status, and treat its `archive-class` as `safe` only when
the row is outside `---RECENT-WINDOW-DAYS---`. A recent Jira-Done row stays retained with an empty
`archive-class`. A row with several tickets counts as done only when **every** ticket it names is Done.

If the Jira MCP errors or isn't configured, skip silently — never fail over Jira.

---

## §Status — classify a row → status glyph

Pick the first that applies, in this order:

1. `superseded-by` non-empty → `⏩ superseded` with the newer handoff's slug and reason, e.g. `⏩ by ab-1470-complete (same branch)`. Humanise the reason: `branch` → "same branch", `slug` → "same topic", `collision` → "same-day re-wrap". Derive the newer slug from the `superseded-by` filename (strip the `YYYY-MM-DD-` prefix and `.md`).
2. `pr-state` = `open` → `🟠 PR #{pr-number} open` (active work — link `pr-url` if rendering allows).
3. `pr-state` = `merged` → `✅ PR #{pr-number} merged` (definitive — survives squash-merge).
4. `beads-done` = `Y` → `✅ done (beads closed)` (every referenced bead is closed — the finished-work signal when there's no live branch/PR, e.g. trunk repos).
5. Jira-Done from §Jira-Done → `✅ done ({KEY} done)` (ticket closed in Jira; only reachable when that step ran).
6. `pr-state` = `closed` → `🚫 PR #{pr-number} closed` (abandoned).
7. `branch-state` = `merged` → `🔵 merged` (branch landed; no PR data).
8. `branch-state` = `gone` → `⚪ branch gone`.
9. otherwise → `🟢 live` (treat `unknown` as live — we have no evidence it's dead).

Supersede wins because "a newer handoff continues this" is the most actionable signal. PR state beats
`branch-state` because it's ground truth (and the only thing that catches a squash-merge); an open PR
specifically means *don't archive*. The two `✅ done` states (beads / Jira) rank above closed/gone for
the same reason a merged PR does — the work shipped. Recent-retention can still leave
`archive-class` empty; status and archive eligibility are deliberately separate.

Emit emoji glyphs **exactly as written here**, including the variation selector on `✂️` and `⚠️`
(the wide colored forms, not the narrow text `✂︎`/`⚠︎`) — mixing presentations makes column widths jump.

---

## §Archive-glyph — archive recommendation column

Render directly from the `archive-class` field — `safe` → `🗄️ safe`, `keep` → `⚠️ keep?`, empty →
`—` (a §Jira-Done promotion is `safe` only outside the recent window). `safe` is low-regret (superseded / merged / done);
`keep?` is higher-regret (abandoned / branch gone with no merge evidence).

---

## §Archive-flow — the opt-in archive cleanup

Skip entirely only if `current_repo_superseded == 0`, `current_repo_stale == 0`, **and** §Jira-Done
promoted no older row to `safe`. The script counters cannot include model-side Jira results, so an
older promotion is itself an effective Done candidate even when both counters remain zero. A recent
Jira-Done status is retained and does not open this flow.

Archiving **moves** handoffs to `~/.claude/handoffs/archive/` (still on disk, still greppable; just
out of the active listing). It is opt-in and never automatic — rows stay pickable until the user says so.

The candidates split by regret — the `archive-class` field already encodes which is which. Present
them as **distinct groups** and be honest about the difference:

- **Superseded** (`archive-class=safe`, `superseded-by` non-empty) — a newer handoff in this repo continues the thread. Low regret: the context lives on in the newer file.
- **Done** (`archive-class=safe`, not superseded — Status `✅ PR merged`, `✅ done (beads closed)`, `✅ done ({KEY} done)`, or `🔵 merged`) — the work shipped: the PR landed, every referenced bead is closed, the ticket is Done, or the branch tip is in the default branch. Low regret. This is the group that catches finished trunk work and trunk-parked PR handoffs that used to masquerade as `🟢 live`.
- **Stale** (`archive-class=keep` — Status `🚫 PR closed` or `⚪ branch gone`) — abandoned, and *no newer handoff supersedes it*. Higher regret: this may be the **only** record of that thread. Default to leaving these unless the user is sure.

A row is **never** a candidate while its PR is open (`🟠`) — that's live work. A recent row is also
never a candidate unless it is superseded; completion and stale signals remain visible in Status but
receive no archive glyph until the grace window passes. A row that is both superseded and otherwise
archivable belongs in the Superseded group (supersede is the safest reason to archive).

Prompt with `AskUserQuestion` (multiSelect). One option per candidate, labelled `{date} {slug}`,
described by its group:

- superseded → `⏩ superseded by {newer-slug}`
- done → `✅ PR #{pr-number} merged` / `✅ beads closed` / `✅ {KEY} done` / `🔵 branch merged`
- stale → `🚫 PR #{pr-number} closed — no newer handoff` / `⚪ branch gone — no newer handoff`

> Archive these to `~/.claude/handoffs/archive/`? They stay on disk (greppable), just out of the
> picker. **Superseded** and **done** ones are safe — the context lives on or the work shipped.
> **Stale** ones may be the only record of an abandoned thread, so leave any you might still want.

For the selected filenames, archive them in one call:

```bash
~/.agents/skills/handoffs/scripts/archive.sh {file1} {file2} …
```

Parse the script's `---ARCHIVED---` / `---SKIPPED---` sections and confirm:

```markdown
✅ Archived {N} handoff(s) to `~/.claude/handoffs/archive/`.
```

Surface any `---SKIPPED---` lines verbatim with their reason — never drop them silently. Only ever
offer rows with a non-empty `archive-class` (`safe` or `keep`); never a `🟢 live`, `🟠 PR open`, or
`unknown` row. Never delete — `archive.sh` only moves. If the user selects none, render nothing.
After archiving, **drop the archived rows** from any subsequent listing or picker the caller renders
(and subtract them from `current_repo_total`) so they aren't offered again this run.

---

## §Archive-flow-members — archiving workspace-member handoffs from the root

Used by `/handoffs` and `/handoffs-tidy`. Both commands use this separate, per-member confirmation
flow after their current-repo archive steps; `/handoffs` must not leave classified `safe` member rows
as a table-only dead end.

Member rows feed `workspace_member_stale`, never `current_repo_stale`, so §Archive-flow's candidate
set stays strictly current-repo. That guard is deliberate and stays: a prompt aimed at the repo you're
standing in must never sweep up a sibling's handoff. This section is the *explicit* opt-in that makes
member handoffs tidyable without weakening it.

**Gate — skip entirely unless all of:** you ran with `--check-branches` (member rows are otherwise
unclassified), `workspace_member_handoffs > 0`, and at least one member row has
**`archive-class=safe`**.

**Only `safe` rows are offered here.** A member row classed `keep` (PR closed unmerged, or branch gone
with no merge evidence) is higher-regret and may be the only record of an abandoned thread — judging
that needs the full per-row context, so it requires `cd`ing into the member repo and running
`/handoffs-tidy` there. Say so rather than silently dropping them:
`_{N} keep-class candidate(s) in {repo} need a closer look — `cd {path}` and re-run._`

Render the candidates grouped by member repo, newest first:

```markdown
## 🧱 Archive candidates — workspace members ({count})

| Repo | Date | Slug | Branch | Status |
|------|------|------|--------|--------|
```

**Confirm one repo at a time.** Do *not* enumerate candidates as individual options: `AskUserQuestion`
caps at 4 options, and a member repo can easily hold more (the case that motivated this had 8 in one
repo). Ask **one question per member repo**, in descending candidate count:

> Archive the {N} finished handoff(s) for `{repo}`? They're all merged/superseded — the work shipped.

Options:
- **Archive all {N}** — every `safe` candidate for that repo.
- **Superseded only ({M})** — just the rows with a non-empty `superseded-by` (the lowest-regret
  subset). Omit this option when M is 0 or M == N.
- **Skip {repo}** — leave them; suggest `cd {path} && /handoffs-tidy` for per-row control.

Collect the selections across repos and archive them in **one** `archive.sh` call (it takes bare
filenames and is repo-agnostic — it only ever moves files within `~/.claude/handoffs/`). Parse
`---ARCHIVED---` / `---SKIPPED---` and confirm exactly as §Archive-flow does, naming the repos:

```markdown
✅ Archived {N} handoff(s) from {repo-list} to `~/.claude/handoffs/archive/`.
```

Never offer a member row that is `🟢 live`, `🟠 PR open`, or `unknown`.

---

## §Trunk-review — assisted prompt for un-auto-classifiable trunk handoffs

A **legacy** trunk-parked handoff (recorded on `master` before the `**Deliverable:**` field existed)
can't be auto-classified: branch/PR state is `unknown`, and its `**Beads:**` list mixes own work with
context/epic beads, so neither the all-closed rule nor branch/PR liveness fires. The script flags
exactly these with **`needs-review=Y`** (renders `🟢 live`, trunk-parked, no Deliverable field,
partial bead closure — `beads-progress` with closed ≥ 1). They are **not** `archive-class` candidates
and never auto-archive — the open beads might be live own-work or might be untouched context, and the
script can't tell.

Run this only when there is at least one `needs-review=Y` current-repo row. It is a **separate,
clearly-labelled** prompt — *not* mixed into the §Archive-flow groups, because these are
judgement calls, not safe candidates:

```markdown
## 🔍 Trunk handoffs worth a look ({count})

These are recorded on the trunk with some beads closed and some open, and no **Deliverable:** marker
to tell own-work from context — so I can't tell if they're finished. Open the ones you're unsure of.

| Date | Slug | Beads closed | Beads |
|------|------|--------------|-------|
```

- **Beads closed**: the `{beads-progress}` value (e.g. `1/4`).
- **Beads**: the `{beads-field}` token list, so the closed/open split is visible inline.

Then offer, via `AskUserQuestion` (multiSelect, one option per `needs-review` row, labelled
`{date} {slug}`, described by its `{beads-progress}` + bead list):

> Archive any whose **own** work is actually done? The open beads here may just be context/epics that
> never close — if so the handoff is finished and safe to archive. Leave any whose own work is still live.

Archive the selected filenames via the same `archive.sh` call and confirmation as §Archive-flow. The
durable fix is upstream: once these age out and new handoffs carry `**Deliverable:**`, this prompt
goes quiet on its own.

---

## §Age-review — assisted prompt for old rows with no usable signals

A handoff with `branch-state=unknown` can remain `🟢 live` forever when it has no usable PR signal,
no resolvable beads, and no other completion signal. This includes trunk-parked rows and feature
branches whose liveness cannot be established. Age does **not** prove that it finished; it only makes
the row worth asking about. `list.sh` flags these current-repo rows with `needs-age-review=Y` once they
are older than `---STALE-DAYS---` (the recent-window size by default, configurable with `--stale-days N`).

Run this after §Jira-Done. If Jira promoted a flagged row to `safe`, handle it as Done instead and do
not include it here. Present the remaining rows as a separate assisted group, never mixed into
§Archive-flow or §Trunk-review:

```markdown
## 🕰️ Old handoffs with no completion signal ({count})

These are older than {stale-days} days, have unknown branch liveness, no usable PR signal, and no
resolvable beads. Age is only a reason to ask; skip anything still waiting on external work.

| Date | Slug | Jira | Evidence |
|------|------|------|----------|
```

- **Jira**: `{jira-field}`, or `—`.
- **Evidence**: `no usable PR signal · no resolvable beads · >{stale-days}d`.

Prompt with `AskUserQuestion` using `multiSelect` and batches of at most four rows. Label each option
`{date} {slug}` and describe it as `>{stale-days}d · Jira: {jira-field-or-dash}`. Leave every option
unselected by default:

> Archive any old handoffs you no longer need? Age is not a done signal; leave parked or uncertain
> threads untouched.

Only filenames the user explicitly selects go to `archive.sh`. These rows retain empty
`archive-class`, are never auto-selected, and are never auto-archived. Skipping must be trivial and
silent. `/handoffs` and `/handoffs-tidy` must both consume this shared flag and follow this section,
so their classification and safeguards stay identical.
