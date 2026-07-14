---
name: watch-flux-rollout
description: >
  After a push or merge, watch a CircleCI + FluxCD deploy until it lands — CircleCI green for
  the commit, then the k8s Deployment's image tag moves off its pre-push baseline and pods go
  ready — then run a read-only smoke test scoped to the change. Goal-terminating loop — stops
  when the rollout lands and the smoke completes, or when it fails.
allowed-tools: "Read,Write,AskUserQuestion,Skill,Bash(~/.claude/skills/watch-flux-rollout/scripts/rollout-status.sh:*),Bash(~/.claude/skills/watch-flux-rollout/scripts/default-head-sha.sh:*),Bash(~/.claude/skills/circleci-status/scripts/status.sh:*),Bash(git:*),Bash(gh:*),Bash(curl:*),Bash(date:*),Bash(kubectl get:*),Bash(kubectl config current-context:*),mcp__claude-in-chrome__*,mcp__playwright__*"
model-tier: standard-workflow
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
model: sonnet
effort: medium
version: "1.0.0"
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
~/.claude/skills/watch-flux-rollout/scripts/default-head-sha.sh
```

Fallback if the script is unavailable — two steps, never `&&`: `git fetch origin main -q`,
then `git rev-parse origin/main`.

Capture the **pre-deploy baseline** now:

```bash
~/.claude/skills/watch-flux-rollout/scripts/rollout-status.sh {deployment} {namespace}
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
~/.claude/skills/circleci-status/scripts/status.sh {branch}
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

### Phase 4 — Watch the rollout (compose `/loop`)

Hand a **self-contained** dynamic-loop prompt to `/loop` — it must carry the sha, branch,
deployment, namespace, `fromTag`, and smoke spec, since each wake re-runs the prompt from
scratch:

```
/loop Watch the CircleCI+Flux rollout of {sha} on {branch} ({deployment} in {namespace}).
Stage 1 — CI: run ~/.claude/skills/circleci-status/scripts/status.sh {branch}; parse
---CIRCLECI-STATUS---. If no pipeline with vcs.revision {sha} yet, or its workflows are
still running → reschedule ~240s. If a workflow for {sha} failed → report it and stop.
Stage 2 — rollout (only once CI is green for {sha}): run
~/.claude/skills/watch-flux-rollout/scripts/rollout-status.sh {deployment} {namespace}.
Deployed when tag has moved OFF "{fromTag}" AND ready == desired. Not yet → reschedule ~240s.
If CI has been green over ~30 min and the tag still equals "{fromTag}" → report a Flux stall
(likely: ImagePolicy semver range excludes the new tag, or image automation interval/suspend)
and stop.
On deployed → run the smoke test: {smoke spec, with URL}. Report pass/fail with captured
evidence, then stop the loop.
```

~240s keeps each wake inside the prompt-cache window and matches the real cadence (a CircleCI
build takes minutes; Flux image automation scans on an interval, typically 1–10 min). The loop
is **goal-terminating** — it ends when the smoke completes, the deploy fails, or Flux stalls.

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
