# Implementation Plan: Portable `orchestrate` Skill

## Planning tier

- Tier: all-in
- Primary planning route: premium reasoning in the current Pi session
- Independent validation: Claude CLI, because the current session uses a GPT-family model
- Why: this introduces a cross-runtime coordination policy and must avoid duplicating or conflicting with `architect`, `total-review`, Pi's model-tier router, and `pi-subagents`.

## Goal

Create a portable, explicitly invoked coordination skill named `orchestrate` in the shared `agent-skills` repository. It should keep important judgment, integration, and final validation with the parent agent while delegating bounded execution to the cheapest adequate worker available in the current runtime. Pi should apply its native `pi-subagents` mechanism with explicit per-launch model selection, Claude Code should use native subagents with floating child-model aliases, and Codex should capability-detect and use its stable native multi-agent support with runtime-local child overrides, falling back to serial parent execution only when delegation is unavailable.

The skill is a policy/orchestration layer, not a replacement for the Pi model-tier router or the `pi-subagents` extension.

## Context gathered

- Shared skill source: `/home/ivar/Code/flurdy/agent-skills/shared/skills/`
- Shared routing policy: `/home/ivar/Code/flurdy/agent-skills/shared/MODEL_ROUTING.md`
- Skill authoring/indexes: `README.md`, `skills/README.md`, `CLAUDE.md`
- Existing planning boundary: `skills/architect/SKILL.md` plans but explicitly does not implement.
- Existing review boundary: `skills/total-review/SKILL.md` owns the full pre-PR review gauntlet.
- Existing Pi mechanism: the installed `pi-subagents` skill already defines async launches, fresh/fork context, one-writer safety, review loops, intercom escalation, and model overrides.
- Existing Pi router: `/home/ivar/Code/flurdy/ai-tools/pi/model-tier-router/` routes the current agent when a tiered skill is invoked, supports nested upward-only upgrades, confirms metered candidates, and restores the previous model/thinking level after settlement.
- Local Pi model mappings live in `~/.pi/agent/model-tier-router.json`; exact model IDs must remain runtime-local.
- Installed Codex `0.144.3` reports `multi_agent` as stable and enabled. Skipping this repo's `agents/` assembly layer does not mean Codex lacks native delegation.
- The shared repo uses direct commits on `main`. At this revision, `main` is one commit ahead of `origin/main` with the cheap-bulk effort update; only `plans/orchestrate-skill.md` is untracked.

## Assumptions

- The user must explicitly invoke `/orchestrate`; invocation authorizes ordinary bounded delegation inside the requested scope, but not new external side effects or broader product decisions.
- The parent remains the sole decision-maker and owns integration/final response.
- Subagent capabilities differ by runtime and version; the shared skill must describe policy first and treat runtime-specific tooling as an adapter.
- Exact provider/model IDs must not be embedded in shared skill text or frontmatter.
- The first release should favor a small, understandable skill over an automatic scheduler, global subagent overrides, namespaced role duplication, or a new cross-extension protocol.

## Recommended approach

### 1. Add a portable policy skill

Create:

```text
skills/orchestrate/
  SKILL.md
  references/
    runtime-adapters.md
```

`SKILL.md` should contain the runtime-neutral contract and remain concise enough to load routinely. `runtime-adapters.md` should contain Pi-rich execution guidance plus conservative Claude Code/Codex fallbacks, avoiding duplication of full runtime documentation.

Recommended frontmatter:

```yaml
---
name: orchestrate
description: Coordinate substantial multi-stage work through bounded delegation, one-writer safety, independent review, and risk-based escalation. Use only when explicitly invoked; skip trivial, tightly coupled, or serial work.
allowed-tools: "Read,Grep,Glob,Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(git show:*),Bash(git rev-parse:*),Task,Skill,AskUserQuestion"
disable-model-invocation: true
model-tier: premium-reasoning
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
effort: high
version: "1.0.0"
author: "flurdy"
---
```

Rationale:

