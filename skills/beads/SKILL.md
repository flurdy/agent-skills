---
name: beads
description: >
  Shared Beads workflow baseline. Use whenever an agent uses `bd`,
  manages durable tasks, blockers, or handoffs, resolves work ownership, or decides between an
  ephemeral checklist and durable tracking. Covers store authority and remote Dolt safety.
allowed-tools: "Read,Bash(python3 ~/.agents/skills/beads/scripts/integration_cleanup.py:*),Bash(bd:*),Bash(~/.agents/skills/next/scripts/next-select:*),Skill(next),Skill(triage),Skill(refine),Skill(plan-to-backlog),Skill(backlog-groom),Skill(tracking-sweep),Skill(trello-beads),Skill(beads-check-dolt-migration),Skill(beads-migrate-to-dolt),Skill(beads-setup),AskUserQuestion"
model-tier: economy
model: haiku
effort: medium
version: "0.11.0"
author: "flurdy"
---

# Beads Workflow

Apply this baseline whenever Beads is active. It decides where durable work belongs and which
focused skill owns the operation; it is not another intake, grooming, migration, or sync
procedure.

## Authority and opt-in

Repository-local instructions remain authoritative for whether Beads is active, which tracker
and store own work, lifecycle conventions, and stronger safety rules. Follow the nearest
`AGENTS.md` or equivalent project guidance before this shared baseline when they differ.

Do not initialize Beads merely because this skill loaded. If the repository has no active Beads
store, follow its declared Jira, Trello, or other tracking policy. If no tracker is declared, ask
before introducing one.

Never edit generated Beads integration blocks manually during ordinary work. This includes the
legacy `<!-- BEGIN BEADS INTEGRATION -->` marker and metadata-bearing variants through
`<!-- END BEADS INTEGRATION -->`. The only exception is the explicit cleanup-only, marker-bounded native edit in [integration-cleanup.md](references/integration-cleanup.md), after its exact preview, ownership
checks, recovery evidence and fresh confirmation. `bd` may regenerate removed blocks; put
human-maintained policy outside its markers.

## Explicit fresh-store setup

For an explicitly requested fresh repository store with a private GitHub Dolt remote, use
[beads-setup](../beads-setup/SKILL.md). Its preview grants no initialization or publication
permission. It refuses existing/ancestor/workspace-owned stores and owns the characterized bd
fresh-init exception: bind process cwd but omit `-C` until the store exists. All later commands
retain owning-store qualification. Never initialize merely to satisfy another workflow's discovery.

## Explicit integration cleanup

For `/beads cleanup /absolute/repository` (or `cleanup --inspect` for preview only), or
`/beads cleanup --global` for user-level Claude `bd prime` hooks (removed by the helper, not bd), read
[integration-cleanup.md](references/integration-cleanup.md). It owns standalone post-init
inspection and separately confirmed native removal, including linked instruction files and
shared hooks. It never runs merely because this baseline loaded and never mutates issue data.
For a separately authorized future initialization, help-check `--skip-agents --skip-hooks`;
these prevent integrations, not other init effects, and never remove existing setup.

## Resolve the owning store

Resolve ownership before the first decision-driving read in a focused operation and freshly
at every mutation boundary. Never infer the owning store from an issue ID, label, prefix, or the current directory.

For an existing bead or selector, run the shared resolver first:

```text
~/.agents/skills/next/scripts/next-select resolve <selector>
```

- `resolved`: use the returned absolute `directory`. Every later `bd` call uses `bd -C <directory>`.
- `ambiguous`: show the repository-qualified selectors and ask which owner is intended; write
  nothing.
- `unavailable`: report the failed store probes; write nothing because ownership is unproven.
- `not-found`: do not guess another store or create a replacement automatically.

For new durable work, choose ownership by outcome:

- Cross-project work belongs in the validated workspace root store.
- Work wholly owned by one repository belongs in that repository's active store.
- Repository-local tracker policy may override either default.

A workspace store and its member stores remain independent. Do not merge or synchronize them as
a side effect of resolving ownership.

