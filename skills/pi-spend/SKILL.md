---
name: pi-spend
description: Read-only estimate of Pi model cost by provider and model for today, this week, this month, and all recorded history, separating metered credit usage from flat-rate subscription usage.
allowed-tools: "Bash(~/.agents/skills/pi-spend/scripts/pi_spend.py:*)"
model-tier: economy
model: haiku
effort: medium
version: "1.1.0"
author: "flurdy"
---

# Pi Spend

Answer "what have my metered models cost me lately" from Pi's own session telemetry. Periods are
today, the current week (Monday start), the current calendar month, and all recorded history, all in
the machine's local timezone.

## Usage

```text
/pi-spend                       # all four periods, every provider and model
/pi-spend --metered-only        # show only responses classified as metered
/pi-spend --period today        # single period; repeatable
/pi-spend --json                # normalized schema v2 JSON
/pi-spend --billing-policy PATH # use another effective-dated local policy
/pi-spend --router-config PATH   # explicit legacy current-policy projection
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
- call out the `unknown` billing class when present, since it means no valid interval covers that
  exact provider/model response rather than that the model is free;
- call out `legacy-current-router-policy` as a current-policy projection that may relabel history; and
- mention responses that recorded no cost only when the collector reports some.

Never describe the output as an invoice, an account balance, or remaining credits.

## Sources and authority

- Pi sessions: `~/.pi/agent/sessions/**/*.jsonl`. Assistant messages carry `provider`, `model`,
  `usage`, and a per-response `usage.cost` breakdown. Responses are deduplicated by `responseId`, so
  nested subagent run transcripts are counted once.
- Billing class: `~/.pi/agent/pi-spend-billing-policy.json`, using exact provider/model entries and
  the interval covering each response timestamp. Missing or invalid coverage reports as `unknown`;
  the collector does not guess from provider or model names.

Pi is the only local harness that records cost. Claude Code transcripts contain no cost field and
Codex rollouts record cumulative token counts only, which is why this skill is Pi-scoped.

## Billing policy

The local policy uses schema version 1. `effectiveUntil` is exclusive; `null` leaves the interval
open. Timestamps must be timezone-aware UTC (`Z` or `+00:00`). Intervals for one exact model may be
contiguous but must not overlap.

```json
{
  "schemaVersion": 1,
  "models": {
    "provider/model-id": [
      {
        "effectiveFrom": "2026-01-01T00:00:00Z",
        "effectiveUntil": "2026-07-01T00:00:00Z",
        "billing": "metered"
      },
      {
        "effectiveFrom": "2026-07-01T00:00:00Z",
        "effectiveUntil": null,
        "billing": "subscription"
      }
    ]
  }
}
```

Add a new interval when billing changes; do not rewrite the earlier interval. Renamed models get a
separate exact key. There are no aliases or automatic historical backfills. Back up this unshared
file with the retained Pi sessions it classifies.

Missing files, malformed policy JSON, duplicate keys, non-UTC timestamps, invalid ranges, overlaps,
and uncovered response dates fail closed to `unknown` with bounded diagnostics. An invalid model
entry does not disable valid, non-overlapping entries for other models.

`--router-config PATH` preserves the old `modelPolicies[*].metered` interpretation only when invoked
explicitly. Its rows and report metadata are labelled `legacy-current-router-policy` because current
router policy is projected across all history and can relabel older responses. Bare model-name
fallback is not supported.

## JSON schema

Schema v2 adds top-level `billingPolicy` source/status/diagnostics, classification counters under
`stats`, and `billingSource` on each row. A single provider/model may produce multiple rows in one
period when its billing interval changes. `costAuthority` remains `pi-catalog-estimate`.

## Limitations

- Cost is Pi's own catalog list-price calculation at response time, not a provider invoice,
  subscription allowance, or credit balance. Treat it as an estimate for relative comparison.
- Subscription-billed providers still get a computed cost. That figure is notional and is not
  charged; keep it out of any metered total.
- Coverage is bounded by retained session files. History starts at the oldest surviving transcript,
  so `all` may be shorter than it appears and older periods are not recoverable.
- The unshared billing policy is trusted local configuration, not a tamper-proof history. Explicitly
  rewriting an old interval can still change reports.
- Metered models may bill through different pools, for example direct Anthropic versus OpenRouter.
  Reconcile each provider against its own dashboard before treating a figure as owed.
- Responses missing a cost block are excluded from the estimate and reported as a count rather than
  counted as zero. Undated and future-dated responses are also excluded and counted separately.

## See also

- `/token-dashboard` for cross-harness token telemetry across Claude Code, Pi, Codex, and OpenRouter,
  scoped to the current session and UTC week. It is deliberately token-only; this skill is the cost
  view and covers Pi alone.
- `/model-update-check` for auditing router and panel model IDs against the live catalog.
