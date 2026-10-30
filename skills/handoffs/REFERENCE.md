# Handoffs — shared classification & archive spec

Normative reference for **`/handoffs`** (the picker) and **`/handoffs-tidy`** (the pruner). Both
skills run `list.sh` and `Read` this file; it is the single source of truth for **how to read the
script's output, classify each handoff, and run the archive flow**. The *signals* themselves come
from `list.sh` (the `archive-class` field already encodes the safe/keep verdict after completion-aware retention) — this file is the
single source for how to render and act on them, so the two skills can never drift on classification.

## Prompt boundaries

**Visible preview first.** In both `/handoffs` and `/handoffs-tidy`, render the applicable
candidate or assisted-review table as visible Markdown before any archive question (structured
or plain text). Include every row that question offers, even if it was outside the capped member
inventory. Never replace the preview with a prose summary or rely on collapsed tool output.
Send the preview in an assistant message before calling `AskUserQuestion`, not in a final
response after it returns. `/handoffs` additionally renders its full prescribed inventory before
entering these flows; `/handoffs-tidy` needs only the relevant candidate previews, not that inventory.

All archive flows below require explicit filename selections. Suggestions are not preselected
consent. Use 2–4 options per structured question; for a single candidate offer Archive / Keep.
For more than four candidates, use bounded batches or a plain-text filename selection with an exact
confirmation. An abandoned prompt selects nothing. This also applies to §Trunk-review, §Age-review, and §Age-review-members:
those assisted groups may have unknown/live display status and empty archive-class. They are explicit
exceptions to the automatic-candidate restrictions in §Archive-flow, not permission to archive by age.

**Storage gate.** Every archive flow (§Archive-flow, §Archive-flow-members, §Trunk-review,
§Age-review, §Age-review-members) runs only when `---STORAGE---` is `canonical`. For `legacy`,
`mixed` or `partial`, show the candidates once as a read-only preview, say that archiving stays
disabled until `~/.claude/handoffs` is migrated (or the unreadable location is fixed), and ask no
archive question: `archive.sh` refuses while the legacy location exists.

Cite sections by anchor: §Run, §Retention, §Fields, §Jira-Done, §Status, §Archive-glyph, §Archive-flow, §Trunk-review, §Age-review, §Age-review-members.

---

## §Run — invoking `list.sh`

```bash
~/.agents/skills/handoffs/scripts/list.sh --check-branches [--retention-days N] [--stale-days N]
```

`--retention-days` sets the positive-integer retention period (default **14**); see §Retention.
`--stale-days` sets the age floor for §Age-review and §Age-review-members. It defaults to the
retention period; shorter values are clamped to it. It never changes `archive-class`.
`--recent-days` still controls only recent-activity summaries (3 days, or 4 on Tuesday), not archiving.

Required runtimes: Bash, Git, standard Unix text tools and GNU/BSD `date`, plus **Python 3.10+**
(standard library only) for `scripts/retention.py`. A missing Python/helper fails clearly with exit 2.
Optional `gh`, `bd`, and Jira access degrade as described below. Listing never writes retention state.

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

## §Retention — completion-aware archive eligibility

Completed context remains visible and pickable; completion is not an archive deadline. Both skills
and all current-repo and workspace-member flows use the same policy:

- Default **14 calendar days**, configurable with `--retention-days N`; no sprint-calendar integration.
- Capture one UTC `---AS-OF-DATE---`. Compare calendar dates, not elapsed hours. Retain the boundary
  day: eligibility requires **both** the handoff date and completion date to be strictly earlier
  than `as-of-date − retention-days`. On 20 August with 14 days, 6 August is retained; 5 August may
  be offered. The later date therefore controls retention.
- Accept only valid timezone-aware completion timestamps; normalize to UTC before taking the date.
  PRs use `mergedAt` (merged) or `closedAt` (closed unmerged). Beads use the latest `closed_at` across
  the closure-check set; missing/unresolved IDs cannot prove all-closed. Jira uses the latest
  `resolutiondate` across every referenced Done ticket. Never use `updated_at`, commit author dates,
  file mtime, handoff age, or the time completion was first observed as a closure timestamp.
