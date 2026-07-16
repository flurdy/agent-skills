---
name: orchestrate
description: Safely coordinate bounded subagent delegation through explicit ownership, child-route consent, one-writer execution, independent review, and parent-owned validation. Use only when explicitly invoked; skip trivial, tightly coupled, or serial work.
allowed-tools: "Read,Grep,Glob,Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(git show:*),Bash(git rev-parse:*),Bash(bd status:*),Bash(bd list:*),Bash(bd show:*),Task,Skill(architect),Skill(verify-task),Skill(total-review),Skill(triage),Skill(second-opinion),Skill(pi-subagents),AskUserQuestion"
disable-model-invocation: true
model-tier: premium-reasoning
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
effort: high
version: "1.3.0"
author: "flurdy"
---

# Orchestrate

Coordinate bounded delegated work while keeping outcome, scope, judgment,
integration, and final validation in the parent agent. Delegation is an execution
mechanism, not a transfer of authority.

This version provides a conservative delegation workflow rather than a persistent or
fully adaptive scheduler. See [`README.md`](README.md) for current maturity and the
future orchestration roadmap.

## Tier guard

This skill is `model-tier: premium-reasoning`. Before starting, check the current
model. If it is below the runtime's premium tier, say so and use the runtime's native
user-question mechanism (`AskUserQuestion` in Claude Code) to offer:

- **Continue here** — accept reduced coordination depth for this run.
- **Stop** — switch to a premium model and invoke the skill again.

If the runtime cannot expose the effective model, say so and ask whether to continue
with an unverified tier; never claim that the premium guard passed. Skip the prompt
when the user explicitly selected the current model. On a verified premium model,
stay silent. This guard checks capability; parent-route cost confirmation remains the
runtime/router's responsibility. Use `high` for routine coordination and raise effort
only when architecture, risk, or final judgment warrants it.

## 1. Decide whether delegation pays

Use this skill only after explicit user invocation. Invocation authorizes ordinary
bounded delegation within the requested scope, not external side effects, tracker
mutations, product decisions, or broader work.

Decline delegation and continue directly when the task is trivial, tightly coupled,
inherently serial, or cheaper to do than to brief and supervise. Delegation must save
more context, latency, or cost than briefing, coordination, and review consume.

The parent always owns:

- Outcome, scope, acceptance, architecture, and high-impact decisions
- Decomposition, child selection, route consent, and writer ownership
- Integration, conflict resolution, review synthesis, and final response
- Inspection of the actual diff and validation evidence

Use `architect` when ambiguity or blast radius requires a plan. Do not send unresolved
architecture to a worker. `verify-task` and `total-review` remain separate gates;
invoke them rather than copying their workflows.

## 2. Establish outcome, context, and acceptance

Before delegation, establish the user-visible outcome, explicit non-goals, and
acceptance evidence. If those are disputed or consequential architecture remains
unresolved, ask the user or invoke `architect` before assigning implementation.

Continue directly when the work is one coherent unit with shared context, ownership,
and validation. For work with material dependencies, uncertainties, or integration
seams, read and follow
[`references/work-graph.md`](references/work-graph.md). Its compact method separates:

1. Decisions retained by the parent, user, or `architect`.
2. Material uncertainties and the smallest evidence needed to resolve them.
3. Bounded work units with hard dependencies and ownership boundaries.
4. Integration points, ready work, and the critical dependency path or candidates.
5. Splits whose coordination value is too low and should be collapsed.

A work-graph node is not automatically a child launch or tracker item. A valid graph
may conclude that one writer should perform all work serially. The graph exposes
topology and readiness; later execution-shape selection decides what, if anything, to
delegate.

This version still uses a shallow execution shape, not a persistent dependency
scheduler. Use parallel children only for genuinely independent read-only questions
or intentionally isolated worktrees. If decomposition exposes unresolved
architecture, return to the parent or invoke `architect`, then rebuild affected graph
edges before assigning implementation.

Read repository rules, established patterns, and current status/diff. Use tracking
only for durable context:

- Use Beads only when `bd` is available, active Beads context exists, and a relevant
  bead or epic is present.
- Otherwise use the established Jira, Trello, or other tracker. If none exists, report
  durable milestone suggestions generically.
- Never create one item per child, recon pass, review, retry, or handoff.
- Propose independently valuable tracker work only; mutate tracking after explicit
  approval. Invoke `triage` only in a Beads-enabled repository.
- Consume a portable control-plane index when useful, but do not require, create, or
  silently rewrite one.

## 3. Choose the execution shape

Give the user a short execution shape before launching children. For a non-trivial
work graph, include only the material fields:

```text
retained decisions: <D IDs and what stays with the parent>
material uncertainties: <U IDs, resolution evidence, and blocked work>
work graph: <W IDs, deliverables, and hard dependencies>
ready/critical: <ready set and dependency spine/candidates>
integration: <seams and parent synthesis point>
declined fanout: <collapsed units or none>
writer: <single owner and files/worktree>
verification: <commands, flows, and independent review>
escalate/stop: <conditions that return control>
```

For one coherent unit, keep this to outcome, writer ownership, verification, and stop
conditions; do not manufacture registers or graph nodes for presentation.

Default to:

