---
name: ready-to-release
description: >
  Deep release-readiness gate for one service using normalized Git, CI, contract, ordering,
  toggle, and deployment evidence. Emits a capability-aware gate table and one verdict without
  prompting or mutating state. Use before deciding whether a service is safe to ship.
allowed-tools: "Read,Bash(./scripts/release-digest:*),Bash(./scripts/release-order:*),Bash(./scripts/contract-check:*)"
model-tier: standard
model: sonnet
effort: medium
version: "1.4.0"
author: "flurdy"
---

# Ready to Release

A focused, per-service readiness gate. Where `/release-manager` scans all services and can prompt,
this skill answers one question without taking action: **is `<service>` safe to ship now?**

It is the deploy-side cousin of `/ready-to-merge`: one gates an already-merged service release,
the other gates a pull-request merge.

## Usage

```text
/ready-to-release dispatch
```

A service argument is required. If it is absent, print usage and stop without running commands.

## Evidence

1. **Gather the normalized project digest.** Run `./scripts/release-digest` without service scoping
   so dependency rows remain available. Parse:

   - `---META---`: `ciProvider=<circleci|github-actions|cloud-build|none>` and
     `ci=<available|partial|unavailable>`.
   - `---SERVICES---`: require this exact header and select the named service:
     `service|unpushed|uncommitted|ci|ciBranch|gitBranch|head|deploy|tag|age|ciRevision|ciExpectedRevision`.
   - `---TOGGLES---`: optional normalized live toggle values.

   If the command is missing, exits nonzero, is malformed, or omits the service, keep going and
   render every gate as `➖ N/A` with the evidence reason. The verdict is `HOLD ⚠️` because the
   required Git and CI evidence is unavailable. Do not fall back to provider-specific commands.

2. **Read optional project policy.** If `docs/release-manifest.yaml` is absent or unreadable, use
   empty `toggles`, `parked`, `ignore`, and `non_deploying` defaults. Otherwise read only those
   sections. A service in `non_deploying` has no deployment or remote-CI release gate.

3. **Gather optional dependency order.** Run `./scripts/release-order` when available. A successful,
   well-formed result supplies provider metadata and the effective `---GRAPH---`.

   - `provider=none` with an empty graph is valid and means no deploy ordering is configured.
   - A graph with no entry for the service is valid evidence that it has no prerequisites.
   - If the command is missing, nonzero, or malformed, order evidence is unavailable. The order row
     is `➖ N/A`, but unavailable safety-critical evidence produces `HOLD ⚠️`; never claim readiness
     from an assumed empty graph.

4. **Gather optional contract health.** Run `./scripts/contract-check all` when available. Treat
   contract evidence as applicable when its output names the service or when valid Pact-backed
   order evidence places the service in a consumer/provider relationship.

   - Stale, different, missing-provider, uncommitted, not-built, or not-synced evidence is a hard
     blocker.
   - A verification `GAP` involving the service is a soft hold.
   - A clean applicable result passes.
   - When no contract relationship applies, the gate is `➖ N/A` and has no verdict impact.
   - When a relationship is known but the contract command is unavailable or malformed, the gate
     is `➖ N/A` and the verdict is `HOLD ⚠️` because expected safety evidence is unavailable.

5. **Read optional in-flight state.** If `.release-state.json` exists and is valid, read
   `rolloutWatch` without modifying it. Ignore an absent or malformed state file; saved state alone
   never proves deployment status.

## Gate table

Render exactly one table with columns `Gate | Result | Evidence`. Use these result classes:

- `✅ pass` — applicable evidence proves the gate.
- `⚠️ hold` — evidence is unsettled or an expected capability is unavailable.
- `❌ block` — evidence proves release is unsafe or there is nothing to release.
- `➖ N/A` — the project does not use that capability or the gate cannot be evaluated.

An N/A row is never a blocker by itself. Expected safety evidence can still make the overall
verdict `HOLD ⚠️`, as defined below.

