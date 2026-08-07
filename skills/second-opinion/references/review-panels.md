# Review panel configuration and execution

Review panels are policy-neutral route sets. `quorum` and `consensus` execute the same enabled routes
from the selected panel exactly once; only interpretation differs. Quorum asks whether `quorum`
routes returned successfully. Consensus comparison additionally requires `consensusQuorum` unique
providers. Neither route count nor agreement establishes correctness.

## Configuration

The local, credential-free configuration remains:

```text
~/.agents/second-opinion/config.json
```

It stays at schema version 1. Each entry under `profiles` contains exactly one of:

- legacy `models`: the existing OpenRouter-only shape; or
- `routes`: the policy-neutral panel shape below.

A route profile requires `quorum`, measured in **successful routes**, and the existing bounded
`limits` object. Optional `consensusQuorum` is measured in **unique successful providers** and
defaults to the smaller of `quorum` and the enabled unique-provider count. Each threshold must fit
its own unit. Routes from the same provider count separately toward quorum but remain
same-provider corroboration for consensus interpretation.

Optional `enabled` defaults to `true` on profiles and routes. Selecting a disabled profile fails
without fallback. Disabled routes remain visible in check/evaluation output with status `disabled`,
but are never invoked and never count toward a threshold. The optional root-level `modelPolicies`
object remains exact OpenRouter spend authority; it is separate from profile/route availability and
does not accept `enabled`.

