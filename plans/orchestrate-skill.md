# Implementation Plan: Portable `orchestrate` Skill

> **Status:** Implemented as the conservative delegation-governance v1. Current scope,
> document ownership, capability maturity, and the adaptive task-orchestration roadmap
> are maintained in [`../skills/orchestrate/README.md`](../skills/orchestrate/README.md).
> This file preserves the original implementation rationale and dogfood constraints.

## Planning tier

- Tier: all-in
- Primary planning route: premium reasoning in the current Pi session
- Independent validation: Claude CLI, because the current session uses a GPT-family model
- Why: this introduces a cross-runtime coordination policy and must avoid duplicating or conflicting with `architect`, `total-review`, Pi's model-tier router, and `pi-subagents`.

## Goal

Create a portable, explicitly invoked coordination skill named `orchestrate` in the shared `agent-skills` repository. It should keep important judgment, integration, and final validation with the parent agent while delegating bounded execution through runtime-native subagents. Pi v1 should orchestrate correctly while inheriting the parent model unless the user/runtime already supplies an explicit verified child mapping; it must not reimplement model-tier resolution inside the skill. Claude Code should use native subagents with floating child-model aliases, and Codex should capability-detect native multi-agent support and use child overrides only when configured and verified, falling back to honest inherited/no-downshift or serial behavior otherwise.

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
- Beads epic `skills-88v` tracks this plan and its durable implementation/dogfooding decisions. Beads should track durable milestones, not individual child launches or review rounds.
- The shared repo uses direct commits on `main`. The plan is tracked in Git; inspect current status before implementation rather than relying on this snapshot.

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
allowed-tools: "Read,Grep,Glob,Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(git show:*),Bash(git rev-parse:*),Bash(bd status:*),Bash(bd list:*),Bash(bd show:*),Task,Skill(architect),Skill(verify-task),Skill(total-review),Skill(triage),Skill(second-opinion),Skill(pi-subagents),AskUserQuestion"
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
- A verified child mapping must include both the effective model identity, resolved before launch by trusted runtime/resolver evidence, and a trusted `metered: true|false` classification. Launch evidence should confirm the identity when available. If identity resolves only after exposure, classify the route as unknown and ask first; a mismatch invalidates the classification and stops further fanout until a new disclosure/decision. Trusted classification must come from runtime/resolver metadata or an explicit user-approved local policy; never infer it from provider name, model ID, authentication type, or parent routing.
- A user-approved local policy is a declaration in the runtime's user-owned instruction/configuration layer that is supplied to the active session and names the runtime, exact effective child route/model identity, `metered` value, and scope (`user` or an explicitly approved project). Project scope must also identify the project by stable ID or absolute root; `scope: project` alone is ambiguous. Arbitrary repository instructions do not qualify. The portable shape is:

  ```yaml
  orchestrate-child-policy:
    runtime: <runtime>
    scope: user | project
    project: <stable-project-id-or-absolute-root; required for project scope>
    routes:
      <route>:
        identity: <effective-model-identity>
        metered: true | false
  ```

  The runtime adapter should document the detected user-level location/mechanism rather than invent a shared cross-runtime settings file. An in-conversation approval is scoped only to the disclosed current run or panel and does not become durable policy. `/orchestrate` must never persist or widen policy automatically; it may suggest a separately approved user-level configuration change.
- Keep the `SKILL.md` cost gate compact:

  | Child classification | Action |
  |---|---|
  | Verified identity + `metered: false` | Launch within the approved task scope. |
  | Verified identity + `metered: true` | Confirm the disclosed child or bounded panel for this run. |
  | Inherited route or unknown classification | Disclose inherited/no-downshift behavior and confirm for this run. |
  | Confirmation declined | Continue serially without claiming independent delegation. |

- One confirmation may cover a clearly disclosed bounded panel for the current run; expanding its models, count, scope, or metered exposure requires confirmation again. Parent-route confirmation never authorizes child fanout.
- `allowed-tools` follows the repo's dominant convention but pre-approves only read-only Git inspection and the named skills this plan permits, not mutating `git` operations or an unscoped `Skill` surface. Runtime-specific custom tools such as Pi's `subagent` remain capability-detected rather than encoded as a portable requirement.

