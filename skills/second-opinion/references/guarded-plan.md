# Second opinions in guarded Pi sessions

## Disposition

Named panels are eligible in guarded plan, conflict, acquiring, lost, and file-only sessions
**only through the installed [private stdin transport](panel-stdin.md)** and a guard supporting
that exact command shape. Caller-file panel commands remain unsupported. This applies to `quorum`
and `consensus` with any profile, including `premium`; a profile is not another `--agent` value.

Stop **before creating** caller-owned prompt, PR-snapshot, check, or result artifacts. The stdin
helper owns its scratch files without source-write authority. A missing helper or older guard is
unavailable support: do not bypass it, emulate a panel with direct calls or a subagent workflow,
or silently choose another route. Do not emulate unsupported panels. Never recommend implementation
mode solely for a supported read-only consultation. Panel authorization and billing approval still
precede their respective execution stages; check alone authorizes no model request.

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
| Named quorum / premium-profile / consensus panel | Eligible through the installed stdin helper only | Supporting guard, helper and usual coordinator prerequisites; selected routes and consent | Actual bounded helper/route results; unavailable or skipped providers are not passing |
| Named panel in a live worktree implementation session | Existing panel procedure only; no new authority from this document | Exact configured panel, digests, prerequisites, limits and metered consent | Per-route results and evaluation; passing tests alone are not live provider evidence |

Direct eligibility does not exempt artifact-producing context collectors such as the PR snapshot
workflow. If required context cannot be collected within current authority, report that context
boundary as blocked; do not skip PR identity checks or redirect the review to another checkout.

### Historical compatibility baseline — 2026-09-15

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

## Private-artifact exception

The trusted `review-panel-stdin.py` transport reuses the existing coordinator. Each request owns
one fresh private scratch directory, supplies coordinator files internally, and returns bounded
JSON on stdout. No stateful native adapter, caller-selected artifact paths or shell-path parser is
needed. Read [the exact invocation and schema](panel-stdin.md) before using it.

The guard still rejects caller-file `review-panel.sh`/`openrouter-panel.sh` invocations, `mktemp`,
native Write, arbitrary redirects and cleanup. It allows only a literal single-quoted JSON printf
pipe into the installed Python helper; old guards still deny or lack support. Passing a different
command through a checker gap is not authorization. No broad temporary-directory, home-directory,
repository or exact-file grant is introduced; no source lease is acquired.

The helper and its sibling coordinator are trusted installed code, not digest-verified native
capabilities or an OS sandbox. Private permissions and existing exit/signal cleanup address normal
runs. SIGKILL, power loss, or uncooperative children can leave private artifacts/processes; no
crash-proof cleanup or automatic reaper is claimed. Shell/tool transcripts contain the sanitized
inline packet, and provider CLI config/cache effects remain outside the guard's confinement.

The compatibility table above is historical 2026-09-15 evidence for the previous deny-only policy,
not proof that the new path or any current provider launched. Recheck current runtime support.

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
