# Private panel transport

Use `scripts/review-panel-stdin.py` for named panels in guarded Pi sessions. It is a small,
stateless transport around the existing `review-panel.sh` coordinator, not another panel runner.
It needs Python 3.10+, Bash, jq and the coordinator's usual prerequisites. The installed guard must
support this helper; an older guard denial is unavailable support, not permission to bypass it.

## Invocation

Send one JSON object on stdin through this exact command shape:

```bash
printf '%s' '{"version":1,"action":"check","panel":"focused","prompt":"Review this sanitized plan."}' | python3 ~/.agents/skills/second-opinion/scripts/review-panel-stdin.py
```

Keep the JSON in **single quotes**. Encode every apostrophe in JSON string values as `\u0027`;
use JSON escapes for newlines and other control characters. Do not interpolate shell variables,
use double-quoted payloads, add flags, change the helper path, redirect output, chain commands or
wrap this in another shell. The guard accepts this one fixed form, including inside a supported
parallel tool wrapper. It does not inspect task or billing authorization: those remain the skill's
responsibility. Read the JSON response directly from stdout and preserve it exactly.

No caller-selected file, config, cwd, environment, or executable fields exist. The helper uses the
ordinary user-owned panel configuration, inherits the invoking cwd, and creates all artifacts in a
fresh private temporary directory. It never calls another action automatically.

## Requests

All requests require `version: 1`, `action`, and the same exact nonempty sanitized `prompt`.
Optional `panel` defaults to `focused`. Optional `routeModels` and `routeEfforts` map exact route IDs
to the overrides already supported by the coordinator (at most eight each). Repeat the same panel,
prompt and overrides for every stage. Unknown fields, duplicate JSON keys and CLI arguments fail.

| Action | Additional fields | Result / authority |
|---|---|---|
| `check` | None | Existing check response; no model request. Display route identity, availability, limits and consent basis. |
| `run-local` | `panelSha256`, `promptSha256`; optional `openrouterSha256`, `timeout` | Existing local result array. Only after explicit panel authorization and applicable local billing checks; PR checkout preflight still applies. |
| `run-openrouter` | All three digests, `consent`, optional `timeout` | `consent: "configured"` only when every exact route is configured-allow; `"confirmed"` only after fresh approval of the displayed subset. Existing coordinator verifies digests and configured policy. |
| `decline-openrouter` | All three digests | Existing declined-result array; no model request. |
| `evaluate` | `policy: "quorum"` or `"consensus"`, `check`, `results` | Exact check object and an array of zero to two exact result arrays (local and OpenRouter). Existing evaluator retains partial/declined/disabled evidence and checks result bindings. No model request. |

`panelSha256`, `promptSha256` and `openrouterSha256` are the 64-character hashes returned by
`check`, never reconstructed or guessed. Route/config/policy/prompt drift still requires a new
check and applicable fresh consent. `timeout` is seconds, 1–1800, as in the existing coordinator;
otherwise the profile's per-route deadline applies. Transport adds a ceiling of eight maximum
route deadlines plus 30 seconds for run actions; non-run actions have a 30-second ceiling.

For evaluation, pass `check` as an object and `results` as arrays, not strings or paths. Preserve
raw results without summarizing them first. Do not turn omitted/failed routes into success or
manufacture receipts. The envelope transports data; it does not attest that caller-supplied
results came from a provider. Final synthesis and PR stale-safety remain owned by the skill.

## Bounds, cleanup and limitations

The prompt limit remains 65,536 UTF-8 bytes (the existing profile may be stricter, including its
OpenRouter completion contract). The transport caps request and stdout at 16 MiB, stderr at 8 KiB,
and evaluation at two arrays of at most eight routes. Caller/tool command-length limits may be
smaller: disclose unavailable transport, never silently truncate or switch to unapproved files.

The helper uses a fresh private directory and `umask 077` (directories 700, files 600). Nested
coordinator artifacts use that same private scratch tree. Success, ordinary errors, SIGINT and
SIGTERM clean it; cancellation first asks the coordinator to terminate its reviewers. SIGKILL,
power loss, or a child ignoring shutdown can leave residual private files/processes. No automatic
reaper or promise of crash-proof cleanup is introduced.

This is trusted-helper execution under a cooperative accidental-change guard, **not a sandbox**.
The installed helper and its sibling coordinator, normal runtime executables, user configuration,
and provider CLIs remain trusted. CLI hooks, caches and provider-side effects are not confined by
this transport. Never pass secrets in the prompt: the Bash tool call and session transcript contain
the literal packet. The existing caller-file interface remains available outside guarded sessions;
there is no general `/tmp` write grant, source lease acquisition, new persistent state, or native
adapter. Source/Git/package/system mutations and unrelated artifact collectors remain governed by
their existing rules.
