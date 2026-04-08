---
name: contract-test
description: Run consumer-driven contract tests (pact-lite, no broker). Guides through generating, syncing, and verifying contracts between services.
version: "1.0.0"
author: "flurdy"
---

# Contract Test (Pact-Lite)

Consumer-driven contract testing without a broker. Contracts are JSON files exchanged directly between consumer and provider services via the filesystem.

## When to Use

- After modifying a **connector**, **API client**, or **endpoint interface** (request/response models, URLs, headers)
- When adding a **new REST endpoint** that other services will consume
- To verify contracts haven't broken after upstream/downstream changes
- When a consumer or provider test is failing and you need to re-sync contracts

## Usage

```
/contract-test                     # Auto-detect: run contract tests for current service
/contract-test consumer            # Run consumer tests to generate contract files
/contract-test sync                # Copy generated contracts to provider services
/contract-test provider            # Run provider verification against current contracts
/contract-test full                # Consumer + sync + provider (end-to-end)
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

1. **Identify the current service** — check the working directory or ask the user
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

4. **Determine service role**:
   - Look for consumer test files: `*Consumer*.{scala,java,ts,js,go,py,rs}`, `*Pact*.{...}`
   - Look for provider verification files: `*Verify*Pact*`, `*Provider*Verify*`
   - Check for contract output directory: `target/pacts/`, `pacts/`, `contracts/`
   - Check for contract input directory: `test/resources/pacts/`, `src/test/resources/pacts/`, `contracts/`

### Step 1: Generate Contracts (Consumer Side)

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

### Step 2: Sync Contracts to Providers

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

### Step 3: Verify Contracts (Provider Side)

Navigate to each affected provider service and run verification:

```bash
cd ../<provider-service>
make test-contract

# Or run provider-specific verification tests
# Look for test files named VerifyConsumerPacts, *ProviderVerify*, etc.
```

### Step 4: Report Results

After running, report:
- Which contracts were generated/synced/verified
- Any failures with clear indication of which consumer-provider pair failed
- Suggestions for fixing broken contracts

## Subcommand Details

### `consumer`
Run consumer contract tests. Generates contract files but does not sync or verify.

### `sync`
Copy existing contract files from consumer output directories to provider input directories. Does not run any tests.

### `provider`
Run provider verification tests. Assumes contracts are already synced.

### `full`
Run the complete workflow: consumer -> sync -> provider (all affected providers).

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
- Pact libraries often regenerate random IDs, timestamps, or metadata in contract JSON even when the actual contract hasn't changed
- This causes git diffs on synced files that are just noise
- Inspect the diff to confirm — if only generated IDs changed, the sync can be skipped or the noise committed as-is
- Projects can add normalization (sort keys, strip IDs) to their `pact-publish` Makefile target if they know their exact Pact format, but this skill does not attempt it automatically since it varies by language and library

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
- Connectors are service boundary code — treat any change as a potential breaking contract change
- If a Makefile target exists, prefer it over raw commands
- Report clearly which consumer-provider pairs were tested and their pass/fail status
