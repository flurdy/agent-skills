---
name: watch-prs
description: >
  Start a recurring PR status dashboard — runs /pr-status on an adaptive cadence
  (fast when CI is in flight, backing off when settled) until end of day. Unattended:
  renders tables and suggested next actions, never prompts or blocks.
model-tier: standard-coding
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
model: sonnet
effort: medium
version: "2.2.0"
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

Self-manage the loop with the `ScheduleWakeup` tool — do **not** route ticks through the `/loop`
skill, and do **not** run the first tick inline. A composed turn (watch-prs + loop + pr-status
instruction stacks in one context) reliably ends on a bare `ScheduleWakeup` with no dashboard,
while a turn that *begins* with `/pr-status` reliably renders in full. So every tick, including
the first, must arrive as its own wakeup turn whose prompt starts with `/pr-status`:

1. Load the `ScheduleWakeup` tool if needed (via ToolSearch), then call it with
   `delaySeconds: 60` and `prompt` set to the tick prompt below, substituting `{stop_hour}`.
2. Confirm to the user: loop started, first dashboard lands in ~1 minute, ticks self-pace until
   `{stop_hour}:00`. Do NOT invoke `pr-status` or run its fetch scripts in this start turn.

Tick prompt — one line, and every tick's own `ScheduleWakeup` call echoes it verbatim:

```
/pr-status — print the full dashboard (timestamp, both tables, deltas, next-tick line) as visible text; then, only after the next-tick line is printed, call ScheduleWakeup with delaySeconds taken from that next-tick line (600 if it is missing) and this exact prompt verbatim. If that wake would land past {stop_hour}:00 local time, call ScheduleWakeup with stop: true instead. The turn ends the instant ScheduleWakeup returns, so a tick that schedules before the dashboard is printed shows the user nothing and has failed
```

Because the prompt starts with `/pr-status`, every wakeup re-loads that skill's SKILL.md — table
spec, deltas, `next-tick:` recommendation and all — so no tick depends on conversation memory
surviving between wakes, and each tick runs in the same shape as a standalone `/pr-status`.

Each tick then paces the next wake from the recommendation `/pr-status` prints **last** in its
output (enforced by the tick prompt above; the buckets are background for readers of this skill):

```
next-tick: {hot|warm|cold} (~{N}s) — {reason}
```

Use `{N}` as the `delaySeconds` for the next wake (the dynamic loop clamps to `[60, 3600]`). Don't
second-guess the bucket — `/pr-status` already weighs CI / push / transition state (its step 6):

- **hot** (~180s) — CI in flight or a PR changed this tick; check soon to catch the result.
- **warm** (~600s) — PRs awaiting review, nothing time-critical.
- **cold** (1200 → 1800s) — settled; escalating back-off via the `quietStreak` counter.

Once the next wake would land past `{stop_hour}:00`, the tick ends the loop with
`ScheduleWakeup(stop: true)`. If a tick produces no `next-tick:` line (e.g. it errored before
step 6), it falls back to ~600s and continues.

**Keep the cadence commentary terse — never the tables.** Each tick already ends with `/pr-status`'s
machine-readable `next-tick:` line, and the wakeup narrator shows the scheduled delay. Those two are
the entire cadence budget — do NOT add a third prose line restating the bucket, CI state, or
next-check time. This terseness applies ONLY to pacing commentary: the timestamp, tables, deltas,
and suggested-actions footer are the whole point of the tick and are always rendered in full.

### Fixed mode (interval given)

Invoke the `/loop` skill with the literal interval — `/pr-status`'s `next-tick:` line is ignored.
The same per-tick contract applies (minus the `ScheduleWakeup` ordering — cron fires fixed ticks),
embedded in the prompt for the same reason:

```
/loop {interval} /pr-status — each tick: invoke the pr-status skill via the Skill tool (never run its scripts from memory) and print its full dashboard (timestamp, both tables, deltas) as visible text; a tick that only runs scripts is a failed tick
```

Tell the loop to stop at `{stop_hour}:00` local time.

## Note

`/pr-status` is read-only and never prompts, so this loop runs **unattended** — leave it in a tab.
The suggested-action footer points you at `/ready-to-merge`, `/review-comments`, etc. as PRs become
actionable, but you run those yourself when you choose; the watcher never acts. For an attended
release-gatekeeper that prompts to push/defer/cancel, use `/watch-release` instead.