Evaluate these rows:

1. **Unpushed work**
   - `unpushed > 0` and clean tree → `✅ pass`, showing the count and local head.
   - `unpushed > 0` with `uncommitted=true` → `⚠️ hold`; commit or intentionally discard first.
   - `unpushed = 0` → `❌ block`; there is nothing to release.
   - Missing normalized service evidence → `➖ N/A` plus overall hold.

2. **CI**
   - A deploying service requires `ciBranch == gitBranch`; both revisions must be non-`-`, and
     `ciRevision == ciExpectedRevision` before interpreting native status.
   - Exact `success` → `✅ pass`; exact `failed`/`error` → `❌ block`; exact `running` → `⚠️ hold`.
   - `unknown`, unavailable provider evidence, missing fields, or any branch/revision mismatch →
     `⚠️ hold`. Never accept branch-only or stale green evidence.
   - A `non_deploying` service → `➖ N/A`; its release does not trigger a deployment pipeline.

3. **Contracts**
   - Apply step 4's pass, hold, block, and not-applicable mapping.

4. **Deploy order**
   - A `non_deploying` service → `➖ N/A` with no verdict impact. Do not require or evaluate order
     evidence because the service has no rollout prerequisites.
   - Valid `provider=none` → `➖ N/A` (`no ordering configured`) with no verdict impact.
   - Valid graph with no prerequisites → `✅ pass`.
   - For each prerequisite, use its digest row and optional `rolloutWatch` entry. Unpushed work,
     `N/M` with N<M, `cron:rollout`, or a pushed tag that has not settled means co-changing and
     yields `❌ block` (`waiting on <prereq>`).
   - A settled `N/N` deployment or `cron` marker with no unpushed work passes. If a required
     prerequisite has no observable deployment evidence, use `⚠️ hold`; do not infer it is live.
   - Unavailable order evidence → `➖ N/A` plus overall hold.

5. **Feature toggle**
   - No manifest toggle for the service means no toggle policy applies: `➖ N/A`.
   - A `parked` flag is `➖ N/A` and informational only. Include `superseded_by` and
     `reconsider_if` when present.
   - A `dark-release` flag is `➖ N/A` and informational; its later flip is a manual decision.
   - For an active declared flag, show the normalized live value and `flip_when`. A false value is
     `⚠️ hold` for the follow-up; true is `✅ pass`.
   - If an active flag is declared but normalized toggle evidence is missing, use `➖ N/A` plus
     overall hold. Do not invoke a project-specific toggle command.

6. **Live deployment**
   - Observable `N/N` or `cron` evidence → `✅ pass`, showing ready/tag/age.
   - Observable `N/M` with N<M or `cron:rollout` → `⚠️ hold`; avoid overlapping a rollout.
   - For `unknown`, `notfound`, `not-applicable`, or `-`, deployment evidence is unavailable:
     `➖ N/A`. This informational gate has no verdict impact unless the service is a prerequisite
     needed by the deploy-order gate.
   - A `non_deploying` service is `➖ N/A`.

## Verdict

End with exactly one verdict. Hard blockers take precedence over holds; holds take precedence over
readiness.

- **READY ✅** — unpushed work is clean, exact CI is green when applicable, no hard block or hold
  remains, and every applicable safety gate passed. N/A optional gates do not prevent readiness.
- **NOT READY ❌** — list every hard-blocking row, including no unpushed work, failed CI, stale
  contracts, or a co-changing prerequisite.
- **HOLD ⚠️** — no hard blocker exists, but one or more warnings or required evidence gaps remain.
  Name what must settle or become available.

Never suggest that the skill itself push. A user may later invoke `/release-manager` after reviewing
the evidence.

## Safety

This skill is strictly passive: never prompt and never mutate state. Never push, trigger or retry
CI, reconcile order, flip toggles, deploy, or edit `.release-state.json`.
