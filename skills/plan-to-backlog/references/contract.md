# Plan-to-Backlog Contract

**Status:** Approved implementation contract for `agents-vqy.1`
**Public entry point:** `/plan-to-backlog <plan-source>`
**Tracker:** Beads
**Default behavior:** Read-only proposal; mutation requires explicit confirmation

## Decision summary

Add a standalone `plan-to-backlog` skill that turns an approved architecture or
implementation plan into a proportionate durable-tracking proposal. It owns plan-source
validation, existing-work inspection, no-item/single-item/epic disposition, proposal
rendering, confirmation, application, and recovery.

The workflow must not automatically materialize every plan step. A valid result may be:

1. no new item;
2. one focused item; or
3. one bounded epic with independently valuable children.

`/architect` remains read-only, `/triage` remains generic forward intake, and
`/backlog-groom` remains retrospective backlog quality work.

## Unique question

`/plan-to-backlog` answers:

> Given this approved, cited plan and the work already tracked, what durable Beads
> structure—if any—should exist, and what exact confirmed writes would create only the
> missing structure?

This differs from nearby skills:

| Skill | Question | Mutation boundary |
|---|---|---|
| `/architect` | What should be built, how, and with what evidence? | Never mutates trackers |
| `/triage` | How should a raw prompt or Jira request enter the backlog? | Generic intake creation |
| `/plan-to-backlog` | What durable structure should represent this approved plan? | Proposal first; apply only after exact confirmation |
| `/backlog-groom` | Is the existing backlog healthy and proportionate? | Retrospective; read-only by default |

## Naming decision

Use `/plan-to-backlog`, not `/triage plan` or a facade backed by triage.

The new workflow has a materially different safety contract from current triage:
plan citation, a first-class no-item result, an exact write preview, explicit confirmation,
and partial-apply recovery. A standalone skill makes that boundary discoverable and keeps
one authoritative implementation.

The name can imply that backlog creation is guaranteed. Counter that in the skill's first
line and every proposal header:

> Proposal-first. May recommend no backlog change. Never writes without confirmation.

Alternatives were rejected as follows:

- `/plan-triage` is plausible but too easily confused with `/triage`; users would have to
  learn whether the noun or subcommand owns a request.
- `/plan-tracking` can sound like progress monitoring rather than materialization.
- `/refine-plan` describes improving plan content, which belongs with architecture work.
- `/groom-plan` suggests retrospective plan quality and collides with `/backlog-groom`.
- A `/plan-to-backlog` facade over `/triage plan` pays for two surfaces while obscuring the
  authoritative safety boundary.

A two-provider naming quorum preferred standalone `/plan-to-backlog`. One additional local
reviewer preferred `/plan-tracking` because no-item is a valid outcome. This was quorum
evidence, not proof by vote; repository boundaries and discoverability are the decisive
evidence.

## Invocation

```text
/plan-to-backlog <plan-source>
```

Examples:

```text
/plan-to-backlog docs/plans/payment-retry-plan.md
/plan-to-backlog agents-abc.1
/plan-to-backlog https://example.atlassian.net/wiki/spaces/ENG/pages/12345
/plan-to-backlog current architect plan
```

There is no public `apply` shortcut that bypasses preview. Even when the user asks to
apply in the initial invocation, the workflow must first render the exact proposal and
obtain confirmation for that proposal.

## Accepted plan sources

The workflow accepts a complete plan from:

1. a readable repository or workspace Markdown file;
2. a Bead whose description, design, notes, or linked specification contains the plan;
3. a Jira or Confluence locator when the active runtime can retrieve the complete plan;
4. the current-session `/architect` result when the exact plan text can be captured and
   fingerprinted.

Every source record contains:

| Field | Requirement |
|---|---|
| `kind` | `file`, `bead`, `jira`, `confluence`, or `session` |
| `locator` | Stable path, key, URL, bead ID, or session locator |
| `title` | Human-readable plan title |
| `fingerprint` | SHA-256 of the exact consumed plan text |
| `approvalEvidence` | Explicit user approval in the current run or cited approval state |

The workflow must not infer approval from a filename, an architect heading, a ticket
status, or the existence of a tracking recommendation. Without explicit approval it may
inspect and preview, but readiness is `needs-clarification` and apply is forbidden.

