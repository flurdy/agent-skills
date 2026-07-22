# Kimi K2.7 Code panel trial

**Date:** 2026-07-22

**Decision:** keep the current Kimi K2.6 panel slot unchanged; do not promote K2.7 Code from this trial.

## Scope

This trial compared the existing Kimi K2.6 long-context-review role with Kimi K2.7 Code. It used a private, temporary two-route panel and did not modify `~/.agents/second-opinion/config.json`.

The OpenRouter helper gave both routes only sanitized prompt text. It provided neither repository access nor tools, so tool use was intentionally not exercised.

## Method

| Scenario | Prompt size | Requests | Limits |
|---|---:|---:|---|
| Committed prompt-template code review | 7,159 bytes | one per model | 1,200 output tokens/model, 180 s, concurrency 2 |
| Second-opinion implementation and policy review | 39,428 bytes | one per model | 1,200 output tokens/model, 180 s, concurrency 2 |

The second scenario is a moderate long-context sample, not a 262,144-token-limit test. Both scenarios were authorized separately immediately before their requests.

## Results

| Scenario | K2.6 | K2.7 Code | Comparison |
|---|---|---|---|
| Code review | OpenRouter request failed; no usage or response | OpenRouter request failed; no usage or response | Inconclusive |
| Long-context review | OpenRouter request failed; no usage or response | OpenRouter request failed; no usage or response | Inconclusive |

The local preflight found curl available and OpenRouter authentication configured, but inference returned the helper's opaque `OpenRouter request failed` result for all four calls. This does not establish a provider, model, or prompt fault, and the helper retained no more specific failure detail.

## Capability and cost evidence

The 2026-07-22 public metadata check reported both models available, reasoning-capable, and tool-call-capable, with 262,144-token context and output limits. The current panel helper does not send tool definitions, so this does not demonstrate tool compatibility for the panel role.

| Metric | K2.6 | K2.7 Code | Change |
|---|---:|---:|---:|
| Public input list price | $0.684 / M tokens | $0.820 / M tokens | +19.9% |
| Public output list price | $3.420 / M tokens | $3.750 / M tokens | +9.6% |
| Public cache-read list price | $0.144 / M tokens | $0.160 / M tokens | +11.1% |
| Measured latency, usage, and cost | unavailable | unavailable | inconclusive |

Public list prices can change and do not substitute for run telemetry.

## Recommendation

Do not update the consensus panel slot. The candidate is more expensive at published list prices, offers no documented context-limit increase for this role, and produced no review evidence in the authorized trials. Keep the current configuration unchanged.

Before a future retest, diagnose the OpenRouter inference path in a separate, explicitly scoped investigation that preserves its credential and spend safeguards. Retest only after that path returns model responses; use multiple sanitized review prompts and record returned usage and latency before making a replacement decision.
