# Pi watch-release pilot — 2026-07-30

## Scope

Validate the attended `watch-release` protocol-v1 branch without pushing, syncing production config, or restarting a deployment. The source plan was `docs/architecture/pi-watch-loop-extension-plan.md` in the workspace at SHA-256 `0ddec57af9076de2550bd527ce54d53492d17d11d4f24fd736b284d0c4240038`.

The port retains adaptive and fixed cadence, local stop-hour deadlines, Claude scheduling, and every confirmation owned by `release-manager`. Pi uses `missedCompletionPolicy: pause` so an interrupted or unanswered attended tick cannot retry itself.

## Static checks

| Check | Result |
|---|---|
| `make -C repos/agent-skills validate-skills` | PASS — 56 skills |
| `make -C repos/agent-skills dry-run` | PASS — managed links resolved without collisions |
| `make -C repos/agent-skills test-watch-protocols` | PASS — all four Pi/Claude watcher contracts |
| `make -C repos/agent-skills clean-code` | PASS — no shell syntax or ShellCheck warnings |
| `make -C repos/ai-tools/pi/watch-loop check` | PASS — 33 tests and TypeScript typecheck |

## Attended Pi UAT

The real letterbox workspace had no unpushed service candidate, so it could not naturally reach a push/defer/cancel confirmation. The UAT used the real `watch-release` and `release-manager` skills in an isolated local letterbox fixture with one read-only digest row: `dispatch` had one unpushed commit, matching green branch CI, and a ready deployment. Fixture `git-push`, `k8s-sync`, and `kubectl rollout restart` paths were guarded by a mutation sentinel.

Because the host's BST time was already past every valid same-day stop hour, the disposable Pi process used `TZ=America/New_York`. `/skill:watch-release 23` produced `stopAt: 2026-07-30T23:00:00-04:00`, proving that the deadline retained its local offset.

The adaptive start used protocol 1, a 60-second initial delay, and `missedCompletionPolicy: pause`. Generation 1 rendered the release dashboard, then opened this attended question:

> What should I do with dispatch? Pushing deploys 1 unpushed commit to prod on CI-green; remote CI has not verified this commit.

The harness selected `Defer (Recommended)`. Observations:

- no `agent_settled` event occurred while the question was open;
- `release-manager` persisted `deferred.dispatch` in the isolated `.release-state.json`;
- the visible result said `no push or production action performed`;
- the tick ended with `next-tick: warm (~600s)`;
- the matching completion occurred 8.760 seconds after the answer with `outcome: continue` and `delaySeconds: 600`;
- the runtime remained valid and `armed` at `Ticks: 1`, with the next run in ten minutes and the `pause` policy retained;
- the mutation sentinel was absent, proving no fixture push, config sync, or rollout restart path ran;
- no compaction occurred.

After recording the valid armed state, `/watch-stop` was used only to clean up the disposable session. Final status was `stopped` with reason `watch stopped by user`.

## Local evidence

The fixture, observer, PTY harness, and captures were kept outside the repository under `/tmp/agents-3bw.4-uat/` for the session.

| Artifact | SHA-256 |
|---|---|
| Protocol event log | `e0792f0f29dc5f1da1d2f94d3eec3ef0121135610a9987d74137b4ec4a86a065` |
| TUI capture | `6962619ce49affe80044b3b01ae3830f1784a90ec34f174eee74e8dadaee9a2d` |
| Deferred release state | `05fe4fab4f9e91a86e8088f65efdcb555c1be2177ec8654bcc2f6655e1fbf569` |

## Verdict

PASS. The attended question blocked settlement, defer completed the tick, adaptive cadence resumed with the watcher still valid, and no release or deployment action occurred. The Claude path remains covered by the preserved fallback contract.
