# Second opinions in guarded Pi sessions

## Disposition

Named panels are **unsupported** in guarded plan, conflict, acquiring, lost, and file-only
implementation sessions. This includes `quorum` and `consensus` with any profile, including a
profile named `premium`. `premium` is not an additional valid `--agent` value. A direct Claude
`--model fable` request is still one route, not a premium panel.

Stop **before creating** prompt, PR-snapshot, check, or result artifacts, running a panel helper,
or requesting panel billing consent. Do not emulate a panel with several direct calls or a
subagent workflow. Do not silently downgrade an explicitly selected panel: offer one independent
direct route and wait for the user to select it. Never recommend implementation mode solely for
a supported read-only consultation.

Use the current host's guard state; an environment variable, bead claim, writable-looking path,
or successful unknown-script invocation does not establish authority. If the state is unclear,
inspect `/leases` and `/grants` rather than testing writes. An unsupported or unverifiable state
is not permission to create artifacts.

## Policy support matrix

This is a policy matrix, not an assertion that a CLI is installed, authenticated, affordable,
or successfully launched. Record actual runtime evidence separately for the current task.

| Route | Guarded plan / file-only eligibility | Independent prerequisites | Launch evidence required |
|---|---|---|---|
| Direct `peer` | Eligible after resolving exactly one independent vendor | Selected route's executable, auth, billing, and read-only contract | Evidence for that selected route; not for all possible peers |
| Direct Claude / `ask-claude` | Eligible; no panel artifacts required | CLI supports the requested model and read-only flags; subscription check or current-run consent | Terminal response and actual model when reported |
| Direct Fable / `ask-fable` | Eligible as a single Claude route | Requested model/effort supported; its own billing check | Fable result; an Opus result does not prove Fable availability |
| Direct Codex | Eligible with read-only sandbox | Executable, auth and billing check; native options supported | Terminal Codex response, not merely login status |
| Direct Gemini | Eligible with its sandbox | Executable, sandbox, auth and current-run billing consent as applicable | Terminal Gemini response; absence is unavailable, not passing |
| Verified external read-only child | Eligible with inherited cwd; async-only | Current `subagent` capability/preflight and guard discovery both accept the exact definition; separate billing rules | Completed run plus read-only contract and observed terminal process |
| Named quorum / premium-profile / consensus panel | Unsupported by design in guarded states | No approved private-artifact mechanism | Report blocked; never count as passing or as a partial panel launch |
| Named panel in a live worktree implementation session | Existing panel procedure only; no new authority from this document | Exact configured panel, digests, prerequisites, limits and metered consent | Per-route results and evaluation; passing tests alone are not live provider evidence |

Direct eligibility does not exempt artifact-producing context collectors such as the PR snapshot
workflow. If required context cannot be collected within current authority, report that context
boundary as blocked; do not skip PR identity checks or redirect the review to another checkout.

### Current compatibility baseline — 2026-09-15

This baseline is evidence for Pi 0.85.1 only. It records one machine's runtime results rather than
promising future authentication, model availability, pricing or compatibility.

| Route | Plan policy | Executable / auth evidence | Billing evidence | Launch evidence |
|---|---|---|---|---|
| `peer` resolved to direct Claude Opus | eligible; parent vendor was OpenAI | Claude Code 2.1.267; `claude.ai` subscription login; no API override | exact `opus` policy allowed | passed through actual Pi guarded Bash; explicit alias accepted and terminal marker returned; text mode did not report canonical model |
| Direct Fable | eligible | same Claude executable/auth evidence | exact `fable` policy allowed | passed through actual Pi guarded Bash; explicit alias accepted and terminal marker returned; text mode did not report canonical model |
| Direct Codex | eligible | Codex CLI 0.154.0; ChatGPT login; no API override | exact `gpt-6-astra` policy allowed | passed through actual Pi guarded Bash; reported model `gpt-6-astra`, sandbox `read-only`, approval `never`, terminal marker returned; configured user hooks ran |
| Direct Gemini | policy-eligible only | executable present; auth not established | unknown; no consent requested | skipped; not passing |
| External `claude-code` child | eligible only after current discovery/preflight | pi-subagents 0.67.0; Claude Code 2.1.267; existing CLI auth | native model identity cannot be prebound; user gave one-run subscription/usage-credit consent | passed: canonical model `claude-opus-5`, inherited cwd, async run complete, external exit 0, runner terminal observed, plan permission, tools none, strict empty MCP, persistence false |
| External `codex-exec` child | discovery-eligible; inherited cwd only | executable and current definition available | native child model not prebound | not run; direct Codex does not prove child launch |
| External `cursor-agent` child | discovery contract eligible | executable unavailable | not evaluated | unavailable; not passing |
| Named panels | unsupported by design | helper availability is irrelevant in guarded states | no panel consent requested | current-Pi scripted provider passed pre-dispatch denial: helper marker absent, temp contents unchanged, no source lease; not a provider success |

