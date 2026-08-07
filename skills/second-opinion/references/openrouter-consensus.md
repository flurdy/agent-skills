# OpenRouter panel subset safety

Read this file completely whenever a selected `quorum` or `consensus` panel contains OpenRouter
routes. The ordinary single-agent and local-only panel paths do not use this flow.

## Purpose and boundary

OpenRouter routes are an explicit, metered subset of a policy-neutral review panel. They are never
inferred from risk, an API key, `peer`, or a local-only panel. The same execution flow serves quorum
and consensus; the selected policy changes interpretation, not requests.

The official `@openrouter/cli` is not used. The hardened `scripts/openrouter-panel.sh` calls
OpenRouter's OpenAI-compatible chat-completions API without tools or repository access.

## Configuration

Panel configuration defaults to:

```text
~/.agents/second-opinion/config.json
```

It contains no credentials. The API key remains in the user's secret manager and is loaded on demand through `secret-api-key` when `SECRET_API_KEY_PROJECT` is configured.
Exact model IDs belong in local configuration, not the shared skill. See
[review-panels.md](review-panels.md) for the mixed-route schema.

The existing version-1 legacy `models` shape remains valid, but actively maintained profiles should
use `routes`. The optional root-level `modelPolicies` object sets exact user-local authorization only;
it never contains credentials or route availability:

```json
{
  "version": 1,
  "modelPolicies": {
    "openrouter/moonshotai/kimi-k3": {
      "metered": true,
      "consent": "allow"
    }
  },
  "profiles": {
    "extreme": {
      "enabled": true,
      "quorum": 2,
      "consensusQuorum": 4,
      "routes": [
        {
          "id": "qwen",
          "kind": "openrouter",
          "enabled": true,
          "model": "openrouter/qwen/<configured-model-id>",
          "vendor": "Qwen",
          "role": "independent reasoning"
        },
        {
          "id": "grok",
          "kind": "openrouter",
          "enabled": true,
          "model": "openrouter/x-ai/<configured-model-id>",
          "vendor": "xAI",
          "role": "adversarial critique"
        },
        {
          "id": "deepseek",
          "kind": "openrouter",
          "enabled": true,
          "model": "openrouter/deepseek/<configured-model-id>",
          "vendor": "DeepSeek",
          "role": "technical verification"
        },
        {
          "id": "kimi",
          "kind": "openrouter",
          "enabled": true,
          "model": "openrouter/moonshotai/kimi-k3",
          "vendor": "Moonshot AI",
          "role": "long-context review"
        }
      ],
      "limits": {
        "maxParallel": 4,
        "maxPromptBytes": 65536,
        "maxOutputTokensPerModel": 2000,
        "defaultTimeoutSeconds": 600
      }
    }
  }
}
```

A `consensusQuorum: 4` profile must retain at least four enabled unique providers. Disabled OpenRouter
routes make no request and are excluded from consent.

A panel may contain 1–8 unique model identities. Repeated provider namespaces count as separate
routes toward quorum but only once toward the consensus provider threshold. `vendor` is display-only;
the helper derives provider identity from canonical `openrouter/<provider>/<model-id>` values. Each policy must use the exact
canonical OpenRouter model ID, declare `metered: true`, and set `consent` to `ask` or `allow`.
`allow` does not apply to a provider, panel, renamed model, or unlisted model.

Local limits may lower but never exceed the compiled ceilings:

- 8 requests total;
- 4 concurrent requests;
- 65,536 combined sanitized-user-prompt and fixed completion-contract bytes;
- 2,000 output tokens per model;
- 1,048,576 response bytes per HTTP transport;
- 1,800 seconds per request.

The response-byte ceiling is a transport safety bound, not a token conversion or price estimate.

Models are never selected dynamically, substituted, or added during a run.

## Execution

Run these steps only after assembling one prompt for the ordinary second-opinion mode.

### 1. Sanitize and bound context

Remove credentials, `.env` content, private keys, tokens, and other sensitive data. The helper sends
the prompt bytes verbatim as the user message and adds only a fixed, non-secret system completion
contract. It cannot reliably identify arbitrary secrets. If context exceeds the profile cap, create a
focused summary before `check`; never silently truncate.

### 2. Resolve the full panel without network access

Write the exact sanitized prompt to a mode-`600` temporary file, then run:

```bash
~/.agents/skills/second-opinion/scripts/review-panel.sh check \
  --panel {panel_name} \
  --prompt-file {literal_prompt_file} \
  {route_overrides}
```

Retain `panelSha256`, `openrouterSha256`, and `promptSha256`. They bind the effective panel, exactly
the metered subset plus fixed completion-contract digest, and exactly the disclosed user prompt. The
result reports the fixed completion contract's byte count; it is included within `maxPromptBytes`.
The result also reports missing local
CLIs, curl, and OpenRouter authentication without making a request or exposing a credential.

