---
name: release-status
description: >
  Read-only release dashboard for letterbox — one view of what's built-but-unpushed,
  pushed-but-not-rolled-out, deployed-but-toggle-still-off, and what's blocked by deploy
  order. Passive: never prompts, never pushes. Use for a quick "where is everything" glance.
allowed-tools: "Read,Bash(./scripts/release-digest:*),Bash(make feature-toggles-disabled:*),Bash(./scripts/pact-graph:*),Bash(./scripts/contract-check:*)"
model-tier: long-context-audit
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
model: sonnet
effort: medium
version: "1.4.1"
author: "flurdy"
---

# Release Status

A read-only snapshot of release state across all letterbox services. This is the passive
sibling of `/release-manager` — it shows the same picture but **takes no action and asks no
questions**. Safe to run anytime.

## When to Use

- A quick "what's the release situation right now" glance
- Before starting a `/watch-release` loop, to see the baseline
- To sanity-check what `/release-manager` would act on, without being prompted

For the interactive version that prompts to push / defer / cancel and auto-files CI-failure
beads, use `/release-manager`. For a deep gate on one service, use `/ready-to-release <service>`.

## Usage

```
/release-status                 # all services
/release-status dispatch        # one service
```

## Instructions

1. **Gather.** Run the shared mechanical digest (pass through any service arg to scope it):

   ```bash
   ./scripts/release-digest        # git + ci + deploy + toggles, one parsed result
   ```

   Parse the delimited sections (already ANSI-free):
   - `---META---`: `context=<kubectl ctx>`, `ci=<available|unavailable>` — when `ci=unavailable`
     (no `CIRCLECI_TOKEN`/`.env.circleci`) every `ci` field is `unknown`; show it as such.
   - `---SERVICES---`: one pipe-delimited line per service after the header line:
     `service|unpushed|uncommitted|ci|ciBranch|gitBranch|head|deploy|tag|age`.
     - `unpushed` (int, commits ahead of origin), `uncommitted` (`true|false`), `head` = short
       sha of the current local HEAD (`-` if no checkout).
     - `ci` ∈ `success|failed|running|error|unknown`; `ciBranch`/`gitBranch` are the pipeline branch
       and the repo's current branch.
     - `deploy` = a Deployment's `<ready>/<desired>` (`1/1` = rolled out; `N/M`, N<M = rolling out;
       `0/1` = failing); for **CronJob-backed services** (digest, patrol, reconciler) it's a marker:
       `cron` = settled / rolled out, `cron:rollout` = images differ (Flux mid-bump). Also
       `notfound`/`unknown` (e.g. no kubectl). `tag`/`age` = live image tag + pod-or-run age.
   - `---TOGGLES---`: `FLAG=value` lines — **compact by default**: only false-valued and
     manifest-referenced (`toggles:`/`parked:`) flags, with a trailing `# compact: …` summary of
     what was hidden. This covers the TOGGLE READY cross-reference (manifest flags show at any
     value; everything still-`false` is present). For the full map run
     `./scripts/release-digest --full-toggles`; for disabled-only, `make feature-toggles-disabled`.

2. **Read the manifest** at `docs/release-manifest.yaml` for the `order` block
   (`derived` / `manual` / `suppress`), the `toggles` map, and the `ignore` list.
   The effective dependency map = `(derived ∪ manual) − suppress`.

2b. **Scan dependencies + contract coverage** (both read-only, no tokens/network):

   ```bash
   ./scripts/pact-graph              # dependency ordering authority
   ./scripts/contract-check coverage # CI verification coverage
   ```

   Both are project symlinks installed by their owning skills — `pact-graph` by
   /release-manager (see its Setup), `contract-check` by /contract-check.

   From `pact-graph` parse:
   - `---GRAPH---` — `consumer: [providers]`, derived live from pact filenames.
   - `---DRIFT---` — `status: in-sync`, or `new:`/`removed:` edge lines = the manifest's
     `order.derived` block no longer matches the pacts.

   From `contract-check coverage` parse the `GAP`/`OK` lines: a `GAP <provider> … not-verified=…`
   means that provider's CI doesn't verify all its synced consumer contracts. (Contract *health*
   lives in `/contract-check`, not `pact-graph` — the dependency graph is purely the rate limiter.)