- `disable-model-invocation: true` makes the skill genuinely opt-in and prevents wording such as “parallelize” from unexpectedly upgrading a cheaper parent session.
- `premium-reasoning` with explicit `effort: high` is a settled v1 decision: this skill is explicit-only and strictly for substantial multi-stage work, so the parent should retain strong judgment without routinely spending `xhigh`. A trivial invocation should decline orchestration, but the premium parent route is accepted as the cost of explicit misuse.
- Premium skills remain unpinned in Claude Code and therefore require the existing premium tier guard copied/adapted from `architect`.
- `ask-above-standard` protects a metered premium-parent fallback consistently with existing premium skills. Child launches need a separate body rule because the Pi model-tier router does not inspect `subagent` calls.
- The body must ask before any metered child launch or multi-agent panel. Automatic child fallbacks should remain subscription-only; after an unavailable subscription child, retain the parent or ask before choosing a metered child.
- `allowed-tools` follows the repo's dominant convention but pre-approves only read-only Git inspection, not mutating `git` operations. Runtime-specific custom tools such as Pi's `subagent` remain capability-detected rather than encoded as a portable requirement.

### 2. Define clear boundaries with existing skills and mechanisms

The skill must explicitly state:

- `architect` owns architecture/implementation planning when ambiguity or blast radius warrants a plan. `orchestrate` may call it or stop for plan approval; it must not silently redo architecture in a cheap worker.
- `orchestrate` owns execution coordination after scope and acceptance are sufficiently clear.
- `verify-task` and `total-review` remain named gates; `orchestrate` may invoke them when requested or appropriate but must not copy their complete logic.
- `pi-subagents` is Pi's execution mechanism. `orchestrate` decides whether, why, and at what semantic tier to delegate.
- The model-tier router controls skill-level routing of the current Pi agent. It does not own child scheduling.

### 3. Use a proportionate judgment packet before every downshift

Every delegated task needs an explicit contract, but its size must match the risk:

- **Cheap read-only lookup/recon:** objective or question, bounded scope, expected evidence/output, and stop condition. This may be a few lines.
- **Implementation writer or consequential analysis:** include the full packet below.

Full packet:

1. Goal and user-visible outcome.
2. Owned files/modules or a bounded read-only question.
3. Relevant repository/runtime rules and established patterns.
4. Explicit non-goals and prohibited scope expansion.
5. Acceptance criteria and exact validation commands or user flows.
6. Known risks, assumptions, and unresolved questions.
7. Required output: changed files/evidence, commands with outcomes, residual risks, and decisions needing approval.
8. Escalation/stop conditions.

If the packet still asks a worker to discover architecture, redefine scope, or choose a high-impact alternative, the parent must retain the work or use `architect`/a stronger advisory pass first.

### 4. Route by work shape and risk, not line count

Use semantic routes rather than exact models. **Downshifting is realized only by passing a runtime-local model override on the child launch.** Invoking a lower-tier skill in the already-routed parent does not downshift it: Pi's router intentionally retains equal/lower nested tiers and only permits upward upgrades.

| Work shape | Child role and model class | Effective effort |
|---|---|---|
| Focused lookup or repository/document research | `context-builder` or `researcher` + cheap model class (`cheap-bulk`) | medium from the builtin role |
| Narrow mechanical implementation with explicit files/pattern/tests | `worker` + cheap model class | high from the builtin role |
| Bounded implementation or routine independent review | `worker`, `planner`, or fresh `reviewer` + balanced model class | high from the builtin role |
| Complex implementation requiring meaningful local design judgment | strong coding model class (`standard-coding`) or retain in parent | high |
| Architecture, unclear ownership, public contracts, destructive/security-sensitive work | keep with parent `premium-reasoning`; optionally use `oracle` on the strongest subscription model | high, then xhigh/max only when justified |
| Independent final/craft judgment | fresh/separate `reviewer`, `premium-review`, or named review skill | xhigh only when justified |

Pi v1 routing algorithm:

