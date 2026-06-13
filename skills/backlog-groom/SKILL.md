---
name: backlog-groom
description: "Per-bead quality audit over the open backlog — flags vague descriptions, missing acceptance criteria, label drift, stale YAGNIs, mis-prioritised nice-to-haves, obvious splits/epics, and duplicates. Read-only sweep that produces a proposal report; mutations apply only on explicit approval, and the dangerous ones (close, supersede, promote, split) are confirmed one at a time. Delegates splitting to /triage and cross-system linking to /tracking-sweep (Jira) or /trello-beads (Trello), calibrating to whichever tracker the project actually uses."
allowed-tools: "Read, Grep, Glob, Task, AskUserQuestion, Bash(bd status:*), Bash(bd list:*), Bash(bd show:*), Bash(bd lint:*), Bash(bd stale:*), Bash(bd find-duplicates:*), Bash(bd children:*), Bash(bd epic:*), Bash(bd label:*), Bash(bd priority:*), Bash(bd update:*), Bash(bd note:*), Bash(bd close:*), Bash(bd supersede:*), Bash(bd dep:*), Bash(bd memories:*), mcp__jira__jira_get"
model: sonnet
effort: medium
version: "0.1.0"
author: "flurdy"
---

# Backlog Groom — Per-Bead Quality Audit

Walk the **open backlog** and ask, for each bead: *is this any good?* Flag hygiene, priority, lifecycle, structure, and duplicate problems, propose a concrete fix for each, and **only mutate on explicit approval**.

This is the hygiene counterpart to the intake/reconciliation skills — it is the only one that systematically reads every open bead and improves its quality.

## Relationship to other tools

- **`/triage`** is *forward intake*: prompt/Jira → new bead(s), with dup-check and splitting **at creation time**. The groomer does not create beads from prompts and does not re-implement splitting — when a bead obviously needs splitting, it hands the bead to `/triage`.
- **`/tracking-sweep`** is *cross-system drift* (Jira ↔ beads ↔ PRs), read-only. The groomer does not re-implement cross-system linking — when a bead lacks a Jira/Trello link, it flags it and points at `/tracking-sweep` (or `/trello-beads`).
- **`tracking-auditor`** (agent) is *per-branch*: does THIS diff match its ticket? Unrelated.
- **`/backlog-groom`** (this skill) is *per-bead quality of the backlog itself*: descriptions, labels, priority, lifecycle, structure, duplicates.

If a finding belongs to one of those tools, **delegate — don't duplicate its logic**.

## Usage

```bash
/backlog-groom                 # Read-only sweep of open beads → proposal report. Changes nothing.
/backlog-groom apply           # After showing the report, batch-apply the SAFE proposals on approval;
                               #   destructive ones still confirm one at a time.
/backlog-groom all             # Widen scope to open + ready + blocked (default is open only).
/backlog-groom labels          # Just the DB-wide label-normalisation pass (fast).
/backlog-groom <bead-id> …     # Groom only the named beads.
```

Default is **report-only**. Mutation never happens without either `apply` or a per-finding confirmation.

## Operating rules

- **Read-only until approved.** The sweep (sections 1–7) calls only read commands. No `bd close`, `bd update`, `bd priority`, `bd label add/remove`, `bd supersede`, `bd dep` until the user approves in section 8.
- **Three dispositions per finding — `[fix]`, `[bead]`, delegate.** Most findings are `[fix]` (an edit the gate can apply). A finding that is itself *work* — needs design, policy, or several steps, not a one-shot edit — gets a `[bead]` disposition: **file a tracked bead instead of editing**. The rest delegate to another tool.
  - **Two tiers within `[fix]`.** *Safe* (relabel to a canonical name, bump to P4, append a scaffolded `## Acceptance Criteria` skeleton, add a link-reminder note) may batch-apply under `apply`. *Destructive / judgement-heavy* (close, supersede, promote-to-epic, split, priority bumps **up**) are **always confirmed one at a time**, never batched.
