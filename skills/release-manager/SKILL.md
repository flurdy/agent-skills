---
name: release-manager
description: >
  Interactive release gatekeeper for letterbox — runs one tick of the release dashboard,
  then prompts to push / defer / cancel each ready service, auto-files a bead on CI failure,
  enforces deploy order, watches rollouts, syncs k8s config and schedules the restarts that
  applied config needs, and nudges feature toggles. Drive it on a loop with
  /watch-release. Advisory: it only pushes after you explicitly choose "push".
allowed-tools: "Read,Write,Skill,AskUserQuestion,Bash(./scripts/release-digest:*),Bash(make feature-toggles-disabled:*),Bash(make git-push:*),Bash(make k8s-sync:*),Bash(kubectl rollout restart:*),Bash(./scripts/mgit log:*),Bash(./scripts/pact-graph:*),Bash(./scripts/contract-check:*),Bash(bd create:*),Bash(bd list:*)"
model-tier: long-context-audit
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
effort: medium
version: "1.10.0"
author: "flurdy"
---

# Release Manager

The interactive gatekeeper. One invocation = one **tick**: gather release state, evaluate
gates, take care of CI failures, and prompt you for a decision on anything that's ready to
ship. Designed to run on a loop in a dedicated tab via `/watch-release`.

It is **advisory and explicit**: nothing gets pushed unless you choose `push` at the prompt
(honors the project rule "never auto-push, always ask"). The one thing it does autonomously is
**file a bead when CI is red** — deduplicated, so it never double-files.

## When to Use

- Driven by `/watch-release` (adaptive cadence — step 8b's `next-tick:` line paces the loop) in a kitty tab during parallel work.
- Ad-hoc, when you want to be walked through what's ready to push/release right now.

For a passive look with no prompts, use `/release-status`. For a deep gate on a single service,
use `/ready-to-release <service>`.

## Usage

```
/release-manager              # one tick across all services
/release-manager dispatch     # one tick scoped to a service
```

## Setup

This skill ships `pact-graph` (the deploy ORDERING authority — also used by /release-status
and /ready-to-release). On first run, ensure the project symlink exists:

```bash
ln -sfn "$SKILLS_DIR/release-manager/scripts/pact-graph" ./scripts/pact-graph
chmod +x ./scripts/pact-graph
```

Where `$SKILLS_DIR` resolves to `${CLAUDE_HOME:-$HOME/.claude}/skills`. The script finds the
project root by walking up to the nearest `.mgit.conf` (same convention as contract-check);
`docs/release-manifest.yaml` and `.release-state.json` stay project-local.

## State file

Per-item decisions persist in `.release-state.json` at the repo root (gitignored) so the
watcher doesn't re-nag every tick. Create it if missing. Schema:

```json
{
  "deferred":       { "dispatch": { "untilEpochTick": false } },
  "cancelled":      { "web": { "sha": "<short sha when cancelled>" } },
  "ciBeads":        { "account@master": "letterbox-xyz" },
  "rolloutWatch":   { "dispatch": { "sha": "<pushed sha>", "fromTag": "<live tag at push time>" } },
  "configApply":    { "letterbox-app-config": { "baseline": "<resourceVersion at sync time>", "consumers": ["web"], "syncedSha": "<k8s repo sha>" } },
  "restartPending": { "web": { "config": "letterbox-app-config", "appliedRV": "<resourceVersion when Flux applied>" } },
  "restartWatch":   { "web": { "for": "letterbox-app-config", "ageBaseline": "<pod age at restart>" } },
  "quietStreak":    0
}
```

- `deferred` — snoozed this session; cleared and re-prompted on the next tick (defer = "ask me again later").
- `cancelled` — suppressed until the service's unpushed HEAD sha changes (new commits arrive).
- `ciBeads` — dedup map of auto-filed beads → bead id. Keys: `<service>@<branch>` for red CI
  builds; `coverage:<provider>` for contract-coverage gaps. Drop a key when its problem clears.
- `quietStreak` — count of consecutive **cold** ticks (nothing in flight, nothing queued). Drives
  the adaptive back-off in step 8: reset to 0 on any hot/warm tick, incremented on a cold one.
  Ignored entirely under a fixed-interval loop.
- `rolloutWatch` — services pushed in a prior tick, awaiting their new tag in K8s. `fromTag` is the
  live deploy tag captured **at push time** (the pre-push baseline). The exact post-push tag can't
  be known at push: CircleCI tags images `<IMAGE_BASE_VERSION>.<CIRCLE_BUILD_NUM>` (e.g. `1.0.<N>`)
  and `CIRCLE_BUILD_NUM` is assigned only when the build runs (after the push) and is not
  `previous+1`. So confirmation (step 4) is "the live tag has moved **off** `fromTag`", not an
  exact-tag match. `fromTag` may be `null` if deploy-status was unavailable at push — step 4 then
  falls back to the older heuristic.
- `configApply` / `restartPending` / `restartWatch` — the **config-restart state machine**. Every
  service reads its ConfigMaps/Secrets only at startup, so a synced config change does NOT take
  effect until its consumers get a `kubectl rollout restart` — and only *after* Flux has applied it
  (restarting sooner just reloads the old config). The consumer set is **derived, never curated**:
  the digest's `---CONFIG---` `restart` column (deployment yamls for who mounts the map; per-key
  source grep to narrow shared maps), minus `manifest.config_restarts.suppress`.
  Three states, each a separate tick, mirroring `rolloutWatch`'s push→confirm pattern:
  - `configApply` — config synced via `make k8s-sync` (step 5b) and awaiting Flux. `baseline` is the
    resource's live `resourceVersion` captured **at sync time** (the pre-apply baseline, exactly like
    `fromTag`); step 4b confirms apply when it moves **off** `baseline`. `consumers` = the derived
    restart set frozen at sync time (`["?"]` if underivable); `syncedSha` = the k8s repo sha that
    shipped it.
  - `restartPending` — Flux applied the config (step 4b saw `resourceVersion` move); the listed
    services now await a restart decision. Survives a `defer` so it re-prompts next tick. `appliedRV`
    is the resourceVersion observed at apply (audit/debug only).
  - `restartWatch` — restart issued (step 7b ran `kubectl rollout restart`); awaiting pod cycle.
    `ageBaseline` is the pod age at restart time — step 4b confirms when pods show fresh + ready.

