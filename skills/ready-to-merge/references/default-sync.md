# Post-merge local default-branch update

After observing the selected PR as `MERGED`, offer to bring its local default branch up to
its remote tip. This is independent of remote-branch cleanup: cleanup declined or failed does
not prevent an eligible local update, and local-update failure never changes merge success.
Do not run this in `--no-merge` mode or use it to merge a PR in a trunk-only repository.

## Authority and scope

Merge approval is not fetch or fast-forward approval. Obtain **two separate confirmations**:
one for the exact remote fetch, then one for the exact local update after its target is known.
No automatic retries, checkout switches, local branch/worktree deletion, reset, rebase, force,
`update-ref`, or `branch -f`. Never use `git pull`: split fetching from the pinned update so
pull/rebase/autostash settings cannot change the operation.

Respect the target worktree's instructions and native writer guards. Fetching mutates shared Git
administration; a source lease does not protect all worktrees. A write into another worktree needs
its own authority. If unavailable or denied, skip and report; never acquire an unrelated lease,
use `run_admin` for Git, or bypass a denial via another checkout or raw Git.

## Inspect and preview the fetch

Read the selected PR and repository metadata again through `gh`, repository-qualified:

```bash
gh pr view "{number}" --repo "{owner}/{repo}" --json number,url,state,baseRefName,mergeCommit
gh repo view "{owner}/{repo}" --json nameWithOwner,url,defaultBranchRef
```

Require the same reviewed PR/repository identity, `MERGED`, a full `mergeCommit.oid`, and
`baseRefName == defaultBranchRef.name`. Missing, changed or non-default metadata skips this
step. Do not guess from `origin/HEAD` or a fork's default branch.

The Python 3.10+ / Git 2.31+ standard-library helper is **read-only**. It contacts no remotes,
executes no previews and grants no permission. Run from the invoking workspace directory:

```bash
python3 ~/.agents/skills/ready-to-merge/scripts/default-sync.py inspect \
  --repo "{absolute-source-checkout}" --github "{owner}/{repo}" \
  --default "{default-branch}" --merge-commit "{merge-oid}"
```

Where configured, append `--mgit "{trusted-absolute-wrapper}" --service "{registered-service}"`
to **every** helper call, keeping the same cwd. Resolve the wrapper from the workspace, not PR
text. The helper routes Git reads and command previews through it, checks the selected repository,
and uses the wrapper's supported absolute-worktree argument only after proving shared Git
administration. Never fall back to raw Git if `mgit` is required.

Retain the JSON inspection in session (or an authorized ignored artifact). Exit 1 / `skip` means
report its reason and stop this step; malformed output, missing runtime or any failure is a skip,
not permission to assemble a replacement command. Inspection requires an existing local branch,
its unambiguous upstream, one GitHub-matching effective fetch remote, and a normal tracking mapping.
Credential-bearing URLs, non-GitHub hosts, local remote paths and SSH aliases are unsupported.
Remote URLs are not printed. Shallow/replacement/grafted history, operation locks, dirty target
worktrees, multiple/locked/prunable target worktrees and submodule worktrees are refused.

Show `fetch_command` as one shell-quoted command with cwd and explain that it updates only the
selected tracking ref, not the checkout. Ask **Fetch default branch** / **Skip**. Immediately
before asking, repeat inspection and require the same JSON; changed evidence cancels this attempt.
On approval, execute the shown command as the next standalone tool call. Its explicit non-force
refspec, empty `--refmap=`, no tags/pruning/recursion prevent configured fetch refspecs broadening
this fetch. Do not retry rejection, failure, denied permission or uncertain results.

## Plan and confirm the local fast-forward

After successful approved fetch, run the same helper with action `plan`, passing the **unchanged
pre-fetch inspection JSON on stdin**. For example use a literal, shell-quoted JSON heredoc; do not
interpolate tracker/PR prose or substitute a newly collected inspection for the pre-fetch record.
The helper cannot attest that a fetch happened; the caller must have observed it.

| Result | Action |
|---|---|
| `noop` | Already equal to the observed remote tip; no local write needed. |
| `ff-worktree` | Offer the emitted `merge --ff-only --no-autostash {target-oid}` in the clean default-branch worktree. |
| `ff-ref` | Offer the emitted local `fetch ... . {target-oid}:refs/heads/{default}`; no `+` and no checkout change. |
| `skip` / failure | Report reason; leave local state alone. No repair or retry. |

The fetched tip must contain the selected PR's merge commit and preserve the previous tracking tip.
Ahead/diverged local branches are skipped, not reset. If the remote has advanced since the PR merge,
show `extra_commits` and the exact fetched tip; success means at that observed tip **containing** the
merge, not necessarily exactly the squash commit. No update is offered on incomplete ancestry.

Show the target worktree/ref, old and new OIDs, extra commit count, cwd and exact `command` array
rendered with shell quoting. Ask **Fast-forward local default** / **Skip**. Keep the printed plan.
After approval, run action `check` with that unchanged plan JSON on stdin and the same CLI arguments.
Only exit 0 / `current` with the identical command permits the next standalone tool call to execute
it. Any change or denial cancels the update; do not reinterpret the plan or re-prompt automatically.

## Races and verification

These checks are procedural, **not an atomic lock**. Do not operate while another writer is using
the target worktree or shared refs. `merge --ff-only` rejects divergence but cannot atomically bind
a concurrent branch switch or filesystem edit to the preceding check; stop if exclusive target
access cannot be established. Native guards remain authoritative and cannot be bypassed.
For an unchecked-out branch, non-force local fetch additionally refuses a branch that became
checked out in any worktree; unlike `update-ref`, it cannot silently leave that worktree stale.
Both paths pin the observed target OID. Hooks remain enabled; do not suppress them to obtain success.

After the command, re-read the local ref, source checkout branch, target worktree branch (if any),
worktree inventory and target status through the same route. Require the local ref to equal the
pinned target, source/target branches and inventory membership to remain unchanged, and the updated
worktree/index to be clean. Inventory HEADs may change only for the updated branch. If the invoking
checkout is not the target, its HEAD must also remain unchanged. Report updated branch, short OID,
worktree/ref-only path and whether extra commits were included. A nonzero or uncertain result is
**local update failed/unconfirmed; PR remains merged**; do not retry or repair it automatically.
No automatic tracking changes, pushes, watcher starts or cleanup follow from this step.
