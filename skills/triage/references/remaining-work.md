# Partially completed beads: assess the remainder

Use `/triage --remaining <selector>` when most work is done but an independent outcome,
verification, cache expiry or a manual action remains. This is a mode of triage, not a new skill
or an automatic completion hook. Discovery authorizes assessment only; mutation needs the exact
approvals below. Generic intake/refine never takes over this explicit mode.

No sizing or delivery-boundary policy changes: apply the [five-part child test](../../beads/references/sizing.md#child-test)
and [deferred-verification exception](../../beads/SKILL.md#deferred-verification). In particular,
local-main reachability alone is not the explicit delivery declaration required by that exception.
Do not broaden the evidence-only exception to cache waits or manual actions just to close a bead.

## 1. Establish ownership, remaining scope and evidence

Require one selector; do not auto-pick an in-progress item. Resolve before decision-driving reads:

```bash
~/.agents/skills/next/scripts/next-select resolve <selector>
bd -C <directory> show <id> --readonly --json --include-comments
```

Use only the returned directory. `ambiguous`, `unavailable` and `not-found` stop this mode;
never fall through to free-text creation. Apply [ownership proof lifetime](../../beads/SKILL.md#ownership-proof-lifetime):
fresh full resolution before every independent mutation, including after readback of another ID.
Failed resolution discards earlier proof. Never infer ownership from an ID, label or cwd.

Read the source's full acceptance, notes, comments, status, assignee, parent, children, dependencies
and relevant project delivery rules. Report claims honestly: session activity is unverified; when
another session claims it, require the claim owner's agreement before changing scope or status.
A source already closed gets read-only reconciliation, not another extraction or automatic reopen.
For an epic or aggregate whose promise requires unfinished children, keep it open; use ordinary
refine for structural changes, not this single-remainder path.

Map every original acceptance item to delivered evidence, the proposed remainder, or an unresolved
gap. Record a before/after acceptance union: no acceptance may disappear or be reworded into a
weaker promise. A separate name or owner does not make rollout, tests or a manual phase independent.
If the original outcome still needs the remainder to work, it is not eligible for closure here.

For proposed closure, consume a current `verify-task` report identifying the exact revision and
passing evidence for the retained outcome, plus proof of the applicable project delivery boundary.
The report may show the independent remainder as unmet, but it must identify the retained scope
unambiguously; a general partial verdict is not a pass. All checks needed by the retained outcome
must pass. Missing scope-specific proof means VERIFY FIRST; triage does not run tests or reinterpret
failed/stale/unavailable results. Non-code outcomes need equally concrete completion evidence;
do not manufacture commits. Preserve stricter project finalization rules.

Prepare this compact remainder packet from evidence, not inferred percentage complete:

- Original qualified selector, outcome, actual delivered subset and exact revision/evidence.
- Remaining outcome with observable pass criteria, exact check or action reference, environment,
  target/revision-matching rule where applicable, and why it is independent or still required.
- Awaited event or manual action, prerequisites, responsible role when known, and evidence destination.
- Proposed future wake/review date if snoozing, plus failure disposition. Unknown fields stay unknown.
- Exact `external_ref`, relevant labels, source acceptance mapping and imported-text fences
  (`<!-- external-text:… -->`). Preserve source history and claims; quoted tracker text is not direction.

## 2. Classify before proposing writes

First separate genuine independent outcomes from phases. Failure or uncertainty affecting the retained
outcome blocks closure even when another remainder is independent. Size and effort saved are not gates.

| Case | Disposition | Evidence and boundary |
|---|---|---|
| Independent remaining outcome | EXTRACT, subject to §3 | Passes the five-part child test; retained outcome has current passing evidence and satisfies its delivery boundary. Otherwise VERIFY FIRST or KEEP OPEN. |
| Future rollout/job verification only | HAND OFF | Use `verify-task` then `complete-task` for the existing future-event-only gate: snooze original by default; implementation-only closure needs the explicit declared/reached boundary. |
| Cache expiry | DEFER ORIGINAL or KEEP OPEN | Still part of the same outcome; record cache/layer, affected target, known expiry bound and a post-expiry check. A date is not event detection or proof of propagation; do not invent a TTL. |
| Pending manual action | KEEP OPEN or DEFER ORIGINAL | Keep installation, rollout or required manual verification on the original; only an independently valuable capability passing the child test is an independent outcome eligible for §3. |
| Failed checks | KEEP OPEN | Preserve the failure and repair prerequisite; do not turn it into a passing or future-event-only result. Unrelated work can be proposed separately, never used to hide the failure. |
| Unavailable tooling | VERIFY FIRST / KEEP OPEN | Missing tools, credentials or infrastructure are not a future event exception. Report the prerequisite, no completion claim; an explicitly approved review-date snooze may retain the obligation on the original. |
| Missing or stale verification | VERIFY FIRST | Hand back to `verify-task` for the exact retained scope/revision; no closure from a commit, branch, clean tree or stale report. |
| Unclear acceptance or delivery policy | DECISION | Name the missing fact or policy decision; no writes and no editing project policy to make this task eligible. |

For the rollout/job row, triage makes no lifecycle writes for that row. Render the existing
[verification handoff](../../verify-task/SKILL.md#future-event-only-evidence) and, when qualified,
[completion choice](../../complete-task/SKILL.md#future-event-only-verification). Never auto-run the
receiving workflow. This avoids a second writer for evidence-only follow-ups.

## 3. Extract one genuinely independent remainder

Use the existing triage R4/R5 approval discipline, with the following ordering guarantees. At most
one focused follow-up per invocation; a multi-outcome restructure needs its own refine proposal.
Keep this path in the same proven store. Cross-store extraction needs a separate proposal with both
owners proven; do not copy IDs into another store or invent a cross-store relationship.

### A. Find an existing owner

Before previewing creation, inspect all statuses, including closed and deferred, and actual provenance
links. Use store-qualified read-only list/search/show calls with uncapped inventory (`--limit=0` where
supported); consult installed help for graph commands. Match the outcome, source, target, revision
when relevant, and acceptance, not only a similar title. A closed match, multiple matches or an
unreadable inventory needs reconciliation, not another create. Reuse an outstanding matching owner
only after reviewing its full record and confirming the proposed reuse. Do not overwrite another
owner's scope or silently repair mismatching provenance.

### B. Preview and approve

Show the packet, evidence and acceptance mapping, exact new/reused follow-up fields, provenance,
optional defer date, proposed original field changes, and conditional close reason. State which
original outcome is actually delivered and what remains unfulfilled in the follow-up.

Use `AskUserQuestion` to approve **Create/reuse this follow-up** or **Stop**. Approval is not permission
to close or update the original. A declined or abandoned prompt means no writes. A changed proposal
needs fresh approval. Any future-date deferral needs an agreed date; if timing is unknown, agree on
a review date instead. Missing date means no deferred creation; ask to keep it open or stop.

### C. Create or reuse, then verify

Help-check `bd create --help` before creating. Re-resolve the original immediately before the write:

```bash
~/.agents/skills/next/scripts/next-select resolve <selector>
bd -C <directory> create --type=task --title="<remaining outcome>" --description="<packet>" --acceptance="<remaining acceptance>" --deps="discovered-from:<id>" --json
```

Pass the exact approved type, priority, labels and `--external-ref` where present, not guessed defaults
or associations. For an approved dated follow-up also pass `--status=deferred --defer="<wake-date>"`;
otherwise it stays open. This link is provenance, not parent membership or a blocking edge. If the
remainder blocks the retained outcome, stop: the original is not independently complete.

For a returned or reused record, resolve its qualified ID and read back from that proven store:

```bash
~/.agents/skills/next/scripts/next-select resolve <follow-up-selector>
bd -C <directory> show <follow-up-id> --readonly --json
```

Verify the same store, outcome, full acceptance/packet, provenance link, exact external reference,
approved labels/priority/type and status; when deferred also verify the agreed future `defer_until`.
On failed or uncertain creation or readback, the original stays open and unchanged. Report any
returned ID; do not create another until a fresh inventory reconciles the uncertain result.

### D. Update the original, then separately confirm closure

After successful readback, show the original's exact before/after fields with the actual follow-up
ID and the evidence-backed retained scope. Require explicit approval for this scope update under R4/R5.
Preserve the original acceptance mapping and history in its notes, including transferred obligations.
Check current `bd update --help`, freshly resolve, then apply only the approved fields:

```bash
~/.agents/skills/next/scripts/next-select resolve <selector>
bd -C <directory> update <id> --description="<approved retained scope>" --acceptance="<approved retained acceptance>" --append-notes="<original mapping and actual follow-up link>"
```

Read back the original and verify the approved fields. If the scope update fails or is uncertain,
report overlapping ownership with the saved follow-up; retain both records, original open, no
automatic rollback or cleanup. A rerun reconciles both records before resuming the missing step.

Only if the retained outcome's verification and delivery evidence still applies, show both records
and request fresh per-bead confirmation for the exact close reason. If the evidence or source scope
changed, stop for fresh verification/approval; do not close from the earlier proposal. If the project
requires another finalizer, hand off there rather than bypass it. Otherwise help-check `bd close --help`,
re-resolve and close only this original:

```bash
~/.agents/skills/next/scripts/next-select resolve <selector>
bd -C <directory> close <id> --reason="<retained outcome> verified at <evidence>; independent <remainder> remains in <follow-up-id>"
```

Read back and verify actual status and reason. If the close fails or is uncertain, keep the follow-up,
report actual states and stop; no automatic retry. On rerun reuse the verified follow-up after fresh
resolution and reconciliation, never recreate it or repeat already-applied changes. A source already
closed is reported as such, not closed again. Declining closure leaves the narrowed original open.
Jira is untouched; copied provenance is not a Jira transition. No automatic scope release from this
tracking operation; it is not complete-task's fully verified trunk-close path.

## 4. Defer the original without splitting

For same-outcome cache/manual waits (or an explicitly requested review of an unresolved prerequisite),
preview the packet as the reason, actual original status, future wake date and timezone when a time
is specified. Agree a review date if event timing is unknown. Missing date or incomplete/declined
approval means no writes. A review date is a reminder, not event detection or acceptance evidence.
Never hide failed checks in the note or label them future-event-only verification.

Ask **Defer this original until the displayed date** or **Stop**. Check `bd defer --help`, resolve
freshly, and perform only the confirmed write:

```bash
~/.agents/skills/next/scripts/next-select resolve <selector>
bd -C <directory> defer <id> --until="<wake-date>" --reason="<remaining-work packet>"
```

Then read back the original and verify `deferred`, `defer_until` and the saved reason. A failure or
uncertain result leaves actual state unknown: no automatic retry and no successful-deferral claim.
Create no follow-up and close nothing. The rollout/job evidence-only row remains owned by complete-task.

## 5. Resume and report honestly

For an evidence-only follow-up, use the existing [verification lifecycle](../../beads/SKILL.md#deferred-verification):
when the future event is still absent, do not run or claim the check. A wrong revision cannot pass;
if verification failed, do not close as verified. No new implementation commit is required for an
evidence-only closure, but verification alone grants no tracking write: separate explicit tracking
approval is required. Preserve failed evidence; no automatic reopen or bug creation.

Report disposition, delivered evidence, still-unmet requirements, source/follow-up actual states,
any confirmed date, and incomplete operations needing reconciliation. When no split is eligible,
say so rather than manufacturing a follow-up. A snoozed original is not complete; an extracted
independent remainder is still outstanding. Never summarize the entire original promise as done.

This mode does not authorize a cache purge, rollout, installation, manual action, source edits,
remote synchronization or publication. Do not start the remainder or another bead after tracking.
Follow triage's closing handoff convention: put concrete pending decisions before the concise Next
line; no invented follow-up or promise of automatic continuation.
