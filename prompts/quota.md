---
description: Report Codex and Claude usage windows plus OpenRouter account credits
argument-hint: "[no arguments]"
---

Run exactly these three read-only shell commands, as separate commands, then answer from their JSON
alone:

    codex-quota
    claude-quota
    openrouter-quota

Each provider is independent: one provider's failure never hides or skips the other reports. A
non-zero exit with JSON on stdout is that provider's reported error. If a command is not found,
report for that provider only that its helper from flurdy/ai-tools (`pi/quota/README.md`) is not
installed on PATH. Do not search for a checkout, run `codex` or `claude`, query any provider
yourself, retry, sign in, switch models, look up credentials, change account/project configuration,
or change settings, limits, or balances.

Use only the JSON values, with the display formatting below; never estimate from the footer,
a screenshot, or memory. Null means unknown, never zero. Round only for display; the helpers
retain exact values. Never recompute the remaining balance. Do not show retrieval dates or times
unless requested: a fresh query's timestamp adds no useful information to the routine report.
Keep it compact: figures, resets and errors only. Do not print a caveats section or a model-turn
reminder; standing notes belong in the prompt README. Keep stale and unknown indicators inline
with the affected value.

**Codex** (`codex-quota`):

Render a one-row table with columns Window, Used, Reset, and Time until reset.
Use "GPT weekly" for the window; put credits below the table.

- GPT weekly: `weekly.usedPercent`% used, or "unknown" when `weekly` is null.
- Reset: `weekly.resetsAtLocal` plus `weekly.untilReset.text` remaining, or "unknown" when null. If
  `weekly.resetPassed` is true, say the window is stale and its percentage is not current.
- Credits: format `credits.balance` with thousands separators and at most two decimal places;
  trim trailing zeros (for example, `1000.0000000000` → **1,000**, `126.4375` → **126.44**).
  Preserve "unlimited" and "unknown" when null. These are not dollars, requests, or weekly allowance.

**Claude** (`claude-quota`):

Render a table with columns Window, Used, Reset, and Time until reset.

- One row per entry in `windows`, in order: `label`, then `usedPercent`% used or "unknown" when
  null, then the reset: `resetsAtLocal` plus `untilReset.text` remaining; otherwise `resetsAtText`
  with `resetsTimeZone`; otherwise "unknown". If `resetPassed` is true, say the window is stale and
  its percentage is not current. When `windows` is empty, say Claude usage is unknown.

**OpenRouter** (`openrouter-quota`):

Render a one-row table with columns Remaining, Purchased, Used, headed **OpenRouter (USD)**.
This is an account balance, not a subscription window:

- Remaining: `credits.derived.remainingCredits`; Purchased: `credits.reported.totalCredits`;
  Used: `credits.reported.totalUsage`. Do not recalculate any field.
- Format all three as USD with `$`, thousands separators and exactly two decimal places,
  rounding decimal half away from zero. For example, `73.148107563` → **$73.15**,
  `115` → **$115.00**, `41.851892437` → **$41.85**.
- Preserve zero and negative balances (for example, `0` → **$0.00**, `-12.345` → **-$12.35**);
  never clamp a negative to zero. Missing/null values are "unknown", not zero.
- Keep derived/reported provenance in the helper JSON and docs, not repeated in the routine table.
- Do not invent resets, percentages, requests or token conversions.

For any provider, when `status` is "error", report `error.kind`, `error.message`, and any `hint`
as "Codex quota unavailable", "Claude quota unavailable", or "OpenRouter credits unavailable",
then continue with the other providers.
