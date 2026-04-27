---
name: watch-prs
description: Start a recurring PR status dashboard — polls every 5 minutes until end of day. Shortcut for `/loop 5m /pr-status`.
model: haiku
effort: low
version: "1.1.0"
author: "flurdy"
---

# Watch PRs

Start a `/pr-status` loop that runs every 5 minutes until 18:00 local time.

## Usage

```
/watch-prs            # every 5m, stop at 18:00
/watch-prs 10m        # every 10m, stop at 18:00
/watch-prs 3m 17      # every 3m, stop at 17:00
```

## Instructions

Parse optional arguments:

1. **Interval** — first arg matching `\d+m`. Default: `5m`.
2. **Stop hour** — first arg matching `\d{1,2}` (not already consumed as interval). Default: `18`.

Then invoke the `/loop` skill with:

```
/loop {interval} /pr-status
```

Tell the loop to stop at `{stop_hour}:00` local time. If the current time is already past the stop hour, tell the user and don't start the loop.
