# Reviewed migration evidence and advisory preview

This is the audit's bounded input/output contract, not a configuration applier. Evidence files
are local working input: use ignored `.artifacts/` only when authorized, do not commit machine-local
pins or raw audit output. No evidence file or emitted preview grants execution, consent or file authority.

## Input: `--evidence FILE` or `--evidence -`

For normal conversation, the agent researches the selected upgrade after **Review and preview**
and submits reviewed JSON on stdin (`--evidence -`). The user need not author JSON or a file.
The helper reads at most 64 KiB into private disposable scratch and then follows the exact same
validator, snapshot and digest path as file input. Output source `path` is `stdin`; the payload
digest is retained. Oversized input is rejected before native collection/refresh. No user config
or caller-selected evidence file is written. A preview still requires separate application approval.

UTF-8 JSON, maximum 64 KiB, strict duplicate-key/constant handling. Top-level keys are exactly
`schemaVersion: 1` and `recommendations` (0–32 entries). Each recommendation contains:

| Key | Contract |
|---|---|
| `from`, `to` | Distinct exact identities on the same runtime route; never fuzzy matched |
| `checkedAt` | UTC timestamp, no more than seven days old and not in the future |
| `citations` | 1–4 `{url, quote}` records; HTTPS without credentials, default/443 port; quote ≤2,000 characters |
| `compatibility` | Non-empty ≤2,000-character assessment for each of `role`, `stability`, `reasoning`, `modalities`, `limits`, `pricing`, `billingRoute` |
| `nativeAvailability` | Optional ≤2,000-character reviewed exact CLI-resolution evidence; required for local CLI proposals |
| `routerPolicy` | Optional `{metered: boolean, consent: "ask" or "allow", evidence: string}`; explicit proposed policy, never inherited from `from` |
| `billing` | Optional `{billing: "metered" or "subscription", effectiveFrom: UTC timestamp, evidence: string}`; exact-model interval evidence, not launch consent |

Unknown keys, wrong types, stale/future evidence, cross-route pairs and duplicates are rejected.
Missing configuration/catalog data still blocks the affected preview; citations do not override a
negative exact-route Pi/OpenRouter availability result. Local CLI availability stays a reviewed
claim, not an inference from public catalog presence. A malformed evidence file never erases the
remaining read-only audit.

Identities are:

- Pi/router and OpenRouter: the configured `provider/model-id` string, including `~` where present;
- local reviews/allowlists: `local/claude/<pin>`, `local/codex/<pin>`, `local/gemini/<pin>`.

These are distinct routes even when the final model names happen to match. To migrate a router
candidate **and** a local CLI pin, supply separate reviewed pairs in the same file. Native defaults
and aliases are preserved, not materialized into pins. A `model-latest` CLI alias remains native.
OpenRouter catalog aliases remain exact provider identifiers and are audited on that route.

The collector does **not** fetch or authenticate arbitrary citation URLs. The invoking agent/user
must have reviewed authoritative public sources and verified that each quote actually supports the
claimed relationship and role. All preview records retain
`evidenceTrust: "reviewed-input-not-independently-verified"`. A release announcement establishes
existence, not subscription availability, comparative quality or consent.

Billing evidence specifies the intended start; the helper never chooses a historical date from a
model release or invents a subscription classification. A proposed start before the audit time is
unresolved rather than a historical backfill, even when the input claims billing evidence. Appending an interval reuses
`pi-spend/scripts/pi_spend.py::parse_billing_policy` to reject invalid/overlapping ranges. Existing
keys/intervals are preserved, including prior billing for the target. An identical interval is not
proposed twice. Invalid/missing policy requires separate repair rather than automatic initialization.

## Output: audit schema version 2

Existing source-health, configured-model, recent-list and finding fields remain. Additional fields:

- `interaction` (version 1): read-only primary conversation action and exact-location opportunities.
  Fixed priority: invalid core config → review supplied preview → review discovered candidate →
  investigate unavailable catalogs → none. Billing housekeeping never authorizes or displaces review.
  Action kinds are `inspect-config`, `review-upgrade`, `review-preview`, `inspect-availability`, `none`;
  no `apply` or `update` action exists. `requiresReply` and `doesNotAuthorize` preserve the boundary
  between review/preview and application, refresh, billing, allowlists or inference.