- For multiple matching PRs at the winning status, use the latest timestamp and require all clocks
  to be valid. An open PR wins over merged/closed matches. When both merged PR and all-closed Beads
  signals exist, retain until both clocks pass. A newer completion cannot be masked by an older one.
- Missing, malformed, naive, or future timing **never** earns an archive suggestion. Keep accurate
  merged/done/stale Status and empty Archive. Branch ancestry or disappearance alone has no trustworthy
  completion date, so those rows stay retained. There is no first-observation cache or listing write.
- Superseded continuations are the sole immediate exception: newer context replaces them. Supersede
  remains distinct from merely completed work and still requires explicit archive confirmation.
- Assisted prompts cannot bypass retention. Partial-bead trunk review requires the handoff and every
  known closed bead's timestamp to pass the same clock; an unknown closed timestamp suppresses it.
  Signal-less age review uses the clamped age floor; a failed Beads lookup/parser is not evidence
  for that prompt. Once Jira proves completion, suppress both
  assisted flags even when completion timing is missing or retention has not elapsed.

`retention.py` is the clock authority for the lister and §Jira-Done. It is read-only and never
archives. These rules change suggestions, not the explicit confirmation requirement or pickability.
Retained completed rows are not active-work resume nudges: `/landscape` and exact task matches
continue to exclude done/stale rows independently of archive eligibility.

---

## §Fields — reading the output

Delimited sections:

- `---CURRENT-REPO---` — current identity: the enclosing repo (origin URL preferred, falling back to realpath of git-common-dir); outside any repo, the directory itself as `dir:{realpath}`; `NONE` only if even that fails.
- `---CURRENT-REPO-DISPLAY---` — short label (basename of the repo root, or of the directory), or `NONE`.
- `---CURRENT-REPO-KIND---` — `repo`, `dir` (not in a git repo; matching is by exact directory, no branch/PR liveness or workspace members), or `NONE`.
- `---RECENT-WINDOW-DAYS---` — days used for the "recent" filter (3 default; Mon → 3, Tue → 4 weekend buffer).
- `---RETENTION-DAYS---` — completion-aware archive retention period (14 by default).
- `---AS-OF-DATE---` — UTC calendar date captured once for this listing; use it for §Jira-Done too.
- `---STALE-DAYS---` — assisted age-review floor (defaults/clamps to the retention period).
- `---HANDOFFS-DIR---` — the canonical directory (`~/.agents/handoffs`). Rows carry their own
  `{path}`; load that, never `{HANDOFFS-DIR}/{filename}`.
- `---STORAGE---` — which locations were read:
  - `canonical` — only `~/.agents/handoffs` (or neither location) exists. The only writable state.
  - `legacy` — only the retired `~/.claude/handoffs` exists; its rows are listed read-only.
  - `mixed` — both exist; rows from both are listed and labelled by `{source}`.
  - `partial` — a location is a symlink, not a directory, unreadable, vanished mid-read, or holds a
    filename that cannot be represented in a record. That location is never followed or read; rows
    from readable locations are still listed and the script exits `3`. A partial inventory is not
    an empty one.
  For anything but `canonical`, saving (wrap-up) and archiving stay disabled until the legacy
  location is migrated by a separately approved whole-directory move. Reading is not permission to
  move, merge or edit either location.
- `---SOURCES---` — one `{source}|{dir}|{status}|{listed}` line per location (`canonical`, then
  `legacy`); status is `ok`, `absent`, `unsafe`, `unreadable` or `vanished`.
- `---HANDOFFS---` — one pipe-delimited line per handoff, newest first (see line format below).
- `---MATCHED-HANDOFFS---` — emitted with `--bead` / `--ticket`: exact-token, case-insensitive
  current-repo matches, excluding superseded/completed/inactive rows under the available evidence.
  Fields: `{filename}|{date}|{time}|{slug}|{branch}|{exists}|{pr-state}|{pr-number}|{pr-url}|{source}|{path}`;
  load the matched handoff from `{path}`.
  Offline eligibility is not proof of live session ownership or remote branch state. An empty match
  does not prove the requested task shipped; a failed lookup is not an empty match.
