---
name: watch-prs
description: >
  Start a recurring PR status dashboard — runs /pr-status on an adaptive cadence
  (fast when CI is in flight, backing off when settled) until end of day. Unattended:
  renders tables and suggested next actions, never prompts or blocks.
model: sonnet
effort: medium
version: "2.0.0"
author: "flurdy"
---

# Watch PRs

Start a `/pr-status` loop that runs until 18:00 local time, **pacing itself adaptively**:
checking again soon (~3 min) while CI is running or a PR just changed, and backing off
(10 → 30 min) once everything is settled. Unlike `/watch-release`, this loop is **unattended** —
`/pr-status` only reads and renders (tables + suggested-action footer), it never prompts or
blocks, so you can leave it running in a tab while you work.

## Usage

```
/watch-prs            # adaptive cadence, stop at 18:00   (default)
/watch-prs 17         # adaptive, stop at 17:00
/watch-prs 10m        # FIXED 10-minute interval, stop at 18:00
/watch-prs 5m 17      # fixed 5m, stop at 17:00
```

Adaptive is the default. Pass an explicit `\d+m` interval only when you deliberately want a fixed
glance rhythm (e.g. a tab you check on a known cadence).

## Instructions

Parse optional arguments:

1. **Interval** — first arg matching `\d+m`. **Absent → adaptive mode** (the default). Present →
   fixed-interval mode at that interval.
2. **Stop hour** — first arg matching `\d{1,2}` not already consumed as the interval. Default: `18`.

If the current time is already past the stop hour, tell the user and don't start the loop.

### Adaptive mode (no interval given)

Invoke the `/loop` skill in **dynamic (self-paced)** mode with `/pr-status`:

```
/loop /pr-status
```

Then pace each next wake from the recommendation `/pr-status` prints **last** in its tick output:

```
next-tick: {hot|warm|cold} (~{N}s) — {reason}
```

Use `{N}` as the `delaySeconds` for the next wake (the dynamic loop clamps to `[60, 3600]`). Don't
second-guess the bucket — `/pr-status` already weighs CI / push / transition state (its step 6):

- **hot** (~180s) — CI in flight or a PR changed this tick; check soon to catch the result.
- **warm** (~600s) — PRs awaiting review, nothing time-critical.
- **cold** (1200 → 1800s) — settled; escalating back-off via the `quietStreak` counter.

Stop and don't reschedule once the wake would land past `{stop_hour}:00`. If a tick produces no
`next-tick:` line (e.g. it errored before step 6), fall back to ~600s and continue.

### Fixed mode (interval given)

Invoke the `/loop` skill with the literal interval — `/pr-status`'s `next-tick:` line is ignored:

```
/loop {interval} /pr-status
```

Tell the loop to stop at `{stop_hour}:00` local time.

## Note

`/pr-status` is read-only and never prompts, so this loop runs **unattended** — leave it in a tab.
The suggested-action footer points you at `/ready-to-merge`, `/review-comments`, etc. as PRs become
actionable, but you run those yourself when you choose; the watcher never acts. For an attended
release-gatekeeper that prompts to push/defer/cancel, use `/watch-release` instead.
