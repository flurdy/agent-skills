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

It contains no credentials. `OPENROUTER_API_KEY` remains in the user's shell or secret manager.
Exact model IDs belong in local configuration, not the shared skill. See
[review-panels.md](review-panels.md) for the mixed-route schema.

The existing version-1 legacy shape remains valid:

```json
{
  "version": 1,
  "profiles": {
    "extreme": {
      "models": [
        {
          "model": "openrouter/<provider>/<model-id>",
          "vendor": "Vendor name",
          "role": "independent reasoning"
        }
      ],
      "limits": {
        "maxParallel": 4,
        "maxPromptBytes": 65536,
        "maxOutputTokensPerModel": 2000,
        "defaultTimeoutSeconds": 180
      }
    }
  }
}
```

A panel may contain 1–8 unique model identities. Repeated provider namespaces are allowed for
corroboration but count once toward quorum. `vendor` is display-only; the helper derives provider
identity from canonical `openrouter/<provider>/<model-id>` values.

Local limits may lower but never exceed the compiled ceilings:

- 8 requests total;
- 4 concurrent requests;
- 65,536 prompt bytes;
- 2,000 output tokens per model;
- 1,048,576 response bytes per HTTP transport;
- 600 seconds per request.

The response-byte ceiling is a transport safety bound, not a token conversion or price estimate.

Models are never selected dynamically, substituted, or added during a run.

## Execution

Run these steps only after assembling one prompt for the ordinary second-opinion mode.

### 1. Sanitize and bound context

Remove credentials, `.env` content, private keys, tokens, and other sensitive data. The helper sends
prompt bytes verbatim and cannot reliably identify arbitrary secrets. If context exceeds the profile
cap, create a focused summary before `check`; never silently truncate.

### 2. Resolve the full panel without network access

Write the exact sanitized prompt to a mode-`600` temporary file, then run:

```bash
~/.agents/skills/second-opinion/scripts/review-panel.sh check \
  --panel {panel_name} \
  --prompt-file {literal_prompt_file} \
  {route_overrides}
```

Retain `panelSha256`, `openrouterSha256`, and `promptSha256`. They bind the effective panel, exactly
the metered subset, and exactly the disclosed prompt. The result reports missing local CLIs, curl,
and OpenRouter authentication without making a request or exposing a credential.

Local routes may run before the consent decision. If OpenRouter prerequisites are missing, preserve
those routes as unavailable and continue with honest quorum degradation; do not install software,
request a pasted key, or inspect another tool's credential store.

### 3. Obtain fresh subset-only metered consent

Immediately before requests, use one `AskUserQuestion`. Disclose:

- panel name and every OpenRouter route's exact model ID, vendor, provider, and role;
- exact number of OpenRouter requests and configured maximum concurrency;
- prompt-byte cap, output-token cap per model, and timeout;
- that only this subset consumes OpenRouter credits and prices can change.

Options:

1. **Run metered OpenRouter subset** — authorize only these disclosed requests.
2. **Keep local results only** — make no OpenRouter request.

A negative, abandoned, or ambiguous answer means no request. Consent applies once and is never
stored or inferred. Declining does not discard successful local results.

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

On decline, run `decline-openrouter` with the same panel, prompt, digests, and overrides. It emits one
`declined` result per OpenRouter route and calls no network endpoint.

`run-openrouter` rebuilds and verifies the effective panel and prompt before delegating the exact
subset to `openrouter-panel.sh`. The hardened helper keeps the bearer token out of argv using a
mode-private curl config, enforces the response-byte ceiling in curl and again before JSON parsing,
makes every configured request at most once, and preserves each error.
A changed panel, subset, or prompt requires a new check and fresh consent.

Always remove private prompt/result files after evaluation, success or failure.

## Presentation and interpretation

Preserve every route's status, role, vendor, derived provider, exact model, effective settings, and
provenance. Usage is post-call telemetry, not a reliable pre-run estimate.

Quorum is mechanical: count unique providers with successful responses. Same-provider successes are
reported separately and cannot inflate quorum.

Consensus is semantic and only eligible after quorum. Report:

- claim-level evidence-backed agreements;
- disagreements and uncertainty;
- shared assumptions repeated without independent evidence;
- same-provider corroboration;
- unavailable, declined, failed, or timed-out routes.

A majority is not correctness. Finally verify every material finding against repository evidence and
list only actionable items.

## Safety invariants

- Never call OpenRouter without an explicitly selected panel containing those routes and immediate
  subset-only consent.
- Never persist consent, retry a failed route, substitute a model, or run a metered panel unattended.
- Never print credentials or put the bearer token in argv.
- Never exceed compiled model, concurrency, prompt, output, or timeout ceilings.
- Never give OpenRouter models tools, repository access, environment contents, or unsanitized data.

## Maintainer validation

```bash
skills/second-opinion/tests/test-review-panel.sh
skills/second-opinion/tests/test-openrouter-panel.sh
```

Both suites use fake CLIs/curl and must consume no network credits. Also run `make clean-code`.