### 2. Define clear boundaries with existing skills and mechanisms

The skill must explicitly state:

- `architect` owns architecture/implementation planning when ambiguity or blast radius warrants a plan. `orchestrate` may call it or stop for plan approval; it must not silently redo architecture in a cheap worker.
- `orchestrate` owns execution coordination after scope and acceptance are sufficiently clear.
- `verify-task` and `total-review` remain named gates; `orchestrate` may invoke them when requested or appropriate but must not copy their complete logic.
- `pi-subagents` is Pi's execution mechanism. `orchestrate` decides whether, why, and at what semantic tier to delegate.
- The model-tier router controls skill-level routing of the current Pi agent. It does not own child scheduling.
- Use the repository's established tracker for durable work context when available. Beads integration applies only when `bd` is available, the repository has active Beads context, and a relevant bead/epic exists; otherwise use the established Jira/Trello/other tracker or report durable milestone suggestions generically when no tracker exists.
- Never create one tracker item per subagent, recon pass, review round, retry, or temporary handoff.
- When orchestration discovers independently valuable milestones that may span sessions, commits, or PRs, propose the repository's established tracking workflow. Invoke `/triage` only in a Beads-enabled repository, and create or mutate any tracker only after explicit user approval. Leave completion/closure to existing tracking and completion skills.
- If the portable control-plane index tracked by `skills-88v.6` exists in a target workspace, consume its authoritative context when building judgment and validation packets. Orchestrate v1 must remain useful without it; this is a soft integration, not an implementation dependency.

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

Use semantic routes rather than exact models. Invoking a lower-tier skill in the already-routed parent does not downshift it: Pi's router intentionally retains equal/lower nested tiers and only permits upward upgrades.

| Work shape | Child role/model policy | Effective effort |
|---|---|---|
| Focused lookup or repository/document research | `context-builder` or `researcher`; use a cheap model only when an explicit verified mapping exists, otherwise inherit and disclose | medium from the builtin role |
| Narrow mechanical implementation with an exact packet | `worker`; `standard-coding` is the default, with the documented bounded-edit exception only when an explicit verified cheaper mapping exists | high from the builtin role |
| Bounded implementation or routine independent review | `worker`, `planner`, or fresh `reviewer`; use a balanced model only when an explicit verified mapping exists, otherwise inherit and disclose | high from the builtin role |
| Complex implementation requiring meaningful local design judgment | use a verified `standard-coding` child route; without one, inherit with disclosure or retain in parent | high |
| Architecture, unclear ownership, public contracts, destructive/security-sensitive work | keep with parent `premium-reasoning`; optionally use `oracle` on a verified strongest subscription route | high, then xhigh/max only when justified |
| Independent final/craft judgment | fresh/separate `reviewer`, `premium-review`, or named review skill | xhigh only when justified |

Pi v1 routing algorithm:

1. Call subagent discovery before execution and use only executable/non-disabled roles.
2. Inspect builtin role/model reporting before launch so inherited behavior is visible.
3. Do **not** parse or merge model-tier-router files inside the skill. That would duplicate trusted project/global merging, candidate availability, fallback ordering, and metered classification.
4. Treat a mapping as verified only when trusted runtime/resolver evidence resolves the effective model identity before launch and trusted policy supplies metered classification. Pass its child `model` explicitly and confirm the identity from launch evidence when available.
5. If identity resolves only after launch, or no verified mapping exists, use the unknown-route consent path before exposure. For inherited Pi behavior omit the model override, report inherited/no-downshift behavior, and ask before launch. Declining continues serially; a post-launch mismatch stops further fanout and requires a new disclosure/decision.
6. Never add an automatic metered fallback. Verified `metered: true` and unknown classifications both require child-specific confirmation; prior confirmation of the parent route does not count.
7. If a supplied mapping is rejected, retain/inherit the parent or continue locally and report the failure without claiming a semantic route.

Role constraints:

