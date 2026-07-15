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
- Use Gemini OAuth for long-context audit, repo-wide summarisation, or broad
  document review.
- Route routine workflow orchestration to Terra/Sonnet and implementation workflows
  that edit or deeply reason about code to Sol/Opus.
- Treat model capability and thinking effort as separate choices: `model-tier` selects
  the model class, while `effort` selects reasoning depth.
- For implementation after a plan, prefer the standard coding tier unless the plan
  explicitly says the implementation itself needs premium reasoning.

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
cheap-bulk, `sonnet` for standard-workflow and long-context-audit, and `opus` for
standard-coding — because Claude Code reads `model` directly and would otherwise
run every skill on the (possibly premium) session model. Premium tiers omit it so
the session model applies. pi's model-tier router ignores `model:` in skill files
but pi honors it in **agent** files, so agents never set it (it would route pi to
metered Claude).

Premium-tier skills carry no `model:` pin (they should ride the best session
model), so each starts with a **tier guard**: if the running model is below the
declared tier, say so and ask whether to continue at reduced depth or stop and
switch. Advisory, not enforced — copy the guard block from
`skills/architect/SKILL.md` when authoring a new premium skill.

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

  standard-coding:
    primary: openai-oauth:gpt-sol
    fallback: anthropic-oauth:claude-opus
    default-effort: high
    use-for: Workflows that edit code, resolve conflicts, migrate data, or require implementation-grade reasoning.

  long-context-audit:
    primary: gemini-oauth
    fallback: openai-oauth:gpt-sol
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
  standard coding tier.
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
