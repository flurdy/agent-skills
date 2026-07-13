---
name: watch-rollout
description: >
  After a merge, watch the GitHub Actions deploy run until the gating job lands, then run a
  smoke test scoped to the change (browser for UI, GET for read-only API) against staging.
  Goal-terminating loop — stops when the deploy lands and the smoke completes, or when it fails.
allowed-tools: "Read,Write,AskUserQuestion,Skill,Bash(~/.claude/skills/watch-rollout/scripts/run-jobs.sh:*),Bash(~/.claude/skills/watch-rollout/scripts/default-head-sha.sh:*),Bash(gh:*),Bash(git:*),Bash(curl:*),Bash(date:*),mcp__claude-in-chrome__*,mcp__playwright__*"
model-tier: standard-coding
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
model: sonnet
effort: medium
version: "1.0.1"
author: "flurdy"
---

# Watch Rollout

Watch a post-merge GitHub Actions deploy to staging, then smoke-test the change once it lands —
the generic, GitHub-Actions-based cousin of `/watch-release` (which is hardwired to letterbox's
kubectl/CircleCI/Flux stack). Built for client repos with extensive CD workflows.

Chains naturally after `/ready-to-merge`: merge → watch the deploy job → confirm the change is live.

## Usage

```
/watch-rollout                 # deploy of latest origin/main commit, smoke staging
/watch-rollout 6790            # resolve via PR number (uses its merge commit)
/watch-rollout <sha>           # specific commit
/watch-rollout --run 28440286944   # specific workflow run id
/watch-rollout --prod          # allow a read-only prod smoke (safety-gated, see below)
/watch-rollout --no-smoke      # watch the deploy only, skip the smoke test
```

## Procedure

### Phase 0 — Load config (optional)

Read `.claude/rollout.yaml` at the repo root if present. Recognised keys (all optional):

```yaml
workflow:    CMS Pages                                   # deploy workflow name to watch
gating_job:  Deploy blc-uk                               # substring of the job that gates the target env
staging_url: https://legacy.staging.bluelightcard.co.uk
prod_url:    https://www.bluelightcard.co.uk
smoke: |
  Load /en logged-out, capture the first Amplitude "Page Viewed" request,
  assert login_state=logged_out is in the event user properties.
```

Anything missing is inferred or asked for below. Never require the file — it's a convenience for
repos you watch repeatedly.

### Phase 1 — Resolve the commit and run

Determine the target commit (first match wins): `--run` id (skip to job listing) → PR number's
merge commit (`gh pr view {n} --json mergeCommit --jq .mergeCommit.oid`) → explicit sha → latest
default-branch commit:

```bash
~/.claude/skills/watch-rollout/scripts/default-head-sha.sh        # fetches origin/main, prints its sha
```

Fallback if the script is unavailable — run as two steps, never `&&` (each stays prefix-matchable):

```bash
git fetch origin main -q
git rev-parse origin/main
```

List runs on that commit and pick the deploy workflow:

```bash
gh run list --commit {sha} --limit 20 --json databaseId,name,status,conclusion,workflowName,event
```

Choose the run by config `workflow`, else by name heuristic (`deploy`/`release`/`cd`/`publish`),
else **ask** via `AskUserQuestion` when more than one plausible candidate exists. Don't guess
silently across ambiguous workflows.

### Phase 2 — Identify the gating job

```bash
~/.claude/skills/watch-rollout/scripts/run-jobs.sh {run_id}
```

Emits a JSON object: `{status, conclusion, jobs: [{name, status, conclusion}]}`. Fallback if the
script is unavailable: `gh run view {run_id} --json status,conclusion,jobs` (read the raw JSON).

A deploy run is often a matrix (per brand / per region). Watch the **one job that gates the env you
care about** — the others don't block your target (e.g. `Deploy blc-uk [preview]` gates BLC-UK
staging; au/dds/prod jobs are irrelevant to it). Pick it by config `gating_job`, else infer from
the branch/PR context, else **ask** which job(s) gate the target. If tests gate the deploy job and
the deploy job isn't spawned yet, note that — a test failure means the deploy never starts.

### Phase 3 — Derive the smoke test (derive + confirm)

