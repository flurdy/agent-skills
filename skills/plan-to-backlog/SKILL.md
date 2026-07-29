---
name: plan-to-backlog
description: "Proposal-first materialization of an approved cited plan into proportionate Beads tracking. Recommends no item, one item, or a bounded epic; checks owners and duplicates; previews every write; and applies only after explicit confirmation with partial-failure recovery."
disable-model-invocation: true
allowed-tools: "Read,Grep,Glob,AskUserQuestion,Bash(bd status:*),Bash(bd list:*),Bash(bd search:*),Bash(bd show:*),Bash(bd children:*),Bash(~/.agents/skills/plan-to-backlog/scripts/utc-now.sh:*),Bash(~/.agents/skills/plan-to-backlog/scripts/sha256-stdin.sh:*),Bash(~/.agents/skills/plan-to-backlog/scripts/confirmed-bd.sh:*),mcp__jira__*,mcp__confluence__*"
model-tier: standard
model: sonnet
effort: high
version: "1.0.0"
author: "flurdy"
---

# Plan to Backlog

Proposal-first. May recommend no backlog change. Never writes without confirmation.

Turn an approved architecture or implementation plan into the smallest justified durable
Beads structure. Inspect the cited plan and existing work, decide whether no item, one
focused item, or a bounded epic is warranted, preview the exact write set, then apply only
that confirmed proposal.

The canonical behavior and thresholds are defined in the
[plan-to-backlog contract](../../docs/plans/plan-to-backlog-contract.md).

## When to use

Use `/plan-to-backlog` when:

- an `/architect` or implementation plan has been explicitly approved;
- the plan has a stable source or exact capturable session text;
- the user wants durable Beads ownership rather than another planning pass; and
- no-item versus single-item versus epic is still a meaningful decision.

Do not use it for raw ideas or Jira intake (`/triage`), plan refinement (`/architect`),
retrospective backlog quality (`/backlog-groom`), or cross-system reconciliation
(`/tracking-sweep` or `/trello-beads`).

## Usage

```text
/plan-to-backlog <plan-source>
```

Accepted sources:

- repository or workspace Markdown path;
- Bead ID whose description, design, notes, or linked specification contains the plan;
- Jira or Confluence key/URL when the runtime can retrieve the complete plan; or
- the exact current-session `/architect` result.

There is no invocation that bypasses preview. An initial request to "apply" still follows
the full source, proposal, and confirmation procedure.

## Ownership boundary

- `/architect` owns technical planning and remains read-only.
- `/triage` owns unstructured prompt/Jira intake and hands approved structured plans here.
- `/plan-to-backlog` alone owns plan-derived disposition, proposal, confirmation, apply,
  and recovery.
- `/backlog-groom` remains retrospective and read-only by default.

Do not call `/triage` to classify or apply the plan. Similar low-level Beads lookups do not
change this skill's ownership of the plan-specific policy.

## Safety invariants

- Stay read-only until the exact proposal has been rendered and confirmed.
- Never create one bead per plan step.
- Never infer plan approval from a filename, heading, ticket status, or tracking
  recommendation.
- Never choose silently between plausible existing owners or duplicates.
- Never add a dependency merely to represent preferred execution order.
- Never close, delete, supersede, or automatically roll back a bead.
- Never use `bd promote` to turn a durable task into an epic; it promotes wisps only.
- Never use a broad graph write in v1; apply individual commands so every result is
  attributable in the ledger.
- A changed source, tracker graph, or proposal invalidates confirmation.

## 1. Resolve and approve the source

Parse `<plan-source>` and load only the complete plan needed for materialization.

Resolve the installed stdin-only hashing helper at
`~/.agents/skills/plan-to-backlog/scripts/sha256-stdin.sh`. Never place plan text in shell
arguments. File sources use raw bytes. Bead, Jira, Confluence, and session text use
`--canonical-text`, which normalizes UTF-8 text to LF line endings and exactly one trailing
newline (`utf8-lf-final-newline-v1`). Record the selected normalization with the source.

