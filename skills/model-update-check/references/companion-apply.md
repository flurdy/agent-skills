# Attended model-migration companion

`../scripts/apply_migration.py` consumes a saved schema-v2 `/model-update-check --evidence` report.
It is not the audit's default path and never applies a finding automatically. The report file is
private working input, not a tracked artifact. A normal audit with no reviewed evidence has no
complete recommendation to select. The script contains no shared model IDs or billing assumptions.

## Workflow and authority

1. Run the read-only audit with reviewed evidence after choosing the upgrade. The agent may use
   `--evidence -` for conversational preview; an actual attended application needs a privately
   retained report file. Obtain file authority before saving it; do not use Bash redirection as a
   guard workaround.
2. In a trusted terminal, preview selected recommendations (indices are **1-based**):

   ```text
   python3 -B scripts/apply_migration.py --report /private/audit.json --select 1 --select 2
   ```

   Preview validates the report's schema/evidence, exact from/to identities, all selected JSON
   pointers and source digests. It shows per-file before/after values, canonical target paths,
   pre/post SHA-256 hashes, whether unrelated parsed fields are unchanged, and a plan digest.
   It does not write targets or create backups. If all selected pointers already match, it reports
   `already-applied` and performs no write, even when the old source digest differs. In that case
   `unrelatedUnchanged` is unknown, not a claim that the whole file matches the earlier preview;
   a partly different selected change refuses the plan. Overlapping pointers refuse composition.
3. **Only after** reviewing the entire preview and obtaining fresh approval of the exact selected
   changes, including separate consent-sensitive allowlist/router-policy decisions, use the
   same `--report` and `--select` values with `--apply` and one `--allow-target` per canonical
   file to be written. The script requires a real stdin/stdout TTY and asks for the complete
   plan digest; consent-sensitive changes require a second `CONSENT <digest>` response. There is
   no `--yes`, environment override, inference call or model/catalog/package update. An audit,
   bead claim, router lease, approval to refresh or previously entered digest is not file authority.
   A Pi agent must additionally have the native file grants/leases for **each** target; passing
   `--allow-target` cannot grant them. Do not route an attended `--apply` through a noninteractive
   Bash tool or attempt to emulate the TTY.

The script accepts only router tier model replacements and exact policy additions, panel model
replacements/allowlist additions, and effective-dated billing policy additions/replacements already
emitted in a complete reviewed recommendation. It checks evidence for the proposed billing class,
start date and router consent, keeps previous allowlist entries and old model entries, and rejects
past billing starts, duplicate/overlapping intervals, unknown pointer operations and stale data.
It imports the pi-spend owner's strict validator and uses the existing offline audit helper to
validate staged router/panel JSON before writing. The helper may read native Pi auth state to list
available models; no credentials are inspected or printed by this companion. Synthetic fixtures
run with an isolated HOME and never exercise real targets.

## Backups, failure and activation

Apply mode creates a private run directory under `~/.local/state/model-update-check/backups`
by default (0700 directory, 0600 backups/manifest). It backs up **all pending target bytes**
and fsyncs them before the first write. Keep this backup root outside Dropbox and every target
directory. The report names the actual backup paths. Backups are retained; deletion is a
separately approved housekeeping action.

Writes are per-file, in sorted source order, through fsynced temporary files and atomic replacement
of each **canonical target**; symlinks themselves remain intact. Original file modes are retained.
The tool rechecks the exact source bytes and symlink target before each replacement, stops on the
first error and reports `applied`, `already-applied`, `failed`, or `not-attempted` per file, including
whether a failed write changed the target when observable. It cannot promise cross-file atomicity.
**No automatic rollback**: inspect private backups and current file hashes; recovery needs a
separate explicit authorization. Reapplication of an identical completed plan performs no writes
and does not add duplicate spend intervals. A changed unrelated field with pending selected edits
refuses the stale report; with already-present selected edits it writes nothing and labels
unrelated-content verification unknown. Create a fresh audit/preview for any further changes.

Parsed JSON is serialized with two-space indentation and a trailing newline on changed files.
Unrelated **values and key order** are preserved, but whitespace may normalize. The preview
shows the exact changed pointers and both whole-file SHA-256 values; it deliberately does not
print all unchanged private config fields. Only change records in the audit may be displayed.

On successful application, the CLI reruns `/model-update-check --offline` against the three
selected target paths and reports their validation statuses. A post-write audit failure is
`applied-unverified`, not success; backups remain. No `/reload`, model switch or review launch
is automatic. Open Pi's `/model` (or start a new Pi process) to reload `models.json` metadata when
that file was separately changed; this companion's scope is router/panel/spend JSON only.
Start a new session or use the owning router's status/reload workflow to check routing activation;
second-opinion reads its profile at its next invocation and pi-spend reads its policy on the next
collection. Do not infer activation from a file write alone.
