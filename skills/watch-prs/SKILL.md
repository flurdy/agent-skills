---
name: watch-prs
description: >
  Start a recurring PR status dashboard — runs /pr-status on an adaptive cadence
  (fast when CI is in flight, backing off when settled) until end of day. Unattended:
  renders tables and suggested next actions, never prompts or blocks.
model-tier: standard-workflow
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
effort: medium
version: "2.3.2"
author: "flurdy"
---

# Watch PRs

Run `/pr-status` on a self-rescheduling loop until a stop hour. Each tick is an ordinary
`/pr-status` run that ends by scheduling the next one. Unattended — leave it in a tab.

## Usage

```
/watch-prs            # adaptive cadence, stop at 18:00   (default)
/watch-prs 17         # adaptive, stop at 17:00
/watch-prs 10m        # fixed 10-minute interval, stop at 18:00
/watch-prs 5m 17      # fixed 5m, stop at 17:00
```

## Instructions

Parse arguments: an interval matching `\d+m` (absent → adaptive mode, the default), and a stop
hour matching `\d{1,2}` (default `18`). If the current time is already past the stop hour, say so
and don't start.

**Session-model guard (adaptive mode only).** Before anything else, state which model powers this
session — your system prompt names it ("You are powered by …"). If it is any Fable model, do NOT
start the adaptive loop: say why, point at the alternatives below, and end the turn without
calling `ScheduleWakeup`. This is not a capability judgment you can pass by intending to render
first — on wakeup turns Fable-class models emit their main output as the turn's final message
after tool calls, and `ScheduleWakeup` ends the turn the instant it returns, mechanically
discarding that message; every tick will be blank regardless of intent. Alternatives: run the
watcher in a tab launched with `claude --model sonnet` (session-only, leaves the saved default
alone), or use fixed mode (`/watch-prs 10m`), whose cron ticks carry no scheduling duty and work
on any model. Sonnet- and Opus-class sessions pass this guard.

(This skill deliberately has no `model:` pin — the guard must run on the session model to be able
to name it.)

### Adaptive mode (default)

Do NOT run `/pr-status` in this turn, and do NOT use the `/loop` skill. Just start the loop:
call `ScheduleWakeup` (load it via ToolSearch if needed) with `delaySeconds: 60` and this prompt,
substituting the stop hour — then confirm the loop is started and the first dashboard lands in
about a minute:

```
/pr-status — afterwards schedule the next check: ScheduleWakeup(delaySeconds = N from your next-tick line, prompt = this message verbatim), or ScheduleWakeup(stop: true) if that wake would land past {stop_hour}:00
```

Each wakeup is then a plain `/pr-status` run — dashboard first, one `ScheduleWakeup` call at the
very end. `/pr-status` closes with `next-tick: {hot|warm|cold} (~{N}s) — {reason}`; that `N`
(hot ~180s / warm ~600s / cold 1200–1800s, 600 if the line is missing) is the next delay.

Keep scheduling to that single trailing call — ticks that dwell on scheduling have skipped the
dashboard, and the dashboard is the whole point.

### Fixed mode (interval given)

Invoke the `/loop` skill with the literal interval; the `next-tick:` line is ignored:

```
/loop {interval} /pr-status
```

Tell the loop to stop at `{stop_hour}:00` local time.

## Note

`/pr-status` is read-only and never prompts, so this loop runs unattended. Its suggested-action
footer points at `/ready-to-merge`, `/review-comments`, etc. as PRs become actionable — you run
those yourself; the watcher never acts. For an attended release gatekeeper, use `/watch-release`.