### File source

1. Resolve the path without editing it.
2. Read the complete plan.
3. Stream the exact file bytes to the hashing helper through standard input.

### Bead source

1. Run `bd show <id> --json --include-comments`.
2. Identify the exact description, design, notes, comments, or specification text being
   consumed.
3. Stream that exact logical text to the hashing helper's `--canonical-text` mode through
   standard input.

### Jira or Confluence source

1. Fetch the cited issue/page with the available connector.
2. Identify the exact plan body and linked material being consumed.
3. Stream only the sanitized exact plan text to the hashing helper's `--canonical-text`
   mode through standard input.

### Session source

1. Identify the exact finalized plan in the current session.
2. If it cannot be distinguished from drafts or captured exactly, ask the user to save or
   cite it and stop.
3. Stream the exact finalized text to the hashing helper's `--canonical-text` mode through
   standard input.

When a shell heredoc is the only stdin mechanism, use a quoted delimiter that does not
occur in the text so no content is expanded or truncated. Canonical-text mode makes the
heredoc's terminal newline deterministic. Never include credentials, `.env` contents,
keys, tokens, or irrelevant personal data.

Record:

```text
source.kind
source.locator
source.title
source.fingerprint
source.normalization
source.approvalEvidence
```

Approval must be explicit in the current run or cited from a specific approval statement.
If approval is absent or ambiguous, continue only as a read-only preview and set readiness
to `needs-clarification`; apply is unavailable.

## 2. Gather Beads context read-only

Run:

```text
bd status
bd list --status=open
```

If no active Beads database is available, render a tracker-neutral breakdown when useful,
mark apply unavailable, and stop before confirmation.

Search in this order, using only supported read forms:

1. `bd search --metadata-field plan_source_sha256=<source-fingerprint> --status all`
2. source locator through metadata, external references, specification IDs, descriptions,
   and notes;
3. high-signal outcome keywords across open and closed work;
4. likely owners' parents, children, and dependencies with `bd show` and `bd children`.

Inspect high-signal matches rather than auditing the whole backlog. Classify each as:

- `owner` — already owns the complete durable outcome;
- `duplicate` — competing representation of the same outcome;
- `related` — relevant but materially different; or
- `not-relevant` — inspected and excluded.

An exact existing owner is reused. Closed work is evidence, not automatically an active
owner. If two plausible owners remain, list both with evidence, set readiness to
`needs-clarification`, and ask the user to resolve ownership.

## 3. Select readiness and disposition

Use this schema:

```text
readiness: ready | needs-clarification
disposition: no-item | single-item | epic
```

Omit disposition when readiness is `needs-clarification` and the missing decision could
change the shape.

### No item

Choose `no-item` when an existing bead/tree already owns the complete outcome, or the plan
contains only execution mechanics under one existing owner. Cite the owner and evidence.
The write set is empty and no confirmation is needed.

### Single item

Choose `single-item` when one independently valuable durable outcome remains. Keep coding,
tests, review, documentation of the same change, rollout, commits, retries, agents, and
handoffs in the item's design or execution checklist.

### Epic

The normal threshold is three to six direct children. Allow two only when they cross a
genuine ownership, repository, release, or independently shippable boundary and the
aggregate outcome itself needs tracking. More than six requires clustering or
clarification.

Every child must have:

1. an observable outcome;
2. its own acceptance evidence;
3. value if a sibling changes, is delayed, or is omitted;
4. an independent close/reprioritize/assign lifecycle; and
5. outcome language rather than work-phase language.

If fewer children pass, collapse to `single-item`.

A dependency is genuine only when the dependent cannot satisfy its acceptance criteria
until the prerequisite outcome exists. Planning order, coding before tests, review after
implementation, and shared context do not qualify.

## 4. Build the proposal

Set `proposalVersion` to `1` and obtain `generatedAt` from the no-argument
`~/.agents/skills/plan-to-backlog/scripts/utc-now.sh` helper. Exclude `generatedAt` from
fingerprint input so time alone cannot invalidate an unchanged proposal.

