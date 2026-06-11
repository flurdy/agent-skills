---
name: watch-release
description: >
  Start a recurring release-gatekeeper loop — runs /release-manager every 10 minutes until
  end of day in a dedicated tab. Shortcut for `/loop 10m /release-manager`. Prompts to push /
  defer / cancel as services become ready; runs attended.
model: sonnet
effort: medium
version: "1.0.0"
author: "flurdy"
---

# Watch Release

Start a `/release-manager` loop that runs every 10 minutes until 18:00 local time. Intended for
a dedicated kitty tab during parallel work — it keeps an eye on git/CI/deploy state and prompts
you when something is ready to ship.

## Usage

```
/watch-release            # every 10m, stop at 18:00
/watch-release 5m         # every 5m, stop at 18:00
/watch-release 5m 17      # every 5m, stop at 17:00
```

## Instructions

Parse optional arguments:

1. **Interval** — first arg matching `\d+m`. Default: `10m`.
2. **Stop hour** — first arg matching `\d{1,2}` (not already consumed as interval). Default: `18`.

Then invoke the `/loop` skill with:

```
/loop {interval} /release-manager
```

Tell the loop to stop at `{stop_hour}:00` local time. If the current time is already past the
stop hour, tell the user and don't start the loop.

## Note

`/release-manager` prompts (push / defer / cancel) and **blocks each tick until you answer**, so
this loop is meant to run **attended** in a visible tab. For an unattended, never-blocking view,
loop `/release-status` instead (`/loop 10m /release-status`) and act on its recommendations manually.
