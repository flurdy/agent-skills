---
name: beads-migrate-to-dolt
description: "Migrate beads from classic SQLite/JSONL to Dolt, or safely upgrade an existing Dolt schema after a bd upgrade."
allowed-tools: "Read,Grep,Glob,Bash(bd:*),Bash(dolt:*),Bash(env:*),Bash(git:*),Bash(cp:*),Bash(rm:*),Bash(mkdir:*),Bash(ls:*),Bash(cat:*),Bash(test:*),Bash(wc:*),Bash(pgrep:*),Bash(kill:*),Bash(sqlite3:*),Bash(python3:*),Bash(echo:*),Bash(brew:*),AskUserQuestion"
model-tier: premium
model: opus
effort: high
version: "1.3.0"
author: "flurdy"
---

# Beads Storage and Schema Migration

Safely migrate classic SQLite/JSONL data to Dolt or upgrade an existing Dolt schema after a `bd` upgrade. Both paths prioritize backups, count verification, and preservation of remote history.

## bd Version Compatibility

This skill has been validated against:
- **bd 0.59.x – 0.63.x**: server-mode Dolt at `.beads/dolt/`
- **bd 1.0.x**: embedded Dolt commonly at `.beads/embeddeddolt/`
- **bd 1.1.0**: schema migrations through v53, remote-backed migration gate, `bd bootstrap`, and native `bd backup` subcommands

Important differences:
- Existing server-mode repositories remain supported after upgrading to bd 1.1; do not reinitialize merely to change storage mode.
- `bd migrate --inspect --json` is the schema diagnostic on bd 1.1+.
- A remote-backed database with pending migrations must have exactly one designated migrator. Independent clone migrations fork schema history unrecoverably.
- `bd init --force` is deprecated in bd 1.1 in favor of `--reinit-local`; remote replacement additionally requires `--discard-remote` and a destroy token in non-interactive mode.
- `bd backup` is now a command group: `bd backup init|status|sync|restore|remove`.
- `bd export --all` includes infrastructure records and memories; use it for the broadest JSONL safety export.
- `bd sync` is removed; use `bd dolt push|pull|commit|status` for Dolt remotes.

## When to Use

- Classic `.beads/beads.db` or JSONL-only data needs conversion to Dolt
- `bd migrate --inspect` reports pending schema migrations after a bd upgrade
- bd reports a `remote_migrate_gate`
- Dolt initialization is partial or broken

## Usage

```
/beads-migrate
```

## Prerequisites

- `bd` CLI installed; use the target version before inspecting or migrating
- `dolt` binary on PATH for server-mode repositories; embedded mode bundles its engine
- Git repository with an existing `.beads/` directory
- Operator confirmation of the designated clone when a shared Dolt remote has pending migrations

## Route Selection

First inspect files and schema without bypassing safety gates:

```bash
bd --version
ls -la .beads/beads.db .beads/issues.jsonl .beads/dolt .beads/embeddeddolt 2>/dev/null
cat .beads/metadata.json 2>/dev/null
cat .beads/config.yaml 2>/dev/null
bd migrate --inspect --json 2>&1 || true
```

- If classic SQLite/JSONL exists without a working Dolt store, use **Path B** below.
- If Dolt works and no migrations are pending, stop: no migration is needed.
- If Dolt works and migrations are pending, use **Path A**. Do not run the classic remove/reinitialize steps.

## Path A: Upgrade an Existing Dolt Schema (bd 1.1+)

### A1. Resolve the Remote Migration Gate

If inspection reports `remote_migrate_gate`, ask the operator to choose:

1. **Designated migrator**: this is the only clone that will migrate, verify, and publish.
2. **Adopting clone**: another clone will publish; preserve local unpushed work and later run `bd bootstrap`.

Never infer this choice or set `BD_ALLOW_REMOTE_MIGRATE=1` before explicit confirmation.

### A2. Record Counts and Back Up

Before changing schema:

```bash
bd list --status all --limit 0 --json > /tmp/bd-pre-schema-list.json
bd export --all -o /tmp/bd-pre-schema-upgrade.jsonl
wc -l /tmp/bd-pre-schema-upgrade.jsonl
bd dolt stop
test ! -e .beads-schema-migration-backup
mkdir .beads-schema-migration-backup
cp -a .beads/. .beads-schema-migration-backup/
```

The stopped-server raw copy is the mandatory fallback. If `bd list` or `bd export` fails because a partially applied schema references a not-yet-created column, do not reset the Dolt working set. Record direct read-only counts where possible:

```bash
bd sql 'SELECT COUNT(*) AS issues FROM issues' --json
bd sql 'SELECT status, COUNT(*) AS count FROM issues GROUP BY status' --json
bd sql 'SELECT COUNT(*) AS dependencies FROM dependencies' --json
bd sql 'SELECT COUNT(*) AS comments FROM comments' --json
```