1. Call subagent discovery before execution and use only executable/non-disabled roles.
2. Inspect builtin role details/model reporting before launch. The installed defaults currently provide medium thinking for `context-builder`/`researcher` and high for `worker`/`planner`/`reviewer`/`oracle`.
3. Resolve exact child model IDs from runtime-local configuration: cheap from the local `cheap-bulk` subscription candidate, balanced from the local balanced/Terra-class subscription candidate, and strong from the local Sol/frontier subscription candidate.
4. Pass the resolved `model` explicitly on every child launch. Do not edit canonical `agentOverrides`, create namespaced duplicate roles, or rely on inherited parent models in v1.
5. Keep automatic routes subscription-only. Do not pass metered fallback models; ask before an explicit metered child or panel.
6. If a model mapping is missing or a launch rejects it, report that no downshift occurred and either inherit/retain the parent safely or continue locally. Never imply that a semantic route was applied.

Role constraints:

- Do not use builtin `scout` for the default medium cheap path because its installed thinking default is low.
- Do not use builtin `delegate` for routed v1 work because it has no explicit thinking default.
- Use `worker` with a cheap model for narrow mechanical edits when cheap execution is objectively testable; use the balanced model for broader bounded implementation.
- Request `context: "fresh"` for genuinely independent reviewers where supported.

Cross-runtime model classes:

- Claude Code: cheap → floating `haiku`, balanced → floating `sonnet`, strong → floating `opus`; use the native child model override and report when child effort cannot be independently controlled.
- Codex: map cheap/balanced/strong to the installed runtime's configured Luna/Terra/Sol-class child models and reasoning overrides. If no verified mapping exists, inherit and explicitly report that no downshift occurred.
- Shared skill text must not contain dated or provider-qualified model IDs.

Rules:

- Pass the child model on every launch; do not expect parent skill routing to change the child automatically.
- Tune effort within a suitable model before jumping multiple model classes.
- Prefer cheap workers only when success is objectively testable.
- Do not delegate open-ended architecture to a cheap worker.
- Do not use number of changed lines as the risk proxy.
- Delegation must save more context, latency, or cost than it adds in briefing, supervision, and review.

Do not add a shared `bounded-coding` frontmatter tier in v1. The balanced model class is an orchestration-time child selection. Revisit a portable tier only after dogfooding shows that it is useful outside orchestration.

### 5. Keep writes single-threaded

Policy-level workflow:

```text
clarify/scope
  -> define validation contract
  -> optional read-only recon/advice
  -> one implementation writer
  -> independent review/validation when the runtime provides it
  -> parent synthesis and, when needed, one fix writer
  -> parent final inspection and validation
```

When delegation is unavailable, the parent may continue serially but must label the result as self-validated rather than independently reviewed. If the task or user requires genuine independence, invoke `/second-opinion` through its existing cost guardrails or stop and ask; do not silently weaken the review contract.

Constraints:

- Only one writer may edit a shared worktree at a time.
- Parallelize research, reconnaissance, review, and validation by default—not ordinary writes.
- Parallel writers require intentional worktree isolation, non-overlapping ownership, and a clean base.
- When delegation is available, the implementing worker cannot be the sole authority that its work is complete. In serial fallback, disclose that only self-validation was possible.
- The parent must inspect the actual diff/evidence rather than trusting the worker summary.
- Cap routine review fanout at two or three distinct angles; avoid swarms.
- Do not implement a separate generic review-loop engine in this skill. On Pi, defer mechanics to `pi-subagents`/its review-loop recipe; use `total-review`, `verify-task`, or other named gates where they own the requested depth. The skill supplies policy and acceptance, not another convergence framework.

### 6. Define dynamic escalation and stop rules

A worker must stop and return to the parent when:

- Required work expands beyond owned files or acceptance criteria.
- Repository behavior contradicts the judgment packet.
- A public API, schema, migration, permission, compatibility, product, or architectural decision appears.
- Authentication, authorization, secrets, destructive operations, financial correctness, concurrency, deployment control, or irreversible data is involved unexpectedly.
- The same validation failure survives two evidence-based attempts.
- The worker is guessing about hidden state or cannot explain the failure.
- Integration reveals conflicting edits or cross-task architectural coupling.