- Prefer `context-builder`/`researcher` for medium-effort cheap read-only work when a verified mapping exists.
- Use `worker` for all writes. A cheaper worker route is allowed only by the bounded-edit exception below; otherwise use/inherit `standard-coding` strength.
- Request `context: "fresh"` for genuinely independent reviewers where supported.

Cross-runtime model classes:

- Claude Code: cheap → floating `haiku`, balanced → floating `sonnet`, strong → floating `opus`; use a native child override without another cost prompt only when the runtime resolves the alias to the policy identity before launch. Otherwise classify it as unknown and ask before exposure, then confirm the launched identity. Report when child effort cannot be independently controlled.
- Codex: use configured cheap/balanced/strong child model and reasoning overrides only when the installed runtime exposes and verifies them. Otherwise delegate with inherited settings and explicitly report that no downshift occurred.
- Pi: v1 guarantees orchestration and honest inherited/no-downshift behavior. Because inherited child metered status is unknown without resolver metadata, ask before that delegation. Automatic semantic downshifting and trusted classification are deferred to `skills-88v.5`.
- Shared skill text must not contain dated or provider-qualified model IDs.

Bounded-edit exception to add to `MODEL_ROUTING.md`:

- `standard-coding` remains the default model class for code-writing workflows.
- An orchestrated child may use a cheaper model class only when its full judgment packet fixes owned files, an established implementation pattern, explicit non-goals, acceptance criteria, exact verification, and escalation conditions.
- The premium/strong parent retains architecture, integration, review synthesis, and final validation. Any newly exposed product, public-contract, security, migration, destructive, or architectural decision returns to the parent.
- This exception does not permit ordinary code-editing skills to declare `cheap-bulk` or `standard-workflow`; it applies only to a bounded child launch inside an explicitly invoked orchestration run.

Rules:

- Pass a child model only when a verified mapping includes identity and trusted metered classification; do not expect parent skill routing to change the child automatically.
- Tune effort within a suitable model before jumping multiple model classes.
- Prefer cheaper workers only when success is objectively testable and the bounded-edit exception is satisfied.
- Do not delegate open-ended architecture to a cheap worker.
- Do not use number of changed lines as the risk proxy.
- Delegation must save more context, latency, or cost than it adds in briefing, supervision, and review.

Do not add a shared `bounded-coding` frontmatter tier in v1. Revisit a portable tier only after dogfooding shows that it is useful outside orchestration.

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
- Immediately before every launch, inspect executable roles and builtin model/thinking metadata using the installed subagent discovery/model commands. Repeat model reporting after any skill read, router event, or manual model change; do not reuse stale preflight evidence. Pass `model` only when the user/runtime supplies identity plus trusted metered classification; otherwise inherit, disclose no downshift, and ask because child billing classification is unknown.
- Launch asynchronously by default. When the parent must finish the orchestration in the same turn, use `wait()` rather than ending the turn or polling.
- For prose-only review with no acceptance ledger, use the runtime's explicit disable form with a reason (currently `{ level: "none", reason: "Read-only prose review" }`); the string shorthand does not lower an inferred stronger gate. Otherwise request and satisfy review-appropriate structured evidence.
- Prefer the role's default context. If a forked role cannot start because parent-session persistence is unavailable, retry with `context: "fresh"` only when the judgment packet is self-contained; otherwise continue in the parent.
- This skill adds only the delegate-or-not ROI decision, child-role choice, proportionate judgment packet, cost gate, and escalation/stop policy.
- If `pi-subagents` is unavailable, continue serially in the parent and apply the self-validation disclosure rule.

#### Claude Code

- Use native `Task`/subagents when available, passing the floating child mapping explicitly: cheap → `haiku`, balanced → `sonnet`, strong → `opus` only when trusted local policy also classifies the child route's metered status.
- Request the appropriate child effort when the runtime exposes that control; otherwise report inherited/default effort rather than claiming an override. Ask before child launch when metered classification is true or unknown.
- Keep architecture/integration in the parent and assign explicit bounded ownership.
- If native delegation is unavailable, execute serially in the parent and apply the self-validation disclosure rule.

#### Codex

