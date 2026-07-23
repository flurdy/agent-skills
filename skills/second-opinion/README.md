# Second opinion

`/second-opinion` obtains an independent review of a pull request, plan, bug report, or
technical question. It is for improving a decision, not outsourcing it: review findings still
need checking against the repository before action.

[`SKILL.md`](SKILL.md) is the operational contract for an agent. This README is the human
quick-start and deliberately links to the detailed policy rather than reproducing it.

## Choose a review mode

| Need | Command | What happens |
|---|---|---|
| A quick independent perspective | `/second-opinion ask "…"` | Uses `peer`, the default single route chosen to differ from the current model vendor. |
| Review an open pull request | `/second-opinion review-pr 123` | Gathers PR metadata and diff, then asks one independent peer to review it. |
| Challenge an implementation plan | `/second-opinion validate-plan "…"` | Reviews feasibility, gaps, risks, dependencies, and simpler alternatives. |
| Structure a bug investigation | `/second-opinion triage-bug "…"` | Requests root-cause hypotheses and falsification steps. |
| Ask a specific provider | `/second-opinion ask "…" --agent codex` | Runs exactly the named local CLI route. |
| Check panel coverage | `/second-opinion review-pr 123 --agent quorum --panel focused` | Runs a named panel and reports whether enough distinct providers returned. |
| Compare panel claims | `/second-opinion validate-plan "…" --agent consensus --panel extreme` | Runs a named panel, then compares claims only if quorum is met. |

Use one peer for ordinary decisions. Use a panel when different provider perspectives are
material enough to justify the extra time, review effort, and—where configured—cost.

## Direct peer review

`peer` is both the default and the recommended ordinary path. The skill prefers a provider
different from the one that produced the work:

- Claude session → Codex first, then Gemini.
- GPT/Codex session → Claude first, then Gemini.
- Other sessions → the best available Claude or Codex route.

You can choose a direct route explicitly with `--agent claude`, `--agent codex`, or
`--agent gemini`. Direct routes use their installed CLI's normal authentication and model defaults.
An explicit `--model <id>` is passed to that CLI; omit it unless you need a particular model.

Examples:

```text
/second-opinion review-pr 123
/second-opinion validate-plan "Move the cache invalidation to the write path..."
/second-opinion triage-bug "Checkout intermittently returns 500 after a retry"
/second-opinion ask "What edge cases are missing from this migration?" --agent claude
```

## Panels: quorum and consensus

A panel is a configured set of local and optionally OpenRouter routes. `quorum` and `consensus`
run the same panel; they differ only in the interpretation:

- **Quorum** is mechanical coverage: did the configured number of *distinct providers* return?
  Multiple models from one provider count once.
- **Consensus** is claim comparison after quorum. It must distinguish supported agreements,
  disagreements, repeated assumptions, same-provider corroboration, and unavailable routes.

Neither a vote count nor agreement proves a finding is correct. Verify each material finding in the
repository.

Useful commands:

```text
/second-opinion review-pr 123 --agent quorum
/second-opinion review-pr 123 --agent quorum --panel focused
/second-opinion validate-plan "..." --agent consensus --panel extreme
/second-opinion review-pr 123 --agent quorum --panel large \
  --route-model claude-fable=opus --route-effort claude-fable=max
```

`focused` is the local Claude-and-Codex built-in. `local-legacy` is a reserved local-only
compatibility panel. `--agent all` is deprecated; use `--agent quorum` instead.

## Setup

For a direct route, install and authenticate the relevant CLI:

- `claude`
- `codex`
- `gemini`

For panels, `jq` and the included coordinator are also required. Local panel profiles and any
OpenRouter routes live in:

```text
~/.agents/second-opinion/config.json
```

The configuration contains route identities and limits, not credentials. See
[review-panels.md](references/review-panels.md) for the supported schema, built-ins, per-route
model/effort overrides, and limits.

OpenRouter panels additionally require `curl` and `OPENROUTER_API_KEY` in your shell or secret
manager. Put exact OpenRouter model IDs in the local configuration, never in this shared README.

## Cost, privacy, and consent

Local CLI routes are read-only reviewers and may inspect readable files in the current repository.
Only run them where that repository is safe to share with their providers. The skill removes obvious
secrets from assembled context, but you remain responsible for not requesting review of credentials,
private keys, `.env` contents, or sensitive personal data.

OpenRouter routes receive only the sanitized prompt—no tools or repository access—but consume
credits. If the selected panel contains OpenRouter routes, the skill shows the exact metered subset,
limits, and timeout and asks for approval immediately before the requests. Approval is one-run only.
Declining retains any local results and records the OpenRouter routes as declined.

The skill never silently retries failed routes, substitutes models, or expands a panel. See
[openrouter-consensus.md](references/openrouter-consensus.md) for the full safety boundary.

## Reading the result

Expect the result to include each route's status and effective model/effort, followed by the raw
successful opinions or explicit failures, timeouts, and declines.

Treat the final assessment as a review checklist:

1. Check each actionable finding against the code, diff, tests, or primary documentation.
2. Keep independently evidenced concerns, including a single strong concern.
3. Reject unsupported repetition; several models repeating an assumption is not evidence.
4. Record unresolved disagreement as uncertainty, not a majority decision.
5. Fix, defer, or track only findings that remain valid after verification.

For model and effort precedence—including why omitted settings are reported as `native-default`—see
[external-model-resolution.md](references/external-model-resolution.md).

## Troubleshooting

| Symptom | What to do |
|---|---|
| `peer` route is unavailable | Install/authenticate another supported local CLI, or select an available route explicitly. The skill does not silently substitute one. |
| A panel falls short of quorum | Read the unavailable-route statuses; partial results are still useful but are not complete coverage. |
| OpenRouter routes were not run | Check the displayed prerequisite or consent status. Declining consent is expected to leave those routes as declined. |
| A panel configuration is rejected | Check route IDs/models for uniqueness and use the schema in [review-panels.md](references/review-panels.md). |
| Result has conflicting recommendations | Verify the disputed claims in the repository; use consensus as a structured comparison, not a tie-breaker. |
| Context is too large or sensitive | Provide a focused, sanitized summary. Do not paste secrets or rely on silent truncation. |

## Further reading

- [Operational instructions](SKILL.md)
- [Panel configuration and execution](references/review-panels.md)
- [OpenRouter safety and consent](references/openrouter-consensus.md)
- [Model and effort resolution](references/external-model-resolution.md)