## Command discipline

Every Bash call in a tick must match `allowed-tools` **as written** — a plain invocation of one
listed script/command. Never wrap them in `for` loops, variable expansion, command substitution,
or pipes (`| head`, `| grep`): the composed command can't match `Bash(./scripts/mgit log:*)`, so
it stalls the whole watcher loop on a permission prompt until a human answers. If you want the
same fact for several services, that's a sign it belongs in the digest — and the per-service
basics (`unpushed`, `head`, …) already do: read the columns, don't shell out. The one sanctioned
drill-down is the step-7 `why?` flow — run `./scripts/mgit log <service> --oneline @{u}..HEAD`
as one plain call per service (parallel calls are fine; loops are not).

## Per-tick flow

1. **Gather.** Run the shared mechanical digest — it keeps the raw kubectl/CircleCI/git dumps out
   of this loop's context by emitting only a compact parsed result, so no subagent is needed:

   ```bash
   ./scripts/release-digest          # all services (or pass a service arg to scope the tick)
   ```

   Parse the delimited sections:
   - `---META---`: `context=<kubectl ctx>`, `ci=<available|unavailable>` (CI is `available` only
     when `CIRCLECI_TOKEN`/`.env.circleci` is present; otherwise every `ci` field is `unknown`).
   - `---SERVICES---`: one pipe-delimited line per service after the header line:
     `service|unpushed|uncommitted|ci|ciBranch|gitBranch|head|deploy|tag|age`.
     - `unpushed` (int), `uncommitted` (`true|false`), `head` = short sha of the current local
       HEAD (`-` if no checkout) — the tip identity for every sha comparison/record this tick
       (step 6 `cancelled` check, step 7 `rolloutWatch.sha`); never run per-service git commands
       to re-derive it.
     - `ci` ∈ `success|failed|running|error|unknown`; `ciBranch` = the branch the latest pipeline
       ran on (`-` if none). `gitBranch` = the service repo's current branch (what `git push`
       sends). Both branches are needed for the step-6 branch-match gate.
     - `deploy` = a Deployment's `<ready>/<desired>` (e.g. `1/1`, `0/1`); for **CronJob-backed
       services** (digest, patrol, reconciler) it is a marker, not replicas: `cron` = the service's
       CronJobs all share one image (settled) and `cron:rollout` = images differ (Flux mid-bump).
       Also `notfound`/`unknown`. `tag` = live image tag, `age` = pod age (Deployment) or most-recent
       run age (CronJob). Treat tag-movement (not ready replicas) as the rollout signal for CronJob
       services in steps 4 and 6.
   - `---TOGGLES---`: `FLAG=value` lines — **compact by default**: only false-valued flags and
     those referenced in the manifest's `toggles:`/`parked:` sections (so an already-flipped
     dark-release flag still shows its live value). A trailing `# compact: …` line notes how many
     were hidden. This is exactly what steps 5/5b need. For the complete map (all true flags +
     membership tiers), run `./scripts/release-digest --full-toggles`; for the disabled-only view,
     `make feature-toggles-disabled`.
   - `---K8S---`: state of the `kubernetes` GitOps repo (which ships via `make k8s-sync`, not as a
     `---SERVICES---` entry): `present=<true|false>`, then when present `branch`, `head` (short
     sha), `unpushed` (int), `uncommitted` (bool), `behind` (int, from the last-known remote ref —
     may be stale). Consumed by step 5b.
   - `---CONFIG---`: one pipe-delimited line per ConfigMap/Secret referenced by a Deployment in the
     `kubernetes` GitOps repo, after the header: `name|kind|resourceVersion|changed|mounts|restart`.
     All **derived** by the digest (deployment yamls for who-mounts-what; per-key source grep for
     shared maps) — nothing curated. `kind` ∈ `configmap|secret|notfound`; `resourceVersion` is the
     live value (or `-`) — the apply baseline steps 5b/4b watch; `changed` (`true|false`) means a
     file defining this resource is in the repo's unpushed diff, i.e. `make k8s-sync` ships it
     **this** tick; `mounts` = comma-list of Deployment services mounting it (CronJob services never
     appear — no restart needed); `restart` = the derived restart set for this change: `-` (not
     changed), a comma-list of services, or `?` (changed but underivable — warn, don't guess).
     Consumed by steps 5b (register) and 4b (confirm apply).

1b. **Scan dependencies + contract coverage** (cheap, no subagent needed — compact output):

   ```bash
   ./scripts/pact-graph              # ordering authority
   ./scripts/contract-check coverage # CI verification coverage
   ```

   If `./scripts/pact-graph` is missing, create the symlink first (see Setup).

   From `pact-graph`: `---GRAPH---` (`consumer: [providers]`) and `---DRIFT---` (`in-sync` or
   `new:`/`removed:` edges). From `contract-check coverage`: per-provider `GAP`/`OK` lines.
   Keep these for steps 2b, 6, 6b. (pact-graph = ordering; contract-check = contract health.)

2. **Load context.** Read `.release-state.json` (create `{}`-shaped default if absent) and
   `docs/release-manifest.yaml`. From `order`, build the **effective dependency map** =
   `(derived ∪ manual) − suppress`. Also read `toggles`, `parked`, `ignore`,
   `non_deploying`, and `config_restarts.suppress` (maps whose changes must never produce a
   restart prompt — vetoes the digest's derived `restart` column in steps 5b/7b).

2b. **Dependency drift reconcile.** If `---DRIFT---` is not `in-sync`, the pacts have diverged
   from `order.derived`. Print the `new`/`removed` edges, then prompt once (AskUserQuestion):
   *"Reconcile dependency map into the manifest?"* — `reconcile` / `skip`.
   - `reconcile` → `./scripts/pact-graph --write` (rewrites the GENERATED block), then note any
     **new** edges so you can decide whether any belong in `order.suppress` (backward-compatible,
     shouldn't gate). Re-read the manifest after writing.
   - `skip` → leave it; drift resurfaces next tick.

3. **CI failures → auto-bead (dedup).** For each service whose `ci` is `failed`/`error`:
   - Compute key `<service>@<branch>`. If it's already in `state.ciBeads`, skip (already filed).
   - Otherwise verify no open bead exists: `bd list --status=open` and grep for a matching
     `CI FAILED: <service>` title. If none, file one:
     ```bash
     bd create --title="CI FAILED: <service>" --type=bug --priority=1 --labels "<service>" \
       --description="CI build failed on <branch>. Detected by /release-manager."
     ```
   - Record `state.ciBeads["<service>@<branch>"] = <new bead id>`. Print `🔴 CI FAILED <service> → filed <bead id>`.
   - When that service's CI later goes green, drop the key from `ciBeads` so a future failure re-files.

4. **Rollout confirmation.** For each entry in `state.rolloutWatch`, compare the live deploy
   `tag` against the recorded `fromTag` baseline (the tag that was live when you pushed). Rollout
   is confirmed when the live tag has **moved off** `fromTag` — Flux has applied the new image:
   - **Deployment service:** confirmed when the live `tag` differs from `fromTag` **and** it's
     `ready` (e.g. `1/1`). Print `✅ ROLLED OUT <service> <tag>` (was `<fromTag>`) and remove it.
   - **CronJob service** (`deploy` is `cron`/`cron:rollout`): no ready replicas — confirmed when
     the live `tag` differs from `fromTag` **and** the marker is `cron` (settled, not
     `cron:rollout`). Print `✅ ROLLED OUT <service> <tag>` (was `<fromTag>`) and remove it.
   - **`fromTag` is `null`** (deploy-status was unavailable at push): fall back to the older
     heuristic — tag looks advanced from what you'd expect **and** the pod/last-run age is fresh
     (recent). Less precise; note `…rolling out <service> (no baseline)`.
   - Otherwise (live tag still equals `fromTag`, or not yet ready/settled) leave it — optionally
     note `…rolling out <service>`.

4b. **Config-apply & restart confirmation.** Two follow-on confirmations for the config-restart
   machine (both read this tick's `---CONFIG---` and `---SERVICES---`):

   - **`configApply` → `restartPending` (Flux applied the config).** For each `state.configApply`
     entry, look up the resource's current `resourceVersion` in `---CONFIG---`. If it has **moved
     off** `baseline`, Flux has applied the synced change. Print `✅ CONFIG APPLIED <name>`. If
     `consumers` is `["?"]` (derivation failed at sync time), don't guess: print
     `⚠️ <name> applied — consumers underivable, restart manually if a service reads it` and just
     remove the entry. Otherwise, for each `consumer`, queue a restart —
     `state.restartPending[<consumer>] = { config: <name>, appliedRV: <new resourceVersion> }` —
     **unless** that consumer's new pods will already pick the config up on their own, in which case
     skip it (no restart needed):
     - consumer is in `state.rolloutWatch`, or has `unpushed > 0`, or shows `deploy` mid-rollout —
       it's deploying anyway; its fresh pods read the applied config. Note `…<consumer> deploying —
       picks up <name> without a restart`.
     Then remove the `configApply` entry. If `resourceVersion` is still `baseline` (or `-`/notfound),
     leave it — note `…config applying <name>`. (Over-registration is harmless: a config that didn't
     actually change never moves off `baseline`, so it just sits until you sync something — prune
     stale entries if a `syncedSha` is long gone.)
   - **`restartWatch` → done (pods cycled).** For each `state.restartWatch` entry, the restart is
     confirmed when the service shows `deploy` ready (e.g. `1/1`) with a **freshly-aged** pod (the
     `age` in `---SERVICES---` is younger than `ageBaseline` — pods were replaced). A config restart
     does **not** move the image `tag`, so age-reset + ready is the signal (not tag movement like
     step 4). Print `✅ RESTARTED <service> (config <for>)` and remove. Otherwise leave it — note
     `…restarting <service>`. (Heuristic, like step 4's `fromTag: null` fallback: if age is
     ambiguous, prefer leaving it one more tick over a false confirm.)

5. **Toggle readiness.** For each `manifest.toggles` entry: if its `service` is rolled out
   (a Deployment showing `deploy ready`, or a CronJob service showing the settled `cron` marker)
   AND the live flag value is still `false`, print
   `🚩 TOGGLE READY <flag> — <flip_when>`. (Informational; flipping happens via the K8s repo,
   not here.) Also flag toggles that are referenced in code/manifest but missing from prod if
   you spot them. Exceptions:
   - A toggle with `status: dark-release` is in a deliberate shadow launch — print
     `🌓 DARK RELEASE <flag> — flip is a manual call once validated`, do NOT nudge it as ready.
   - **Skip `manifest.parked` flags entirely** — they are deliberately off (e.g. superseded by
     another path); never nudge them. At most show once as a footnote
     (`<flag> parked — superseded by <x>; reconsider_if <y>`).

5b. **K8s config sync watch.** The `kubernetes` GitOps repo ships via `make k8s-sync` (pull
   `--rebase` + push → Flux applies to the cluster), **never** `make git-push` — so it's in
   `manifest.ignore` and is *not* a step-6 push candidate. But committed-but-unsynced config there
   is a frequent **prerequisite** for a service deploy: ship the service while its ConfigMap /
   Secret / manifest change is still local and the release breaks. So the gatekeeper watches its
   state even though it never `git-push`es it.

   Read the digest's `---K8S---` section: `present`, and (when present) `unpushed`, `uncommitted`,
   `behind`. If `present=false`, skip silently. If `unpushed=0` **and** `uncommitted=false` **and**
   `behind=0`, the repo is in sync — skip silently.

   Otherwise it has **pending config**. Surface it prominently (this is high-signal — it gates real
   deploys):

   ```
   ⚠️ KUBERNETES UNSYNCED — <unpushed> unpushed, <uncommitted?>, <behind> behind on <branch>; run `make k8s-sync`
   ```

   Then prompt **once** (AskUserQuestion), *before* the step-7 service-push prompts so config lands
   first: *"Sync the kubernetes config now?"*
   - `sync` → run `make k8s-sync`. On success print `✅ k8s-synced`; the change is now en route to
     the cluster via Flux. On failure (rebase conflict, push rejected — `make k8s-sync` does
     `pull --rebase` then push), surface stderr verbatim and **do not retry** — a conflict is a
     human call. `make k8s-sync` never edits the repo or force-pushes.
     **Then register restart watches:** for each `---CONFIG---` line with `changed=true` (it was part
     of the commits just synced), unless the name is in `manifest.config_restarts.suppress`, record
     `state.configApply[<name>] = { baseline: <its resourceVersion from THIS tick's ---CONFIG--->,
     consumers: <its restart column, split on commas>, syncedSha: <the `head` from this tick's
     ---K8S--- — pre-sync, fine for this audit-only field> }`. The
     `resourceVersion` read *now* (before Flux applies) is the pre-apply baseline step 4b watches to
     move off — exactly like `fromTag` at push. A `restart` of `?` still registers (with consumers
     `["?"]`) so the apply gets confirmed — step 4b then warns instead of queuing restarts. Print
     `🔁 watching restart for <name> → <consumers>`.
   - `skip` → leave it. It resurfaces next tick (no state recorded — git is the source of truth),
     and step 7 carries the caution into any push prompt below.

   `uncommitted=true` means there are **uncommitted** edits in the k8s repo — `make k8s-sync` won't
   ship those (only committed commits push). Note that explicitly: `…uncommitted edits won't sync
   until committed`.

   Carry an `k8sUnsynced` boolean (true when pending config exists and wasn't just synced) into
   step 7 and the step-8b cadence.

6. **Evaluate ready-to-push.** Build the candidate set: anything with `unpushed > 0`, excluding
   `manifest.ignore`, excluding `cancelled` whose stored sha still matches the digest's `head`
   column (a moved `head` means new commits landed — the cancel expires; this is a pure data
   comparison, no git commands). Then
   **partition** it:
   - **Non-deploying repos** (in `manifest.non_deploying`, e.g. root, functional-tests) are NOT
     CircleCI services — `git push` triggers no prod deploy, there's no pipeline to gate on and no
     rollout to watch. **Skip every gate below** (CI/branch-match, deploy-order, contract
     staleness/coverage) — none of their assumptions apply. Mark each `📦 READY (non-deploying)`
     and carry it straight to step 7 with the non-deploying label. Do **not** treat their
     `ci=unknown` as a stop; `unknown` there is expected, not a risk.
   - **Deploying services** (everything else) run the full gate sequence below. For each:
   - **Pre-push verification gate (safety-critical — evaluate FIRST, before any other gate).**
     `make git-push <service>` pushes the unpushed commits straight to the service's remote, and
     CircleCI auto-deploys to **production** on green — there is no further human gate after the
     push. So a service is only a push candidate when its branch is in a known-good state. Two
     facts make this subtle:
     1. `ci-status.sh` reports the **latest pipeline on the service's repo** — i.e. the last
        *pushed* commit's build, on whatever branch that pipeline ran. It does **not** and
        **cannot** reflect the candidate: the candidate commits are still unpushed, so remote CI
        has never seen that SHA. Treat remote CI as a statement about the branch's *already-live*
        tip, never about what you are about to push.
     2. Therefore "remote CI is green" is necessary-but-not-sufficient, and "remote CI is
        red/running/unknown" is a hard stop on offering the push.

     Apply, in order, and **drop from the prompt set** (print the line, don't ask) on any stop:
     - **Branch match.** Confirm `ciBranch` equals `gitBranch` (both from the step-1 digest). If
       they differ, the latest pipeline ran on an unrelated branch — the status says nothing about
       the commits you'd push — so treat it as `unknown` below.
     - `ci` = `failed`/`error` → mark `🔴 CI RED — not offering push` and drop. The branch tip
       you'd be stacking onto is broken; pushing risks a bad prod deploy the moment it goes
       green. (Step 3 already filed the bead.)
     - `ci` = `running` → mark `⏳ CI RUNNING — wait` and drop this tick. The branch tip is
       mid-build and unsettled; it resurfaces next tick.
     - `ci` = `unknown` (no `CIRCLECI_TOKEN`, no pipeline, or branch mismatch above) → mark
       `❔ CI UNKNOWN — verify locally before pushing` and drop, **unless** you (the operator)
       have confirmed the service's tests pass locally this session — only then keep it as READY.
       Never silently offer a push on `unknown`.
     - `ci` = `success` **and** branch matches → the branch tip is green. Keep it, but the
       candidate is **still remotely unverified** (green is for the last pushed SHA, not the N
       unpushed commits). Carry this caveat into the step-7 prompt.
   - **Deploy order (the rate limiter).** Look up the service's prereqs in the effective
     dependency map. A prereq P **blocks** this consumer only if P is *co-changing* — any of:
     (a) P has `unpushed > 0`, (b) P is mid-rollout — a Deployment showing `deploy` `N/M` (N<M),
     or a CronJob service showing `cron:rollout` (its CronJobs not yet on one tag) — or (c) P is in
     `state.rolloutWatch` (pushed but rollout not yet confirmed). If any prereq blocks, mark
     `WAITING ON <prereq>` and drop from the prompt set (print the line, don't ask). A stable,
     already-live prereq does NOT block — its contract is already satisfied.
     > This is what paces releases: pushing a provider this tick auto-defers its consumers to
     > a later tick, because the consumer can't clear this gate until the provider leaves
     > `rolloutWatch` (step 4 confirms its rollout). The dependency graph IS the rate limit.
   - **Contract staleness.** If the service touches connectors/contracts, run
     `Skill /contract-check status` (NOT a normalize/`--check` proxy — that only checks file
     formatting, not verification). If pacts are out of sync, mark `CONTRACTS STALE` and warn
     (don't offer push until resolved).
   - **Contract coverage.** Cross-reference step 1b's `contract-check coverage` output: if the
     service is a provider with a `GAP` line, warn `⚠️ <svc> contract coverage gap
     (not-verified=<…>)` — its change may not be verified against all consumers. Don't
     hard-block, but make it loud in the prompt.
   - Otherwise it's **READY**.

6b. **Contract coverage beads (dedup).** For each `contract-check coverage` `GAP` line, treat
   it like a CI failure for tracking: key `coverage:<provider>`. If not already in
   `state.ciBeads` and no open bead titled `CONTRACT COVERAGE: <provider>` exists
   (`bd list --status=open`), file one:
   ```bash
   bd create --title="CONTRACT COVERAGE: <provider>" --type=bug --priority=2 --labels "<provider>" \
     --description="<provider> CI does not verify all consumer contracts (not-verified=<…>). Detected by /release-manager via ./scripts/contract-check coverage."
   ```
   Record `state.ciBeads["coverage:<provider>"] = <id>`; drop it when the gap later clears.

7. **Prompt per READY service, capped at 3 this tick.** Order candidates **providers/leaves
   first** — a service that others depend on (appears as a provider in the effective map) before
   its consumers — so the safe-to-ship-first work surfaces first; sort any **non-deploying repos
   last** (they carry no deploy risk). Take the first 3; if more remain, print
   `… N more ready — re-run /release-manager for the rest`. Prompt each (AskUserQuestion, one
   question per item, options `push` / `defer` / `cancel` / `why?`). Each question must state the
   push consequence plainly, and the wording depends on the kind:
   - **Deploying service:** *"push deploys N unpushed commit(s) to prod on CI-green; remote CI has
     not verified these commits (its green is for the last pushed SHA)."*
   - **Non-deploying repo:** *"push sends N unpushed commit(s) to the <repo> remote — no CI gate,
     no prod deploy, no rollout to watch."*
   - **When `k8sUnsynced` (step 5b) and the candidate is a deploying service:** append a caution to
     the push consequence — *"⚠️ kubernetes has unsynced config (`make k8s-sync` not yet run) — if
     this deploy depends on it, sync first or the release may break."* This is a caution, **not a
     hard block** — the skill can't know whether *this* service needs *that* config, so it surfaces
     the risk and leaves the call to you. (A hard prerequisite belongs in the manifest's `order`,
     not here.)
   - `push` → `make git-push <service>`; print `⬆️ pushed <service>`. On success, **for a
     deploying service** add it to `state.rolloutWatch` as `{ sha: <the service's `head` from the
     step-1 digest>, fromTag: <the service's current live deploy tag from the step-1 digest> }`. `fromTag` is the pre-push
     baseline step 4 watches to move off (the exact post-push tag isn't knowable at push — see the
     State file note); use `null` only if deploy-status had no tag for the service. A
     **non-deploying repo** is NOT added to `rolloutWatch` (there is no rollout) — it just
     disappears from the candidate set once pushed.
   - `defer` → add to `state.deferred`; it'll resurface next tick.
   - `cancel` → add to `state.cancelled` with current HEAD short sha; stays quiet until new commits.
   - `why?` → show `./scripts/mgit log <service> --oneline @{u}..HEAD` (the unpushed commits) plus
     the gate reasoning (CI/contract/coverage/order), then re-ask the same question for that service.

7b. **Restart prompt per `restartPending` service.** These are services whose startup config Flux
   applied (step 4b queued them); they need a `kubectl rollout restart` to read the new values. For
   each `state.restartPending` entry:
   - **Re-check it's still needed first.** If the service has since deployed a new image (it left
     `rolloutWatch`, or its `tag` advanced this tick), its fresh pods already loaded the applied
     config — drop the entry silently (print `…<service> redeployed — config picked up, no restart`)
     and skip the prompt. This guards the case where a normal deploy overtakes the config restart.
   - Otherwise prompt (AskUserQuestion, one per service, options `restart` / `defer` / `skip`). State
     the consequence plainly: *"restart deployment/<service> to load applied config <config> — brief
     rolling pod cycle, **no new image**, no CI gate, no prod deploy."* CronJob-backed services never
     appear here (the digest derives mounts from `deployment.yaml`s only — CronJobs read fresh config
     each run); if one somehow does, skip it with that note.
     - `restart` → run `kubectl rollout restart deployment/<service> -n apps`; print
       `🔄 restarted <service>`. On success move it from `restartPending` to
       `state.restartWatch[<service>] = { for: <config>, ageBaseline: <the service's current pod age
       from this tick's ---SERVICES--->`. Step 4b confirms the cycle (age resets + ready).
     - `defer` → leave it in `restartPending`; it re-prompts next tick.
     - `skip` → remove from `restartPending` (you've decided this service doesn't need the kick —
       e.g. it actually re-reads config live). It will not re-prompt unless a future sync re-queues it.
   This is the one prod action beyond push/sync; like them it's **confirm-gated** — never an
   autonomous restart.

8. **Persist & summarise.** Write the updated `.release-state.json`. Print a one-line tick
   summary: e.g. `tick: 2 pushed, 1 restarted, 1 config applying, 1 deferred, 1 waiting, 1 CI bead,
   1 coverage gap, 1 toggle ready`.

8b. **Adaptive cadence recommendation.** Classify this tick so an adaptive watcher (`/watch-release`,
   default mode) can pace the next run. A fixed-interval loop ignores this line. Pick the **first**
   bucket that matches:

   - **hot** — something is *in flight or imminent*: `state.rolloutWatch` is non-empty (a push is
     mid-rollout — the live tag could move any tick), **or** `state.configApply` is non-empty (Flux
     mid-apply — `resourceVersion` could move any tick), **or** `state.restartWatch` is non-empty
     (pods mid-cycle), **or** a candidate's `ci=running`, **or** a service was pushed or restarted
     *this* tick. External events that resolve in minutes; check again soon to catch them. →
     **~180s** (3 min — inside the prompt-cache window, but not so tight it burns the cache several
     times per CircleCI build).
   - **warm** — nothing in flight, but *pending work*: `state.deferred` non-empty, `state.restartPending`
     non-empty (config applied, awaiting your restart answer), unreconciled dependency drift (step 2b
     skipped), `k8sUnsynced` (step 5b — pending config not yet synced), or ready candidates still
     awaiting your push/defer answer, or any `unpushed > 0` not yet actioned. → **~600s** (10 min).
   - **cold** — fully settled: no `rolloutWatch`, no `configApply`/`restartPending`/`restartWatch`,
     no running CI, nothing pushed or restarted this tick, nothing deferred, nothing unpushed, no
     ready candidates. → escalating back-off: **1200s** first cold tick, **1500s** second, **1800s**
     (30 min) third and beyond.

   Maintain `state.quietStreak`: **cold** → increment, then `seconds = min(1800, 1200 + 300 × (quietStreak − 1))`;
   **hot/warm** → reset to 0. Persist it alongside the rest of the state in step 8.

   Print one machine-readable line **last**, after the tick summary, so the watcher can parse it:

   ```
   next-tick: {hot|warm|cold} (~{seconds}s) — {one-clause reason}
   ```

   e.g. `next-tick: hot (~180s) — dispatch mid-rollout` / `next-tick: cold (~1500s) — all settled, 2 quiet ticks`.
   The seconds are a recommendation; the adaptive loop clamps to `[60, 3600]`. Never let a hot
   recommendation drop below ~120s — a CircleCI build takes minutes, so tighter polling just burns
   the cache without catching the rollout sooner.

## Caveats

- On a `/loop`, an AskUserQuestion **blocks the tick until you answer** — intended for an
  attended watcher tab, but an unattended tab will pause at the first prompt. If you want it to
  run unattended, prefer `/release-status` (no prompts) on the loop and act manually.
- `push` runs `make git-push <service>` which triggers a production deploy (CircleCI auto-deploys
  on green, no further human gate). The prompt is the explicit authorization; there is no
  auto-push. The step-6 pre-push gate withholds the prompt entirely while CI is red/running/
  unknown for the service's branch.
- **K8s config (step 5b) is watched but never `git-push`ed.** The `kubernetes` repo is in
  `manifest.ignore` so it's never a `make git-push` candidate — but the skill still reads its state
  from the digest's `---K8S---` section and, when it has unsynced config, warns and offers
  `make k8s-sync` (on explicit confirm — it's prod-affecting via Flux, same "always ask" rule as
  service pushes). It's a **caution, not a hard gate** on dependent service pushes: the skill can't
  know which service needs which config. A true ordering prerequisite belongs in the manifest's
  `order`.
- **Config restarts (steps 5b→4b→7b) are spread across ticks, never bundled.** A synced ConfigMap/
  Secret only restarts a startup-reading service after Flux *applies* it — restarting in the same
  tick as the sync would just reload the **old** config (Flux hasn't reconciled yet). So the machine
  runs sync (register) → confirm apply (`resourceVersion` moves off baseline) → confirm-gated
  `kubectl rollout restart` → confirm pod cycle, one hop per tick, mirroring `rolloutWatch`. The
  restart is the third prod action (after `make git-push` / `make k8s-sync`), and like them it's
  **confirm-gated** — never autonomous. The restart set is **derived, never curated** (the digest
  reads the GitOps repo's deployment yamls for who mounts each map, and narrows shared maps per
  changed env-var key by grepping each mounting service's source — keys are referenced verbatim,
  e.g. `${?FT_SES_API}`); `manifest.config_restarts.suppress` is the only human knob (veto). When
  derivation can't resolve a change (`restart=?`), the skill warns "restart manually" rather than
  guessing. CronJob-backed services are excluded by construction (mounts come from `deployment.yaml`s
  only — they read fresh config on their next run). Apply-confirm uses `resourceVersion` movement;
  restart-confirm uses pod age-reset (a config restart doesn't move the image tag), so it's
  heuristic — it prefers waiting a tick over a false confirm.
- **Remote CI never verifies the candidate.** `ci-status.sh` reports the latest pipeline on the
  repo — the last *pushed* SHA — so it cannot have run the unpushed candidate commits. A green CI
  is a statement about the branch's already-live tip, not about what you're about to ship; the
  only true verification of the candidate is local tests before push (or the post-push pipeline
  that runs once the commits land). The gate uses CI red/running/unknown as a hard stop, and
  surfaces "candidate remotely unverified" in the push prompt even when CI is green.
- Needs `CIRCLECI_TOKEN` and kubectl context `paperboy` for full data; degrade any missing
  section to `unknown` rather than failing the tick.
- `.release-state.json` is gitignored and local — defer is per-session, cancel persists until
  new commits land on that service.
- The deploy-order gate only blocks on *co-changing* providers (unpushed / mid-rollout / in
  `rolloutWatch`), never on stable live ones — so it paces same-tick provider+consumer pushes
  without permanently withholding independent work. The 3-per-tick cap is a separate backstop
  against prompt overload; together they keep each tick small and dependency-safe.
- `./scripts/pact-graph` is pure-filesystem (no tokens/network) and owns the manifest's
  `order.derived` block between its markers; humans own `order.manual` / `order.suppress`.
  `--write` is only invoked via the step 2b reconcile prompt — never silently.