2c. **Read in-flight pushes** from `.release-state.json` at the repo root, **read-only** — if the
   file is absent or unreadable, skip this (do NOT create it; that's `/release-manager`'s job).
   Parse `rolloutWatch`: each entry `<service>: { sha, fromTag }` is a service `/release-manager`
   pushed in a prior tick whose new image hasn't been confirmed live yet. This is the only source
   for the *pushed-but-not-rolled-out* state — once a service is pushed, its `unpushed` count
   drops to 0, so nothing in the `release-digest` output reveals that a rollout is still in flight. Keep
   these for step 4.

3. **Render a single table**, one row per service (skip `ignore`d services), columns:
   `service | unpushed | uncommitted | CI | deployed (ready/tag/age)`.

4. **Below the table, observations only** (no prompts):
   - `⤴️ PUSHED — rolling out <service>` — for each `rolloutWatch` entry from step 2c: compare the
     live deploy `tag` against the recorded `fromTag`. If the live tag still equals `fromTag` (or
     deploy is `unknown`), the rollout is **in flight** — Flux hasn't applied the new image yet;
     show `was <fromTag>, awaiting new tag`. If the live tag has moved off `fromTag` (Deployment
     `ready`, or CronJob marker `cron`), it has effectively rolled out — `/release-manager` will
     clear it from `rolloutWatch` on its next tick; you may note `✅ rolled out <service> <tag>`.
     (Read-only: this skill never edits `rolloutWatch`.)
   - `READY` — has unpushed commits, CI green, and no **co-changing** prereq (see WAITING below).
   - `WAITING ON <prereq>` — has unpushed commits AND a provider it depends on (effective
     map) is *co-changing*: that provider also has unpushed commits, is mid-rollout (a Deployment
     `N/M`, N<M, or a CronJob service showing `cron:rollout`), or was pushed-but-not-confirmed
     (it's in step 2c's `rolloutWatch` with its live tag still at `fromTag`).
     A stable, already-live provider does **not**
     trigger this — only a provider that is itself changing right now. (This is the deploy
     rate limiter: a consumer waits a tick for its provider's rollout to confirm.)
   - `📊 DEPENDENCY DRIFT` — if `---DRIFT---` is not `in-sync`, list the `new`/`removed`
     edges and note `/release-manager` can reconcile them into `order.derived`.
   - `🔗 CONTRACT COVERAGE GAP` — for each `contract-check coverage` `GAP` line, show
     `provider: <not-verified=…>` (e.g. `contactform: not-verified=digest,patrol,…`). This is a
     prod-safety signal — a provider whose CI doesn't verify all its consumer contracts can
     break them silently. (For full contract health — staleness, sync-gaps — run `/contract-check`.)
   - `CI RED` — CI failed/errored (note: `/release-manager` would auto-file a bead here).
   - `TOGGLE READY` — a `toggles` entry whose gating service is rolled out (a Deployment showing
     `deploy ready`, or a CronJob service showing the settled `cron` marker) but whose flag is
     still `false` in prod (cross-reference the `---TOGGLES---` map from step 1). Exceptions:
     - A toggle with `status: dark-release` is **not** "ready" — show it as `🌓 DARK RELEASE
       <flag> — flip is a manual call once validated`, never as TOGGLE READY.
     - **Never** treat a `parked` flag as ready — those are intentionally off; list them once
       under a quiet "parked" footnote (flag, `superseded_by`, `reconsider_if`) and do not nudge.

5. Keep it to one screen. End with a one-line summary (e.g. "3 ready, 1 waiting, 1 CI red, 1
   toggle ready, 2 coverage gaps").

## Notes

- Strictly read-only. If you find yourself wanting to push, file a bead, or reconcile drift,
  that's `/release-manager`.
- `CIRCLECI_TOKEN` and kubectl context `paperboy` are needed for full data; degrade gracefully to
  `unknown` for any section that isn't available rather than failing the whole dashboard.
- `./scripts/pact-graph` (ordering) and `./scripts/contract-check coverage` (contract health)
  are pure-filesystem, need no network/tokens, and always run. The dependency graph is the
  deploy rate limiter; coverage gaps are a standing prod-safety signal independent of the
  current release. Full contract health (staleness, sync-gaps) is `/contract-check`.
