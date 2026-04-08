---
name: beads-migrate-to-dolt
description: "Migrate a beads installation from classic format (SQLite/JSONL on beads-sync worktree branch) to the new Dolt-based format."
allowed-tools: "Read,Grep,Glob,Bash(bd:*),Bash(git:*),Bash(cp:*),Bash(rm:*),Bash(mkdir:*),Bash(ls:*),Bash(cat:*),Bash(wc:*),Bash(pgrep:*),Bash(kill:*),Bash(sqlite3:*),Bash(python3:*),Bash(echo:*),AskUserQuestion"
version: "1.1.0"
author: "flurdy"
---

# Beads Migration: Classic to Dolt

Migrate a beads installation from the classic format (SQLite + JSONL with git worktree sync branch) to the modern Dolt-based format. This is a one-time migration that prioritizes safety through backups and pre-flight validation.

## When to Use

- Repository has `.beads/beads.db` (SQLite) but no `.beads/dolt/` directory
- Repository has `.beads/issues.jsonl` from the classic format without Dolt
- After upgrading `bd` CLI to v0.59.0+ which requires Dolt
- When `bd` commands fail with backend/database errors on an old installation

## Usage

```
/beads-migrate
```

## Prerequisites

- `bd` CLI v0.59.0+ installed
- `dolt` binary installed and on PATH (`brew install dolt`, or https://github.com/dolthub/dolt/releases)
- Git repository with existing `.beads/` directory containing classic format data
- The repo may have a `beads-sync` (or similar) branch used as a worktree for issue commits

## Instructions

### 0. Pre-Flight: Stop Legacy Daemons

Legacy `bd` (≤0.55.x) ran a background daemon per workspace that holds the SQLite WAL open. Stop them cleanly first, or WAL writes may be lost.

```bash
cat ~/.beads/registry.json 2>/dev/null
pgrep -af "bd daemon\|bd .* daemon" 2>/dev/null
```

For any daemon matching a `.beads/` workspace you're migrating, `kill -TERM <pid>` and wait a second. A graceful SIGTERM checkpoints the WAL into the main db on shutdown.

Verify after: `.beads/beads.db-wal` and `.beads/beads.db-shm` should be gone (absorbed into `beads.db`).

Note: if `bd` was uninstalled while the daemon was running, `/proc/<pid>/exe` points at a deleted binary — SIGTERM still works.

### 1. Detect Current State

**On-disk inspection is authoritative.** Do NOT trust `bd doctor` / `bd doctor --migration=pre` for this — on newer `bd` with classic data on disk, the doctor reports "Already using Dolt backend" because it checks the configured backend, not files. Use the checks below as the gate.

```bash
ls -la .beads/beads.db 2>/dev/null
ls -la .beads/issues.jsonl 2>/dev/null
ls -la .beads/dolt/ 2>/dev/null
cat .beads/metadata.json 2>/dev/null
cat .beads/config.yaml 2>/dev/null
git worktree list
```

If `beads.db` exists, also sanity-check that SQLite and JSONL are in sync (otherwise a later JSONL re-import may lose rows):

```bash
sqlite3 .beads/beads.db "SELECT COUNT(*) FROM issues"
wc -l .beads/issues.jsonl
```

If the counts differ, the SQLite db has unflushed writes. Normally a graceful daemon stop in step 0 fixes this; if not, the user needs to decide whether to trust JSONL or SQLite as source of truth.

Classify the state:

| State | Indicators | Action |
|-------|-----------|--------|
| **Classic** | `beads.db` exists, no `dolt/` dir | Full migration |
| **JSONL-only** | `issues.jsonl` exists, no `beads.db`, no `dolt/` | Init + import |
| **Already Dolt** | `dolt/` exists, metadata says `"backend": "dolt"` | Stop — no migration needed |
| **Partial** | `dolt/` exists but empty/broken, classic files remain | Resume migration |
| **No beads** | No `.beads/` directory | Stop — not a beads repo |

If **Already Dolt**: inform the user and suggest `bd doctor` if they have issues.
If **No beads**: inform the user and suggest `bd init` for a fresh installation.

### 2. Pre-Migration Validation

```bash
bd doctor --migration=pre
```

**Known false positive**: on bd 0.62.0+ with on-disk classic data, this prints "Already using Dolt backend" with `JSONL Count: 0`. Ignore it if step 1 classified the repo as Classic or JSONL-only — the doctor only looks at runtime config.

Otherwise, review the output for real blockers and stop if there are any.

### 3. Record Pre-Migration State

Capture current state for post-migration verification. `bd list` won't work on classic data from a newer bd, so read counts directly:

```bash
sqlite3 .beads/beads.db "SELECT COUNT(*) FROM issues" 2>/dev/null
wc -l < .beads/issues.jsonl 2>/dev/null
cat .beads/config.yaml 2>/dev/null
```

Note the issue count and `sync-branch` value from config.yaml.

### 4. Back Up Old Data

**This step is mandatory. Never skip it.**

```bash
mkdir -p .beads-migration-backup

cp .beads/beads.db .beads-migration-backup/ 2>/dev/null || true
cp .beads/issues.jsonl .beads-migration-backup/ 2>/dev/null || true
cp .beads/config.yaml .beads-migration-backup/ 2>/dev/null || true
```

Then try a structured JSONL backup:

```bash
bd backup
ls -la .beads/backup/
```

**This is expected to fail** on bd 0.62.0+ with classic data — `bd backup` errors out with "no beads database found" because the runtime backend is Dolt and there's no Dolt db yet. Continue anyway; the raw copies in `.beads-migration-backup/` are the real fallback and step 7 imports from `.beads/issues.jsonl` directly.

### 5. Remove Old Backend

Remove old database files and any stale locks to prepare for Dolt initialization:

```bash
rm -f .beads/beads.db .beads/beads.db-shm .beads/beads.db-wal
rm -f .beads/metadata.json
rm -f .beads/daemon.lock .beads/dolt-server.lock
```

**Do NOT remove:**
- `.beads/config.yaml` — contains sync-branch and team settings
- `.beads/backup/` — just created in step 4
- `.beads/issues.jsonl` — primary data source for step 7

### 6. Initialize Dolt Backend

```bash
bd init --force
```

The `--force` flag is needed because `.beads/` already exists.

**What `bd init --force` does and does NOT do:**
- Creates an empty Dolt database under `.beads/dolt/`, writes new `metadata.json`, starts a local Dolt sql-server on a random port
- Modifies `.gitignore` (adds Dolt-related entries) and creates `AGENTS.md` in the repo root — both will show up as modified/untracked in `git status` after migration
- Does **NOT** import `.beads/issues.jsonl` — it creates an *empty* database. Importing happens in step 7.

Verify initialization:

```bash
ls -la .beads/dolt/
cat .beads/metadata.json
```

Confirm metadata shows `"backend": "dolt"`.

### 7. Restore Data

**Preferred path** (works if step 4's `bd backup` succeeded, which it won't on classic data):

```bash
bd backup restore .beads/backup/
```

**Fallback path** (the actual path for classic-data migrations): import directly from the JSONL that step 5 preserved.

```bash
bd import .beads/issues.jsonl
```

Note: `.beads-migration-backup/` contains raw SQLite+JSONL copies, not the structured format `bd backup restore` expects — so don't try `bd backup restore .beads-migration-backup/`, it will fail.

**Schema mismatch: legacy `comments[].id` (int → string)**

If `bd import` errors with:

```
failed to parse issue from JSONL: json: cannot unmarshal number into Go struct field Comment.comments.id of type string
```

…the JSONL was written by a legacy bd (≤0.49.x era) that stored comment IDs as integers; newer bd expects strings. Transform the file and re-import:

```bash
python3 - <<'PY'
import json
src = ".beads/issues.jsonl"
dst = "/tmp/bd-issues-fixed.jsonl"
with open(src) as fh, open(dst, "w") as out:
    for line in fh:
        line = line.strip()
        if not line: continue
        d = json.loads(line)
        for c in d.get("comments") or []:
            if isinstance(c.get("id"), int):
                c["id"] = str(c["id"])
        out.write(json.dumps(d) + "\n")
print(f"wrote {dst}")
PY
bd import /tmp/bd-issues-fixed.jsonl
rm /tmp/bd-issues-fixed.jsonl
```

If a different schema error comes up (other fields flipping int↔string), apply the same pattern: locate the field, cast it, retry. Preserve the original `.beads-migration-backup/` throughout.

If import still fails after schema fixes, stop and report. The original data is safe in `.beads-migration-backup/`.

### 8. Verify Migration

Regenerate `.beads/issues.jsonl` from Dolt so the on-disk file matches the new schema (bd's auto-export doesn't always trigger immediately after an import):

```bash
bd export -o .beads/issues.jsonl
```

Note: `bd export` writes to stdout by default — `-o <file>` is required.

Then verify:

```bash
bd doctor --migration=post
bd list 2>&1 | wc -l
bd doctor
```

Compare the post-migration issue count with the pre-migration count from step 3. If counts don't match, warn the user with both numbers and ask whether to proceed or investigate.

`bd doctor --migration=post` may still report `JSONL Valid: false` as a stale sub-check even after a successful export — trust the full `bd doctor` output (0 errors) as the real signal.

### 9. Set Up Sync Branch

If config.yaml had a `sync-branch` value (found in step 3):

```bash
bd migrate sync <branch-name>
```

If no sync branch was configured, ask the user if they want one. For team projects, recommend it.

### 10. Clean Up Legacy Artifacts

Remove old format files and worktrees:

```bash
bd doctor --check=artifacts --fix
```

Check for and remove old beads worktrees:

```bash
git worktree list
```

If a beads worktree exists at `.git/beads-worktrees/<branch>/`:

```bash
git worktree remove .git/beads-worktrees/<branch-name>
```

If removal fails due to uncommitted changes, use `--force` and inform the user.

**Clear the legacy daemon registry**: `~/.beads/registry.json` is the per-user daemon discovery file used by bd ≤0.55.x. bd 0.62.0+ in Dolt mode doesn't use it, so any entries there are stale dead PIDs pointing at vanished SQLite files. On the last migrated repo for this user, clear it:

```bash
echo '[]' > ~/.beads/registry.json
```

### 11. Migration Backup Cleanup

Ask the user before removing the backup:

> Migration completed successfully. The backup is at `.beads-migration-backup/`. Would you like to keep it as a safety net, or remove it?

If user agrees:

```bash
rm -rf .beads-migration-backup/
```

### 12. Update Documentation

Search the repo for files containing outdated beads references:

```bash
grep -rl "bd sync\|bd daemon\|beads\.db\|sqlite\|\.jsonl" \
  .beads/PRIME.md CLAUDE.md AGENTS.md .claude/ docs/ README.md \
  2>/dev/null
```

Outdated patterns to look for:
- `bd sync` — removed in v0.59.0, Dolt handles sync natively
- `bd daemon` — removed, no background daemon in Dolt mode
- References to `beads.db`, `sqlite`, or `.jsonl` as the storage backend
- References to the old worktree-based sync mechanism
- Outdated `bd` subcommands or flags

For each file with matches, show the user the outdated lines and suggest replacements. Common files to check:
- `.beads/PRIME.md` — AI workflow context (most likely to have outdated commands)
- `CLAUDE.md` / `.claude/` — Claude Code project instructions
- `AGENTS.md` — agent configuration
- `README.md`, `docs/` — project documentation

### 13. Report

Summarize the migration:

- Previous format (Classic SQLite or JSONL-only)
- New format: Dolt
- Issues migrated: count
- Sync branch: configured name or "not configured"
- Artifacts cleaned: yes/no
- Migration backup: kept/removed

## Handling Edge Cases

- **JSONL-only (no SQLite)**: Skip the `beads.db*` removal in step 5. Step 7's fallback (`bd import .beads/issues.jsonl`) is already the correct path. Warn that events not captured in JSONL may be lost.
- **`bd backup` fails on old format**: Expected — step 7's fallback handles it.
- **Schema mismatch on import (`cannot unmarshal number into ... string`)**: Legacy bd wrote certain fields as ints that newer bd expects as strings. Comment IDs (`comments[].id`) are the known case — see the Python transform in step 7. Apply the same pattern for any other field that trips the import.
- **SQLite/JSONL count mismatch in step 1**: Classic daemons had unflushed WAL writes. Re-run step 0's graceful stop; if daemons are already dead, SQLite recovers the WAL on next open (run `sqlite3 .beads/beads.db ".recover"` or just let `bd init` do it).
- **Partial previous migration**: If `dolt/` exists but is empty or corrupt, remove it (`rm -rf .beads/dolt/`) and re-run `bd init --force`, then proceed with restore.
- **Issue count mismatch (post-migration)**: Common cause is infrastructure beads (agents, rigs) excluded from default export. Suggest re-exporting with `--all` flag.
- **Worktree removal fails**: Try `git worktree remove --force <path>`. If still fails, inform user for manual cleanup.
- **Multiple beads worktrees**: List all with `git worktree list`, identify beads-related ones (path contains `beads-worktrees`), remove each.
- **Config.yaml missing**: Proceed without sync branch setup. After migration, suggest `bd config set sync.branch <name>` if needed.
- **Daemon binary already deleted but process still running**: `brew uninstall` removes the on-disk binary but a running daemon keeps it mmap'd. `kill -TERM <pid>` still works; the daemon shuts down cleanly from the in-memory code.
- **Multiple repos to migrate**: Each workspace needs its own run (daemon stop → backup → remove → init → import → export → verify). The `~/.beads/registry.json` cleanup in step 10 only needs to happen once at the end.

## Rules

- Never skip the backup step (step 4). If backup fails, stop and inform the user.
- Never delete `.beads-migration-backup/` without user confirmation.
- Never proceed past verification failures without explicit user approval.
- Preserve `config.yaml` through the migration — it contains team settings.
- Always run `bd doctor --migration=post` before declaring success.
- If any step fails, stop and report the error. Do not force through.
