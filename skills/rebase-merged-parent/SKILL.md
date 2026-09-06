---
name: rebase-merged-parent
description: Rebase onto main after the parent PR merged, keeping only your commits. Alias for `/rebase merged`.
allowed-tools: "Read,Skill"
model-tier: economy
model: haiku
effort: low
version: "2.0.0"
author: "flurdy"
---

# rebase-merged-parent (alias)

Retained entry point. The workflow lives in the `rebase` skill; this alias only fixes the
target mode.

## Usage

```
/rebase-merged-parent [{old-parent}] [--old-tip {sha}]
```

## Instructions

Invoke the `rebase` skill with the Skill tool and the arguments `merged {args}`, where
`{args}` are the arguments given here, if any. If the Skill tool is unavailable, read
`~/.agents/skills/rebase/SKILL.md` and follow it with that target. Perform no step of the
rebase here.