- Capability-detect native multi-agent tools in the installed runtime; do not gate behavior on a pinned Codex version or copy observed version claims into the adapter.
- Use native multi-agent delegation when available, passing configured cheap/balanced/strong child model and reasoning overrides only when identity and trusted metered classification are verified.
- If the Codex mapping/classification is missing, inherit, explicitly report that no downshift occurred, and ask before the unknown-classification child launch.
- Apply the same judgment packet, one-writer, cost, escalation, and parent-authority rules.
- Treat this repo's skipped `agents/` assembly layer only as a packaging limitation for shared Markdown agents, not proof that Codex lacks delegation.
- Fall back to serial parent execution only when native multi-agent capability is unavailable, and apply the self-validation disclosure rule.

For unlisted runtimes, capability-detect native delegation without inventing a model mapping. Apply the same cost gate, packet, one-writer rule, fresh-review preference, and parent authority; otherwise fall back to disclosed serial self-validation. The adapter should also bridge portable cheap/balanced/strong classes to the main work-shape policy so runtime vocabularies do not drift.

The adapter reference should stay short and point to runtime-owned documentation rather than copying it. Implementation must verify the currently installed Claude Code and Codex invocation syntax rather than guessing fragile command examples.

### 8. Do not change the Pi model-tier router in v1

No extension code change is required for the first implementation:

- Invoking `orchestrate` can route the parent through its own frontmatter.
- Child execution is already supported by runtime-native subagent tooling and local agent/model configuration.
- Nested upward-only routing is desirable for the parent because a coordination run should not accidentally downshift its judgment model.
- Restoration behavior remains useful after the orchestration run settles.

Avoid intercepting or rewriting `subagent` tool calls in the model-tier router. That would couple two extensions, duplicate confirmation behavior, and make shared policy dependent on Pi internals.

Document one deferred enhancement, tracked by `skills-88v.5`, but do not implement it in orchestrate v1: a read-only semantic tier resolver/tool or RPC that reuses the router's trusted config merge, candidate availability, fallback ordering, and metered classification and returns model, effort, metered status, and source without launching anything. Until that integration exists, Pi v1 inherits unless an explicit verified mapping is already supplied; the skill must not duplicate resolver logic.

### 9. Update documentation and indexes

Update:

- `skills/README.md` description table with `orchestrate`.
- `skills/README.md` model-routing table under `premium-reasoning`, with effort `high`, no Claude `model:` pin, and a tier guard. Add a brief footnote explaining that `high` is deliberate for routine parent coordination while `xhigh` remains reserved for harder planning/review.
- `MODEL_ROUTING.md` with the parent-vs-child clarification plus the precise bounded-edit orchestration exception from section 4. Preserve `standard-coding` as the default for ordinary code-writing skills; invoking a lower-tier nested skill does not downshift the parent.
- Keep the corrected wording in `README.md`, and update `Makefile`, `assemble.sh`, and `agents/README.md` where necessary to replace stale claims that Codex has no subagent concept. State instead that `make apply-codex` skips this repo's Claude-style Markdown `agents/` layer while installed Codex versions may provide native multi-agent tools.
- Runtime-adapter documentation with conditional verified child mappings and honest inherited/no-downshift behavior. The implementation must not mutate canonical user or project subagent settings.

Do not add a new top-level shared agent. The skill coordinates runtime-provided agents; a second shared "foreman agent" would duplicate authority and the shared `agents/` packaging remains Claude-specific.

## Alternatives considered

1. **Extend the Pi router to auto-spawn or rewrite child models now** — rejected for v1. It couples independent extensions, is Pi-only, and is unnecessary to validate the policy.
2. **Copy the colleague's Codex skill nearly verbatim** — rejected. It hard-codes Codex model names/effort assumptions and lacks this repo's cross-runtime routing and safety boundaries.
3. **Create a shared `foreman` agent instead of a skill** — rejected. This repo's shared Markdown agents are currently assembled only for Claude Code, and a second orchestration authority would conflict with the parent-agent contract. Codex native multi-agent capability does not require adding a shared agent file.
4. **Put all Pi instructions in the main `SKILL.md`** — rejected. It would make the shared skill noisy and less portable; use a small runtime adapter reference.
5. **Add a new balanced/bounded-coding semantic tier immediately** — deferred. It might better represent Terra/Sonnet bounded implementation, but should follow evidence from dogfooding rather than widening taxonomy and local config now.
6. **Set global Pi `agentOverrides` for canonical roles** — rejected. It would change every Pi subagent workflow, not only `/orchestrate`.
7. **Create namespaced duplicate orchestration roles** — deferred as unnecessary in v1. Orchestrate can reuse builtin roles with inherited settings until explicit verified mappings or a resolver are available.

