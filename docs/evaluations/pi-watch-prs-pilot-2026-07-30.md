# Pi watch-prs pilot — 2026-07-30

## Scope

Validate the `watch-prs` protocol-v1 capability branch against the in-memory Pi watch-loop extension while retaining the Claude Code path. The source plan was `docs/architecture/pi-watch-loop-extension-plan.md` in the workspace at SHA-256 `0ddec57af9076de2550bd527ce54d53492d17d11d4f24fd736b284d0c4240038`.

Environment:

- Pi 0.82.1 with `ai-tools` commit `c59fd38` loaded through `-e ./repos/ai-tools/pi/watch-loop`;
- `openai-codex/gpt-5.6-sol:minimal` for Pi UAT;
- Claude Code 2.1.220 with Sonnet for fallback compatibility;
- local timezone BST (`+01:00`);
- live `pr-status` data contained three draft PRs and no actionable transitions.

## Static checks

| Check | Result |
|---|---|
| `make -C repos/agent-skills validate-skills` | PASS — 56 skills |
| `make -C repos/agent-skills dry-run` | PASS — managed links resolved without collisions |
| `make -C repos/agent-skills test-watch-prs` | PASS — protocol and Claude fallback contract |
| `make -C repos/agent-skills clean-code` | PASS — no shell syntax or ShellCheck warnings |
| `make -C repos/ai-tools/pi/watch-loop check` | PASS — 33 tests and TypeScript typecheck |

## Live Pi UAT

### Fixed deadline

`/skill:watch-prs 1m 22` probed protocol 1, then started a fixed watcher at 21:57:51 with `stopAt: 2026-07-30T22:00:00+01:00`. Generation 1 rendered a complete 965-byte dashboard at 21:58:58. Its matching completion was accepted, but the runtime returned `deadline_prevents_schedule` because another 60-second interval would reach or cross the deadline. Final state was `stopped`.

### Adaptive cadence and manual controls

`/skill:watch-prs 23` probed protocol 1 and started adaptive mode with a 60-second initial delay, `retry` missed-completion policy, and the local 23:00 deadline. Generation 1 rendered a complete 965-byte dashboard and passed `delaySeconds: 1200` from `next-tick: cold (~1200s) — drafts only`. `/watch-status` showed the next run in 20 minutes. `/watch-stop` followed by `/watch-status` showed `State: stopped` and `Last reason: watch stopped by user`.

### Thirty-tick soak

`/skill:watch-prs 1m 23` ran a fixed one-minute watcher for 30 completed generations.

| Signal | Observation |
|---|---|
| Watch IDs | One |
| Generations | Exactly 1–30, each once |
| Matching completions | 30 unique watcher/generation pairs |
| Complete dashboards | 30/30 |
| Dashboard size | 963–969 bytes |
| Timestamp and `next-tick:` footer | Present on 30/30 dashboards |
| Completion-to-next-dispatch cadence | 60.002–60.021s; median 60.010s |
| Compactions | 0 |
| `/watch-status` | Confirmed `armed`, fixed mode, and `Ticks: 3/unbounded` during the soak |
| Manual stop | Confirmed `Ticks: 30/unbounded`, warning notification, then `State: stopped` |

No duplicate generation, missed completion, malformed dashboard, or visible quality degradation occurred. Pi did not compact during the 30 ticks, so post-compaction quality was not exercised.

## Claude Code compatibility

A Claude Code fixed-mode run of `/watch-prs 1m 23` retained the existing `/loop {interval} /pr-status` path. It rendered five consecutive dashboards at 22:07:26, 22:08:27, 22:09:28, 22:10:31, and 22:11:35 before the disposable test process exited. This exceeds the required one-tick compatibility check; no Claude scheduling process remained afterward.

## Local evidence

The disposable PTY harness and raw captures were kept outside the repository under `/tmp/agents-3bw.2-uat/` for the session. Evidence hashes:

| Artifact | SHA-256 |
|---|---|
| Fixed-deadline event log | `1277b558fdc15383c89b3f68963b413177227ce61f89cf5c4089578f78eabf2d` |
| Adaptive event log | `3d5ab542a57013c2ebebe71421110b2d3fc29b91033a3980226125f82df88228` |
| Thirty-tick event log | `e5fc95e021a29dc43f9641fd5b115bb167003fd2fb4721685ac4bc0963b14d90` |
| Thirty-tick TUI capture | `7deffb885fd34b896256a211b061821ca28c7158e29e62a5b4fedcc335ac3ffb` |
| Claude Code TUI capture | `e272ebfa33f7b53a1ad5870070eeffe67ef47b4da4b7fdd96ebcda334649818c` |

## Verdict

PASS. The Pi branch provides bounded fixed and adaptive scheduling, visible dashboards, status, manual stop, and deadline handling without duplicate or degraded ticks. The Claude Code path remains operational.
