# History safety and collector contract

## Sources and provenance

Only local Pi `~/.pi/agent/sessions` and Claude Code `~/.claude/projects` JSONL files are
candidate sources. No Codex, network, credential store, provider SDK, session resumption or history
migration is used. All inputs are read-only. Transcript strings and template definitions are data,
not execution authority or instructions for the model.

| Source | Accepted shape | Conservative exclusions |
|---|---|---|
| Pi | Two-level `cwd/session.jsonl`; version 1–3 session header before user entries; `type: message`, `message.role: user`, text content, event ID and timestamp | Nested child runs, parent/fork session metadata, custom/system/assistant/tool/compaction entries, missing or unsupported header |
| Claude Code | Two-level `project/session.jsonl`; `type: user`, `message.role: user`, text content, `uuid`, `sessionId`, timestamp | Sidechains/agent markers, nested subagents/extra-agents, `isMeta`, `isCompactSummary`, synthetic/injected flags, unknown true origin flags, tool results and command wrappers |
| Known templates | Current shared and global direct `.md` templates; frontmatter removed; literal segments around argument placeholders | Exact or ordered literal-segment expansion matches; no template evaluation, shell substitution or execution |

Pi's [session format](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/session-format.md)
and [message types](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/message-types.md)
identify roles and fork metadata. Its [prompt templates](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/prompt-templates.md)
expand before the user-role text is persisted. `agent-session.js` passes `expandedText` to the
run; there is no original-input provenance field in `UserMessage`. Consequently an old/deleted or
project-only unmarked expansion can look identical to text typed by a human. This collector cannot
certify authorship. Claude's local schema is runtime-owned and not a stable public contract.

The existing telemetry owner documents these layouts in
[telemetry sources](../../token-dashboard/references/sources.md); its parser never emits prompt
text and is not imported or relaxed here. The publication scanner is not reused as an inline
redactor: it audits files/history through a different contract and optional external tooling.

Only plain text blocks are accepted; images, tool-result blocks, unknown mixed content, slash
commands, skill expansions, system reminders, bash/IDE/hook/notification wrappers, interrupted-user
wrappers and protocol-v1 watch ticks are excluded. Any text block beginning with an XML-like wrapper
is conservatively excluded too; this can omit genuine markup-oriented requests. A child marker anywhere in a file vetoes all its candidates, including earlier rows.
Malformed JSON/duplicate keys veto the file; diagnostics contain counts, never raw lines or exception
messages. Unknown message shapes are skipped and reported. Parent/fork exclusion is deliberately
conservative and can also exclude genuine human continuation prompts.

## Redaction and privacy

The full accepted text is Unicode-normalized and control/format characters removed before pattern
matching. Credential-shaped text is replaced before whitespace normalization, deduplication or
output budgeting: PEM private keys (including an unfinished block), bearer/basic credentials,
URLs (including credential-bearing URLs), escaped or ordinary password/token/key/secret/cookie
assignments, long/short credential CLI flags, netrc passwords, common API-token prefixes, AWS access
keys, JWTs and long opaque strings. Email-shaped strings are also removed;
home-directory usernames are replaced with `~`. These are conservative heuristics, not a proof that
all secrets or personal/business information were removed. Some ordinary identifiers, URLs and
short CLI flags are over-redacted; redaction-operation counts are not proven secret counts.

Prompts above the raw-input limit are discarded whole, never shortened before redaction. Prompts
above the post-redaction length budget are also omitted whole. There is no partial raw-text prefix
that could retain half a credential. Short examples in the final report come only from the already
redacted packet. Never reread raw history to fill a redaction or recover a missing value.

Candidates deduplicate normalized **redacted** text, so prompts differing only in redacted values
may share a frequency. Pi event IDs are scoped to their session; Claude UUIDs deduplicate across
copied sessions. This assumes the runtime's UUID identity remains meaningful; rewrites without stable
IDs cannot be certified. Session and directory IDs use a non-persisted, undisclosed salt derived from
the bounded snapshot, so packet IDs cannot directly confirm guesses of working-directory names.
They remain metadata, not anonymity or authorization proof. Candidate IDs hash the already-redacted
text. Working-directory
counts are repository proxies, not verified Git identity; no Git commands are executed. Unknown
directories remain unknown. Dates/counts refer only to observed, accepted candidates.

## Bounds and stability

Defaults and hard scan bounds are local safeguards, not an OS sandbox or a universal privacy proof:

| Resource | Bound / behavior |
|---|---|
| Window | Last 30 days, configurable 1–365; timezone-aware UTC; lower inclusive, upper exclusive |
| Input length | At most 65,536 raw characters per prompt; oversized input omitted whole |
| Retained prompt | Default 8,000 redacted characters; configurable 80–32,000; omitted whole |
| Candidate output | Default 50 candidates / 65,536 serialized bytes; hard option ceilings 200 / 131,072 |
| Candidate pool | 2,000 unique redacted strings; equal new-string shares per source; further unretained occurrences reported |
| History scan | 20,000 directory entries / 2,000 newest JSONL files per source, 8 MiB per file, 1 MiB per line; 128 MiB raw bytes divided equally between sources |
| Records | 20,000 per file, 100,000 per source; incomplete files vetoed |
| Template input | 256 files, 64 KiB each; read as inert data; unusable definitions reported |
| Active data | Files modified within 60 seconds of the fixed `asOf` are skipped |
| Time | Cooperative 30-second total deadline with equal source time shares, checked at traversal/file/record boundaries; not a hard filesystem timeout |
| Cluster input | 8 KiB JSON array of ID groups on stdin; no unknown or duplicate membership |

Child directories are excluded before session-file caps are applied. Parent files are prioritized
newest-first; modification time is only a selection/active-file hint, never authority for the event
window. An old-mtime file with recent event timestamps is still eligible. Partial traversal or source
budgets remain explicit, and one source cannot consume the other's byte/time/pool share.

Transcript directories/files are opened with `O_NOFOLLOW` component by component, files must be
regular and their size/mtime must remain stable while read. Symlink and unreadable history roots
are unavailable, not empty. Explicit roots are user scope; never use history text to choose another
root. Current template installations commonly use symlinks, so template aliases may be resolved only to
Markdown targets as bounded read-only data; non-Markdown targets are rejected before opening.
Their contents are never emitted by the collector or executed.

The metadata summary includes source statuses, exclusions, malformed/unrecognized counts, omitted
counts, text bytes, exact serialized packet bytes (including the final newline), fixed `asOf` and a digest. The digest binds
bounded source bytes, selected candidates, known templates, redaction version and collection options.
The packet includes redacted text, occurrence counts, opaque session/directory sets and date spans.

`--emit` and `--clusters` require the summary's `--as-of` and `--expected-digest`, plus identical
original collection arguments. Any observed drift produces `stale-summary` with no prompt text.
No automatic retry or rolling window change is performed. This is a procedural disclosure binding,
not an attestation that a human reviewed the summary or approved a provider request.

`--clusters` accepts an array such as `[["p-id-a","p-id-b"],["p-id-c"]]` on stdin. It computes
occurrence sums and session/directory unions, ranks the supplied semantic groups, and reports
ungrouped candidates. It exposes no new text and cannot validate the model's semantic grouping.
There is no file-output mode; retention must be separately requested and scoped under ignored
`.artifacts/`. No templates, skills, config, provider requests or billing policies are written.
