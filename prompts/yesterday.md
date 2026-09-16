---
description: Read-only previous-workday recap through the canonical today workflow
argument-hint: "[no arguments]"
---

Load and follow the skill named `today` with the arguments `--previous-workday $ARGUMENTS`,
forwarding anything supplied unchanged for canonical validation. If the Skill tool is unavailable,
read `~/.agents/skills/today/SKILL.md` and follow it with the same arguments using the exposed
read-only tools. If the canonical skill is missing or unreadable, stop and report it as unavailable.
Never fall back to same-day mode. Perform no collection, rendering, or date selection here.
