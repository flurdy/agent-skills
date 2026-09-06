# Optional repository aftercare

**Explicit opt-in only:** `/beads-migrate-to-dolt --aftercare [repository-path]` selects this
procedure. A migration request, successful import or completed verification never selects it.
Do not rerun migration. Apply the core skill's file-only target binding and repository rules first.
If the caller only wants recommendations, stay read-only throughout.

## Selection and confirmation

1. Read the completed migration evidence: target identity, verified data, publication/adoption
   status, retained source/backup paths and relevant integration observations. If absent or stale,
   report unknown status; do not recreate it by running migration. Destructive cleanup remains blocked.
2. Inspect only the affected repository and known migration-generated changes. Preserve unrelated
   concurrent work. Collect a compact table of proposed actions with exact paths, rationale,
   effect, rollback source and verification method.
3. Ask which actions to perform, including **None — keep existing state**. Do not treat selection
   as blanket shell permission. Every destructive/remote action needs separate confirmation
   immediately before its one visible command. Recheck paths/state when approval becomes stale.
4. Apply only the selected, supported actions; stop on error and preserve the partial diff. Missing
   tools or permissions require a scoped handoff to the repository's coding workflow, not a bypass.
   No automatic retries, rollback, broad staging, dependency upgrades or migrations in this mode.

## Bounded action menu

### Init-generated integration

Inspect the actual before/after Git state and any init-created commit. Do not assume a particular
bd version always creates the same files. Existing `AGENTS.md`, `CLAUDE.md`, client settings and
ignore files remain owned by their repository, not by this skill.

Propose only concrete unwanted additions or conflicts introduced by the selected migration. Use
focused follow-up edits under the repository's normal coding workflow. Never rewrite Git history
or undo an entire init commit as a shortcut; no reset, amend, or blanket revert recipe. Inspect
staged paths before any separately requested commit, and never stage unrelated work.

### Hook integration, including Husky

Detect the real hook owner, configured hooks path, installed tool version and actual hook contents.
Old Husky v8/v9 reports are historical clues, not automatic symlink/dispatcher-copy instructions.
Do not run a hook just to test it: a hook may commit, push, install packages or mutate files.

Prefer a supported native preview after checking the installed command's help. On the checked CLI:

```bash
bd -C "$ROOT" --sandbox migrate hooks --dry-run --json
```

This preview concerns marker-managed hooks; it does not establish that any particular Husky bug is
fixed or that its proposed edits preserve project checks. Inspect the exact plan. A selected repair
needs a separate confirmation and appropriate syntax plus project-specific behavior verification.
Do not inline commands, fetch packages with npx, bypass hooks or repoint hooks paths automatically.
A broken required hook blocks repository delivery until separately repaired; it does not negate
already-verified data migration or authorize an unselected repair.

### Legacy worktrees and user registry

Inventory only the legacy worktrees named by the selected migration. Check each worktree's status,
untracked files and unique commits. A data backup does not prove unrelated Git work is preserved.
Never force-remove a worktree or discard modified files. Preserve branches by default; deletion,
if requested, is a distinct action with its own evidence and confirmation.

The legacy `~/.beads/registry.json` is cross-repository user state. Default: leave it untouched.
Any requested cleanup is **entry-scoped** to proven migrated workspace paths and dead processes,
with the file backed up and unrelated entries preserved. Never replace the whole registry with an
empty array. PID reuse and activity in other repositories must not be inferred away.

### Backup retention

Keep the verified backup and original sources by default. Removal is eligible only with current
schema/data evidence and, for a remote-backed migration, verified remote plus adopter evidence.
Show exact backup path, why retention can end and what recovery copy will remain. Unknown status,
a mismatch or pending adoption blocks removal; an earlier cleanup approval is not sufficient.

### Curated documentation

Limit changes to selected, user-authored lines made stale by this migration; do not scan-and-rewrite
all docs or assistant settings. Validate replacement commands against the actual CLI and topology.
JSONL can still be used for interchange, so a `.jsonl` mention is not inherently stale. Do not
replace server-mode paths with embedded paths based on version alone.

Never manually edit the `<!-- BEGIN BEADS INTEGRATION -->` / `<!-- END BEADS INTEGRATION -->`
region or a versioned equivalent. Regeneration belongs to the supported owning tool and is a
separately selected action. Do not create new duplicate instruction files beside canonical ones.

## Report

List only the selected actions, resulting paths, checks, skipped actions and unresolved errors.
Keep migration verification, publication and aftercare status distinct. Retaining backups or
declining cosmetic cleanup is a valid outcome. Never silently advance tracker/Git state.