## Implementation slices

1. Add `skills/orchestrate/SKILL.md` with frontmatter, explicit-only trigger, settled premium/high parent route, boundaries, proportionate judgment packet, conditional child-route policy, one-writer workflow, child metered/unknown-cost gate, escalation rules, optional established-tracker policy, serial-fallback disclosure, completion rules, and premium tier guard.
2. Add `skills/orchestrate/references/runtime-adapters.md` with mandatory capability detection, honest inherited/verified-mapping Pi behavior, Pi async/wait/fresh-context recovery, Claude Code floating child mappings, and conditional Codex native multi-agent mappings.
3. Update `skills/README.md` in both required tables.
4. Add the parent-vs-child routing clarification and child-cost distinction to `MODEL_ROUTING.md`.
5. Preserve the corrected root `README.md` wording and correct the remaining stale Codex-agent wording in `Makefile`, `assemble.sh`, and `agents/README.md` without changing assembly behavior.
6. Run repository validation and manually inspect Claude and Codex assembly output.
7. Dogfood explicit invocation in Pi, Claude Code, and Codex, including inherited/no-downshift behavior, effective child-model evidence when mappings exist, metered and unknown-classification consent/decline, serial fallback, and optional established-tracker context before considering any router/RPC enhancement.

## Test strategy

### Required implementation checks

- Manually inspect frontmatter for required semantic fields, read-only Beads access, named `Skill(...)` permissions only, `disable-model-invocation: true`, and the deliberate absence of a Claude `model:` pin. The repo has no dedicated frontmatter/schema test target; assembly checks do not validate metadata semantics.
- Verify the description table remains alphabetical.
- Verify the routing table places `orchestrate` under `premium-reasoning` with the intended policies, `high` effort, guard marker, and explanatory footnote.
- Confirm all relative links from `SKILL.md` resolve.
- Verify the bounded-edit exception in `MODEL_ROUTING.md` remains narrow and does not permit ordinary coding skills to declare cheap/workflow tiers.
- Run `make dry-run` and `make dry-run-codex`.

### Approval-dependent rollout checks

- Ask before running `make apply` or `make apply-codex`, because they mutate managed symlinks.
- After approval/application, run `make doctor` and `make doctor-codex`.
- Verify both `~/.claude/skills/orchestrate` and `~/.codex/skills/orchestrate` resolve to the new source directory.

### Environment-dependent dogfood checks

