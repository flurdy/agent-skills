# Handoffs — shared classification & archive spec

Normative reference for **`/handoffs`** (the picker) and **`/handoffs-tidy`** (the pruner). Both
skills run `list.sh` and `Read` this file; it is the single source of truth for **how to read the
script's output, classify each handoff, and run the archive flow**. The *signals* themselves come
from `list.sh` (the `archive-class` field already encodes the safe/keep verdict) — this file is the
single source for how to render and act on them, so the two skills can never drift on classification.

Cite sections by anchor: §Fields, §Jira-Done, §Status, §Archive-glyph, §Archive-flow.

---

## §Run — invoking `list.sh`

```bash
~/.claude/skills/handoffs/scripts/list.sh --check-branches
```

`--check-branches` adds branch-liveness classification (the `branch-state` field) for current-repo
handoffs. It runs one `git ls-remote` (network, timeout-guarded) plus local merge-base checks. It is
current-repo-only — the git queries run in pwd, so handoffs in other repos always report `unknown`.

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
- `---HANDOFFS-DIR---` — directory scanned (`~/.claude/handoffs`).
- `---HANDOFFS---` — one pipe-delimited line per handoff, newest first (see line format below).
- `---CURRENT-REPO-LATEST---` — a single `{slug}|{branch}|{date}` line for the newest current-repo handoff, or empty. (Consumed by `/landscape`; the picker and tidy render the full table instead and can ignore it.)
- `---CURRENT-REPO-LIVE---` — one `{slug}|{branch}|{date}|{time}` line per recent non-superseded current-repo handoff. (Consumed by `/landscape`; ignore here.)
- `---SUMMARY---` — `total=N`, `current_repo_total=N`, `current_repo_recent=N`, `current_repo_recent_live=N`, `current_repo_pruned=N`, `current_repo_superseded=N`, `current_repo_stale=N`, `other_repos=N`, `pruned_total=N`, `superseded_total=N`, `unresolved=N`.
- `---OTHER-REPOS---` — one line per distinct non-current repo: `{repo-key}|{count}|{display}`, sorted by count desc.

**`---HANDOFFS---` line — 18 pipe-delimited fields, in order:**

```
{filename}|{date}|{slug}|{cwd}|{branch}|{repo-key}|{exists}|{superseded-by}|{supersede-reason}|{branch-state}|{pr-state}|{pr-number}|{pr-url}|{archive-class}|{time}|{beads-field}|{jira-field}|{beads-done}
```

`{time}` (field 15) is the `HH:MM` the handoff was written — from the `# Resume:` header
(wrap-up v0.8.0+), falling back to the file's mtime; `?` only when neither is available. Fields after
`{time}` were **appended** so older 9-field positional parsers keep working.

### Repo identity (`repo-key`, `exists`)

- Resolution order per handoff: (1) the **`Repo root:`** line (wrap-up v0.2.0+), then (2) walking up the `Where to pick up:` cwd to find a parent repo.
- Identity prefers `remote.origin.url` so independent clones of the same upstream collapse to one row; falls back to realpath of git-common-dir for local-only repos.
- `.claude`-symlink unification: if a repo root's `.claude` is a symlink whose target lives inside another git repo, that other repo's identity wins (one hop, no cycles).
- Pruned worktrees still resolve — the walk-up climbs out of the deleted directory to a still-existing parent.
- `repo-key` is `UNRESOLVED` only when neither the `Repo root:` field nor the cwd walk-up finds a repo.
- `exists=Y` means the recorded cwd still exists on disk; `exists=N` means it was pruned (still pickable — resume in your current checkout or a fresh worktree).

### Supersede (`superseded-by`, `supersede-reason`)

- `superseded-by` is the filename of the **newest** handoff in the same repo that continues this thread, or empty if this is the live tip. `supersede-reason` is `branch` (same branch), `slug` (same exact topic slug), or `collision` (same-day re-wrap). Ticket/cwd overlap is deliberately *not* a supersede signal — a ticket legitimately spans many handoffs.
- **Trunk co-residence never supersedes.** The `branch` reason excludes the default branch (`main`/`master`): two distinct threads both recorded on the trunk (the wrap-up trunk-parking case) are *not* the same thread — they only supersede on an exact slug or same-day collision.

### Branch-state (`branch-state`) — only populated with `--check-branches`, current-repo rows only

- `live` — branch exists and isn't merged into the default branch.
- `merged` — branch tip is an ancestor of the default branch (its PR likely landed).
- `gone` — branch exists neither locally nor on the remote (deleted after merge, or abandoned).
- `unknown` — couldn't determine (other repo, branch `?`, offline with no local ref, **or the handoff's branch is the default branch itself**). **Never treated as stale.**
- `merged` and `gone` are the two "stale" states. Offline runs degrade safely: a branch with no local ref reports `unknown`, never a false `gone`.
- **Default-branch guard:** a handoff recorded on the trunk reports `unknown`, never `merged` — being on the trunk says nothing about whether the work shipped. PR detection still applies on top.

### PR fields (`pr-state`/`pr-number`/`pr-url`) — only with `--check-branches` + `gh`, current-repo rows only