Escalation should be the smallest responsible increase: more effort on the same worker class, a stronger worker/advisor, or return of the decision to the premium parent. It must not automatically mean maximum effort or a broad panel.

The orchestration run ends when:

- Acceptance and validation contracts are met and either independent review finds no fixes worth doing now, or serial fallback is explicitly disclosed as self-validated.
- Remaining findings are optional/deferred.
- An unapproved decision requires the user.
- The selected runtime-native or named review gate reaches its own configured cap; routine orchestration should normally use one review and at most one focused follow-up.
- Delegation is unavailable or no longer economical, in which case the parent continues locally.

### 7. Add mandatory runtime adapters without hard-coded models

After detecting the runtime, the skill must load `references/runtime-adapters.md` before delegating. The reference should specify:

#### Pi

- If `pi-subagents` is installed, load/follow its skill for agent discovery, async launch/wait, context mode, one-writer safety, review recipes, and supervisor coordination; do not duplicate those mechanics here.
- Before launching, inspect executable roles and builtin model/thinking metadata using the installed subagent discovery/model commands. Resolve the runtime-local child model class, then pass `model` explicitly on every launch.
- Launch asynchronously by default. When the parent must finish the orchestration in the same turn, use `wait()` rather than ending the turn or polling.
- Prefer the role's default context. If a forked role cannot start because parent-session persistence is unavailable, retry with `context: "fresh"` only when the judgment packet is self-contained; otherwise continue in the parent.
- This skill adds only the delegate-or-not ROI decision, child-role choice, proportionate judgment packet, cost gate, and escalation/stop policy.
- If `pi-subagents` is unavailable, continue serially in the parent and apply the self-validation disclosure rule.

#### Claude Code

- Use native `Task`/subagents when available, passing the floating child mapping explicitly: cheap → `haiku`, balanced → `sonnet`, strong → `opus`.
- Request the appropriate child effort when the runtime exposes that control; otherwise report inherited/default effort rather than claiming an override.
- Keep architecture/integration in the parent and assign explicit bounded ownership.
- If native delegation is unavailable, execute serially in the parent and apply the self-validation disclosure rule.

#### Codex

- Capability-detect native multi-agent tools in the installed runtime; Codex `0.144.3` currently reports `multi_agent` stable and enabled.
- Use native multi-agent delegation when available, passing the installed runtime's configured cheap/balanced/strong child model and reasoning overrides when verified.
- If the Codex mapping is missing, inherit and explicitly report that no downshift occurred.
- Apply the same judgment packet, one-writer, cost, escalation, and parent-authority rules.
- Treat this repo's skipped `agents/` assembly layer only as a packaging limitation for shared Markdown agents, not proof that Codex lacks delegation.
- Fall back to serial parent execution only when native multi-agent capability is unavailable, and apply the self-validation disclosure rule.

The adapter reference should stay short and point to runtime-owned documentation rather than copying it. Implementation must verify the currently installed Claude Code and Codex invocation syntax rather than guessing fragile command examples.

### 8. Do not change the Pi model-tier router in v1

No extension code change is required for the first implementation:

- Invoking `orchestrate` can route the parent through its own frontmatter.
- Child execution is already supported by runtime-native subagent tooling and local agent/model configuration.
- Nested upward-only routing is desirable for the parent because a coordination run should not accidentally downshift its judgment model.
- Restoration behavior remains useful after the orchestration run settles.

Avoid intercepting or rewriting `subagent` tool calls in the model-tier router. That would couple two extensions, duplicate confirmation behavior, and make shared policy dependent on Pi internals.

Document one deferred enhancement, but do not implement it now: a read-only semantic tier resolver/RPC that returns the locally available candidate and effort for a requested tier. Consider it only if dogfooding shows repeated model-ID duplication or inconsistent child routing. Any future resolver must preserve metered confirmation semantics and must not spawn workers itself.

### 9. Update documentation and indexes

Update:

