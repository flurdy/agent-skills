# Pact-lite project integration

This is a project-facing contract for a **separate setup request**, not an automatic phase of
`contract-check` or `contract-test`. Use the owning project's coding workflow (for example
`/develop`) to add or change integration. Read its instructions, inspect existing destinations,
preview each file/command and affected repository, then obtain confirmation for the exact scope.
Do not initialize workspaces, install packages or execute hooks/tests merely by reading this guide.

## Read-only audit integration

The shipped helper supports these conventions only:

| Surface | Required contract |
|---|---|
| Root | Nearest ancestor `.mgit.conf`, or existing absolute `RELEASE_PROJECT_ROOT` supplied by a caller |
| Topology | Flat service directories immediately below the root; no nested `repos/service` discovery |
| Consumer output | `<consumer>/target/pacts/<consumer>-consumer-<provider>-provider.json` |
| Provider input | `<provider>/test/resources/pacts/` or `<provider>/src/test/resources/pacts/` |
| Git adapter | Reviewed `scripts/mgit status <service> --porcelain=v1 --untracked-files=all -- <pact-directory>/`; must honor `GIT_OPTIONAL_LOCKS=0` and propagate failure |
| Edge collector | Reviewed executable `scripts/pact-pairs`, modes below; not provided by this skill |
| Runtime | Bash 4+ (associative arrays), GNU stat/date, and standard grep/sed/awk/sort/cmp utilities |

Single repositories, other layouts and languages may use the runner through existing explicit
commands, but are not automatically covered by this mechanical auditor. Do not invent compatible
output or create topology to turn unavailable checks green.

### Project-owned edge protocol

`scripts/pact-pairs intended`, `built`, and `synced` emit TSV: consumer name, provider name, optional
additional fields. One edge per line; no headings or diagnostics on stdout. Names must be nonempty
service identifiers, not shell expressions. Duplicate edges are permitted and treated as sets.

- `intended`: edges derived from actual consumer test definitions/project conventions.
- `built`: edges with generated consumer pact files.
- `synced`: edges with provider copies.

The collector must be read-only, send diagnostics to stderr and return nonzero on failure. Empty
output with exit zero asserts an observed empty set, not unavailable discovery. Review all delegated
code before accepting that assertion. The audit does not validate that this project-owned collector
correctly discovers every edge; fixture adapters demonstrate the interface, not adoption completeness.

A collector failure produces `NO_DATA` and `SUMMARY ... status=error`. Failed Git status does likewise,
without `CLEAN`. These markers make the current release parser treat the entire contract report as
incomplete; expect a release HOLD, not silently successful partial evidence.

### Optional project adapter; required for existing release collection

The audit calls `~/.agents/skills/contract-check/scripts/contract-check.sh` directly. Existing release
collection instead invokes `./scripts/contract-check all`, so a project using that release integration
needs a reviewed adapter to the same authority. Do not maintain a divergent copy of the audit.

For a separately approved local setup, after checking that `$ROOT/scripts` exists and the destination
is absent, preview and confirm this exact link command with the actual root substituted:

```bash
ln -s "$HOME/.agents/skills/contract-check/scripts/contract-check.sh" "$ROOT/scripts/contract-check"
```

Use a non-forcing link: **never overwrite** an existing file or symlink without a separate, explicit
replacement decision. Do not change executable permissions through the link; that changes the shared
source. Missing source/executable support is a prerequisite to resolve in its owning installation.
For CI/other machines, use the project's reproducible installed path or reviewed adapter rather than
assuming another user's HOME layout. Test that it emits the same report contract.

Without this adapter the release collector has no audit evidence. Other relationship evidence may
still require contracts, but absence can otherwise appear not applicable; a missing adapter is not
proof the project has no contracts. Audit integration and release-adapter integration must both be
validated during setup.

## Supported static CI evidence

The legacy heading `CI Verification Coverage` is retained for downstream compatibility. It reports
**static text conventions**, never live verification, workflow reachability, triggers, branch filters,
job activation, successful CI runs or complete file selection.

Only `<provider>/.circleci/config.yml` is inspected:

- **enum:** uncommented `PACTCONSUMER`, `PACTCONSUMER1`, etc. scalar entries containing literal
  service names, optionally suffixed `-consumer`; single/double quotes and trailing comments are
  accepted. The literal set is compared with synced consumer names. Enumeration takes precedence
  over a tag mention, conservatively avoiding an assumed all-consumer run.
- **tag:** absent enumeration, a line naming `sbt testOnly -- -n tags.ContractVerifyTest` (including
  the usual quoted testOnly argument), either a shell line or literal `run:`/`command:` value.
  This only names a tag-driven verification mechanism. The project's tests must independently prove
  the tag selects the intended verifier and every relevant pact.
- Comments and prose/echo mentions of `ContractVerifyTest` do not supply tag evidence. Dynamic
  variables/parameters, commands hidden behind Make targets, reusable orbs, folded commands,
  chained commands, extra suite selectors, other tag syntax and `.circleci/config.yaml` are
  unsupported, not inferred. YAML aliases are not resolved; only visible literals are inspected.
- GitHub Actions and other engines are unsupported by this helper. A separate semantic review may
  inspect them, but must not manufacture a mechanical OK row or a CI pass.

This is not a YAML parser. Comment stripping is deliberately conservative: `#` inside a quoted
value also truncates it and can make evidence unavailable. Literal entries can occur in jobs that
never run. An OK row means only the inspected convention names the expected mechanism/consumers.

A known enum omission uses `GAP ... style=enum ... not-verified=<names>`. Missing/unreadable or
unsupported CI uses `GAP ... style=unsupported ... evidence=unavailable`; render this as **UNKNOWN**,
not a proven test gap. The legacy GAP signal gives the existing release evaluator a scoped HOLD
for the provider and its related consumers. It is not a hard compatibility-failure assertion.
The script preserves section headings, summary counters and matrix rows for release consumers.

## Execution setup (separate coding scope)

Supply project-owned, documented commands and tests for:

1. Consumer generation separately from provider verification, with exact expected output pairs.
2. Local sync with explicit destination ownership, preservation of existing edits and scoped copying.
3. Optional normalization with documented transformations and matching scope.
4. Provider verification that demonstrably exercises each intended consumer (including zero-test
   detection), plus CI job wiring and failure propagation for the project's actual engine.

Target names such as `test-contract`, `sync-pacts` or `pact-publish` are not behavior guarantees.
Inspect their delegated commands; broker publication is outside this filesystem-only runner.
Do not add generic placeholder Make targets or language-specific commands without project evidence.

For a named-consumer full run, ALL selected consumers finish before any sync; only affected providers
and authorized files are then synced/normalized/verified. A global-only target requires separately
confirmed scope expansion or a scoped integration change, never silent use.

## Verification boundary

`make test-contract-check` exercises audit fixtures, both role contracts, the setup reference and
real helper output through the existing release parser. `make check` includes it in repository CI.
These checks do not run real consumer/provider suites or certify a project's CI graph. Setup in a
project needs its own selected-command, copy-scope, verifier-selection and actual CI evidence.