The direct smoke commands used fresh isolated Pi `--plan` processes and returned successful Bash tool
results. The external-child smoke used a separate live Pi `--plan` RPC process so its async completion
watcher could observe the runner process terminal; the no-tools child itself made no file changes.
The first detached print-mode probe completed its child but exited before terminal observation and is
not counted as the passing process-terminal smoke. No Gemini or OpenRouter prompt was exposed.

## Why no private-artifact exception

The panel coordinator already owns private internal temporary files, but its multi-stage protocol
requires caller-owned prompt, check, and result files. Native Write, `chmod`, redirects and cleanup
are not permitted merely because files are disposable. The guard also rejects `mktemp` and
recognizable invocations of `review-panel.sh` and `openrouter-panel.sh`, including bounded shell
and `env` wrapper forms. Existing prompt files do not authorize helper execution.

This remains an accidental-change guard, not a shell sandbox: renamed helpers, arbitrary script
indirection and hostile filesystem changes are not comprehensively detected. Passing the checker
is not authorization to exploit those gaps. No broad temporary-directory, home-directory or
repository grant is introduced. Persistent exact-file grants and dynamic source leases are not
private review artifacts. Do not use `/grant-file`, arbitrary Bash writes, an interpreter, or a
new stdin wrapper as a workaround.

A future supported mechanism would need a separately reviewed typed invocation boundary with
trusted helper identity, no caller-selected filesystem paths, private bounded artifacts, and
cancellation/failure/reload cleanup. This disposition does not add that capability.

## External child compatibility

Preserve the verified inherited-cwd async path. Writer variants, unsafe definition overrides,
explicit output authority (`output`, file-only results, `sessionDir`), alternate cwd or agent
scope, managed worktrees, remote sharing and unverified agents remain ineligible. Do not pass
native Pi child options to an external CLI runner to obtain repository tools. Supply sanitized
repository evidence in its packet when its verified profile has no tools.

Pi 0.85.1 omits the experimental server/client packages from its published installation.
The pi-subagents 0.65.1 launch dependency was incompatible with that host; 0.67.0 corrected that
specific dependency. This is historical compatibility evidence, not blanket certification of
later versions, current discovery or authentication. Do not install those experimental packages
or modify Pi's distribution as a repair. Re-run discovery and the current runtime preflight.

## Diagnostics and evidence

Keep these outcomes separate:

- **Unsupported option:** the route or external runner does not accept the requested native option.
- **Plan-policy denial:** no eligible artifact/launch authority; stop before dispatch and consent.
- **Unavailable executable/auth:** policy may permit the route, but its runtime prerequisites fail.
- **Version incompatibility:** discovery or launch infrastructure is incompatible; preserve the error.
- **Billing consent required/declined:** eligibility and login do not authorize metered exposure.
- **Failed, timed out or incomplete:** preserve returned evidence; never retry or substitute silently.

For each live smoke record date, host/runner versions, guard state, exact selected route/options,
billing basis, completion status and permission evidence. Mark skipped, unavailable, declined or
blocked routes explicitly; none is a passing smoke. A fixture using the current Pi host proves
policy dispatch, not real CLI auth, model availability or billing. A successful no-tools child
proves execution, not independent repository inspection.

Outside guarded states, keep the existing panel/prompt/subset/policy digest binding, exact route
selection, provider independence, limits, model-policy checks and metered-route consent unchanged.
Recheck from scratch after a mode or scope change; do not reuse stale checks or approvals. Preserve
partial results and `incomplete` classification without manufacturing quorum. Consensus remains
an evidence-backed comparison gated by its unique-provider threshold, never a majority vote.

The [panel protocol](review-panels.md), [billing contract](billing-evidence.md), and
[Pi guard contract](https://github.com/flurdy/pi-session-mode/blob/main/docs/guard.md) own their
respective detailed rules.
