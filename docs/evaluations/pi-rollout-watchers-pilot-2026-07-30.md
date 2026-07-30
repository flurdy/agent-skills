# Pi rollout-watchers pilot — 2026-07-30

## Scope

Validate protocol-v1 branches for `watch-rollout` and `watch-flux-rollout` without triggering a deployment or mutating a rollout. The source plan was `docs/architecture/pi-watch-loop-extension-plan.md` in the workspace at SHA-256 `0ddec57af9076de2550bd527ce54d53492d17d11d4f24fd736b284d0c4240038`.

Both ports retain setup and smoke confirmation before scheduling, use a 60-second initial delay and 240-second fixed cadence, select the read-only `retry` policy, and have finite budgets:

- GitHub Actions: 30 ticks, just under two hours;
- CircleCI/Flux: 20 ticks, about 80 minutes.

## Static checks

| Check | Result |
|---|---|
| `make -C repos/agent-skills validate-skills` | PASS — 56 skills |
| `make -C repos/agent-skills dry-run` | PASS — managed links resolved without collisions |
| `make -C repos/agent-skills test-watch-rollouts` | PASS — both protocol and Claude fallback contracts |
| `make -C repos/agent-skills test-watch-prs` | PASS — pilot contract remained intact |
| `make -C repos/agent-skills clean-code` | PASS — no shell syntax or ShellCheck warnings |
| `make -C repos/ai-tools/pi/watch-loop check` | PASS — 33 tests and TypeScript typecheck |

## GitHub Actions live UAT

Environment: Pi 0.82.1 with `ai-tools` commit `c59fd38`, `openai-codex/gpt-5.6-sol:minimal`, and live read-only GitHub Actions data from `bluelightcard/admin-panel-web`.

### Pending continuation

The end-to-end command `/skill:watch-rollout --run 30547007480 --prod --no-smoke` resolved the production gating job and skipped smoke confirmation as requested. Pi probed protocol 1 and started the production configuration: fixed mode, 60-second initial delay, 240-second interval, `retry`, and `maxTicks: 30`.

Generation 1 rendered the workflow and all three jobs. The production job was `waiting`, while tests and staging were successful. Its matching completion used `outcome: continue`; the runtime returned `State: armed`, `Ticks: 1/30`, and scheduled the next tick in four minutes.

A post-UAT read confirmed run `30547007480` remained `waiting` with the same job conclusions. The harness ended the disposable Pi process after the continuation; it did not approve, rerun, cancel, or otherwise mutate the workflow.

### Terminal stop

A normal `/watch-rollout` setup correctly avoids starting a watcher for an already completed run. To exercise a terminal generation rather than that setup early-exit, a tick-level protocol probe used the exact production tick prompt against known completed run `30334338308`, with staging as the gating job and smoke disabled.

Generation 1 rendered the successful run and job evidence, then completed with `outcome: stop`. The runtime returned `State: stopped`, `Ticks: 1/30`, and reason `Gating job 🚀 Deploy to Staging completed successfully; smoke disabled (--no-smoke).`

A post-UAT read confirmed the source run remained completed and successful. No smoke, workflow action, or deployment was triggered.

## CircleCI/Flux live UAT blocker

Status: **TBD — BLOCKED**, not simulated.

The available candidate was `flurdy/bad_usernames_api`:

- CircleCI authentication worked and returned revision `9788153e60fa14560879d53e771735662b66dc9d` with a successful workflow;
- no active pipeline existed to observe a pending transition;
- current Kubernetes context was `syndicate`;
- `rollout-status.sh badusernames-deployment apps` returned `found: false` because the DigitalOcean credential helper could not authenticate (`doctl` reported that an access token is required).

The mandatory pre-watch baseline and live tag/readiness checks were therefore unavailable. No credential configuration, pipeline trigger, Flux reconciliation, Kubernetes mutation, or deployment was attempted. Complete the pending/terminal Pi UAT when read-only cluster credentials and a naturally occurring rollout are both available.

## Local evidence

Disposable PTY harnesses and captures were kept outside the repository under `/tmp/agents-3bw.3-uat/` for the session.

| Artifact | SHA-256 |
|---|---|
| GitHub pending event log | `4217837d2f2cd3b12b3abf8526d0663c5c0b920a1abe4736ac8870db8a684e52` |
| GitHub pending TUI capture | `fb71790b2e040036ef160c51b24f84a5d3aa811e1557f1feeb125d1f8633ceff` |
| GitHub terminal event log | `0d8d77b4f89ee8ac7808d1f65f0105e5b5f060f877c944df7f73cdaa6bb3d31d` |
| GitHub terminal TUI capture | `5c467cadc0330a591920b8ea954fe4789be209e0e38c0512dcab477892413d93` |

## Verdict

Implementation and GitHub Actions live UAT pass. The CircleCI/Flux implementation passes its protocol contract, while live UAT remains explicitly blocked by unavailable cluster authentication and the absence of an active pipeline. This records the missing evidence without manufacturing a deployment.
