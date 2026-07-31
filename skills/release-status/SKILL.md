---
name: release-status
description: >
  Read-only release dashboard showing the release states a project can prove: unpushed work,
  normalized CI, deployment progress, deploy-order blockers, and optional feature-toggle gates.
  Passive: never prompts, pushes, or mutates state. Use for a quick release snapshot.
allowed-tools: "Read,Bash(./scripts/release-digest:*),Bash(./scripts/release-order:*),Bash(./scripts/contract-check:*)"
model-tier: standard
model: sonnet
effort: medium
version: "1.6.0"
author: "flurdy"
---

# Release Status

A read-only snapshot of release state across a project's services. It is the passive sibling of
`/release-manager`: show only states supported by available project evidence, take no action, and
ask no questions.

## When to Use

- A quick "what's the release situation right now" glance
- Before starting `/watch-release`, to see the baseline
- To inspect what `/release-manager` could evaluate without being prompted

For the interactive gatekeeper, use `/release-manager`. For a deep gate on one service, use
`/ready-to-release <service>`.

## Usage

```text
/release-status                 # all services
/release-status dispatch        # one service
```

## Instructions

1. **Gather the project digest.** Run the shared mechanical digest and pass through any service
   argument:

   ```bash
   ./scripts/release-digest
   ```

   The digest is the required project adapter. If it is missing, exits nonzero, omits the service
   header, or is malformed, print one bounded `_Release status unavailable: <reason>_` line and
   stop. Do not guess from project files or invoke a provider directly.

   Parse its ANSI-free sections:

   - `---META---`: `context=<name>`, `ciProvider=<circleci|github-actions|cloud-build|none>`, and
     `ci=<available|partial|unavailable>`. Provider identity is diagnostic only; decision and
     rendering logic use normalized fields below and never branch by provider.
   - `---SERVICES---`: one pipe-delimited row per service after this exact header:
     `service|unpushed|uncommitted|ci|ciBranch|gitBranch|head|deploy|tag|age|ciRevision|ciExpectedRevision`.
     - `unpushed` is commits ahead of upstream; `uncommitted` is `true|false`; `head` is local HEAD.
     - `ci` is `success|failed|running|error|unknown`. Treat it as `unknown` for display when
       `ciBranch != gitBranch`, either revision is `-`, or `ciRevision != ciExpectedRevision`.
       A provider's branch-only or stale green is not exact evidence.
     - `deploy`, `tag`, and `age` are optional deployment observations. An `N/M` value and
       `cron`/`cron:rollout` are observable; `unknown`, `notfound`, `not-applicable`, and `-` are
       not evidence of deployment state.
   - `---TOGGLES---`: optional `FLAG=value` lines. Use them only when the optional manifest context
     in step 2 declares toggle policy.

2. **Read optional manifest context.** If `docs/release-manifest.yaml` is absent or unreadable,
   use empty defaults for `toggles`, `parked`, `ignore`, and `non_deploying`. Otherwise read only
   those sections. Ordering never depends on parsing the manifest here.

2b. **Read optional ordering and contract coverage.** When the executable exists, run each command
   read-only:

   ```bash
   ./scripts/release-order
   ./scripts/contract-check coverage
   ```

   - From a successful, well-formed `release-order`, parse `---GRAPH---` as the effective
     `consumer: [providers]` map and `---DRIFT---` as informational drift evidence. If the command
     is missing, exits nonzero, or is malformed, use an empty dependency map and mark dependency-order evidence unavailable.
     Omit dependency drift; the dashboard still renders.
   - From a successful `contract-check coverage`, parse `GAP`/`OK` lines. If the command is missing,
     exits nonzero, or is malformed, omit contract-coverage observations; the dashboard still
     renders.

2c. **Read optional in-flight state.** Read `.release-state.json` at the project root only when it
   exists and is valid. Never create, repair, or rewrite it. `rolloutWatch` entries have the shape
   `<service>: { sha, fromTag }` and describe pushes whose new deployment has not been confirmed.
   Keep an entry only as potential context until step 3 establishes that deployment is observable
   for that service.

