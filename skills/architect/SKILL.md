---
name: architect
description: Architecture and implementation planning gate for complex or high-blast-radius work. Produces evidence-backed prior-art decisions, reviewable slices, acceptance evidence, and conditional tracking recommendations without editing code.
allowed-tools: "Read,Grep,Glob,Bash(git:*),Bash(bd:*),Bash(find:*),Bash(ls:*),Bash(pwd:*),Bash(rg:*),WebFetch,WebSearch,Skill(librarian),Skill(second-opinion),AskUserQuestion,mcp__jira__*,mcp__confluence__*"
model-tier: premium
effort: xhigh
version: "1.5.0"
author: "flurdy"
---

# Architect

Architecture and implementation planning before coding.

Use this skill to spend deliberate reasoning budget on the plan, while leaving the
implementation itself free to use a cheaper/faster model when the plan is clear.

## When to Use

Use `/architect` for tasks with architectural uncertainty, high blast radius, or expensive
mistakes:

- Cross-module, cross-service, or multi-repo changes
- New abstractions, boundaries, workflows, or domain model changes
- Database/schema migrations or data backfills
- Public APIs, event schemas, contracts, SDKs, or integrations
- Auth, permissions, privacy, compliance, or security-sensitive work
- Performance, scalability, resiliency, or concurrency-sensitive changes
- Hard-to-reverse decisions
- Ambiguous requirements or multiple plausible approaches
- Work likely to split into several commits, beads, tickets, or PRs
- Any task where the user explicitly asks for architecture, design, planning, or approach

Usually skip it for:

- Small bug fixes with obvious locality
- Copy/text tweaks
- Simple CSS/layout adjustments
- Mechanical dependency bumps
- Straightforward test additions
- Refactors whose pattern and scope are already obvious

## Usage

```text
/architect <task, bead id, Jira key, or question>
/architect ABC-123
/architect bd-456
/architect --tier premium <task>
/architect --tier second-opinion <task>
/architect --tier all-in <task>
/architect --no-prompt <task>
```

## Planning Tiers

Do not expose model churn as the primary interface. Ask for a planning **tier** when the
user has not specified one and the choice matters.

| Tier | Meaning | Use when |
|------|---------|----------|
| `standard` | Standard coding tier | Moderate planning, low ambiguity |
| `premium` | Premium reasoning tier, preferring subscription/OAuth routes | Architectural uncertainty or costly mistakes |
| `second-opinion` | In-session draft + one vendor-independent `/second-opinion validate-plan` review | Need an independent validation pass |
| `all-in` | Premium draft + one bounded `/second-opinion validate-plan --agent all` review batch | High-risk, cross-service, security, data migrations |

This skill declares `model-tier: premium`, but that is semantic routing metadata,
not a mandate to use a particular provider or model. Prefer the best configured premium
route; concrete route mappings, authentication, and metered classification live in the
runtime rather than this skill. Treat external API-backed panels as separately consented,
bounded routes.

If the user names a specific model/provider, preserve that preference in the plan metadata and,
where possible, recommend how to run the planning session with that route. If unavailable, fall
back to the best configured reasoning tier and say so.

## Instructions

### Tier guard

This skill is `model-tier: premium`. Before starting, check which model you are
running as. If it is below the premium tier for this runtime (e.g. Sonnet or Haiku in
Claude Code), say so and ask via `AskUserQuestion` whether to:

- **Continue here** — accept reduced depth on this run
- **Stop** — switch model (`/model` in Claude Code) or rerun in a premium session

Skip the prompt when the user explicitly chose the current model or passed `--no-prompt`.
On a premium model, stay silent and proceed. This guard checks the *engine*; the planning
tier prompt below (step 2) chooses how much reasoning to *spend* — they compose.

### 1. Parse the Request

Identify:

- The task/request/question
- Any Jira key (`[A-Z][A-Z0-9]+-\d+`)
- Any bead id (`bd-...` or project-specific bead id)
- Any explicit planning tier (`--tier standard|premium|second-opinion|all-in`)
- Any explicit model preference (`--model <id>` or a natural-language model mention)
- Whether the user asked not to be prompted (`--no-prompt`)

If the request is missing or too vague, ask one clarifying question before investigating.

### 2. Decide Whether to Prompt for Tier

