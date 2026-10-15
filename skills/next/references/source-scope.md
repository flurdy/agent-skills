# Explicit source scope and advisory Pi occupancy

Tracking ownership is not source ownership. Neither labels, a title, free-text analysis,
`repository_path`, nor a shared Beads store establishes every worktree a task will change.
Safe selection requires an explicitly reviewed declaration in the owning bead's metadata:

```json
{
  "source_scope": {
    "version": 1,
    "complete": true,
    "roots": ["repos/api", "repos/web"]
  }
}
```

The three fields inside `source_scope` are required; unknown fields/versions are invalid.
`complete` must be a boolean, not a truthy string. `roots` contains 1–32 literal relative
paths, at most 4096 characters each, relative to the resolver-proven owning store's canonical
directory. Run local collection from that store root; an unproven ancestor/redirected base
cannot certify scope. `.` explicitly declares root-only work. For an independently owned
repository, `.` names that repository, not a workspace that happens to link it. Workspace-owned
beads must explicitly name their member paths; their tracking root is never substituted.

Relative `..` paths can name other repositories. Absolute paths, home expansion and control
characters are rejected; no shell expansion or globbing occurs. Existing symlink aliases are
resolved and deduplicated. Each declared directory must match the exact canonical Git root
returned by the public observer; a subdirectory cannot silently widen to its parent. A nested
repository is independent and must be declared separately when touched. Missing/unresolvable
paths and absent observer evidence remain unavailable.

Completeness is a reviewed declaration, **not machine-proven absence of other source work**.
The agent may propose it during planning, but must show the complete set and obtain explicit
approval before recording or replacing `metadata.source_scope`. Preserve unrelated metadata
and follow Beads ownership resolution and mutation rules. These readers never backfill
metadata. Unknown declarations remain inspectable. If implementation discovers another source,
stop treating the previous result as safe, review the new set, mark it incomplete or replace it
after approval, then recheck. No task-scoped declaration changes native write permissions.

## Portable packet

`~/.agents/skills/next/scripts/next-bd --safe-json` returns version 1 with `candidates`,
`in_progress`, `blocked`, `deferred`, and `diagnostics`. Candidates retain normal P0–P3
ranking and each has its owning `selector`, `repository` and a normalized `source_scope`
(`state`, canonical `roots`, `reason`). States are `declared`, `partial`, `unknown`,
`invalid`, and `unavailable`. This packet alone contains **no occupancy evidence**.
It intentionally retains label-conflicting candidates for separate reporting. Safe flags
supersede `--avoid-busy`; ordinary `--json` retains its existing array contract.

`next-bd --safe` is the no-native-helper fallback. It keeps the familiar ranked review
table with one Lease check column: scope unknown/incomplete/invalid or observation
unavailable. Complete declarations are still not checked without a native observer.
Tracker-label overlaps remain inspectable in their own unnumbered table.
Python 3.10+, Bash, jq, Git and the existing compatible `bd` are sufficient. It never
imports Node or Pi. `--safe-json` is an integration packet, not a replacement for the
ordinary selector index or an automatically claimable queue.

## Optional Pi integration

The helper is **not installed by skill assembly**. `pi/index.ts` registers the read-only
`next_safe` tool; `pi/lease-selection.ts` owns collection and classification. This is
optional user-level runtime code, not something a project manifest can enable implicitly.
Review it and separately approve installation. No settings or dependency installation is
performed by `/next`.

When `@flurdy/pi-session-mode/lease-observer` is resolvable from the extension, load
`skills/next/pi/index.ts` as a Pi extension. For a separately installed Git package/checkout,
a small user-owned extension can wire the exact selected package's exported entry point:

```typescript
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { registerNextSafe } from "/absolute/agent-skills/skills/next/pi/index.ts";

export default function (pi: ExtensionAPI) {
  registerNextSafe(pi, async () => {
    const observer = await import("/absolute/selected-pi-session-mode/lease-observer.ts");
    return observer.probeWorktreeLeaseOccupancies;
  });
}
```

Replace both paths with reviewed canonical paths; the second is the entry point exported
as `@flurdy/pi-session-mode/lease-observer`, not a copied lock implementation. Keep guard
and observer on the same reviewed revision and reload together. Do not enable both the
wrapper and the default extension. User wiring is trusted runtime configuration; this
helper cannot attest which guard revision is active or certify a custom guard namespace.

Keep the local helper as `.ts`: Pi 1.1.0 reloads it through Jiti. Native `.mjs` imports
can remain cached across `/reload`, leaving a new entry point bound to old exports.
No global cache deletion, environment override or guard change is required. The existing
user wrapper still points to `pi/index.ts`; `/reload` picks up the `.mjs` to `.ts` migration.
A full Pi restart is only a fallback if running an older, unverified loader.

The observer runs **inside Pi**, not in the collector child. It receives no `selfPid` or
`runtimeDir` override: the public API uses this process's PID and live runtime environment,
just as the default guard does. Neither caller environment assertions nor diagnostic holder
JSON establish identity. Linux `/proc` and `lslocks` availability are checked before probing.
A custom guard using a different namespace/dependency-injected runtime is unsupported and
must not use this integration as safety evidence. Other Pi processes with different runtime
directories, other users, hosts, and noncooperating writers are outside coverage.