- `skills/README.md` description table with `orchestrate`.
- `skills/README.md` model-routing table under `premium-reasoning`, with effort `high`, no Claude `model:` pin, and a tier guard. Add a brief footnote explaining that `high` is deliberate for routine parent coordination while `xhigh` remains reserved for harder planning/review.
- `MODEL_ROUTING.md` with one concise paragraph clarifying that skill-tier routing selects the parent/current skill model while orchestration must separately choose child routes through runtime-native configuration; invoking a lower-tier nested skill does not downshift the parent.
- `README.md`, `Makefile`, `assemble.sh`, and `agents/README.md` where necessary to replace the stale claim that Codex has no subagent concept. State instead that `make apply-codex` skips this repo's Claude-style Markdown `agents/` layer while installed Codex versions may provide native multi-agent tools.
- Runtime-adapter documentation with explicit per-launch model mapping and honest inherited/no-downshift behavior. The implementation must not mutate canonical user or project subagent settings.

Do not add a new top-level shared agent. The skill coordinates runtime-provided agents; a second shared "foreman agent" would duplicate authority and the shared `agents/` packaging remains Claude-specific.

## Alternatives considered

1. **Extend the Pi router to auto-spawn or rewrite child models now** — rejected for v1. It couples independent extensions, is Pi-only, and is unnecessary to validate the policy.
2. **Copy the colleague's Codex skill nearly verbatim** — rejected. It hard-codes Codex model names/effort assumptions and lacks this repo's cross-runtime routing and safety boundaries.
3. **Create a shared `foreman` agent instead of a skill** — rejected. This repo's shared Markdown agents are currently assembled only for Claude Code, and a second orchestration authority would conflict with the parent-agent contract. Codex native multi-agent capability does not require adding a shared agent file.
4. **Put all Pi instructions in the main `SKILL.md`** — rejected. It would make the shared skill noisy and less portable; use a small runtime adapter reference.
5. **Add a new balanced/bounded-coding semantic tier immediately** — deferred. It might better represent Terra/Sonnet bounded implementation, but should follow evidence from dogfooding rather than widening taxonomy and local config now.
6. **Set global Pi `agentOverrides` for canonical roles** — rejected. It would change every Pi subagent workflow, not only `/orchestrate`.
7. **Create namespaced duplicate orchestration roles** — deferred as unnecessary in v1. Per-launch model selection reuses builtin role prompts and their appropriate thinking defaults without duplicating agents.

## Implementation slices

1. Add `skills/orchestrate/SKILL.md` with frontmatter, explicit-only trigger, settled premium/high parent route, boundaries, proportionate judgment packet, child-route policy, one-writer workflow, child metered-cost gate, escalation rules, serial-fallback disclosure, completion rules, and premium tier guard.
2. Add `skills/orchestrate/references/runtime-adapters.md` with mandatory capability detection, concrete per-launch Pi model selection, Pi async/wait/fresh-context recovery, Claude Code floating child mappings, and Codex native multi-agent mappings.
3. Update `skills/README.md` in both required tables.
4. Add the parent-vs-child routing clarification and child-cost distinction to `MODEL_ROUTING.md`.
5. Correct stale Codex-agent wording in `README.md`, `Makefile`, `assemble.sh`, and `agents/README.md` without changing assembly behavior.
6. Run repository validation and manually inspect Claude and Codex assembly output.
7. Dogfood explicit invocation in Pi, Claude Code, and Codex, including effective child-model evidence, delegated, unavailable-mapping, metered-child-decline, and serial-fallback scenarios, before considering any router/RPC enhancement.

## Test strategy

### Static/repository checks