3. **Classify available capabilities before rendering.** Capabilities come from evidence, not
   project or provider names:

   - **CI exactness:** available per row only when normalized ref and revision fields match as
     described in step 1. Otherwise display `unknown` even if native status says success.
   - **Deployment observation:** a service is deployment-observable only when its `deploy` value is
     `N/M`, `cron`, or `cron:rollout`. Include the `deployed (ready/tag/age)` column when at least
     one displayed service is deployment-observable. If none is, omit the `deployed` column and
     omit rollout-derived observations; do not infer a rollout state from Git history, CI, a saved
     `rolloutWatch`, or naming conventions.
   - **Toggle policy:** available only when the manifest has a non-empty `toggles` or `parked` map.
     When both `toggles` and `parked` are empty, skip toggle evaluation entirely and omit toggle
     observations. Never infer a toggle system from source names or a non-empty digest section.
   - **Dependency order:** available only from a successful, well-formed `release-order` result;
     `provider=none` with an empty graph is valid evidence. When unavailable, omit `READY`,
     `WAITING`, and dependency-drift observations because prerequisite safety is not computable.
   - **Contract coverage:** available only from a successful, well-formed coverage result. Its
     absence removes coverage observations, not the service rows.

4. **Render one table**, skipping `ignore`d services:

   - Always show `service | unpushed | uncommitted | CI`.
   - Add `deployed (ready/tag/age)` only when deployment observation is available globally. Use `—`
     in that column for an individual service without observable deployment evidence.
   - Keep provider names out of column names and gate labels.

5. **Render observations only when computable.** This skill must never ask a question. It must
   never write state.

   - `⤴️ PUSHED — rolling out <service>` requires both a valid `rolloutWatch` entry and current
     observable deployment evidence for that service. When the live tag still equals `fromTag`,
     show `was <fromTag>, awaiting a new deployed tag`. When the tag moved but deployment remains
     `N/M` with N<M or `cron:rollout`, show `new tag <tag>, rollout still unsettled`. Only when the
     tag moved and deployment is settled may you note `✅ rolled out <service> <tag>`. Without
     observable deployment evidence, omit the observation rather than guessing.
   - `READY` requires valid dependency-order evidence. It means the service has unpushed commits,
     exact CI success, and no co-changing prerequisite in the effective map. A valid empty map can
     therefore yield `READY`; unavailable order evidence cannot.
   - `WAITING ON <prereq>` requires valid dependency-order evidence, a service with unpushed
     commits, and a prerequisite from the effective map that is co-changing. Unpushed work is
     always observable. Count a prerequisite as mid-rollout only when its current deployment is
     observable (`N/M` with N<M or
     `cron:rollout`) or when its valid `rolloutWatch` entry can be compared with observable current
     deployment evidence. A stable already-live prerequisite does not block.
   - `📊 DEPENDENCY DRIFT` appears only when valid order evidence contains concrete `new:` or
     `removed:` edges. `unmanaged`, `not-applicable`, absent, and malformed evidence are not drift.
   - `🔗 CONTRACT COVERAGE GAP` appears only for valid `GAP` evidence, formatted as
     `<provider>: <not-verified=…>`.
   - `CI RED` appears for exact `failed` or `error` evidence. `running` stays visibly in progress;
     stale or mismatched evidence displays as `unknown`.
   - `TOGGLE READY` requires declared toggle policy, a false manifest-referenced flag, and settled
     observable deployment evidence for its gating service. A `status: dark-release` toggle is
     shown as `🌓 DARK RELEASE <flag> — flip is a manual call once validated`. A `parked` flag is
     never ready; list it at most once in a quiet parked footnote. If deployment or toggle evidence
     is unavailable, omit this state instead of reporting a failure.

6. **Summarize in one line.** Count only rendered states, for example:
   `3 ready, 1 waiting, 1 CI red, 2 coverage gaps`. Omit zero-count capability categories that were
   not available. Keep the full result to roughly one screen.

## Notes

- This skill is strictly read-only: never prompt, push, file work, reconcile drift, trigger CI,
  mutate deployment, or update `.release-state.json`.
- `release-digest` is the one required project adapter. Deployment and toggle implementations are
  deliberately opaque to this skill; normalized evidence decides what can be shown.
- `release-order` and `contract-check coverage` enrich the dashboard when installed. Their absence
  must not hide basic Git and CI status.
