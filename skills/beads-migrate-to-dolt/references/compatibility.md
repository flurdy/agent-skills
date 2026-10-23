# Version and capability evidence

There is **no version allowlist**. Use current capabilities and target-specific safety evidence,
not a version comparison, to decide whether a path is available. These are bounded snapshots:

| CLI | Evidence | Limits |
|---|---|---|
| bd 1.2.2 (Homebrew) | Historical version/help audit underlying the original examples | No live migration certification |
| bd 1.3.1 (Homebrew), 2026-10-23 | Installed CLI passed `make test-beads-migrate-cli`; `migrate legacy-sqlite --help` was also inspected | Help only; no database opened or representative migration exercised by these checks |

This is **command-surface evidence**, not a live migration certification, a compatibility range
promise, or proof that a preview cannot initialize storage. Actual mode, paths and side effects
must be verified for the target version/topology before stateful commands run.

## Path-specific capability audit

A newer or unlisted version is not automatically incompatible. Record its exact version and audit
only the selected path, including its protection and verification steps. A missing optional command
for another path does not block this one. The opt-in full CLI suite checks all documented surfaces;
a failure means that full snapshot is unavailable, not that every migration path is unsupported.

| Selected scope | Required evidence | On drift or absence |
|---|---|---|
| Every core path | Target qualification (`-C`), auto-push suppression (`--sandbox`), protected inspection (`migrate --inspect --json`), read-only comparable baseline/export and post-checks with complete record coverage | Stop the affected path unless an independently reviewed equivalent preserves every safety guarantee; never silently drop flags or records |
| Existing Dolt (A) | Installed migration semantics, actual mode/paths, remote gate and designated-migrator rules if remote-backed | Keep backup-first, unknown-state and coordination gates regardless of version; do not try alternate migration commands to bypass refusal |
| Classic conversion (B) | Lossless exporter for the actual source schema on a working copy; fresh init with integration suppression; explicit-source import preview and reconciliation | No ad hoc converter, destructive reinit or stale-overwrite workaround; stop if fidelity cannot be established |
| Remote publication/adoption | Current push destination/branch and non-force behavior; bootstrap preview and local-history preservation semantics | Missing safe adoption/publication leaves that stage incomplete; local verification is not remote completion |
| Selected aftercare only | Installed help and exact preview for the chosen action, e.g. `migrate hooks --dry-run --json` | Leave unsupported actions untouched; do not rerun migration or widen cleanup scope |

Help flag presence is necessary for these example spellings, not sufficient proof of semantics.
Review changed meanings against matching-version documentation or implementation before approving
stateful commands. Treat any store open as potentially migrating even if newer help omits that warning.
An unknown semantic effect blocks the affected operation; a higher version number does not waive it.

## Help-observed command surface

Run version/help commands without opening a database. The checked binary can still initialize
user-level config and event caches under HOME; help is not filesystem-pure. On 1.3.1,
`bd help init-safety` created `.beads/eventsData`, `.beads/machine-id` and `.config/bd/config.yaml`
in the isolated HOME. A `.beads` directory there alone is not evidence of a database.
The optional test isolates HOME from its separate empty cwd and checks that no repository database
directory is created; it does not certify every possible filesystem side effect.
Record the exact installed version and relevant flags in private run evidence; never switch binaries
mid-run. The table records help-advertised behavior, not a guarantee exercised by the CLI test.
The test checks command identity and declared flags, not incidental wording or behavioral correctness.
A missing required command/flag or conflicting semantic evidence stops that path rather than silently
dropping a safety flag.

| Evidence command | Checked contract / implication |
|---|---|
| `bd --version` | Identifies the binary used for all following evidence. |
| `bd --help` | Check global `-C`/`--directory`, `--readonly`, `--sandbox` and `--json`; confirm the intended safety semantics separately. |
| `bd migrate --help` | `--inspect`, `--json`, `--dry-run`; preserve diagnostic errors, not assumed success. |
| `bd migrate schema --help` | Schema migrations also run automatically on store open; backup precedes store-opening probes. |
| `bd init --help` | `--non-interactive`, `--reinit-local`, `--skip-hooks`, `--skip-agents`, `--from-jsonl`, and server options exist. Suppression flags reduce integration work, not all side effects. |
| `bd help init-safety` | `--force` is a deprecated local-reinit alias. `--reinit-local` does not authorize remote divergence. `--discard-remote` plus a noninteractive destroy token permits history replacement on the next push; not part of routine migration. |
| `bd migrate legacy-sqlite --help` | Optional exporter advertised by 1.3.1: `--source-db` reads an authenticated legacy SQLite source, `--output` selects JSONL output. Help-only evidence; source eligibility and field fidelity still need proof on a working copy. Absence is not a blocker when another lossless exporter is available. |
| `bd import --help` | Explicit source, `--dry-run`, structured output, upsert semantics, stale/tie skips, `--allow-stale`. Skips/overwrites must be reconciled, not hidden with retries. |
| `bd export --help` | `--all` includes infrastructure records and memories; `-o` writes JSONL. Does not back up Dolt history, branches, working sets or all non-issue tables. |
| `bd list --help` | `--all --limit 0 --json` plus `--include-infra`, `--include-templates`, `--include-gates` for comparable issue coverage. Defaults can omit rows; do not count terminal glyphs. |
| `bd backup --help` | Native init/status/sync/restore/remove command group. Sync can push off-machine. A raw SQLite directory is not a native backup destination. |
| `bd bootstrap --help` | `--dry-run` previews; `--json` only formats output; `--yes` skips the apply prompt. Existing databases may only be validated, so verify the actual adoption plan and result. |
| `bd dolt stop --help` | Gracefully stops a managed project server; subsequent bd commands may restart it. This does not prove safe quiescence for an external/shared/embedded engine. |
| `bd dolt push --help` | Publishes to a configured remote; 1.3.1 also advertises remote derivation with consent when none exists. Verify the actual existing destination; no automatic adoption, force or remote change is authorized. |
| `bd migrate hooks --help` | Separate `--dry-run` and `--apply` modes; hook aftercare is not data migration. |
| `bd doctor --help` | Current help exposes migration and selected-check diagnostics. Do not carry forward the blanket old embedded-mode skip. It is supplemental evidence, never a substitute for data reconciliation. |