If no tier/model was specified:

- For clearly high-risk work, default to `premium` and state why; prefer the configured
  subscription/OAuth reasoning route first.
- For very high-risk work (security/data/cross-service), ask whether to use `premium` or
  `all-in` before adding a bounded multi-model review. Explain that `all-in` queries the
  available subscription/OAuth-first CLIs and still requires explicit consent for any route
  that `/second-opinion` classifies as metered or unknown.
- For moderate work, ask with `AskUserQuestion`:
  - `standard` — good enough, stay in-session
  - `premium` — spend stronger reasoning budget
  - `second-opinion` — draft, then request one independent validation
  - `all-in` — premium draft, then request one bounded multi-model validation batch
- If `--no-prompt` was supplied, choose the lowest tier that is responsible and continue.

Never block on model selection if the user has already made the intent clear.

### 3. Gather Context Read-Only

Stay read-only. Do **not** edit code, create branches, create beads, transition tickets, or
commit changes.

Gather only the context needed to plan:

1. **Tracker context**
   - Jira key: fetch the ticket, acceptance criteria, linked Confluence/design links, and
     related issues using Jira tools or `/jira-ticket` when available.
   - Bead id: run `bd show <id>` and inspect dependencies/children when relevant.
   - When `bd status` succeeds in the current repository, use `bd list --status=open` and
     targeted `bd search "<keywords>" --status all` queries to check current and historical
     work for plausible duplicates or related items. Inspect only high-signal matches; this
     is a read-only relevance check, not a backlog audit.
   - When Beads is unavailable, use the established Jira/Trello/other tracker when its
     context is accessible. Otherwise retain a tracker-neutral view of independently
     valuable durable work; do not introduce a tracker merely to satisfy the template.
2. **Repository shape**
   - `pwd`
   - `git status --short`
   - `git branch --show-current`
   - `git ls-files | head -200` or targeted `find`/`rg` for the relevant area
3. **Existing patterns**
   - Search for similar features, APIs, migrations, tests, contracts, or components.
   - Read representative files. Prefer a few high-signal files over broad scanning.
4. **Conditional prior-art research**
   - Trigger this pass when the plan selects or replaces a dependency, introduces a third-party
     integration, proposes a reusable component or abstraction, or addresses a problem likely to
     have an established solution. Also trigger it when the user explicitly asks for buy-vs-build,
     ecosystem options, or prior art.
   - Skip it entirely for routine local changes whose repository pattern and implementation path
     are already clear. Do not render a skipped-research placeholder, require a web search, or turn
     this into a planning gate.
   - When triggered, search in this order and stop as soon as the evidence is sufficient:
     1. Repository code, history, dependency manifests, and nearby docs.
     2. Capabilities, dependencies, and specialist skills already available in the current runtime.
     3. Authoritative external sources only when the local pass leaves a material fit, support,
        compatibility, licensing, or maintenance question unresolved.
   - Reuse `/librarian` when it is available for open-source library internals, implementation
     details, history, and source-backed comparisons. For package availability or public API facts,
     use the runtime's existing search/fetch tools against official registries, vendor docs, specs,
     or upstream source. Do not create a parallel research workflow or rely on unsourced summaries.
   - Keep the lookup bounded to plausible candidates. For each serious candidate, record the source
     evidence, fit, and material gaps, then recommend exactly one classification:
     - **Adopt** — use an existing capability as-is.
     - **Extend** — make a bounded change to the closest-fit capability.
     - **Compose** — combine existing capabilities without introducing a new foundational solution.
     - **Build** — add the minimum new implementation because evidenced gaps rule out the others.
   - A **Build** recommendation must say why the inspected candidates are insufficient. Absence of a
     search result is not evidence; narrow the claim or name the unresolved question instead.
5. **Docs/designs**
   - If Jira or the user links to Confluence, fetch the page.
   - If Figma/design details are required, mention the needed design context and use the
     available Figma/context tooling if present in the runtime.

Keep the context summary concise and cite file paths, official URLs, or upstream source clearly.

### 4. Produce an Architecture Plan

Output a plan that is implementation-ready but does not perform implementation.

Use this structure:

