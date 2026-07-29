---
name: implement-solution
description: Explicitly invoked premium coding workflow that applies repository consensus, proportional TDD, KISS/YAGNI, demonstrated DRY, and contextual SOLID/FP to the smallest maintainable implementation.
allowed-tools: "Read,Edit,Write,Grep,Glob,Bash(git:*),Bash(make:*),Bash(npm:*),Bash(npx:*),AskUserQuestion"
model-tier: premium
model: opus
effort: high
version: "2.0.0"
author: "flurdy"
---

# Implement Solution

Implement the smallest maintainable solution that meets the requested outcome. Apply strong engineering judgment before and during coding without replacing the model's native coding ability with a principle checklist.

This is an explicit premium/high implementation route. Invoking it deliberately spends stronger configured capability on the implementation; ordinary bounded coding does not automatically require premium. It is not an always-on gate and should not add ceremony when the repository already makes the right change obvious.

## When to Use

Route through this skill only when the user explicitly invokes `/implement-solution` or explicitly asks for a premium or strongest-capability implementation pass. After that opt-in, use it to:

- apply engineering principles from the start rather than inspect them only afterward;
- find the simplest solution or apply a no-nonsense YAGNI/KISS check;
- avoid over-engineering, unnecessary dependencies, or speculative abstractions;
- simplify an implementation already in progress.

Do not auto-invoke it merely because a request changes code or asks for simplicity. Skip a clearly mechanical edit unless the user explicitly requests this route.

## Boundaries

- `/architect` owns ambiguous, high-blast-radius, security-sensitive, public-contract, migration, and hard-to-reverse decisions. Escalate rather than making those decisions under the banner of simplicity.
- `/diagnose-bug` owns evidence-led diagnosis when the cause of an observed failure is unknown. Return here once the cause and verification contract are established.
- `/pedantic-review` is the post-implementation craft review. This skill shapes the implementation proactively but does not duplicate that report.
- `/verify-task` verifies that finished work meets its requirements and has enough coverage.
- `/clean-code` owns whole-codebase formatting, linting, and warning cleanup. This skill keeps its own change clean without broadening scope to unrelated warnings.

## Usage

```text
/implement-solution <task or request>
/implement-solution --plan <task>       # recommend an approach without editing
/implement-solution --review-current    # simplify the current uncommitted approach
```

## Engineering Judgment

Apply these rules in order when principles conflict:

1. **Required behavior and safety** — correctness, explicit requirements, security, accessibility, compatibility, and data integrity are not simplification opportunities.
2. **Repository consensus** — follow established local architecture, naming, error handling, testing, and language idioms unless the task explicitly changes them.
3. **YAGNI and KISS** — prefer fewer concepts, dependencies, indirections, and extension points while keeping the code readable.
4. **Observable behavior** — design the change so its important behavior can be demonstrated and failures remain diagnosable.
5. **DRY where knowledge is shared** — remove demonstrated duplication of logic or policy whose copies must change together; do not abstract incidental similarity.
6. **SOLID, DDD, and FP where they pay now** — use them to solve a concrete responsibility, dependency, domain-boundary, state, or mutation problem. Do not impose them as style doctrine.

Prefer self-explanatory names, cohesive units, explicit data flow, and existing error conventions over comments or cleverness. A direct local implementation is often better than a reusable abstraction with one consumer.

## Proportional TDD

For new or changed behavior, define the evidence before editing production code.

- For a bug fix, add the smallest regression test that reproduces the failure and confirm it fails for the intended reason before fixing it.
- For new behavior, write a focused behavioral test first when the repository has suitable test infrastructure and the behavior is observable at that boundary.
- For a behavior-preserving refactor, establish that relevant existing tests pass; add tests only for material behavior that is currently unprotected.
- For docs, config, generated files, or mechanical changes, use the repository's appropriate static or direct check rather than manufacturing a unit test.
- For `--review-current` or other existing production changes, do not reconstruct or claim a red phase. Verify the changed behavior now and disclose that test-first evidence is unavailable.

