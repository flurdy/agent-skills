# `/orchestrate`: current design and thin-core candidate

> **Status:** Decision record, not an implementation plan. The **after** state below is a
> candidate defined by the traceability audit in `skills-lac.2`; it has not been built,
> dogfooded, or approved for implementation.
>
> **Purpose:** Make the proposed simplification legible without implying that existing
> safeguards can be removed now. The candidate is deliberately a smaller governance
> layer, not a new scheduler or a replacement for runtime-native delegation.

## Evidence and decision basis

- The initial multi-model review and the focused Sol/Fable adjudication are recorded in
  Beads `skills-lac.1`.
- The source-traceability audit—with every current normative rule, ownership boundary,
  and nine dogfood corrections mapped to a candidate destination—is recorded in
  `skills-lac.2`.
- The current skill's prior dogfood evidence is
  [`orchestrate-dogfood-evidence.md`](orchestrate-dogfood-evidence.md) and
  [`orchestrate-decomposition-dogfood-evidence.md`](orchestrate-decomposition-dogfood-evidence.md).
- The current scope decision is in
  [`../../skills/orchestrate/README.md`](../../skills/orchestrate/README.md): adaptive
  scheduling and similar process-heavy extensions are deliberately paused.

The reviews support a **bounded thin-core candidate**, not an immediate cull. They do
not establish that a shorter prompt improves adherence, cost, latency, or quality.

## Before: current artifact

`/orchestrate` is an explicit-invocation, premium/high delegation-governance skill. It
keeps authority and final validation with the parent, while using runtime-native child
mechanisms.

| Current artifact | Current role | Current size |
|---|---|---:|
| [`SKILL.md`](../../skills/orchestrate/SKILL.md) | Main policy: ROI, parent authority, outcome/evidence, packets, role/risk assignment, integration, review, escalation | 268 lines / 1,936 words |
| [`child-routing-policy.md`](../../skills/orchestrate/references/child-routing-policy.md) | Trusted child identity, metering classification, consent, mismatches, durable policy shape, semantic bridge | 94 / 593 |
| [`runtime-adapters.md`](../../skills/orchestrate/references/runtime-adapters.md) | Pi, Claude Code, Codex, and generic runtime mechanics | 86 / 658 |
| [`work-graph.md`](../../skills/orchestrate/references/work-graph.md) | Conditional dependency-aware decomposition, tables, readiness, split/collapse tests | 175 / 1,159 |
| [`README.md`](../../skills/orchestrate/README.md) | Scope/maturity/ownership explanation and adaptive-work pause | 116 / 735 |

### What works today

The current artifact expresses real safeguards:

- delegation is execution, not a transfer of parent authority;
- a child receives bounded ownership and evidence expectations;
- shared worktree writes are single-writer by default;
- the parent reconciles actual diff and validation evidence rather than trusting a child
  completion report;
- unknown or metered child exposure needs fresh consent and cannot reuse parent-route
  approval;
- stale route evidence, scope expansion, consequential decisions, and repeated
  evidence-based failures return control to the parent;
- serial fallback is disclosed as **self-validated**, not independent review.

Dogfood also found real defects: route evidence became stale after a parent route
change, and Pi's prose-review acceptance disable needed an explicit reason object.
Those findings justify keeping a safety core.

### What is costly or unclear today

The current skill and references repeat some concepts—outcome/evidence, risk tiers,
runtime mechanics, and review shape. A Pi run that loads the relevant references may
also load the installed `pi-subagents` skill, which already owns lifecycle, worktree,
context, acceptance, and intercom mechanics.

The current documentation also risks overstating prompt-level controls as
"Implemented" even when the runtime, not the Markdown skill, enforces them. The
existing dogfood does **not** prove a verified lower-cost writer path, a better direct
execution alternative, or that the work-graph tables outperform ordinary planning.

## After: candidate thin-core design

The candidate retains the safety semantics while reducing duplicate process prose. It
is not a commitment to a specific line count; the planning target is a typical
launch-path budget below roughly 200 lines, with optional references loaded only when
they add independent value.

| Candidate artifact | Intended role | Change from current |
|---|---|---|
| `skills/orchestrate/SKILL.md` | Portable governance core: authority, ROI, outcome/evidence, compact packet/result, one writer, integration, review, escalation, serial fallback | Condense to roughly 100–130 lines; remove duplicated routing, runtime, graph-table, and tier-assignment detail |
| `references/launch-safety.md` | Portable child preflight and consent invariants | Replaces the current child-routing policy's normative core; does **not** define a portable settings/YAML format |
| `references/runtime-index.md` | Short index of runtime-specific evidence hooks and canonical runtime owners | Replaces the adapter's duplicated mechanics; Pi points to `pi-subagents`, while Claude/Codex retain only capability/evidence/fallback facts |
| `references/decomposition.md` | Optional graph-pays and split/collapse test | Replaces work-graph registers/tables; loaded only if dependencies, uncertainty, or an integration seam materially changes execution |
| `README.md` | Scope, ownership, evidence limits, and maturity labels | Uses `specified`, `runtime-observed`, or `runtime-enforced` rather than treating prose controls as implemented |
| `MODEL_ROUTING.md` | Canonical routing ownership | Atomically names the candidate launch-safety/runtime-index ownership and owns the effort-before-capability escalation rule |