- `---CURRENT-REPO-LATEST---` — a single `{slug}|{branch}|{date}` line for the newest current-repo handoff, or empty. (Consumed by `/landscape`; the picker and tidy render the full table instead and can ignore it.)
- `---CURRENT-REPO-LIVE---` — one `{slug}|{branch}|{date}|{time}` line per recent active current-repo handoff; completed, stale, and superseded rows are excluded. (Consumed by `/landscape`; ignore here.)
- `---SUMMARY---` — `total=N`, `current_repo_total=N`, `current_repo_recent=N`, `current_repo_recent_live=N`, `current_repo_pruned=N`, `current_repo_superseded=N`, `current_repo_stale=N`, `current_repo_age_review=N`, `other_repos=N`, `pruned_total=N`, `superseded_total=N`, `unresolved=N`, `workspace_members=N`, `workspace_member_handoffs=N`, `workspace_member_stale=N`, `workspace_member_age_review=N`, `workspace_classified=N`, `legacy_total=N`, `source_collisions=N`.
- `---OTHER-REPOS---` — one line per distinct non-current repo: `{repo-key}|{count}|{display}`, sorted by count desc. **Workspace members are still counted here** — the section is deliberately unfiltered so existing parsers see no change; a caller rendering the workspace sections below should subtract them (see §Workspace-members).
- `---WORKSPACE-MEMBER-REPOS---` — one line per member repo of the multi-repo workspace the cwd belongs to: `{repo-key}|{display}|{path}|{handoff-count}`, in `.mgit.conf` order. Empty when the cwd isn't in a workspace. The current repo is excluded.
- `---WORKSPACE-MEMBER-HANDOFFS---` — one line per handoff owned by a member, newest first. The **same 24 fields** as `---HANDOFFS---` plus `{member-display}|{member-path}` appended (26 total; the member path is always the final field), so an existing parser can be reused unchanged. Suppressed by `--summary-only`.
- `---SOURCE-COLLISIONS---` — one `{filename}|identical` or `{filename}|different` line per
  filename present in both locations (content compared byte-for-byte). Each copy is its own row,
  identified by `{source}`/`{path}`; the two never supersede each other, and neither is preferred,
  merged or deleted.

Field values never contain the `|` delimiter or a newline: `list.sh` replaces both
with a space when it builds a record. Handoff text is author-controlled, and these
records are read by position, so an unescaped delimiter would shift every later
field and change what a row appears to say. Parsers can rely on the field count.

**`---HANDOFFS---` line — 24 pipe-delimited fields, in order:**

```
{filename}|{date}|{slug}|{cwd}|{branch}|{repo-key}|{exists}|{superseded-by}|{supersede-reason}|{branch-state}|{pr-state}|{pr-number}|{pr-url}|{archive-class}|{time}|{beads-field}|{jira-field}|{beads-done}|{deliverable-field}|{beads-progress}|{needs-review}|{needs-age-review}|{source}|{path}
```

`{source}` (field 23) is `canonical` or `legacy`; `{path}` (field 24) is the exact file the row was
read from. `{filename}` alone is ambiguous when both locations hold the same name.

`{time}` (field 15) is the `HH:MM` the handoff was written — from the `# Resume:` header
(wrap-up v0.8.0+), falling back to the file's mtime; `?` only when neither is available. Fields after
`{time}` were **appended** so older positional parsers keep working.

### Repo identity (`repo-key`, `exists`)

- Resolution order per handoff: (1) the **`Repo root:`** line (wrap-up v0.2.0+), then (2) walking up the `Where to pick up:` cwd to find a parent repo.
- Identity prefers `remote.origin.url` so independent clones of the same upstream collapse to one row; falls back to realpath of git-common-dir for local-only repos.
- `.claude`-symlink unification: if a repo root's `.claude` is a symlink whose target lives inside another git repo, that other repo's identity wins (one hop, no cycles).
- Pruned worktrees still resolve — the walk-up climbs out of the deleted directory to a still-existing parent.
- **Directory fallback:** when no repo is found above the recorded cwd but the directory still exists, the handoff keys to `dir:{realpath}` (display = basename). This is what makes handoffs written from a non-git workspace root pickable when `/handoffs` runs from that same directory. Exact match only — no walk-up, so a pruned non-repo path never keys to a surviving parent.
- `repo-key` is `UNRESOLVED` only when the `Repo root:` field, the cwd walk-up, and the directory fallback all fail (path invalid or gone).
- `exists=Y` means the recorded cwd still exists on disk; `exists=N` means it was pruned (still pickable — resume in your current checkout or a fresh worktree).

