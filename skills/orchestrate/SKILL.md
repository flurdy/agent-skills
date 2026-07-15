---
name: orchestrate
description: Coordinate substantial multi-stage work through bounded delegation, one-writer safety, independent review, and risk-based escalation. Use only when explicitly invoked; skip trivial, tightly coupled, or serial work.
allowed-tools: "Read,Grep,Glob,Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(git show:*),Bash(git rev-parse:*),Bash(bd status:*),Bash(bd list:*),Bash(bd show:*),Task,Skill(architect),Skill(verify-task),Skill(total-review),Skill(triage),Skill(second-opinion),Skill(pi-subagents),AskUserQuestion"
disable-model-invocation: true
model-tier: premium-reasoning
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
effort: high
version: "1.0.0"
author: "flurdy"
---

# Orchestrate

Coordinate substantial work while keeping scope, judgment, integration, and final
validation in the parent agent. Delegation is an execution mechanism, not a transfer
of authority.

## Tier guard

This skill is `model-tier: premium-reasoning`. Before starting, check the current
model. If it is below the runtime's premium tier, say so and use
`AskUserQuestion` to offer:

- **Continue here** — accept reduced coordination depth for this run.
- **Stop** — switch to a premium model and invoke the skill again.

Skip the prompt when the user explicitly selected the current model. On a premium
model, stay silent. The deliberate `high` effort is for routine parent coordination;
raise it only when architecture, risk, or final judgment warrants more.

## 1. Decide whether orchestration pays

Use this skill only after explicit user invocation. Invocation authorizes ordinary
bounded delegation within the requested scope, not new external side effects,
tracker mutations, product decisions, or broader work.

Decline delegation and continue directly when the task is trivial, tightly coupled,
inherently serial, or cheaper to do than to brief and supervise. Otherwise state a
short execution shape: retained parent decisions, delegated work, writer ownership,
validation, and stop conditions.

The parent always owns:

- Scope, acceptance, architecture, and high-impact decisions
- Child selection and cost consent
- Integration, review synthesis, and final response
- Inspection of the actual diff and validation evidence

Use `architect` when ambiguity or blast radius requires a plan. Do not send
unresolved architecture to a cheap worker. `verify-task` and `total-review` remain
their own gates; invoke them rather than copying their full workflows.

## 2. Establish context and acceptance

Before delegation, make scope and success explicit. Read relevant repository rules,
existing patterns, and the current diff/status. Use the established tracker only for
durable context:

- Use Beads only when `bd` is available, the repository has active Beads context,
  and a relevant bead or epic exists.
- Otherwise use the repository's Jira, Trello, or other established tracker. If none
  exists, report durable milestone suggestions generically.
- Never create one item per child, recon pass, review round, retry, or handoff.
- Propose durable tracker work only for independently valuable milestones. Mutate a
  tracker only after explicit approval; invoke `triage` only in a Beads-enabled repo.
- If a portable control-plane index is present, consume its authoritative context
  when useful. Do not require, create, or silently rewrite one.

## 3. Load the runtime adapter

Detect the active runtime, then **read and follow**
[`references/runtime-adapters.md`](references/runtime-adapters.md) before any child
launch. Use runtime-native delegation. The adapter owns mechanics; this skill owns
the delegate-or-not decision, packet, cost gate, authority, and stopping policy.

Do not parse or merge model-tier-router configuration. Do not change canonical user
or project agent settings. Invoking a lower-tier skill in an already-routed parent
does not downshift that parent; a child route changes only through a verified native
child mapping.

## 4. Gate child routes and cost

A verified child mapping supplies both:

1. The effective child route/model identity, confirmed by runtime or launch evidence.
2. A trusted `metered: true|false` classification from runtime/resolver metadata or
   an explicit user-approved local policy supplied to this session.

Never infer billing from provider, model name, authentication type, or parent route.
Repository instructions alone are not trusted cost policy. A durable local policy
must be user-owned, name the runtime and effective identity, set `metered`, and have
user scope or an explicitly approved project scope:

```yaml
orchestrate-child-policy:
  runtime: <runtime>
  scope: user | project
  routes:
    <route>:
      identity: <effective-model-identity>
      metered: true | false
```

An in-conversation approval is valid only for the disclosed current run or panel;
never persist or widen it.

