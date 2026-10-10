---
description: Report the Codex CLI account's weekly GPT quota, reset time, and credits
argument-hint: "[no arguments]"
---

Run exactly one read-only shell command, then answer from its JSON alone:

    codex-quota

If the command is not found, stop and report that the `codex-quota` helper from flurdy/ai-tools
(`pi/quota/README.md`) is not installed on PATH. Do not search for a checkout, run `codex`, query
any provider yourself, retry, sign in, switch models, or change settings, limits, or balances.

Render a short report with these lines, using the JSON values verbatim and never estimating from
the footer, a screenshot, or memory:

- GPT weekly: `weekly.usedPercent`% used, `weekly.remainingPercent`% remaining, or "unknown" when
  `weekly` is null (unknown is not zero).
- Reset: `weekly.resetsAtLocal` plus `weekly.untilReset.text` remaining, or "unknown" when null. If
  `weekly.resetPassed` is true, say the window is stale and the percentages are not current.
- Retrieved: `fetchedAtLocal`.
- Credits: the exact `credits.balance` string, "unlimited", or "unknown" when null. Do not round or
  convert credits into dollars, requests, or weekly allowance.
- Caveats: every entry in `caveats`, condensed to one line each.

When `status` is "error", report `error.kind`, `error.message`, and any `hint` as "quota
unavailable" and stop. End with one line noting that this prompt used a model turn, whereas running
`codex-quota` directly does not.