Also preserve any recent `.beads/backup/*.jsonl`. `bd dolt stop` flushes the partial working set before the raw copy; the designated migration can then finish it. If a native backup destination is already configured and schema access is not gated, also run `bd backup status` and `bd backup sync`. Never overwrite or delete an existing migration backup without confirmation.

### A3. Migrate the Designated Clone

For a local-only database:

```bash
bd migrate
```

For a remote-backed database, only after the operator designates this clone:

```bash
env BD_ALLOW_REMOTE_MIGRATE=1 bd migrate
```

Do not use `bd migrate schema` to evade the remote gate. The environment override records the explicit coordination decision while normal migration applies and commits all pending versions.

**Old Dolt working-set guard (`gastownhall/beads#4566`)**

Repositories created before `schema_migrations` may have legitimate uncommitted `config` rows or may accumulate a partial migration working set. bd then refuses with:

```
pending schema migrations alter pre-existing dirty tables: ...;
run 'bd dolt commit' to commit the working set at the current schema
```

Try `bd dolt commit -m "checkpoint working set before schema migration"`. If that command fails with the same initialization guard:

1. Confirm the mandatory raw backup exists.
2. Stop the Dolt server cleanly.
3. Run `dolt diff --summary` in `.beads/dolt/<database>/`.
4. Stage only the tables named by that diff, explicitly; never use a blanket add.
5. Commit the checkpoint with raw Dolt, then rerun `bd migrate`.

```bash
dolt add <explicit-table> [<explicit-table> ...]
dolt commit -m "checkpoint working set before schema migration"
bd migrate
```

A very old database may stop twice: first for pre-existing `config` rows, then for tables changed by the partial schema sequence. Inspect and checkpoint each working set separately. Never reset or discard it, never commit unexpected issue data without investigating, and never automate an unbounded retry loop.

### A4. Verify Before Publishing

```bash
bd migrate --inspect --json
bd list --status all --limit 0 --json > /tmp/bd-post-schema-list.json
bd export --all -o /tmp/bd-post-schema-upgrade.jsonl
wc -l /tmp/bd-post-schema-upgrade.jsonl
bd dolt status
```

Compare pre/post issue counts, statuses, dependencies, and comments. Confirm inspection reports the target schema with no pending migrations and the Dolt working set is clean. Stop on any mismatch.

### A5. Publish and Adopt

A remote-backed schema upgrade is incomplete until the designated clone publishes it. Check the local push guard, then ask for explicit permission immediately before the standalone remote action:

```bash
bd config get no-push 2>/dev/null || true
bd dolt push
```

If `no-push: true` blocks the approved push, ask again before bypassing the guard. Keep the config unchanged and use a one-command override:

```bash
env BD_NO_PUSH=false bd dolt push
```

Verify the local remote-tracking ref matches local `main`. Every other clone must preserve unpushed work, then adopt the published database:

```bash
bd export --all -o /tmp/bd-before-bootstrap.jsonl
bd bootstrap
```

`bd bootstrap` may replace the local database. Review its plan or use `--dry-run` first; never bootstrap over unpushed work without an export or push.

Keep the raw backup until the migrated remote and at least one adopter have been verified.

## Path B: Classic SQLite/JSONL to Dolt

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
| **Dolt (server)** | `dolt/` exists, metadata says `"backend": "dolt"`, server reachable | Run `bd migrate --inspect`; use Path A only if pending |
| **Dolt (embedded)** | `embeddeddolt/` exists, metadata `"dolt_mode": "embedded"`, `bd list` works | Run `bd migrate --inspect`; use Path A only if pending |
| **Partial (server)** | `dolt/` exists but empty or sql-server says `database "<name>" not found` | Resume migration |
| **Partial (embedded)** | `embeddeddolt/` exists but `bd list` errors out | Resume migration |
| **No beads** | No `.beads/` directory | Stop — not a beads repo |

If **Dolt**: return to Path A. Do not remove or reinitialize a working Dolt store just because bd was upgraded.
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

The raw copy is authoritative for classic data. On bd 1.1+, `bd backup` is a command group rather than a standalone backup action, and its native backup path requires a working Dolt database. Do not attempt it against classic-only files. After Dolt initialization, a separately configured destination can be managed with `bd backup init`, `bd backup sync`, and `bd backup restore`.

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
# bd 1.1+
bd init --non-interactive --reinit-local

# bd 1.0 and earlier
bd init --non-interactive --force
```

- `--reinit-local` is the bd 1.1 replacement for the deprecated `--force` alias.
- If bd detects existing remote Dolt history, stop. Use `bd bootstrap` to adopt it, or obtain separate explicit approval before `--discard-remote`; non-interactive replacement also requires the destroy token documented by `bd help init-safety`.
- `--non-interactive` skips wizard prompts. Pass it explicitly in automation.
- Add `--server` only when intentionally retaining or selecting server mode.

**What `bd init` does and does NOT do** (behavior varies by version; inspect the resulting Git diff and log):

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

**Native backup path** (only when a Dolt-native backup destination was configured and synced):

```bash
bd backup restore <configured-backup-path>
```

**Classic migration path**: import directly from JSONL.

If step 3a's converter ran (JSONL was empty/stale), use that file. Otherwise use `.beads/issues.jsonl`:

```bash
# Step 3a output:
bd import /tmp/bd-issues-from-sqlite.jsonl

