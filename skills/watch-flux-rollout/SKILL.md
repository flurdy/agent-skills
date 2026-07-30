---
name: watch-flux-rollout
description: >
  After a push or merge, watch a CircleCI + FluxCD deploy until it lands — CircleCI green for
  the commit, then the k8s Deployment's image tag moves off its pre-push baseline and pods go
  ready — then run a read-only smoke test scoped to the change. Goal-terminating loop — stops
  when the rollout lands and the smoke completes, or when it fails.
allowed-tools: "Read,Write,AskUserQuestion,Skill,Bash(~/.agents/skills/watch-flux-rollout/scripts/rollout-status.sh:*),Bash(~/.agents/skills/watch-flux-rollout/scripts/default-head-sha.sh:*),Bash(~/.agents/skills/circleci-status/scripts/status.sh:*),Bash(git:*),Bash(gh:*),Bash(curl:*),Bash(date:*),Bash(kubectl get:*),Bash(kubectl config current-context:*),mcp__claude-in-chrome__*,mcp__playwright__*"
model-tier: standard
model: sonnet
effort: medium
version: "1.1.0"
author: "flurdy"
---

# Watch Flux Rollout

Watch a CircleCI + FluxCD deploy of one commit until it's live, then smoke-test the change —
the kubectl/CircleCI sister of `/watch-rollout` (which watches GitHub-Actions CD). Built for
single-repo services deployed the Flux image-automation way: CircleCI builds and pushes an
image tagged `<base>.<CIRCLE_BUILD_NUM>`, a Flux ImagePolicy bumps the Deployment, the cluster
rolls it out.

The rollout-confirmation semantics are extracted from letterbox's `/release-manager` (step 4)
and `deploy-status.sh`: the exact post-push tag is **unknowable at push time** (the build
number is assigned when CircleCI runs), so "deployed" means the live tag has **moved off** the
pre-push baseline — never an exact-tag match.

## Usage

```
/watch-flux-rollout                # latest origin/main commit
/watch-flux-rollout <sha>          # specific commit
/watch-flux-rollout --no-smoke     # watch the rollout only, skip the smoke test
```

## Procedure

### Phase 0 — Load config (optional)

