---
name: watch-release
description: >
  Start a recurring release-gatekeeper loop — runs /release-manager on an adaptive cadence
  (fast when something is in flight, backing off when settled) until end of day in a dedicated
  tab. Prompts to push / defer / cancel as services become ready; runs attended.
model-tier: standard-coding
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
effort: medium
version: "1.1.0"
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

1. **Interval** — first arg matching `\d+m`. **Absent → adaptive mode** (the default). Present →
   fixed-interval mode at that interval.
2. **Stop hour** — first arg matching `\d{1,2}` not already consumed as the interval. Default: `18`.

If the current time is already past the stop hour, tell the user and don't start the loop.

### Adaptive mode (no interval given)

Invoke the `/loop` skill in **dynamic (self-paced)** mode with `/release-manager`:

```
/loop /release-manager
```

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

### Fixed mode (interval given)

Invoke the `/loop` skill with the literal interval — `/release-manager`'s `next-tick:` line is
ignored:

```
/loop {interval} /release-manager
```

Tell the loop to stop at `{stop_hour}:00` local time.

## Note

`/release-manager` prompts (push / defer / cancel) and **blocks each tick until you answer**, so
this loop is meant to run **attended** in a visible tab. The adaptive interval is time measured
*after* a tick completes (including after you answer a prompt) — so a `hot` 3-minute cadence only
kicks in once you've cleared the prompt. For an unattended, never-blocking view, loop
`/release-status` instead (`/loop 10m /release-status`) and act on its recommendations manually.
