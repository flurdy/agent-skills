---
name: beads
description: >
  Shared Beads workflow and durable-tracking baseline. Use whenever an agent uses `bd`,
  manages durable tasks, blockers, dependencies, follow-ups, or shared handoff memory,
  resolves durable work ownership, or decides between an ephemeral execution checklist and durable tracking.
  Covers store ownership, local authority, focused-skill routing, and remote Dolt safety without duplicating command procedures.
allowed-tools: "Read,Bash(bd:*),Bash(~/.agents/skills/next/scripts/next-select:*),Skill(next),Skill(triage),Skill(plan-to-backlog),Skill(backlog-groom),Skill(tracking-sweep),Skill(trello-beads),Skill(beads-check-dolt-migration),Skill(beads-migrate-to-dolt),AskUserQuestion"
model-tier: economy
model: haiku
effort: medium
version: "0.1.1"
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

Never edit generated Beads integration blocks manually. In particular, content between
`<!-- BEGIN BEADS INTEGRATION -->` and `<!-- END BEADS INTEGRATION -->` is owned by `bd` and may
be regenerated. Put human-maintained policy outside those markers.

## Resolve the owning store

Resolve ownership before every read that drives a decision and before every mutation.
Never infer the owning store from an issue ID, label, prefix, or the current directory.

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
lifecycle.

## Dispatch by intent

Dispatch to the focused skill instead of reproducing its procedure.

| Intent | Owner |
|---|---|
| Rank or start ready work | `/next` |
| Create from a raw prompt or Jira ticket, refine, or split a bead | `/triage` |
| Materialize an explicitly approved cited plan | `/plan-to-backlog` |
| Audit backlog quality, priority, labels, lifecycle, or duplicates | `/backlog-groom` |
| Reconcile Jira, Beads, and pull-request drift | `/tracking-sweep` |
| Bridge a Trello-managed project and Beads | `/trello-beads` |
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

## Use current CLI guidance

Use `bd prime` to recover the active repository's current workflow context after compaction or
when local Beads policy is unclear; hooks may already have injected it. Use `bd where` when the
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

Ask for explicit confirmation immediately before every `bd dolt push`. Obtain fresh confirmation
for other remote synchronization that can publish data or replace local state, and explain the
scope first. Approval from an earlier task or session does not carry forward.

Run each remote or destructive Beads action as its own visible tool call. Never hide it in a
command chain, script, completion step, or unrelated Git operation. If local policy is stricter,
follow it.