- **File a bead for work, not for edits — and never for spam.** Use `[bead]` only when the gate *can't* fix it in one shot: systemic patterns (e.g. "set a bead-template default so AC stops being missing" for an all-beads lint failure; "consolidate the `foo`/`foos`/`fooing` label taxonomy"), or a decision needing an owner/later. **One bead per pattern, never one per affected bead.** Never file a bead for something inline-fixable (a single relabel, one P4 bump) — that is noise. A finding the user can simply resolve in-session is resolved, not filed.
  - **Route bead creation through `/triage`, not raw `bd create`** — so it gets dedup-checked (won't re-file a hygiene bead a past groom already created), gets proper acceptance criteria, and is labelled `backlog-hygiene`.
  - **Recursion-safe:** because `/triage` gives the new bead AC, it won't trip its own `bd lint` next run; the `backlog-hygiene` label lets future grooms recognise prior suggestions and skip re-filing.
- **Never fabricate scope.** When extending a thin description, add a *scaffold* (the missing section header plus draft bullets derived strictly from the existing title/comments) and mark it for human review. Do not invent acceptance criteria that change what the bead means.
- **Closing is the riskiest verb.** A wrongly-closed bead is invisible afterward. Only ever *propose* a close with a one-line rationale; require explicit per-bead confirmation; close with `bd close --reason="…"` so the judgement is recorded.
- **Don't restate healthy beads.** A bead with a good description, correct labels, sane priority and no duplicate is uninteresting — skip it. A short report is a good report.
- **Delegate, don't duplicate.** Splitting → `/triage`. Cross-system linking → `/tracking-sweep` / `/trello-beads`. Branch-vs-ticket → `tracking-auditor`.
- **Be fast.** This is a sweep. If a single bead needs real investigation, flag it and move on.

## Procedure

Sections 1–6 are read-only data gathering and can be run back-to-back. The default scope is **open** beads; `all` adds ready+blocked.

### 1. Inventory

```bash
bd status                                  # totals, sanity check the DB is reachable
bd list --status=open -n 0                 # the working set (use --all-ish scope per mode)
```

### 2. Hygiene signals (per-bead)

Beads can carry the issue but be cheap to detect — lean on `bd`'s own filters rather than re-deriving:

```bash
bd lint                                    # missing template sections by type:
                                           #   bug → Steps to Reproduce + Acceptance Criteria
                                           #   task/feature → Acceptance Criteria
                                           #   epic → Success Criteria
bd list --empty-description --status=open -n 0
bd list --no-labels --status=open -n 0
```

`bd lint` is the primary "description too vague / incomplete" detector — prefer it over guessing from prose length.

**Collapse universal failures — don't emit one line per bead.** If a single check fails on (nearly) *all* open beads — e.g. every bead is missing `## Acceptance Criteria` — that is a **template/process gap, not 46 individual defects**. Emitting a scaffold proposal per bead would bury every other finding in noise. Instead, report it once as a systemic observation ("N/N beads missing AC — set a bead template default rather than scaffolding each") and only call out the *individual* beads that have an **additional** problem (empty description, no labels, also a YAGNI). Rule of thumb: if a hygiene check fails on >~70% of scope, summarise it; below that, list the beads.

### 3. Label-normalisation signals (DB-wide)

```bash
bd label list-all
```

Scan the label list for:
- **Near-duplicate labels** — singular/plural or stem variants pointing at the same concept (e.g. `ui-test` / `ui-tests` / `ui-testing`). Propose one canonical form and a relabel of the minority spellings.
- **Malformed labels** — labels containing spaces or punctuation that look like a failed multi-label entry (e.g. a single label `"queue dlq worker"` that should have been three). Propose splitting into separate labels.
- **Singleton labels** — labels on exactly one bead. Often a typo of an existing label, occasionally legitimately new. Flag only as `ℹ️`, never auto-merge.

This pass is independent of the per-bead passes and is the whole of `/backlog-groom labels`.

### 4. Lifecycle & priority signals

```bash
bd stale                                   # not updated in 30+ days
```

For each stale bead and each P3/P4 bead, judge (conservatively) whether it reads as:
- **already done** — the work it describes appears shipped (cross-check git log / closed siblings) → propose close,
- **YAGNI** — speculative, no longer plausibly worth doing → propose close with reason,
- **a genuine nice-to-have** still worth keeping → propose bump to **P4** (down only; never auto-raise priority),
- **still valid** — leave it.

Do not close anything in this section — only record proposals.

### 5. Structure signals

- **Obvious split** — a title joining unrelated work with `+`, `&`, `and`, `,`, or a description listing independent deliverables → propose handing the bead to `/triage` to split. Do not split here.
- **Promote-to-epic** — a single bead that has visibly grown into a multi-bead programme → propose `bd promote` / converting to an epic and parenting the pieces. Confirm per-bead.
- **Orphaned epic children** — use `bd children <epic>` / `bd epic` to spot child beads whose parent is closed or missing → propose re-parent or close.

### 6. Duplicate signals

```bash
bd find-duplicates --status open                 # mechanical (free); --method ai for semantic
bd find-duplicates --status open --threshold 0.4 # widen if the default 0.5 finds nothing
```

For each pair, propose `bd supersede` (keep the better-described one) or `bd duplicate` — never auto-merge; confirm per-pair.

### 7. Cross-system linkage (detect the regime, then flag-and-delegate)

Beads integrate with **either** Jira **or** Trello depending on the project, and the *meaning of a missing link differs* between the two. Don't assume Jira. First **detect the regime** from how open beads are actually linked, then calibrate.

A bead is **Jira-linked** if it carries the `jira` label or its title/description contains a `[A-Z]+-[0-9]+` key (same heuristic as `/tracking-sweep`). It is **Trello-linked** if it carries the `trello` label or a Trello card URL/short-link.

Measure linkage density across open beads:

```bash
bd list --status=open -l jira -n 0   | grep -cE '^[○◐●]'   # jira-linked count
bd list --status=open -l trello -n 0 | grep -cE '^[○◐●]'   # trello-linked count
```

Then:

- **Jira-dominant regime** (most open beads are jira-linked — typical of Jira-managed projects, where nearly every bead maps to a ticket): an **unlinked** bead is a genuine anomaly → `⚠️` "No Jira link in a Jira-tracked backlog — create/link a ticket via `/tracking-sweep`." Optionally verify a referenced key still exists / isn't Done:
  ```
  mcp__jira__jira_get  path: /rest/api/3/issue/{KEY}  jq: "{status: fields.status.name}"
  ```
- **Trello-partial regime** (only *some* beads are trello-linked, no jira labels — typical of these local projects, where Trello covers a subset on purpose): an unlinked bead is **expected, not a finding**. Do **not** flag missing links here. Only surface a Trello note if a linked card looks closed/missing → delegate to `/trello-beads`.
- **No tracker** (no jira and no trello labels anywhere): skip this section entirely — beads-only project.

Do **not** create Jira issues, Trello cards, or write links here. Detect, calibrate, and point at `/tracking-sweep` (Jira) or `/trello-beads` (Trello).

### 8. Render the proposal report

Group by grooming dimension, not by bead. Every line is a *proposal* with a concrete command-shaped action and a one-line rationale. Tag each `[safe]` (batch-fixable), `[confirm]` (fix one-at-a-time), or `[bead]` (file as tracked work via `/triage`).

```markdown
## Backlog Groom — {YYYY-MM-DD HH:MM}

**Scope:** {N} open beads · {W} lint warnings · {S} stale · {D} duplicate pairs · {L} label issues
_Read-only. Nothing changed. Re-run with `apply` to action the safe proposals._

### ✍️  Hygiene — thin / incomplete ({count})
- _Systemic: {W}/{N} open beads missing `## Acceptance Criteria` — a template gap, not {W} edits._
  → `[bead]` file one bead via `/triage`: set a bead-template default so new beads include AC.
- **myrepo-def** [bug] — empty description, missing Steps to Reproduce (in addition to the systemic gap).
  → `[confirm]` draft repro skeleton; needs human detail before it's actionable.

### 🏷  Labels ({count})
- `ui-test` (6) / `ui-tests` (18) / `ui-testing` (10) — three spellings, one concept.
  → `[confirm]` canonicalise to `ui-tests`; relabel the other 16 beads.
- `"queue dlq worker"` (1) — malformed multi-word label.
  → `[safe]` split into `queue` + `dlq` + `worker`.

### 📉  Priority & lifecycle ({count})
- **myrepo-ghi** [P3, 84d stale] — speculative, no movement since creation.
  → `[confirm]` close as YAGNI (`bd close --reason="YAGNI — speculative, 84d no activity"`).
- **myrepo-jkl** [P2] — genuine nice-to-have, not blocking anything.
  → `[safe]` bump to P4.
- **myrepo-mno** — work appears shipped in {commit/closed sibling}.
  → `[confirm]` close as done.

### 🧱  Structure ({count})
- **myrepo-pqr** — title bundles 3 independent deliverables.
  → `[confirm]` hand to `/triage` to split.
- **myrepo-stu** — grown into a programme of work.
  → `[confirm]` promote to epic and parent the pieces.

### 👯  Duplicates ({count})
- **myrepo-vwx** ↔ **myrepo-yz01** (0.71 similar).
  → `[confirm]` supersede `myrepo-yz01` (thinner) by `myrepo-vwx`.

### 🔗  Cross-system (delegate) ({count})
- _Jira-dominant regime ({J}/{N} beads linked)._ **myrepo-2345** — no Jira link, anomalous here.
  → _Run `/tracking-sweep` to reconcile / link._ (not actioned here)
- _Trello-partial regime ({T}/{N} beads linked) — missing links expected, not flagged._

---
**Summary:** {X safe proposals} · {Y confirm-each} · {B beads to file} · {Z delegated}
**Next:** re-run `/backlog-groom apply` to action the safe set, or pick a `[confirm]`/`[bead]` item.
```

Skip empty sections. If nothing needs grooming:

```markdown
## Backlog Groom — {YYYY-MM-DD HH:MM}
✅ Backlog is clean — {N} open beads, no hygiene/label/priority/duplicate issues found.
```

### 9. Apply (only with `apply`, or on per-finding confirmation)

1. **`[fix]` safe set** — present the safe proposals together via `AskUserQuestion` (approve all / pick subset / none). On approval run the corresponding commands:
   - relabel → `bd label add` / `bd label remove`
   - bump down → `bd priority <id> 4`
   - scaffold description → `bd update <id> --description="…"` (or `bd note`), preserving existing content and appending the drafted section
2. **`[fix]` confirm-each set** — for every confirm proposal, show the bead and the exact command, and ask per-item. Never batch closes, supersedes, promotions, or splits.
   - close → `bd close <id> --reason="…"`
   - supersede → `bd supersede <new> <old>` (confirm direction)
   - split → invoke `/triage <id> break into subtasks` rather than splitting inline
3. **`[bead]` set** — for each systemic/work finding, confirm per-item, then file **one** bead via `/triage` describing the fix (e.g. `/triage Set a bead-template default so new beads include Acceptance Criteria` or `/triage Consolidate contract-test* label taxonomy across 16 beads`). Let `/triage` handle dedup, AC, and the `backlog-hygiene` label — do not `bd create` directly. Offer this as the fallback for any `[fix]` confirm-item the user wants to defer rather than action now.
4. After applying, print a short ledger of what changed (id, action), what beads were filed (new id, title), and what was skipped.

## Failure modes

- **No beads (`bd` missing or no `.beads/`)**: report `_No beads database found — nothing to groom._` and stop.
- **`bd lint` / `bd find-duplicates` unavailable** (older `bd`): skip that section, note it, run the rest.
- **No Jira MCP**: skip the optional key-existence check in section 7; still flag unlinked beads as `ℹ️`.
- **Large backlog (>~100 open)**: run the DB-wide passes (labels, stale, lint) in full but cap the per-bead prose judgement to the highest-priority N; `log` how many were not individually judged so the user knows coverage wasn't total.