A PR matches a handoff either by branch (headRefName) **or by a number recorded in the handoff's
`**PRs:**` field** — the number fallback rescues the **trunk-parking** case (wrap-up recorded `main`
because the feature branch was already gone after merge; a branch-only lookup matches nothing and the
row wrongly shows `🟢 live`, but the merged PR's number is still in the body).

- `merged` — a PR for this branch (or recorded number) was merged. **Ground truth that beats `branch-state`** — local ancestry can't see a squash-merge (the branch is never an ancestor of the default tip).
- `open` — a PR is open. *Active* work — overrides everything except supersede; **never** an archive candidate.
- `closed` — a PR was closed without merging (abandoned).
- `none` — `gh` ran but found no PR for this branch.
- `unknown` — `gh` wasn't consulted (no flag, no `gh`, offline, or branch `?`). Falls back to `branch-state`.

### Beads / Jira (`beads-field`, `jira-field`, `beads-done`)

- `{beads-field}` — raw `**Beads:**` token list; empty unless beads exist locally or a `--bead`/`--ticket` filter is active.
- `{jira-field}` — raw `**Jira:**` token list; populated under `--check-branches` (and filters). Bash can't call the Jira MCP, so the script never sets a jira-done flag — it only hands you the keys (see §Jira-Done).
- `{beads-done}` — `Y` when **every** bead the handoff references is closed (all `**Beads:**` IDs resolve to `status=closed`), else empty. Computed locally via `bd` for current-repo rows whenever beads exist — **independent of `--check-branches`**. A field truncated with `(+N more)` can't be fully verified and stays empty (conservative).

### Archive-class (`archive-class`) — current-repo rows only

The script's per-row archive recommendation, so callers read straight off it instead of re-deriving:

- `safe` — superseded, or `pr-state=merged`, or `beads-done=Y`, or `branch-state=merged`. Low regret — the context lives on, or the work demonstrably shipped.
- `keep` — `pr-state=closed`, or `branch-state=gone` with no merged/done evidence. Higher regret — may be the only record.
- empty — live work (incl. an open PR) or `unknown`. **Not an archive candidate.**

Precedence: supersede > open PR > merged PR > **beads-done** > closed PR > local `merged` > `gone`.
Beads-done sits just under a merged PR (the finished-work signal when there's no live branch/PR — the
trunk case) but **below** an open PR. Jira-Done is *not* in this list — the script can't query Jira;
the skill folds it in at §Jira-Done. `current_repo_stale` counts the `keep`/`safe` rows that are
**not** superseded; superseded rows are counted by `current_repo_superseded`.

---

## §Jira-Done — resolve ticket closure for still-live rows (skill layer)

`list.sh` can read PR and bead state but **cannot call the Jira MCP** — so a handoff whose only
"finished" signal is its ticket being closed in Jira still arrives with `archive-class` empty
(`🟢 live`). Close that gap here, model-side. This step is **optional**: a skill that wants to stay
network-/tool-light may skip it and let the PR/bead/supersede classification stand.

**Gate — skip entirely unless _all_ of:** you ran with `--check-branches`, the Jira MCP is
configured, and there is at least one current-repo row that is **still live** (`archive-class` empty)
**and** has a non-`—` `{jira-field}`. If none qualify, do nothing.

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
**promote it to done**: treat its `archive-class` as `safe` for the rest of this run. A row with
several tickets counts as done only when **every** ticket it names is Done.

If the Jira MCP errors or isn't configured, skip silently — never fail over Jira.

---

## §Status — classify a row → status glyph

Pick the first that applies, in this order:

1. `superseded-by` non-empty → `⏩ superseded` with the newer handoff's slug and reason, e.g. `⏩ by ge-1470-complete (same branch)`. Humanise the reason: `branch` → "same branch", `slug` → "same topic", `collision` → "same-day re-wrap". Derive the newer slug from the `superseded-by` filename (strip the `YYYY-MM-DD-` prefix and `.md`).
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
the same reason a merged PR does — the work shipped — and mirror the script's `archive-class=safe`.

Emit emoji glyphs **exactly as written here**, including the variation selector on `✂️` and `⚠️`
(the wide colored forms, not the narrow text `✂︎`/`⚠︎`) — mixing presentations makes column widths jump.

---

## §Archive-glyph — archive recommendation column

Render directly from the `archive-class` field — `safe` → `🗄️ safe`, `keep` → `⚠️ keep?`, empty →
`—` (treat a §Jira-Done promotion as `safe`). `safe` is low-regret (superseded / merged / done);
`keep?` is higher-regret (abandoned / branch gone with no merge evidence).

---

## §Archive-flow — the opt-in archive cleanup

Skip entirely if `current_repo_superseded == 0` **and** `current_repo_stale == 0`.

Archiving **moves** handoffs to `~/.claude/handoffs/archive/` (still on disk, still greppable; just
out of the active listing). It is opt-in and never automatic — rows stay pickable until the user says so.

The candidates split by regret — the `archive-class` field already encodes which is which. Present
them as **distinct groups** and be honest about the difference:

- **Superseded** (`archive-class=safe`, `superseded-by` non-empty) — a newer handoff in this repo continues the thread. Low regret: the context lives on in the newer file.
- **Done** (`archive-class=safe`, not superseded — Status `✅ PR merged`, `✅ done (beads closed)`, `✅ done ({KEY} done)`, or `🔵 merged`) — the work shipped: the PR landed, every referenced bead is closed, the ticket is Done, or the branch tip is in the default branch. Low regret. This is the group that catches finished trunk work and trunk-parked PR handoffs that used to masquerade as `🟢 live`.
- **Stale** (`archive-class=keep` — Status `🚫 PR closed` or `⚪ branch gone`) — abandoned, and *no newer handoff supersedes it*. Higher regret: this may be the **only** record of that thread. Default to leaving these unless the user is sure.

A row is **never** a candidate while its PR is open (`🟠`) — that's live work. A row that is both
superseded and otherwise archivable belongs in the Superseded group (supersede is the safest reason to archive).

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
~/.claude/skills/handoffs/scripts/archive.sh {file1} {file2} …
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
