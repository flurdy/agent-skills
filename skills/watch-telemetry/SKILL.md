---
name: watch-telemetry
description: "Query opt-in local watcher-execution counters, labelled partial and agent-reported. Separately enable, disable, or prune collection without retaining transcripts or target identities."
allowed-tools: "Read,AskUserQuestion,Bash(~/.agents/skills/watch-telemetry/scripts/watch_telemetry.py counts:*)"
model-tier: economy
effort: medium
version: "0.1.0"
author: "flurdy"
---

# Watcher Execution Counts

One local counter authority for the seven `watch-*` entry points. These are **agent-reported**
execution observations, always **partial**: not scheduler dispatch, unique runs, successful work,
or evidence that a watcher is safe to retire. Do not read native transcripts to fill gaps.

## Usage

```text
/watch-telemetry                 # counts for the last 90 UTC days, including today
/watch-telemetry counts --days 7
/watch-telemetry enable          # explicitly opt in on this machine
/watch-telemetry disable         # stop collection; retain recent counters
/watch-telemetry prune           # remove expired counter/configuration-day buckets
```

Requires Python 3.10+ on Unix with `fcntl`, directory-relative file operations, and a local
filesystem supporting advisory locks and atomic rename. No packages, network, credentials,
repository inspection, or runtime extension are needed. Missing support means unavailable;
never install dependencies or modify another workflow to make telemetry work.

## Query

With no arguments use `counts --days 90`. Accept only the forms above; days must be 1–90.

```bash
~/.agents/skills/watch-telemetry/scripts/watch_telemetry.py counts --days 90
```

Render the returned UTC window and one compact table: watcher, harness, invocations, ticks.
`watch-rollout` selects a specialist and has no ticks: render its null tick count as `—`, not zero.
An invocation of the dispatcher followed by its specialist intentionally appears under both names;
do not sum those rows as unique watches.

Always show `source: agent-reported; coverage: partial` for an existing store. Configuration-day
counts (`enabled`, `disabled`, `mixed`, `unknown`) describe the configured policy, **not** successful
instrumentation coverage. A missing store is disabled/unavailable with no numeric rows; an unsafe,
malformed, locked, or unreadable store is unavailable, not empty success. Do not repair it here.

Zero observations are **not proof of zero use**. Collection is disabled by default; other machines,
old scheduled prompts, skipped helper calls, unavailable permissions and interrupted starts are
unobserved. Duplicate calls can overcount. There is no deduplication ledger or exactly-once claim.
Do not infer continuous coverage, counts before installation, or unique users/sessions.

## Explicit controls

Only an explicit request for `enable`, `disable`, or `prune` authorizes that action. Before executing,
state its local scope and retention behavior, then use the exact corresponding helper command.
These commands are not preapproved by the skill's tool declaration. A query, watcher launch, or
installation is never an enable request. Do not edit harness permissions, environment, or settings.

- `enable`: create the private store if absent and enable collection. Repeating it is safe.
- `disable`: disable collection without deleting recent history. Missing storage remains absent.
- `prune`: explicitly prune expired daily buckets, including while collection is disabled, and
  discard a reserved interrupted-write temporary file without replaying its uncommitted counters.

## Recorder contract for consumers

The narrow internal call is:

```text
~/.agents/skills/watch-telemetry/scripts/watch_telemetry.py record WATCHER HARNESS EVENT
```

- WATCHER is exactly `watch-prs`, `watch-release`, `watch-pr-feedback`, `watch-review-requests`,
  `watch-rollout`, `watch-actions-rollout`, or `watch-flux-rollout`.
- HARNESS is exactly `pi` or `claude`, selected from the current harness/tool surface, never the
  model name or a shell probe. Bind the literal before scheduling; adapt Pi prompts when reused
  in Claude. Unknown harnesses are unobserved, never guessed.
- EVENT is `invocation` for a normal execution request, including nested specialist invocation,
  or `tick` for one recurring execution attempt. `watch-rollout tick` is invalid. Reading a skill
  as context, `status`, `reset`, `recheck`, and `disposition` do not count as new watches or ticks.
- Record at most once at normal execution entry, after argument validation but before setup.
  The scheduler's self-contained prompt owns the single tick call; loading the watcher again
  within that tick must not also record an invocation. Never record merely while preparing a
  prompt, scheduling a future wake, or repeating a skill read.
- Record at the tick head, before domain work, questions, final cadence output or terminating
  scheduling. The recorder is silent on success, disabled storage, and storage failure. It has
  a bounded two-second lock wait and never retries a failed write. Denied/missing tooling also
  means skip recording, not stop the watch. Never append telemetry bookkeeping to a quiet tick.
- Consumer frontmatter grants only this helper's `record` prefix. It does not authorize enablement,
  arbitrary commands, feedback persistence, repository writes or any external action. Harness
  permissions still apply; do not change them automatically. A blocked helper leaves partial data.

## Storage and retention

The per-machine store is `$XDG_STATE_HOME/agent-skills/watch-telemetry/`, or
`~/.local/state/agent-skills/watch-telemetry/` when XDG_STATE_HOME is unset. It must be a private,
user-owned, non-symlink directory on a local, non-synced filesystem. Its ancestors must not be
untrusted-writable. User-selected XDG storage must not point at a synced folder; the helper cannot
prove a mount is not synchronized. No arbitrary output path is accepted through command arguments.

Normal storage contains only `counts.json` and `.lock`. One fixed `.counts.tmp` slot may remain
after process termination during a write; it makes collection/query unavailable until explicit
`prune` discards it. No unbounded temporary filenames or raw events accumulate. A missing lock for
existing state is unavailable, not automatically recreated, even by `enable`.
The schema allows version, enabled flag, policy day, and
up to 90 daily buckets of enabled/disabled flags plus fixed-key integer counters. No free text,
transcripts, prompts, URLs, repository paths, target identities, session IDs, hashes of content,
model names, credentials, or raw event log. Directory mode is 0700; files are 0600. Symlinks,
hardlinked files, unexpected fields, excessive size and unsafe permissions are rejected, not repaired.

The window is the last **90 UTC days including today**. Each enabled record and each explicit
control prunes expired buckets; queries project the current window without rewriting data.
There is **no background cleanup**: when idle or disabled, old on-disk buckets remain until an
explicit `prune` or later enabled write. Disabling is not erasure. Retention is active/lazy, not a
wall-clock deletion guarantee, and atomic replacement is not forensic secure erasure.

The data file and temporary slot each have a 256 KiB write/read bound; the lock contains no payload.
Concurrent writers use an advisory lock and atomic replacement. Lock timeout, I/O failure,
corruption, or a backward clock skips recording silently; the query exposes its own failures.
Counters are bounded, and retries/other machines are not merged. Telemetry errors never alter
watch-loop protocol tokens, deadlines, budgets, confirmation rules or runtime memory-only state.

## Verification boundary

Run `make test-watch-telemetry` for the real recorder's fixtures and every consumer's scheduling
contracts, then `make check`. These tests prove the counter and instruction boundaries, not that
an LLM will execute every instruction. Live Pi/Claude watcher observations remain a separate,
explicitly enabled validation; never start operational watchers merely to test this helper.
