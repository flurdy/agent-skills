---
name: token-dashboard
description: Read-only current-session and UTC-week token telemetry dashboard for Pi, Claude Code, Codex, and optional OpenRouter management analytics.
allowed-tools: "Read,Bash(~/.claude/skills/token-dashboard/scripts/token_dashboard.py:*),Bash(~/.codex/skills/token-dashboard/scripts/token_dashboard.py:*),AskUserQuestion"
model-tier: economy
model: haiku
effort: low
version: "1.0.0"
author: "flurdy"
---

# Token Dashboard

Show read-only token telemetry for the current session and current UTC calendar week. The week starts
Monday at 00:00 UTC. This skill has no `/usage` alias and does not modify transcripts or settings.

## Usage

```text
/token-dashboard                    # terminal dashboard; optional OpenRouter analytics when configured
/token-dashboard --offline          # local telemetry only; guarantees no network
/token-dashboard --json             # normalized schema v1 JSON
/token-dashboard --json --offline   # machine-readable local-only report
/token-dashboard --session-id ID    # explicitly select a known local session; the ID is never emitted
```

Resolve `scripts/token_dashboard.py` relative to this `SKILL.md`, then run the executable with the
user's arguments. Pi can load the managed Claude/Codex skill directory through its configured skills
path, and the collector remains compatible with Pi telemetry:

```bash
/path/to/token-dashboard/scripts/token_dashboard.py --offline
/path/to/token-dashboard/scripts/token_dashboard.py --json
```

Do not replace the collector with ad-hoc transcript reads or provider calls. Render its output as-is,
including unavailable and partial source diagnostics. Never call this skill `/usage`.

## Setup and source authority

The stdlib-only collector reads these telemetry roots recursively:

- Claude Code: `~/.claude/projects/**/*.jsonl`; only top-level assistant `message.usage` is
  authoritative. Parent, subagent, and extra-agent transcripts are globally deduplicated.
- Pi: `~/.pi/agent/sessions/**/*.jsonl`; official assistant-message usage is authoritative. Parent
  sessions and linked nested child runs are deduplicated.
- OpenAI Codex: `~/.codex/sessions/**/*.jsonl`; rollout `event_msg/token_count` cumulative counters
  are authoritative and converted to duplicate-suppressed deltas.
- OpenRouter, optionally: Management Analytics API metadata plus one UTC-week query. Set
  `OPENROUTER_MANAGEMENT_API_KEY`; an `OPENROUTER_API_KEY` is inference-only and is never sent.

The collector never reads auth files. It does not emit or persist credentials, prompts, responses,
tool output, raw transcript lines, session/message IDs, file paths, or raw API error bodies.
OpenRouter requests use the fixed `https://openrouter.ai` origin, reject redirects, bound response
size and timeout, and do not retry. `--offline` performs no network request even when a management
key exists.

See [telemetry sources and authority](references/sources.md) for upstream evidence, retention,
authentication, period semantics, exactness definitions, and the prior-art decision.

## Reading the report

Terminal output always has **Current session**, **Week**, and **Sources** sections. Every usage row
names its scope, source, harness, provider, model, agent, period/timezone, exactness, request count,
and nullable token counters. Control characters in displayed model and agent values are replaced.
Unavailable sources remain visible and do not make healthy sources fail.

JSON output uses normalized schema version `1` with:

- `generatedAt` and `periods` for `current-session` and `week`;
- UTC start/end boundaries, completeness, and current-session selection precision;
- `sources` with status, exactness, detail, and authority;
- flat `usage` rows with nullable `input`, `output`, `cacheRead`, `cacheWrite`, `reasoning`, and
  `total` counters, controlled unavailable reasons, and subset/exclusivity semantics.

Current-session selection uses `--session-id` when supplied. Otherwise it detects an active Pi,
Claude Code, or Codex harness from supported runtime environment evidence and selects only that
harness. Pi parent and nested child-run sessions are linked by their official directory layout and
`parentSession` metadata when present. Without active-harness evidence, only the single globally
newest local session is selected and labelled `estimated`; unrelated per-harness sessions are not
combined.

## Limitations

- Local JSONL telemetry is not provider billing, subscription quota, or an authoritative allowance.
  Claude, Pi, and Codex subscription allowance can be unavailable.
- OpenRouter analytics is API telemetry for returned metrics, not subscription quota. Metric
  availability is negotiated from the live metadata response; truncated or skipped rows are partial.
- Missing counters stay `null`; the collector does not invent zero. Claude does not record reasoning
  or a portable total in the accepted usage rows. Pi reasoning is a subset of output. Codex cached
  input and reasoning are subsets of input and output respectively.
- Malformed or oversized rows, missing timestamps, incompatible duplicate snapshots, rejected
  symlinks, read failures, missing roots, network failures, and sanitized 401/403/429 responses
  degrade only the affected source.
- Version 1 supports UTC only and offers no timezone option.

## Maintainer validation

```bash
python3 -m unittest discover -s skills/token-dashboard/tests -p 'test_*.py' -v
make validate-skills
make test-validate-skills
make clean-code
```

Tests use temporary telemetry roots and mocked OpenRouter requests; they send no real network
traffic and contain no live credentials.