Skip entirely if `--no-smoke`. Otherwise assemble a candidate smoke from, in order: config `smoke`,
`/ready-to-merge`'s post-merge follow-up note (if this session just merged), the PR description, and
the Jira AC. Classify the change:

- **UI change** → browser smoke (Chrome MCP): a staging URL + what to observe (screenshot, a network
  request, a console signal).
- **Read-only API change** → an HTTP `GET` + the expected status/payload assertion.
- **Neither / unclear** → present what you found and ask the user to supply the check.

Present the candidate (target URL + assertion) and let the user confirm or tweak **before** the
watch starts. Don't run a derived smoke unconfirmed.

### Phase 4 — Watch the deploy (compose `/loop`)

Hand a **self-contained** dynamic-loop prompt to `/loop` — it must carry the run id, gating-job name,
smoke spec, and target URL, since each wake re-runs the prompt from scratch:

```
/loop Watch GitHub Actions run {run_id} ({workflow} on {sha}).
Run: ~/.claude/skills/watch-rollout/scripts/run-jobs.sh {run_id}.
While the gating job "{gating_job}" is in_progress (or not yet started), reschedule ~240s.
On gating-job success → run the smoke test: {smoke spec, with URL}. Report pass/fail with captured evidence.
On gating-job failure → report which job failed and stop. Stop the loop once the smoke is done or the deploy failed.
```

~240s keeps each wake inside the prompt-cache window and catches completion promptly. The loop is
**goal-terminating** — it ends when the smoke completes or the deploy fails, not at end of day.
Polling is unattended; the smoke step (Phase 5) may need you present for a browser permission prompt.

### Phase 5 — Smoke test (the loop's terminal tick)

When the gating job is green:

- **Browser (UI):** drive a browser to the staging URL and capture per the spec — screenshot, a
  specific network request, or a console signal. Pick the driver to fit the check:
  - **Chrome MCP** (`mcp__claude-in-chrome__*`) — when you want it in the user's visible Chrome
    session (shared cookies/auth, watching it happen). `/browser-screenshot` covers the screenshot
    case. Captures network via `read_network_requests`, console via `read_console_messages`.
  - **Playwright MCP** (`mcp__playwright__*`) — when a clean, headless, scriptable check suits better
    (no visible session needed, deterministic network capture via `browser_network_requests`).
  **Read-only navigation only** with either driver — no form submits, clicks, or actions that mutate
  state; never trigger a JS dialog.
- **API:** `curl`/`gh api` a `GET` and assert the status code / payload field.

Report **pass/fail with the captured evidence** (the screenshot path, the network payload, the
status code), then stop the loop.

### Phase 6 — Offer to save config

If config was inferred (not loaded from `.claude/rollout.yaml`) and the run went cleanly, offer to
write the resolved `workflow`, `gating_job`, URL, and `smoke` to `.claude/rollout.yaml` so the next
run is one command. Only on explicit yes.

## Safety rules

- **Staging by default.** Smoke prod only with `--prod` **and** only for strictly read-only checks
  (GET / navigation). **Never** issue writes (POST/PUT/PATCH/DELETE), submit forms, or perform
  auth-mutating actions against prod. If a derived prod smoke isn't clearly read-only, refuse it and
  ask.
- **Watch only.** Never re-trigger, cancel, re-run, or approve a workflow; never deploy. This skill
  observes a rollout, it doesn't drive one.
- **Don't thrash.** If a browser permission is denied or a fetch fails twice, stop and report — don't
  retry in a loop.

## Failure modes

- **No deploy workflow on the commit** → report it and stop (the merge may not trigger a deploy, or
  the workflow runs on a tag/schedule instead).
- **Gating job never spawns** (gated behind failing tests/lint) → detect the upstream failure, report
  which job failed, stop.
- **Ambiguous workflow or gating job** → ask; never guess across candidates.
- **Browser blocked** (bot detection, auth wall, permission denied) → stop and report what was
  reached, rather than retrying.

## Notes

- Goal-terminating, so unlike `/watch-prs` and `/watch-release` it does not take a stop-hour.
- This skill is for GitHub-Actions-deployed repos. For CircleCI + FluxCD repos use
  `/watch-flux-rollout` (same shape, kubectl/CircleCI watch); for letterbox's multirepo release
  flow use `/watch-release` / `/release-status`.
