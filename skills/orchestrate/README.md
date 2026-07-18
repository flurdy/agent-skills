# Orchestrate skill

`/orchestrate` is the single explicit entry point for coordinating delegated work.
It is a safe delegation and integration workflow, and — by decision (`skills-mcn`) —
deliberately not a persistent or adaptive task scheduler. See
[Scope decision](#scope-decision-2026-07-17) for why the adaptive build-out was paused.

## Current scope

The parent agent retains outcome, scope, architecture, decomposition, integration,
conflict resolution, and final validation. The skill provides:

- a delegation return-on-investment decision;
- explicit ownership, stop conditions, and observable outcome → acceptance-evidence pairs;
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
| Structured ongoing communication | By design: native progress when available, result envelope otherwise (`skills-mcn`) |
| Dynamic replanning | Out of scope by decision (`skills-mcn`); model-native judgment |
| Conflict adjudication | Out of scope by decision (`skills-mcn`); model-native judgment |
| Evidence-led verification design | Outcome → evidence pairs preserved through work units and judgment packets; full gates remain in `/verify-task` and `/total-review` |
| Cross-child shared work state | Out of scope by decision (`skills-mcn`) |

These are deliberate scope statements (see [Scope decision](#scope-decision-2026-07-17)),
not instructions to simulate unsupported capabilities during a run.

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

## Scope decision (2026-07-17)

Beads epic `skills-rd6`, *Evolve orchestrate into adaptive task orchestration*, was
**paused** (`skills-mcn`). Only its first step shipped:

1. Dependency-aware task decomposition — implemented in v1.2

The remaining steps — adaptive serial/parallel strategy, child communication protocol,
evidence ledger, assumption-driven replanning, proportionate-verification derivation,
context efficiency — were deferred, not because they are hard but because they are the
wrong artifact for the gain:

- **A skill is a prompt, not code.** Past a couple hundred injected lines, extra prose
  lowers the odds the whole protocol is followed. More words describing adaptive
  coordination do not add capability a premium reasoning model lacks — they add
  ceremony (registers, decision records) the model may perform *instead of* doing the
  work.
- **Deterministic decisions belong in code.** Model/tier/cost routing lives in the
  `model-tier-router` (real code with tests), where the logic is encoded and verified,
  not restated as skill prose.
- **The useful bits were already a sentence.** Proportionate verification still means
  composing `/verify-task` and `/total-review` by risk rather than building a subsystem.
  The bounded addition is to preserve each planned observable outcome and its acceptance
  evidence through work units, writer packets, reviewer packets, and parent integration.

`/orchestrate` therefore stays a bounded-delegation governance skill: outcome and
authority retained by the parent, route/cost consent, one-writer execution, independent
review, escalation, and disclosed serial fallback. Any future adaptive step must be
justified by evidence that a real coordination outcome improved — see `skills-mcn`.

Related standalone work (unaffected by the pause):

- `skills-1hp` replaces the earlier seven-tier routing taxonomy with portable
  `economy`, `standard`, and `premium` capability tiers plus independent effort.
- `skills-88v.6` tracks the portable control-plane project-context pattern.

## Evidence

Initial cross-runtime dogfood and policy corrections are recorded in
[`../../plans/orchestrate-dogfood-evidence.md`](../../plans/orchestrate-dogfood-evidence.md).
Dependency-aware decomposition dogfood is recorded in
[`../../plans/orchestrate-decomposition-dogfood-evidence.md`](../../plans/orchestrate-decomposition-dogfood-evidence.md).
The original implementation plan is
[`../../plans/orchestrate-skill.md`](../../plans/orchestrate-skill.md).