```text
scope and acceptance
  -> optional independent recon/advice
  -> one implementation writer
  -> integration inspection
  -> independent review/validation
  -> at most one focused fix pass
  -> parent final validation and response
```

This is a default, not a reason to manufacture children. Omit stages that provide no
independent value.

## 4. Load launch policy and runtime mechanics

Before any child launch:

1. Read and follow
   [`references/child-routing-policy.md`](references/child-routing-policy.md).
2. Detect the active runtime, then read and follow
   [`references/runtime-adapters.md`](references/runtime-adapters.md).

The compact invariant is: launch without another cost prompt only when trusted
evidence resolves the effective child identity before launch and classifies it as
unmetered. Metered, inherited, or unknown routes require current-run consent. Parent
route approval never authorizes child fanout; mismatches stop further launches; ad hoc
consent is never persisted.

Do not parse or merge model-tier-router configuration, change canonical agent
settings, infer billing, or invent a mapping. The references own route policy and
runtime mechanics; the remainder of this skill owns work coordination.

## 5. Give every child a judgment packet

Match packet size to risk. A cheap read-only lookup needs an objective, bounded scope,
expected evidence, and stop condition. A writer or consequential analyst needs:

1. Goal and user-visible outcome.
2. Owned files/modules or bounded read-only question.
3. Relevant rules, context pointers, and established patterns.
4. Non-goals and prohibited expansion.
5. Acceptance criteria and exact validation commands or user flows.
6. Risks, assumptions, dependencies, and unresolved questions.
7. Required result: status, files/evidence, validation outcomes, discoveries,
   residual risks, and decisions needed from the parent.
8. Escalation and stop conditions.

Require the child to return one of `complete`, `blocked`, or `needs-decision`. A
blocked or decision result must include evidence and the smallest question needed to
continue. Do not let children silently redefine scope, architecture, or acceptance.

If the packet still asks the child to discover architecture or choose a high-impact
alternative, retain that work in the parent or use a stronger advisory/planning pass.

## 6. Assign by work shape and risk

Use semantic classes rather than exact shared model IDs or changed-line counts:

| Work shape | Assignment |
|---|---|
| Focused lookup or repository/document research | Read-only context/research role; cheap route only when verified. |
| Narrow mechanical implementation | One writer on `focused-coding` only when the packet fixes scope, pattern, non-goals, acceptance, validation, and escalation. |
| Bounded implementation or routine independent review | One focused writer or fresh reviewer on a verified focused/balanced route; otherwise inherit with disclosure and consent. |
| Complex implementation with local design judgment | Verified `advanced-coding` child, inherited child with consent, or retain in the parent. |
| Architecture, unclear ownership, public contracts, destructive or security-sensitive work | Retain the decision in the premium parent; use a strongest-route advisor only when justified. |
| Final craft judgment | Fresh reviewer, `premium-review`, or a named review skill; use extra effort only when risk warrants it. |

All writes use the runtime's implementation role, named `worker` when available. Tune
effort within a suitable class before jumping classes.

## 7. Execute, communicate, and integrate

Only one writer may edit a shared worktree at a time. Parallelize research, recon,
review, and validation—not ordinary writes. Parallel writers require intentional
worktree isolation, a clean base, non-overlapping ownership, and an explicit
integration order.

Use native progress/intercom facilities when available for material discoveries,
blockers, and decision requests. Do not require chatter for healthy bounded work; a
one-shot result envelope is the portable fallback. The parent decides whether new
evidence changes the packet, requires a focused follow-up, returns to architecture,
or stops.

After a writer returns, the parent must inspect the actual diff, reconcile it with
other findings and repository state, and run or witness required validation. A child
summary is not integration evidence.

Use fresh/separate context for genuine independent review where supported. Cap routine
fanout at two or three distinct angles. The implementer cannot be the sole authority
that its work is complete when delegation exists. Use named review gates rather than
building an unbounded generic review loop.

If delegation is unavailable or declined, continue serially and label the result
**self-validated**, not independently reviewed. If genuine independence is required,
use `second-opinion` under its cost guardrails or stop and ask.

## 8. Verify, escalate, and finish

A child must stop and return evidence when:

- Work expands beyond owned files or acceptance criteria.
- Repository behavior contradicts the packet or invalidates an assumption.
- A public API, schema, migration, permission, compatibility, product, or architecture
  decision appears.
- Auth, secrets, destructive operations, financial correctness, concurrency,
  deployment control, or irreversible data appears unexpectedly.
- The same validation failure survives two evidence-based attempts.
- It is guessing about hidden state or cannot explain the failure.
- Integration reveals conflicting edits or architectural coupling.

Use the smallest responsible response: revise the bounded packet, increase effort in
the same class, use a stronger worker/advisor, return to architecture/user judgment,
or stop. Do not automatically jump to a maximum-effort panel or silently widen scope.

Finish when acceptance and validation pass and review finds no fixes worth doing now;
remaining findings are optional/deferred; a decision needs the user; or the selected
review gate reaches its cap. Routine orchestration normally uses one review and at
most one focused follow-up.

Report the execution shape, material child route evidence, changes and validation,
conflicts or decisions, residual risks, deferred work, and whether validation was
independent or self-validated.
