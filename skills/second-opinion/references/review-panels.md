# Review panel configuration and execution

Review panels are policy-neutral route sets. `quorum` and `consensus` execute the same selected
panel; only interpretation differs. Quorum asks whether enough independent providers returned.
Consensus first requires quorum, then the caller compares claim-level evidence. Neither policy treats
route count or agreement as correctness.

## Configuration

The local, credential-free configuration remains:

```text
~/.agents/second-opinion/config.json
```

It stays at schema version 1. Each entry under `profiles` contains exactly one of:

- legacy `models`: the existing OpenRouter-only shape; or
- `routes`: the policy-neutral panel shape below.

A route profile requires `quorum`, measured in **unique successful providers**, and the existing
bounded `limits` object. Routes from the same provider may corroborate each other but count once
toward quorum.

```json
{
  "version": 1,
  "profiles": {
    "large": {
      "quorum": 4,
      "routes": [
        {
          "id": "claude-fable",
          "kind": "local",
          "agent": "claude",
          "model": "fable",
          "effort": "xhigh",
          "role": "architecture reasoning"
        },
        {
          "id": "codex",
          "kind": "local",
          "agent": "codex",
          "effort": "high",
          "role": "implementation critique"
        },
        {
          "id": "qwen",
          "kind": "openrouter",
          "model": "openrouter/qwen/<configured-model-id>",
          "vendor": "Qwen",
          "role": "independent reasoning"
        },
        {
          "id": "deepseek",
          "kind": "openrouter",
          "model": "openrouter/deepseek/<configured-model-id>",
          "vendor": "DeepSeek",
          "role": "technical verification"
        },
        {
          "id": "kimi",
          "kind": "openrouter",
          "model": "openrouter/moonshotai/<configured-model-id>",
          "vendor": "Moonshot AI",
          "role": "long-context review"
        },
        {
          "id": "grok",
          "kind": "openrouter",
          "model": "openrouter/x-ai/<configured-model-id>",
          "vendor": "xAI",
          "role": "adversarial critique"
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

Replace every `<configured-model-id>` locally with a current canonical OpenRouter identity. Exact IDs
stay out of the shared skill. `model` is optional for local routes and means the CLI-native default
when omitted. `effort` is optional and route-specific:

- Claude: `low`, `medium`, `high`, `xhigh`, `max`;
- Codex: `minimal`, `low`, `medium`, `high`, `xhigh`;
- Gemini and OpenRouter: unsupported and rejected.

The coordinator derives local providers (`anthropic`, `openai`, `google`) and the OpenRouter provider
namespace. Route IDs and model identities must be unique. Repeated provider namespaces are allowed
but cannot inflate quorum.

### Built-ins and compatibility

Panel availability:

- `focused`: local Claude + Codex, quorum 2; local config may override it;
- `local-legacy`: reserved built-in local Claude + Codex + Gemini, quorum 2; a same-named config
  entry is ignored so compatibility workflows remain guaranteed local-only.

The deprecated `--agent all` spelling maps to `--agent quorum --panel local-legacy`.

A legacy profile with `models` remains valid and normalizes to OpenRouter routes. Its quorum defaults
to `min(2, unique providers)`. The configured `extreme` profile is not changed or synthesized;
`--agent consensus` continues to default to it.

## Route overrides

Panel routes use unambiguous per-route overrides:

```text
--route-model claude-fable=opus
--route-effort claude-fable=max
--route-model codex=<native-model-id>
--route-effort codex=xhigh
```

Repeat flags as needed. Unknown route IDs, OpenRouter model overrides, unsupported effort values, and
Gemini/OpenRouter effort are rejected. Generic `--model` remains for a single direct agent only and
is invalid with `quorum` or `consensus`.

## Coordinator protocol

The skill invokes `scripts/review-panel.sh` in four bounded stages:

1. `check` normalizes the selected profile, applies overrides, checks route availability, and binds the
   canonical panel, OpenRouter subset, and exact prompt with SHA-256 digests.
2. `run-local` verifies the panel and prompt digests and executes only local routes. Every local route
   receives the same private prompt through stdin, runs at most once, and is read-only/sandboxed.
3. If OpenRouter routes exist and prerequisites are available, the skill discloses **only that subset**
   and asks for fresh metered consent. `run-openrouter --confirmed` verifies all three digests and
   delegates the exact subset once to `openrouter-panel.sh`. Declining uses `decline-openrouter` and
   makes no request.
4. `evaluate` preserves route order and failures, counts unique successful providers, and reports
   whether quorum was met. It reports same-provider corroboration separately and does no semantic
   consensus analysis.

Every result reports route ID, kind, provider, effective model and effort, their source (`panel`,
`override`, or `native-default`), status, and the bound panel and prompt digests. Local CLIs receive a
minimal environment containing native config locations but not arbitrary inherited secrets or API
keys. Their stdout (65,536 bytes) and stderr (8,192 bytes) are bounded while streaming; empty or
oversized output is a route error. Local routes are approved read-only repository reviewers and may
inspect readable repository files, so the repository itself remains a trust boundary and must not
contain shareable secrets. OpenRouter receives prompt bytes only and no tools. Missing CLIs, timeouts,
declined metered routes, and model errors remain explicit; routes are never retried or substituted.

For consensus, the caller may synthesize agreements only when `consensusEligible` is true. The
synthesis must separately report evidence-backed agreements, disagreements, shared assumptions,
same-provider corroboration, and unavailable routes. Material claims still require repository-grounded
verification.
