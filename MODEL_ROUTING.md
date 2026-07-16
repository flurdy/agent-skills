# Model Routing and Cost Policy

This repo is shared by Claude Code, pi.dev, and Codex. Skills should describe the
capability and cost tier they need; exact provider/model IDs belong in each
runtime's configuration whenever possible.

## Principles

- Prefer subscription/OAuth routes before metered API-key routes.
- Do not make `/architect` or other planning skills automatically mean
  "use Claude/Opus".
- Treat Claude via pi.dev OAuth as premium/metered extra usage: use it
  deliberately for judgement, review, architecture taste, refactor critique, and
  maintainability concerns. This is distinct from invoking `claude -p` with an
  existing `claude.ai` subscription login, which consumes subscription usage;
  Claude CLI API-key/BYOK authentication remains metered.
- Treat OpenRouter as metered credits/BYOK: useful for cheap, fallback, and
  experimental models, but cap it and avoid default long-running loops.
- Use Gemini only as an optional secondary opinion, particularly when a different
  provider or long-context perspective is useful.
- Route routine workflow orchestration to Terra/Sonnet at medium effort. Route
  bounded, well-specified implementation to the same class at high effort, and reserve
  Sol/Opus for advanced implementation that needs meaningful local design judgment.
- Treat model capability and thinking effort as separate choices: `model-tier` selects
  the model class, while `effort` selects reasoning depth.
- For implementation after a plan, prefer `focused-coding` when scope and validation
  are fixed; use `advanced-coding` when implementation still carries design risk.

## Skill front matter

Prefer capability metadata over hard-coded model names:

```yaml
model-tier: premium-reasoning
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
model-second-opinion-tier: independent-reasoning
effort: xhigh
```

These fields are intentionally semantic. Runners that do not understand them
should ignore them; the skill body should still explain any important routing or
cost guardrails in plain language.

Skills also keep a floating `model:` alias matching their tier — `haiku` for
cheap-bulk, `sonnet` for standard-workflow, focused-coding, and long-context-audit,
and `opus` for advanced-coding — because Claude Code reads `model` directly and
would otherwise run every skill on the (possibly premium) session model. Premium
tiers omit it so the session model applies. pi's model-tier router ignores `model:`
in skill files but pi honors it in **agent** files, so agents never set it (it would
route pi to metered Claude).

Premium-tier skills carry no `model:` pin (they should ride the best session
model), so each starts with a **tier guard**: if the running model is below the
declared tier, say so and ask whether to continue at reduced depth or stop and
switch. Advisory, not enforced — copy the guard block from
`skills/architect/SKILL.md` when authoring a new premium skill.

### Parent and child routing

Skill routing applies to the current parent agent. Invoking a lower-tier skill from
an already-routed parent does not downshift it: Pi's router permits nested upgrades
but retains equal or lower tiers. A downshift happens only through a runtime-native
child launch with an explicit verified child mapping.

Treat parent and child cost approval separately. Parent-route preferences in the
principles above describe configured runtime policy; they are not trusted child
billing classification. The Pi model-tier router can confirm the parent route but does
not inspect child launches. A child mapping is verified only
when trusted runtime/resolver evidence resolves its effective model identity before
launch and trusted metadata or user-approved local policy supplies
`metered: true|false`; launch evidence should confirm the identity when available.
When identity resolves only after exposure, classify the route as unknown and ask
first. A mismatch invalidates the classification and stops further fanout until a new
disclosure/decision. Never infer billing from provider, model name, authentication
type, or the parent route. Metered or unknown/inherited children require separate
current-run consent. Parent consent never authorizes fanout, and an ad hoc child/panel
approval must not be persisted.

**Dynamic-loop dashboard skills** (`watch-prs`, `pr-status`) cannot rely on a
skill alias for loop ticks: `ScheduleWakeup` wakeup prompts run on the *session*
model, ignoring skill `model:` pins. A tick that must render then self-schedule
also breaks on Fable-class session models — they defer their main output to a
final message after all tool calls, which `ScheduleWakeup`'s turn-end discards,
leaving blank ticks (verified by A/B: identical ticks render on a Sonnet session,
blank on a Fable session, Jul 2026). Hence `watch-prs` has no pin and uses a
session-model guard; Sonnet/Opus sessions and cron-fired fixed mode are fine.

## Tiers

GPT entries name the Terra/Sol/Luna capability split, not a pinned version — use the
latest available model in that split.