Repositories declared `beadsStore: "workspace"` in validated workspace topology have no independent
store: route their new work to the root directory reported by `next-select stores`. Run discovery
from that workspace root and use `workspace:<id>` for existing root-owned work; do not treat a
member qualifier or an owner hint as proof that the root owns a particular issue. See
[next's ownership contract](../next/SKILL.md#workspace-tracking-ownership).

## Ownership proof lifetime

A successful resolver result may be reused for store-qualified reads of the exact qualified
target within one focused operation. Bind the actual returned issue/store identity and the
originating cwd/session; an owner hint, user assertion or model-invented receipt is not proof.
This is an instruction-level boundary, not a runtime cache or receipt API.

Invalidate read reuse when the target selector, owning repository/store identity,
topology/declaration/redirect, originating cwd or session changes, or the operation ends.
Any failed resolution (including `unavailable`) invalidates earlier success: never fall back to
cached ownership, write on failed proof, or interpret an unavailable result as not-found.

Immediately before each independent mutation, run a fresh full ownership resolution for its
exact target. A helper such as `next-select start` that performs this resolution internally
satisfies that boundary once for its bounded claim operation (attribution/update/display); do
not duplicate it with an identical caller-side check. Every direct `bd` mutation needs its own
fresh resolution. Neither read reuse nor a completed helper authorizes later independent writes
or unrelated targets. Stricter repository rules, source/plan guards and sync approvals still apply.

| Scenario | Required action |
|---|---|
| Same exact qualified target, unchanged context, more reads in one operation | Reuse actual successful resolution; qualify reads with its directory |
| Bare selector ambiguous across stores | Stop; ask for an exact owner; no reusable proof |
| Changed target selector | Resolve again before reading or writing |
| Changed repository/store identity or topology/declaration/redirect | Invalidate; resolve again |
| Changed originating cwd or session, or ended operation | Invalidate; resolve again |
| Later failed resolution, including unavailable | Discard earlier success; no fallback writes |
| Direct bd mutation after reads | Fresh full resolution immediately before that mutation |
| Helper start with its own resolver | One internal full resolution; no duplicate caller check |
| Stale or invented proof, later independent write or unrelated target | No authority; obtain fresh full resolution |

## Local issue mutations versus source authority

Local means a mutation in the resolver-proven owning store, not only the invoking cwd.
A guarded plan-mode session may use `bd -C <proven directory>` for ordinary comments, creates,
updates and closes in another repository without `/implement` or a source worktree lease.
User intent and repository-specific tracker rules still govern the operation; ambiguous,
unavailable or not-found resolution writes nothing. Beads writes never acquire a source lease
or authorize source, Git, package or system changes.

A configured Dolt remote alone does not turn a local comment into synchronization.
Verify effective export, backup and synchronization settings and actual side effects when
classifying an operation, rather than relying on command syntax or commented config examples.
Side effects beyond local tracking need their own applicable authority. Follow the remote and
destructive safety rules separately; `/implement` alone does not authorize remote or destructive actions.

## Durable tracking versus execution checklists

Use `todo` only as an ephemeral execution checklist for the active tracked item. It may break a
non-trivial implementation into concrete steps for this session, but it is not durable ownership.
Never duplicate a durable backlog item into `todo`. Clear or replace the checklist when the active
tracked item changes.

Keep blockers, dependencies, and follow-ups in Beads. Record work that must survive this session,
be independently prioritized, block another outcome, or be resumed by another agent in the owning
store rather than leaving it only in chat, a `todo` list, or an untracked note.

Do not create a bead for every implementation step, test, commit, review, retry, or handoff. Keep
those under the existing durable owner unless they have an independently valuable outcome and
lifecycle. The shared [sizing criteria](references/sizing.md) define that test and the epic
threshold.

## Dispatch by intent

Dispatch to the focused skill instead of reproducing its procedure.

| Intent | Owner |
|---|---|
| Rank or start ready work | `/next` |
| Create from a raw prompt or Jira ticket, refine, or split a bead | `/triage` |
| Judge whether one existing bead should stay whole, be clarified, or split | `/refine` |
| Materialize an explicitly approved cited plan | `/plan-to-backlog` |
| Audit backlog quality, priority, labels, lifecycle, or duplicates | `/backlog-groom` |
| Reconcile Jira, Beads, and pull-request drift | `/tracking-sweep` |
| Bridge a Trello-managed project and Beads | `/trello-beads` |
| Set up an explicitly selected fresh store with a private GitHub remote | `/beads-setup` |
| Detect storage or schema migration state | `/beads-check-dolt-migration` |
| Perform a confirmed storage or schema migration | `/beads-migrate-to-dolt` |

Invoke the corresponding allowed `Skill(...)` only when its preconditions are satisfied and its
Beads operations will stay in the selected store.

If a focused skill has no owner-routing input and the selected store is not the current active store, do not invoke it there.
Instead, render a switch-directory and focused-invocation handoff, then stop; an unqualified skill
run from a workspace root must not create or mutate repository-owned work in the workspace store.

When a focused skill is selected, its narrower confirmation, read-only, ownership, and failure
rules govern the operation. This baseline remains the fallback for store ownership and remote
safety.

## Routine CLI safeguards

For routine operations that do not need a focused skill, use the `bd` CLI only after the owning
store is proven, and keep every call qualified with `bd -C <directory>`. Inspect an existing bead
before changing it. Do not use `bd edit`; it opens an interactive editor. Use non-interactive
update flags instead, and prefer `--json` when parsing output programmatically.

Discovery does not authorize mutation. Do not claim, update, or close a bead merely because it
was found; mutate only when user intent and repository lifecycle rules justify the change, and
close only when the tracked outcome is actually complete.

Do not infer assignment, a claim or session activity from the issue `owner`. Owner identifies the
accountable human and may be set while `assignee` is empty; the same owner can have work handled by
several machines or sessions. Check `assignee`, status, `started_at` and claim-attribution evidence
separately. Even a recorded claim attributes a transition and does not prove that its session is live.
When an operation requires an unassigned issue, verify `assignee` is empty rather than treating an
owner value as an assignment.

Every agent-driven transition to `in_progress` records one claim-attribution comment containing
the available harness session ID, a UTC timestamp, and the proven owning store. The comment must
say that session activity is unverified: it attributes the claim but is not liveness evidence.
Make the attribution idempotent for the same session, issue, and store so retries and no-op claim
attempts do not create duplicate comments. Mutation helpers such as `next-select start` enforce
this convention; prose alone is not sufficient.

## Lifecycle and human decisions

Pick the lifecycle verb that records why the bead left the ready queue rather than closing
everything the same way:

- `bd close --reason` when the outcome is complete or deliberately abandoned; say which.
- `bd supersede` when a newer bead replaces it, so the history points forward.
- `bd defer --until` when it is waiting on a date or external event; do not park it at P4.

When progress needs a decision only the user can make, do not guess or leave the question in
chat. Record the options in the bead, add the `human` label, and stop that thread. `bd human list`
surfaces pending decisions; `bd human respond` records the answer and closes the bead, so
follow-on work goes in a new or dependent bead rather than reopening it.

Before reporting a tracked item as done, close it in its owning store.

Do not use `bd remember` for cross-session notes; the harness's own memory owns those, and Beads
holds only tracked work.

### Deferred verification

Use this narrow exception when implementation is committed and the only unmet acceptance is
verification that must wait for a future rollout or scheduled job. All presently executable
checks must pass against the recorded implementation; failed checks, missing local coverage,
stale evidence, unavailable tooling or an unowned detached commit do not qualify. Do not silently
leave eligible work `in_progress` while waiting; offer the dated lifecycle choice through
[complete-task](../complete-task/SKILL.md#6-finalize-the-bead). [verify-task](../verify-task/SKILL.md)
reports the pending evidence and hands back without tracker writes or a verification pass.

| Path | Gate | Tracking outcome |
|---|---|---|
| **Snooze the original** (default) | No explicit project declaration, boundary not reached, or user chooses to retain one bead | Defer the original with a verification note and wake date; do not close or split it. |
| **Close implementation + deferred follow-up** | Applicable project guidance explicitly declares commit/merge as delivery, that boundary has been reached, and the user confirms the exact proposal | Create the follow-up first, verify it was saved, then close implementation with its evidence gap and follow-up ID. |

A branch name, trunk workflow, commit alone, or generic permission to close does not establish the
second gate. Cite the applicable project declaration and proof of reaching its boundary (for example,
commit reachability from local `main`, or the required merge evidence). Guidance must distinguish
implementation delivery from the later check. Do not edit project or user-level guidance to make a
case eligible. Example declaration for a project's own `AGENTS.md` (adapt only with authorization):

```text
Implementation delivery boundary: the verified implementation commit is reachable from local main.
Future-event verification may remain outstanding in one dated, evidence-only follow-up.
Verify after the next scheduled staging job using <exact job URL/command>; require its deployed
revision to contain the recorded commit and <specific pass criteria>. Record the evidence on the
verification bead. Closing implementation does not claim rollout or runtime verification.
```

Both paths require a concrete future wake date agreed with the user, with timezone when a time is
specified. Use a dated snooze, not a dateless icebox or P4 parking. The wake date is a reminder:
`bd defer --until` does not detect the event or run a check. If timing is unknown, agree on a review
date and retain the event condition. Missing date or declined confirmation means no lifecycle writes;
report the unresolved decision, not a successful deferral.

The verification note or follow-up must contain:

- What remains unverified, with the exact command, URL or job to check.
- Target environment and immutable implementation revision; how to establish the deployed/job revision.
- Observable pass criteria, the wake date, and the event to confirm before attempting the check.
- An evidence destination (normally the owning bead), and failure disposition.

Create at most one evidence-only follow-up in the same owning store, linked by `discovered-from`,
not parent membership or a blocking edge. Preserve relevant provenance, including an exact Jira
`external_ref` when present; no guessed associations. On rerun, inspect existing links and reuse a
matching follow-up rather than duplicate it. A failed/uncertain create or unverified saved record
leaves the original open; never close first and promise to create later. Close with an honest reason:
`implemented at <sha>; <check> unverified, tracked in <follow-up>`.

When the snooze wakes, confirm the event and revision first. If the event has not happened, obtain
confirmation for a new dated snooze on the same bead; no automatic polling or replacement follow-up.
After explicitly authorized verification passes, close the verification follow-up (or snoozed
original) in its proven store with checked evidence and revision. No new implementation commit is
required for an evidence-only closure; do not manufacture one via `complete-task`. Verification alone
still cannot write tracking. Jira remains a separate explicitly requested, approved action.

On verification failure, never close it as verified. Reopen the original only when the failure
invalidates its recorded completion claim; otherwise track a new linked bug under the normal
confirmation/ownership rules. Preserve the failed evidence and explicit disposition on the verification
record; no automatic reopen or bug creation. This is not a general exception to
[one outcome, one bead](references/sizing.md#deferred-verification-exception).

## Use current CLI guidance

Run `bd prime` yourself when local Beads policy is unclear; no hook injects it, and this baseline
plus repository guidance override anything it prints. Use `bd where` when the
current repository's active store is uncertain. That identifies the local active store, not the
owner of an arbitrary selector, so existing-bead ownership still requires the shared resolver.

Use `bd <command> --help` immediately before a version-sensitive or unfamiliar operation. Treat
the installed CLI and repository configuration as evidence; do not assume a command form from
another repository or older session.

Do not turn this baseline into a version-specific command catalog. Detailed command sequences
belong in the focused skills or current CLI help so upgrades do not leave copied procedures stale.

## Remote and destructive safety

A local commit never authorizes remote Beads synchronization. Treat Dolt pull, push, bootstrap,
remote migration, and other remote synchronization as separate actions from local issue updates
and Git commits.

Ask for explicit confirmation immediately before every raw `bd dolt push`. Obtain fresh
confirmation for raw remote synchronization that can publish data or replace local state, and
explain the scope first. Approval from an earlier task or session does not carry forward.

In a validated project-workspace providing `make beads-sync`, use that target for routine
workspace synchronization instead of assembling an ad hoc command loop. First show the unique
store set with `make beads-sync-check`; it previews intended actions without contacting remotes
and does not prove remote freshness. Obtain fresh explicit confirmation for the complete
`make beads-sync` invocation, then run it as one visible command. That bounded approval covers
the target's sequential per-store pull and non-force push; it never authorizes force, reset,
conflict resolution, migration, bootstrap, remote configuration, backup publication or Git push.
Report per-store failures and the overall non-zero result, not workspace success. A failed pull
may leave merge state requiring separately reviewed recovery; do not retry automatically.

Outside that workspace workflow, keep raw remote commands separately confirmed and owner-qualified.
Stricter repository policy still wins; approval of a wrapper never bypasses a requirement to approve
each underlying action.

Permission is not an instruction to sync.
Never invoke synchronization during a read-only list, resolver probe or local triage operation.
Run each remote or destructive Beads action as its own visible tool call.
The explicitly confirmed workspace target above is the only grouped workflow described here;
never hide other remote actions in a command chain, script, completion step or unrelated Git operation.
If local policy is stricter, follow it.
