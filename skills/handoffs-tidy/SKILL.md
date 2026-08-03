---
name: handoffs-tidy
description: Prune handoffs that no longer point at live work — superseded, done, stale, or old and wholly unclassified — and archive only what you confirm so the /handoffs picker stays focused. Archives, never deletes.
allowed-tools: "Bash(~/.agents/skills/handoffs/scripts/list.sh:*), Bash(~/.agents/skills/handoffs/scripts/archive.sh:*), Read, AskUserQuestion, mcp__jira__jira_get"
model-tier: standard
model: sonnet
effort: low
version: "0.5.0"
author: "flurdy"
---

# Handoffs-tidy — retire handoffs that no longer point at live work

Keep `~/.claude/handoffs/` focused on **live** threads. Handoffs go stale three ways, and the
common one isn't supersede:

- **Superseded** — a newer handoff continues the same thread (same branch / topic / same-day re-wrap).
- **Done** — the work shipped: its PR merged, every referenced bead is closed, the branch landed, or
  its Jira ticket is Done. These are usually **never re-wrapped**, so nothing supersedes them — they
  just sit in the picker looking `🟢 live` until you notice the work is long gone.
- **Stale** — abandoned: the PR was closed unmerged, or the branch is gone with no merge evidence.
- **Old and signal-less** — unknown branch liveness with no usable PR signal or resolvable beads. Age only earns an assisted
  question; it never makes the handoff an automatic archive candidate.

This command finds all four and archives the ones you confirm. A recent handoff is retained even when
finished or stale; superseded rows are the sole immediate exception. Nothing is deleted — archived
files move to `~/.claude/handoffs/archive/` and stay greppable.

Run it **ad-hoc** whenever the picker feels noisy, or right after a `/wrap-up`. It is the standalone
twin of `/handoffs`'s opt-in archive step (§3b): same `list.sh` classification, same archive flow —
shared verbatim via `REFERENCE.md` — but with no full table, no picker, and no resume step. It only
ever offers candidates; it never touches a live or open-PR row.

> **Earlier versions only found _superseded_ handoffs** (it ran `list.sh` with no flags and looked at
> one field). That's why it rarely found anything — supersede is the narrowest signal. From v0.2.0 it
> runs the full liveness pass, so finished-but-never-re-wrapped handoffs finally surface.

## When to use

- After a `/wrap-up` whose handoff continued an earlier thread, or whose work has now shipped.
- Periodically, when `/handoffs` shows entries you've moved past — merged PRs, closed beads, dead branches.
- Not needed if you keep only one live handoff per topic and archive as you go.

## Instructions

> **MUST use the helper scripts.** Never construct ad-hoc `ls`/`grep`/`git`/`gh`/`bd` pipelines
> against `~/.claude/handoffs/` — they bypass the per-script permission allowlist and miss the
> repo-matching and liveness logic. Classification and the archive flow are specified **once** in
> `~/.agents/skills/handoffs/REFERENCE.md`; read it rather than re-deriving the rules here, including
§Age-review for old rows with no usable signals.

### 1. Load the shared spec

`Read` `~/.agents/skills/handoffs/REFERENCE.md`. It defines how to read `list.sh`'s output, classify
each row, and run the archive flow — the same definitions `/handoffs` uses, so the two never drift.

### 2. Run the lister with liveness

```bash
~/.agents/skills/handoffs/scripts/list.sh --check-branches [--stale-days N]
```

Forward `--stale-days N` when the user supplied it; otherwise let the script match the age-review
floor to the recent window (3 days, or 4 on Tuesday). Shorter values are clamped to that window. The
threshold only controls the assisted age-review group and never changes `archive-class`.

`--check-branches` is what makes this command capable: it fills `branch-state` and (when `gh` is
present) `pr-state`, so the script can mark merged PRs, landed branches, and closed PRs. Bead-closure
(`beads-done`, keyed off the `**Deliverable:**` field when present) and supersede are computed
regardless. See REFERENCE §Run and §Fields for the flag semantics and the 22-field line format.
Degrades cleanly offline (REFERENCE §Run / the failure modes below).

Parse the `---HANDOFFS---` lines and the `---SUMMARY---` counts. For each current-repo row, derive its
**Status** (REFERENCE §Status) and **archive-class** (`safe` / `keep` / empty — REFERENCE §Fields).
Also note rows with `needs-review=Y` (step 5b) and `needs-age-review=Y` (step 5c) — both are
assisted judgement groups, never automatic archive candidates.

### 3. Resolve Jira-Done (optional)

Follow REFERENCE §Jira-Done for any current-repo row without another done/stale/supersede signal that names a Jira ticket. This catches
handoffs whose *only* finished signal is a closed ticket (no merged PR, no closed beads). It's gated
exactly as REFERENCE describes and degrades silently if the Jira MCP isn't configured — skip it freely
if you want to stay network-light; PR/bead/branch/supersede classification still stands.

### 4. Present the candidates

