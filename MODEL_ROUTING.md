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
  maintainability concerns.
- Treat OpenRouter as metered credits/BYOK: useful for cheap, fallback, and
  experimental models, but cap it and avoid default long-running loops.
- Use Gemini OAuth for long-context audit, repo-wide summarisation, or broad
  document review.
- For implementation after a plan, prefer a standard/cheaper coding tier unless
  the plan explicitly says the implementation itself needs premium reasoning.

## Skill front matter

Prefer capability metadata over hard-coded model names:

```yaml
model-tier: premium-reasoning
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
model-second-opinion-tier: independent-reasoning
```

These fields are intentionally semantic. Runners that do not understand them
should ignore them; the skill body should still explain any important routing or
cost guardrails in plain language.

Skills also keep a floating `model:` alias matching their tier — `haiku` for
cheap-bulk, `sonnet` for standard-coding and long-context-audit — because Claude
Code reads `model` directly and would otherwise run every skill on the (possibly
premium) session model. Premium tiers omit it so the session model applies. pi
ignores `model:` in skill files but honors it in **agent** files, so agents never
set it (it would route pi to metered Claude).

Premium-tier skills carry no `model:` pin (they should ride the best session
model), so each starts with a **tier guard**: if the running model is below the
declared tier, say so and ask whether to continue at reduced depth or stop and
switch. Advisory, not enforced — copy the guard block from
`skills/architect/SKILL.md` when authoring a new premium skill.

**Dynamic-loop dashboard skills** (`watch-prs`, `pr-status`) keep the alias, but
note it does NOT reach loop ticks: `ScheduleWakeup` wakeup prompts run on the
*session* model, ignoring skill `model:` pins. And a tick that must render then
self-schedule breaks on Fable-class session models — they defer their main output
to a final message after all tool calls, which `ScheduleWakeup`'s turn-end
discards, leaving blank ticks (verified by A/B: identical ticks render on a
Sonnet session, blank on a Fable session, Jul 2026). Hence `watch-prs`'s
session-model guard; Sonnet/Opus sessions and cron-fired fixed mode are fine.

## Tiers

GPT entries name the Terra/Sol/Luna capability split, not a pinned version — use the
latest available model in that split.

```yaml
tiers:
  standard-coding:
    primary: openai-oauth:gpt-terra
    fallback: openrouter:qwen-coder
    use-for: Daily coding, routine workflow orchestration, straightforward fixes.

  premium-reasoning:
    primary: openai-oauth:gpt-sol
    fallback: anthropic-oauth:claude-sonnet
    note: Claude may be metered extra usage, so use deliberately.
    use-for: Architecture, hard planning, high-risk verification, costly mistakes.

  premium-review:
    primary: anthropic-oauth:claude-sonnet
    fallback: openrouter:grok-4.5
    note: Use only for review/judgement, not long grind loops.
    use-for: Maintainability critique, refactor taste, PR judgement, craft review.

  cheap-bulk:
    primary: openrouter:qwen-coder
    note: Metered; cap usage and avoid unlimited loops.
    use-for: Cheap status checks, mechanical scans, low-risk summaries.

  independent-reasoning:
    primary: openrouter:qwen-reasoning
    fallback: openrouter:grok-4.5
    note: Metered; ask or cap before broad panels.
    use-for: Cross-checking plans, PRs, root-cause analysis, independent critique.

  long-context-audit:
    primary: gemini-oauth
    use-for: Repo-wide summarisation, large diffs, broad document/release audits.
```

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

- **pi.dev:** skill front matter is ignored except `name`, `description`, and
  `disable-model-invocation` (verified on 0.80.6) — skills always run on the
  current pi session model. Agent files *can* honor `model:`, so agents omit it.
- **Claude Code:** Claude Code reads the `model` frontmatter field directly, so
  non-premium skills keep a floating alias (`haiku`/`sonnet`) as an enforcement
  hint. Single alias only (no lists, no dated IDs); the canonical policy is the tier.
- **Codex:** keep provider/model selection in Codex configuration or CLI flags;
  skills should not bake in one model ID.