Local routes may run before the consent decision. If OpenRouter prerequisites are missing, preserve
those routes as unavailable and continue with honest quorum degradation; do not install software,
request a pasted key, or inspect another tool's credential store.

### 3. Obtain fresh subset-only metered consent

If every selected route has a matching `consent: "allow"` policy, the coordinator reports configured
authorization and may execute that exact digest-bound subset without an interactive question. Otherwise,
immediately before requests, use one `AskUserQuestion`. Disclose:

- panel name and every OpenRouter route whose policy remains `ask`, with exact model ID, vendor,
  provider, and role;
- exact number of OpenRouter requests and configured maximum concurrency;
- prompt-byte cap, including the displayed fixed completion-contract bytes, output-token cap per
  model, and timeout;
- that only this subset consumes OpenRouter credits and prices can change.

Options:

1. **Run metered OpenRouter subset** — authorize only these disclosed requests.
2. **Keep local results only** — make no OpenRouter request.

A negative, abandoned, or ambiguous answer means no request. Interactive consent applies once and is
never stored or inferred. Configured authorization is exact-model, user-local, and digest-bound.
Declining does not discard successful local results.

### 4. Execute or decline once

After affirmative consent:

```bash
~/.agents/skills/second-opinion/scripts/review-panel.sh run-openrouter \
  --confirmed \
  --panel {panel_name} \
  --panel-sha256 {panelSha256} \
  --openrouter-sha256 {openrouterSha256} \
  --prompt-sha256 {promptSha256} \
  --prompt-file {literal_prompt_file} \
  {route_overrides}
```

When configured authorization applies, run `run-openrouter --configured-consent` with the same panel,
prompt, digests, and overrides. The coordinator rejects this flag unless every selected route remains
explicitly `allow`. On interactive approval, use `run-openrouter --confirmed`. On decline, run
`decline-openrouter` with the same panel, prompt, digests, and overrides. It emits one `declined`
result per OpenRouter route and calls no network endpoint.

The fixed system contract asks each OpenRouter route to end a completed answer with a marker. The
helper strips that marker from visible output. A route is `ok` only when it returns non-empty text,
uses normalized finish reason `stop`, contains no tool calls, and supplies the marker. Missing markers,
non-stop termination, and attempted tool calls become `incomplete`; their visible partial content and
bounded termination diagnostics remain available, but they cannot count toward quorum. Marker
compliance is transport completion only, not proof of correctness or substantive review.

`run-openrouter` rebuilds and verifies the effective panel and prompt before delegating the exact
subset to `openrouter-panel.sh`. The hardened helper keeps the bearer token out of argv using a
mode-private curl config, enforces the response-byte ceiling in curl and again before JSON parsing,
makes every configured request at most once, and preserves each error.
A changed panel, subset, prompt, or effective policy requires a new check and, when any route remains
`ask`, fresh interactive consent.

Always remove private prompt/result files after evaluation, success or failure.

## Presentation and interpretation

Preserve every route's status, role, vendor, derived provider, exact model, effective settings, and
provenance. OpenRouter results also preserve bounded response ID/model/provider, normalized and native
finish reasons, and tool-call count. Tool arguments and hidden reasoning text are discarded. Usage is
post-call telemetry, not a reliable pre-run estimate.

Quorum is mechanical: count routes with successful responses. Same-provider successes count as
separate configured reviews and are also reported as corroboration.

Consensus is semantic and only eligible after route quorum and the configured unique-provider
`consensusQuorum` threshold are both met. Report:

- claim-level evidence-backed agreements;
- disagreements and uncertainty;
- shared assumptions repeated without independent evidence;
- same-provider corroboration;
- unavailable, declined, failed, or timed-out routes.

A majority is not correctness. Finally verify every material finding against repository evidence and
list only actionable items.

## Safety invariants

- Never call OpenRouter without an explicitly selected panel containing those routes and either
  immediate subset-only consent or exact user-local configured authorization.
- Never persist interactive consent, retry a failed route, substitute a model, or expand a metered
  panel beyond its selected, digest-bound routes.
- Never print credentials or put the bearer token in argv.
- Never exceed compiled model, concurrency, prompt, output, or timeout ceilings.
- Never give OpenRouter models tools, repository access, environment contents, or unsanitized data.
- Never invoke disabled routes, count a disabled or `incomplete` response toward either threshold,
  or treat the completion marker as semantic review.

## Maintainer validation

```bash
skills/second-opinion/tests/test-review-panel.sh
skills/second-opinion/tests/test-openrouter-panel.sh
```

Both suites use fake CLIs/curl and must consume no network credits. Also run `make clean-code`.
