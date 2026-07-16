# Orchestrate skill

`/orchestrate` is the single explicit entry point for coordinating delegated work.
Version 1 is deliberately conservative: it is a safe delegation and integration
workflow, not yet a persistent or fully adaptive task scheduler.

## Current scope

The parent agent retains outcome, scope, architecture, decomposition, integration,
conflict resolution, and final validation. The skill provides:

- a delegation return-on-investment decision;
- explicit outcome, ownership, acceptance, and stop conditions;
- compact dependency-aware work graphs with retained decisions, material
  uncertainties, integration seams, and declined-fanout reasoning;
- bounded child judgment packets and result states;
- trusted child-route and cost consent;
- one-writer execution with safe read-only parallelism;
- independent review and parent inspection of the actual diff;
- evidence-based escalation and disclosed serial fallback.

Its normal execution shape is intentionally shallow:

```text
scope and acceptance
  -> optional independent recon/advice
  -> one implementation writer
  -> integration inspection
  -> independent review/validation
  -> at most one focused fix pass
  -> parent final validation and response
```

## Capability maturity

| Capability | Current maturity |
|---|---|
| Safe child launch and consent | Implemented |
| Bounded judgment packets | Implemented |
| One-writer coordination | Implemented |
| Independent review | Implemented |
| Risk escalation and stopping | Implemented |
| Dependency-aware decomposition | Implemented; compact parent-owned work graph, not adaptive scheduling |
| Structured ongoing communication | Minimal; native progress when available, result envelope otherwise |
| Dynamic replanning | Minimal |
| Conflict adjudication | Minimal |
| Evidence-led verification design | Partial |
| Cross-child shared work state | Not implemented |

These limitations are scope statements, not instructions to simulate unsupported
capabilities during a run.

## Boundaries and ownership

- [`SKILL.md`](SKILL.md) owns the operational delegation workflow.
- [`references/work-graph.md`](references/work-graph.md) owns dependency-aware
  decomposition, split/collapse rules, readiness, and critical dependency paths.
- [`references/child-routing-policy.md`](references/child-routing-policy.md) owns
  trusted identity, metered classification, consent, route changes, and semantic
  child classes.
- [`references/runtime-adapters.md`](references/runtime-adapters.md) owns Pi, Claude
  Code, Codex, and fallback launch mechanics.
- [`../../MODEL_ROUTING.md`](../../MODEL_ROUTING.md) owns repository-wide model policy.
- `/architect` owns architecture and implementation planning when ambiguity or blast
  radius warrants it.
- `/verify-task`, `/total-review`, and specialist review skills own their complete
  verification workflows.
- `pi-subagents` owns Pi execution lifecycle and inter-agent mechanics.
- A present `/control-plane` index may provide authoritative project context, but
  orchestration must work without it and never silently rewrite it.

## Roadmap

Beads epic `skills-rd6`, **Evolve orchestrate into adaptive task orchestration**,
tracks the next capability step:

1. Dependency-aware task decomposition — implemented in v1.2
2. Adaptive serial/parallel delegation strategy
3. Child communication and handoff protocol
4. Evidence ledger and conflict synthesis
5. Assumption-driven replanning
6. Proportionate verification strategy
7. Context efficiency and reuse

Related standalone work:

- `skills-88v.3` introduces the portable `focused-coding` tier and renames the
  stronger implementation class to `advanced-coding`.
- `skills-88v.6` tracks the portable control-plane project-context pattern.

Do not split these capabilities into separate user-facing orchestration commands by
default. The intended design is one `/orchestrate` control loop that composes named
planning, execution, routing, and verification owners.

## Evidence

Initial cross-runtime dogfood and policy corrections are recorded in
[`../../plans/orchestrate-dogfood-evidence.md`](../../plans/orchestrate-dogfood-evidence.md).
Dependency-aware decomposition dogfood is recorded in
[`../../plans/orchestrate-decomposition-dogfood-evidence.md`](../../plans/orchestrate-decomposition-dogfood-evidence.md).
The original implementation plan is
[`../../plans/orchestrate-skill.md`](../../plans/orchestrate-skill.md).
