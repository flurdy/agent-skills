# Release-order authority pilot — 2026-07-31

## Scope

Validate one deploy-order boundary for `release-manager`, `release-status`, and
`ready-to-release` without requiring Pact contracts or a release manifest.

## Contract

`release-order` emits three bounded sections:

- `---SOURCE---`: provider (`pact`, `manifest`, or `none`), accepted graph source, and manifest
  presence;
- `---GRAPH---`: the effective `consumer: [providers]` map;
- `---DRIFT---`: pact drift when reconcilable, otherwise an explicit `unmanaged` or
  `not-applicable` status.

The effective map is `(accepted provider edges ∪ order.manual) − order.suppress`. A committed
pact-generated block remains accepted while drift is awaiting explicit reconciliation; projects
without pacts use `order.manual`; projects without either source receive an empty graph.

## Automated evidence

`make test-release-order` passes seven behavioral fixtures plus the three-consumer contract:

1. no manifest and no pacts → `provider=none`, empty graph, success;
2. manifest-only manual edges and suppression → effective declared graph;
3. pact-generated edges plus manual edges and suppression → merged effective graph;
4. pacts without a manifest → live graph, read-only unmanaged status, guarded write refusal;
5. the generated block keeps the pact provider active after the last edge disappears, then
   `--write` reconciles it in a temporary project;
6. unsupported non-empty inline manual maps fail clearly instead of losing edges;
7. the pact provider works in a normal Git root without `.mgit.conf`.

The consumer contract proves all three release skills invoke `./scripts/release-order`, none invoke
the pact provider directly, reconciliation uses `release-order --write`, and missing-manifest
defaults are documented.

## Letterbox compatibility check

A read-only run from `/home/ivar/Code/flurdy/letterbox` selected:

```text
provider=pact
graph=generated
manifest=present
```

Its effective graph matched the accepted generated manifest, including `hosted -> scoring`. It
also preserved the existing provider drift signal `removed: hosted -> scoring`; no reconciliation
or project file mutation was performed. The legacy direct provider returned the same live pact
graph and drift.

## Safety

- No network, credentials, Git remote operation, release action, or production action is used.
- `--write` is unavailable for `manifest` and `none` providers and fails without a manifest.
- The release manager offers reconciliation only for concrete `new:`/`removed:` drift lines.
- Manifest-free projects default optional manifest sections to empty rather than failing order
  evaluation.
