---
name: contract-check
description: "Audit health of contract tests across services — staleness, sync gaps, uncommitted pacts, missing tests."
allowed-tools: "Read,Grep,Glob,Bash(./scripts/contract-check:*),Bash(./scripts/mgit:*),Bash(ls:*),Bash(chmod:*),Skill,AskUserQuestion"
version: "1.0.0"
author: "flurdy"
---

# Contract Check — Pact Health Auditor

Audits the health of consumer-driven contract tests across all letterbox services. Surfaces staleness, sync gaps, uncommitted pacts, missing tests, documentation drift, and disabled tests.

This is a **read-only audit** — it does not run tests or modify files. Use `/contract-test` to execute contract test workflows.

## When to Use

- Starting a work session to check contract health
- After modifying connectors or API endpoints
- Before a release to verify all contracts are synced and committed
- Periodically to catch drift and gaps

## Usage

```
/contract-check              # Full audit (all checks)
/contract-check status       # Summary dashboard only
/contract-check stale        # Consumer output newer than provider copy
/contract-check uncommitted  # Pact files not committed in service repos
/contract-check sync-gaps    # Pairs missing from sync-pacts.sh
/contract-check missing      # Connectors with no consumer tests
/contract-check docs         # Documentation drift in pact-workflow.md
/contract-check disabled     # Contract tests excluded from default builds
/contract-check <service>    # All checks scoped to one service
```

## Setup

On first run, ensure the script symlink exists:

```bash
ln -sfn "$SKILLS_DIR/contract-check/scripts/contract-check.sh" ./scripts/contract-check
chmod +x ./scripts/contract-check
```

Where `$SKILLS_DIR` resolves to `${CLAUDE_HOME:-$HOME/.claude}/skills`.

## Instructions

### Step 0: Ensure Setup

Check that `./scripts/contract-check` exists and is executable. If not, create the symlink as shown in Setup above.

### Step 1: Parse Subcommand

Parse the user's argument:
- `(none)` or `full` → Run all checks (mechanical + semantic)
- `status` → Run all checks but only show the summary table
- `stale` → Run `./scripts/contract-check stale`
- `uncommitted` → Run `./scripts/contract-check uncommitted`
- `sync-gaps` → Run `./scripts/contract-check sync-gaps`
- `missing` → Run semantic Missing Consumer Tests check (Step 3)
- `docs` → Run semantic Documentation Drift check (Step 4)
- `disabled` → Run semantic Disabled Tests check (Step 5)
- `<service>` → Run all checks scoped to that service
- `matrix` → Run `./scripts/contract-check matrix`

### Step 2: Mechanical Checks (via script)

Run the appropriate script subcommand:

```bash
./scripts/contract-check all      # or stale, uncommitted, sync-gaps, matrix
```

Parse the script output. Each line starts with a status keyword:
- `OK` — no action needed
- `STALE` — consumer pact is newer than provider copy
- `DIFFERS` — same age but content differs
- `MISSING_PROVIDER` — provider does not have this pact file
- `UNCOMMITTED` — pact file has uncommitted changes
- `COVERED` — pair is in sync-pacts.sh
- `NOT_SYNCED` — pair has consumer pact but is missing from sync-pacts.sh
- `STALE_SYNC` — pair is in sync-pacts.sh but consumer has no pact file (not built)
- `CLEAN` — no issues found
- `NO_DATA` — no consumer pact files found
- `SUMMARY` — counts for the check

### Step 3: Missing Consumer Tests (LLM-driven)

For each consumer service, compare connectors against consumer test files:

1. **Find connectors** — Glob for connector files:
   - Play services (admin, hosted, registration, profile, web): `<service>/app/connectors/*Connector.scala`
   - Scala 3 services (digest, patrol, reconciler, dispatch, etc.): `<service>/src/main/scala/**/connectors/*Connector.scala`

2. **Find consumer tests** — Glob for consumer test files:
   - Play services: `<service>/test/contract/*Consumer*.scala`
   - Scala 3 services: `<service>/src/test/scala/**/contract/*Consumer*.scala`

