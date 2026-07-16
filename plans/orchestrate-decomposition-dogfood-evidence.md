# Orchestrate dependency-aware decomposition dogfood

## Scope

- Bead: `skills-rd6.1`
- Parent epic: `skills-rd6`
- Method under test: `skills/orchestrate/references/work-graph.md`
- Evidence policy: preserve tracker facts, label inference, and do not create or mutate
  dependency relationships during dogfood.

This evidence applies the compact work-graph method to the parent epic and to the
method's own implementation. It tests useful decomposition and the deliberate refusal
to equate work units with child launches.

## Scenario 1 — `skills-rd6` epic

### Outcome frame

```text
outcome: /orchestrate becomes outcome- and dependency-driven while retaining one
user-facing entry point and parent authority.
non-goals: persistent scheduling; duplicated runtime routing; duplicated architect or
verification workflows; one tracker item per child launch.
acceptance: all seven capability children are integrated and the epic acceptance
criteria are evidenced in the operational skill and documentation.
```

### Retained decisions

| ID | Decision | Owner | Status | Blocks |
|---|---|---|---|---|
| D1 | Keep one explicit `/orchestrate` entry point | Parent/user | Decided in prior scope work | — |
| D2 | Keep architecture, integration, and final judgment in the parent | Parent | Decided in v1 policy | — |
| D3 | Runtime routing and execution mechanics stay in their existing owners | Parent | Decided in v1 policy | — |

### Material uncertainties

| ID | Unknown | Why it matters | Resolution evidence | Blocks |
|---|---|---|---|---|
| U1 | Relative duration of the seven capability children | Prevents duration-backed critical-path claims | Completion evidence from later child implementations | Precise timing only |
| U2 | Whether later implementation exposes additional hard dependencies | Could alter ready sets and integration order | Evidence from each child; update Beads only through normal approved tracking flow | Future graph revisions |

Neither uncertainty justifies speculative reconnaissance now. Existing tracker edges
are sufficient to identify current readiness and candidate dependency spines.

### Work graph

Tracker evidence was gathered with read-only `bd show`, `bd blocked`, and child
queries. Parent-child relationships are hierarchy, not blocking edges. W1–W7 preserve
tracker-backed capability relationships; W8 is a method-derived epic integration gate,
not a Beads dependency.

| ID | Deliverable | Ownership boundary | Hard dependencies | Integration point | Done evidence |
|---|---|---|---|---|---|
| W1 | Dependency-aware decomposition | `skills-rd6.1` | — | Main outcome/execution sections | Compact method documented and dogfooded |
| W2 | Adaptive delegation strategy | `skills-rd6.2` | W1 | Work graph ready set → execution shape | Strategy AC satisfied |
| W3 | Communication and handoff protocol | `skills-rd6.3` | W1 | Work-unit state and escalation | Protocol AC satisfied |
| W4 | Evidence ledger and conflict synthesis | `skills-rd6.4` | W3 | Child claims/results → parent synthesis | Ledger/adjudication AC satisfied |
| W5 | Assumption-driven replanning | `skills-rd6.5` | W1, W4 | Evidence changes the graph | Replanning AC satisfied |
| W6 | Proportionate verification strategy | `skills-rd6.6` | W1 | Work-unit acceptance → validation contract | Verification AC satisfied |
| W7 | Context efficiency and reuse | `skills-rd6.7` | W3 | Shared state/context handoffs | Context AC satisfied |
| W8 | Epic integration (method-derived) | Parent-owned `/orchestrate` policy and docs | W1–W7 (epic completion gate, not a tracker edge) | `SKILL.md`, references, maturity docs | Epic AC and final validation pass |

### Readiness and critical dependency candidates

At observation time:

```text
ready/in progress: W1
blocked: W2 <- W1; W3 <- W1; W4 <- W3; W5 <- W1 + W4;
         W6 <- W1; W7 <- W3; W8 <- W1-W7
critical dependency candidates (no duration evidence):
  W1 -> W3 -> W4 -> W5 -> W8
  W1 -> W3 -> W7 -> W8
  W1 -> W2 -> W8
  W1 -> W6 -> W8
```

