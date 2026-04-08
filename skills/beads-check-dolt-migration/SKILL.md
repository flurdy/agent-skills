---
name: beads-check-dolt-migration
description: "Detect whether a beads installation needs migration from classic format (SQLite/JSONL) to Dolt."
allowed-tools: "Read,Bash(bd:*),Bash(git:*),Bash(ls:*),Bash(test:*),Bash(cat:*)"
version: "1.0.0"
author: "flurdy"
---

# Beads Migration Check

Read-only detection of whether a repository's beads installation needs migration to Dolt. Reports the current state and recommends next steps without making any changes.

## When to Use

- Before running `/beads-migrate-to-dolt` to understand what's needed
- When `bd` commands fail and you suspect a format mismatch
- As a diagnostic when onboarding to a repo with beads

## Usage

```
/beads-check-migration
```

## Instructions

### 1. Check for Beads Installation

```bash
ls -la .beads/ 2>/dev/null
```

If no `.beads/` directory exists, report "No beads installation found" and stop.

### 2. Detect Storage Format

Check for indicators of each format:

```bash
# Classic format indicators
test -f .beads/beads.db && echo "FOUND: SQLite database"
test -f .beads/issues.jsonl && echo "FOUND: JSONL issues file"

# Dolt format indicators
test -d .beads/dolt && echo "FOUND: Dolt database directory"
test -f .beads/metadata.json && cat .beads/metadata.json
```

### 3. Check Sync Branch and Worktrees

```bash
cat .beads/config.yaml 2>/dev/null
git worktree list 2>/dev/null
```

Look for:
- `sync-branch` setting in config.yaml
- Worktrees at `.git/beads-worktrees/` (classic sync mechanism)

### 4. Check bd CLI Compatibility

```bash
bd --version 2>/dev/null
bd doctor --migration=pre 2>&1 || true
```

### 5. Classify and Report

Based on findings, classify the state and report:

| State | Indicators | Recommendation |
|-------|-----------|----------------|
| **Classic** | `beads.db` exists, no `dolt/` | Migration needed — run `/beads-migrate-to-dolt` |
| **JSONL-only** | `issues.jsonl` exists, no `beads.db`, no `dolt/` | Migration needed — run `/beads-migrate-to-dolt` |
| **Already Dolt** | `dolt/` exists, metadata says `"backend": "dolt"` | No migration needed |
| **Partial** | `dolt/` exists but empty/broken, classic files remain | Migration incomplete — run `/beads-migrate-to-dolt` to resume |
| **No beads** | No `.beads/` directory | Not a beads repo — run `bd init` for fresh installation |

Include in the report:
- Current format detected
- bd CLI version
- Whether sync branch is configured (and branch name)
- Whether classic worktrees exist
- Any warnings from `bd doctor --migration=pre`
- Clear recommendation (migrate, no action needed, or init)

## Rules

- This skill is strictly read-only. Never modify files, databases, or git state.
- Always run `bd doctor --migration=pre` output through error handling — it may fail on old formats.
- Report findings clearly so the user can decide whether to proceed with migration.
