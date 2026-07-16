# Runtime adapters

Load this reference only after detecting the active runtime. Follow the runtime's
installed documentation and tools when they differ from these capability-level
notes. Never mutate runtime settings, agent definitions, or cost policy during an
orchestration run.

## Trusted local policy channels

A local declaration is trusted only when it is user-owned, supplied to the active
session, and states the runtime, effective child route/model identity, explicit
`metered: true|false`, and scope (`user` or an explicitly approved project). Project
scope must also name a stable project identity or absolute root; `scope: project`
alone is ambiguous. Runtime model configuration proves routing intent but does not,
by itself, prove billing classification.

Use the runtime's own instruction mechanism rather than inventing a shared settings
file:

- **Pi:** user instructions in `~/.pi/agent/AGENTS.md`. Child model overrides may
  come from user `~/.pi/agent/settings.json` or an explicitly approved project
  `.pi/settings.json`, but their cost classification still needs trusted metadata or
  the user instruction declaration.
- **Claude Code:** user instructions in `~/.claude/CLAUDE.md`. A personal,
  gitignored `CLAUDE.local.md` may carry a user-approved project-scoped declaration;
  checked-in project instructions alone never qualify. Verify the declaration is
  loaded in the active Claude session (for example via `/memory` or an equivalent
  startup/context report) before trusting it. A child model may come from a native
  per-launch override or subagent definition.
- **Codex:** global instructions in `$CODEX_HOME/AGENTS.md` (normally
  `~/.codex/AGENTS.md`; an active `AGENTS.override.md` takes precedence). That
  user-owned declaration may limit a route to an explicitly approved project.
  Custom agent model/effort settings may live under `$CODEX_HOME/agents/` or project
  `.codex/agents/`, but checked-in `AGENTS.md` never supplies cost classification.

Arbitrary repository text, inferred authentication, or a model/provider name is not
trusted classification. Resolve the effective child identity before launch whenever
its classification would otherwise avoid a prompt. If the runtime can reveal identity
only after launch, use the unknown-route consent path before exposure, then confirm
the identity from launch evidence. A mismatch invalidates the classification, stops
further fanout on that route, and requires a new disclosure/decision. Ad hoc approval
applies only to the disclosed current run or panel and must never be written back
automatically.

## Semantic class bridge

Keep runtime-local names subordinate to the shared work-shape policy:

- **Cheap:** focused read-only lookup/recon only.
- **Balanced:** bounded implementation or routine review with objective validation.
- **Strong / `standard-coding`:** implementation requiring meaningful local design
  judgment.
- **Premium:** architecture, high-impact decisions, and final judgment retained by
  the parent.

If a runtime cannot map these classes without guessing, inherit with disclosure and
unknown-route consent or continue serially.

## Pi

1. If `pi-subagents` is installed, load its skill and use it for discovery, launch,
   async lifecycle, context modes, one-writer safety, review recipes, and supervisor
   coordination. Do not reproduce its mechanics.
2. Immediately before every launch, use the installed discovery and builtin
   model-reporting actions (currently `subagent({ action: "list" })` and
   `subagent({ action: "models" })`). Repeat model reporting after any skill read,
   router event, manual model change, or other action that may have changed the parent
   route; do not reuse stale preflight evidence. Use only executable, non-disabled
   roles.
3. Builtin roles inherit by default. Pass `model` only when supplied mapping evidence
   includes the effective identity and trusted metered classification. Do not read or
   merge model-tier-router files to manufacture that evidence.
4. Without a verified mapping, omit `model`, disclose inherited/no-downshift behavior,
   classify child billing as unknown, and ask before launch. If consent is declined,
   continue serially.
5. Launch asynchronously by default. If this turn must finish the orchestration, call
   `wait()` when no independent parent work remains; do not poll or end the turn with
   live required children.
6. For prose-only review where no acceptance ledger is wanted, current
   `pi-subagents` requires an explicit reason, for example
   `acceptance: { level: "none", reason: "Read-only prose review" }`. The string
   shorthand `"none"` does not lower an inferred stronger gate. Otherwise use a
   review-appropriate contract and require its structured evidence.
7. Prefer each role's default context. If a forked role cannot start because the
   parent session is not persisted, retry with `context: "fresh"` only when the
   judgment packet is self-contained. Otherwise continue in the parent.
8. Use `context-builder`/`researcher` for bounded read-only work, `worker` for writes,
   fresh `reviewer` for independent review, and `oracle` only for strong advisory
   judgment. The parent integrates and validates.

If `pi-subagents` is unavailable, continue serially and disclose self-validation.
Pi v1 deliberately does not resolve semantic child tiers itself; a read-only resolver
remains a possible later enhancement.

## Claude Code

1. Capability-detect the native Agent/Task subagent tool exposed by the current
   session. Keep architecture and integration in the parent and give every child
   explicit bounded ownership.
2. Use a native per-invocation child override without another cost prompt only when
   trusted runtime evidence resolves the floating alias to the policy's effective
   identity before launch. The portable aliases are cheap -> `haiku`, balanced ->
   `sonnet`, strong -> `opus`; never assume their current resolution.
3. If alias resolution is available only after launch, treat the override as unknown,
   disclose it, and ask before exposure. Confirm the launched identity afterward; on
   mismatch, stop further launches on that route and re-gate it as unknown.
4. If no verified mapping exists, inherit the parent model, disclose that no
   downshift is guaranteed, and ask because billing classification is unknown.
5. Request child effort through the native control when available. Otherwise report
   inherited/default effort; do not claim an override. Current native agent
   definitions support a child `effort` field, while runtime capabilities may vary.
6. Use one implementation-capable child for writes and fresh/separate children for
   independent review. Do not assume a child sees the parent conversation; include a
   self-contained judgment packet.

If native delegation is unavailable, continue serially and disclose self-validation.

## Codex

1. Capability-detect native multi-agent/subagent tools. Do not gate on a pinned Codex
   version, and do not treat this repository's skipped Claude-style `agents/` assembly
   layer as evidence that Codex cannot delegate.
2. Use native delegation when available. Personal custom agents can be defined in
   `$CODEX_HOME/agents/*.toml` and project agents in `.codex/agents/*.toml`; supported
   per-agent settings include `model` and `model_reasoning_effort`. Omitted settings
   inherit from the parent/runtime.
3. Pass or select configured cheap/balanced/strong child settings only when effective
   identity and trusted metered classification are verified. Otherwise inherit,
   disclose that no downshift is guaranteed, and ask before the unknown-classification
   launch.
4. Keep the parent on requirements, decisions, integration, and final output. Favor
   parallel read-heavy exploration, testing, and review; use one `worker` for writes
   unless isolated worktrees and non-overlapping ownership were explicitly chosen.
5. Respect inherited sandbox and permission policy. Do not weaken it as an
   orchestration convenience.

If native multi-agent capability is unavailable, continue serially and disclose
self-validation.

## Other runtimes

Capability-detect native delegation without inventing model mappings. Apply the same
pre-launch identity/classification gate, proportionate packet, one-writer rule, fresh
review preference, and parent authority. When either native delegation or trustworthy
route evidence is unavailable, continue serially and disclose self-validation; do not
improvise provider/model IDs from this shared policy.
