---
name: contract-test
description: "Execute existing Pact-lite consumer generation, local sync, normalization and provider verification in an explicit scope. Status delegates to contract-check; setup and repairs are separate."
allowed-tools: "Read,Grep,Glob,Skill(contract-check),AskUserQuestion"
model-tier: premium
model: opus
effort: high
version: "3.0.0"
author: "flurdy"
---

# Contract Test — Pact-Lite Runner

Run existing project-owned contract commands. Pact-lite exchanges JSON contracts through local
files, without a broker. This skill owns execution, not health auditing, adoption, scaffolding,
application/test repair, Git commits or publication. Project-facing integration belongs to the
[separately authorized setup contract](../contract-check/references/project-setup.md).

No build or mutation command is preapproved by this skill's tool declaration. Explicit run intent
selects phases; harness permissions, repository ownership and confirmation rules still apply.

## Usage and phase boundaries

```text
/contract-test                    # current service's existing contract target; ask if ambiguous
/contract-test consumer           # generate for current consumer only
/contract-test sync               # copy current consumer's existing output only
/contract-test provider           # verify current provider's existing input only
/contract-test full               # current consumer → affected providers
/contract-test full all           # all declared consumers → all declared providers
/contract-test full <svc> ...     # named consumers → their affected providers
/contract-test status             # compatibility alias, read-only
```

`consumer stops after generation`; `sync stops after copying`; `provider` stops after verification.
Only `full` sequences generation → sync → optional normalization → verification. Standalone sync
neither regenerates nor normalizes files and never implies compatibility. Reject other arguments.

## Status compatibility alias

Delegate `/contract-test status` wholly to `/contract-check status`, including its rendering and
unknown/error semantics. Use `Skill(contract-check)` or read
`~/.agents/skills/contract-check/SKILL.md` and follow it. If the authority is missing or unavailable,
stop with unavailable status; do not reconstruct health evidence or run tests as a fallback.

## Preflight each run

1. Read the owning repository instructions and actual project topology. Resolve the service and
   requested roles from existing documentation, test suites and recipes. A service may have both
   roles; do not guess which target runs consumer versus provider tests.
2. Discover and **inspect** existing Makefile targets, package scripts or documented native commands,
   including delegated scripts and hooks. Target names and language detection alone are not proof
   of command behavior. In particular, `pact-publish` may contact a broker: only verified local copy
   commands belong to this runner. Network publication, deploys, dependency installation and setup
   require a separate handoff, not an expanded run.
3. Identify exact input/output paths, expected pairs, normalization behavior and affected provider
   repositories. Reuse project relationship evidence and the audit's matrix when needed; do not
   recreate a staleness, CI-coverage or health collector here.
4. Show the execution plan: repository paths, ordered commands, phases, write destinations and
   affected consumer/provider pairs. Proceed only within explicit task ownership. Confirm any
   unresolved expansion or overwrite decision before executing it. A request for one consumer does
   not authorize unrelated services or repairs.

Do not broaden a named-consumer run to a whole-project sync or normalization target silently.
Use an inspected scope-aware command, or stop and ask for explicit expansion to the named additional
repositories/paths. The same rule applies to a single-service full run. If the project cannot
isolate consumer generation from provider verification, do not pretend it meets full-run ordering;
request a separate integration change or a supported, explicitly scoped workflow.

## Execute the selected phases

### Generate

Run the inspected consumer command in each selected consumer's directory, sequentially unless the
project proves independent resources. ALL selected consumers must succeed before sync.

Check the command's actual test selection/results and expected contract outputs. A recent mtime,
existing file, or green command that skipped the intended tests is not proof of fresh generation.
Stop on failure, missing expected output, or uncertain selection; do not sync partial/stale results.
Do not edit consumer tests to make the run pass. Consumer-only execution ends here.

### Sync

Immediately before sync, reuse `/contract-check uncommitted` for destination-pact preservation;
never duplicate its Git health checks. Also inspect the exact destination diffs to understand
potential overwrites. Unknown audit evidence or unreviewed local changes means stop, not overwrite.
The user must explicitly select how to preserve changes and confirm the exact overwrite scope;
a run request is not permission to discard unrelated work.

Run only the preflighted local sync command for the authorized pairs. Compare expected source and
destination contents before treating copy as complete. Do not invent wildcard copies or delete
old pacts. Standalone sync ends after the copy report.

### Normalize (full only, when supported)

If the inspected project provides normalization, run it only within the authorized destinations.
Record that it changes files; inspect its transformations rather than assuming every UUID/date is
noise. No normalizer means an explicitly reported omitted phase, not permission to install one.
Stop on normalization failure; do not claim a completed full workflow.

### Verify

After all required generation, copying and normalization succeeds, run the inspected verification
command for every affected provider (`full all`: every declared provider). Confirm the intended
consumer set was exercised. A command selecting zero relevant tests is not verification.
Provider-only execution uses current inputs; it does not imply they were generated or synced now.
Stop on a provider failure, name completed/not-run pairs, and hand diagnosis/repairs to a separately
requested coding workflow. Never change the API or weaken a contract merely to make this run green.

## Report execution, not health

Render phases and consumer/provider pairs with PASS/FAIL/UNKNOWN/NOT-RUN, the command and evidence
actually observed, files changed, and any unexecuted phases. Retain partial results and the exact
failed command; do not retry after repairs automatically. A full success requires every planned
phase and expected pair. No commits, pushes, tracker writes or setup changes follow automatically.

For staleness, sync gaps, CI configuration or broader health questions, point to `/contract-check`.
These remain owned by the audit even when requested during an execution workflow.