- Restart/reload Pi as needed and verify the explicit skill command is discovered from the configured shared skill path.
- Inspect Pi's effective builtin role models/thinking. Run with inherited settings by default; only run mapped-model checks when an explicit verified mapping is supplied.
- Run bounded launches in Claude Code and Codex and capture the effective child model/effort or an explicit report that the runtime inherited defaults.
- Treat cross-runtime launches, unavailable-feature/fallback simulations, and latency/quota observations as environment-dependent evidence, not required implementation checks.

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
11. Trusted local policy: accept only a user-owned declaration supplied to the active session with runtime, effective identity, explicit metered value, and user/approved-project scope; reject arbitrary repository text or inference as classification evidence.
12. Ad hoc policy offer: a confirmation applies only to the current disclosed run/panel and is not persisted automatically; any durable user-level policy change is proposed and approved separately.
13. Verified unmetered child: launch normally with effective identity/effort evidence.
14. Verified metered child or panel: ask before launch; declining continues serially.
15. Inherited or otherwise unknown-classification child: disclose inherited/no-downshift behavior and ask before delegation; declining continues serially.
16. Parent-route confirmation: confirm it is not reused as authorization for child fanout; expanding an approved bounded panel asks again.
17. Pi async launch: launch asynchronously and use `wait()` when the same turn must continue to completion.
18. Pi fork unavailable: retry with `context: "fresh"` only for a self-contained judgment packet.
19. Pi inherited routing: inspect builtin model/thinking metadata and verify the unknown-classification consent gate before a bounded inherited child.
20. Pi mapped routing, conditional: when the user/runtime supplies verified identity plus metered status, launch or ask according to classification and verify run evidence.
21. Claude effective routing: exercise a floating alias only with trusted cost classification; otherwise test the unknown-classification gate and report inherited effort if it cannot be set independently.
22. Codex capability and routing: capability-detect native multi-agent support without version gating; without verified identity/classification, guarantee inherited/no-downshift disclosure plus consent. Exercise mapped-model and unavailable-feature fixtures only when those conditions can be supplied.
23. Tracker context: use Beads only when `bd`, active Beads context, and a relevant bead exist; otherwise use the established tracker or generic milestone suggestions. Never create ephemeral per-agent tracker items; `/triage` is Beads-only and approval-gated.
24. Control-plane context: consume a present `skills-88v.6`-style canonical index without requiring one or silently rewriting it.
25. Pi model lifecycle: `/model-tier status` shows the parent route during the run and the original model/thinking restores after settlement.
26. Cheap-bulk effort experiment: record latency, retries/corrections, tool-call count, and observable quota usage at medium; lower an individual workflow to low only when the saving is meaningful and reliability does not regress.

## Risks and mitigations

- **Duplication with `pi-subagents`:** keep the main skill policy-level and the Pi adapter short; reference rather than restate runtime mechanics.
- **Over-orchestration:** require explicit user invocation, a delegation ROI check, proportionate packets, and explicit skipping of trivial, serial, or tightly coupled work.
- **Confused authority:** state that the parent owns architecture, scope, integration, approval, and final response; children escalate decisions.
- **Parallel write corruption:** one writer by default; require worktree isolation for intentional parallel writers.
- **Cross-runtime drift:** runtime adapters must be capability-detected, use verified native mechanisms, and degrade to disclosed serial self-validation.
- **Child route not actually applied:** inherit by default; pass a model only when an explicit verified mapping exists, verify effective routing when used, and report rather than imply a downshift when mapping or evidence is missing.
- **Router logic duplicated in the skill:** never parse/merge tier config or reproduce availability/fallback/metered decisions; keep semantic resolution deferred to `skills-88v.5`.
- **Global behavior accidentally changed:** do not modify canonical Pi role overrides or project/user settings in v1.
- **Tracking noise or lock-in:** use a relevant established tracker only when present, keep ephemeral child/review/retry state in runtime artifacts, use `/triage` only for approved durable milestones in Beads-enabled repositories, and otherwise report milestone suggestions generically.
- **Unknown child billing:** require trusted identity plus metered classification; ask before metered or unknown children/panels, and never treat parent-route confirmation as fanout approval.
- **Premium cost creep:** use `effort: high`, cap normal fanout, use `ask-above-standard` for the parent, and reserve xhigh/max for explicit risk.
- **Implicit child rerouting by tiered skills:** delegated workers should receive direct bounded task contracts and only load another tiered skill deliberately; if this becomes a recurring source of unexpected upgrades, capture it during dogfooding before altering the router.

## Rollout and rollback

- Rollout is explicit-only: add and assemble the new skill, then dogfood orchestration on low-risk tasks through the runtime's skill command (`/skill:orchestrate` in Pi). Pi inherits by default until a verified mapping or resolver exists.
- No model-tier-router code migration or Pi settings mutation is required; normal skill discovery/reload is the only Pi runtime change.
- Roll back by removing the skill directory and documentation rows, then re-running Claude/Codex apply and doctor targets.
- Router behavior remains unchanged, so rollback does not affect model selection for existing skills.

## Independent validation and resulting changes

Six independent review passes agreed with the core design: create a shared policy skill, keep parent judgment strong, do not add a new shared agent/frontmatter tier, and keep Pi semantic child resolution out of orchestrate v1. They identified corrections incorporated into this final plan:

