---
description: Report Codex weekly GPT quota and credits, and Claude Code session and weekly usage
argument-hint: "[no arguments]"
---

Run exactly these two read-only shell commands, as separate commands, then answer from their JSON
alone:

    codex-quota
    claude-quota

Each provider is independent: one provider's failure never hides or skips the other's report. A
non-zero exit with JSON on stdout is that provider's reported error. If a command is not found,
report for that provider only that its helper from flurdy/ai-tools (`pi/quota/README.md`) is not
installed on PATH. Do not search for a checkout, run `codex` or `claude`, query any provider
yourself, retry, sign in, switch models, or change settings, limits, or balances.

Use the JSON values verbatim and never estimate from the footer, a screenshot, or memory. Null
means unknown, never zero.

**Codex** (`codex-quota`):

- GPT weekly: `weekly.usedPercent`% used, `weekly.remainingPercent`% remaining, or "unknown" when
  `weekly` is null.
- Reset: `weekly.resetsAtLocal` plus `weekly.untilReset.text` remaining, or "unknown" when null. If
  `weekly.resetPassed` is true, say the window is stale and the percentages are not current.
- Retrieved: `fetchedAtLocal`.
- Credits: the exact `credits.balance` string, "unlimited", or "unknown" when null. Do not round or
  convert credits into dollars, requests, or weekly allowance.
- Caveats: every entry in `caveats`, condensed to one line each.

**Claude** (`claude-quota`):

- One line per entry in `windows`, in order: `label`, then `usedPercent`% used or "unknown" when
  null, then the reset: `resetsAtLocal` plus `untilReset.text` remaining; otherwise `resetsAtText`
  with `resetsTimeZone`; otherwise "unknown". If `resetPassed` is true, say the window is stale and
  its percentage is not current. When `windows` is empty, say Claude usage is unknown.
- Retrieved: `fetchedAtLocal`.
- Caveats: every entry in `caveats`, condensed to one line each.

For either provider, when `status` is "error", report `error.kind`, `error.message`, and any `hint`
as "Codex quota unavailable" or "Claude quota unavailable", then continue with the other provider.
End with one line noting that this prompt used a model turn, whereas running `codex-quota` or
`claude-quota` directly does not.