Use stable local references such as `owner`, `child-1`, and `child-2`. Each proposed item
contains:

```text
ref
action: reuse | create | update-type
existingId
type
priority
title
scope
acceptance
sourceCitation
```

Default priority is P2 unless source evidence justifies another value. Priority never
justifies a separate child by itself.

Relationships contain:

```text
kind: parent | blocking
from
to
rationale
```

Build an ordered logical write set containing stable proposal refs, call templates, and
the expected result for every mutation. A template that needs a newly created ID uses an
explicit placeholder such as `${owner.actualId}`; it never guesses the future Beads ID.
Use only these write classes:

- `bd create` for a new owner or child;
- `bd update <id> --type epic` for an explicitly confirmed durable owner conversion;
- `bd update <id> --parent <owner-id>` for an explicitly confirmed reused-child parent;
- `bd dep add <dependent-id> <prerequisite-id>` for a justified blocker.

Do not include unrelated field edits. New items include a human-readable source citation
and metadata keys for `plan_source`, `plan_source_sha256`, and `plan_proposal_ref`.
Preserve existing external references.

Create a canonical text representation containing `proposalVersion`, the source
fingerprint and normalization, readiness, disposition, items, relationships, and logical
write set with stable-ref placeholders. Exclude `generatedAt`, runtime-resolved actual IDs,
and the later execution-guard arguments. Stream the canonical text to the stdin-only
hashing helper to obtain the proposal fingerprint. After hashing, render guarded call
templates using that fingerprint for both proposal and confirmation arguments; the guard
envelope and later ledger-based placeholder substitution are not part of the logical
write set.

## Render the proposal

Render this header before any mutation:

```text
Plan-to-Backlog Proposal — READ-ONLY
Proposal-first. May recommend no backlog change. Nothing has been changed.
```

Then show:

1. `proposalVersion` and `generatedAt`;
2. source locator, fingerprint, and approval evidence;
3. readiness, disposition, and rationale;
4. existing-owner and duplicate evidence;
5. every proposed/reused item;
6. every parent and blocking relationship with rationale;
7. the ordered guarded helper call templates, including every stable-ref placeholder;
8. warnings and open questions;
9. the proposal fingerprint.

For `no-item` or `needs-clarification`, stop after the preview and next action. Do not show
an apply choice.

## Confirm the exact proposal

When readiness is `ready` and the write set is non-empty, use `AskUserQuestion` immediately
before apply. The question names the proposal fingerprint and exact counts, for example:

> Apply proposal `abc123`: create one epic and three children, reuse one existing child,
> update one parent link, and add one blocking dependency?

Offer:

1. **Apply exact proposal** — run only the displayed write set.
2. **Revise proposal** — return to read-only analysis and render a new fingerprint.
3. **Decline** — stop with no changes.

Declining, abandoning, or answering ambiguously performs no writes.

Confirmation authorizes only the displayed fingerprint. It does not authorize additional
fixes, duplicate cleanup, closures, rollback, or changed commands.

## Apply the confirmed proposal

Immediately before the first write:

1. re-read and re-hash the source;
2. rerun every source, locator, outcome, owner, and duplicate query used to build the
   proposal, then compare every classification;
3. verify every reused ID and relevant graph relationship;
4. rebuild the canonical proposal and verify its fingerprint equals the confirmed value;
5. prepare one matching preflight per create. Run each preflight only immediately before
   its corresponding create, after every required runtime ID is present in the ledger.

Any material drift stops apply and renders a new read-only proposal for fresh
confirmation.

Run every mutation through
`~/.agents/skills/plan-to-backlog/scripts/confirmed-bd.sh`, passing the rebuilt proposal
fingerprint and the confirmed fingerprint separately. Never invoke mutating `bd` commands
directly. The helper rejects mismatched fingerprints, unsupported actions/flags, missing
source citation metadata, and commands outside the bounded create/update-parent/
update-type/add-blocker surface.