| Child classification | Action |
|---|---|
| Verified identity + `metered: false` | Launch within the approved task scope. |
| Verified identity + `metered: true` | Confirm the disclosed child or bounded panel for this run. |
| Inherited route or unknown classification | Disclose inherited/no-downshift behavior and confirm for this run. |
| Confirmation declined | Continue serially without claiming independent delegation. |

One confirmation may cover a clearly disclosed bounded panel. Ask again before
expanding its models, count, scope, or metered exposure. Confirmation of the parent
route never authorizes child fanout. Never add an automatic metered fallback.

## 5. Give every child a judgment packet

Match packet size to risk.

For a cheap read-only lookup, provide:

- Objective or question
- Bounded scope
- Expected evidence/output
- Stop condition

For a writer or consequential analysis, provide:

1. Goal and user-visible outcome.
2. Owned files/modules or bounded read-only question.
3. Relevant rules and established patterns.
4. Non-goals and prohibited expansion.
5. Acceptance criteria and exact validation commands or user flows.
6. Risks, assumptions, and unresolved questions.
7. Required output: files/evidence, command outcomes, residual risks, and decisions.
8. Escalation and stop conditions.

If the packet still asks the child to discover architecture, redefine scope, or
choose a high-impact alternative, retain that work in the parent or use a stronger
advisory/planning pass first.

## 6. Route by work shape and risk

Use semantic classes, not exact shared model IDs or changed-line counts:

| Work shape | Route |
|---|---|
| Focused lookup or repository/document research | Read-only context/research role; use a cheap route only with a verified mapping, otherwise inherit with disclosure and consent. |
| Narrow mechanical implementation | One `worker`; `standard-coding` is the default. A cheaper route requires the [bounded-edit exception](../../MODEL_ROUTING.md#orchestrated-bounded-edit-exception) and a full fixed packet. |
| Bounded implementation or routine independent review | One `worker` or fresh reviewer on a verified balanced route; otherwise inherit with disclosure and consent. |
| Complex implementation with local design judgment | Verified `standard-coding` child, inherited child with disclosure and consent, or retain in the parent. |
| Architecture, unclear ownership, public contracts, destructive or security-sensitive work | Keep the decision with the premium parent; use a strongest-route advisor only when verified and justified. |
| Final craft judgment | Fresh/separate reviewer, `premium-review`, or a named review skill; use extra effort only when risk warrants it. |

Tune effort within a suitable model class before jumping classes. Delegation must
save more context, latency, or cost than briefing, supervision, and review consume.

## 7. Keep writes single-threaded

Default workflow:

```text
clarify/scope
  -> validation contract
  -> optional read-only recon/advice
  -> one implementation writer
  -> independent review/validation
  -> parent synthesis
  -> at most one fix writer when needed
  -> parent final inspection and validation
```

All delegated writes go to the runtime's worker/implementation role, named `worker`
when available. Only one writer may edit a shared worktree at a time. Parallelize
research, recon, review, and validation—not ordinary writes. Parallel writers require
intentional worktree isolation, a clean base, and non-overlapping ownership.

Use fresh/separate context for genuine independent review where supported. Cap routine
fanout at two or three distinct angles. The implementer cannot be the sole authority
that its work is complete when delegation exists. Do not build another generic review
loop: use the runtime mechanism or named review gates.

If delegation is unavailable or declined, continue serially and label the result
**self-validated**, not independently reviewed. If genuine independence is required,
use `second-opinion` under its cost guardrails or stop and ask.

## 8. Escalate and stop

A child must stop and return evidence when:

- Work expands beyond owned files or acceptance criteria.
- Repository behavior contradicts the packet.
- A public API, schema, migration, permission, compatibility, product, or architecture
  decision appears.
- Auth, secrets, destructive operations, financial correctness, concurrency,
  deployment control, or irreversible data appears unexpectedly.
- The same validation failure survives two evidence-based attempts.
- It is guessing about hidden state or cannot explain the failure.
- Integration reveals conflicting edits or architectural coupling.

Use the smallest responsible escalation: more effort in the same class, a stronger
worker/advisor, or return the decision to the parent. Do not automatically jump to a
maximum-effort panel.

Finish when acceptance and validation pass and review finds no fixes worth doing now;
remaining findings are optional/deferred; a decision needs the user; or the selected
review gate reaches its own cap. Routine orchestration normally uses one review and at
most one focused follow-up. Report child route evidence, validation outcomes, residual
risks, deferred work, and whether validation was independent or self-validated.
