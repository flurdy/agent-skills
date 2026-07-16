# OpenRouter Consensus Panels

Read this file completely only when the user explicitly passes `--agent consensus`.
The ordinary `claude`, `codex`, `gemini`, and `all` routes do not use this flow.

## Purpose and boundary

Consensus is an exceptional, opt-in escalation for unusually high-stakes or hard-to-reverse
decisions. It adds a locally configured, cross-vendor OpenRouter panel. It is not a default,
an unattended loop, or proof by majority vote.

The official `@openrouter/cli` is not used: its v1 commands are SDK devtools and a Claude Code
statusline, not chat inference. The bundled `scripts/openrouter-panel.sh` calls OpenRouter's
OpenAI-compatible chat-completions API without giving models tools or repository access.

## Local configuration

The harness-neutral config defaults to:

```text
~/.agents/second-opinion/config.json
```

It contains no credentials. `OPENROUTER_API_KEY` remains a secret supplied by the user's shell or
secret manager. Exact model IDs belong in this local config, not in the shared skill.

```json
{
  "version": 1,
  "profiles": {
    "extreme": {
      "models": [
        {
          "model": "openrouter/<vendor>/<model-id>",
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

Profiles may contain **1-8 models**. Model IDs and case-insensitive vendor names must each be unique,
so multiple routes from one vendor cannot inflate apparent consensus. Every model identity must use
the canonical `openrouter/<model-id>` form; the helper strips the first `openrouter/` only when
building the API request.

Local profile limits may lower but never exceed the helper's compiled ceilings:

- 8 requests total
- 4 concurrent requests
- 65,536 prompt bytes
- 2,000 output tokens per model
- 600 seconds per request

Use `--panel <name>` to select a profile; the default is `extreme`. Do not choose models dynamically,
substitute failed models, expand a profile, or edit local configuration during a run. The configured
identities are what the user sees and approves.

## Execution

Do these steps only after parsing the ordinary second-opinion mode and assembling its prompt.

### 1. Sanitize and bound context

Remove credentials, `.env` content, private keys, tokens, and other sensitive data. The helper sends
prompt bytes verbatim and cannot reliably determine whether arbitrary source text is secret. This is
a mandatory human/agent review boundary, not a guarantee supplied by regex scanning.

If context exceeds the selected profile's prompt cap, make a focused summary before consent. Never
silently truncate a diff or plan.

### 2. Check configuration without a network request

For Claude Code's shared installation:

```bash
~/.claude/skills/second-opinion/scripts/openrouter-panel.sh check --profile {panel_name}
```

Use the equivalent installed skill path for the active harness (for example
`~/.codex/skills/second-opinion/...`). The check is local: it parses config, checks command/key
presence, and prints model identities and limits without contacting OpenRouter or exposing the key.
If `jq` itself is unavailable, it can report only a minimal JSON error because it cannot parse the
config.

If the result is not ready, report every listed problem. Do not install software, ask the user to
paste a key into chat, read Pi's auth store, or fall back to a metered request. Offer `--agent all`
or a configured single CLI instead.

### 3. Obtain fresh metered consent

Immediately before the API call, use one `AskUserQuestion`. Disclose:

- profile name and every configured model ID/vendor;
- exact number of requests and configured maximum concurrency;
- prompt byte cap, output-token cap per model, and timeout;
- that all requests consume OpenRouter credits and exact prices can change.

Options:

1. **Run metered panel** — recommended only when the requested decision warrants it.
2. **Keep subscription-only review** — make no OpenRouter request and offer `--agent all`.

A negative, abandoned, or ambiguous answer means no request. Consent is valid only for this one
panel run; never persist or infer it.

### 4. Write the prompt safely and run once

After affirmative consent:

1. Create a path with `mktemp` and set mode `600`.
2. Use the harness's `Write` tool to write the exact sanitized prompt to that literal path. Do not
   pass prompt content as a shell argument or leave the file empty.
3. Invoke the helper once, passing the literal path, selected profile, `--confirmed`, and the parsed
   timeout converted to seconds.
4. Remove the prompt file after success or failure.

```bash
prompt_file=$(mktemp)
chmod 600 "$prompt_file"
```

```text
Write tool: write the assembled sanitized prompt verbatim to the returned prompt_file path.
```

Run the helper and cleanup in one shell invocation so the prompt file is removed even when the
helper reports a model error:

```bash
status=0
~/.claude/skills/second-opinion/scripts/openrouter-panel.sh run \
  --confirmed \
  --profile {panel_name} \
  --prompt-file {literal_prompt_file_path} \
  --timeout {timeout_seconds} || status=$?
rm -f {literal_prompt_file_path}
exit "$status"
```

The helper rejects missing/empty prompts before any request. It batches configured models up to the
profile's concurrency limit and makes each request exactly once. A timeout, bad model, rate limit,
HTTP error, or malformed response becomes a model-specific error; never retry or substitute.

## Present results

Preserve every configured model's success/error status. Label output with role, vendor, and exact
model ID. Usage is post-call telemetry, not a reliable pre-run price estimate.

```markdown
## Extreme Consensus Panel: `{profile}`

| Role | Vendor | Model | Status | Result |
|---|---|---|---|---|
| {role} | {vendor} | `{model_id}` | ok / error | concise response or error |

### Agreements
- {claims independently supported by at least two successful vendors}

### Disagreements / uncertainty
- {conflicting claims, unsupported assumptions, failures, and missing perspectives}

*Source: OpenRouter chat-completions API; {count} explicitly approved metered requests; mode: {mode}.*
```

A point is not consensus merely because several models repeat the prompt's premise. Distinguish
independent evidence from shared assumptions. With fewer than two successful vendors, state that no
consensus was established.

Finally apply the main skill's repository-grounded assessment: verify each material finding against
actual code and list only genuinely actionable items. Agreement does not establish correctness.

## Safety invariants

- Never invoke this flow unless the user explicitly selected `--agent consensus`.
- Never call OpenRouter before the immediate consent step.
- Never persist consent or run consensus in an unattended loop.
- Never print credentials or put the bearer token in argv. The helper stores it in a mode-private
  temporary header file and removes it on exit.
- Never exceed the compiled model, concurrency, prompt, output, or timeout ceilings even if local
  config asks for more.
- Never send models tools, repository access, environment contents, or unsanitized sensitive data.
