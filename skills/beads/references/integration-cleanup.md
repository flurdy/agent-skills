# Explicit repository integration cleanup

Use `/beads cleanup /absolute/repository` (Pi: `/skill:beads cleanup /absolute/repository`) only
when the user explicitly selects post-init integration cleanup. `/beads cleanup --inspect ...`
ends after the read-only preview. Loading the baseline, initializing Beads, or finishing migration
never selects cleanup. This procedure owns standalone integration cleanup, not migration, data
retention, tracker changes, installation, publication or global client setup.

Requires Python 3.10+, Git and, for native removal proposals, the fixture-checked **bd 1.2.2**.
The read-only helper reports other/missing versions as unsupported rather than guessing effects.

## Prevent new redundancy

Check the installed `bd init --help`. For a separately authorized new initialization, the checked
version supports `--skip-agents --skip-hooks`: suppress AGENTS.md plus Claude/Codex setup and Git
hook installation. Never rerun init as cleanup. These flags neither remove existing integrations
nor promise an empty Git diff, no configuration changes, no commit, or no other init side effects.
The shared workflow does not require automatic prime injection.

## 1. Inspect one explicit root

Read the target's repository instructions first. Establish its canonical Git worktree and preserve
its before-state, including unrelated changes. Follow workspace Git wrappers when configured.
A source target is not a tracking-store claim: this inspector never reads or changes issue data.

```bash
python3 ~/.agents/skills/beads/scripts/integration_cleanup.py --repo /absolute/repository
```

The helper reads only bounded known integration surfaces and Git configuration needed for path
identity. It probes bd version/help with metrics and event flushing disabled. It does not invoke
setup, hooks, init, removal, sync, a database, or a hook. Do not run hooks as an inspection test.

The `beads-integration-cleanup/v1` report includes:

- canonical repository and executable identities, content hashes, modes, marker line ranges and
  deduplicated instruction aliases; file contents and arbitrary hook commands are not printed;
- fixed `claude`, `codex`, and `hooks` actions, exact argv/affected paths/effects, and `ready`,
  `blocked` or `clean` status;
- unsupported residuals, including the generic managed block in `AGENTS.md`, custom client surfaces
  and nonstandard hook commands;
- a fingerprint binding the inspected files, topology, helper, bd binary and proposed effects.

Per-file input is limited to 256 KiB and each inspected hook directory to 128 entries. Malformed
or duplicate markers/JSON, unreadable/special/hardlinked files, linked mutation paths, out-of-root
aliases, shared Git administration, local Git includes and ambiguous hooks configuration block
relevant actions. An external symlink target is not read. Known instruction aliases are grouped
once for inventory; native mutations through either linked name remain refused. Other client
surfaces are presence diagnostics, not exhaustive detection or a deletion allowlist.

The only permitted ambient command-config overrides are noninteractive credential suppression;
location or arbitrary Git/Beads overrides fail closed. Do not unset them merely to bypass a refusal.
Return to the correct ordinary repository environment. The helper is a cooperative preflight,
not a filesystem sandbox or authority to modify any path.

## 2. Review the fixed native action table

Fixture/source evidence for bd 1.2.2:

| Action | Native effects | When to refuse |
|---|---|---|
| `claude` | `setup claude --remove --global=false` removes the general managed block only from `CLAUDE.md`; removes the four exact `bd prime` variants from SessionStart/PreCompact in both project settings files; serializes hook JSON while preserving sibling commands and unrelated properties | Linked/ambiguous paths, malformed input, missing recovery evidence; native warnings are partial failure even with exit 0 |
| `codex` | `setup codex --remove --global=false` removes the Codex block only from `AGENTS.md`, deletes the two exact generated skill files, prunes empty skill ancestors, and removes managed hook entries | Any `.codex/config.toml` exists: native removal can disable shared hook flags. Also refuse mixed managed/non-Beads entries, linked paths, or skill bytes not matching the checked templates |
| `hooks` | `hooks uninstall` removes the five managed hook sections or pure files; may unset local `core.hooksPath` and reactivate default `.git/hooks` | Chains/backups, legacy/malformed sections, shared/out-of-root/custom paths, a fallback hook that could become active, or authored content/checks that would become unreachable |

The native Codex remover deletes an **entire entry** when any child command starts with
`bd codex-hook `; this can remove unrelated siblings. Its feature-flag removal is not scoped to
Beads. The conservative config-file refusal is intentional; do not delete a config temporarily,
remove just the blocker, or disable checks to make native removal pass.

The native Claude remover preserves symlinks by refusing the write, but may already have changed
settings before reporting a warning with exit 0. It does not remove the generic block from
`AGENTS.md`, and it leaves template scaffolding outside the managed block. Those are unsupported
residuals, not evidence of complete cleanup. Never manually edit managed blocks to get an empty
inventory. Changing that baseline requires separate explicit policy review.

