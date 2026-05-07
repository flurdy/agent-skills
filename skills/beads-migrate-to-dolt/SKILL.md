---
name: beads-migrate-to-dolt
description: "Migrate a beads installation from classic format (SQLite/JSONL on beads-sync worktree branch) to the new Dolt-based format."
allowed-tools: "Read,Grep,Glob,Bash(bd:*),Bash(git:*),Bash(cp:*),Bash(rm:*),Bash(mkdir:*),Bash(ls:*),Bash(cat:*),Bash(wc:*),Bash(pgrep:*),Bash(kill:*),Bash(sqlite3:*),Bash(python3:*),Bash(echo:*),Bash(brew:*),AskUserQuestion"
version: "1.2.0"
author: "flurdy"
---

# Beads Migration: Classic to Dolt

Migrate a beads installation from the classic format (SQLite + JSONL with git worktree sync branch) to the modern Dolt-based format. This is a one-time migration that prioritizes safety through backups and pre-flight validation.

## bd Version Compatibility

This skill has been validated against:
- **bd 0.59.x – 0.63.x** (server-mode Dolt: `.beads/dolt/` with a sql-server)
- **bd 1.0.x** (embedded Dolt: `.beads/embeddeddolt/`, no separate server) — **recommended**

Notable differences in **bd 1.0+** that change the migration flow:
- Default storage is `.beads/embeddeddolt/`, not `.beads/dolt/`
- `bd doctor` prints "not yet supported in embedded mode" — fall back to `bd list` counts + round-trip `bd export`
- `bd doctor --migration=pre|post` likewise unavailable; trust on-disk inspection and counts
- `bd sync` is removed; the replacements are `bd dolt push|pull|commit|status`
- `bd init` auto-commits a chunk of files (see step 6) — be prepared to revert if unwanted
- `bd init` runs interactive prompts — pass `--non-interactive` (or set `BD_NON_INTERACTIVE=1`) when running through automation

## When to Use

- Repository has `.beads/beads.db` (SQLite) but no `.beads/dolt/` or `.beads/embeddeddolt/` directory
- Repository has `.beads/issues.jsonl` from the classic format without Dolt
- After upgrading `bd` CLI to v0.59.0+ which requires Dolt
- When `bd` commands fail with backend/database errors on an old installation
- **Partial migration**: `.beads/dolt/` exists with a running sql-server but the database it expects (e.g. `beads`) is missing — `bd list` returns "database not found"

## Usage

```
/beads-migrate
```

## Prerequisites

- `bd` CLI installed. **Recommended: 1.0.3+** (`brew upgrade bd`). Earlier 0.59–0.63 also work but expose `bd doctor` paths the skill no longer relies on.
- `dolt` binary on PATH only required for **server-mode** (bd ≤0.63). bd 1.0+ embedded mode bundles its own Dolt engine.
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

**On-disk inspection is authoritative.** Do NOT trust `bd doctor` / `bd doctor --migration=pre` for this — on newer `bd` with classic data on disk, the doctor reports "Already using Dolt backend" because it checks the configured backend, not files. On bd 1.0 in embedded mode, `bd doctor` outright refuses to run. Use the checks below as the gate.