### Supersede (`superseded-by`, `supersede-reason`)

- `superseded-by` is the filename of the **newest** handoff in the same repo that continues this thread, or empty if this is the live tip. `supersede-reason` is `branch` (same branch), `slug` (same exact topic slug), or `collision` (same-day re-wrap). Ticket/cwd overlap is deliberately *not* a supersede signal — a ticket legitimately spans many handoffs.
- Recency is date first, then the `# Resume:` time when both records have one. Equal or unknown same-day times are conservatively unordered, except an established filename collision family (`topic` → `topic-2` → `topic-3`): higher collision suffixes are newer. A trailing numeric topic component such as `ABC-123` is never a global recency signal unless an unsuffixed `ABC` handoff establishes that exact collision family.
- **A same-named copy never supersedes.** The same filename in both storage locations is a copy,
  not a newer thread (see `---SOURCE-COLLISIONS---`). Different filenames across locations
  supersede normally, so a newer canonical handoff still retires an older legacy one; resolve
  `superseded-by` against rows from the same location first.
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

- `{beads-field}` — raw `**Beads:**` token list (own-work **and** context/epic beads); populated when beads exist locally, a `--bead`/`--ticket` filter is active, or `--check-branches` enables member-store checks.
- `{jira-field}` — raw `**Jira:**` token list; populated under `--check-branches` (and filters). Bash can't call the Jira MCP, so the script never sets a jira-done flag — it only hands you the keys (see §Jira-Done).
- `{deliverable-field}` — raw `**Deliverable:**` token list: just the **own-work** beads this handoff was advancing (wrap-up v0.10.0+), the subset whose closure means the handoff is finished. Empty for older handoffs that predate the field.
- `{beads-done}` — `Y` when **every** bead in the **closure-check set** is closed (all resolve to `status=closed`), else empty. The closure-check set is the **`**Deliverable:**` field when present**, else the full `**Beads:**` field (legacy fallback). Computed locally via `bd` for current-repo rows whenever beads exist — **independent of `--check-branches`**. A field truncated with `(+N more)` can't be fully verified and stays empty (conservative).
  - **Why Deliverable matters:** in trunk repos all work commits to `master`, so wrap-up records every handoff with `branch: master` → `branch-state=unknown` (the default-branch guard) and no PR. The bead is then the only "done" signal — but the `**Beads:**` list mixes own work with recurring "in-progress elsewhere" context beads and parent epics that never close, so an all-`**Beads:**`-closed rule can never fire. Keying off `**Deliverable:**` (own work only) fixes that. Safety: over-including a bead in Deliverable only ever *under*-detects (a never-closing bead keeps the row live); **omitting** an own-work bead is the only way to false-positive, so wrap-up errs toward including.