The first chain is the longest known dependency spine, but it is not called the timed
critical path because U1 remains unresolved.

### Fanout decision

The graph exposes later concurrency opportunities after W1, but does not authorize
launches. No child agents or new tracker items were created for W2–W8. Execution-shape
selection remains owned by `skills-rd6.2`.

## Scenario 2 — implementing `skills-rd6.1`

### Outcome frame

```text
outcome: /orchestrate gains a compact, conditional work-graph method that separates
decisions, uncertainties, executable deliverables, dependencies, and integration.
non-goals: adaptive scheduling; communication protocol; evidence ledger; dynamic
replanning; full verification-strategy design; routing/runtime changes.
acceptance: method is documented, integrated into the main workflow, dogfooded on a
non-trivial graph, and explicitly declines low-value fanout.
```

### Retained decisions

| ID | Decision | Owner | Status | Blocks |
|---|---|---|---|---|
| D1 | Keep detailed decomposition policy in a conditional reference | Parent | Decided | — |
| D2 | Expose topology/readiness but leave execution-shape choice to `skills-rd6.2` | Parent | Decided | — |
| D3 | Conceptual work units do not imply child launches or tracker items | Parent | Decided | — |

No unresolved architecture remained after the planning pass. Ordinary wording and
layout choices stayed within the implementation boundary.

### Work graph

| ID | Deliverable | Ownership boundary | Hard dependencies | Integration point | Done evidence |
|---|---|---|---|---|---|
| I1 | Work-graph method | `references/work-graph.md` | D1–D3 | Main skill decomposition stage | Method covers split/collapse, readiness, integration, and critical candidates |
| I2 | Operational integration and maturity update | `SKILL.md`, `README.md` | I1 | Existing outcome and execution-shape sections | Links resolve; version/maturity match behavior |
| I3 | Dogfood evidence | This file | I1, I2 | Parent review of method usability | Both epic and implementation scenarios recorded |
| I4 | Independent review and repository validation | Read-only review plus checks | I2, I3 | Parent final synthesis | No must-fix findings; required checks pass |

```text
ready at start: I1
critical dependency candidates: I1 -> I2 -> I3 -> I4
integration: parent reconciles reference semantics with SKILL.md and README.md
```

### Declined fanout

I1–I3 were deliberately kept with one parent writer:

- all are Markdown policy with shared terminology and tight semantic coupling;
- I2 depends directly on the method settled in I1;
- I3 feeds discoveries back into both documents;
- separate writers would duplicate context and increase reconciliation cost;
- no independent implementation artifact could safely land before the shared method.

Only I4 benefits from fresh independent context. This is a successful “decompose but
do not fan out implementation” result, not a failure to orchestrate.

## Validation record

Validated 2026-07-16 after implementation:

| Check | Result | Evidence |
|---|---|---|
| Markdown/link wiring | PASS | Relative links resolve; `SKILL.md` reports v1.2.0; README maturity matches the implemented boundary |
| Whitespace/diff integrity | PASS | `git diff --check` |
| Claude assembly preview | PASS | `make dry-run` |
| Codex assembly preview | PASS | `make dry-run-codex` |
| Claude managed-link health | PASS | `make doctor` |
| Codex managed-link health | PASS | `make doctor-codex` |
| Parallel-session scope guard | PASS | Task changes are confined to orchestrate policy/docs and this evidence file; pre-existing `skills-4xa`/`skills/README.md` work was not modified by this task |
| Independent policy review | PASS after fixes | Initial review found ambiguous graph-entry precedence and unclear W8 provenance; both were corrected |
| Focused independent re-review | PASS | Confirmed direct-work precedence, method-derived W8 labeling, sibling-capability boundaries, and no remaining must-fix AC issue |

No executable product code changed, so repository assembly, link integrity, live Beads
comparison, dogfood scenarios, and independent policy review are the proportionate
validation. Completion is supported by those outcomes rather than inferred from the
graph alone.
