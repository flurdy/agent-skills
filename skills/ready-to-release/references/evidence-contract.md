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
| `./scripts/release-config-uptake` | Optional; `---META---` provider and `---UPTAKE---` rows, see [Config uptake](#config-uptake-advisory) |

It also reads optional `docs/release-manifest.yaml` and `.release-state.json`. It never creates,
rewrites, or repairs either, never passes `--write`, and never runs provider commands itself.
Adapters are trusted project read-only commands; this helper is not a sandbox for arbitrary scripts.
`release-digest` has a 90-second budget and the other commands 20 seconds each, so one collection
may take up to 150 seconds; `RELEASE_GATES_TIMEOUT` overrides every budget (bounded 1–120). An
expired budget kills the adapter's process group and reports `<command> timeout after <N>s budget`
in top-level `errors`, which consumers render as a prominent incomplete-check heading, never as a
verdict. Each command also has a 1 MiB accepted output limit. Diagnostics do not echo raw command
stderr or configuration contents.

`release-order` and `release-ci` remain installed under `release-manager/scripts/`. The former
composes Pact with manual/suppressed edges; the latter supplies exact upstream CI evidence to the
project digest, polling at most four services concurrently in stable input order. Setup belongs to an explicitly requested project setup task, not any release tick.
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
| Work | Clean with unpushed commits | Releasing service's own dirty tree, including non-deploying repos; missing Git evidence | No unpushed work |
| CI | Exact upstream success; N/A for non-deploying | Missing/degraded evidence, running, ref/revision mismatch | Exact failed/error |
| Contracts | Applicable clean; N/A with no known relationship and no adapter | Applicable coverage GAP; expected/malformed/unavailable evidence | Stale/different/missing/uncommitted/not-built/not-synced |
| Order | Settled prerequisites, even with uncommitted local changes; valid empty `provider=none`; N/A for non-deploying | Missing graph/prerequisite/live evidence | Co-changing prerequisite (unpushed or rolling) |
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
A prerequisite's uncommitted local changes are undeployed work, not an ordering hold by
themselves. Preserve its dirty field in emitted rows and report an informational note on the
consumer, including when the prerequisite is omitted from a selected or ignored display.
The releasing service's own cleanliness and applicable contract gates remain unchanged;
prerequisite unpushed commits, rolling rollouts and missing/unsettled evidence retain their gates.

Any saved `publishing` record adds a `publication` HOLD to every service: a push is in progress or
its outcome is uncertain, so further publication waits. Unreadable state holds every service the
same way, including non-deploying ones. Only the release-state helper settles a record, or
`/release-maintenance resolve-publication <service>` after an explicit human answer.
`--exclude-publication <id>` evaluates as if that single attempt's record were absent; the
manager uses it only to recheck readiness for its own in-progress attempt.

## Config uptake (advisory)

Config uptake answers **which configuration revision is desired, which the controller applied,
and which the running workload actually consumes**. It is advisory: it adds no gate, never
changes a verdict, and its diagnostics stay out of `errors`. Unsupported projects see
`uptake.status` `absent` or `not-captured` and `configUptake: []`. Nothing is inferred from
mounts, source greps, flag names, resourceVersion movement, pod age or the legacy digest
`---CONFIG---` section, and legacy `configApply`/`restartPending`/`restartWatch` state is not read.

Projects opt in with explicit declarations in `docs/release-manifest.yaml`, parsed separately
from readiness policy so a bad declaration is an `uptake.diagnostics` entry, not a hold:

```yaml
config_uptake:
  web-config:
    service: web
    resource: configmap/web-config
    context: prod
    namespace: apps
    workload: deployment/web
    reload: startup   # startup | dynamic | unknown (default)
```

and the optional read-only adapter `./scripts/release-config-uptake` (20-second budget):

```text
---META---
provider=kubernetes
---UPTAKE---
resource|context|namespace|workload|desired|applied|consumed|rolloutState|template
configmap/web-config|prod|apps|deployment/web|c2|c2|c1|settled|c2
```

| Field | Meaning |
|---|---|
| `desired` | Intended configuration revision from the project's source of truth |
| `applied` | Revision the controller observably applied to that resource (for example the Flux Kustomization's last applied revision whose inventory contains it); a Git push or a changed resourceVersion is not applied |
| `consumed` | Revision the workload's current serving pods are verified to consume (application-effective); a pod-template annotation alone is intent, not consumption |
| `rolloutState` | `settled`, `rolling` or `unknown` for that workload |
| `template` | Revision newly started pods would receive from the current pod template |

Every field is a name/revision token or `-` (unknown); values, secrets and free text are rejected
and the whole source is reported `malformed` without echoing it. Use one immutable, resource-bound
revision scheme across the four revision fields: the evaluator compares tokens and cannot detect
reused labels. Observations match declarations on the full resource/context/namespace/workload
identity; duplicate observations conflict, and observations without a declaration are listed in
`uptake.unmapped`.

Each declared mapping yields one `configUptake` entry with `state` and optional `maintenance`:

| State | Condition | Maintenance |
|---|---|---|
| `unknown` | Evidence not captured, absent, unavailable or malformed; no or conflicting observation; identity mismatch; `desired` or `applied` unknown | none |
| `pending` | `applied` differs from `desired` | none; the controller has not applied it |
| `effective` | `consumed` equals `desired` | none |
| `rolling` | Applied, and a rollout in progress whose template delivers `desired` | none; wait |
| `applied` | Applied but not verified consumed | `restart` only with `reload: startup`, a settled workload, a known different `consumed` and a template that delivers `desired`; otherwise `investigate` |

`restart` names the workload and the handoff `/release-maintenance restart <service>`; it is a
suggestion for a separately requested, freshly confirmed operation, never an action. Declared
`dynamic` reload is capability, not proof: without verified consumption it is `investigate`.
An unrelated rollout never satisfies uptake and never earns a restart while it is in flight.
Entries other than `effective` also appear as `config <id>: …` notes so every consumer shows them.

## JSON output and fixtures

Output schema version 1 includes `observedAt`, `context`, `services`, `drift`, `errors`, an
advisory `uptake` summary (`status`, `unmapped`, `diagnostics`, optional `reason`), and an
aggregate `verdict`. Each service preserves normalized digest fields plus `nonDeploying`,
`prerequisites`, `rollout`, `gates`, `notes`, `configUptake`, and `verdict`. Each gate has `result` and an `evidence`
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

Source status is `ok`, `absent`, or `unavailable`; ok requires bounded text. An optional sixth key
`uptake` carries the config-uptake adapter envelope; omitting it means not captured. Other unknown
schema keys or versions are invalid. Collector absence/failure is visible in `errors` even when an optional gate legitimately resolves
to N/A; those diagnostics do not override the returned per-service verdict. Unmanaged ordering
appears in `drift`, and an explicitly selected ignored service has an explanatory error.
Snapshots are test/debug data, not a persisted release authorization;
interactive actions always recollect current evidence.