If `current_repo_superseded == 0` **and** `current_repo_stale == 0` **and** §Jira-Done promoted no
older row to `safe` **and** no row has `needs-review=Y` **and** no row has `needs-age-review=Y` **and** no
member row is
archivable (step 5d's gate), report
nothing and stop at step 6 — the picker is already tidy:

```markdown
_No archivable handoffs — remaining rows are live, unknown, or still inside the recent grace window._
```

> **Check step 5d's gate before stopping.** In a multi-repo workspace the current repo can be
> perfectly tidy while its members hold many finished handoffs — member rows deliberately never feed
> `current_repo_stale`. Stopping on the current-repo counts alone reports "nothing to tidy" while
> archivable handoffs sit one level away, which is precisely the blind spot this command exists to
> close. When only member candidates exist, skip to step 5d rather than stopping.

If there are auto-classified candidates, render them as a table, grouped by regret (REFERENCE
§Archive-flow defines the groups). When only an assisted flag is present, skip straight to step 5b
for `needs-review` or step 5c for `needs-age-review`.

```markdown
## 🗂️ Archive candidates ({count})

| Archive? | Date | Slug | Branch | Status | Group |
|----------|------|------|--------|--------|-------|
```

- **Status**: the §Status glyph for the row.
- **Group**: `Superseded` / `Done` / `Stale`. A row that is both superseded and otherwise archivable
  goes in **Superseded** (the safest reason to archive). Order the table Superseded → Done → Stale.
- **Archive?**: pre-suggest `✅` for `safe` (Superseded, Done) and leave `☐` for `keep` (Stale) —
  Stale rows may be the only record of an abandoned thread.

### 5. Confirm + archive

Run the archive flow exactly as REFERENCE §Archive-flow specifies: prompt with `AskUserQuestion`
(multiSelect, one option per candidate, grouped and described per that section), then archive the
selected filenames in one `archive.sh` call and parse `---ARCHIVED---` / `---SKIPPED---`. Pre-check
`safe` candidates; leave `keep` unchecked. Surface every `---SKIPPED---` line verbatim with its
reason. Never offer a `🟢 live`, `🟠 PR open`, or `unknown` row. `archive.sh` only moves — never deletes.

```markdown
✅ Archived {N} handoff(s) to `~/.claude/handoffs/archive/`.
```

### 5b. Trunk handoffs worth a look (assisted)

If any current-repo row has `needs-review=Y`, run the assisted prompt per **REFERENCE §Trunk-review**
— a separate, clearly-labelled prompt (not mixed into the step-5 groups) for legacy trunk-parked
handoffs the script couldn't auto-classify: partial bead closure (`beads-progress` like `1/4`), no
`**Deliverable:**` marker, so it can't tell finished own-work from never-closing context. Present the
`{beads-progress}` and bead list per row and let the user decide; archive any they confirm via the
same `archive.sh` call. Skip entirely when no row is flagged. This prompt goes quiet on its own as
old handoffs age out and new ones carry `**Deliverable:**`.

### 5c. 🕰️ Old handoffs with no completion signal

If any current-repo row still has `needs-age-review=Y` after §Jira-Done promotion, run the assisted
prompt exactly as **REFERENCE §Age-review** specifies. Keep it separate from the safe/done/stale and
§Trunk-review groups. Age is not evidence of doneness: leave every option unselected, make skipping
trivial, and archive only filenames the user explicitly confirms. Skip when no row is flagged.

### 5d. 🧱 Workspace-member handoffs

Run the member archive flow exactly as **REFERENCE §Archive-flow-members** specifies, after the
current-repo steps. In a multi-repo workspace, member repos are where finished handoffs accumulate —
the root itself often holds one or two.

Read the member rows from `---WORKSPACE-MEMBER-HANDOFFS---` (24 fields: the usual 22 plus
`{member-display}|{member-path}`) and the per-repo totals from `---WORKSPACE-MEMBER-REPOS---`.
Classify each with the same §Status / §Archive-glyph rules as current-repo rows — member rows are
already classified against their own repo when `--check-branches` was passed.

Key points from that section, so they aren't missed:

- **Gate**: `--check-branches` was passed, and at least one member row is `archive-class=safe`; recent non-superseded member rows have an empty class and are not offered.
- **Only `safe` rows are offered from here.** `keep`-class member rows (PR closed unmerged, branch
  gone with no merge evidence) are higher-regret — name them and point at `cd {path} && /handoffs-tidy`
  rather than offering them.
- **One question per member repo**, not one per candidate — `AskUserQuestion` caps at 4 options and a
  single repo can hold more candidates than that.
- Archive every selection across repos in **one** `archive.sh` call; it takes bare filenames and is
  repo-agnostic.

Skip the step entirely when the gate doesn't pass.

### 6. Done

If nothing was archivable or reviewable (steps 4–5d), or the user selected none, say so plainly and stop. This command
never touches live work and never deletes — at worst it's a no-op.

## Failure modes

- **`list.sh` / `archive.sh` / `REFERENCE.md` missing** (handoffs skill not installed): say so plainly
  and stop — this command is a thin driver over the handoffs skill's scripts and shared spec.
- **No `~/.claude/handoffs/` directory**: nothing to tidy; say so and stop.
- **Not in a git repo**: liveness needs a repo to classify against — say so and stop. (`cd` into the
  repo and re-run.)
- **Multi-repo workspace**: member repos are covered by step 5d, but only their `safe` rows. Anything
  needing judgement (`keep`-class, trunk-review) still requires `cd`ing into that member and re-running.
- **Offline / remote unreachable**: `branch-state` degrades to local-only (`merged` still detected
  against the local default tip; no false `gone`). The Done/Stale groups just shrink. Don't retry.
- **`gh` missing, unauthenticated, or timed out**: `pr-state` reports `unknown` and classification
  falls back to `branch-state` + `beads-done`. No error, no retry. Squash-merged branches may show as
  `⚪ branch gone` (`keep?`) rather than `✅ merged` (`safe`) unless a closed bead or Jira-Done marks them done.
- **`bd` missing or no `.beads/`**: `beads-done` is always empty — finished work then relies on
  PR/branch/supersede (and §Jira-Done) signals alone.
- **Jira MCP missing or errors**: step 3 is skipped silently; PR/bead/supersede classification stands.