### Candidate core, in plain language

A future thin `SKILL.md` would:

1. Remain explicit-only and retain the advisory premium-tier guard.
2. Decline delegation when direct work is cheaper or acceptance cannot be named.
3. Keep outcome, scope, architecture, integration, and final validation with the parent.
4. Require a compact child contract: outcome; bounded ownership/non-goals; relevant
   context; capable evidence and expected signal; stop/return conditions.
5. Require a result of `complete`, `blocked`, or `needs-decision`, with observed
   evidence, artifacts/changed files, residual risks, and the smallest needed question
   when blocked.
6. Keep one writer per shared worktree; use isolated worktrees only for intentionally
   parallel writers.
7. Require parent inspection of the actual diff/artifact and witnessed evidence.
8. Keep independent review as the current default for delegated writes until comparative
   evidence supports a more selective policy.
9. Compose—not reimplement—`architect`, `verify-task`, `total-review`,
   `second-opinion`, and runtime-native delegation workflows.

### Candidate launch safety

The candidate preserves these invariants, whether enforcement comes from a runtime or
from the parent skill:

- Never infer child billing from provider, model name, authentication, repository text,
  or parent route.
- Treat a route as verified only with fresh pre-launch effective identity **and** trusted
  metered classification. Identity known only after launch is unknown before exposure.
- Re-resolve identity immediately before every launch and after a route-affecting event;
  stale evidence cannot authorize a launch.
- Metered or unknown child exposure requires current-run consent. Consent names one
  child or a disclosed bounded panel; it never persists, widens, or transfers from the
  parent route.
- A post-launch identity mismatch stops further fanout. Declined consent means serial,
  disclosed self-validation. No automatic metered fallback is allowed.
- Durable route classification, if supported, must be user-owned, actively loaded, and
  explicitly scoped. The candidate intentionally does not invent a portable YAML
  configuration format.

`MODEL_ROUTING.md` remains the canonical owner of portable tier/effort semantics and
runtime-local exact model/billing configuration. A candidate must update its current
child-launch ownership wording in the same change; otherwise it would leave a policy
hole.

### Candidate decomposition and runtime boundaries

The optional decomposition reference keeps only questions that can change execution:

- Does a dependency, material uncertainty, or integration seam make a graph worthwhile?
- What decision or evidence blocks the next unit, and what is actually ready now?
- Is each proposed unit an independently valuable deliverable with bounded ownership,
  hard prerequisites, and a real seam?
- Does splitting save more coordination than it costs, or should it collapse back to one
  serial writer?

A conceptual unit is never automatically a child launch or tracker item.

The runtime index does not reproduce runtime manuals. It states that runtime tools own
launch/lifecycle/context/worktree/acceptance mechanics, while `/orchestrate` retains
its portable consent, one-writer, and review-cap policy for that run. For Pi, the
canonical mechanics owner is `pi-subagents`; a Pi-specific acceptance-disable pointer
remains until a stable runtime API makes it unnecessary.

## What does not change

| Invariant | Candidate disposition |
|---|---|
| Explicit user invocation and bounded authorization | Retained |
| Parent authority and final integration | Retained |
| Outcome → evidence → decisive signal; no invented proof | Retained |
| No silent scope/evidence substitution | Retained |
| Fresh child identity and child-spend consent safeguards | Retained |
| One writer in a shared worktree | Retained |
| Parent inspection of actual diff/evidence | Retained |
| Evidence-based stop/escalation conditions | Retained |
| Honest self-validated serial fallback | Retained |
| No per-child/review/retry tracker items | Retained |
| No adaptive scheduler, ledger, persistent policy, or generic review loop | Retained as a non-goal |

## What remains deliberately unproven

The candidate must not claim that it is cheaper, faster, safer, or more compliant just
because it is shorter. The current evidence does not establish:

- that a 100–130-line core improves protocol compliance;
- that risk-based review can safely replace the existing default independent review;
- that target runtimes can always establish child identity and billing classification
  before launch;
- that removing work-graph tables improves real delivery outcomes;
- that an automatic verified-unmetered child route is safe or economical.

## Transition and evidence gates

No candidate implementation exists. If a separate implementation bead is approved, it
must make the following changes atomically:

1. Apply the traceability mapping in `skills-lac.2`.
2. Add the thin core, launch-safety reference, runtime index, and optional compact
   decomposition reference.
3. Amend `MODEL_ROUTING.md` ownership and effort-escalation wording.
4. Correct README maturity and anti-simulation wording.
5. Retain current references as **superseded pending dogfood**; do not delete them.

Only real-product dogfood may authorize later cleanup. It must run on Pi and at least
one other runtime, and exercise unknown-route consent, declined-child serial fallback,
route-change re-preflight, acceptance propagation, one-writer behavior, and independent
review.

Do not delete legacy references, loosen the current review default, or claim a
compliance/cost/latency improvement until the evidence gates recorded in `skills-lac.2`
pass.

## Decision status

The proposed after state is sufficiently specified for a future, separately approved
implementation bead. Until then, the **before** state remains the active behavior.