```bash
bd --version
ls -la .beads/beads.db 2>/dev/null
ls -la .beads/issues.jsonl 2>/dev/null
ls -la .beads/dolt/ 2>/dev/null            # bd 0.59–0.63 server mode
ls -la .beads/embeddeddolt/ 2>/dev/null    # bd 1.0+ embedded mode
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

**Worktree-cached JSONL is often newer than `.beads/issues.jsonl` in main.** When the classic worktree at `.git/beads-worktrees/<branch>/` exists, also check `wc -l .git/beads-worktrees/<branch>/.beads/issues.jsonl` — that file usually has the last `bd sync` snapshot, which can be more recent than the empty/stale JSONL in the main worktree.

Classify the state:

| State | Indicators | Action |
|-------|-----------|--------|
| **Classic** | `beads.db` exists, no `dolt/` or `embeddeddolt/` dir | Full migration |
| **JSONL-only** | `issues.jsonl` exists, no `beads.db`, no Dolt dir | Init + import |
| **Already Dolt (server)** | `dolt/` exists, metadata says `"backend": "dolt"`, server reachable | Stop — no migration needed |
| **Already Dolt (embedded)** | `embeddeddolt/` exists, metadata `"dolt_mode": "embedded"`, `bd list` works | Stop — no migration needed |
| **Partial (server)** | `dolt/` exists but empty or sql-server says `database "<name>" not found` | Resume migration |
| **Partial (embedded)** | `embeddeddolt/` exists but `bd list` errors out | Resume migration |
| **No beads** | No `.beads/` directory | Stop — not a beads repo |

If **Already Dolt**: inform the user and suggest `bd dolt status` (1.0) or `bd doctor` (≤0.63) if they have issues.
If **No beads**: inform the user and suggest `bd init` for a fresh installation.

**For Partial (server) state**, take a last look at running processes before destroying state:

```bash
cat .beads/dolt-server.pid 2>/dev/null    # the sql-server we'll need to stop
cat .beads/dolt-monitor.pid 2>/dev/null   # bd's monitor that respawns the server
pgrep -af "dolt sql-server" 2>/dev/null
```

Step 5 will TERM both. Skipping this risks the monitor respawning the server during cleanup.

### 2. Pre-Migration Validation

On bd 0.59–0.63:

```bash
bd doctor --migration=pre
```

**Known false positive**: on bd 0.62.0+ with on-disk classic data, this prints "Already using Dolt backend" with `JSONL Count: 0`. Ignore it if step 1 classified the repo as Classic or JSONL-only — the doctor only looks at runtime config.

On **bd 1.0+ in embedded mode, `bd doctor` is unavailable** — it prints "not yet supported in embedded mode" and exits 0. Skip this step entirely; rely on step 1's on-disk inspection.

Otherwise, review the output for real blockers and stop if there are any.

**Optional: upgrade `bd` first if you're on a pre-1.0 release.** Newer bd is significantly easier to recover from edge cases (the import path is more forgiving, embedded mode avoids server lifecycle bugs). If the user is on, say, 0.59.x and the migration is otherwise unconstrained:

```bash
brew upgrade bd      # or whatever installer they used
bd --version
```

A major-version jump (e.g. 0.59 → 1.0) is generally safe for the migration path because the JSONL import format is stable across this range. The schema fixes in step 7 cover the known transition cases.

### 3. Record Pre-Migration State

Capture current state for post-migration verification. `bd list` won't work on classic data from a newer bd, so read counts directly:

```bash
sqlite3 .beads/beads.db "SELECT COUNT(*) FROM issues" 2>/dev/null
sqlite3 .beads/beads.db "SELECT status, COUNT(*) FROM issues GROUP BY status" 2>/dev/null
sqlite3 .beads/beads.db "SELECT COUNT(*) FROM dependencies" 2>/dev/null
sqlite3 .beads/beads.db "SELECT COUNT(*) FROM comments" 2>/dev/null
wc -l < .beads/issues.jsonl 2>/dev/null
wc -l < .git/beads-worktrees/*/\.beads/issues.jsonl 2>/dev/null
cat .beads/config.yaml 2>/dev/null
```

Note the **authoritative** issue count (almost always SQLite, sometimes the worktree JSONL is more recent than main worktree's empty JSONL) and the `sync-branch` value from config.yaml.

If SQLite count > `.beads/issues.jsonl` line count, plan to use the SQLite→JSONL converter in step 3a — relying on the empty/stale JSONL would silently drop rows.

### 3a. SQLite → JSONL Converter (when JSONL is stale or empty)

**Skip if `.beads/issues.jsonl` already has all the data SQLite does.**

When the main-worktree JSONL is empty or older than the SQLite db (common: classic bd's "auto-flush" leaves the main worktree's `.beads/issues.jsonl` at 0 bytes; only the `beads-sync` worktree gets non-empty exports), step 7's fallback `bd import .beads/issues.jsonl` would import nothing. Convert directly from SQLite first:

```python
# Save as /tmp/bd-sqlite-to-jsonl.py and run with python3
import json, sqlite3
from collections import defaultdict
from pathlib import Path

DB = Path(".beads/beads.db")
OUT = Path("/tmp/bd-issues-from-sqlite.jsonl")

TOP_FIELDS = ["id","title","description","status","priority","issue_type",
              "owner","created_by","created_at","updated_at","closed_at",
              "close_reason","notes"]

def normalize_ts(ts):
    if not ts: return None
    if "T" not in ts and " " in ts: ts = ts.replace(" ","T",1)
    if not (ts.endswith("Z") or "+" in ts[10:] or ts.endswith("+00:00")):
        ts += "Z"
    return ts

con = sqlite3.connect(str(DB)); con.row_factory = sqlite3.Row

deps = defaultdict(list)
for r in con.execute("SELECT issue_id,depends_on_id,type,created_at,created_by FROM dependencies"):
    deps[r["issue_id"]].append({"issue_id": r["issue_id"], "depends_on_id": r["depends_on_id"],
        "type": r["type"], "created_at": normalize_ts(r["created_at"]) or "",
        "created_by": r["created_by"] or ""})

cmts = defaultdict(list)
for r in con.execute("SELECT id,issue_id,author,text,created_at FROM comments"):
    cmts[r["issue_id"]].append({"id": str(r["id"]), "issue_id": r["issue_id"],
        "author": r["author"] or "", "text": r["text"] or "",
        "created_at": normalize_ts(r["created_at"]) or ""})

n = 0
with OUT.open("w") as out:
    for r in con.execute("SELECT * FROM issues WHERE deleted_at IS NULL AND status != 'tombstone'"):
        d = {f: r[f] for f in TOP_FIELDS if f in r.keys() and r[f] not in (None,"")}
        for tf in ("created_at","updated_at","closed_at"):
            if tf in d: d[tf] = normalize_ts(d[tf])
        if r["id"] in deps:  d["dependencies"] = deps[r["id"]]
        if r["id"] in cmts:  d["comments"] = cmts[r["id"]]
        out.write(json.dumps(d, ensure_ascii=False) + "\n"); n += 1
print(f"wrote {n} issues to {OUT}")
```

```bash
python3 /tmp/bd-sqlite-to-jsonl.py
wc -l /tmp/bd-issues-from-sqlite.jsonl     # must equal SQLite count
head -1 /tmp/bd-issues-from-sqlite.jsonl | python3 -m json.tool   # spot-check
```

In step 7, import from `/tmp/bd-issues-from-sqlite.jsonl` instead of `.beads/issues.jsonl`.

**Notes**:
- The SQLite `issues` table has many columns (`compaction_level`, `event_kind`, `agent_state`, etc.); only the `TOP_FIELDS` list maps cleanly to bd's import schema. Other columns are bd internals and shouldn't round-trip through user-facing JSONL.
- `comments[].id` is converted to string here to satisfy bd ≥0.50's import schema.
- Tombstones and soft-deleted issues are skipped — re-importing them would produce confusing dangling rows.

### 4. Back Up Old Data

**This step is mandatory. Never skip it.**

```bash
mkdir -p .beads-migration-backup

cp -a .beads/. .beads-migration-backup/ 2>/dev/null || true
cp /tmp/bd-issues-from-sqlite.jsonl .beads-migration-backup/ 2>/dev/null || true
```

(`cp -a .beads/.` snapshots everything — SQLite, JSONL, hooks, dolt directories, lockfiles. Cheap insurance vs. selectively copying individual files.)

Then try a structured JSONL backup:

```bash
bd backup
ls -la .beads/backup/
```

**This is expected to fail** on bd 0.62.0+ with classic data — `bd backup` errors out with "no beads database found" because the runtime backend is Dolt and there's no Dolt db yet. Continue anyway; the raw copies in `.beads-migration-backup/` are the real fallback and step 7 imports from JSONL directly.

### 5. Remove Old Backend

For **Partial (server) state**, stop the running Dolt server and monitor first — otherwise the monitor will respawn the server during cleanup:

```bash
[ -f .beads/dolt-server.pid ]  && kill -TERM "$(cat .beads/dolt-server.pid)"  2>/dev/null
[ -f .beads/dolt-monitor.pid ] && kill -TERM "$(cat .beads/dolt-monitor.pid)" 2>/dev/null
sleep 1
pgrep -af "dolt sql-server" 2>/dev/null    # should be empty
```

Remove old database files and any stale locks to prepare for Dolt initialization:

```bash
rm -f .beads/beads.db .beads/beads.db-shm .beads/beads.db-wal
rm -f .beads/metadata.json
rm -f .beads/daemon.lock .beads/daemon.log
rm -f .beads/dolt-server.lock .beads/dolt-server.log .beads/dolt-server.pid \
      .beads/dolt-server.port .beads/dolt-server.activity .beads/dolt-config.log
rm -f .beads/dolt-monitor.pid .beads/dolt-monitor.pid.lock
rm -f .beads/.local_version .beads/last-touched
rm -rf .beads/dolt/                # for Partial (server) state
rm -rf .beads/embeddeddolt/        # for Partial (embedded) state
```

**Do NOT remove:**
- `.beads/config.yaml` — contains sync-branch and team settings
- `.beads/backup/` — just created in step 4
- `.beads/issues.jsonl` — primary data source for step 7 (or rely on `/tmp/bd-issues-from-sqlite.jsonl` from step 3a if JSONL is empty)

### 6. Initialize Dolt Backend

```bash
bd init --non-interactive --force
```

- `--force` is needed because `.beads/` already exists.
- `--non-interactive` skips bd 1.0's wizard prompts (role, contributor, fork detection). Without it, `bd init` blocks waiting for input. (Auto-detected when stdin isn't a TTY or `CI=true`, but pass it explicitly for safety.)
- For server-mode (bd ≤0.63 or bd 1.0 with external dolt sql-server), add `--server`.

**What `bd init --force` does and does NOT do** (bd 1.0+):

Creates the Dolt store:
- `.beads/embeddeddolt/` (1.0 embedded, default) **or** `.beads/dolt/` (server mode)
- New `metadata.json` (e.g. `{"backend":"dolt","dolt_mode":"embedded","dolt_database":"<repo>"}`)

**Auto-commits a chunk of repo files in a single `bd init: initialize beads issue tracking` commit**:
- `.gitignore` (adds Dolt-related ignores: `*.db`, `embeddeddolt/`, etc.)
- `.beads/.gitignore`, `.beads/metadata.json`, `.beads/issues.jsonl`
- `.beads/hooks/{post-checkout,post-merge,pre-commit,pre-push,prepare-commit-msg}` (its own hooks dir; `core.hooksPath` repointed)
- `AGENTS.md` — appends a `<!-- BEGIN BEADS INTEGRATION -->` block (preserves existing content), or creates the file if missing
- `CLAUDE.md` at the repo root — **created from scratch** (~70 lines). If the repo already organises Claude config under `.claude/CLAUDE.md`, the new repo-root file is redundant and may need to be removed/merged. Surface this to the user.
- `.claude/settings.json` — appends bd-related entries

Does **NOT** import `.beads/issues.jsonl` — it creates an *empty* database. Importing happens in step 7.

Verify initialization:

```bash
ls -la .beads/embeddeddolt/   # or .beads/dolt/ in server mode
cat .beads/metadata.json
git log --oneline -1          # should show the bd init commit
git show --stat HEAD          # review what bd auto-committed
```

Confirm metadata shows `"backend": "dolt"` (and `"dolt_mode": "embedded"` for 1.0).

**After init, ask the user** whether to keep or revert specific auto-committed files. The most common ask: revert/delete the new repo-root `CLAUDE.md` if `.claude/CLAUDE.md` is the project's canonical location. Use `git revert` of the init commit + cherry-pick the parts they want to keep, or `git reset HEAD~1` if the init commit is HEAD and they want to selectively re-stage.

### 6a. Repair Husky Integration (if applicable)

**Known bd bug, not fixed in 0.63.3 (latest as of 2026-03-30).** When a repo uses [husky](https://typicode.github.io/husky/) for git hooks, `bd init` sets `core.hooksPath` to `.beads/hooks/` and copies hook content into it — but it mishandles husky's helper layout. The copied hook silently fails or no-ops unless repaired.

Skip this section if the repo does not have a `.husky/` directory.

Detect the husky version by looking at the first line of `.husky/pre-commit`:

```bash
cat .husky/pre-commit
```

**Husky v8 style** (hook sources `_/husky.sh` at the top):

```sh
#!/usr/bin/env sh
. "$(dirname -- "$0")/_/husky.sh"

npx lint-staged
```

bd copies this content into `.beads/hooks/pre-commit` but does NOT copy `.husky/_/` into `.beads/hooks/_/`, so the source line fails at runtime. Fix by symlinking the helper dir:

```bash
ln -s ../../.husky/_ .beads/hooks/_
```

Verify: `ls -la .beads/hooks/_/husky.sh` should resolve to an existing file.

**Husky v9 style** (hook is just the command list, no sourcing):

```sh
#!/usr/bin/env sh
npx lint-staged
```

bd installs its own `h` dispatcher at `.beads/hooks/h` and writes a `.beads/hooks/<name>` that sources it with `. "$(dirname "$0")/h"`. The dispatcher then looks for the real hook at `$(dirname "$(dirname "$0")")/<name>`, which resolves to `.beads/<name>` instead of `.husky/<name>`. That file doesn't exist, so `h` silently exits 0 and **none of your husky checks run**.

Fix by inlining the `.husky/<name>` commands directly into `.beads/hooks/<name>`, replacing the broken `h` source line. Example for `.beads/hooks/pre-commit`:

```sh
#!/usr/bin/env sh
# Inlined from .husky/pre-commit (bd's 'h' dispatcher resolves wrong path at this depth)
export PATH="node_modules/.bin:$PATH"
<commands from .husky/pre-commit>

# --- BEGIN BEADS INTEGRATION v0.62.0 ---
# ... existing beads block preserved unchanged
```

Repeat for every hook the repo uses (`pre-commit`, `pre-push`, `commit-msg`, etc.). Check `sh -n <hookfile>` for syntax validity afterwards.

Note the `export PATH="node_modules/.bin:$PATH"` — husky's v9 `h` dispatcher normally adds this so `lint-staged` and friends resolve; when inlining, preserve it.

### 7. Restore Data

**Preferred path** (works if step 4's `bd backup` succeeded, which it won't on classic data):

```bash
bd backup restore .beads/backup/
```

**Fallback path** (the actual path for classic-data migrations): import directly from a JSONL.

If step 3a's converter ran (JSONL was empty/stale), use that file. Otherwise use `.beads/issues.jsonl`:

```bash
# Step 3a output:
bd import /tmp/bd-issues-from-sqlite.jsonl

# Or, if .beads/issues.jsonl already had the full data:
bd import .beads/issues.jsonl
```

The bd 1.0 import preserves the original prefix from the imported issues' IDs (e.g. `expire-*`) regardless of the new database's configured prefix. Don't worry about `bd init`'s auto-detected prefix overriding the migrated IDs.

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

Then verify counts. The verification path depends on bd version:

**bd 1.0+ (embedded mode)** — `bd doctor` is unavailable, fall back to `bd list` + round-trip:

```bash
# By default bd list filters to open; --status all is essential
bd list --status all 2>&1 | tail -2     # final line: "Total: N issues..."
bd list --status open --limit 0 | grep -c "^[○◐●✓❄]"
bd list --status closed --limit 0 | grep -c "^[○◐●✓❄]"
bd export -o /tmp/bd-roundtrip.jsonl
wc -l /tmp/bd-roundtrip.jsonl            # must equal pre-migration count
bd dolt status                            # confirms embedded server is up
```

**bd 0.59–0.63 (server mode)** — full doctor:

```bash
bd doctor --migration=post
bd list 2>&1 | wc -l
bd doctor
```

`bd doctor --migration=post` may still report `JSONL Valid: false` as a stale sub-check even after a successful export — trust the full `bd doctor` output (0 errors) as the real signal.

In both versions, compare the post-migration count with the pre-migration count from step 3. Also spot-check at least one issue with dependencies and one with comments to confirm those round-tripped:

```bash
bd show <id-with-deps>          # should show DEPENDS ON / BLOCKS sections
bd show <id-with-comments>      # should show COMMENTS section
```

If counts don't match, warn the user with both numbers and ask whether to proceed or investigate.

**Common confusion**: `bd list` defaults to filtering on `--status open`. Right after import, "No issues found" can be alarming when in fact 100+ closed issues are there. Always include `--status all` (or `--status closed`) for verification.

### 9. Set Up Sync Branch

If config.yaml had a `sync-branch` value (found in step 3):

```bash
bd migrate sync <branch-name>
```

bd 1.0's `bd migrate sync` rejects `--yes`; it just runs without confirmation. If your tooling tries to pass `--yes`, drop it.

After this, the replacement workflow for `bd sync` is:

```bash
bd dolt push     # push issue data to the configured sync branch on remote
bd dolt pull     # pull updates from remote
bd dolt status   # show local state vs sync branch
bd export -o .beads/issues.jsonl   # auto-runs after writes; force-run if needed
```

If no sync branch was configured, ask the user if they want one. For team projects, recommend it.

### 10. Clean Up Legacy Artifacts

Remove old format files and worktrees:

```bash
# bd 0.59–0.63 only — bd 1.0 doesn't expose --check or --fix flags
bd doctor --check=artifacts --fix 2>/dev/null || true
```

Check for and remove old beads worktrees:

```bash
git worktree list
```

If a beads worktree exists at `.git/beads-worktrees/<branch>/`:

```bash
git worktree remove .git/beads-worktrees/<branch-name>
```

The legacy worktree typically has a stale `.beads/issues.jsonl` modified vs. its branch — `git worktree remove` will fail with "contains modified or untracked files". Since the data is preserved both in the new Dolt and in `.beads-migration-backup/`, force-remove:

```bash
git worktree remove --force .git/beads-worktrees/<branch-name>
```

The `<branch>` itself (e.g. `beads-sync`) should be **kept** — bd 1.0's `bd dolt push` writes to it.

**Clear the legacy daemon registry**: `~/.beads/registry.json` is the per-user daemon discovery file used by bd ≤0.55.x. bd 0.62.0+ in Dolt mode doesn't use it, so any entries there are stale dead PIDs pointing at vanished SQLite files. On the last migrated repo for this user, clear it:

```bash
cat ~/.beads/registry.json    # review first — may have entries from other repos still on classic
echo '[]' > ~/.beads/registry.json
```

Don't blindly wipe if other workspaces are still on classic bd; remove only the entries for migrated workspaces.

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
grep -rln "bd sync\b\|bd daemon\|beads\.db\|sqlite" \
  .beads/PRIME.md CLAUDE.md AGENTS.md .claude/ docs/ README.md \
  2>/dev/null
```

(Drop `\.jsonl` from the grep — bd 1.0 still uses `.beads/issues.jsonl` for export, so matches there are fine.)

Outdated patterns to look for and the bd 1.0+ replacements:

| Outdated | Replacement |
|----------|-------------|
| `bd sync` | `bd dolt push` (after commit) and `bd dolt pull` |
| `bd sync --status` | `bd dolt status` |
| `bd daemon` | n/a — no background daemon in Dolt mode |
| `bd doctor` | `bd dolt status` / `bd dolt show` (in embedded mode) |
| References to `.beads/dolt/` as the storage path | `.beads/embeddeddolt/` (1.0 default) |
| References to `beads.db` / `sqlite` as storage | Embedded Dolt (or external sql-server with `--server`) |
| Worktree-based sync (`.git/beads-worktrees/<branch>/`) | Dolt branch sync via `bd dolt push|pull` |

For each file with matches, edit to replace the outdated lines. Common files to check:
- `.beads/PRIME.md` — AI workflow context (most likely to have outdated commands)
- `CLAUDE.md` / `.claude/` — Claude Code project instructions
- `AGENTS.md` — agent configuration (may have a bd-managed `<!-- BEGIN BEADS INTEGRATION -->` block — leave that alone, edit only user-curated sections)
- `README.md`, `docs/` — project documentation

Don't edit the bd-managed integration blocks (`<!-- BEGIN BEADS INTEGRATION -->...<!-- END BEADS INTEGRATION -->`) — bd regenerates these on init/upgrade and your edits will be clobbered. Edit only user-authored content outside those markers.

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
- **Empty/stale `.beads/issues.jsonl` in main worktree but data in SQLite**: Common with classic bd's auto-flush. Step 7's fallback would import zero rows. Use the SQLite→JSONL converter in step 3a, then `bd import /tmp/bd-issues-from-sqlite.jsonl`.
- **Worktree's JSONL is fresher than main's but older than SQLite**: SQLite is authoritative. Use the converter; the worktree JSONL is just a snapshot of the last `bd sync` call.
- **Schema mismatch on import (`cannot unmarshal number into ... string`)**: Legacy bd wrote certain fields as ints that newer bd expects as strings. Comment IDs (`comments[].id`) are the known case — the converter in step 3a already coerces this. Apply the same pattern for any other field that trips the import.
- **SQLite/JSONL count mismatch in step 1**: Classic daemons had unflushed WAL writes. Re-run step 0's graceful stop; if daemons are already dead, SQLite recovers the WAL on next open (run `sqlite3 .beads/beads.db ".recover"` or just let `bd init` do it).
- **Partial previous migration (server mode, bd 0.59–0.63)**: Symptom: `bd doctor` reports "Already using Dolt backend" but `bd list` errors with `database "<name>" not found on Dolt server at 127.0.0.1:NNNN`. The `.beads/dolt/` directory exists but is empty (no actual Dolt repo inside, just a `config.yaml` and stub `.dolt/` skeleton). Recovery: stop the running server (step 5), `rm -rf .beads/dolt/`, re-run `bd init --force`, proceed with restore.
- **Partial previous migration (embedded mode, bd 1.0+)**: `.beads/embeddeddolt/` exists but `bd list` errors. Same fix: `rm -rf .beads/embeddeddolt/` and `bd init --non-interactive --force`.
- **`bd doctor` not available in embedded mode**: bd 1.0 says "not yet supported in embedded mode". Use `bd dolt status` and `bd dolt show` for diagnostics; use `bd export` round-trip for verification.
- **Issue count mismatch (post-migration)**: Common cause is infrastructure beads (agents, rigs) excluded from default export. Try `bd list --status all` (default filter is `open`) before assuming data loss. If genuinely missing rows, re-import with `--dedup=false` and check the import log.
- **`bd list` reports "No issues found" right after import**: Default filter is `--status open`. Use `bd list --status all` or `--status closed` to see the rest. ~85% of imported issues are typically closed (historical data).
- **Worktree removal fails**: Try `git worktree remove --force <path>`. If still fails, inform user for manual cleanup.
- **Multiple beads worktrees**: List all with `git worktree list`, identify beads-related ones (path contains `beads-worktrees`), remove each.
- **Config.yaml missing**: Proceed without sync branch setup. After migration, suggest `bd config set sync.branch <name>` if needed.
- **Daemon binary already deleted but process still running**: `brew uninstall` removes the on-disk binary but a running daemon keeps it mmap'd. `kill -TERM <pid>` still works; the daemon shuts down cleanly from the in-memory code.
- **Dolt server respawning during cleanup**: bd's monitor (`.beads/dolt-monitor.pid`) restarts the sql-server if it dies. Always TERM the monitor *before* TERM-ing the server, or in parallel (the monitor exits on its own SIGTERM cleanly).
- **Multiple repos to migrate**: Each workspace needs its own run (daemon stop → backup → remove → init → import → export → verify). The `~/.beads/registry.json` cleanup in step 10 only needs to happen once at the end.
- **Husky integration broken after `bd init`**: See step 6a. bd 0.62.0 and 0.63.3 both mishandle husky helper layout — v8 needs a symlink fix, v9 needs the dispatcher inlined. Silently breaks commits if not repaired. (Status in bd 1.0.x: not verified — re-run step 6a's detection if husky is in use.)
- **Unwanted `AGENTS.md`, `CLAUDE.md`, `.gitignore` changes from `bd init` (1.0)**: bd 1.0 makes a single auto-commit `bd init: initialize beads issue tracking` modifying these files. If the project organises Claude config under `.claude/CLAUDE.md`, the new repo-root `CLAUDE.md` is redundant. Options: `git revert HEAD` then re-stage selectively; or `git reset --soft HEAD~1` to unstage the init commit and rebuild. Ask the user before doing either.
- **`.beads-migration-backup/` showing as untracked**: Add it to `.git/info/exclude` (not `.gitignore`) for stealth-mode users, alongside their existing `.beads/` entry.
- **`bd init --force` blocks on prompts**: bd 1.0 has interactive wizards (role, contributor, fork-detect) that block when stdin is a TTY. Always pass `--non-interactive` (or set `BD_NON_INTERACTIVE=1` / `CI=true`) when running through automation.

## Rules

- Never skip the backup step (step 4). If backup fails, stop and inform the user.
- Never delete `.beads-migration-backup/` without user confirmation.
- Never proceed past verification failures without explicit user approval.
- Preserve `config.yaml` through the migration — it contains team settings.
- Always verify post-migration counts before declaring success — `bd doctor --migration=post` on bd ≤0.63, or `bd list --status all` count + `bd export` round-trip on bd 1.0+.
- If `.beads/issues.jsonl` is empty/stale and SQLite has more rows, MUST use the step 3a converter — never silently import a near-empty JSONL.
- If any step fails, stop and report the error. Do not force through.