If test-first work is impractical, state the concrete reason and establish the next-best evidence before implementing. TDD is a feedback discipline, not a ceremony or a demand to test implementation details.

## Decision Ladder

After understanding the requested outcome and relevant flow, prefer the first responsible option:

1. **No new work** — the request is unnecessary, already satisfied, or can be met by removing an accidental complication.
2. **Existing repository capability** — reuse an established module, component, helper, convention, or configuration.
3. **Standard library** — use language-provided capability.
4. **Native capability** — use browser, platform, framework, or database capability already available to the project.
5. **Installed dependency** — use an existing dependency according to local conventions.
6. **Minimum readable new code** — add only the code needed, in the existing architectural home.

Do not contort code to climb this ladder. Direct, readable new code is better than awkward reuse or an abstraction that hides the behavior.

## Workflow

### 1. Confirm the outcome and constraints

Read the request, acceptance criteria, and relevant local instructions. Identify the observable outcome, explicit non-goals, important constraints, and whether a consequential decision belongs with the user or `/architect`.

Ask one focused question only when the answer materially changes the implementation. Do not ask questions merely to create process.

### 2. Trace the relevant flow

Read the smallest useful set of files: the entry point, affected behavior, nearby tests, and one or two representative peers. Use targeted Grep/Glob searches for existing names, capabilities, and dependencies before proposing new code. Inspect focused repository history when it adds material context.

```bash
git log --oneline -10 -- <relevant paths>
```

Do not infer that a helper or dependency is absent without checking. Do not start broad external research unless the user asks or a material dependency/integration question remains unresolved.

### 3. Establish the verification contract

Decide what evidence will prove the outcome before editing:

- the focused test and expected initial failure for behavioral work;
- the existing tests that protect a refactor;
- the static, build, or direct check appropriate for non-behavioral work;
- any relevant sad path, boundary, or regression case.

Keep this proportional. Do not turn an obvious local change into a test plan document.

### 4. Choose the smallest responsible approach

Apply the engineering judgment rules and decision ladder. State the approach only when the choice is non-obvious; otherwise proceed without producing a faux design document.

For `--plan`, report concisely:

```markdown
## Simplest responsible approach

- **Outcome:** ...
- **Reuse checked:** ...
- **Choice:** ...
- **Why not smaller / alternatives rejected:** ...
- **Verification:** ...
```

If the request is already satisfied or unnecessary, say so and make no change unless cleanup was explicitly requested.

### 5. Implement in a tight feedback loop

When implementation is requested:

1. Add or identify the focused failing evidence when applicable.
2. Make the minimum readable production change that satisfies it.
3. Run the focused check.
4. Refactor only when it reduces present complexity, demonstrated duplication, or unclear responsibility.
5. Repeat only for the next required behavior.

Use existing conventions and place symbols where their peers live. Preserve error handling and edge cases. Prefer local composition over a new framework, registry, factory, adapter, base class, or extension point without a current need.

Stop and escalate if implementation exposes an unapproved architecture, authorization, migration, public-contract, destructive, or irreversible compatibility decision.

### 6. Verify proportionately

Run the focused evidence first, then the smallest repository-supported lint, type, build, or test checks needed for confidence. Inspect the resulting diff for unrelated changes, accidental complexity, and missing required behavior.

Use `/verify-task` when the task needs a full requirements-and-coverage gate. Do not automatically invoke every review workflow; `/pedantic-review` remains an optional independent craft pass.

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
- add special comments, debt ledgers, scoring, personas, principle reports, modes, or an always-on extension;
- replace evidence with generic principle names;
- create abstractions for imagined future consumers;
- claim repository reuse without reading the candidate;
- force FP, OOP, SOLID, DDD, or a design pattern against local consensus;
- make the solution smaller by silently dropping a required edge case.

## Output

For a recommendation, report only the outcome, reuse checked, chosen approach, and proportional verification needed. For an implementation, list changed paths, checks with outcomes, and any residual risk or escalated decision. Keep principle application visible in the code and evidence, not in a lecture about the principles.