```markdown
## Architect Plan: <short title>

### Planning tier
- Tier: <standard|premium|second-opinion|all-in>
- Model preference: <none|user preference|fallback>
- Why this tier: <one sentence>

### Goal
<what we are trying to achieve>

### Context gathered
- Tracker/docs: ...
- Relevant code paths: ...
- Existing patterns: ...

### Assumptions
- ...

### Prior-art decision
<Include only when step 4's conditional research was triggered; otherwise omit this section entirely.>

| Candidate | Source evidence | Fit / material gaps |
|---|---|---|
| ... | <repository path, official URL, registry entry, spec, or upstream source> | ... |

- Recommendation: <Adopt|Extend|Compose|Build> — <why>
- New implementation justification: <required for Build; otherwise omit>

### Recommended approach
<the proposed architecture/design, incorporating the prior-art decision when present>

### Alternatives considered
1. <alternative> — rejected/accepted because ...
2. ...

### Implementation slices
| # | Slice / deliverable | Observable outcome | Acceptance evidence |
|---|---|---|---|
| 1 | <small, reviewable slice> | <user-visible behavior or system state that becomes true> | <runnable check, named CI evidence, manual UAT flow, or source evidence + expected signal> |
| 2 | ... | ... | ... |

### Tracking recommendation
<One compact recommendation: no additional item, one proposal marked not created, or an expanded epic/children breakdown when genuinely warranted. Include the decisive duplicate/related-work evidence.>

### Test strategy
- Happy path:
- Sad path:
- Edge cases:
- Regression/contract/migration checks:

### Risks and mitigations
- Risk: ... → Mitigation: ...

### Rollout / rollback
<feature flags, migrations, compatibility, observability, rollback plan if relevant>

### Open questions
- ...

### Recommended implementation tier
<standard/high is safe | use premium/high | retain premium/xhigh for implementation or final review>
```

Pair every implementation slice with both an observable outcome and the evidence that proves it.
The pair is the slice's acceptance contract, not a duplicate test plan:

- **Runnable check:** give the repository-supported command and the expected decisive signal.
- **CI evidence:** name the check/artifact and what success demonstrates; a future green status
  without the relevant artifact or commit coverage is not enough.
- **Manual UAT:** give the smallest necessary flow, environment, and expected observation when
  behavior cannot responsibly be proven by automation.
- **Source evidence:** use a rendered preview, link check, schema/config inspection, or specialist
  review for documentation-only or inherently non-executable work.

Do not manufacture a shell command merely to fill the table. If proof depends on unavailable
infrastructure or an unresolved decision, say `TBD`, name the owner or prerequisite, and keep the
slice blocked rather than presenting vague acceptance. The broader **Test strategy** section still
covers cross-slice happy/sad/edge cases and project gates; it should reference rather than restate
the per-slice evidence.

Always render **Tracking recommendation**, but keep it proportionate. Choose exactly one form:

- **No additional item:** the existing Jira ticket, bead, card, or request already owns the whole
  coherent outcome. Say so in one line and cite the decisive duplicate/related-work evidence when
  Beads is active; there is no proposal status to render.
- **One focused item:** one independently valuable durable outcome is not already tracked. Keep it
  to one or two lines: `Proposal — not created`, suggested title, and the essential outcome/scope.
  Add type, priority, acceptance, or dependency detail only when it materially changes the proposal.
- **Epic with children:** use only when several child outcomes are independently reviewable,
  deliverable, and worth tracking even if another child changes. Label the epic and every child
  `Proposal — not created`; give title/type/priority, scope, acceptance, and only genuine blocking
  dependencies. Do not turn every implementation slice into a child.
- **Tracker-neutral breakdown:** use when no tracker is established but the work genuinely needs a
  durable multi-item shape. Keep the same outcome/dependency discipline without prescribing a
  system.

