---
name: beads-migrate-to-dolt
description: "Safely migrate classic Beads data or upgrade a Dolt schema, preserving backups and remote history. Repository aftercare is a separate, explicitly selected mode."
allowed-tools: "Read,Grep,Glob,AskUserQuestion,Bash(~/.agents/skills/next/scripts/next-select stores:*),Bash(bd --version),Bash(bd migrate --help),Bash(bd init --help),Bash(bd import --help),Bash(bd export --help),Bash(bd bootstrap --help),Bash(bd backup --help),Bash(bd dolt stop --help),Bash(bd list --help),Bash(bd doctor --help),Bash(bd help init-safety),Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(git rev-parse:*),Bash(git worktree list:*)"
model-tier: premium
model: opus
effort: high
version: "2.0.0"
author: "flurdy"
---

# Beads Storage and Schema Migration

Own data preservation, conversion/schema upgrade, verification, and coordinated publication for
one explicitly selected repository. Do not install or upgrade tools during the run. Reading this
skill or editing it is not permission to migrate a database.

## Usage

```text
/beads-migrate-to-dolt [repository-path]
/beads-migrate-to-dolt --aftercare [repository-path]
```

Default mode runs the core steps below. `--aftercare` selects only the
[confirmed aftercare procedure](references/aftercare.md), not another migration.
Never enter aftercare automatically at the end of migration. Reject unknown/duplicate flags.

Read [version and capability evidence](references/compatibility.md) before either mode. It records
checked CLI help, not universal compatibility. Read `--help` before each version-sensitive command;
missing capabilities are a blocker, not permission to guess a flag or change the installed version.

## 1. Bind the target without opening a store

Read the repository's own rules and the [Beads baseline](../beads/SKILL.md). At a workspace root,
use `~/.agents/skills/next/scripts/next-select stores` for file-only repository discovery. Select
exactly one explicit absolute repository path as `ROOT`, matching its physical `.beads` location.
If selection is ambiguous, ask; never infer the target from an ID prefix or migrate every member.
Do not resolve a Bead ID before backup: the resolver's issue probes open databases. Resolve any
later tracker reads normally, after protection; they are not migration target discovery.

Inspect local files without opening the engine. Record only redaction-safe storage mode/path,
configured remote identity, and policy values; never dump full config or credential values.
Account for redirected or external storage, Git common directories, symlinks, shared servers,
and legacy worktree JSONL. A `.beads` copy alone cannot protect an external database.
`issues.jsonl` alone does not establish which backend is authoritative. No installation means stop,
not automatic `bd init`. Partial/unknown evidence is not permission to rebuild a store.

Every database command uses `bd -C "$ROOT"`; use the repository's Git wrapper where required.
Set `ROOT` and all other path variables to the proven absolute locations before using examples.
Use `--sandbox` on applicable local bd operations to disable configured auto-push, not to bypass
schema or permission guards. No mutating command is preapproved by this skill's tool declaration.
Show the scope and plan before local writes; immediately before every remote or destructive action,
obtain fresh approval with one visible command per confirmation. Never chain such actions.

## 2. Quiesce and verify a mandatory backup

Modern bd may auto-migrate on store open. Protect data before counts or schema inspection: do not
run list, export, SQL, doctor, bootstrap, or migration probes against an unprotected old store.

Coordinate **all writers** first, including other agents, clients, legacy SQLite daemons, and
embedded engine processes. Choose a version/mode-appropriate graceful quiesce operation. For a
proven project-managed server, the documented stop command is:

```bash
bd -C "$ROOT" --sandbox dolt stop
```

Verify shutdown and flush completion without reopening bd. Do not infer quiescence from a sleep,
PID file, or successful signal alone. A shared server or externally managed engine needs a
service-owner-approved consistent backup plan; never stop unrelated databases. If the quiesce
command itself might open/migrate the store, or a consistent snapshot cannot be proven, stop for
operator recovery. Never bypass a guard to obtain a backup.

Choose a private local `BACKUP_PARENT` outside the repository, active database roots and synced
folders. For a confirmed self-contained `.beads` store, an exclusive backup example is:

```bash
set -euo pipefail
umask 077
BACKUP=$(mktemp -d "$BACKUP_PARENT/beads-migration.XXXXXXXX")
cp -af "$ROOT/.beads/." "$BACKUP/beads"
```

Run each step with checked exit status; copy or verification failure is a hard stop.
Never overwrite a backup or suppress a copy error. Include the full physical engine data, branches, history,
working set, metadata/config, hooks, legacy SQLite WAL/SHM sidecars if present, and all candidate
JSONL/worktree sources. Add separately proven external roots to the backup manifest when applicable;
the example alone is insufficient for those topologies.