- Manually inspect frontmatter for required semantic fields, `allowed-tools`, `disable-model-invocation: true`, and the deliberate absence of a Claude `model:` pin. The repo has no dedicated frontmatter/schema test target; `make dry-run` and `doctor` validate assembly/symlinks, not metadata semantics.
- Verify the description table remains alphabetical.
- Verify the routing table places `orchestrate` under `premium-reasoning` with the intended policies, `high` effort, guard marker, and explanatory footnote.
- Confirm all relative links from `SKILL.md` resolve.
- Run `make dry-run` and `make dry-run-codex`.
- Run `make apply` and `make apply-codex` after approval because adding a skill directory changes managed symlinks.
- Run `make doctor` and `make doctor-codex`.
- Verify both `~/.claude/skills/orchestrate` and `~/.codex/skills/orchestrate` resolve to the new source directory.
- Restart/reload Pi as needed and verify the explicit skill command is discovered from the configured shared skill path.
- Inspect Pi's effective builtin role models/thinking before dogfooding, then run bounded child launches with explicit per-launch models and capture evidence of the actual child model/effort. Configuration inspection alone is not sufficient.
- Run equivalent bounded launches in Claude Code and Codex and capture the effective child model/effort or an explicit report that the runtime inherited defaults.

### Manual behavioral scenarios

1. Trivial one-file task: skill declines delegation and avoids ceremony.
2. Read-only lookup: parent creates the minimal packet and routes a child cheaply if available; the premium parent does not try to downshift by invoking a lower-tier skill itself.
3. Bounded code task: one writer works from explicit acceptance/validation criteria; parent reviews the diff.
4. Parallelizable investigation: multiple read-only workers use non-overlapping questions; one parent synthesizes. Any reviewer used as an independent gate receives fresh/separate context where supported.
5. Scope expansion: worker stops rather than editing outside ownership.
6. Repeated test failure: after two evidence-based attempts, worker escalates.
7. High-risk discovery: auth/schema/destructive concern stays with or returns to premium parent.
8. Review findings: parent synthesizes and launches at most one fix writer, followed by focused re-review when warranted.
9. No subagent runtime: parent follows the same policy serially, labels the result self-validated, and does not claim independent review.
10. Independence-required serial case: use `/second-opinion` or stop and ask rather than silently weakening the contract.
11. Metered child or panel candidate: ask before launch; declining leaves the parent/subscription path intact.
12. Runtime-local model mapping absent: report that no downshift is configured and inherit/continue safely without claiming a tier change.
13. Pi async launch: launch asynchronously and use `wait()` when the same turn must continue to completion.
14. Pi fork unavailable: retry with `context: "fresh"` only for a self-contained judgment packet.
15. Pi effective routing: inspect builtin model/thinking metadata, launch cheap and balanced children with explicit models, and verify run evidence shows the requested child model plus the role's effective effort.
16. Claude effective routing: launch one bounded cheap or balanced child and verify the floating alias resolved as intended; report inherited effort if it cannot be set independently.
17. Codex capability and routing: confirm `multi_agent` detection, exercise one bounded delegated task with configured model/reasoning overrides, and verify effective child evidence; exercise serial fallback only with the feature unavailable.
18. Pi model lifecycle: `/model-tier status` shows the parent route during the run and the original model/thinking restores after settlement.
19. Cheap-bulk effort experiment: record latency, retries/corrections, tool-call count, and observable quota usage at medium; lower an individual workflow to low only when the saving is meaningful and reliability does not regress.

## Risks and mitigations

- **Duplication with `pi-subagents`:** keep the main skill policy-level and the Pi adapter short; reference rather than restate runtime mechanics.
- **Over-orchestration:** require explicit user invocation, a delegation ROI check, proportionate packets, and explicit skipping of trivial, serial, or tightly coupled work.
- **Confused authority:** state that the parent owns architecture, scope, integration, approval, and final response; children escalate decisions.
- **Parallel write corruption:** one writer by default; require worktree isolation for intentional parallel writers.
- **Cross-runtime drift:** runtime adapters must be capability-detected, use verified native mechanisms, and degrade to disclosed serial self-validation.
- **Child route not actually applied:** pass a model explicitly on every child launch, verify effective routing with bounded runs, and report rather than imply a downshift when mapping or evidence is missing.
- **Global behavior accidentally changed:** do not modify canonical Pi role overrides or project/user settings in v1; per-launch selection scopes routing to `/orchestrate`.
- **Model-ID duplication:** resolve exact IDs at runtime from local configuration and keep them out of the shared repo; defer a resolver until real usage proves necessary.
- **Premium cost creep:** use `effort: high`, cap normal fanout, use `ask-above-standard` for the parent, ask explicitly before metered children/panels, and reserve xhigh/max for explicit risk.
- **Implicit child rerouting by tiered skills:** delegated workers should receive direct bounded task contracts and only load another tiered skill deliberately; if this becomes a recurring source of unexpected upgrades, capture it during dogfooding before altering the router.

