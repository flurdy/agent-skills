---
name: contract-test
description: Run consumer-driven contract tests (pact-lite, no broker). Guides through generating, syncing, and verifying contracts between services. Supports both single-service and multi-service project-wide runs.
version: "2.0.0"
author: "flurdy"
---

# Contract Test (Pact-Lite)

Consumer-driven contract testing without a broker. Contracts are JSON files exchanged directly between consumer and provider services via the filesystem.

## When to Use

- After modifying a **connector**, **API client**, or **endpoint interface** (request/response models, URLs, headers)
- When adding a **new REST endpoint** that other services will consume
- To verify contracts haven't broken after upstream/downstream changes
- When a consumer or provider test is failing and you need to re-sync contracts
- After bulk changes that touch multiple services — run project-wide to verify all contracts

## Usage

```
/contract-test                     # Auto-detect: run contract tests for current service
/contract-test consumer            # Run consumer tests to generate contract files
/contract-test sync                # Copy generated contracts to provider services
/contract-test provider            # Run provider verification against current contracts
/contract-test full                # Single-service: consumer + sync + provider for current service
/contract-test full all            # Multi-service: ALL consumers → sync → normalize → ALL providers
/contract-test full <svc> <svc>    # Multi-service: named consumers → sync → normalize → affected providers
/contract-test status              # Show contract test coverage and staleness
```

## Concepts

### Consumer-Driven Contracts (Pact-Lite)