Current init and dolt help disagree about default embedded/server operation. The mode must be observed
from the actual installation, not guessed from those defaults or a version number. Protect every
physical data location, including custom/shared-server paths; `.beads/dolt/` and
`.beads/embeddeddolt/` are possible historical layouts, not a complete inventory.

`--from-jsonl` uses configured `import.path`, not an arbitrary positional source path. The core
procedure deliberately keeps explicit initialization and import preview separate so the selected
source and its outcomes remain reviewable. `bd migrate sync --help` advertises `--dry-run`, not
`--yes`; changing sync configuration is not an automatic migration step. Preserve existing team
settings and distinguish a Dolt data branch from the Git trunk branch.

The remote migration gate and the one-command `BD_ALLOW_REMOTE_MIGRATE` / `BD_NO_PUSH` overrides
remain coordination rules, not permission to bypass guards while inspecting. Recheck installed
behavior and destination identity before using them; a CLI upgrade never designates a migrator.

## Historical observations — not freshly certified

- **0.59–0.63 server mode:** old workflows described `.beads/dolt/`, legacy doctor sub-check false
  positives and incomplete server/monitor initialization. Do not replay their delete/reinit recipes.
- **1.0 embedded mode:** old reports described `.beads/embeddeddolt/`, unavailable doctor diagnostics,
  auto-generated integration commits and comment-ID format changes. None establishes current behavior.
- **1.1:** remote schema coordination, bootstrap and native backup groups were documented; a fixed
  schema number is not a durable target. Use current inspection after the mandatory backup.
- **1.2.2 → bd 1.3.0 (v53 → v66, observed 2026-09):** the new binary could not read the old schema,
  even with `--readonly --ignore-schema-skew` (missing `leases` table), so the pre-migration baseline
  came from raw `dolt sql` over a copy of the verified backup. The migration regenerated comment and
  event IDs without changing their content, added `events` to `dolt_ignore`, and made server-mode
  inspection require a running server. Until the migrated schema was pushed, every `bd dolt pull`
  failed with `local changes would be stomped by merge: events`, even with no remote changes to merge.
- **Classic SQLite/JSONL:** old exporters varied in fields and tombstone handling. If no matching
  exporter can preserve the actual data on a copy, stop for reviewed conversion rather than use a
  short field allowlist, guessed timestamp normalization or arbitrary int/string casts.

No blanket version upgrade, storage-mode conversion, old Husky fix or installer command is part of
this skill. Unknown versions need their own capability audit before executing the selected path,
and representative disposable-data migration tests before claiming end-to-end compatibility.
Those tests are a certification requirement, not permission to run experiments automatically or a
blanket version gate. A help-checked version remains untested end-to-end unless migration evidence
exists. Disclose that limitation in remote designated-migrator approval and the final report. Never
promote a version into migration-tested status merely because this help suite or one run succeeds.

## Repository verification

- `make test-beads-migrate` runs database-free instruction contracts and help-parser fixtures in
  the normal gate. Fixtures reject parent-command fallback, unknown topics, prefix matches and
  flags mentioned only in prose; harmless help-description changes are accepted.
- `make test-beads-migrate-cli` is an opt-in version/help check in a temporary empty directory;
  it never invokes a live migration or opens the user's database. A missing bd is reported as skipped.
  It audits the full example surface, not the optional legacy exporter, and never certifies semantics.
  Semantic review and any path-specific exceptions must still be recorded explicitly.
- `make check` remains the full repository gate. Neither contract nor help tests certify data fidelity
  on a live or historical database; a real migration must satisfy the core runbook's verification.
