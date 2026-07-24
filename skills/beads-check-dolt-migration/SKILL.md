---
name: beads-check-dolt-migration
description: "Detect whether a beads repository needs classic-to-Dolt migration or an in-place Dolt schema upgrade."
allowed-tools: "Read,Bash(bd:*),Bash(git:*),Bash(ls:*),Bash(test:*),Bash(cat:*)"
model-tier: economy
model: haiku
effort: medium
version: "1.1.0"
author: "flurdy"
---

# Beads Migration and Schema Check

Read-only detection of whether a repository needs classic-to-Dolt migration, a Dolt schema upgrade, or no action. Reports the current state without changing files, databases, remotes, or Git state.

## When to Use

- Before running `/beads-migrate-to-dolt`
- After upgrading `bd`, especially across a minor or major version
- When `bd` reports pending schema migrations or a remote migration gate
- When `bd` commands fail and the storage format or schema may be stale
- When onboarding to a repo with beads

## Instructions

### 1. Check for Beads Installation

```bash
ls -la .beads/ 2>/dev/null
```

If no `.beads/` directory exists, report "No beads installation found" and stop.

### 2. Detect Storage Format

On-disk inspection is authoritative:

```bash
# Classic format indicators
test -f .beads/beads.db && echo "FOUND: SQLite database"
test -f .beads/issues.jsonl && echo "FOUND: JSONL issues file"

# Dolt format indicators
test -d .beads/dolt && echo "FOUND: server-mode Dolt directory"
test -d .beads/embeddeddolt && echo "FOUND: legacy embedded-Dolt directory"
test -f .beads/metadata.json && cat .beads/metadata.json
```

`issues.jsonl` is not proof of classic storage: modern bd can export JSONL for interchange while Dolt remains authoritative.

### 3. Check Configuration, Remotes, and Worktrees

```bash
cat .beads/config.yaml 2>/dev/null
git worktree list 2>/dev/null
```

For a Dolt repository also run:

```bash
bd dolt status 2>&1 || true
bd dolt remote list 2>&1 || true
bd config get no-push 2>&1 || true
```

Look for:
- `sync.remote` or `sync.branch` in config
- A configured Dolt remote
- Worktrees at `.git/beads-worktrees/` from the classic sync mechanism

### 4. Check bd and Schema Compatibility

```bash
bd --version 2>/dev/null
bd migrate --inspect --json 2>&1 || true
```

Treat the inspection output as diagnostic even when it exits non-zero. On bd 1.1+, a remote-backed database with pending migrations intentionally refuses automatic migration and returns a `remote_migrate_gate`. Do not bypass that gate during this read-only check.

For classic data, optionally collect the legacy diagnostic too:

```bash
bd doctor --migration=pre 2>&1 || true
```

Do not trust `bd doctor` to classify storage: newer versions may inspect configured defaults rather than the files on disk, and embedded mode may not support it.

### 5. Classify and Report

| State | Indicators | Recommendation |
|-------|------------|----------------|
| **Classic** | `beads.db` exists, no Dolt directory | Full migration needed |
| **JSONL-only** | `issues.jsonl` exists, no SQLite or Dolt directory | Initialize Dolt and import |
| **Dolt, current** | Dolt directory exists, `bd migrate --inspect` reports no pending migrations | No migration needed |
| **Dolt, pending (local-only)** | Inspection reports pending migrations and no Dolt remote | Back up, then run the schema-upgrade path |
| **Dolt, pending (remote-backed)** | Inspection returns `remote_migrate_gate` | Choose exactly one designated clone to migrate and push; every other clone must adopt with `bd bootstrap` |
| **Partial/broken Dolt** | Dolt directory exists but `bd list` or `bd dolt status` fails | Diagnose and recover from backup or bootstrap; do not destroy data automatically |
| **No beads** | No `.beads/` directory | Run `bd init` only if the repo should use beads |

Include in the report:
- Current storage format and mode
- bd CLI version
- Current and target schema versions, when available
- Issue count, when readable
- Configured Dolt remote or sync branch
- Whether `no-push` is enabled and will require a one-command approved override
- Whether classic worktrees exist
- Any `remote_migrate_gate` and its two choices
- Clear recommendation: migrate classic data, upgrade schema here, adopt another clone, repair, or do nothing

## Remote-Backed Upgrade Safety

When bd 1.1+ reports pending schema migrations on a database with a remote:

- Never set `BD_ALLOW_REMOTE_MIGRATE=1` during this check.
- Ask the operator which single clone is the designated migrator.
- The designated clone backs up, runs `BD_ALLOW_REMOTE_MIGRATE=1 bd migrate`, verifies, then pushes.
- Ask for explicit permission immediately before `bd dolt push`.
- Other clones preserve any unpushed issues, then use `bd bootstrap` to adopt the published schema. They must not migrate independently because that forks schema history.

## Rules

- This skill is strictly read-only. Never modify files, databases, remotes, or Git state.
- Always preserve output from commands that may fail on old formats or a migration gate.
- Prefer on-disk evidence over backend defaults reported by old `bd doctor` versions.
- Never recommend independent schema migration on multiple clones of one Dolt remote.
