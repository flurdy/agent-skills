# Attended local Dolt recovery

`/next recover <repository>` is a skill workflow, not an executable collector flag.
Use the exact repository name from an unavailable-store notice (`local` outside a
workspace). It requests an eligibility check and confirmation, **not permission to
start a server**. A user may also explicitly accept the recovery offer after a failed
list or resolution. Recover one named store; never batch-start workspace stores.

## Why not auto-start on read?

In bd 1.3.1, strict `--readonly` disables both server auto-start and maintenance.
Dropping it enables more than startup. A disposable server-mode characterization
confirmed that a stopped server fails a strict read both without a port file and
with a stale port file; an ordinary read auto-starts, and an explicit start permits
an unchanged strict read. This does not establish every future bd version's behavior.

`bd dolt start` is not a side-effect-free start-only primitive: it may clean up
orphan processes, initialise missing storage or identity, and reclaim a port.
The installed CLI has no no-kill/no-init switch. Therefore **never remove
`--readonly`**, hide a start inside `collect.load_issues`, or advertise a no-kill
promise for this command. Shared/external lifecycle ownership still rules it out.

Source contracts: bd 1.3.1's
[`effectiveRootStorePolicy`](https://github.com/steveyegge/beads/blob/v1.3.1/cmd/bd/main.go),
[`dolt start`](https://github.com/steveyegge/beads/blob/v1.3.1/cmd/bd/dolt.go), and
[`Start`](https://github.com/steveyegge/beads/blob/v1.3.1/internal/doltserver/doltserver.go).
Check installed `bd --version` and `bd dolt start --help`; incompatible or unknown
semantics stop recovery, not justify another command or stripped flags.

## 1. Establish the exact target, read-only

Run `~/.agents/skills/next/scripts/next-select stores` from the original listing cwd.
Match the requested owner to one usable store row and canonical directory. This
filesystem/topology check works while the database is stopped; it is not proof of
server eligibility. Never choose by a bead prefix, a partial path or stderr prose.
Workspace-owned members must resolve to the workspace owner, not another server.
If topology is unavailable, ambiguous, redirected or changes, stop without starting.

Retain the failed invocation's cwd, mode and qualified selector (if any). Require a
fresh strict read failure containing **both** `Dolt server unreachable` and
`connection refused` at a numeric loopback endpoint. Use the original collector or
resolver to reproduce it, keeping `--readonly` on database reads. A successful read
needs no recovery. Timeout, authentication, schema, corruption, malformed output and
other failures do not qualify. An unreachable diagnostic alone never proves a local
server should be started.

## 2. Check ownership and effective configuration

Inspect configuration read-only, never print credentials or whole unfiltered
configuration payloads. Check the installed CLI's config-report support; an optional
`bd -C <directory> config show --json --readonly` must be consumed privately and
filtered to lifecycle keys. It is not sole proof: metadata, selectors, environment
and runtime-generated port state have separate precedence. If a complete effective
view cannot be established without connecting to the failed server, stop.

Require all of the following; **unknown means ineligible**:

- A canonical Git root with its own regular, non-symlink `.beads` directory and
  readable `metadata.json`: Dolt backend, explicit `dolt_mode: server`, existing
  repo-local `.beads/dolt` storage. No missing storage, custom/external data directory,
  linked store, worktree indirection or `.beads/redirect`.
- No shared-server, proxied-server, team-server or externally managed route. No
  explicitly pinned host, port, socket, TLS endpoint or server configuration, even
  if it points to localhost. A generated `dolt-server.port` is bookkeeping, not a
  pinned endpoint and not proof of ownership.
- Auto-start is not disabled, and no operator readonly/sandbox policy forbids
  lifecycle changes. Inspect both `BEADS_DOLT_AUTO_START` and effective
  `dolt.auto-start`, including `BD_*` mappings; false/0/off or an unrecognised value
  refuses the offer. Never override a disable setting to make recovery eligible.
- No unresolved selector or route overrides: include `BEADS_DIR`, `BEADS_DB`, `BD_DB`,
  `BEADS_DOLT_*`, `BEADS_PROXIED_SERVER_*`, `BD_*`, and `.beads/.env`. Read names and
  relevant non-secret policy values only. Also account for project `config.yaml`,
  `config.local.yaml`, global/user configuration and explicit Dolt server YAML.
  Do not use a home-grown partial YAML parser or interpret absent local keys as
  absence of global overrides. Ambiguous precedence refuses recovery.

Do not initialise, migrate, repair, stop, restart or kill any server yourself. Do
not follow repair commands printed by bd. These checks reduce accidental targeting;
they cannot turn bd's lifecycle routine into an atomic start-only operation.

## 3. Fresh confirmation and one visible command

Immediately before confirmation, recheck the target and eligibility evidence. Show
its canonical directory and this exact shell-quoted command (not a command chain):

```text
bd -C <directory> --sandbox dolt start
```

Disclose: this starts a background local process and writes runtime state; bd may
also clean up orphan processes, reclaim a port or initialise storage/identity.
`--sandbox` disables Dolt auto-push, **not** those lifecycle effects. No remote sync,
publication, migration or repair is requested. Starting does not claim a bead or
acquire a source lease. Obtain fresh explicit approval for this one command.

Declined, abandoned or unclear confirmation means **no start and no retry**.
A changed target/configuration invalidates confirmation. Session guards remain
binding: if blocked, stop; never use another tool, subprocess wrapper, disabled
protection or alternate checkout to bypass it.

Execute the exact approved command as a standalone visible tool call, at most once
for this store in this recovery invocation, with a 60-second timeout. Do not hide it
in the collector, codemode batch, `&&` chain or test command. Report a nonzero exit,
timeout or unknown outcome and stop: **never retry a failed start** or claim it did
nothing (a background child may already exist). Do not stop it as automatic cleanup.

## 4. One strict retry, then stop

Only after exit zero, report `start command succeeded; read still unverified`, then
rerun the original read-only invocation once, with the same cwd/options/qualified
selector. This is a new collection with ordinary deadlines, not a retry loop. Show
its complete output and preserve machine diagnostics; report start/retry status
separately, never inject prose into JSON stdout. A successful start alone is not a
healthy-store result. A failed read remains unavailable, even after a successful start.

For `next_safe`, use the native list/recheck tool again, not a replacement observer.
Reproduce list Markdown verbatim. Recheck eligibility, occupancy and tracker-overlap
rules are unchanged. Do not restart `next-select start`, mark work in progress, or
claim write authority as part of recovery. Successful recovery returns to the picker;
a selected-bead workflow needs fresh ownership/handoff and (for safe work) recheck
before a separately requested claim. A successful read is not permission to select
the next bead automatically.

A standalone `/next recover <repository>` without an earlier failed invocation uses
`next-bd --list` once after a successful start. No other store is started if that
retry reveals another failure. Store startup notices are operational evidence, not
Beads mutations; no issue needs to be created merely for a normal recovery.