Implementation slices are delivery mechanics, not automatically tracker items. Never propose one
item per test, review pass, commit, subagent, retry, handoff, or other ephemeral activity. If a
proposal is useful, recommend the established creation path (`/triage`, Jira, Trello, or the
project's tracker workflow) as a later explicit user action; the architecture run remains read-only.

### 5. External Validation, When Requested

If the tier is `second-opinion` or `all-in`, perform exactly one review-and-revision pass:

1. Complete the full architecture draft before requesting review.
2. Build a review packet containing:
   - A concise context summary: requirements, constraints, relevant tracker/docs, repository
     evidence with file paths, assumptions, and open questions. Do not include secrets.
   - The complete finalized draft.
   - This review rubric:
     - Requirements coverage and unsupported assumptions
     - Technical feasibility and simpler or stronger alternatives
     - Interfaces, ownership boundaries, and internal/external dependencies
     - Migration, backwards compatibility, and data integrity
     - Security, privacy, permissions, and abuse cases
     - Reliability, failure modes, concurrency, and performance
     - Testability, adequacy of the proposed test strategy, and whether each slice's observable
       outcome is paired with evidence capable of proving it
     - When prior-art research was triggered, whether the candidate evidence supports the
       Adopt/Extend/Compose/Build recommendation and justifies any new implementation
     - Whether tracking recommendations reflect independently valuable durable work, account for
       existing related items, and avoid mirroring implementation mechanics
     - Rollout, rollback, observability, and operational burden
     - YAGNI, unnecessary abstractions, and decisions still missing
3. Invoke the tier-specific route once:
   - `second-opinion`: `/second-opinion validate-plan "<review packet>"`. Keep its default
     vendor-independent selection; do not pass `--agent all`.
   - `all-in`: `/second-opinion validate-plan "<review packet>" --agent all`. This is one
     bounded parallel batch across the available subscription/OAuth-first CLIs, not a sequence
     of follow-up reviews.
4. Invoke only through `/second-opinion`; do not probe authentication or call the CLIs directly.
   Let that skill apply its independence, availability, timeout, and cost rules. When it classifies
   a selected route as metered/BYOK or unknown-cost, ask for explicit consent with
   `AskUserQuestion` immediately before the invocation. Declining that route reduces the attempted
   reviewer set; it does not block the plan.
5. Treat each response as advisory. Check claims against repository, tracker, and documentation
   evidence. Do not use majority vote as truth: one well-evidenced unique finding may outweigh
   agreement, while repeated unsupported claims remain invalid.
6. Revise the draft only for validated findings, then stop. Do not send the revision out for a
   second review batch or loop until reviewers agree.

`--agent all` never includes OpenRouter and must not be rewritten as `--agent consensus`.
The explicit, metered consensus panel tracked separately from this workflow is opt-in only; use
it only when the user separately requests that named `/second-opinion` mode and completes its
fresh-consent flow.

Append this validation record to the final plan:

```markdown
### External validation
- Review tier: <second-opinion|all-in>
- Coverage: <reviewers attempted, succeeded, unavailable, declined, or timed out>
- Reviewer findings:
  - <reviewer attribution>: <material findings>
- Consensus / agreements: <shared findings with supporting evidence; descriptive, not a vote>
- Disagreements: <conflicting recommendations and evidence-based resolution or uncertainty>
- Unique findings: <single-reviewer concerns and their validation status>
- Rejected findings: <non-actionable/incorrect suggestions and why>
- Plan changes: <what changed and why, or "None">
- Residual uncertainty: <unresolved risks/questions, or "None">
```

For partial results, synthesize only the reviewers that returned and identify every unavailable,
declined, or timed-out route; never describe partial coverage as a complete panel. If no external
reviewer succeeds or `/second-opinion` is unavailable, preserve the in-session plan, set coverage
accordingly, and explicitly state that external validation was skipped.

### 6. Guardrails

- Do not implement code changes.
- Do not create or mutate Jira issues/beads unless the user explicitly asks after the plan.
- Label every proposed tracker item as not created and route later creation through the established
  triage/tracker workflow.
- Prefer small, reversible implementation slices with observable outcomes and proportionate proof.
- Do not invent commands for documentation-only or inherently manual acceptance; name the
  necessary source evidence or UAT flow instead.
- Flag YAGNI: avoid introducing new abstractions unless they pay for themselves now.
- Do not claim the ecosystem lacks a solution without bounded, source-backed research; do not run
  that research when a routine local change already has an obvious path.
- Prefer repository and installed-capability evidence before external lookup, and prefer official or
  upstream evidence over commentary when external lookup is warranted.
- Call out when the right answer is “do the simple thing” rather than architecting.
- If requirements are unclear, list open questions and recommend the smallest discovery step.
- End with the next concrete action the implementation agent should take.
