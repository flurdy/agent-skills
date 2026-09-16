---
name: beads
description: >
  Shared Beads workflow baseline. Use whenever an agent uses `bd`,
  manages durable tasks, blockers, or handoffs, resolves work ownership, or decides between an
  ephemeral checklist and durable tracking. Covers store authority and remote Dolt safety.
allowed-tools: "Read,Bash(python3 ~/.agents/skills/beads/scripts/integration_cleanup.py:*),Bash(bd:*),Bash(~/.agents/skills/next/scripts/next-select:*),Skill(next),Skill(triage),Skill(plan-to-backlog),Skill(backlog-groom),Skill(tracking-sweep),Skill(trello-beads),Skill(beads-check-dolt-migration),Skill(beads-migrate-to-dolt),Skill(beads-setup),AskUserQuestion"
model-tier: economy
model: haiku
effort: medium
version: "0.5.0"
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
permission. It refuses existing/ancestor/workspace-owned stores and owns the checked bd 1.2.2
fresh-init exception: bind process cwd but omit `-C` until the store exists. All later commands
retain owning-store qualification. Never initialize merely to satisfy another workflow's discovery.

## Explicit integration cleanup

For `/beads cleanup /absolute/repository` (or `cleanup --inspect` for preview only), read
[integration-cleanup.md](references/integration-cleanup.md). It owns standalone post-init
inspection and separately confirmed native removal, including linked instruction files and
shared hooks. It never runs merely because this baseline loaded and never mutates issue data.
For a separately authorized future initialization, help-check `--skip-agents --skip-hooks`;
these prevent integrations, not other init effects, and never remove existing setup.

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

Repositories declared `beadsStore: "workspace"` in validated workspace topology have no independent
store: route their new work to the root directory reported by `next-select stores`. Run discovery
from that workspace root and use `workspace:<id>` for existing root-owned work; do not treat a
member qualifier or an owner hint as proof that the root owns a particular issue. See
[next's ownership contract](../next/SKILL.md#workspace-tracking-ownership).

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

The bounded exception is user-enrolled routine sync through `sync_beads_store`, when that trusted
Pi tool is available. Enrollment binds the canonical store, exact remote URL and Dolt branch
through a TUI-only confirmation, including connection and executable identities.
A direct tool call may then fetch, safely pull or
non-force push that binding without another prompt, including in guarded plan mode and for an
owner-resolved store outside cwd. The tool revalidates the binding and safety state, refuses changed
or unknown destinations, pending work, schema drift, unsafe divergence and prospective conflicts,
and does not acquire a source worktree lease or switch session mode. It never authorizes force,
reset, migration, bootstrap, remote configuration, backup publication, Git push or production
changes. If the tool or enrollment is unavailable, use the confirmed raw-command path instead;
never imitate the tool with a shell wrapper.

Permission is not an instruction to sync.
Never invoke synchronization during a read-only list, resolver probe or local triage operation.
Run each remote or destructive Beads action as its own visible tool call.
Never hide it in a command chain, script, completion step, or unrelated Git operation.
If local policy is stricter, follow it.