```json
{
  "version": 1,
  "modelPolicies": {
    "openrouter/moonshotai/<configured-model-id>": {
      "metered": true,
      "consent": "allow"
    }
  },
  "profiles": {
    "focused": {
      "enabled": true,
      "quorum": 2,
      "consensusQuorum": 2,
      "routes": [
        {
          "id": "claude",
          "kind": "local",
          "agent": "claude",
          "enabled": true,
          "role": "independent review"
        },
        {
          "id": "codex",
          "kind": "local",
          "agent": "codex",
          "enabled": true,
          "role": "independent review"
        }
      ],
      "limits": {
        "maxParallel": 2,
        "maxPromptBytes": 65536,
        "maxOutputTokensPerModel": 2000,
        "defaultTimeoutSeconds": 600
      }
    },
    "extreme": {
      "enabled": true,
      "quorum": 2,
      "consensusQuorum": 4,
      "routes": [
        {
          "id": "qwen",
          "kind": "openrouter",
          "model": "openrouter/qwen/<configured-model-id>",
          "vendor": "Qwen",
          "role": "independent reasoning"
        },
        {
          "id": "grok",
          "kind": "openrouter",
          "model": "openrouter/x-ai/<configured-model-id>",
          "vendor": "xAI",
          "role": "adversarial critique"
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

Replace every `<configured-model-id>` locally with a current canonical OpenRouter identity. Exact IDs
stay out of the shared skill. `model` is optional for local routes and means the CLI-native default
when omitted. `effort` is optional and route-specific:

- Claude: `low`, `medium`, `high`, `xhigh`, `max`;
- Codex: `minimal`, `low`, `medium`, `high`, `xhigh`;
- Gemini and OpenRouter: unsupported and rejected.

The coordinator derives local providers (`anthropic`, `openai`, `google`) and the OpenRouter provider
namespace. Route IDs and model identities must be unique. Repeated provider namespaces are allowed
but cannot inflate either threshold. `peer` remains a direct-route convenience selected from the
current session provider; panel configuration intentionally uses explicit `claude`, `codex`, or
`gemini` local routes.

### Configured OpenRouter consent

OpenRouter routes are metered by default and prompt before each run. To suppress that prompt for one
exact model, add a root-level policy to the user-local config:

```json
{
  "modelPolicies": {
    "openrouter/moonshotai/kimi-k3": {
      "metered": true,
      "consent": "allow"
    }
  }
}
```

`metered` must be `true`; `consent` is either `ask` (the default) or `allow`. Policies are matched by
full canonical model ID, not provider or panel name. An absent, invalid, or non-matching policy is
`ask`. A mixed subset prompts if any selected OpenRouter route is not `allow`. Effective policy and
basis (`configured` or `confirmation-required`) are included in the check and route results. Policy
values are included in the panel and OpenRouter subset digests. The OpenRouter subset digest also binds
the fixed completion contract, so a policy or contract change invalidates a prior check.

### Built-in panel

`focused` provides local Claude + Codex with route quorum and provider consensus threshold 2. Local
config may override it.

A legacy profile with `models` remains valid and normalizes to enabled OpenRouter routes. Its route
quorum defaults to `min(2, enabled routes)` and its provider consensus threshold defaults to the
smaller of quorum and enabled unique providers.
Modernize actively maintained profiles to `routes`; `--agent consensus` continues to default to the
configured `extreme` profile.

### Migrating a legacy profile

For each legacy `models` entry, add a stable `id`, set `kind: "openrouter"`, and move it unchanged
into `routes`. Add explicit `quorum` and, when consensus should be stricter, `consensusQuorum`.
Optional `enabled` switches belong on the profile or routes. Leave root `modelPolicies` unchanged:
they authorize exact OpenRouter spend and are not route-selection configuration. Run `check` against
the migrated profile before invoking any route; `legacy: false`, the intended thresholds, and the
expected enabled route/request counts prove the migration took effect.

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

1. `check` rejects a disabled profile, normalizes its routes and thresholds, applies overrides, checks
   enabled-route availability, and binds the canonical panel, OpenRouter subset, and exact prompt with
   SHA-256 digests.
2. `run-local` verifies the panel and prompt digests and executes only enabled local routes. Every
   enabled local route receives the same private prompt through stdin, runs at most once, and is
   read-only/sandboxed.
3. If OpenRouter routes exist and prerequisites are available, the skill discloses **only the routes
   whose exact policies remain `ask`** and asks for fresh metered consent. If every selected route is
   explicitly `allow`, it invokes `run-openrouter --configured-consent`; otherwise it invokes
   `run-openrouter --confirmed` only after approval. Both paths verify all three digests and delegate
   the exact subset once to `openrouter-panel.sh`. The OpenRouter helper adds a fixed completion
   contract, strips its marker from completed output, and classifies missing markers, non-stop
   termination, or tool-call attempts as `incomplete`. Declining uses `decline-openrouter` and makes
   no request.
4. `evaluate` preserves route order, disabled evidence, and failures; counts successful routes and
   unique successful providers; and reports route-based `quorumMet` plus provider-based
   `consensusEligible` against their configured thresholds. It reports same-provider corroboration
   separately and does no semantic consensus analysis.

Every result reports route ID, kind, provider, effective model and effort, their source (`panel`,
`override`, or `native-default`), effective OpenRouter consent policy/basis when applicable, status,
and the bound panel and prompt digests. OpenRouter results also retain bounded response ID/model/provider,
normalized and native finish reasons, usage, and tool-call count while discarding tool arguments and
hidden reasoning text. An `incomplete` route remains visible but cannot count toward quorum; completion
marker compliance is not semantic validation. Local CLIs receive a
minimal environment containing native config locations but not arbitrary inherited secrets or API
keys. Their stdout (65,536 bytes) and stderr (8,192 bytes) are bounded while streaming; empty or
oversized output is a route error. Local routes are approved read-only repository reviewers and may
inspect readable repository files, so the repository itself remains a trust boundary and must not
contain shareable secrets. OpenRouter receives the sanitized user prompt plus the bounded fixed
completion contract and no tools. Their combined bytes stay within `maxPromptBytes`. Missing CLIs,
timeouts, incomplete responses, declined metered routes, and model errors remain explicit; routes are
never retried or substituted.

For consensus, the caller may synthesize agreements only when route quorum is met, the successful
unique-provider count meets `consensusQuorum`, and `consensusEligible` is true. Falling short can
still meet ordinary quorum; in that case preserve the individual opinions but make no consensus
assessment. The synthesis must
separately report evidence-backed agreements, disagreements, shared assumptions, same-provider
corroboration, and unavailable or disabled routes. Material claims still require repository-grounded
verification.
