# Release evidence contract

`ready-to-release/scripts/release-gates` is the sole read-only collection, normalization, and
readiness policy authority. Python 3.10+ standard library; no provider SDK or YAML dependency.
Consumers render its JSON and never implement their own gates.

## Collection

Run from a verified project root, or supply `--project-root <path>`. No ancestor-root guessing.
The helper invokes only these project adapters, with the full project in scope:

| Adapter | Contract |
|---|---|
| `./scripts/release-digest` | `---META---`, exact `---SERVICES---` header below, optional `---TOGGLES---` |
| `./scripts/release-order` | `---SOURCE---`, effective `---GRAPH---`, `---DRIFT---` |
| `./scripts/contract-check all` | Staleness, uncommitted, sync coverage, verification coverage, relationship matrix |

It also reads optional `docs/release-manifest.yaml` and `.release-state.json`. It never creates,
rewrites, or repairs either, never passes `--write`, and never runs provider commands itself.
Adapters are trusted project read-only commands; this helper is not a sandbox for arbitrary scripts.
Each command has a 20-second timeout (bounded 1–120 via `RELEASE_GATES_TIMEOUT`) and a 1 MiB accepted
output limit. Diagnostics do not echo raw command stderr or configuration contents.

`release-order` and `release-ci` remain installed under `release-manager/scripts/`. The former
composes Pact with manual/suppressed edges; the latter supplies exact upstream CI evidence to the
project digest. Setup belongs to an explicitly requested project setup task, not any release tick.
See their `--help` and tests for adapter-specific configuration; do not bypass them in consumers.

Digest header:

```text
service|unpushed|uncommitted|ci|ciBranch|gitBranch|head|deploy|tag|age|ciRevision|ciExpectedRevision
```

Metadata requires a nonempty provider name in `ciProvider` and
`ci=available|partial|unavailable`. Supported providers are `circleci`, `github-actions`,
`cloud-build`, and `none`; unsupported providers retain other evidence but cannot pass the CI gate. `context` is optional display evidence. Service names must be
unique; unpushed counts are nonnegative integers and dirty markers are exactly `true`/`false`.
Malformed required evidence never means an empty all-clear.

## Policy subset

Absent manifest means empty defaults. Unreadable, malformed, or unsupported readiness policy
produces `HOLD`, not empty defaults. The helper deliberately supports only the policy subset below,
not arbitrary YAML. Other top-level sections belong to their existing adapters and are not parsed.

```yaml
ignore: [infrastructure]
non_deploying:
  - documentation
toggles:
  FLAG_EXAMPLE:
    service: web
    status: active
    flip_when: "after validation # not a YAML comment"
parked:
  OLD_FLAG:
    superseded_by: FLAG_EXAMPLE
    reconsider_if: requirements change
```

Two-space block indentation; flow or block service lists; block flag maps (or empty `{}`); plain,
single-quoted, or JSON-compatible double-quoted scalar text. Anchors, aliases, multiline scalars,
nonempty inline maps, duplicate readiness keys, and unsupported indentation fail closed. Active
flag entries require a service; status defaults to `active` and may be `parked` or `dark-release`.
A flag in `parked` overrides its active declaration. No inferred flags or new `expected` field.

## Policy table

`block` outranks `hold`; either outranks `READY`. `na` has no verdict impact. Required unavailable
evidence is a `hold`, not an ambiguous N/A row. No gate can be overridden by a consumer.

| Gate | Pass / informational | Hold | Block |
|---|---|---|---|
| Work | Clean with unpushed commits | Dirty tree, including non-deploying repos; missing Git evidence | No unpushed work |
| CI | Exact upstream success; N/A for non-deploying | Missing/degraded evidence, running, ref/revision mismatch | Exact failed/error |
| Contracts | Applicable clean; N/A with no known relationship and no adapter | Applicable coverage GAP; expected/malformed/unavailable evidence | Stale/different/missing/uncommitted/not-built/not-synced |
| Order | Settled prerequisites; valid empty `provider=none`; N/A for non-deploying | Missing graph/prerequisite/live evidence | Co-changing prerequisite (unpushed or rolling) |
| Toggle | Active true **or false** observed; parked/dark-release informational | Missing/unknown active declared flag | — |
| Deployment | Settled `N/N` (N>0) or `cron`; unavailable optional capability is N/A | Overlapping rollout or saved rollout lacking evidence | — |

CI requires matching non-sentinel branches and revisions. Partial provider availability does not
invalidate an individually exact service row; unavailable provider evidence does. Upstream green
never implies candidate-tested. A non-deploying classification exempts only CI/order/deployment,
not cleanliness, applicable contracts, or declared active flags.

False active flags yield an **activation follow-up** note; shipping disabled is allowed. Missing
active evidence holds. Parked/dark-release flags never cause a flip or a push blocker.

Coverage GAP holds the provider and named `not-verified` consumers. A provider-wide GAP without
that list also holds its consumers identified by contract relationship evidence; never infer
coverage from a missing list. Summary/finding inconsistencies hold while proven hard findings
retain precedence.

Contract applicability comes from named contract evidence or Pact-backed graph relationships.
An absent optional adapter with no known relationship is N/A. A present but broken/incomplete
adapter holds rather than implying no contracts. Existing adapter limitations remain visible:
this evaluator does not establish coverage that a collector cannot observe.

Unreadable/malformed saved rollout state holds deploying candidates rather than silently discarding
possible in-flight work. Absent state is valid. Saved `rolloutWatch` entries are advisory tracking,
not proof. A known pre-push `fromTag`, a
changed non-sentinel live tag, and settled replicas/cron confirm observed rollout movement.
This does **not** prove exact candidate-image provenance. Missing baselines or live observations
remain unknown; never substitute pod age or assume completion. `/release-maintenance
acknowledge-rollout <service>` is the explicit evidence-backed recovery path. Dependency checks
use the full snapshot, even for a single-service display, including ignored prerequisite rows.

## JSON output and fixtures

Output schema version 1 includes `observedAt`, `context`, `services`, `drift`, `errors`, and an
aggregate `verdict`. Each service preserves normalized digest fields plus `nonDeploying`,
`prerequisites`, `rollout`, `gates`, `notes`, and `verdict`. Each gate has `result` and an `evidence`
array. Use **per-service** verdicts for push candidates: an idle service's `NOT READY` does not
block an unrelated ready service. The aggregate is a summary, not a batch push authorization.

Missing/invalid digest or snapshot produces `HOLD`, `errors`, and no service rows. Evaluation
failures are data, not a successful readiness exit-code convention; consumers must inspect JSON.
CLI usage errors may exit nonzero. Invalid/empty output always withholds action.

For offline tests, `--snapshot <file>` runs **no collectors** and reads no project files. The raw
evidence envelope (never hand-transcribe it to authorize a push) is:

```json
{
  "schemaVersion": 1,
  "digest": {"status": "ok", "text": "<raw digest stdout>"},
  "order": {"status": "ok", "text": "<raw order stdout>"},
  "contracts": {"status": "absent", "reason": "no adapter"},
  "manifest": {"status": "absent", "reason": "not configured"},
  "state": {"status": "absent", "reason": "no state"}
}
```

Source status is `ok`, `absent`, or `unavailable`; ok requires bounded text. Unknown schema keys
or versions are invalid. Collector absence/failure is visible in `errors` even when an optional gate legitimately resolves
to N/A; those diagnostics do not override the returned per-service verdict. Unmanaged ordering
appears in `drift`, and an explicitly selected ignored service has an explanatory error.
Snapshots are test/debug data, not a persisted release authorization;
interactive actions always recollect current evidence.
