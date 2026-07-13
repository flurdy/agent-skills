---
name: ready-to-release
description: >
  Deep release-readiness gate for a single letterbox service — checks CI green, contracts in
  sync, deploy-order prereqs satisfied, feature toggle present, and unpushed work vs the live
  deploy. Emits a gate table and a single verdict. Use before deciding to ship one service.
allowed-tools: "Read,Skill,Bash(make git-status:*),Bash(make ci-status:*),Bash(make deploy-status:*),Bash(make feature-toggles:*),Bash(./scripts/mgit log:*),Bash(./scripts/pact-graph:*)"
model-tier: standard-coding
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
effort: medium
version: "1.2.0"
author: "flurdy"
---

# Ready to Release

A focused, per-service readiness gate. Where `/release-manager` scans everything and prompts,
this answers one question thoroughly: **is `<service>` safe to ship right now?** Read-only —
it reports a verdict, it does not push.

This is the deploy-side cousin of `/ready-to-merge` (which gates a PR *merge*). This gates a
*release* of an already-merged service: built locally, CI green, contracts honoured, deploy
order respected, toggle in place.

## Usage

```
/ready-to-release dispatch
```

A service argument is required.

## Instructions

Run these checks for the named service and present a gate table (✅ / ⚠️ / ❌ per row):

1. **Unpushed work** — `make git-status <service>`. Show commits ahead (`N`) and whether the
   tree is dirty (`*`). `N = 0` → nothing to release (note it and stop). Dirty tree → ⚠️
   (commit first). List the unpushed commits with `./scripts/mgit log <service> --oneline @{u}..HEAD`.

2. **CI** — `make ci-status <service>`. `success` → ✅; `running` → ⚠️ (wait); `failed`/`error`
   → ❌ (blocker); `unknown` (no `CIRCLECI_TOKEN`) → ⚠️.

3. **Contracts** — if the service has connectors/pacts, run `Skill /contract-check status` and
   read the rows for this service. Covers both contract *state* (staleness / unsynced /
   uncommitted → ❌) and *verification coverage* — if this service is a provider with a
   coverage `GAP` (CI doesn't verify all its consumer pacts, e.g. commented-out consumers),
   flag ⚠️ (a contract change may break an unverified consumer).

4. **Deploy order** — run `./scripts/pact-graph` (a project symlink installed by
   /release-manager — see its Setup if missing) and read `docs/release-manifest.yaml`. Build
   the effective dependency map = `(order.derived ∪ order.manual) − order.suppress`, and take
   this service's prereqs. A prereq blocks only if it is *co-changing* — has unpushed commits,
   is mid-rollout (`make deploy-status <prereq>` shows a Deployment `N/M`, N<M, or a CronJob
   service — digest/patrol/reconciler — showing `cron:rollout`), or was pushed-but-not-rolled.
   A stable, already-live prereq (a Deployment `1/1` at current tag, or a CronJob service showing
   the settled `cron` marker) does **not** block. All clear → ✅; any
   co-changing prereq → ❌ (waiting on `<prereq>`). (Contract coverage is checked in step 3, not
   here — this step is purely deploy ordering.)

5. **Feature toggle** — if `docs/release-manifest.yaml` `toggles` has an entry whose `service`
   is this one, report the flag, its live value (`make feature-toggles`), and the `flip_when`
   condition so you know whether shipping needs a follow-up toggle flip. Missing-but-expected
   toggle → ⚠️. A toggle with `status: dark-release` means the service is in a shadow launch —
   report it as `🌓 dark-release` (flip is a later manual call), not a blocker. If the service
   has a `parked` flag, note it as informational only (deliberately off, `superseded_by` /
   `reconsider_if`) — never treat it as a pending flip.

6. **Live deploy** — `make deploy-status <service>`: show current `ready/tag/age` so you can see
   what's running versus what you're about to ship. For a CronJob service (digest/patrol/reconciler)
   this is the `cron`/`cron:rollout` marker + tag + last-run age, not replicas.

## Verdict

End with one line:

- **READY ✅** — unpushed commits, CI green, contracts in sync, prereqs rolled out. Suggest
  `make git-push <service>` (the user runs it, or use `/release-manager`).
- **NOT READY ❌** — list the blocking rows.
- **HOLD ⚠️** — only soft warnings (CI running, dirty tree, toggle follow-up); say what to wait for.

Read-only: never push here. Pushing is an explicit action via `/release-manager` or `make git-push`.
