---
name: beads-migrate-to-dolt
description: "Migrate a beads installation from classic format (SQLite/JSONL on beads-sync worktree branch) to the new Dolt-based format."
allowed-tools: "Read,Grep,Glob,Bash(bd:*),Bash(git:*),Bash(cp:*),Bash(rm:*),Bash(mkdir:*),Bash(ls:*),Bash(cat:*),Bash(wc:*),AskUserQuestion"
version: "1.0.0"
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
- `dolt` binary installed and on PATH
- Git repository with existing `.beads/` directory containing classic format data
- The repo may have a `beads-sync` (or similar) branch used as a worktree for issue commits

## Instructions

### 1. Detect Current State

Determine what format the repository is currently using:

```bash
ls -la .beads/beads.db 2>/dev/null
ls -la .beads/issues.jsonl 2>/dev/null
ls -la .beads/dolt/ 2>/dev/null
cat .beads/metadata.json 2>/dev/null
cat .beads/config.yaml 2>/dev/null
git worktree list
```

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

Review the output for blocking issues. If there are blockers, report them and stop.

### 3. Record Pre-Migration State

Capture current state for post-migration verification:

```bash
bd list --all --json 2>/dev/null | wc -l
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

Then create a structured JSONL backup:

```bash
bd backup
ls -la .beads/backup/
```

If `bd backup` fails (old format incompatible with current CLI), warn the user. The raw copies in `.beads-migration-backup/` serve as the fallback.

### 5. Remove Old Backend

Remove old database files to prepare for Dolt initialization:

```bash
rm -f .beads/beads.db
rm -f .beads/metadata.json
```

**Do NOT remove:**
- `.beads/config.yaml` — contains sync-branch and team settings
- `.beads/backup/` — just created in step 4
- `.beads/issues.jsonl` — fallback data source

### 6. Initialize Dolt Backend

```bash
bd init --force
```

The `--force` flag is needed because `.beads/` already exists.

Verify initialization:

```bash
ls -la .beads/dolt/
cat .beads/metadata.json
```

Confirm metadata shows `"backend": "dolt"`.

### 7. Restore Data

Import backed-up data into the new Dolt database:

```bash
bd backup restore .beads/backup/
```

If that fails, try the migration backup:

```bash
bd backup restore .beads-migration-backup/
```

If both fail, inform the user. The backup files are preserved in `.beads-migration-backup/` for manual recovery.

### 8. Verify Migration

```bash
bd doctor --migration=post
bd list --all --json 2>/dev/null | wc -l
bd doctor
```

Compare the post-migration issue count with the pre-migration count from step 3. If counts don't match, warn the user with both numbers and ask whether to proceed or investigate.

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

- **JSONL-only (no SQLite)**: Skip step 5 removal of `beads.db`. Otherwise same flow.
- **`bd backup` fails on old format**: Fall back to raw file copies. Warn user that events, comments, and labels may not be preserved if only `issues.jsonl` is available.
- **Partial previous migration**: If `dolt/` exists but is empty or corrupt, remove it (`rm -rf .beads/dolt/`) and re-run `bd init --force`, then proceed with restore.
- **Issue count mismatch**: Common cause is infrastructure beads (agents, rigs) excluded from default export. Suggest re-exporting with `--all` flag.
- **Worktree removal fails**: Try `git worktree remove --force <path>`. If still fails, inform user for manual cleanup.
- **Multiple beads worktrees**: List all with `git worktree list`, identify beads-related ones (path contains `beads-worktrees`), remove each.
- **Config.yaml missing**: Proceed without sync branch setup. After migration, suggest `bd config set sync.branch <name>` if needed.

## Rules

- Never skip the backup step (step 4). If backup fails, stop and inform the user.
- Never delete `.beads-migration-backup/` without user confirmation.
- Never proceed past verification failures without explicit user approval.
- Preserve `config.yaml` through the migration — it contains team settings.
- Always run `bd doctor --migration=post` before declaring success.
- If any step fails, stop and report the error. Do not force through.