# Or, if .beads/issues.jsonl already had the full data:
bd import .beads/issues.jsonl
```

The bd 1.0 import preserves the original prefix from the imported issues' IDs (e.g. `myrepo-*`) regardless of the new database's configured prefix. Don't worry about `bd init`'s auto-detected prefix overriding the migrated IDs.

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
- **Native `bd backup` is unavailable on old format**: Expected. Preserve the raw copy and import JSONL after initialization.
- **Empty/stale `.beads/issues.jsonl` in main worktree but data in SQLite**: Common with classic bd's auto-flush. Step 7's fallback would import zero rows. Use the SQLite→JSONL converter in step 3a, then `bd import /tmp/bd-issues-from-sqlite.jsonl`.
- **Worktree's JSONL is fresher than main's but older than SQLite**: SQLite is authoritative. Use the converter; the worktree JSONL is just a snapshot of the last `bd sync` call.
- **Schema mismatch on import (`cannot unmarshal number into ... string`)**: Legacy bd wrote certain fields as ints that newer bd expects as strings. Comment IDs (`comments[].id`) are the known case — the converter in step 3a already coerces this. Apply the same pattern for any other field that trips the import.
- **SQLite/JSONL count mismatch in step 1**: Classic daemons had unflushed WAL writes. Re-run step 0's graceful stop; if daemons are already dead, SQLite recovers the WAL on next open (run `sqlite3 .beads/beads.db ".recover"` or just let `bd init` do it).
- **Partial previous migration (server mode, bd 0.59–0.63)**: Symptom: `bd doctor` reports "Already using Dolt backend" but `bd list` errors with `database "<name>" not found on Dolt server at 127.0.0.1:NNNN`. The `.beads/dolt/` directory exists but is empty (no actual Dolt repo inside, just a `config.yaml` and stub `.dolt/` skeleton). Recovery: stop the running server (step 5), `rm -rf .beads/dolt/`, re-run `bd init --force`, proceed with restore.
- **Partial previous migration (embedded mode)**: `.beads/embeddeddolt/` exists but `bd list` errors. Back it up first, then remove it and reinitialize with the version-appropriate flag (`--force` on bd 1.0, `--reinit-local` on bd 1.1+). Stop instead if remote history exists; adoption with `bd bootstrap` is safer.
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
- **`bd init` blocks on prompts**: Always pass `--non-interactive` (or set `BD_NON_INTERACTIVE=1` / `CI=true`) in automation. On bd 1.1 use `--reinit-local`; do not add `--discard-remote` without a separate operator decision and the required destroy token.
- **Remote-backed schema gate**: Exactly one clone runs `env BD_ALLOW_REMOTE_MIGRATE=1 bd migrate` and publishes. Every other clone adopts with `bd bootstrap`; independent migrations can fork schema history unrecoverably.
- **Partial schema working set**: A blocked auto-migration may leave schema changes uncommitted and make `bd list` or `bd export` fail. Preserve it in the stopped-server raw backup; do not reset it. Use direct `bd sql` counts, then let the designated migration finish the sequence.
- **Dirty-table guard loops on old Dolt**: If `bd dolt commit` is itself blocked by schema initialization, stop the server and use raw `dolt diff --summary`, explicit `dolt add <tables>`, and `dolt commit`. Re-run migration and repeat only for another inspected, expected working set; older pre-`schema_migrations` databases can require two checkpoints.
- **`no-push: true`**: This is a deliberate permission guard. After explicit push approval, use `env BD_NO_PUSH=false bd dolt push` for that command only; do not persistently disable the guard.

## Rules

- Never skip the applicable backup step (A2 or step 4). If backup fails, stop and inform the user.
- Never delete `.beads-migration-backup/` or `.beads-schema-migration-backup/` without user confirmation.
- Never proceed past verification failures without explicit user approval.
- Never bypass `remote_migrate_gate` until the operator designates exactly one migrator.
- Always ask for explicit permission immediately before `bd dolt push`; migration approval alone is not push approval.
- Preserve `config.yaml` through the migration — it contains team settings.
- Always verify post-migration counts before declaring success — `bd doctor --migration=post` on bd ≤0.63, or `bd list --status all` count + `bd export` round-trip on bd 1.0+.
- If `.beads/issues.jsonl` is empty/stale and SQLite has more rows, MUST use the step 3a converter — never silently import a near-empty JSONL.
- If any step fails, stop and report the error. Do not force through.
