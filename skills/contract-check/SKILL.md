---
name: contract-check
description: "Read-only Pact-lite health audit: content drift, uncommitted pacts, sync gaps, static CI evidence, and semantic test gaps. One status authority; never runs tests or repairs setup."
allowed-tools: "Read,Grep,Glob,Bash(~/.agents/skills/contract-check/scripts/contract-check.sh:*)"
model-tier: standard
model: sonnet
effort: medium
version: "2.0.0"
author: "flurdy"
---

# Contract Check — Read-Only Pact Health

Own contract health evidence and rendering. The [runner](../contract-test/SKILL.md) owns
explicit test generation, local sync, normalization and provider verification. Release workflows
consume this audit's mechanical evidence; do not create a second health collector.

This audit never runs tests, creates links, changes permissions, copies pacts, fixes CI, or writes
tracking. Do not normalize before auditing or dismiss generated-looking diffs as harmless. Report
findings and optional next-command pointers without confirmation prompts or automatic handoffs.
A separate setup request belongs to the [project setup contract](references/project-setup.md).

## Usage

```text
/contract-check                 # full mechanical and semantic audit
/contract-check status          # same evidence, summary only
/contract-check stale           # content equality and timestamp diagnostics
/contract-check uncommitted     # provider-pact Git status
/contract-check sync-gaps        # intended → built → synced edges
/contract-check coverage        # bounded static CircleCI evidence
/contract-check matrix          # observed consumer/provider file relationships
/contract-check missing         # semantic missing-test review
/contract-check docs            # semantic documentation drift
/contract-check disabled        # semantic test-exclusion review
/contract-check <service>        # verified service, scoped presentation
```

`full` and `all` mean the default full audit. Reject unrecognized arguments instead of guessing
commands or treating an unknown name as a service. This is not a setup/remediation interface.

## Prerequisites and scope

The helper requires Bash 4+, GNU stat/date, standard shell utilities and the existing project
integration documented in [project setup](references/project-setup.md). Automated discovery is
limited to flat services with `target/pacts/` consumer output and `(src/)test/resources/pacts/`
provider input. Do not claim support for arbitrary language layouts or nested workspace paths.

Run from the intended project. The helper honors an existing absolute `RELEASE_PROJECT_ROOT`
when supplied by the release authority; otherwise it finds the nearest ancestor `.mgit.conf`.
Verify that root before execution. Missing/invalid setup is **UNKNOWN**, not permission to create it.

Before checks that execute project-owned helpers, inspect `scripts/mgit` and `scripts/pact-pairs`
and their delegated commands. Their required modes must be read-only; unknown or mutating helpers
make that check unavailable. Do not execute unreviewed project code merely because a file exists.
`stale`, `coverage`, and `matrix` do not require these project helper calls. Missing executable
support means unavailable; do not install dependencies or repair permissions.

For a service view, confirm the service in project topology. Mechanical collection is project-wide;
filter its findings to edges involving that service and scope semantic reads to it. Do not present
full-project totals as service totals. If project-wide reads are outside authorization, report that
mechanical scoping is unsupported rather than expanding access silently.

## Collect once

Call the installed authority directly; no project symlink is needed for this audit:

```bash
~/.agents/skills/contract-check/scripts/contract-check.sh all
```

Replace `all` with the validated mechanical subcommand when only that check was requested.
Full/status uses one `all` collection, reusing its matrix for semantic review. If a dependency is
unsafe/unavailable, collect only independent safe checks and label omitted checks UNKNOWN.
Never substitute an arbitrary project `scripts/contract-check` implementation.

| Signal | Meaning |
|---|---|
| `OK` | Observed evidence matches the bounded check; not a live test result |
| `STALE` / `DIFFERS` | Pact bytes differ; consumer newer / not newer |
| `MISSING_PROVIDER` | No provider copy found in the supported layout |
| `UNCOMMITTED` | Modified, staged, deleted, renamed or untracked provider pact path |
| `NOT_BUILT` / `NOT_SYNCED` | Intended edge lacks built output / built edge lacks provider copy |
| `GAP ... style=enum ... not-verified=...` | Literal CI enumeration omits synced consumer names |
| `GAP ... style=unsupported ... evidence=unavailable` | CI evidence UNKNOWN, not proven missing tests |
| `CLEAN` | No Git findings from successfully inspected provider directories |
| `NO_DATA` / `status=error` | Absent observations / failed collector; never an all-clear |
| `SUMMARY` / `TOTAL` | Mechanical counters; preserve error/completeness context |

CI results are **static configuration text**, not proof a job is enabled, scheduled, reachable,
checks every file, or passed. Even tag-style OK requires project-specific validation of the selector
and workflow. Other CI engines and dynamic forms remain unknown; see the supported conventions.
No consumer output proves only that output is absent, not that tests were never run.

## Semantic review

For full/status or the requested semantic mode:

- **Missing tests:** use project documentation, connector/client code and actual consumer tests to
  identify intended internal boundaries. Do not infer providers solely by stripping a filename
  suffix, assume every connector is internal, or use a fixed service/external-connector roster.
- **Documentation:** locate the project's authoritative Pact workflow documentation; compare its
  declared relationships with the collected matrix. Absence of generated files is not proof a
  documented relationship is obsolete. Missing documentation is unavailable evidence.
- **Disabled tests:** inspect build exclusions, selected test suites, Makefile recipes and CI paths.
  Distinguish intentional unit-test exclusions with an explicit contract target from contract tests
  that have no evidenced execution path. Do not execute a build to discover its configuration.

Mark uncertain mappings and unsupported layouts UNKNOWN. Keep semantic findings separate from
mechanical findings and cite the relevant file/command evidence.

## Report

Render one table: check, PASS/INFO/WARN/FAIL/UNKNOWN, evidence/limitations. Full audit adds finding
rows by consumer/provider; status omits detail, not missing evidence. Preserve successful checks
when another is unavailable. Static CI OK is informational, never a live verification PASS.

Recommended actions are pointers only: `/contract-test consumer|sync|provider|full` for a separately
requested run, or an explicit coding/setup request for missing integration/tests/CI. Do not run them,
normalize files, create tasks, or offer automatic remediation from this audit.