Read `.claude/rollout.yaml` at the repo root if present — same file `/watch-rollout` uses,
different keys (they don't clash). Recognised keys (all optional):

```yaml
namespace:   apps                            # k8s namespace (default: apps)
deployment:  badusernames-deployment         # the Deployment Flux bumps
url:         https://badusernames.flurdy.io  # base URL the smoke targets
smoke: |
  GET /health, expect 200 and status "ok".
```

Anything missing is inferred or asked for below. Never require the file. If `deployment` is
absent, infer it from the GitOps repo (grep the kubernetes repo for the service's image name)
or ask — don't guess across candidates.

### Phase 1 — Resolve the commit and capture the baseline

Target commit: explicit sha arg, else the latest default-branch commit:

```bash
~/.agents/skills/watch-flux-rollout/scripts/default-head-sha.sh
```

Fallback if the script is unavailable — two steps, never `&&`: `git fetch origin main -q`,
then `git rev-parse origin/main`.

Capture the **pre-deploy baseline** now:

```bash
~/.agents/skills/watch-flux-rollout/scripts/rollout-status.sh {deployment} {namespace}
```

Emits `{context, namespace, deployment, found, ready, desired, image, tag, newestPodCreated}`.
Record `tag` as `fromTag` — Phase 4 confirms the rollout when the live tag moves **off** it.
Sanity-check `context` is the expected cluster and `found` is true before starting the watch.

**Baseline caveat:** if the target commit was pushed long ago, the baseline tag may already
include it — tag movement would then never fire. If CircleCI is already green for the sha and
`newestPodCreated` postdates the pipeline, report "likely already live" and offer to skip
straight to the smoke instead of watching.

### Phase 2 — Confirm what CI leg to watch

The CI leg reuses the `circleci-status` skill's script (symlinked alongside this one):

```bash
~/.agents/skills/circleci-status/scripts/status.sh {branch}
```

Parse the `---CIRCLECI-STATUS---` JSON: the watch tracks the pipeline whose
`pipeline.vcs.revision` equals the target sha — not just the branch's latest pipeline. If the
output is `NO_TOKEN`, degrade to the `---GITHUB-STATUS---` / `---GITHUB-CHECK-RUNS---`
sections from the same script (CircleCI reports state to GitHub) and note the reduced detail.

### Phase 3 — Derive the smoke test (derive + confirm)

Skip entirely if `--no-smoke`. Otherwise assemble a candidate smoke from, in order: config
`smoke`, the commit/PR description, recent conversation context. Classify the change:

- **Read-only API change** → an HTTP `GET` + the expected status/payload assertion.
- **UI change** → browser smoke (Chrome or Playwright MCP): a URL + what to observe.
- **Neither / unclear** → present what you found and ask the user to supply the check.

Present the candidate (target URL + assertion) and let the user confirm or tweak **before**
the watch starts. Don't run a derived smoke unconfirmed.

**Single-env note:** Flux personal/side-project setups often deploy straight to production —
there may be no staging. That's fine *only because* smokes here are strictly read-only (GET /
navigation). If a derived smoke isn't clearly read-only, refuse it and ask.

### Phase 4 — Watch the rollout

Keep the resolved sha, branch, deployment, namespace, `fromTag`, and confirmed smoke spec in the
scheduling prompt. Each tick must match the CircleCI pipeline by exact revision before inspecting
the rollout.

#### Pi protocol v1

If `watch_loop` is available, use this path instead of Claude scheduling:

1. Call `watch_loop` with `action: status`. Continue only when its result reports
   `protocolVersion: 1`. If another watch is `armed`, `running`, or `paused`, do not replace it;
   show the status and point at `/watch-status`, `/watch-stop`, or `/watch-resume`. If the version
   differs, explain the mismatch and stop without scheduling anything.
2. Make this prompt self-contained with the resolved values before passing it to `action: start`:

   ```text
   Load and follow the skill named `watch-flux-rollout` now. This is one continuation tick, not new watcher setup. Watch the CircleCI+Flux rollout of {sha} on {branch}, deployment {deployment} in {namespace}, fromTag "{fromTag}", with confirmed smoke {smoke spec with URL, or "disabled (--no-smoke)"}. Stage 1: run ~/.agents/skills/circleci-status/scripts/status.sh {branch}; parse ---CIRCLECI-STATUS--- and select only a pipeline whose vcs.revision is {sha}. If none exists yet or its workflows are running, render that status and call the matching `watch_loop` action: complete with outcome: continue. If a workflow for that revision failed, report it and complete with outcome: stop. Stage 2, only after CI succeeds: run ~/.agents/skills/watch-flux-rollout/scripts/rollout-status.sh {deployment} {namespace}. Deployed means tag moved off "{fromTag}" and ready equals desired. If not deployed, render tag and readiness, then complete with outcome: continue; but if CI has been green over 30 minutes and the tag is still "{fromTag}", report a Flux stall and complete with outcome: stop. Once deployed, either report success when smoke is disabled, or run the confirmed read-only smoke and report pass/fail with captured evidence; then complete with outcome: stop. If the same read-only CI or kubectl poll fails on two consecutive ticks, report it and stop. Never reconcile Flux, restart or apply Kubernetes resources, re-trigger CI, or issue a mutating smoke request.
   ```

3. State that the watcher starts after about one minute, polls every four minutes, and is capped at
   20 ticks (about 80 minutes). Then make the terminating start call:

   ```yaml
   action: start
   protocolVersion: 1
   label: Flux rollout
   mode: fixed
   initialDelaySeconds: 60
   intervalSeconds: 240
   missedCompletionPolicy: retry
   maxTicks: 20
   tickPrompt: <the prompt above>
   ```

A pending tick uses `action: complete` with `outcome: continue`. CI failure, Flux stall, or completed
smoke uses `action: complete` with `outcome: stop` and a concise reason. Protocol v1 also exposes
model-facing `action: stop` for a terminal abort with the matching watcher and generation tokens.
The runtime owns the cadence and finite budget; do not set `allowIndefinite`.

#### Claude Code fallback

If `watch_loop` is unavailable, retain the existing `/loop` path. Hand it the same resolved values
in a self-contained dynamic-loop prompt:

```
/loop Watch the CircleCI+Flux rollout of {sha} on {branch} ({deployment} in {namespace}).
Stage 1 — CI: run ~/.agents/skills/circleci-status/scripts/status.sh {branch}; parse
---CIRCLECI-STATUS---. If no pipeline with vcs.revision {sha} yet, or its workflows are
still running → reschedule ~240s. If a workflow for {sha} failed → report it and stop.
Stage 2 — rollout (only once CI is green for {sha}): run
~/.agents/skills/watch-flux-rollout/scripts/rollout-status.sh {deployment} {namespace}.
Deployed when tag has moved OFF "{fromTag}" AND ready == desired. Not yet → reschedule ~240s.
If CI has been green over ~30 min and the tag still equals "{fromTag}" → report a Flux stall
(likely: ImagePolicy semver range excludes the new tag, or image automation interval/suspend)
and stop.
On deployed → if smoke is disabled, report rollout success and stop; otherwise run the smoke test:
{smoke spec, with URL}. Report pass/fail with captured evidence, then stop the loop.
```

If neither `watch_loop` nor `/loop` is available, explain that recurring watches are unsupported
and stop. ~240s keeps each wake inside the prompt-cache window and matches the real cadence (a
CircleCI build takes minutes; Flux image automation scans on an interval, typically 1–10 min).
Both paths are **goal-terminating** — they end when the smoke completes, the deploy fails, or Flux
stalls.

### Phase 5 — Smoke test (the loop's terminal tick)

When the rollout is confirmed:

- **API:** `curl` a `GET` and assert the status code / payload field.
- **Browser (UI):** drive Chrome MCP or Playwright MCP to the URL and capture per the spec —
  screenshot, a network request, or a console signal. **Read-only navigation only** — no form
  submits, no clicks that mutate state, never trigger a JS dialog.

Report **pass/fail with the captured evidence** (status code, payload, screenshot path), then
stop the loop.

### Phase 6 — Offer to save config

If config was inferred (not loaded from `.claude/rollout.yaml`) and the run went cleanly,
offer to write the resolved `namespace`, `deployment`, `url`, and `smoke` to
`.claude/rollout.yaml` so the next run is one command. Only on explicit yes.

## Safety rules

- **Read-only, always.** Smokes are GET / navigation only — this skill frequently watches
  production (single-env Flux setups). Never issue writes, submit forms, or perform
  auth-mutating actions.
- **Watch only.** Never `flux reconcile`, `kubectl rollout restart`, `kubectl apply`, or
  re-trigger CI to hurry a rollout along. This skill observes a deploy, it doesn't drive one.
- **Don't thrash.** If kubectl or the CircleCI API fails twice, or a browser permission is
  denied, stop and report — don't retry in a loop.

## Failure modes

- **CI red for the sha** → report which workflow failed and stop; suggest
  `/circleci-status logs` for the failing job.
- **Tag never moves after CI green** (~30 min) → Flux stall. Report likely causes: the
  ImagePolicy semver range excludes the new tag, image automation is suspended or on a long
  interval, or the image push failed. Don't attempt to reconcile.
- **Wrong kubectl context / deployment not found** → `rollout-status.sh` reports `context` and
  `found: false`; stop before the watch starts, don't poll a missing target.
- **`NO_TOKEN`** → degrade to GitHub commit status (Phase 2); if that's also unavailable, stop.
- **Baseline already includes the change** → see the Phase 1 caveat; offer smoke-only.

## Notes

- Goal-terminating, so it takes no stop-hour (unlike `/watch-prs` / `/watch-release`).
- CronJob-backed services (no Deployment, no ready replicas) aren't covered; letterbox's
  `deploy-status.sh` has the aggregation pattern (`cron` / `cron:rollout` markers) to extract
  if the need arises.
- For GitHub-Actions-deployed repos use `/watch-rollout`; for letterbox's multirepo
  release flow use `/watch-release` / `/release-status`.
