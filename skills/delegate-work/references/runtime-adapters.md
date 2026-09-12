# Runtime adapters

Read [`child-routing-policy.md`](child-routing-policy.md) first. Load this reference
only after detecting the active runtime. Follow installed runtime documentation and
tools when they differ from these capability-level notes. Never mutate runtime
settings, agent definitions, or cost policy during a delegation run.

## Pi

1. If `pi-subagents` is installed, load its skill and use it for discovery, launch,
   async lifecycle, context modes, one-writer safety, review recipes, and supervisor
   coordination. Do not reproduce its mechanics.
2. Immediately before each launch, use installed discovery and builtin model
   reporting: `subagent({ action: "list", capabilities: true })`, then
   `subagent({ action: "models", agent: "<agent>" })`. Use only executable,
   non-disabled **native Pi agents only** for configured-consent handling. External CLI
   and job adapters keep their own route policy.
3. Retain every exact primary and every fallback model reported for that agent. An
   unresolved, bare or ambiguous identity is unknown. Call `model_policy_evidence`
   once with the complete ordered exact set. Do not read, parse or merge router files
   yourself. Missing tool, unsupported evidence version, non-`loaded` source, stale
   revision, unmatched row, `unknown`, `invalid`, `conflict`, `missing`, `unavailable`
   or metered/`ask` evidence requires bounded current-run confirmation.
4. Skip only the billing prompt when every row is unmetered/`not-needed` or exact
   metered/`allow`. Report source owner, revision and each policy basis. Keep execution
   and fanout authorization separate; pass the exact primary model from the trusted
   report to the launch and set `fast: false`; this prevents an unreviewed priority
   service tier. The current adapter has no atomic check-and-launch primitive, so
   repeat model reporting and the policy query immediately before each launch and
   recheck after every route/configuration event named by the child policy.
5. If any required fact is unavailable, disclose inherited/no-downshift or fallback
   behavior, classify billing as unknown, and apply the consent gate. If declined,
   continue serially.
6. Launch asynchronously by default. If the turn must finish the delegated work, call
   `wait()` when no independent parent work remains; do not poll or end the turn with
   required children still live.
7. For prose-only review with no acceptance ledger, current `pi-subagents` requires an
   explicit reason, for example
   `acceptance: { level: "none", reason: "Read-only prose review" }`. The string
   shorthand `"none"` does not lower an inferred stronger gate. Otherwise require the
   appropriate structured acceptance evidence.
8. Prefer each role's default context. If a forked role cannot start because the parent
   session is not persisted, retry with `context: "fresh"` only when the judgment
   packet is self-contained. Otherwise continue in the parent.
9. Use `context-builder`/`researcher` for bounded read-only work, `worker` for writes,
   a fresh `reviewer` for independent review, and `oracle` only for strong advisory
   judgment. The parent integrates and validates.

If `pi-subagents` is unavailable, continue serially and disclose self-validation. Pi
v1 deliberately does not resolve semantic child tiers itself.

## Claude Code

1. Capability-detect the native Agent/Task subagent tool exposed by the active
   session. Keep architecture and integration in the parent and give every child
   explicit bounded ownership.
2. Use a native per-invocation child override without another cost prompt only when
   trusted runtime evidence resolves its floating alias to the policy identity before
   launch. Portable aliases are cheap -> `haiku`, balanced -> `sonnet`, and strong ->
   `opus`; never assume their current resolution.
3. When alias resolution is available only after launch, follow the unknown-route
   path before exposure and confirm the launched identity afterward.
4. Without a verified mapping, inherit the parent model, disclose that no downshift is
   guaranteed, and apply the unknown-classification gate.
5. Request child effort through native controls when available. Otherwise report
   inherited/default effort; do not claim an override.
6. Use one implementation-capable child for writes and fresh/separate children for
   independent review. Do not assume a child sees the parent conversation; include a
   self-contained judgment packet.

If native delegation is unavailable, continue serially and disclose self-validation.

## Codex

1. Capability-detect native multi-agent/subagent tools. Do not gate on a pinned Codex
   version or treat this repository's skipped Claude-style `agents/` assembly layer as
   evidence that Codex cannot delegate.
2. Use native delegation when available. Personal agents can live under
   `$CODEX_HOME/agents/*.toml` and project agents under `.codex/agents/*.toml`;
   omitted model or reasoning settings inherit from the parent/runtime.
3. Select configured cheap/balanced/strong child settings only when the child-routing
   policy verifies them. Otherwise inherit, disclose no guaranteed downshift, and
   apply the unknown-classification gate.
4. Keep the parent on requirements, decisions, integration, and final output. Favor
   parallel read-heavy exploration, testing, and review; use one writer unless
   isolated worktrees and non-overlapping ownership were explicitly chosen.
5. Respect inherited sandbox and permission policy. Do not weaken it for convenience.

If native multi-agent capability is unavailable, continue serially and disclose
self-validation.

## Other runtimes

Capability-detect native delegation without inventing mappings. Apply the same launch
gate, bounded packet, one-writer rule, fresh-review preference, and parent authority.
When delegation or trustworthy route evidence is unavailable, continue serially and
disclose self-validation.
