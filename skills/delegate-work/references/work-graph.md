# Dependency-aware work graph

Use this reference after outcome and acceptance are sufficiently clear and before
choosing children or runtime execution mechanics. It defines the parent-owned shape of
the work; it is not a persistent scheduler, tracker schema, or instruction to delegate
every node.

## 1. Decide whether a graph pays

Continue directly with one bounded work unit when the change is coherent, uses the
same context and ownership, and can be validated as one result. This direct rule takes
precedence: multiple files or artifacts alone do not justify graph ceremony.

Otherwise, build a compact graph when at least one is true:

- two or more independently identifiable deliverables have a material dependency,
  ownership, integration, or execution distinction;
- one result must exist before another can start or be validated;
- a material uncertainty must be resolved before implementation;
- outputs cross an integration seam such as shared files, an interface, or parent
  synthesis;
- distinguishing ready work from blocked work will change execution.

A graph may still conclude that one writer should perform everything serially. Useful
decomposition and useful fanout are separate decisions.

## 2. Frame the accepted outcome

Record only what is needed to constrain decomposition:

```text
outcome: <observable result>
non-goals: <explicit exclusions>
acceptance: <evidence that proves the outcome>
```

If the outcome or acceptance is still disputed, ask the user or return to planning.
Do not hide unresolved scope inside an execution node.

## 3. Separate decisions and uncertainties from execution

### Retained decisions

Record decisions that shape scope, architecture, contracts, ownership, or the graph.
They remain with the parent, user, or `/architect`; they are not worker tasks.

| ID | Decision | Owner | Status | Blocks |
|---|---|---|---|---|
| D1 | <decision> | parent/user/architect | decided/open | W2 |

A bounded writer may still make ordinary local implementation choices allowed by its
judgment packet. Do not promote every coding choice into the retained register.

If an open decision affects a public contract, data model, security boundary,
irreversible action, cross-service ownership, or high-blast-radius design, resolve it
with the user or `/architect` before assigning implementation. Rebuild affected graph
edges after the decision.

### Material uncertainties

Record an uncertainty only when resolving it can change scope, dependency order,
ownership, risk, or acceptance.

| ID | Unknown | Why it matters | Resolution evidence | Blocks |
|---|---|---|---|---|
| U1 | <unknown> | <graph/risk effect> | <smallest useful probe> | W1 |

Do not manufacture reconnaissance for harmless unknowns. Fold minor discovery into a
work unit when it does not alter the graph. A probe is justified only when its expected
information value exceeds briefing and synthesis cost.

## 4. Define bounded work units

Each work unit must produce an identifiable deliverable or finding, an observable
outcome, and evidence capable of proving that outcome.

| ID | Deliverable | Ownership boundary | Depends on | Integration point | Observable outcome | Acceptance evidence |
|---|---|---|---|---|---|---|
| W1 | <artifact/finding> | <files, module, or question> | D1, U1, W0 | <where output is consumed> | <behavior/state that becomes true> | <check, CI evidence, UAT flow, or source proof + expected signal> |

Field rules:

- **Deliverable:** state an output, not an activity such as “investigate” or “work on”.
- **Ownership boundary:** name files/modules for writes or a bounded question/source
  set for read-only work. This does not assign a child yet.
- **Depends on:** include only hard prerequisites supported by requirements,
  repository behavior, or known integration order. Do not encode preference as a
  dependency.
- **Integration point:** identify the seam where this output meets another result:
  shared files, an interface, an input to another unit, or parent reconciliation.
  Use `parent synthesis` when no code seam exists.
- **Observable outcome:** state the user-visible behavior or system state that proves
  the unit has value; do not restate the deliverable or implementation activity.
- **Acceptance evidence:** name the repository-supported command and expected signal,
  named CI check/artifact, minimal manual UAT flow, or source/render evidence that can
  prove the outcome. Do not invent a shell command for documentation-only or inherently
  manual work. Detailed verification strategy remains owned by `/verify-task`,
  `/total-review`, or the relevant specialist gate.

Do not create a separate integration unit unless integration itself produces
meaningful work or evidence. The parent always owns final integration even when a
writer performs the mechanical edit.

## 5. Derive readiness and the critical dependency path

After recording hard edges:

1. **Ready set:** list units whose decisions, uncertainties, and work dependencies are
   resolved. Readiness exposes opportunity; it does not authorize parallel launch.
2. **Blocked set:** list each blocked unit and the smallest unresolved prerequisite.
3. **Critical dependency path:** identify the required blocking chain that gates the
   accepted outcome.

Without credible duration estimates, do not claim precise critical-path timing. Name
the dependency spine or candidate critical chains instead:

```text
ready now: W1, W3
blocked: W2 <- U1; W4 <- W1 + W2
critical dependency candidates: W1 -> W4; U1 -> W2 -> W4
```

The adaptive execution-strategy stage owns the later choice of serial, parallel,
advisory, worktree, or review execution shape. This method supplies topology, ready
work, and integration seams only.

## 6. Apply the split/collapse gate

Keep a proposed unit separate only when all of these are true:

- it has an independently describable deliverable;
- ownership can be bounded without duplicating or conflicting work;
- completion can be assessed independently;
- the dependency, information, isolation, or concurrency value is material;
- coordination cost is lower than the expected benefit.

Collapse it into the parent or an adjacent unit when any of these is true:

- it is merely a sequential implementation step;
- it shares the same files and working context as its neighbour;
- it cannot be validated independently;
- it represents speculative work that may never be needed;
- briefing, route consent, supervision, and synthesis cost more than direct execution;
- splitting would create parallel writers in a shared worktree without intentional
  isolation and integration order.

Record important collapsed/declined fanout decisions briefly when they explain the
shape:

```text
declined split: W2 remains inside W1 — same files, context, and validation; no
independent information or concurrency value.
```

Work units are runtime planning state, not tracker items. Never create one bead, Jira
issue, or Trello card per node, probe, review, retry, or handoff. Propose tracking only
for independently valuable durable milestones under the main skill's tracker rules.

## 7. Hand the graph to execution

Render only the amount the user needs before launch:

```text
retained decisions: <D IDs and short status>
material uncertainties: <U IDs and resolution/blocks>
work graph: <W IDs, deliverables, hard dependencies>
ready/critical: <ready set and dependency spine/candidates>
integration: <seams and parent synthesis point>
declined fanout: <collapsed units or “none”>
```

Then use the main skill to choose the execution shape, create judgment packets, apply
child-route consent, integrate evidence, and verify. A node may be executed by the
parent, mapped to one child, combined with adjacent nodes, or deferred. Never equate
“node” with “child”.