A session source is acceptable only when its exact text and fingerprint are included in
the proposal. If the runtime cannot identify or capture that source reliably, ask the
user to save or cite it instead.

## Readiness and dispositions

Readiness is separate from backlog disposition:

- `ready` — the plan is approved, complete enough to classify, and traceable.
- `needs-clarification` — approval, source, ownership, duplicate resolution, or outcome
  boundaries remain unresolved. No apply is possible.

A ready proposal has exactly one disposition.

### No item

Choose `no-item` when:

- an existing bead or existing epic tree already owns the complete durable outcome;
- the plan only adds implementation mechanics to an existing owner;
- no independently valuable durable outcome remains after duplicate resolution; or
- the tracking recommendation explicitly and correctly says no additional item.

A no-item proposal identifies the reused owner and supporting evidence. It has an empty
write set and requires no mutation confirmation.

### Single item

Choose `single-item` when one independently valuable durable outcome remains. Keep coding,
testing, review, rollout, commit, retry, and handoff steps in its description, design, or
execution checklist unless one of those steps produces a separately valuable durable
outcome.

### Epic

Choose `epic` only when the parent represents an aggregate outcome worth tracking and the
children pass the independent-value test below.

The normal threshold is three to six direct children. Two children justify an epic only
when they cross a genuine ownership, repository, release, or independently shippable
boundary and aggregate completion needs durable tracking. More than six direct children
requires clustering or clarification before apply.

Each child must satisfy all of these tests:

1. **Observable outcome:** it makes a user-visible or system state true.
2. **Own acceptance:** it has evidence that can independently prove completion.
3. **Independent value:** it remains worthwhile if a sibling changes, is delayed, or is
   omitted.
4. **Independent lifecycle:** it can be closed, reprioritized, or assigned separately.
5. **Outcome language:** it describes delivered capability or evidence, not a work phase.

If fewer than the required children pass, collapse the proposal to one focused item.

## Mechanical-step exclusion

Never create one bead per plan step. The following are mechanical by default:

- write code;
- add unit tests;
- update documentation that only describes the same change;
- review the diff;
- run CI or validation;
- create commits or pull requests;
- deploy an inseparable part of the same outcome;
- retry a failed command;
- launch an agent or reviewer;
- create a handoff.

A normally mechanical activity becomes durable only when it produces an independently
valuable artifact or gate, such as a reusable compatibility suite, a consumer-owned
migration, or separately reviewable rollout evidence.

## Existing-owner and duplicate checks

Before selecting a disposition:

1. Verify an active Beads database with `bd status`.
2. Inspect open work with `bd list --status=open`.
3. Search exact source metadata or fingerprint where supported.
4. Search source locators through metadata, external references, specification IDs,
   descriptions, and notes.
5. Search outcome keywords across open and closed work.
6. Inspect high-signal matches, their parents, children, and dependencies.
7. Classify each match as `owner`, `duplicate`, `related`, or `not-relevant`, with one
   line of evidence.

An exact existing owner is reused. A partially materialized tree produces an epic or
single-item proposal containing `reuse` actions for existing nodes and `create` actions
only for missing outcomes. Ambiguous competing owners make readiness
`needs-clarification`; the workflow must not choose silently.

Closed work is evidence, not automatically an owner. Reopen, supersede, or replace it
only through the appropriate established workflow and explicit approval.

## Proposal schema

Render the proposal in Markdown with this logical schema:

```text
proposalVersion
proposalFingerprint
generatedAt

source:
  kind
  locator
  title
  fingerprint
  approvalEvidence

readiness: ready | needs-clarification
disposition: no-item | single-item | epic | omitted-when-unready
rationale

existingWork[]:
  id
  relationship: owner | duplicate | related | not-relevant
  evidence

items[]:
  ref
  action: reuse | create | update-type
  existingId
  type: task | feature | bug | epic | decision | chore
  priority
  title
  scope
  acceptance
  sourceCitation

relationships[]:
  kind: parent | blocking
  from
  to
  rationale

writeSet[]:
  sequence
  operation
  targetRef
  expectedResult

warnings[]
openQuestions[]
```

