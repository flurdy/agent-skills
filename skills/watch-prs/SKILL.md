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
version: "2.1.3"
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

Invoke the `/loop` skill in **dynamic (self-paced)** mode. The loop prompt is the only text
re-injected verbatim on every wakeup — `pr-status`'s SKILL.md is NOT re-read on wakeup turns unless
the tick explicitly loads it — so the render contract AND the render-before-schedule ordering must
live inside the prompt string itself, not just here:

```
/loop /pr-status — each tick: invoke the pr-status skill via the Skill tool (never run its scripts from memory), then write the confirmation text the loop requires before ScheduleWakeup — and that confirmation IS the full dashboard: timestamp line, both tables, deltas, next-tick line. A one-line confirmation like "wakeup scheduled" is a failed tick. Only after the dashboard is printed, call ScheduleWakeup as the very last action; the turn ends the instant it returns
```

Pass that whole string (including everything after the dash) as the loop prompt, and echo it back
unchanged in every `ScheduleWakeup` call so later ticks keep the contract.

**Per-tick ordering — render first, schedule last.** The dynamic loop's turn ends the moment
`ScheduleWakeup` returns; any text intended after it is silently dropped, which reads as a tick that
"only ran scripts". The `/loop` skill already requires confirmation text to be written *before*
`ScheduleWakeup` — in this loop, **that confirmation text is the dashboard itself**, never a
one-line summary. So every tick must, in order:

1. **Invoke the `pr-status` skill via the Skill tool.** Its render steps (table columns, deltas,
   `next-tick:` spec) get summarized out of context between ticks — running the fetch scripts from
   memory yields data with no table spec, and the tick renders nothing.
2. **Emit the full `/pr-status` output** — timestamp line, both tables, deltas, suggested actions,
   `next-tick:` line — as visible text. Every tick, including unchanged ones. This is the
   pre-`ScheduleWakeup` confirmation; a one-liner like "Wakeup scheduled for 10:00" in its place is
   a failed tick.
3. **Call `ScheduleWakeup` last.** Never before step 2; a bare `ScheduleWakeup` with no rendered
   dashboard is a failed tick, not a terse one.

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

**Keep the cadence commentary terse — never the tables.** Each tick already ends with `/pr-status`'s
machine-readable `next-tick:` line, and the dynamic `/loop` prints its own one-line narrator for the
next wake. Those two are the entire cadence budget — do NOT add a third prose line restating the
bucket, CI state, or next-check time. This terseness applies ONLY to pacing commentary: the
timestamp, tables, deltas, and suggested-actions footer are the whole point of the tick and are
always rendered in full.

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
