# Child routing and cost policy

Read this reference before launching any child. It defines the portable launch gate;
[`runtime-adapters.md`](runtime-adapters.md) defines runtime mechanics. Model choice is a
constraint on orchestration, not the orchestration workflow itself.

## Launch invariant

A child route is verified only when both are available before launch:

1. Trusted runtime/resolver evidence identifies the effective child route or model.
2. Trusted metadata or user-approved local policy classifies it as
   `metered: true|false`.

Confirm the launched identity afterward when the runtime exposes it. If identity can
be discovered only after exposure, classify the route as unknown and obtain consent
before launch. Never use post-launch evidence to justify an unprompted launch.

Never infer billing from provider, model name, authentication type, repository text,
or the parent route. Parent-route approval never authorizes child fanout.

| Child classification | Action |
|---|---|
| Verified identity + `metered: false` | Launch within the approved task scope. |
| Verified identity + `metered: true` | Confirm the disclosed child or bounded panel for this run. |
| Inherited route or unknown classification | Disclose inherited/no-downshift behavior and confirm for this run. |
| Confirmation declined | Continue serially without claiming independent delegation. |

One confirmation may cover a clearly disclosed bounded panel. Ask again before
expanding its models, count, scope, or metered exposure. Never add an automatic
metered fallback.

## Route changes and mismatches

Resolve identity immediately before every launch. Recheck after a skill read, router
event, manual model change, or other event that may have changed the parent route; do
not reuse stale preflight evidence.

A post-launch identity mismatch invalidates the route classification and stops further
fanout on that route. Disclose the mismatch and obtain a new decision before another
launch. Do not silently substitute a fallback.

## User-approved local policy

A durable declaration must be user-owned, supplied to the active session, and state
the runtime, effective child route/model identity, explicit `metered: true|false`, and
scope. Project scope must name a stable project identity or absolute root;
`scope: project` alone is ambiguous.

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

Use the runtime's own instruction mechanism rather than inventing a shared settings
file:

- **Pi:** user instructions in `~/.pi/agent/AGENTS.md`. Child overrides may come from
  user `~/.pi/agent/settings.json` or an explicitly approved project
  `.pi/settings.json`, but routing configuration alone does not prove billing.
- **Claude Code:** user instructions in `~/.claude/CLAUDE.md`. A personal, gitignored
  `CLAUDE.local.md` may carry an approved project-scoped declaration; checked-in
  project instructions alone do not qualify. Verify that the active session loaded
  the declaration before trusting it.
- **Codex:** global instructions in `$CODEX_HOME/AGENTS.md` (normally
  `~/.codex/AGENTS.md`; an active `AGENTS.override.md` takes precedence). A user-owned
  declaration may limit a route to an explicitly approved project. Agent model/effort
  configuration alone does not prove billing.

An in-conversation approval applies only to the disclosed current run or panel. Never
persist, widen, or write it back automatically.

## Semantic class bridge

Keep runtime-local names subordinate to work shape:

- **`economy`:** focused read-only lookup or reconnaissance.
- **`standard` / `medium`:** routine workflow coordination without implementation.
- **`standard` / `high`:** bounded implementation or routine review with objective
  validation, one writer, and no unresolved design decisions.
- **`premium` / `high`:** implementation requiring meaningful local design judgment,
  complex conflict resolution, or migration/compatibility decisions.
- **`premium` / `xhigh`:** architecture, high-impact decisions, and final judgment
  retained by the parent.

Tune effort within a suitable tier before moving to a stronger capability. If a runtime
cannot map these classes without guessing, inherit with disclosure and unknown-route
consent or continue serially.