## Rollout and rollback

- Rollout is explicit-only: add and assemble the new skill, then dogfood per-launch child routing on low-risk tasks through the runtime's skill command (`/skill:orchestrate` in Pi).
- No model-tier-router code migration or Pi settings mutation is required; normal skill discovery/reload is the only Pi runtime change.
- Roll back by removing the skill directory and documentation rows, then re-running Claude/Codex apply and doctor targets.
- Router behavior remains unchanged, so rollback does not affect model selection for existing skills.

## Independent validation and resulting changes

Three independent review passes agreed with the core design: create a shared policy skill, keep parent judgment strong, do not add a new shared agent/frontmatter tier, and make no Pi router code changes in v1. They identified corrections incorporated into this final plan:

- Made invocation explicitly opt-in with `disable-model-invocation: true` to avoid surprise premium upgrades.
- Added the repo-conventional `allowed-tools` surface.
- Clarified that semantic downshift happens only by launching a child on that route; a lower-tier nested skill cannot downshift the already-routed parent.
- Made the judgment packet proportionate rather than requiring eight fields for trivial recon.
- Trimmed Pi mechanics in favor of referencing `pi-subagents` and its existing review-loop behavior.
- Named Claude Code's per-subagent model override.
- Replaced global canonical Pi role overrides with explicit per-launch model selection, relying on verified builtin role effort defaults and honest behavior when a mapping/effective route is absent.
- Defined Claude's cheap/balanced/strong floating mappings and required Codex runtime-local model/reasoning mappings.
- Required bounded launch evidence of effective child model/effort instead of trusting settings inspection, including protection against project settings silently superseding user defaults.
- Required fresh/separate reviewer context for genuine independence where supported.
- Corrected the Codex adapter after verifying installed Codex `0.144.3` has stable native `multi_agent`; serial execution is fallback, not the default promise.
- Separated premium-parent metered policy from child/panel confirmation because the model-tier router does not inspect child launches.
- Settled `premium-reasoning`/high for the explicit substantial-work parent rather than leaving it as a dogfooding question.
- Defined serial fallback as disclosed self-validation and routed genuine independence through `/second-opinion`.
- Narrowed Git preapproval, made runtime-adapter loading mandatory, and expanded Pi/Codex rollout tests.
- Added documentation/test checks for the deliberate premium/high combination, no model pin, and explicit-only invocation.

One review claim was softened rather than accepted as an absolute blocker: `allowed-tools` is optional in the Agent Skills/Pi specification, but it is present on 43 of 46 existing shared skills and is useful here as a pre-approval surface, so the final plan includes it as a repository convention.

## Open questions for dogfooding, not implementation blockers

- Does repeated per-launch runtime-local model resolution justify a future read-only semantic resolver?
- Does the balanced worker route cover bounded implementation reliably, and should a future portable `bounded-coding` tier formalize it across runtimes?
- Which cheap-bulk workflows can safely return from medium to low effort based on measured latency/quota savings and unchanged reliability?

## Recommended implementation tier

Use `standard-coding` for the skill implementation because it is primarily Markdown policy and documentation with careful cross-runtime semantics. Use `premium-review` only for a final policy/maintainability review if desired.

## Next concrete action

Have one implementation agent work in `/home/ivar/Code/flurdy/agent-skills/shared` on `main`: create the two skill files, update routing/index/Codex-assembly documentation, implement per-launch child mapping without mutating canonical settings, run the Claude/Codex apply and doctor targets plus effective-routing scenarios for Pi/Claude/Codex, and stop before committing if runtime behavior differs from this approved plan.
