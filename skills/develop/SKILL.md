---
name: develop
description: "Load before authorized code changes: features, fixes, refactors, tests, and mechanical edits, including discussion-to-coding transitions. Read separately from edits. Skip read-only requests and implementation already owned by a specialist."
model-tier: standard
effort: high
version: "1.0.1"
author: "flurdy"
---

# Develop

A lightweight coding entry point, not another implementation workflow. Request the
runtime's configured standard/high route, then use normal repository-grounded coding
judgment. Explicit invocation is `/develop <task>`; in Pi use `/skill:develop <task>`. On Claude Code this skill carries no `model:` pin on purpose: it rides the session model rather than downgrading to the standard alias, while Pi routes by `model-tier`.

Read this skill once per new coding run, even if its text remains in context from a
previous run. Use a standalone skill read before generating mutation calls.
Wait for the next model response before emitting edits, writes, or shell mutations;
do not bundle the read and mutations in the same response. Apply the same separation
when loading a specialist below. Already-generated edits are not upgraded by a model
switch.

## Choose the next step

- Keep read-only requests read-only. Skill selection does not authorize edits or
  override plan mode, repository rules, scope, or confirmation requirements.
- If an implementation specialist already owns the work, continue it; do not restart
  through this entry point just to request a route.
- If a bug's cause is unknown, use [diagnose-bug](../diagnose-bug/SKILL.md) first.
- If consequential architecture, security, public-contract, migration, or hard-to-reverse
  decisions remain unresolved, use [architect](../architect/SKILL.md) before coding.
- For implementation-ready work with interacting behavior, meaningful state/error
  paths, or local design trade-offs, load
  [implement-solution](../implement-solution/SKILL.md). Reassess if an initially simple
  edit develops those characteristics; hand off without restarting completed work.
- Otherwise, make the smallest appropriate change using established repository
  patterns and proportionate tests/checks. Do not add planning, delegation, or review
  ceremonies merely because this skill loaded.

## Routing limits

Automatic loading is best-effort, not a pre-write enforcement mechanism. Metadata
requests capability; it does not prove the active model changed. Respect runtime spend
and manual-selection controls; do not edit routing configuration or launch another
model to force a route.

Pi currently protects against nested tier downgrades only after a routed run begins.
The first standard-tier route can replace a stronger session model. This skill does
not establish a capability floor; see [model routing](../../MODEL_ROUTING.md).