`proposalFingerprint` covers the source fingerprint, disposition, item definitions,
relationships, and write set. A changed source or proposal produces a new fingerprint
and invalidates earlier confirmation.

Every created item contains a human-readable source citation. When supported, also store
the source locator, source fingerprint, and proposal item reference as Beads metadata.
Do not overwrite an existing Jira or other external reference to store plan metadata.

Default priority is P2 unless source evidence justifies another priority. Priority does
not determine whether an outcome deserves its own item.

## Proposal rendering

Every preview begins with:

```text
Plan-to-Backlog Proposal — READ-ONLY
Proposal-first. May recommend no backlog change. Nothing has been changed.
```

The preview shows, in order:

1. source and approval evidence;
2. readiness and disposition;
3. existing-owner and duplicate evidence;
4. proposed items, including reused items;
5. parent and genuine blocking relationships;
6. the exact ordered write set;
7. warnings and unresolved questions;
8. the proposal fingerprint;
9. confirmation options when and only when readiness is `ready` and the write set is
   non-empty.

Do not present vague confirmation such as "create the backlog." Confirmation must name
the number and kinds of writes, for example:

> Apply proposal `abc123`: create one epic and three children, reuse `agents-xyz`, and add
> one blocking dependency?

Declining, abandoning, or answering ambiguously performs no writes.

## Apply contract

Immediately before applying:

1. re-read the source and verify its fingerprint;
2. rerun exact-owner and duplicate checks;
3. verify every reused item still exists and remains compatible;
4. verify the active proposal fingerprint matches the confirmed fingerprint;
5. use `bd create --dry-run` or equivalent safe preflight where supported.

Any material drift stops apply and renders a new proposal for fresh confirmation.

Apply in deterministic order:

1. reuse or create the owner;
2. update an existing durable owner to type `epic` when explicitly proposed;
3. reuse or create children;
4. establish parent relationships;
5. add genuine blocking dependencies;
6. re-read the resulting graph and render the result ledger.

Use `bd update --type epic` to convert an existing durable bead to an epic. `bd promote`
is only for promoting an ephemeral wisp to a permanent bead and must not be used as a
generic task-to-epic operation.

A dependency is genuine only when the dependent cannot satisfy its acceptance criteria
until the prerequisite outcome exists. Planning order, preferred implementation order,
shared context, testing after coding, and review after implementation are not sufficient.

Do not automatically close, delete, supersede, or roll back existing or newly created
beads.

## Result ledger and recovery

Return one ledger row per proposed item and relationship:

| Field | Meaning |
|---|---|
| `proposalRef` | Stable reference from the confirmed proposal |
| `action` | Intended `reuse`, `create`, `update-type`, `parent`, or `dependency` action |
| `actualId` | Existing or newly created bead ID when available |
| `status` | `reused`, `created`, `updated`, `failed`, `skipped`, or `declined` |
| `error` | Exact bounded failure evidence |
| `recovery` | Safe next action or rerun instruction |

On failure:

- preserve every successful ID and action in the ledger;
- stop before operations that depend on the failed result;
- do not claim the proposal was fully applied;
- do not automatically delete successful creations;
- instruct the user to rerun from the same source.

A rerun repeats source and duplicate checks, finds created items by source metadata,
fingerprint, citation, and outcome, then reuses them. It proposes only missing or
corrective actions and requires fresh confirmation. It must never create a second tree
merely because the previous run ended partially.

## Failure and degradation behavior

| Condition | Required behavior |
|---|---|
| No active Beads database | Render a tracker-neutral breakdown if useful; mark apply unavailable |
| Source inaccessible | Stop without a disposition or writes |
| Source not explicitly approved | Preview may continue; readiness is `needs-clarification` |
| Plan too vague to identify outcomes | Ask focused questions; do not materialize mechanics |
| Ambiguous owner or duplicate | Show candidates and require resolution |
| More than six credible children | Cluster or clarify; do not emit an unbounded epic |
| Required Beads feature unavailable | Use a proven core-command fallback or block apply |
| Proposal/source changed after confirmation | Invalidate confirmation and rerender |
| Confirmation declined or abandoned | Record declined result; perform no writes |
| Partial command failure | Stop dependent actions and return the recovery ledger |

## Skill handoffs

