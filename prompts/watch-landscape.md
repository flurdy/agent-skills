---
description: Refresh /landscape quick on a fixed cadence until end of day
argument-hint: "[minutes, default 30]"
---

Start an unattended, read-only refresh of `/landscape quick` every $ARGUMENTS minutes (default 30)
until 18:00 local time. Do not run `/landscape` in this turn; only start the loop.

If `watch_loop` is available (Pi protocol v1):

1. Call `watch_loop` with `action: status`. Continue only on `protocolVersion: 1` and no watch
   already `armed`, `running`, or `paused`; otherwise show the status and stop.
2. Make the terminating start call with `mode: fixed`, `label: Landscape`, `initialDelaySeconds`
   and `intervalSeconds` set to the interval in seconds, `missedCompletionPolicy: retry`, `stopAt`
   as today's 18:00 local deadline in ISO-8601 with offset, and this tickPrompt verbatim:

   ```text
   Load and follow the skill named `landscape` with the argument `quick`. Render every block as visible text. Compare each table with the previous tick's tables in this conversation and prefix rows that appeared or changed with `Δ`; on the first tick, or when nothing changed, say so in one line. Do not execute any suggested action. Finish only after the visible output with the matching `watch_loop complete` call injected by the runtime.
   ```

Otherwise, in Claude Code, invoke the `/loop` skill with the interval in minutes, for example:

```text
/loop 30m /landscape quick
```

If neither scheduler is available, say so and stop; do not imitate one.