This is a lightweight version of the [Pact](https://docs.pact.io/) workflow that works without a broker:

1. **Consumer** services define expected interactions with providers in test code
2. Consumer tests **generate contract files** (JSON) describing those expectations
3. Contract files are **copied** from consumer to provider (no broker — just filesystem)
4. **Provider** services verify they satisfy all consumer contracts

### Roles

- **Consumer**: A service that calls another service's API. Generates `.json` contract files.
- **Provider**: A service that exposes an API. Verifies contracts from its consumers.
- A service can be both consumer and provider for different dependencies.

## Instructions

### Step 0: Detect Project Context

Before running any command, detect the project context:

1. **Identify the scope** — is this a single-service or multi-service run?
   - `full all` or `full <svc1> <svc2>` → multi-service (see Multi-Service Workflow below)
   - Everything else → single-service, identify the current service from the working directory or ask the user

2. **Detect build tool and language**:

   | Indicator | Language | Build Tool | Test Command |
   |-----------|----------|------------|--------------|
   | `build.sbt` | Scala | sbt | `sbt test` or `sbt "testOnly -- -n ContractTest"` |
   | `package.json` | JS/TS | npm/yarn/pnpm | `npm test -- --grep contract` |
   | `go.mod` | Go | go | `go test ./... -run Contract` |
   | `pom.xml` | Java | maven | `mvn test -Dtest=*Contract*` |
   | `build.gradle*` | Java/Kotlin | gradle | `gradle test --tests '*Contract*'` |
   | `Cargo.toml` | Rust | cargo | `cargo test contract` |
   | `pyproject.toml` / `setup.py` | Python | pytest | `pytest -k contract` |

3. **Check for Makefile aliases** — prefer these over raw commands:

   ```bash
   # Check if Makefile has contract test targets
   grep -E '(test-contract|contract-test|pact)' Makefile 2>/dev/null
   ```

   Common Makefile targets (use these if available):
   - `make test-contract` — run contract tests (consumer or provider)
   - `make test-contract-only` — run only contract tests
   - `make pact-publish` — copy generated contracts to provider services
   - `make sync-pacts` — sync all contracts across services (root Makefile)
   - `make normalize-pacts` — normalize generated UUIDs/dates to reduce noise

4. **Determine service role**:
   - Look for consumer test files: `*Consumer*.{scala,java,ts,js,go,py,rs}`, `*Pact*.{...}`
   - Look for provider verification files: `*Verify*Pact*`, `*Provider*Verify*`
   - Check for contract output directory: `target/pacts/`, `pacts/`, `contracts/`
   - Check for contract input directory: `test/resources/pacts/`, `src/test/resources/pacts/`, `contracts/`

---

### Single-Service Workflow (consumer / sync / provider / full)

#### Step 1: Generate Contracts (Consumer Side)

Run consumer contract tests to generate contract JSON files:

```bash
# Prefer Makefile targets
make test-contract

# Or run the appropriate test command filtered to contract tests
# The generated contracts will appear in the output directory (e.g. target/pacts/)
```

After running, verify contracts were generated:
```bash
# Find generated contract files
find . -name "*.json" -path "*/pacts/*" -newer . -mmin -5 2>/dev/null
# Or check the known output directory
ls target/pacts/ 2>/dev/null || ls pacts/ 2>/dev/null || ls contracts/ 2>/dev/null
```

#### Step 2: Sync Contracts to Providers

Copy generated contract files from consumer to provider services:

```bash
# Prefer Makefile targets
make pact-publish        # Per-service: copies this consumer's contracts to providers
make sync-pacts          # Root-level: syncs all contracts across all services
```

If no Makefile target exists, copy manually:
```bash
# Pattern: cp <consumer-output>/<contract>.json <provider-input-dir>/
# Example:
cp target/pacts/*-account-provider.json ../account/test/resources/pacts/
```

**Important**: The contract filename typically follows the pattern:
`<consumer-name>-consumer-<provider-name>-provider.json`

#### Step 3: Normalize (if available)

If the project has a normalize step, run it after sync to reduce noisy diffs:

```bash
make normalize-pacts     # Root-level: normalize UUIDs/dates in synced pacts
```

This replaces generated UUIDs and timestamps with deterministic placeholders so git diffs only show meaningful contract changes.

#### Step 4: Verify Contracts (Provider Side)

Navigate to each affected provider service and run verification:

```bash
cd ../<provider-service>
make test-contract

# Or run provider-specific verification tests
# Look for test files named VerifyConsumerPacts, *ProviderVerify*, etc.
```

#### Step 5: Report Results

After running, report:
- Which contracts were generated/synced/verified
- Any failures with clear indication of which consumer-provider pair failed
- Suggestions for fixing broken contracts

---

### Multi-Service Workflow (full all / full <svc1> <svc2>)

For multi-service projects, the `full` subcommand with `all` or named services runs the complete project-wide workflow. **The ordering is critical**: all consumer generation must complete before syncing, and syncing must complete before provider verification.

#### Phase 1: Discover consumer and provider services

Identify which services are consumers and which are providers:
- Check project documentation (e.g. `docs/pact-workflow.md`) for the definitive list
- Or scan for consumer test files and provider verification files across all services
- If the user specified service names, those are the consumer services to run; providers are determined by which providers those consumers talk to

#### Phase 2: Run ALL consumer tests (generate pacts)

Run `make test-contract` in every consumer service. **All consumers must succeed before proceeding to sync.**

Execute consumers sequentially (each may start an sbt process):
```bash
# From project root — run each consumer's contract tests
cd <consumer1> && make test-contract
cd <consumer2> && make test-contract
# ... repeat for all consumer services
```

If any consumer fails, **stop and report the failure**. Do not proceed to sync with partial pacts — that would overwrite good provider pacts with stale ones.

Track results as you go:
```
| Consumer     | Status | Pacts Generated |
|-------------|--------|-----------------|
| admin       | PASS   | 7               |
| hosted      | PASS   | 7               |
| dispatch    | FAIL   | -               |
```

#### Phase 3: Sync ALL pacts at once

After all consumers pass, sync everything in one operation:

```bash
# From project root
make sync-pacts          # Copies all consumer pacts to provider directories
```

This is more reliable than per-service `make pact-publish` because the root sync script covers all known consumer→provider relationships in one pass.

#### Phase 4: Normalize pacts (if available)

```bash
make normalize-pacts     # Replace generated UUIDs/dates with deterministic placeholders
```

#### Phase 5: Run ALL provider verifications

Run `make test-contract` in every affected provider service:

```bash
cd <provider1> && make test-contract
cd <provider2> && make test-contract
# ... repeat for all provider services
```

If `full all` was specified, run all providers. If specific consumers were named, only run providers that those consumers talk to (determined from the sync script or documentation).

Track results:
```
| Provider     | Status | Consumers Verified |
|-------------|--------|--------------------|
| account     | PASS   | admin, digest, patrol |
| messagequeue| PASS   | admin, digest, dispatch, hosted, patrol, reconciler |
| membership  | FAIL   | admin, digest, hosted, patrol, reconciler |
```

#### Phase 6: Report summary

Report:
- Total consumers tested, passed, failed
- Total providers verified, passed, failed
- Any specific consumer→provider pair failures
- Suggestions for fixing broken contracts
- Remind about committing pact file changes if any were updated during sync

## Subcommand Details

### `consumer`
Run consumer contract tests for the current service. Generates contract files but does not sync or verify.

### `sync`
Copy existing contract files from consumer output directories to provider input directories. Does not run any tests. Prefer root-level `make sync-pacts` over per-service `make pact-publish` when available.

### `provider`
Run provider verification tests for the current service. Assumes contracts are already synced.

### `full` (no args)
Single-service workflow: consumer -> sync -> normalize -> provider for the current service and its affected providers. See Single-Service Workflow above.

### `full all`
Multi-service workflow: run ALL consumers -> sync ALL pacts -> normalize -> verify ALL providers. Use this after broad changes or to validate the entire contract test suite. See Multi-Service Workflow above.

### `full <svc1> <svc2> ...`
Multi-service workflow for named consumer services only. Runs the named consumers -> sync -> normalize -> verifies only the providers those consumers talk to. Useful when you know which services changed.

### `status`
Show an overview of contract test health:
- List all consumer-provider relationships detected
- Show last-modified timestamps of contract files
- Flag any contracts where consumer output is newer than provider copy (stale)
- Flag any providers missing contracts

## Error Handling

### Consumer test fails
- The contract definition in test code doesn't match expectations
- Fix the consumer test, then re-run `consumer`

### Provider verification fails
- The provider's actual API doesn't match the consumer's contract
- Either: (a) update the provider API to match, or (b) update the consumer contract if the change is intentional
- After fixing, re-run the full workflow

### Stale contracts
- Consumer output is newer than provider copy
- Run `sync` to update provider copies, then `verify`

### Noisy diffs after sync
- Pact libraries often regenerate random UUIDs, timestamps, or metadata in contract JSON even when the actual contract hasn't changed
- Run `make normalize-pacts` (if available) after sync to replace generated values with deterministic placeholders
- If no normalizer exists, inspect the diff — if only generated IDs changed, the sync can be skipped or the noise committed as-is

### Multi-service run: consumer failure
- If any consumer fails during `full all`, **stop immediately** — do not sync or verify
- Fix the failing consumer test, then restart the `full` run
- Syncing with partial/stale pacts risks overwriting good provider copies and causing cascading false failures

### Missing contracts
- A consumer-provider relationship exists in code but no contract file found
- Create consumer contract tests first, then run `full`

## Adapting to a New Project

This skill works with any project that follows the consumer-driven contract pattern. To adopt it in a new project:

1. **Add Makefile targets** for consistency:
   ```makefile
   test-contract:
   	@echo "Running contract tests..."
   	# Your test command filtered to contract tests

   pact-publish:
   	@echo "Publishing contracts to providers..."
   	# cp commands to copy contracts to provider services
   ```

2. **Organize contract files**:
   - Consumer output: `target/pacts/` or `contracts/output/`
   - Provider input: `test/resources/pacts/` or `contracts/input/`

3. **Name contract files** consistently:
   `<consumer>-consumer-<provider>-provider.json`

4. **Tag contract tests** so they can be run independently of unit tests

## Rules

- NEVER skip contract tests when modifying connectors or API interfaces
- ALWAYS sync contracts after generating — stale provider copies cause false failures
- ALWAYS verify on the provider side after syncing — sync alone doesn't prove compatibility
- ALWAYS normalize after syncing (if available) to keep diffs clean
- In multi-service runs: ALL consumers must pass before syncing — never sync partial results
- In multi-service runs: prefer root-level `make sync-pacts` over per-service `make pact-publish`
- Connectors are service boundary code — treat any change as a potential breaking contract change
- If a Makefile target exists, prefer it over raw commands
- Report clearly which consumer-provider pairs were tested and their pass/fail status
