# Version and capability evidence

The examples were checked against **bd 1.2.2** (Homebrew) using version/help output only. This is
**command-surface evidence**, not a live migration certification, a compatibility range promise,
or proof that a preview cannot initialize storage. Actual mode, paths and side effects must be
verified for the target version/topology before stateful commands run.

## Current command surface

Run version/help commands without opening a database. The checked binary can still initialize
user-level config and event caches under HOME; help is not filesystem-pure. The optional test isolates
HOME from its separate empty cwd and checks that no repository database directory is created.
Record the exact installed version and relevant flags in private run evidence; never switch binaries mid-run. A missing command/flag or
conflicting evidence stops that path rather than silently dropping a safety flag.

| Evidence command | Checked contract / implication |
|---|---|
| `bd --version` | Identifies the binary used for all following evidence. |
| `bd migrate --help` | `--inspect`, `--json`, `--dry-run`; preserve diagnostic errors, not assumed success. |
| `bd migrate schema --help` | Schema migrations also run automatically on store open; backup precedes store-opening probes. |
| `bd init --help` | `--non-interactive`, `--reinit-local`, `--skip-hooks`, `--skip-agents`, `--from-jsonl`, and server options exist. Suppression flags reduce integration work, not all side effects. |
| `bd help init-safety` | `--force` is a deprecated local-reinit alias. `--reinit-local` does not authorize remote divergence. `--discard-remote` plus a noninteractive destroy token permits history replacement on the next push; not part of routine migration. |
| `bd import --help` | Explicit source, `--dry-run`, structured output, upsert semantics, stale/tie skips, `--allow-stale`. Skips/overwrites must be reconciled, not hidden with retries. |
| `bd export --help` | `--all` includes infrastructure records and memories; `-o` writes JSONL. Does not back up Dolt history, branches, working sets or all non-issue tables. |
| `bd list --help` | `--all --limit 0 --json` plus `--include-infra`, `--include-templates`, `--include-gates` for comparable issue coverage. Defaults can omit rows; do not count terminal glyphs. |
| `bd backup --help` | Native init/status/sync/restore/remove command group. Sync can push off-machine. A raw SQLite directory is not a native backup destination. |
| `bd bootstrap --help` | `--dry-run` previews; `--json` only formats output; `--yes` skips the apply prompt. Existing databases may only be validated, so verify the actual adoption plan and result. |
| `bd dolt stop --help` | Gracefully stops a managed project server; subsequent bd commands may restart it. This does not prove safe quiescence for an external/shared/embedded engine. |
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
- **Classic SQLite/JSONL:** old exporters varied in fields and tombstone handling. If no matching
  exporter can preserve the actual data on a copy, stop for reviewed conversion rather than use a
  short field allowlist, guessed timestamp normalization or arbitrary int/string casts.

No blanket version upgrade, storage-mode conversion, old Husky fix or installer command is part of
this skill. Unknown versions need their own capability audit and representative disposable-data
migration tests before claiming end-to-end compatibility.

## Repository verification

- `make test-beads-migrate` runs database-free instruction contracts in the normal gate.
- `make test-beads-migrate-cli` is an opt-in version/help check in a temporary empty directory;
  it never invokes a live migration or opens the user's database. A missing bd is reported as skipped.
- `make check` remains the full repository gate. Neither contract nor help tests certify data fidelity
  on a live or historical database; a real migration must satisfy the core runbook's verification.
