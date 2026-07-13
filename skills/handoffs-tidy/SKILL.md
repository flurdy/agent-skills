---
name: handoffs-tidy
description: Prune handoffs that no longer point at live work — superseded (a newer handoff continues the thread), done (PR merged, all beads closed, branch landed, or Jira ticket Done), or stale (branch gone / PR closed) — and archive them so the /handoffs picker stays focused. Read-only until you confirm; archives (never deletes).
allowed-tools: "Bash(~/.claude/skills/handoffs/scripts/list.sh:*), Bash(~/.claude/skills/handoffs/scripts/archive.sh:*), Read, AskUserQuestion, mcp__jira__jira_get"
model-tier: standard-coding
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
model: sonnet
effort: low
version: "0.3.0"
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

This command finds all three and archives the ones you confirm. Nothing is deleted — archived files
move to `~/.claude/handoffs/archive/` and stay greppable.

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
> `~/.claude/skills/handoffs/REFERENCE.md`; read it rather than re-deriving the rules here.

### 1. Load the shared spec

`Read` `~/.claude/skills/handoffs/REFERENCE.md`. It defines how to read `list.sh`'s output, classify
each row, and run the archive flow — the same definitions `/handoffs` uses, so the two never drift.

### 2. Run the lister with liveness

```bash
~/.claude/skills/handoffs/scripts/list.sh --check-branches
```

`--check-branches` is what makes this command capable: it fills `branch-state` and (when `gh` is
present) `pr-state`, so the script can mark merged PRs, landed branches, and closed PRs. Bead-closure
(`beads-done`, keyed off the `**Deliverable:**` field when present) and supersede are computed
regardless. See REFERENCE §Run and §Fields for the flag semantics and the 21-field line format.
Degrades cleanly offline (REFERENCE §Run / the failure modes below).

Parse the `---HANDOFFS---` lines and the `---SUMMARY---` counts. For each current-repo row, derive its
**Status** (REFERENCE §Status) and **archive-class** (`safe` / `keep` / empty — REFERENCE §Fields).
Also note rows with `needs-review=Y` — trunk-parked legacy handoffs the script couldn't auto-classify
(step 5b).

### 3. Resolve Jira-Done (optional)

Follow REFERENCE §Jira-Done for any still-live current-repo row that names a Jira ticket. This catches
handoffs whose *only* finished signal is a closed ticket (no merged PR, no closed beads). It's gated
exactly as REFERENCE describes and degrades silently if the Jira MCP isn't configured — skip it freely
if you want to stay network-light; PR/bead/branch/supersede classification still stands.

### 4. Present the candidates

If `current_repo_superseded == 0` **and** `current_repo_stale == 0` (after any §Jira-Done promotions)
**and** no row has `needs-review=Y`, report nothing and stop at step 6 — the picker is already tidy:

```markdown
_No archivable handoffs — every handoff for this repo still points at live work._
```

If there are auto-classified candidates, render them as a table, grouped by regret (REFERENCE
§Archive-flow defines the groups). (When the only thing flagged is `needs-review`, skip straight to
step 5b.)

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

### 6. Done

If nothing was archivable (steps 4–5b) or the user selected none, say so plainly and stop. This command
never touches live work and never deletes — at worst it's a no-op.

## Failure modes

- **`list.sh` / `archive.sh` / `REFERENCE.md` missing** (handoffs skill not installed): say so plainly
  and stop — this command is a thin driver over the handoffs skill's scripts and shared spec.
- **No `~/.claude/handoffs/` directory**: nothing to tidy; say so and stop.
- **Not in a git repo**: liveness is current-repo-only, so there's nothing to classify — say so and
  stop. (Cross-repo tidying isn't supported; `cd` into the repo and re-run.)
- **Offline / remote unreachable**: `branch-state` degrades to local-only (`merged` still detected
  against the local default tip; no false `gone`). The Done/Stale groups just shrink. Don't retry.
- **`gh` missing, unauthenticated, or timed out**: `pr-state` reports `unknown` and classification
  falls back to `branch-state` + `beads-done`. No error, no retry. Squash-merged branches may show as
  `⚪ branch gone` (`keep?`) rather than `✅ merged` (`safe`) unless a closed bead or Jira-Done marks them done.
- **`bd` missing or no `.beads/`**: `beads-done` is always empty — finished work then relies on
  PR/branch/supersede (and §Jira-Done) signals alone.
- **Jira MCP missing or errors**: step 3 is skipped silently; PR/bead/supersede classification stands.
