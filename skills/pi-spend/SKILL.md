---
name: pi-spend
description: Read-only estimate of Pi model cost by provider and model for today, this week, this month, and all recorded history, separating metered credit usage from flat-rate subscription usage.
allowed-tools: "Bash(~/.agents/skills/pi-spend/scripts/pi_spend.py:*)"
model-tier: economy
model: haiku
effort: medium
version: "1.0.0"
author: "flurdy"
---

# Pi Spend

Answer "what have my metered models cost me lately" from Pi's own session telemetry. Periods are
today, the current week (Monday start), the current calendar month, and all recorded history, all in
the machine's local timezone.

## Usage

```text
/pi-spend                       # all four periods, every provider and model
/pi-spend --metered-only        # hide models the router marks as subscription
/pi-spend --period today        # single period; repeatable
/pi-spend --json                # normalized schema v1 JSON
```

Resolve `scripts/pi_spend.py` relative to this `SKILL.md` and run it with the user's arguments:

```bash
/path/to/pi-spend/scripts/pi_spend.py --metered-only
```

Do not substitute ad-hoc transcript greps or provider billing calls for the collector.

## Output contract

Paste the collector's complete stdout verbatim in a fenced code block, even when the tool card
already shows it. Do not summarize, reformat, or truncate the table. Use a `json` fence for `--json`
and a plain-text fence otherwise.

## Analysis contract

After the verbatim block, add two to four bullets, at most 120 words:

- name the largest metered rows for the requested period and what drove them, distinguishing
  cache-read volume from fresh input;
- state the metered total separately from the subscription total, and never add them into one
  "spend" figure;
- call out the `unknown` billing class when present, since it means the router policy has no entry
  for that model rather than that the model is free; and
- mention responses that recorded no cost only when the collector reports some.

Never describe the output as an invoice, an account balance, or remaining credits.

## Sources and authority

- Pi sessions: `~/.pi/agent/sessions/**/*.jsonl`. Assistant messages carry `provider`, `model`,
  `usage`, and a per-response `usage.cost` breakdown. Responses are deduplicated by `responseId`, so
  nested subagent run transcripts are counted once.
- Billing class: `~/.pi/agent/model-tier-router.json` `modelPolicies[*].metered`. Models absent from
  that config report as `unknown`; the collector does not guess from the provider name.

Pi is the only local harness that records cost. Claude Code transcripts contain no cost field and
Codex rollouts record cumulative token counts only, which is why this skill is Pi-scoped.

## Limitations

- Cost is Pi's own catalog list-price calculation at response time, not a provider invoice,
  subscription allowance, or credit balance. Treat it as an estimate for relative comparison.
- Subscription-billed providers still get a computed cost. That figure is notional and is not
  charged; keep it out of any metered total.
- Coverage is bounded by retained session files. History starts at the oldest surviving transcript,
  so `all` may be shorter than it appears and older periods are not recoverable.
- Metered models may bill through different pools, for example direct Anthropic versus OpenRouter.
  Reconcile each provider against its own dashboard before treating a figure as owed.
- Responses missing a cost block are excluded from the estimate and reported as a count rather than
  counted as zero.

## See also

- `/token-dashboard` for cross-harness token telemetry across Claude Code, Pi, Codex, and OpenRouter,
  scoped to the current session and UTC week. It is deliberately token-only; this skill is the cost
  view and covers Pi alone.
- `/model-update-check` for auditing router and panel model IDs against the live catalog.