Verify file hashes, file types, permissions and symlink targets against the quiesced source, and
confirm the snapshot is readable and complete. Preserve original metadata; do not recursively change
backup file permissions. Record backup paths/digests, never record contents containing secrets.
Treat the verified backup as immutable: do not open it with bd or use it as an import destination.
Keep writers paused through verification. A failed attempt's backup is never reused or overwritten.

Create a separate private `WORK` directory for derived exports, comparisons and recovery experiments.
If baseline/recovery inspection needs backup data, use a working copy of the backup, never the sole
backup. Native `backup sync` can publish off-machine; it is not an automatic backup step. A configured
native backup may supplement, not replace, the verified fallback under separate destination approval.

## 3. Inspect the protected store

Only after step 2 succeeds, inspect using the target version and retain exit status plus bounded
output. Reuse the [detection vocabulary](../beads-check-dolt-migration/SKILL.md#5-classify-and-report),
not that skill's pre-backup store-opening probes.

```bash
bd -C "$ROOT" --readonly --sandbox migrate --inspect --json
```

A nonzero exit may describe `remote_migrate_gate`, not successful inspection. Do not swallow errors.
If the installed inspection path cannot guarantee nonmutation, inspect an isolated working copy
without live remote bindings, under a separately reviewed recovery plan. Unknown state stops here.

- Working Dolt with no pending migrations: report no migration needed; keep the backup.
- Working Dolt with pending migrations: path A, including the remote coordination decision.
- Proven classic SQLite or JSONL-only source: path B, after source reconciliation below.
- Partial or mixed Dolt is recovery, not permission to reinitialize. Preserve all stores and stop
  for a scoped recovery/adoption plan; never delete an engine directory based on a failed query.

### Record a comparable baseline

Before applying changes, record complete issue IDs/counts by status, dependencies, comments, labels,
and relevant non-issue data/history. On a version supporting these flags:

```bash
bd -C "$ROOT" --readonly --sandbox list --all --limit 0 --include-infra --include-templates --include-gates --json > "$WORK/pre-list.json"
bd -C "$ROOT" --readonly --sandbox export --all -o "$WORK/pre.jsonl"
```

Use structured JSON or read-only queries over a protected copy, not terminal glyph/summary counts.
`export --all` includes memories and infrastructure records; its line count is not an issue count.
JSONL is interchange, not a backup of Dolt tables/history/working sets. If a partial schema prevents
queries, preserve the exact errors and use a version-compatible read-only baseline from a copy.
Do not continue without an adequate baseline or reset the working set to make queries succeed.

For classic sources, compare SQLite, main-worktree JSONL and legacy-worktree JSONL by IDs, fields,
relationships and timestamps. Counts alone cannot prove equal content or establish source authority.
Read SQLite with a read-only connection on a consistent copy. WAL/SHM must be preserved; do not infer
that a missing WAL or the largest/newest-looking JSONL makes that source complete.

## 4. Apply exactly one core path

### A. Existing Dolt schema

For a remote-backed schema, the operator must designate **exactly one designated migrator**.
Other clones preserve unpushed data/history and wait to adopt the published result; they must not
independently apply schema migrations. Set no override until this coordination decision is explicit.

For local-only Dolt, after the approved local plan and verified backup:

```bash
bd -C "$ROOT" --sandbox migrate
```

For the designated remote-backed clone only, show and confirm the exact scoped override:

```bash
env BD_ALLOW_REMOTE_MIGRATE=1 bd -C "$ROOT" --sandbox migrate
```

Never use `migrate schema` to bypass the remote gate. Never reset/discard a dirty or partially
migrated working set. If a dirty-table guard blocks progress, preserve its error and snapshot.
A checkpoint requires inspection of the actual changed tables and separate approval; never blanket
stage tables, commit unexpected issue data, or run a raw-Dolt retry loop. An unproven checkpoint or
repeat failure stops for version-specific recovery rather than another automatic attempt.

### B. Classic SQLite/JSONL conversion

Preserve original sources and their verified backup throughout conversion.
Use a version-compatible exporter on a working copy for stale/missing JSONL.
Never use a fixed-field converter or guess field casts to make import succeed. Labels,
design/acceptance criteria, metadata, timestamps, dependencies, comments, priority 0 and custom
fields must not silently disappear. If a suitable exporter is absent,
stop for a separately reviewed lossless conversion with fixtures for the actual source schema.

Choose and approve the authoritative JSONL and expected records, with explicit handling of tombstones,
soft deletes, memories and unsupported historical fields. Do not pick whichever source imports cleanly.
Native Dolt `backup restore` cannot restore a raw SQLite copy; do not treat them as interchangeable.

Plan a fresh destination while keeping the old backend intact. If it must use the original path,
move the old backend aside to a distinct, verified retained location only after an exact scoped
confirmation; preserve team settings and source exports separately. Never recursively remove the old
store. Do not adopt existing remote Dolt history by importing classic JSONL over it: use the adoption
path below or stop for an operator merge plan. Remote uncertainty is not proof of remote absence.

For a proven fresh destination, help-supported integration suppression keeps aftercare separate:

```bash
bd -C "$ROOT" --sandbox init --non-interactive --skip-hooks --skip-agents
```

Review the expected initialization footprint before approval and inspect files/Git state afterward;
flags do not guarantee an empty Git diff or absence of an auto-commit. Do not repair integration here.
A refusal is not a reason to add `--reinit-local`, `--discard-remote` or a destroy token. Remote history
replacement is outside this migration procedure and requires a separate owner-approved recovery plan.

Preview the selected immutable source, then import only after reviewing the plan:

```bash
bd -C "$ROOT" --sandbox import --dry-run "$SOURCE_JSONL" --json
bd -C "$ROOT" --sandbox import "$SOURCE_JSONL" --json
```

Record created, updated and skipped IDs. Current import is an upsert with stale/tie handling; skipped
rows are not automatically successful copies. Never add `--allow-stale` or deduplication flags to
force a count to match. Prove the reason and obtain a separate scoped decision before overwriting
newer data. Schema/type errors stop for supported conversion, not guess-and-retry transformations.

## 5. Verify data before publication

Repeat protected schema inspection and the same structured baseline/export queries into distinct
post-migration files. Require no pending schema migrations, expected storage identity/mode, and a
clean intended Dolt working set; server-running status alone is not schema/data verification.

Compare issue IDs, statuses, dependencies, comments and labels by identity, not only totals. Compare
exportable field values including metadata, acceptance criteria, original timestamps and priority 0;
check memories/non-issue records separately. Spot-check representative issues with relationships and
comments. Preserve records the interchange format cannot represent in the retained raw backup and
report their limitation; unresolved required-field loss means incomplete migration, not success.

Verification mismatch is a hard stop; approval cannot turn it into success. Approval can authorize
investigation or a new recovery plan, never bypass counts, field fidelity or schema checks. Do not
re-import into a suspect store automatically. Keep all sources, backups and failure evidence.

## 6. Coordinated publication and adoption

For remote-backed migration, data verification is not publication. Record configured destination,
branch, `no-push` guard and local/remote commit identities without printing credentials. Require a
fresh destination check and explicit approval immediately before each push, pull, native backup sync,
or bootstrap that can publish data or replace local state. Migration approval is not remote approval.

A designated migrator publishes as a standalone approved action:

```bash
bd -C "$ROOT" dolt push
```

If `no-push: true` blocks it, stop. Only a new approval may authorize the one-command override below;
never persistently disable the guard:

```bash
env BD_NO_PUSH=false bd -C "$ROOT" dolt push
```

Verify the remote-tracking identity matches the intended local Dolt branch/commit; do not assume
Git `main` is the Dolt data branch. A successful command alone is insufficient publication evidence.

Adopters first protect local unpushed data and history using step 2. Preview the actual plan:

```bash
bd -C "$ROOT" --sandbox bootstrap --dry-run --json
```

Plain `--json` is not a dry-run. Inspect source/destination and local-work preservation. An existing
store may only validate rather than adopt newer history; do not assume bootstrap replaces it. If the
plan does not adopt the intended published revision, stop for supported version-specific recovery.
After a fresh explicit confirmation of a safe adoption plan:

```bash
bd -C "$ROOT" --sandbox bootstrap --yes
```

Verify the adopter's actual schema, data and published Dolt identity. Keep the fallback backup until
the remote and at least one verified adopter match; cleanup still needs its own later confirmation.

## 7. Report and stop

Report separately: source/target mode and CLI version; backup location/digests; baseline versus final
counts/field checks; local data verification; publication/adoption evidence or pending status; and
any integration observations needing optional aftercare. Local-only success requires verified data;
remote-backed completion additionally requires verified publication/adoption. Missing evidence stays
incomplete. Do not change tracker state, create commits or begin unrelated repairs from this report.

Retain backups by default. Offer the aftercare reference only as an optional, separately selected
follow-up; it does not redefine migration success or authorize any cleanup implicitly.