- Made invocation explicitly opt-in with `disable-model-invocation: true` to avoid surprise premium upgrades.
- Added the repo-conventional `allowed-tools` surface.
- Clarified that semantic downshift happens only by launching a child on that route; a lower-tier nested skill cannot downshift the already-routed parent.
- Made the judgment packet proportionate rather than requiring eight fields for trivial recon.
- Trimmed Pi mechanics in favor of referencing `pi-subagents` and its existing review-loop behavior.
- Named Claude Code's per-subagent model override.
- Replaced global canonical Pi role overrides with inherited Pi behavior by default and conditional per-launch selection only when an explicit verified mapping already exists.
- Prohibited the skill from duplicating the router's trusted config merge, availability, fallback, and metered logic; deferred a real resolver to `skills-88v.5`.
- Defined Claude's cheap/balanced/strong floating mappings and conditional Codex runtime-local model/reasoning mappings.
- Required bounded launch evidence of effective child model/effort when a mapping is used instead of trusting settings inspection, including protection against project settings silently superseding user defaults.
- Required fresh/separate reviewer context for genuine independence where supported.
- Corrected the Codex adapter after verifying installed Codex `0.144.3` has stable native `multi_agent`; serial execution is fallback, not the default promise.
- Separated premium-parent metered policy from child/panel confirmation because the model-tier router does not inspect child launches.
- Settled `premium-reasoning`/high for the explicit substantial-work parent rather than leaving it as a dogfooding question.
- Defined serial fallback as disclosed self-validation and routed genuine independence through `/second-opinion`.
- Narrowed Git preapproval, made runtime-adapter loading mandatory, and expanded Pi/Codex rollout tests.
- Added the narrow bounded-edit exception needed to reconcile cheaper orchestrated writers with `MODEL_ROUTING.md` while preserving `standard-coding` as the ordinary writer default.
- Split required, approval-dependent, and environment-dependent validation.
- Defined verified child routing as effective identity plus trusted metered classification; metered or unknown children require separate consent, and parent-route confirmation does not authorize fanout.
- Defined user-approved local policy as a scoped, user-owned runtime declaration; ad hoc consent remains run-scoped and is never persisted automatically.
- Replaced broad `Skill` permission with named skill permissions and required the implementation to present consent as a compact decision table.
- Removed pinned Codex version wording from the runtime-adapter contract, clarified the `standard-coding` mapping row, and linked the optional `skills-88v.6` control-plane integration without making it a dependency.
- Made durable tracking portable: use Beads only when active/relevant, otherwise use the established tracker or generic milestone suggestions; `/triage` remains Beads-only and approval-gated.
- Added documentation/test checks for the deliberate premium/high combination, no model pin, and explicit-only invocation.

One review claim was softened rather than accepted as an absolute blocker: `allowed-tools` is optional in the Agent Skills/Pi specification, but it is present on 43 of 46 existing shared skills and is useful here as a pre-approval surface, so the final plan includes it as a repository convention.

## Open questions for dogfooding, not implementation blockers

- Does Pi orchestration evidence justify implementing the read-only semantic child-tier resolver/tool or RPC tracked by `skills-88v.5`?
- Does the balanced worker route cover bounded implementation reliably, and should a future portable `bounded-coding` tier formalize it across runtimes?
- Which cheap-bulk workflows can safely return from medium to low effort based on measured latency/quota savings and unchanged reliability?

## Recommended implementation tier

Use `standard-coding` for the skill implementation because it is primarily Markdown policy and documentation with careful cross-runtime semantics. Use `premium-review` only for a final policy/maintainability review if desired.

## Next concrete action

Continue `skills-88v.2` using `plans/orchestrate-dogfood-evidence.md`: preserve observed-versus-fixture labels, fix policy defects exposed by review, collect separately consented low-risk Pi/Claude/Codex evidence where trusted routing permits it, and use the results to decide whether `skills-88v.3` through `.5` are justified. Do not manufacture mapped-route evidence, persist ad hoc policy, or create tracker items per child run.