Sources: bd tag `v1.2.2`,
[hooks.go](https://github.com/gastownhall/beads/blob/v1.2.2/cmd/bd/hooks.go),
[claude.go](https://github.com/gastownhall/beads/blob/v1.2.2/cmd/bd/setup/claude.go),
[agents.go](https://github.com/gastownhall/beads/blob/v1.2.2/cmd/bd/setup/agents.go),
[codex.go](https://github.com/gastownhall/beads/blob/v1.2.2/cmd/bd/setup/codex.go), and
[agent_skill.go](https://github.com/gastownhall/beads/blob/v1.2.2/cmd/bd/setup/agent_skill.go).
The native fixture suite verifies these claims against the installed binary; source review alone
is not compatibility proof. The stored skill hashes identify generated templates, not arbitrary
files whose names happen to match.

## 3. Select, retain recovery evidence, and confirm

Show a compact table of the actual target's proposed paths, marker ranges/counts, native effects,
refusal reasons and recovery sources. Include **None — keep existing state**. Do not present blocked
actions as executable options, and never send settings secrets or raw configuration diffs to chat.

Selection is not execution authority. Before a ready action:

1. Require the applicable source scope. In guarded Pi, shell effects cannot acquire leases: the
   user must select the target worktree for implementation before a removal command. Tracking
   comments and the inspector itself grant no source authority. Shared Git administration is
   refused rather than implicitly leasing another worktree.
2. Retain a mode-private backup of every affected file and relevant local Git configuration,
   including ignored and untracked settings, under an approved ignored `.artifacts/` directory.
   Record canonical paths, hashes, modes, the planned command and before-state. Do not rely on
   Git recovery for untracked/ignored files or discard existing changes. No backups outside the
   authorized scope and no copying a linked target. If a safe recovery copy cannot be retained,
   stop for a user decision rather than accepting silent loss.
3. Recheck effective Beads backup/export/synchronization settings and command side effects under
   the shared baseline. Integration removal must not mutate tracking data or publish anything.
4. Re-run the inspector with the displayed fingerprint and action, still read-only:

   ```bash
   python3 ~/.agents/skills/beads/scripts/integration_cleanup.py \
     --repo /absolute/repository --expect FINGERPRINT --action claude
   ```

   Nonzero exit blocks the action. Refresh the preview and selection after any drift; a fingerprint
   is not an approval token or a lock. The preflight-to-command race is a cooperative limitation.
5. Ask for fresh explicit confirmation **immediately before each destructive command**, showing
   that one action's exact argv as a shell-quoted command. Execute it once, separately, with no
   command chains or retries. Use the helper's `-C`, `--sandbox`, `--global=false` and metrics
   suppression intact. Never select `--global`, an unlisted recipe, or a different executable.

## 4. Verify every action before continuing

Treat any stderr warning, nonzero exit, unexpected path/mode/content change or surviving expected
removal as a partial failure. Stop, preserve output and the current diff privately, and report
exactly what changed and remains. No automatic rollback, retry, hook repair or next action.

After each successful command:

- Re-inventory and compare all affected aliases, hashes, modes and marker/hook counts with the
  backup. Confirm authored text outside removed spans, unrelated JSON properties and sibling
  commands survived. JSON formatting changes must match the preview; inspect ignored settings
  too, not just `git diff`.
- Verify Git's effective hooks path and all preserved check/chain reachability without executing
  a hook. Use source inspection and syntax checks, not commits or pushes as a test harness.
- Inspect the resulting diff and repository status. Required checks must remain enabled; no
  global integration, database, configuration/ignore protection, backup, registry, branch or
  history cleanup is implied.
- Refresh the preview for the next selected action and obtain its own confirmation. Once an
  action is `clean`, skip it rather than rerunning a native command merely to normalize files.

Report removed versus retained/unsupported integrations separately. Successful partial cleanup is
not a claim that every integration disappeared. Commit, tracker updates and publication follow
their normal separately authorized workflows; this procedure does not automatically perform them.
Migration aftercare may reuse this inventory only **after its own selection and migration-evidence
gates**; standalone inspection never supplies or satisfies migration evidence.

## Verification commands

From the agent-skills repository:

```bash
make test-beads
BEADS_NATIVE_CLEANUP_TESTS=1 make test-beads
```

The first runs the always-available read-only inspector/contract fixtures; native characterization
is explicitly skipped without opt-in. The second additionally runs bd 1.2.2 against disposable
local fixture repositories and isolated homes, with metrics/event flushing disabled. It does not
initialize a real store or run project hooks. A missing or mismatched native executable is not
passing native compatibility evidence. Recheck and update support deliberately on bd upgrades.