- `{beads-progress}` — `{closed}/{total}` over the closure-check set (Deliverable if present, else Beads), or empty when there are no resolvable beads. Lets a caller distinguish *partial* closure (something shipped, something open) from all-open (nothing done) and all-closed (done).
- `{needs-review}` — `Y` for a current-repo row passing §Retention (including its closed beads' timestamps) that **can't be auto-classified** and warrants the assisted prompt (see §Trunk-review): it renders `🟢 live` (`archive-class` empty), is **trunk-parked** (branch is `main`/`master`/the default), has **no `**Deliverable:**` field** (a legacy handoff), and shows **partial** bead closure (`beads-progress` with closed ≥ 1). Rows with a Deliverable field never set this — they classify cleanly. All-closed rows are done (retained or `safe`); all-open rows are genuinely live.
- `{needs-age-review}` — `Y` for an old current-repo or workspace-member row that has no usable completion or liveness signal and warrants §Age-review or §Age-review-members: `--check-branches` was used, the row is older than `---STALE-DAYS---`, `branch-state=unknown`, it has no usable PR signal (`pr-state=none`, including a handoff whose recorded links belong to another repo; or `unknown` with no recorded PR number), and it has no resolvable beads (`beads-progress` empty). Age is not evidence of doneness, so this flag never changes `archive-class` or stale counts. Rows with an open/merged/closed PR, a known-live branch, or an unknown lookup plus a recorded PR number are not flagged.

### Archive-class (`archive-class`) — current-repo and workspace-member rows

The script's per-row archive recommendation, so callers read straight off it instead of re-deriving:

- `safe` — superseded, or a merged-PR/all-closed-Beads row that passes §Retention. Low regret — the context continues elsewhere, or completion and its age are verified.
- `keep` — a closed-unmerged PR that passes §Retention. Higher regret — may be the only record.
- empty — live/unknown work, or non-superseded context retained by §Retention (including unknown completion dates). **Not an archive candidate.** Status remains truthful, so a retained row can show `✅ merged` with Archive `—`.

Precedence before retention: supersede > open PR > merged PR > **beads-done** > closed PR > local `merged` > `gone`.
Supersede remains immediately `safe`; every other result must pass §Retention. Branch-only merged/gone
signals retain their Status but have no completion clock, so their archive class stays empty.
This applies identically to current-repo and workspace-member rows.
Beads-done (keyed off `**Deliverable:**` when present, else the full `**Beads:**` field) sits just
under a merged PR (the finished-work signal when there's no live branch/PR — the trunk case) but
**below** an open PR. Jira-Done is *not* in this list — the script can't query Jira; the skill folds
it in at §Jira-Done. `current_repo_stale` counts the `keep`/`safe` rows that are **not** superseded;
superseded rows are counted by `current_repo_superseded`. Rows that can't be auto-classified may set
`needs-review` (§Trunk-review) or `needs-age-review` (§Age-review / §Age-review-members) instead — neither is counted in
`current_repo_stale` or `workspace_member_stale`.

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

**Review accounting is kept separate.** Member rows feed `workspace_member_stale` and
`workspace_member_age_review`, never the corresponding current-repo counters — so §Archive-flow and
§Age-review stay strictly current-repo. Member rows are handled only by their explicit workspace-member
flows (§Archive-flow-members and §Age-review-members).

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
configured, and there is at least one current-repo or workspace-member row with no existing
done/stale/supersede signal, no open PR, **and** a non-`—` `{jira-field}`. A recent completed row can also have empty `archive-class`, so do not
use that field alone as the live-row test. If none qualify, do nothing.

For the qualifying rows, collect the distinct Jira keys and resolve their status in **one batched** query:

```
mcp__jira__jira_get
  path: /rest/api/3/search/jql
  queryParams:
    jql: key in (KEY-1, KEY-2, …) AND statusCategory = Done
    fields: status,resolutiondate
  jq: '{issues: issues}'
```

Use the available Jira search tool for this same field set; collect all pages before promotion.
Jira's `Done` status category covers Done / Closed / Resolved / Won't Do across workflow variants.
For each qualifying row, pass the returned `{issues: [...]}` JSON on stdin to the shared helper:

```bash
python3 ~/.agents/skills/handoffs/scripts/retention.py jira --keys ABC-123,ABC-456 --handoff-date YYYY-MM-DD --today YYYY-MM-DD --days N
```

Supply the exact comma-separated keys from that row, its handoff date, `---AS-OF-DATE---`, and
`---RETENTION-DAYS---`; do not substitute today's date or a hand-computed threshold. Input contains
only keys and the requested status/resolution fields; do not persist the tracker response.
The helper returns `{"done": true|false, "archive_class": "safe"|""}`. A row counts as done only
when **every** named ticket is returned in the Done category. Missing/reopened tickets never prove done.

On `done=true`, render Jira-Done and use the returned class. A recent Jira-Done row stays retained,
as does an old handoff with recent or unknown resolution timing. **Always clear both `needs-review` and `needs-age-review`**
for that row, not only when `archive_class=safe`; otherwise assisted review would bypass retention.
Apply this overlay to both current and member tables, candidate gates and review counts; raw script
counters cannot include Jira results. Preserve the row in the picker until explicitly archived.

If Jira access errors or isn't configured, skip silently — never fail over Jira. If the retention
helper fails, do not promote archive eligibility or offer assisted review for a row already known Done.

---

## §Status — classify a row → status glyph

Pick the first that applies, in this order:

1. `superseded-by` non-empty → `⏩ by {newer-slug}`, e.g. `⏩ by ab-1470-complete`, with the slug shortened per §Cells. Derive the newer slug from the `superseded-by` filename (strip the `YYYY-MM-DD-` prefix and `.md`). The reason stays out of the table cell; prompts that need it humanise it: `branch` → "same branch", `slug` → "same topic", `collision` → "same-day re-wrap".
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
the same reason a merged PR does — the work shipped. Completion-aware retention can still leave
`archive-class` empty; status and archive eligibility are deliberately separate.

Emit emoji glyphs **exactly as written here**, including the variation selector on `✂️` and `⚠️`
(the wide colored forms, not the narrow text `✂︎`/`⚠︎`) — mixing presentations makes column widths jump.

---

## §Archive-glyph — archive recommendation column

Render directly from the `archive-class` field — `safe` → `🗄️ safe`, `keep` → `⚠️ keep?`, empty →
`—` (a §Jira-Done promotion is `safe` only after §Retention passes). `safe` is low-regret (superseded / merged / done);
`keep?` is higher-regret (abandoned / branch gone with no merge evidence).

---

## §Cells — compact table cells

Wide tables make Claude Code fall back to per-row key/value cards, and Pi wraps their cells. Keep
handoff tables rendered by `/handoffs` and `/handoffs-tidy` within about **150 display columns**
including borders; the workspace-member table's extra Repo column may reach about 160 in the worst
case. Both stay one line per row in a ~180-column terminal.

Shorten a value only when it exceeds its cap: keep its first `cap − 1` characters and append one
`…`. A tail ellipsis keeps the branch type and ticket key that distinguish rows.

| Cell | Cap | Example |
|------|-----|---------|
| Branch | 24 | `feat/ABC-123-fix-silent…` |
| Where label | 14 | `✅ shared-old-c…` |
| Superseding slug in Status | 16 | `⏩ by abc-456-refineme…` |

Never shorten Date, Repo, Slug (the pick key), or the rest of a Status/Archive glyph. Emoji
presentation rules above still apply.

**Where** combines worktree existence and location: `✅` when `exists=Y`, `✂️` when `exists=N`,
then an optional label from the recorded cwd basename:

- `here` when the cwd matches pwd.
- No label when the basename names the repo's main checkout (current-repo root or `{member-path}`
  basename) or appears case-insensitively in the branch name (a branch-derived worktree).
- `worktrees root` when the cwd ends in `/` under `worktrees/`; `—` alone when the cwd is empty.
- Otherwise the basename, capped as above.

Full values are never lost: picker descriptions carry the full branch and cwd, archive prompt
descriptions carry the full superseding slug and reason, and loading renders the handoff verbatim.

---

## §Archive-flow — the opt-in archive cleanup

Skip entirely only if `current_repo_superseded == 0`, `current_repo_stale == 0`, **and** §Jira-Done
promoted no older row to `safe`. The script counters cannot include model-side Jira results, so an
older promotion is itself an effective Done candidate even when both counters remain zero. A recent
Jira-Done status is retained and does not open this flow.

Archiving **moves** handoffs to `~/.agents/handoffs/archive/` (still on disk, still greppable; just
out of the active listing). It is opt-in and never automatic — rows stay pickable until the user says so.

The candidates split by regret — the `archive-class` field already encodes which is which. Present
them as **distinct groups** and be honest about the difference:

- **Superseded** (`archive-class=safe`, `superseded-by` non-empty) — a newer handoff in this repo continues the thread. Low regret: the context lives on in the newer file.
- **Done** (`archive-class=safe`, not superseded — Status `✅ PR merged`, `✅ done (beads closed)`, `✅ done ({KEY} done)`, or `🔵 merged`) — the work shipped: the PR landed, every referenced bead is closed, the ticket is Done, or the branch tip is in the default branch. Low regret. This is the group that catches finished trunk work and trunk-parked PR handoffs that used to masquerade as `🟢 live`.
- **Stale** (`archive-class=keep` — Status `🚫 PR closed` or `⚪ branch gone`) — abandoned, and *no newer handoff supersedes it*. Higher regret: this may be the **only** record of that thread. Default to leaving these unless the user is sure.

A row is **never** a candidate while its PR is open (`🟠`) — that's live work. A recent row is also
never a candidate unless it is superseded; completion and stale signals remain visible in Status but
receive no archive glyph until §Retention passes with a trustworthy completion clock. A row that is both superseded and otherwise
archivable belongs in the Superseded group (supersede is the safest reason to archive).

Prompt with `AskUserQuestion` (multiSelect). One option per candidate, labelled `{date} {slug}`,
described by its group:

- superseded → `⏩ superseded by {newer-slug} ({humanised reason})`
- done → `✅ PR #{pr-number} merged` / `✅ beads closed` / `✅ {KEY} done` / `🔵 branch merged`
- stale → `🚫 PR #{pr-number} closed — no newer handoff` / `⚪ branch gone — no newer handoff`

> Archive these to `~/.agents/handoffs/archive/`? They stay on disk (greppable), just out of the
> picker. **Superseded** and **done** ones are safe — the context lives on or the work shipped.
> **Stale** ones may be the only record of an abandoned thread, so leave any you might still want.

For the selected filenames, archive them in one call:

```bash
~/.agents/skills/handoffs/scripts/archive.sh {file1} {file2} …
```

Parse the script's `---ARCHIVED---` / `---SKIPPED---` sections and confirm:

```markdown
✅ Archived {N} handoff(s) to `~/.agents/handoffs/archive/`.
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

Cap Branch and Status cells per §Cells.

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
filenames and is repo-agnostic — it only ever moves files within `~/.agents/handoffs/`). Parse
`---ARCHIVED---` / `---SKIPPED---` and confirm exactly as §Archive-flow does, naming the repos:

```markdown
✅ Archived {N} handoff(s) from {repo-list} to `~/.agents/handoffs/archive/`.
```

Never offer a member row that is `🟢 live`, `🟠 PR open`, or `unknown` in this evidence-backed flow.
Old unknown rows may be offered separately, unchecked, by §Age-review-members.

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
are older than `---STALE-DAYS---` (the retention period by default, configurable with `--stale-days N`).

Run this after §Jira-Done. Exclude **every** Jira-Done row, including retained Done rows with empty
archive class; only expired `safe` ones enter the Done archive group. Present the remaining rows as a separate assisted group, never mixed into
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

---

## §Age-review-members — assisted review for old workspace-member rows

Workspace-member rows can have the same missing-signal state as current-repo rows. Hiding them at the
workspace root forces the user to discover and enter each member repo before they can tidy old context.
`list.sh` therefore sets `needs-age-review=Y` for member rows using the same classifier as §Age-review
and counts them in `workspace_member_age_review`.

Run this after §Jira-Done and §Archive-flow-members when member rows still have `needs-age-review=Y`
after the Jira overlay; exclude retained Jira-Done rows even if the raw counter is nonzero. This remains distinct
from the evidence-backed member archive flow: every row has an empty `archive-class`, age is not a
done signal, and no option is preselected.

```markdown
## 🕰️ Old workspace-member handoffs worth a look ({count})

These member handoffs are older than {stale-days} days, have unknown branch liveness, no usable PR
signal, and no resolvable beads. Age is only a reason to ask; skip anything still waiting on work.

| Repo | Date | Slug | Jira | Evidence |
|------|------|------|------|----------|
```

- **Repo**: `{member-display}`.
- **Jira**: `{jira-field}`, or `—`.
- **Evidence**: `no usable PR signal · no resolvable beads · >{stale-days}d`.

Prompt per member repo with `AskUserQuestion` using `multiSelect`, batching at most four rows per
question. Label each option `{date} {slug}` and describe it as `>{stale-days}d · Jira:
{jira-field-or-dash}`. Leave every option unselected:

> Archive any old handoffs for `{repo}` that you no longer need? Age is not a done signal; leave
> parked or uncertain threads untouched.

Collect explicit selections across member repos and archive them in one `archive.sh` call. Parse and
report `---ARCHIVED---` / `---SKIPPED---` exactly as §Archive-flow-members does, then drop archived
rows from any later table or picker. Skipping is silent. Never move these rows into `archive-class`,
never include them in the safe-member bulk choice, and never auto-archive them.
