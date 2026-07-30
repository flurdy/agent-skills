---
name: watch-release
description: >
  Start a recurring release-gatekeeper loop — runs /release-manager on an adaptive cadence
  (fast when something is in flight, backing off when settled) until end of day in a dedicated
  tab. Prompts to push / defer / cancel as services become ready; runs attended.
model-tier: standard
model: sonnet
effort: medium
version: "1.2.0"
author: "flurdy"
---

# Watch Release

Start a `/release-manager` loop that runs until 18:00 local time, **pacing itself adaptively**:
checking again soon (~3 min) while a push is mid-rollout or CI is running, and backing off
(10 → 30 min) once everything is settled. Intended for a dedicated kitty tab during parallel work
— it keeps an eye on git/CI/deploy state and prompts you when something is ready to ship, without
burning a tick every 10 minutes when nothing is happening.

## Usage

```
/watch-release            # adaptive cadence, stop at 18:00   (default)
/watch-release 17         # adaptive, stop at 17:00
/watch-release 10m        # FIXED 10-minute interval, stop at 18:00
/watch-release 5m 17      # fixed 5m, stop at 17:00
```

Adaptive is the default. Pass an explicit `\d+m` interval only when you deliberately want a fixed
cadence (e.g. demoing, or a tab you glance at on a known rhythm).

## Instructions

Parse optional arguments:

1. **Interval** — first positive interval matching `\d+m`. **Absent → adaptive mode** (the
   default). Present → fixed-interval mode at that interval.
2. **Stop hour** — first unconsumed stop hour from `0` through `23`. Default: `18`.

If an argument is invalid, explain the accepted forms and stop. Resolve today's stop hour in local
time. If the current time is already at or past that deadline, tell the user and don't start.

### Pi protocol v1

If `watch_loop` is available, use this path instead of Claude scheduling:

1. Call `watch_loop` with `action: status`. Continue only when its result reports
   `protocolVersion: 1`. If another watch is `armed`, `running`, or `paused`, do not replace it;
   show the status and point at `/watch-status`, `/watch-stop`, or `/watch-resume`. If the version
   differs, explain the mismatch and stop without scheduling anything.
2. Convert today's local stop hour to an ISO-8601 timestamp with its timezone offset for `stopAt`.
3. Use this self-contained prompt in the start call:

   ```text
   Load and follow the skill named `release-manager` now. This is one attended release tick. Invoke the skill rather than improvising its steps, render its full dashboard and every confirmation as visible text, and wait for each answer. Never push, sync config, or restart a deployment without the explicit answer to that action's current question in this tick. An `ask_user_question` call blocks the active tick until the user answers; do not call `watch_loop` complete while a question is open. After release-manager has finished all answered prompts and printed its final `next-tick:` line, call the matching `watch_loop` action: complete with outcome: continue. In adaptive mode pass that line's numeric N as delaySeconds; if the line is missing or malformed, use 600. In fixed mode omit delaySeconds. Do not complete before the dashboard, answers, tick summary, and cadence recommendation are visible.
   ```

4. For adaptive mode, state the local deadline and that the first tick lands after about one
   minute. Then make the terminating start call:

   ```yaml
   action: start
   protocolVersion: 1
   label: Releases
   mode: adaptive
   initialDelaySeconds: 60
   missedCompletionPolicy: pause
   stopAt: <today's local deadline as ISO-8601>
   tickPrompt: <the prompt above>
   ```

   Each successful tick passes `/release-manager`'s numeric `next-tick:` recommendation as
   `delaySeconds`; the runtime clamps it to 60–3600 seconds. Hot/warm/cold remain approximately
   180/600/1200–1800 seconds. A missing or malformed recommendation uses the explicit 600-second
   fallback.

5. For fixed mode, convert the requested minutes to seconds, state the local deadline, and make the
   terminating start call:

   ```yaml
   action: start
   protocolVersion: 1
   label: Releases
   mode: fixed
   initialDelaySeconds: <interval seconds>
   intervalSeconds: <interval seconds>
   missedCompletionPolicy: pause
   stopAt: <today's local deadline as ISO-8601>
   tickPrompt: <the prompt above>
   ```

   Fixed ticks ignore `next-tick:` and let the runtime enforce the requested cadence from each
   successful completion.

A successful start ends the initiating turn. `ask_user_question` blocks the active tick until the
user answers, and only the later matching `action: complete` schedules another tick. The `pause`
policy prevents an unanswered, interrupted, or malformed attended tick from retrying by itself.
Protocol v1 also exposes model-facing `action: stop`; ordinary deadline and manual stopping belong
to the runtime and `/watch-stop`.

### Claude Code fallback

If `watch_loop` is unavailable, retain the existing Claude Code paths below.

#### Adaptive mode (no interval given)

Invoke the `/loop` skill in **dynamic (self-paced)** mode. The loop prompt is the only text
re-injected verbatim on every wakeup — `release-manager`'s SKILL.md is NOT re-read on wakeup turns
unless the tick explicitly loads it — so the output contract and ordering must live inside the
prompt string itself:

```
/loop /release-manager — each tick: invoke the release-manager skill via the Skill tool (never improvise its steps from memory), render its full dashboard and any prompts as visible text, and only THEN call ScheduleWakeup as the very last action of the turn; the turn ends the instant ScheduleWakeup returns, so a tick that schedules before rendering shows the user nothing and has failed
```

Pass that whole string as the loop prompt, and echo it back unchanged in every `ScheduleWakeup`
call so later ticks keep the contract. Each tick must render first and call `ScheduleWakeup` as
its final action — text intended after that call is silently dropped.

Then pace each next wake from the recommendation `/release-manager` prints **last** in its tick
output:

```
next-tick: {hot|warm|cold} (~{N}s) — {reason}
```

Use `{N}` as the `delaySeconds` for the next wake (the dynamic loop clamps to `[60, 3600]`). Don't
second-guess the bucket — `/release-manager` already weighs rollout/CI/queue state (step 8b):

- **hot** (~180s) — a push is mid-rollout or CI is running; check soon to catch it.
- **warm** (~600s) — pending work, nothing time-critical.
- **cold** (1200 → 1800s) — settled; escalating back-off via the `quietStreak` counter.

Stop and don't reschedule once the wake would land past `{stop_hour}:00`. If a tick produces no
`next-tick:` line (e.g. it errored before step 8b), fall back to ~600s and continue.

#### Fixed mode (interval given)

Invoke the `/loop` skill with the literal interval — `/release-manager`'s `next-tick:` line is
ignored. The same per-tick contract applies (minus the `ScheduleWakeup` ordering — cron fires
fixed ticks):

```
/loop {interval} /release-manager — each tick: invoke the release-manager skill via the Skill tool and render its full dashboard as visible text; a tick that only runs scripts is a failed tick
```

Tell the loop to stop at `{stop_hour}:00` local time. If neither `watch_loop` nor the required
Claude scheduling capability is available, explain that recurring watches are unsupported and
stop.

## Note

`/release-manager` prompts (push / defer / cancel) and **blocks each tick until you answer**, so
this loop is meant to run **attended** in a visible tab. The adaptive interval is time measured
*after* a tick completes (including after you answer a prompt) — so a `hot` 3-minute cadence only
kicks in once you've cleared the prompt. For an unattended, never-blocking view, loop
`/release-status` instead (`/loop 10m /release-status`) and act on its recommendations manually.
