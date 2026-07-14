---
name: architect
description: Architecture and implementation planning gate for complex or high-blast-radius work. Gathers context, chooses an appropriate planning tier/model, evaluates alternatives and risks, and outputs an implementation-ready plan without editing code.
allowed-tools: "Read,Grep,Glob,Bash(git:*),Bash(bd:*),Bash(find:*),Bash(ls:*),Bash(pwd:*),Bash(rg:*),Skill(second-opinion),AskUserQuestion,mcp__jira__*,mcp__confluence__*"
model-tier: premium-reasoning
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
effort: high
version: "1.0.0"
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
| `second-opinion` | Draft in-session + `/second-opinion validate-plan` after drafting | Need independent validation |
| `all-in` | Premium reasoning + independent second opinion | High-risk, cross-service, security, data migrations |

This skill declares `model-tier: premium-reasoning`, but that is semantic routing metadata,
not a mandate to use Claude/Opus. Prefer the best configured subscription/OAuth reasoning
route first; concrete route mappings live in the shared repo's `MODEL_ROUTING.md`, not here.
Treat Claude OAuth as a deliberate premium judgement lane, not the default for long planning
loops. Treat OpenRouter as metered/capped fallback or experimental routing.

If the user names a specific model/provider, preserve that preference in the plan metadata and,
where possible, recommend how to run the planning session with that route. If unavailable, fall
back to the best configured reasoning tier and say so.

## Instructions

### Tier guard

This skill is `model-tier: premium-reasoning`. Before starting, check which model you are
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
  `all-in` before adding independent/metered review.
- For moderate work, ask with `AskUserQuestion`:
  - `standard` — good enough, stay in-session
  - `premium` — spend stronger reasoning budget
  - `second-opinion` — draft then validate externally
  - `all-in` — premium + external validation
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
2. **Repository shape**
   - `pwd`
   - `git status --short`
   - `git branch --show-current`
   - `git ls-files | head -200` or targeted `find`/`rg` for the relevant area
3. **Existing patterns**
   - Search for similar features, APIs, migrations, tests, contracts, or components.
   - Read representative files. Prefer a few high-signal files over broad scanning.
4. **Docs/designs**
   - If Jira or the user links to Confluence, fetch the page.
   - If Figma/design details are required, mention the needed design context and use the
     available Figma/context tooling if present in the runtime.

Keep the context summary concise and cite file paths clearly.

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

### Recommended approach
<the proposed architecture/design>

### Alternatives considered
1. <alternative> — rejected/accepted because ...
2. ...

### Implementation slices
1. <small, reviewable slice>
2. ...

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
<cheap-bulk is safe | use standard-coding | keep premium-reasoning/premium-review for implementation>
```

### 5. Second Opinion, When Requested

If the tier is `second-opinion` or `all-in`:

1. First draft the full architecture plan.
2. Invoke `/second-opinion validate-plan` with the plan text and relevant context summary.
3. Compare the response against the draft.
4. Output:
   - What changed after the second opinion
   - Remaining disagreements or uncertainty
   - Final recommended plan

If `/second-opinion` is unavailable or the requested external CLI is not configured, continue
with the in-session plan and explicitly note that independent validation was skipped.

### 6. Guardrails

- Do not implement code changes.
- Do not create or mutate Jira issues/beads unless the user explicitly asks after the plan.
- Prefer small, reversible implementation slices.
- Flag YAGNI: avoid introducing new abstractions unless they pay for themselves now.
- Call out when the right answer is “do the simple thing” rather than architecting.
- If requirements are unclear, list open questions and recommend the smallest discovery step.
- End with the next concrete action the implementation agent should take.
