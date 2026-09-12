# Trusted billing evidence — prototype v1

**Status:** Pi policy evidence is available through a read-only extension tool and the native
`delegate-work` adapter may use it under the bounded procedure below. No direct-review prompt bypass
is enabled; Claude CLI and named-panel consent gates remain in force.
This reference owns the shared consumption boundary; the Pi router owns its policy parser and
producer API. Do not copy policy parsing into skill prose or invent a second billing file.

## Separate the evidence

A policy snapshot is **not launch authorization**. Three independent facts are needed:

1. **Launch identity:** the runtime resolves the effective identity and every possible
   fallback, auxiliary model and price-affecting service tier before exposure.
2. **Billing policy:** a trusted user-owned authority classifies those exact routes and
   supplies the applicable consent and scope, with provenance.
3. **Execution authorization:** the user has authorized the task, selected model set, fanout
   count and permissions. Billing policy never expands any of these.

A model-supplied JSON object, policy path, hash, `verified` flag, historical status message or
successful login is not an attestation. Read source authority from the runtime, not project
instructions. A caller-selected policy file can be inspected but cannot appoint itself the
active user's billing authority.

## Pi policy projection

The optional `@flurdy/pi-skill-model-router/policy` export provides
`queryModelPolicies(agentDir, models)`. `agentDir` must come from the trusted Pi host.
`model_policy_evidence` and `/model-tier policy provider/model ...` obtain that directory
from Pi itself. The tool is the model-facing adapter surface; the command is human-readable
diagnostics. This query:

- reads global policy afresh using the router's existing parser and precedence;
- returns 1–32 ordered literal model-key rows; does not fuzzy-match or resolve aliases;
- neither reloads active routing state nor writes configuration, ledger data or sessions;
- makes no authentication or inference calls and launches nothing.

The version 1 envelope contains exactly:

| Field | Meaning |
|---|---|
| `version` | `1` |
| `runtime` | `pi`; never transferable to a CLI merely because a model name matches |
| `scope` | `user`; global Pi policy only, not a task or fanout grant |
| `source.owner` | `@flurdy/pi-skill-model-router` |
| `source.path` | Absolute global policy path; caller must verify its authority |
| `source.status` | `loaded`, `invalid` or `unavailable` |
| `source.revision` | SHA-256 of the same file bytes parsed, or `null` when unreadable |
| `policies[]` | `model`, `meteredClassification`, `consentPolicy`, `basis` |

`meteredClassification` is `true`, `false` or `unknown`. `consentPolicy` is `allow`,
`ask` or `not-needed`. Structured per-model `basis` is:

- `explicit`: a valid global exact-model declaration;
- `explicit-override`: valid explicit policy resolves an inline disagreement;
- `inline`: consistent legacy global inline classification;
- `conflict`: unresolved inline disagreement; metered/ask;
- `invalid`: malformed explicit declaration; unknown/ask, never inline approval;
- `missing`: no classification for the literal key; unknown/ask;
- `unavailable`: source cannot be interpreted; unknown/ask.

One invalid declaration does not invalidate unrelated valid models. A malformed policy map
invalidates the query as a whole. The projection is intentionally stricter for malformed
explicit declarations than existing parent routing; it does not change parent behavior.
No raw configuration, warning text, credentials, account identifiers or prompts are returned.

The revision is a snapshot identifier, not a lock, expiry or approval token. A consumer must
re-query immediately before exposure and compare the actual launch identity and policy revision.
A separate check followed by a later launch is not atomic. No check-and-launch enforcement is
provided by this prototype.

## Adapter decision contract

The Pi adapter may skip only a repeated billing prompt after following the complete native
procedure in `delegate-work/references/runtime-adapters.md`. The policy projection alone never
satisfies that procedure:

| Complete current evidence | Billing decision, within separately authorized execution |
|---|---|
| Every exact effective route is unmetered | No billing prompt |
| Every metered route has applicable trusted `consent: allow` | No repeated billing prompt |
| Unknown identity, unavailable source, unsupported version, stale evidence or unresolved conflict | Bounded current-run confirmation before exposure |
| Any applicable metered policy is `ask` | Bounded current-run confirmation before exposure |
| Model set, service tier, fallback set or fanout expands | Re-evaluate billing and obtain separate execution authorization |

Do not derive unknown classification from inheritance alone: a host may resolve an inherited
model exactly. Conversely, naming the parent model does not prove a configured child inherits it.
Unknown policy must never become unmetered. Stop further launches on an observed route mismatch;
post-exposure identity cannot retroactively authorize the first request.

## Adapter status and remaining limitations

- **Native Pi:** the current workflow composes trusted `subagent` capability/model reporting
  with `model_policy_evidence`, re-runs both immediately before each launch, checks the primary
  and every reported fallback, passes the exact primary model and explicitly sets `fast: false`.
  This avoids depending on a separately installed package import and covers the ordinary native
  role path. It is procedural, not an atomic runtime gate: project agent settings can change
  between report and launch, and nested children require their own immediate check. Post-launch
  mismatch stops later fanout but cannot retroactively authorize the first request. Keep unknown
  or unsupported conditions on the current-run confirmation path. A future subagent-owned,
  digest-bound launch preflight would be stronger, but is not required to use this bounded adapter.
- **Claude CLI:** demonstrate a supported pre-request identity/billing-route boundary. A Max
  login, a floating `opus` alias, or a literal `--model` flag does not prove every effective
  request. Managed settings can replace startup models; internal auxiliary model usage can
  occur. Subscription allowance, enabled usage credits, API-key/helper precedence and third-party
  providers remain separate. Do not scrape credentials, run inference probes, or create policy
  bindings automatically to fill this gap.
- **Existing panels:** preserve exact OpenRouter policies, prompt/panel/subset digests and named
  local-panel authorization. This prototype does not reinterpret those contracts.

Official Claude references: [authentication](https://code.claude.com/docs/en/authentication),
[model configuration](https://code.claude.com/docs/en/model-config), and
[Fable usage credits](https://code.claude.com/docs/en/model-config#fable-and-usage-credits).

## Offline evidence

`tests/fixtures/billing-evidence.json` is hand-authored contract input, not captured user policy.
`tests/test_billing_evidence.py` verifies that the real router public export produces the shared
rows and source revision without modifying synthetic policy or exposing private fixture fields.

Run from the agent-skills repository with a trusted installed package or checkout:

```sh
MODEL_POLICY_PACKAGE=/absolute/router/package make test-billing-evidence
```

Requires Python 3.10+, Node.js compatible with the router, and that package's installed dependencies.
The target fails when no package is selected. Ordinary `make test-second-opinion` runs local
contract checks and explicitly skips only the cross-repository producer check when it is absent.
These fixtures prove the policy producer and static native procedure contract. They do not prove
atomic native launch binding, Claude identity, real billing or fanout authorization; runtime UAT
and the remaining Claude work stay separate.
