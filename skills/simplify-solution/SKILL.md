---
name: simplify-solution
description: Apply a lightweight common-sense YAGNI/KISS lens to find the smallest maintainable implementation before or during ordinary coding.
allowed-tools: "Read,Edit,Write,Grep,Glob,Bash(git:*),Bash(make:*),Bash(npm:*),Bash(npx:*),AskUserQuestion"
model-tier: standard
model: sonnet
effort: high
version: "1.0.0"
author: "flurdy"
---

# Simplify Solution

Find and implement the smallest maintainable solution that meets the requested outcome. Use common-sense YAGNI and KISS: reduce concepts, dependencies, and long-term maintenance burden — not character count.

This is an explicit, lightweight implementation lens. It is not an always-on gate and should not add ceremony when the simplest path is already obvious.

## When to Use

Use `/simplify-solution` when the user asks for:

- the simplest solution or a no-nonsense approach
- a YAGNI/KISS check before implementing
- a check for over-engineering or unnecessary dependencies
- a smaller alternative while implementing an ordinary change

Usually skip it when the task is already a clear, local edit with an established pattern, or when the user needs architecture-level decisions. Do not invoke it merely to make a solution look shorter.

## Boundaries

- `/architect` owns ambiguous, high-blast-radius, security-sensitive, public-contract, migration, and hard-to-reverse decisions. Escalate rather than deciding those trade-offs here.
- `/pedantic-review` is the post-implementation craft review. This skill is the proactive, lightweight lens before or during implementation.
- `/verify-task` verifies that a finished implementation meets its requirements and has enough coverage.
- The conditional prior-art planning work (`skills-ym4`) may require external research when local evidence is insufficient. This skill starts with local reuse and does not broaden into external research unless the user asks or the planning workflow requires it.
- The effectiveness-evaluation work (`skills-fdy`) measures whether this skill changes outcomes; do not invent outcome metrics or debt tracking during ordinary use.

## Usage

```text
/simplify-solution <task or request>
/simplify-solution --plan <task>       # recommend an approach without editing
/simplify-solution --review-current    # simplify the current uncommitted approach
```

## Decision Ladder

After understanding the requested outcome and relevant flow, prefer the first responsible option:

1. **No new work** — the request is genuinely unnecessary, already satisfied, or can be met by removing an accidental complication.
2. **Existing repository capability** — reuse an established module, component, helper, convention, or configuration.
3. **Standard library** — use language-provided capability.
4. **Native capability** — use browser, platform, framework, or database capability already available to the project.
5. **Installed dependency** — use an existing dependency according to local conventions.
6. **Minimum readable new code** — add only the code needed, in the existing architectural home.

Do not treat the ladder as a rule to contort code around. A direct, readable local implementation is better than awkward reuse or an abstraction that hides the behavior.

## Workflow

### 1. Confirm the outcome and constraints

Read the request, acceptance criteria, and relevant local instructions. Identify:

- the observable outcome and explicit non-goals;
- safety, compatibility, accessibility, operational, and domain constraints;
- whether an existing pattern makes the solution obvious.

If the goal or a consequential trade-off is unclear, ask one focused question or escalate to `/architect`. Do not ask questions merely to create process.

### 2. Trace the relevant flow

Read the smallest useful set of files: the entry point, affected behavior, and nearby tests or peers. Search for existing names, capabilities, and dependencies before proposing new code.

```bash
# Use targeted searches based on the request and relevant directories.
rg "<relevant concept>" <relevant paths>
git log --oneline -10 -- <relevant paths>
```

Do not infer that a dependency or helper is absent without checking the repository. Do not start broad external research by default.

### 3. Choose the smallest responsible approach

Apply the decision ladder and state the choice concisely:

```markdown
## Simplest responsible approach

- **Outcome:** ...
- **Reuse checked:** ...
- **Choice:** ...
- **Why not smaller / alternatives rejected:** ...
- **Verification:** ...
```

If the request is already satisfied or unnecessary, say so clearly and make no change unless the user asks for cleanup.

When the choice is obvious after local inspection, keep this to a few sentences and proceed. Do not produce a faux design document.

### 4. Implement only what the request needs

When implementation is requested, use existing conventions and place the change where its peers live. Prefer:

- direct code over a one-consumer abstraction;
- local composition over a new framework, registry, factory, adapter, or extension point without a current consumer;
- an existing dependency over adding a new one, but not a tortured use of a dependency that does not fit;
- deletion or a smaller edit when it genuinely meets the outcome.

Keep the work scoped. If the investigation exposes architecture, authorization, migration, public-contract, or irreversible compatibility decisions, stop and escalate rather than simplifying away the decision.

### 5. Verify proportionately

State and run the smallest checks that demonstrate the outcome:

- a targeted test or existing test suite for behavioral changes;
- lint/type/build checks when relevant to the project;
- a direct manual or command-line check when that is the repository's appropriate evidence.

A docs-only or demonstrably no-op decision may need no automated test; say why. Use `/verify-task` before completion when the task needs a full requirements-and-coverage gate.

## Guardrails

Never simplify away or weaken:

- explicit requirements or accepted behavior;
- trust-boundary validation, authorization, security, privacy, or abuse protections;
- accessibility or user-facing error handling;
- data-loss prevention, integrity, backups, or rollback requirements;
- required compatibility, public contracts, migrations, or operational observability;
- domain correctness or tests proportionate to the behavior and risk.

Do not:

- optimise for one-line solutions, LOC counts, cleverness, or code golf;
- add special comments, debt ledgers, scoring, personas, modes, or an always-on extension;
- replace evidence with generic “YAGNI” claims;
- create abstractions for imagined future consumers;
- claim repository reuse without reading the candidate;
- make the solution smaller by silently dropping a required edge case.

## Output

For a recommendation, report the outcome, reuse checked, chosen approach, and proportional verification in no more detail than the task needs. For an implementation, also list changed paths and checks run. Name any decision that was escalated to `/architect` or deferred to the user.