- `configurationInventory`: every model-bearing JSON pointer and configured role, retaining
  disabled rows, weights/selection, aliases/defaults, exact global router policy projection and
  current spend coverage. `sourceSha256` binds the private input snapshot to its original target path.
  `spendCoverage.reason` distinguishes missing/invalid policy, absent/invalid model rule and date gaps;
  `explanation` is plain reporting language. The owner's classification always wins: raw policy is
  used only to explain unknown coverage, never to promote it to subscription or metered. Valid entries
  in a partially invalid policy remain covered; exact start/end behavior remains owner-defined.
- `catalogCandidates`: complete discovery from each relevant provider/namespace, not a top-eight
  cutoff. Status is always `discovered-not-successor`. `crossRouteDiscoveryOnly` can suggest a
  research lead, never equivalent identity or runtime access. Keep data source distinctions intact.
- `discoveryLeads`: same-family discovery only when valid dates for both models establish a strictly
  later candidate at their shared precision. These are research leads, not successor/compatibility
  proof; OpenRouter listing timestamps in particular do not establish actual model release order.
  Unreviewed leads make the verdict incomplete, never an automatic upgrade. A retained old
  subscription allowlist entry is not a lead when the candidate is already allowed for that same
  agent; an old explicit profile pin remains a separate actionable lead.
- `discoveryUncertainties`: unreviewed same-family pairs with missing, invalid or overlapping coarse
  dates. They keep the verdict incomplete without creating `review-upgrade` opportunities. Equal
  full dates and demonstrably older candidates are not upgrade leads. Complete catalogs remain
  available under `catalogCandidates`; no dates or source-health uncertainty are invented or hidden.
  An explicitly reviewed pair is handled by `recommendations`, not this discovery-only uncertainty.
- `migrationAssessments`: all affected config paths/roles for each current identity. No proposal
  evidence means a compatibility review, not a name/date-based automatic recommendation.
- `recommendations`: reviewed pairs, candidate availability, optional-upgrade versus incomplete,
  exact `changes`, and `unresolved` prerequisites.
- `changes`: source/config path, source digest, JSON pointer, `operation`, `before`, `after`,
  `consentSensitive`, and `authorization: "separate-current-run-required"`. These are advisory
  before/after records, **not executable JSON Patch**. Applying several selected proposals requires
  composing and revalidating their joint final diff; overlapping parent paths are not independent patches.
- `handoff`: `previewOnly: true`, `companionAvailable: true` and a companion path. This is
  availability of a **separately attended** tool, not permission to apply; see
  [companion-apply.md](companion-apply.md) for the exact authority and backup contract.
- `refresh`: command, disclosure, status, attempted, nativeCompleted and fresh. `fresh` requires
  native success **and** successful subsequent enumeration; it is not a per-model launch guarantee.

Subscription allowlists add a proposed pin while retaining existing entries, with explicit
`consentSensitive: true`. No approval is copied from the old model. Existing candidate policies are
not silently overwritten. OpenRouter panel policy decisions remain separately visible unresolved
work unless already configured. Unrelated config fields, panel quorum/provider diversity and model
weights/order are never part of the generated edits.

The implemented companion independently validates its input and source digests, composes a selected
pointer-level diff, requires exact interactive approval plus each file's authority, and retains private
recovery data without promising cross-file atomicity. This audit implements none of those writes.

## Native refresh evidence (Pi 0.87.1)

Reviewed installed documentation: `docs/models.md` and `docs/cli.md` distinguish models-only refresh
from Pi/package updates. Reviewed implementation:

- `dist/package-manager-cli.js::refreshModelCatalogs`: `ModelRuntime.create` with native auth/model
  paths, then `refresh({allowNetwork: true, force: true})`; native errors/timeouts are failures.
- `dist/core/model-runtime.js::create`: loads `models.json` and uses `models-store.json` for persisted
  model data; refresh also updates native availability/auth checks.
- `dist/core/remote-catalog-provider.js`: publishes persistent metadata on success and some failed
  responses. Failure cannot promise no side effects or an unchanged cache.
- `dist/core/auth-storage.js`: native AuthStorage can create a missing auth file and can execute
  configured credential resolution. The passive collector checks only file existence, uses offline
  enumeration with extensions/project execution disabled, suppresses native diagnostics, and never
  opens credentials itself. Do not claim a universal side-effect guarantee for arbitrary native
  provider/auth configuration or future Pi versions; recheck or report incomplete when uncertain.

Tests prove the wrapper contract with synthetic native commands. A live refresh was not performed
for implementation acceptance; it still requires current-run authorization and reviewed native effects.