3. **Extract provider name** from connector filename: strip `Connector` suffix, lowercase. E.g., `AccountConnector.scala` → `account`.

4. **Exclude external connectors** that are not internal services:
   - Braintree, Stripe, SES, Spam, Web, Api (base class), ConnectorConfiguration, ConnectorModule

5. **Cross-reference**: For each connector, check if a matching consumer test exists. Report connectors with no consumer test.

Output format:
```
### Missing Consumer Tests
| Service | Connector | Provider | Has Consumer Test |
|---------|-----------|----------|-------------------|
| reconciler | EventConnector | event | NO |
| reconciler | MessageQueueConnector | messagequeue | NO |
```

### Step 4: Documentation Drift (LLM-driven)

1. Read `docs/pact-workflow.md`
2. Run `./scripts/contract-check matrix` to get actual relationships
3. Compare the documented consumer→provider relationships against the matrix
4. Flag:
   - Consumers listed in docs but not in matrix (or vice versa)
   - Providers listed in docs but not in matrix (or vice versa)
   - Stale TODOs or notes that have been resolved
   - Missing entries for newer services (digest, patrol, reconciler, profile)

### Step 5: Disabled Tests (LLM-driven)

1. Search for contract test exclusions in build.sbt files:
   - Pattern: `-l tags.ContractTest` or `--exclude-tags=ContractTest`
   - Check both active and commented-out exclusions

2. For services with active exclusions, check if the Makefile `test-contract` target overrides it (e.g., with `set Test/testOptions := Nil`)

3. Report:
   - Services where `sbt test` silently skips contract tests
   - Whether the Makefile target correctly overrides the exclusion
   - Services lacking a `test-contract` Makefile target entirely

### Step 6: Format Report

Combine all findings into a health report:

```markdown
# Contract Health Report

## Summary
| Check            | Status | Details                        |
|------------------|--------|--------------------------------|
| Staleness        | PASS/WARN/FAIL | X stale / Y total       |
| Uncommitted      | PASS/WARN | X files across Y services     |
| Sync coverage    | PASS/FAIL | X/Y pairs in sync-pacts.sh   |
| Missing tests    | PASS/WARN | X connectors without tests    |
| Documentation    | PASS/FAIL | X items out of date           |
| Disabled tests   | PASS/INFO | X services exclude by default |

## Staleness
[details from script output]

## Uncommitted Pact Files
[details from script output]

## Sync Coverage Gaps
[details from script output]

## Missing Consumer Tests
[details from LLM analysis]

## Documentation Drift
[details from LLM analysis]

## Disabled Tests
[details from LLM analysis]

## Recommended Actions (priority order)
1. [most impactful fix first]
2. ...
```

Status thresholds:
- **PASS**: No issues found
- **INFO**: Informational, no action required
- **WARN**: Issues found but not blocking
- **FAIL**: Significant gaps that should be addressed

### Step 7: Offer Remediation

After presenting the report, ask the user:

> Would you like me to create beads for the issues found? I can triage them as P3 tasks with appropriate service labels.

If the user agrees, use `/triage` to create beads for actionable findings. Group related findings into single beads where appropriate (e.g., "Add digest, patrol, reconciler to sync-pacts.sh" as one bead rather than three).

## Scoped Checks (single service)

When invoked with a service name (`/contract-check dispatch`):

1. Run mechanical checks and filter output to only show lines involving that service (as consumer or provider)
2. Run semantic checks scoped to that service only
3. Present a focused report for just that service

## Error Handling

- **Script not found**: Create the symlink (see Setup)
- **mgit not found**: Error — must be run from within the letterbox project root
- **No consumer pact files**: Report that consumer tests haven't been run; suggest `make test-contract` in consumer services
- **Service directory missing**: Skip gracefully, note in output

## Known Provider Pact Directories

Most providers use `test/resources/pacts/`. Exceptions:
- **event**: `src/test/resources/pacts/`
- **membership**: `src/test/resources/pacts/`

## Known External Connectors (exclude from missing-test checks)

Braintree, Stripe, SES, SpamConfiguration, WebConfiguration, ApiConnector (abstract base), ConnectorConfiguration, ConnectorModule
