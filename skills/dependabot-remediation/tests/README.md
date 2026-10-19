# Dependabot remediation checks

Run from the repository root during authorized maintenance:

```sh
make test-dependabot-remediation
make validate-skills
```

Requires Python 3.10+ standard library and Git. The collector suite runs the real script
against a fake `gh` on a private `PATH`, so it never contacts GitHub, never needs
authentication, and asserts the exact request paths, exit codes and redaction. The planner
suite imports the script module directly. No tracker is read, no package registry is queried,
no dependency is installed, and no model is launched.

## Coverage

| Acceptance case | Where it is checked |
|---|---|
| No alerts versus denied / rate-limited / truncated / malformed / timed-out access | collector suite |
| Cursor pagination: exact first request, next links on short pages, full final pages, page cap, malformed/foreign/repeated cursors, failed later pages, all-state filtering | collector suite |
| Valid direct and transitive patch/minor remediation | planner suite |
| Transitive parent ranges: every range must allow the patch; excluded, missing or unsupported range evidence held | planner suite |
| Several alerts resolved by one coherent fix; independent fixes stay distinct | planner suite |
| One bounded batch in priority order with per-outcome evidence; remainder deferred, never dropped; `--batch-limit` bounded; identical plan on rerun | planner suite |
| Unpatched dev-only alerts and majors stay residual risk outside the batch | planner suite |
| Severity independent of upgrade size | planner suite |
| Major / pre-1.0 / breaking / uncertain / no-patched-version / unsupported ecosystem held | planner suite |
| Untrusted advisory text dropped or bounded; token shapes redacted | collector suite |
| Dirty scope and partial evidence surfaced as blockers | planner suite |
| Stale revision, changed alert, dismissed versus fixed, unavailable final read | planner recheck suite |
| Idempotent rerun | planner suite |
| Batch bead reuse / workspace store routing, existing Dependabot PRs changing nothing, exception budget and checkpoints, gate failure, publication audit and single push, run ending without follow-on | `scenarios.json` authored expectations plus `SKILL.md` term assertions |

`scenarios.json` holds authored expectations for review: each case names the helper tests
that mechanically cover it, or an empty list when only the instructions and the composed
owner skills (`develop`, `verify-task`, `complete-task`, `artifact-hygiene`) govern it.
These are not observed model behavior and prove neither live GitHub state nor runtime
permission enforcement. A real-repository dogfood run is separate, explicitly scoped work.

## Regression provenance

The first authorized Sortingoffice discovery returned HTTP 400 because the collector sent
`page=1`. Its original mocks duplicated that unsupported request rather than the API contract.
The cursor regression fixture now rejects numeric `page`, emits HTTP headers only when
`--include` is requested, and tests completion from `Link` rather than result count. The tests
were observed failing before the cursor fix.

An authorized Expire discovery then showed the planner marking `@grpc/grpc-js` 1.9.16 → 1.13.6
eligible although its only parent pins `~1.9.0`. Transitive outcomes now need parent-range
evidence that provably admits the patch; that regression and the npm range table were observed
failing before the fix. Live single-page success alone does not prove
multi-page behavior; the latter remains covered by offline fixtures.

Authorized Gauge runs in October 2026 consumed days in per-package tracking, validation
worktrees, PR triage and deployment monitoring (saved handoffs, not reconstructed skill
behavior). The batch contract now bounds a run to one batch with an explicit limit, an
exception budget and a stopping rule. The batch fixtures and the `one bead per batch` term
assertions fail by construction against the previous planner (no `batch` field) and
per-outcome instructions; they were not run live against Gauge.
