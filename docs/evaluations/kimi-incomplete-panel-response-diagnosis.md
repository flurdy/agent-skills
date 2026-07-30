# Incomplete Kimi panel response diagnosis

- Date: 2026-07-30
- Bead: `skills-vof`
- Status: **CONFIRMED** for the false-success classification; the upstream generation stop cause remains unresolved.

## Observed failure

The Pi watch-loop premium panel twice received only an inspection preamble from its configured Kimi route. The fresh captured response was 189 characters excluding its final newline:

> I'll first verify the plan's claims against the actual repository and installed Pi 0.82.1 documentation, then deliver the review.

The panel nevertheless recorded the route as successful provider coverage. The workspace evidence is in `agents/docs/architecture/reviews/pi-watch-loop-premium-2026-07-30/`.

## Failure boundary

`openrouter-panel.sh` accepted any string at `choices[0].message.content` as `status: "ok"`. It discarded the normalized finish reason, native finish reason, response/generation ID, response model/provider metadata, and tool-call fields. `review-panel.sh` then correctly counted every `status: "ok"` route toward unique-provider quorum. The first incorrect transition was therefore OpenRouter completion classification, not quorum arithmetic.

## Evidence

| ID | Observation | Source | Implication | Strength |
|---|---|---|---|---|
| E1 | The fresh artifact contains a heading and one future-action sentence, but no review. | Workspace `fresh-kimi.md`; 190 bytes including final newline | Confirms the incomplete output symptom. | Direct |
| E2 | The review record says the same route produced a preamble twice despite a fresh prompt explicitly requiring the completed review. | Workspace review `README.md` | Weakens a one-off malformed prompt explanation. | Reported |
| E3 | The recorded telemetry was 302 completion tokens, including 248 reasoning tokens, under the configured 2,000-token cap. | `skills-vof` evidence | Weakens output-cap exhaustion, but cannot establish the stop reason. | Reported |
| E4 | The request included only model, messages, output limit, and temperature; it supplied no tools. | `skills/second-opinion/scripts/openrouter-panel.sh` before the fix | Weakens intended tool use as request construction, but an attempted native tool-call termination could not be ruled out. | Direct |
| E5 | Any string content became `status: "ok"`; finish and tool metadata were ignored. | `openrouter-panel.sh` before the fix | Confirms the mechanism that admitted the preamble to quorum. | Direct |
| E6 | Quorum counts only unique providers whose route status is `ok`. | `skills/second-opinion/scripts/review-panel.sh` | Shows that conservative `incomplete` classification is sufficient to exclude the route without semantic voting. | Direct |
| E7 | OpenRouter documents a response ID and normalized finish reason on chat completions, while generation metadata can expose native finish reason and provider details. | [Chat completion](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion), [generation metadata](https://openrouter.ai/docs/api/api-reference/generations/get-request-&-usage-metadata-for-a-generation) | Identifies bounded diagnostics that must survive result normalization. | Direct documentation |

## Cause classification

| Candidate | Finding |
|---|---|
| Model behavior | **Unresolved contributor.** The route repeatedly emitted a preamble, but the discarded termination metadata prevents attribution to the model itself. |
| Request construction | **Not the false-quorum cause.** The fresh prompt required a completed response, no tools were supplied, and the configured token cap was not reportedly exhausted. Prompt handling may still influence model behavior. |
| Provider routing | **Unresolved contributor.** The configured namespace was Moonshot AI, but the prior result retained no response ID or native/provider termination metadata that could identify the routed endpoint and stop. |
| Completion classification | **Confirmed root cause.** Content existence was treated as completed independent coverage without a completion contract or termination validation. |

No metered reproduction was run during diagnosis. The historical result no longer contains a response/generation ID, so its native metadata cannot be recovered locally. A new paid call was unnecessary to prove the classification defect and would have required current exact-model authorization or fresh consent.

## Resolution policy

OpenRouter panel requests now add a fixed, non-secret system contract requiring a final completion marker. A route counts as `ok` only when it:

1. returns non-empty textual content;
2. ends with the completion marker;
3. has normalized finish reason `stop`; and
4. contains no tool calls.

The marker is stripped before presenting or persisting the visible response. Missing markers, non-stop termination, and tool-call attempts remain visible as `incomplete` results and cannot contribute provider quorum. This is a transport-completion policy, not a claim that the answer is correct, substantive, or semantically in consensus.

Results preserve bounded response ID, response model/provider, normalized and native finish reasons, and tool-call count. Tool arguments and hidden reasoning text are not persisted.
