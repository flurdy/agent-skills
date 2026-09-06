---
name: rebase-parent
description: Rebase the current branch onto an updated stacked parent branch. Alias for `/rebase parent`.
allowed-tools: "Read,Skill"
model-tier: economy
model: haiku
effort: low
version: "2.0.0"
author: "flurdy"
---

# rebase-parent (alias)

Retained entry point. The workflow lives in the `rebase` skill; this alias only fixes the
target mode.

## Usage

```
/rebase-parent [{parent-branch}]
```

## Instructions

Invoke the `rebase` skill with the Skill tool and the arguments `parent {args}`, where
`{args}` are the arguments given here, if any. If the Skill tool is unavailable, read
`~/.agents/skills/rebase/SKILL.md` and follow it with that target. Perform no step of the
rebase here.