Collection uses the fixed installed `next-bd --safe-json` executable, the native context cwd,
a 60-second whole-process deadline and a 2 MiB output cap; its process group is killed on
completion, cancellation or timeout. At most 1000 candidates are accepted. Exceeding a bound
fails explicitly; no truncated result is eligible. Observer calls share one four-second
cancellation budget and use the public two-second per-command timeout. Its process cleanup
is owned by session-mode; the helper does not manipulate lock-holder processes.

One deduplicated union of at most 32 roots uses one public batch observation. Larger unions
remain unavailable, not partly certified; rechecking one exact qualified selector narrows
the scan. Wrong roots, missing rows, unsupported states, cancellation and errors cannot
produce eligible work. A known held root excludes its candidate even alongside missing
observations. Alias deduplication never drops any task's additional roots.

## Output and selection

`next_safe` accepts only `action: list|recheck` and an exact qualified `selector` for
recheck. It runs collection afresh for each call and produces ranked `eligible`, `occupied`,
`unknown`, `unavailable`, and `tracker_conflicts` queues, with observation time, native cwd,
session ID, diagnostics and an explicit coverage statement. Each row retains per-root
observations and separate same-store `tracker_overlap` evidence. No names/labels imply
scope, liveness, or authorization.

List tool content is the finished Markdown report: reproduce it verbatim, without
summarizing, changing columns, reordering rows or recomputing counts. The skill and native
tool prompt guidelines both state this rule so stale conversation formats do not take
precedence. This guides model behavior; it is not deterministic enforcement of its final
prose. Explicit verbatim prompting was confirmed in an attended user trial; ordinary
`/next safe` output after this guidance change still needs a live-session check.

Tool details retain those machine queues,
source declarations and per-root observations. Each row also carries its original packet
position so merging statuses for display cannot change the ranking. The familiar table
uses ordinary IDs (plus Repo only for workspaces), not repeated `local:` prefixes. Its
footer explains how Repo/ID maps to an exact selector. Known occupied rows and all
tracker-label overlaps are unnumbered and separate, with occupied taking precedence.
The safe view suppresses empty auxiliary headings; ordinary list output is unchanged.

Numbered rows are **for review**, including unknown and unavailable scope; the number is
not claim permission. Checked-free labels cover only local cooperating Pi processes.
Not-checked rows require a source-scope review or separately confirmed ordinary selection;
neither an ordinary claim nor metadata backfill is inferred from choosing a review number.
The short summary distinguishes not checked from occupied, with diagnostic reasons kept
where observation failed rather than a wall of empty queues.

Recheck content remains full JSON with the actual queue, so display wording never becomes
eligibility evidence. It uses fresh declarations and tracker state, then observes again.
A selector that is no longer ready or whose source cannot be read fails closed. After the normal handoff check,
recheck immediately before the existing qualified `next-select start` claim. This is a
procedural two-call sequence, not a claim lock or reservation; do not substitute the safe
view's numbers for ordinary ranked indexes. Missing helper or non-eligible recheck means
no safe claim. The user may separately approve an ordinary selection after its coverage
limit is disclosed; never silently fall back or treat a review-table number as that approval.

Only the subsequent concrete native write attempts acquisition. It can still lose a race
after a free observation or successful tracking claim. Never release, steal or bypass a
lease based on advisory output. No helper action creates, updates or closes Beads.

## Verification

- `make test-next`: portable collector/selector fixtures; ordinary modes must not need Pi.
- `make test-next-pi`: optional Node 22.19+ classifier/collector tests; no model requests.
- `NEXT_TEST_SESSION_MODE_DIR=/absolute/reviewed/checkout make test-next-pi`: additionally
  exercises the real public observer and kernel contention with isolated temporary repos
  and runtime directories. Test-only acquisition uses session-mode's existing lease helper;
  production selection code imports only the public observer. This proves self-exclusion,
  a foreign-holder race and independent nested roots, not a live user-session installation.
- Add `NEXT_TEST_PI_PACKAGE_DIR=/absolute/installed/pi-package` to run the optional
  host-loader registration/schema and same-process warm-reload tests against that exact
  installed Pi distribution. These cover a new helper export and the old `.mjs` migration
  through a nested user wrapper, using the production helper and an isolated collector.
  Pi 1.1.0 is verified; re-run this opt-in gate for loader upgrades rather than assuming
  all Pi/Jiti versions share cache behavior. Node 22.19+ supports the direct `.ts` imports
  used by the portable optional test harness; Jiti may create ordinary temporary caches.
- `make validate-skills` and `make doctor`: authoring and installed-link checks.

Without their explicit test paths, real-kernel and host-loader coverage report skipped. Tests do not
install the optional extension, alter global settings, acquire production leases or call
external model providers. Roll back by removing only the separately approved user extension;
ordinary `/next list` and tracker-only quick selection remain available.