### Architect

When `/architect` recommends one focused item or an epic and a stable plan source exists,
it should offer a paste-ready invocation:

```text
/plan-to-backlog <plan-source>
```

Architect must not invoke it automatically, create the proposal itself, or mutate the
tracker. A no-additional-item recommendation needs no handoff.

### Triage

`/triage` remains the owner of raw prompt and Jira intake. When input clearly cites an
approved structured plan and asks to materialize its durable outcomes, triage hands the
request to `/plan-to-backlog` without classifying children or performing writes first.

`/plan-to-backlog` does not call back into triage for plan interpretation or apply. This
avoids two implementations of plan-derived disposition, epic thresholds, and
confirmation. Generic duplicate checks and low-level Beads commands may be similar; the
plan-specific policy remains owned here.

### Backlog groom

`/backlog-groom` remains retrospective and read-only by default. It may identify an
existing bead that needs ordinary splitting and continue to delegate that to `/triage`.
It does not consume plans, construct plan-derived proposals, or apply this workflow.

### Catalog

Add one alphabetical `plan-to-backlog` row to `skills/README.md`. Its description must
include `approved plan`, `Beads`, `proposal-first`, `no-item/single-item/epic`, and
`explicit confirmation` so search and discovery counter the name's mutation implication.

## Validation contract

The implementation must add a named repository test target, expected to be:

```text
make test-plan-to-backlog
```

It must run frozen fixtures without mutating the developer's real Beads database. The
minimum fixture matrix is:

| Scenario | Expected disposition/result |
|---|---|
| Existing owner covers the plan | `no-item`; owner cited; empty write set |
| One outcome with many mechanical steps | `single-item`; no step beads |
| Three independent outcomes | Bounded epic with independently acceptable children |
| Only two tightly coupled outcomes | Collapse to `single-item` |
| Two cross-repository shippable outcomes | Epic only when aggregate ownership is evidenced |
| Existing duplicate tree | Reuse existing nodes; create nothing duplicated |
| Partially materialized tree | Reuse successful nodes; propose only missing actions |
| Unapproved or ambiguous plan | `needs-clarification`; apply unavailable |
| Declined confirmation | No writes |
| Failure after some creates | Exact ledger; no rollback; safe rerun |
| Rerun after partial failure | Existing IDs reused; no second tree |
| Mechanical dependency sequence | No blocking edge |
| Genuine acceptance blocker | One justified blocking edge |
| More than six child candidates | Cluster/clarify; no unbounded apply |

Repository checks for the implementation slice:

```text
make validate-skills
make test-plan-to-backlog
make dry-run
```

Because this adds a new skill directory, applying it to managed client directories later
requires explicit `make apply`; follow with `make doctor`. Application is rollout work,
not part of the read-only contract decision.

Real dogfood must record:

- source locator and fingerprint;
- proposal disposition and item references;
- confirmation decision;
- proposal-reference to actual-ID mapping;
- genuine dependencies created;
- any failed/skipped operations and recovery;
- rerun duplicate behavior;
- tracker/version portability limits.

## Non-goals

- Converting every architecture slice into a bead.
- Revising or approving the technical plan.
- General backlog grooming or lifecycle cleanup.
- Cross-system Jira/Trello reconciliation.
- Automatic creation from architect output.
- Automatic closing, deletion, superseding, or rollback.
- A tracker-independent write abstraction in v1.
- Shared helper extraction before duplicated executable behavior is demonstrated.

## Rollout and rollback

Roll out the standalone skill, its tests, catalog entry, and architect/triage handoffs as
one coherent change. Default invocation remains read-only until confirmation. Existing
skill edits are live through symlinks; the new directory requires an explicit apply to
install its link.

Rollback removes the skill and its catalog/handoff references, then reapplies managed
links. Beads previously created through confirmed runs remain durable evidence and must
not be deleted automatically during rollback.

## Tracking disposition

No additional tracker item is required. Existing work already owns the full delivery:

- `agents-vqy.1` — this contract and epic threshold;
- `agents-vqy.2` — standalone implementation and skill handoffs;
- `agents-vqy.3` — fixtures, partial-failure validation, and real dogfood.

Implementation slices are delivery mechanics under those owners, not new backlog items.