```yaml
tiers:
  cheap-bulk:
    primary: openai-oauth:gpt-luna
    fallback: openrouter:qwen-coder
    default-effort: medium
    use-for: Cheap status checks, mechanical scans, low-risk summaries.

  standard-workflow:
    primary: openai-oauth:gpt-terra
    fallback: anthropic-oauth:claude-sonnet
    default-effort: medium
    use-for: Git, release, tracker, status, and workflow orchestration.

  focused-coding:
    primary: openai-oauth:gpt-terra
    fallback: anthropic-oauth:claude-sonnet
    default-effort: high
    use-for: Bounded, well-specified implementation with one writer, established patterns, and objective validation.

  advanced-coding:
    primary: openai-oauth:gpt-sol
    fallback: anthropic-oauth:claude-opus
    default-effort: high
    use-for: Implementation with meaningful local design judgment, complex conflicts, migrations, or unclear boundaries.

  long-context-audit:
    primary: openai-oauth:gpt-sol
    fallback: anthropic-oauth:claude-opus
    default-effort: high
    use-for: Repo-wide summarisation, large diffs, broad document/release audits.

  premium-reasoning:
    primary: openai-oauth:gpt-sol
    fallback: anthropic-oauth:claude-opus
    default-effort: xhigh
    note: Claude may be metered extra usage, so use deliberately.
    use-for: Architecture, hard planning, high-risk verification, costly mistakes.

  premium-review:
    primary: anthropic-oauth:claude-opus
    fallback: openai-oauth:gpt-sol
    default-effort: xhigh
    note: Use only for review/judgement, not long grind loops.
    use-for: Maintainability critique, refactor taste, PR judgement, craft review.

  independent-reasoning:
    kind: external-opinion-policy
    rule: choose a provider DIFFERENT from the model that produced the work;
      prefer subscription routes first.
    from-claude-session: openai-oauth (codex CLI), then gemini-oauth
    from-gpt-session: claude CLI (prefer claude.ai subscription; API-key/BYOK is metered), then gemini-oauth
    panel-extras: openrouter:qwen-reasoning, openrouter:grok-4.5
    note: This is not an ordinary ranked router tier. Panel extras are metered;
      ask or cap before broad panels.
    use-for: Cross-checking plans, PRs, root-cause analysis, independent critique.
```

## Thinking effort

`effort` is orthogonal to `model-tier`. Use `medium` by default for cheap mechanical
work and routine orchestration, `high` for implementation, and `xhigh` for premium
reasoning/review where missing a subtle issue is costly. Use `low` only after
dogfooding shows a deterministic workflow remains reliable and the latency or quota
saving matters. Reserve `max` for explicit all-in requests; never make it a default.

The pi model-tier router uses the tier's configured thinking level as a fallback,
honors a valid skill `effort`, and allows nested skills to raise but never lower
effort during a run. Runtimes that do not understand `effort` should ignore it.

## Focused-coding eligibility

`focused-coding` is the lowest ordinary code-writing class. Use it only when all of
these conditions hold:

- Owned files/modules, established implementation pattern, explicit non-goals,
  acceptance criteria, exact verification, and escalation/stop conditions are fixed.
- One writer owns the shared worktree; changed-line count is not used as a risk proxy.
- Success is objectively testable without asking the writer to invent architecture,
  product behavior, permissions, public contracts, or migration policy.
- Newly exposed complex conflict, compatibility, or already-decided migration
  implementation escalates to `advanced-coding`.
- Newly exposed product, permission, public-contract, security, destructive,
  migration-policy, or architectural decisions return to premium parent judgment or
  the user instead of being decided by an implementation tier.

Inside `/orchestrate`, the child mapping must still have verified effective identity
and trusted metered classification, and the child-cost gate must be satisfied. This
tier does not permit code-writing skills to declare `cheap-bulk` or
`standard-workflow`. When focused eligibility is unclear, use `advanced-coding`.

## Policy enforcement

Skill tier assignment expresses `cheapest-adequate`, while candidate ordering in
each runtime expresses `prefer-subscription-oauth`; both metadata fields remain
advisory. The pi router enforces metered confirmation but does not implement token
caps or dynamic provider independence. `/second-opinion` owns the
independent-provider rule and panel caps.

## `model-cost-policy` values

- `prefer-subscription-oauth` — use OAuth/subscription providers before metered
  API-key providers.
- `cheapest-adequate` — choose the lowest tier that can responsibly complete the
  task.
- `deliberate-premium` — premium is expected, but explain why and avoid loops.

## `model-metered-policy` values

- `ask-above-standard` — ask before using metered/premium routes beyond the
  ordinary configured coding baseline.
- `cap-or-ask` — set a small explicit cap or ask before using metered routes.
- `ask-before-metered-panel` — ask before running multiple external/metered
  agents in parallel.

## Client notes

- **pi.dev:** stock pi ignores these extra skill fields, but the model-tier router
  in `ai-tools` honors `model-tier`, cost/metered policies, and `effort`. Agent
  files can honor `model:`, so agents omit it.
- **Claude Code:** Claude Code reads the `model` and `effort` frontmatter fields
  directly, so non-premium skills keep a floating alias (`haiku`/`sonnet`/`opus`)
  as an enforcement hint. Single alias only (no lists, no dated IDs); the
  canonical policy is the tier.
- **Codex:** keep provider/model selection in Codex configuration or CLI flags;
  skills should not bake in one model ID.
