# Telemetry sources and authority

The dashboard reports observed token telemetry. It does not turn local files into subscription quota or billing data.

| Source | Evidence and fields | Retention / period | Authentication and limitations |
|---|---|---|---|
| Claude Code | [Agent SDK cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking) documents per-message usage, repeated message IDs, and different parent/subagent aggregation scopes. The local `~/.claude/projects/**/*.jsonl` schema is not a stable public contract, so the collector accepts only top-level assistant usage and deduplicates progressive snapshots by message ID. | Local transcripts persist until Claude Code or the user removes them. A calendar-week sum can be incomplete after deletion, cleanup, ephemeral use, or work on another machine. | Local filesystem only. Personal subscription allowance has no supported local transcript API; see [Claude Code costs](https://code.claude.com/docs/en/costs). |
| Pi | [Pi session format](https://github.com/earendil-works/pi-mono/blob/main/packages/coding-agent/docs/session-format.md) defines `~/.pi/agent/sessions`, assistant `usage`, provider/model fields, tree entries, and fork metadata. | Local sessions persist until removed. `--no-session`, deleted files, and other machines are not represented. | Local filesystem only. Pi is multi-provider and exposes no universal provider allowance API. |
| OpenAI Codex | Codex rollout files contain protocol `token_count` events with cumulative and last-turn usage; the upstream [protocol types](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs) are the implementation source. The collector converts monotonic cumulative snapshots to deltas and suppresses repeated snapshots. | Local rollout files persist until removed. Deleted/ephemeral/remote activity is absent. Week attribution uses event timestamps and pre-boundary cumulative snapshots where available. | Local filesystem only. Rollout telemetry is not OpenAI organization billing or ChatGPT subscription allowance. |
| OpenRouter | [Analytics metadata](https://openrouter.ai/docs/api/api-reference/betaanalytics/get-available-analytics-metrics-and-dimensions) supplies live metric/dimension names. [Analytics query](https://openrouter.ai/docs/api/api-reference/betaanalytics/query-analytics-data) accepts an explicit UTC time range and returns truncation metadata. | Volume/cost analytics can support up to 365 days; provider and other generation dimensions are limited to 31 days. The dashboard's current UTC week is within that limit. | Requires a separate [Management API key](https://openrouter.ai/docs/guides/overview/auth/management-api-keys). A normal inference key is never sent. Analytics describes API activity, not a weekly subscription allowance. |

## Period semantics

Version 1 uses a half-open UTC calendar week beginning Monday 00:00. The report is week-to-date at generation time and also exposes the next Monday as `boundaryEnd`. Vendor rolling allowance windows are different and are not reconstructed from calendar totals.

## Exactness labels

- `exact` means the displayed counters were parsed exactly from the named local/API source.
- `partial` means malformed, unreadable, timestamp-less, conflicting, skipped, or API-truncated records can affect the aggregate.
- `estimated` applies to current-session selection when no active runtime session identifier is available.
- Exact local telemetry still is not authoritative account billing or allowance data.

## Prior-art decision

[`ccusage`](https://github.com/ryoppippi/ccusage) was reviewed because it supports several local coding-agent formats and contains useful replay/deduplication precedent. This skill keeps a small repository-owned stdlib collector instead of requiring an additional Node package: the command must work when `ccusage` is absent, expose this normalized nullable schema, include Pi child-run/current-session behavior, and integrate OpenRouter management analytics. The parsers remain tolerant and fixture-backed because their runtime-owned formats can change.
