---
name: rebase-main
description: Rebase the current branch onto an updated main branch. Alias for `/rebase main`.
allowed-tools: "Read,Skill"
model-tier: economy
model: haiku
effort: low
version: "2.0.0"
author: "flurdy"
---

# rebase-main (alias)

Retained entry point. The workflow lives in the `rebase` skill; this alias only fixes the
target mode.

## Usage

```
/rebase-main 
```

## Instructions

Invoke the `rebase` skill with the Skill tool and the arguments `main {args}`, where
`{args}` are the arguments given here, if any. If the Skill tool is unavailable, read
`~/.agents/skills/rebase/SKILL.md` and follow it with that target. Perform no step of the
rebase here.