Maintain a ledger map from each stable proposal ref to either its confirmed reused ID or
the actual ID returned by a successful create. Immediately before each helper call,
resolve only the declared `${ref.actualId}` placeholders from that map and validate the
resolved IDs. This ledger-based reference resolution does not change the confirmed logical
operation. A missing, ambiguous, or invalid mapping fails the operation before the helper
call; never substitute an undeclared ID or alter static arguments.

Apply one operation at a time in this order:

1. resolve the operation's currently available stable-ref placeholders;
2. immediately before each create, run `preflight-create` with those exact resolved
   arguments; it executes `bd create --dry-run`;
3. reuse or create the owner with `create` and record its actual ID;
4. run `update-type` only for a confirmed durable-owner conversion; it executes
   `bd update --type epic`;
5. resolve the owner ID, then preflight and create each child with its confirmed parent;
6. run `set-parent` for confirmed parent links on reused children;
7. run `add-blocker` for confirmed genuine blockers after both IDs are resolved;
8. re-read the resulting owner, children, and dependencies.

The helper requests JSON output and returns the underlying command status. Capture each
returned ID immediately. A successful preflight authorizes nothing and must be followed
by the matching confirmed `create` call only when its turn is reached. Do not run a later
operation until the current result is understood and recorded.

## Result ledger

Render one row per proposed item and relationship:

| Proposal ref | Action | Actual ID | Status | Error | Recovery |
|---|---|---|---|---|---|

Statuses are `reused`, `created`, `updated`, `failed`, `skipped`, or `declined`.

On failure:

- preserve every successful ID and action;
- stop before operations that depend on the failed result;
- mark later dependent operations `skipped`;
- report the exact bounded error;
- do not claim full application;
- do not delete or roll back successful creations; and
- give one safe rerun instruction using the same source.

After success, re-read the graph and compare actual IDs, parents, and dependencies with the
confirmed proposal. Report mismatches honestly rather than repairing them without another
proposal and confirmation.

## Reruns and partial recovery

Every rerun starts from the source, not from assumptions about the previous session.
Search by source fingerprint, proposal ref, source citation, title, and outcome. Reuse
confirmed matches and propose only missing or corrective operations.

A rerun after partial application must never create a second tree. If metadata is
unavailable or conflicting evidence prevents safe matching, set readiness to
`needs-clarification` and show the candidate IDs.

## Failure and degradation

- **Source inaccessible:** stop without a disposition or writes.
- **Source unapproved:** preview only; apply unavailable.
- **Plan too vague:** ask focused questions; do not materialize mechanics.
- **No Beads database:** tracker-neutral breakdown only; apply unavailable.
- **Ambiguous owner/duplicate:** require resolution before disposition or apply.
- **More than six credible children:** cluster or clarify.
- **Required Beads capability unavailable:** use a proven permitted fallback or block the
  affected operation.
- **Source/tracker/proposal drift:** invalidate confirmation and rerender.
- **Declined confirmation:** no writes.
- **Partial failure:** stop dependent actions and return the result ledger.

## Output summary

End every run with:

```text
Source: <locator> @ <fingerprint>
Readiness: <ready | needs-clarification>
Disposition: <no-item | single-item | epic | unresolved>
Proposal: <fingerprint or unavailable>
Writes: <none | declined | N succeeded, M failed, K skipped>
Next: <single safe action>
```

## Guardrails

- Do not revise the technical plan; return material uncertainty to `/architect`.
- Do not perform general backlog cleanup discovered during searches.
- Do not create Jira/Trello items or cross-system links.
- Do not create tracker items for tests, commits, agents, reviews, retries, or handoffs.
- Do not use raw `bd close`, `bd delete`, `bd supersede`, or `bd promote` commands.
- Do not bypass the confirmed-action helper for Beads mutations.
- Do not persist source or proposal text outside its cited source.
- Do not claim transactionality; Beads writes may partially succeed.
