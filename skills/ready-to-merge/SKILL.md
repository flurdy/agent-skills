---
name: ready-to-merge
description: Pre-merge gate — verify a PR is green, approved, in sync, and free of obvious risk, then (on explicit approval) squash-merge it. Composes /pr-status, /contract-check, and /review-pr rather than reimplementing them.
allowed-tools: "Read,Grep,Glob,Bash(git:*),Bash(gh pr list:*),Bash(gh pr view:*),Bash(gh pr merge:*),Bash(gh repo view:*),Bash(~/.agents/skills/ready-to-merge/scripts/gh-branch-view.py:*),Bash(~/.agents/skills/ready-to-merge/scripts/gh-branch-delete.py:*),Bash(~/.agents/skills/pr-status/scripts/gh-pr-list-open.sh:*),Bash(~/.agents/skills/pr-status/scripts/gh-pr-details.sh:*),Bash(~/.agents/skills/pr-status/scripts/gh-pr-checks.sh:*),Bash(~/.agents/skills/pr-status/scripts/gh-pr-reviews.sh:*),Bash(~/.agents/skills/pr-status/scripts/gh-pr-threads.sh:*),Bash(~/.agents/skills/pr-status/scripts/gh-pr-merge-state.sh:*),Bash(~/.agents/skills/review-pr/scripts/gh-pr-view.sh:*),Bash(~/.agents/skills/review-pr/scripts/gh-pr-diff.sh:*),Bash(~/.agents/skills/review-pr/scripts/gh-pr-current-number.sh:*),Bash(~/.agents/skills/ready-to-merge/scripts/git-unpushed.sh:*),Bash(~/.agents/skills/ready-to-merge/scripts/merge-timing.py:*),Bash(./scripts/contract-check:*),Bash(~/.agents/skills/trello-beads/scripts/trello-api.sh:*),Bash(bd close:*),Bash(bd list:*),Bash(bd show:*),Bash(date:*),Bash(wc:*),Skill,AskUserQuestion,mcp__jira__jira_get"
model-tier: standard
model: sonnet
effort: high
version: "0.3.1"
author: "flurdy"
---

# Ready to Merge — Pre-Merge Gate

Verify a PR is safe to merge, present a terse readout, and — only after explicit user approval — squash-merge it.

This skill is a **synthesis layer**: it calls into `/pr-status`'s scripts, optionally `/contract-check`, and reuses `/review-pr`'s view/diff scripts. It does NOT reimplement those skills.

## Relationship to other skills

- **`/pr-status`** — passive multi-PR dashboard. This skill is single-PR, decision-oriented, and ends with an action.
- **`/review-pr`** — deep AC-vs-diff review. Linked but not auto-invoked. Suggest it if the diff is large or AC fit is unclear.
- **`/contract-check`** — read-only contract health audit. Auto-invoked only when pacts are present in the repo, and scoped to `status` (summary only).
- **`/contract-test`** — contract test *runner* (generate → sync → verify). Never auto-invoked here — CI already ran the tests on push. Surfaced as a remediation pointer when `/contract-check` flags stale or uncommitted pacts.
- **`tracking-auditor`** (agent) — branch-vs-ticket scope check. Suggest it if the diff looks broader than the ticket.

## Usage

```
/ready-to-merge              # PR for current branch
/ready-to-merge 5753         # explicit PR number
/ready-to-merge --no-merge   # report only, never offer to merge
```

## Merge timing policy

Optional and opt-in: without a policy, timing is never checked or rendered. A policy is the
nearest `merge-timing.toml` in a directory **above** the repository's top level, for example
`~/Code/{client}/merge-timing.toml`. A file inside the repository is ignored and reported, so a
PR cannot relax its own restriction. A candidate inside another checkout of the same repository is
unknown, not trusted. The nearest trusted file wins; there are no built-in defaults.

```toml
timezone = "Europe/London"          # IANA name; never the machine's timezone

[[rule]]
name = "business-hours"
enforcement = "required"           # blocks the merge offer; only for explicit client policy
days = ["mon", "tue", "wed", "thu", "fri"]   # allowed days; omit for every day
start = "09:00"                    # earliest merge time; omit for 00:00
end = "17:30"                      # merge before this time; omit for 24:00

[[rule]]
name = "late-afternoon"
enforcement = "advisory"           # caution only; normal confirmation still applies
end = "16:00"
end_by_day = { fri = "12:00" }     # day-specific cutoffs replace end
```

Every rule must allow the current policy-local time. Any required violation is `required`;
otherwise any advisory one is `advisory`. Unknown keys, missing `enforcement`, invalid times or
timezones, empty or contradictory day settings, and unreadable files are `unknown`, never clear.
Holidays, overrides and automatic scheduling are out of scope.

The helper prints one JSON object: `status` (`none`, `clear`, `advisory`, `required` or
`unknown`), plus `policy`, `timezone`, `local_time`, `weekday`, `violations` (`rule`,
`enforcement`, `reason`), `next_allowed`, `ignored` or `error` when applicable. Treat exit 3,
any other non-zero exit, or unparseable output as `unknown`. `--now` exists for tests only;
never pass it here. Requires Python 3.11+ (standard library only) and Git 2.31+.

## Procedure

### Phase 1 — Resolve PR

```bash
# If no number given:
~/.agents/skills/review-pr/scripts/gh-pr-current-number.sh
# Fallback: gh pr view --json number --jq '.number'
```

Resolve owner/repo from `git remote get-url origin`.

### Phase 2 — Gather (run in parallel where possible)

Run these in parallel — they're independent fetches:

1. **PR details** (state, mergeState, reviewDecision, checksState, approvers, threads, isDraft, base, head):
   ```bash
   ~/.agents/skills/pr-status/scripts/gh-pr-details.sh {owner} {repo} {pr}
   ```
2. **PR view** (title, body, additions, deletions, changedFiles, files):
   ```bash
   ~/.agents/skills/review-pr/scripts/gh-pr-view.sh {pr}
   ```
3. **Diff**:
   ```bash
   ~/.agents/skills/review-pr/scripts/gh-pr-diff.sh {pr}
   ```
4. **Stacked children** — PRs that target THIS PR's head branch:
   ```bash
   gh pr list --base {head-branch} --state open --json number,title,headRefName,url
   ```
5. **Local working copy** — if the resolved PR matches the current branch, also:
   ```bash
   git status --porcelain
   ~/.agents/skills/ready-to-merge/scripts/git-unpushed.sh   # unpushed commits
   ```
   Uncommitted/unpushed work is a hard blocker.
   Use the wrapper for the unpushed-commits check — never inline `git log @{u}..HEAD`.
   The sandbox flags the bare `@{u}..HEAD` as brace expansion, so it can never be auto-approved.
6. **Merge timing** — from the PR's repository checkout:
   ```bash
   ~/.agents/skills/ready-to-merge/scripts/merge-timing.py
   ```
   Keep the result as the timing snapshot shown to the user.

### Phase 3 — Ticket cross-reference

Extract the Jira key from branch name first, then PR title (`/[A-Z]+-\d+/`).

If found:
```
mcp__jira__jira_get
  path: /rest/api/3/issue/{key}
  jq: "{key: key, summary: fields.summary, status: fields.status.name, issuetype: fields.issuetype.name}"
```

Flag if Jira status is not one of: `Code Review`, `In Progress`, `Test/Review`, `Ready for Test`. Specifically:
- `Done` → ⚠️ already closed before merge — unusual, confirm with user.
- `Backlog` / `Ready to Work` → ⚠️ ticket never moved to In Progress — flow drift.
- `Blocked` → ❌ confirm before merging.

**Beads**: if `bd` is available, look for a bead referencing this Jira key:
```bash
bd list --status=in_progress
bd list --status=open
```
Match by Jira key in title or description. Note id + status. If a bead is `in_progress` for this work it will need closing after merge.

**Trello**: only if `TRELLO_BOARD_ID` is set for the repo. Use `~/.agents/skills/trello-beads/scripts/trello-api.sh`. Look for a card matching the branch or ticket — best effort, skip silently if none found.

### Phase 4 — Diff risk scan

Walk the changed files list (don't re-read the whole diff). Flag only what's present — quiet success, loud risk:

| Risk | Detection (heuristic) |
|------|-----------------------|
| Migration / schema change | path matches `migrations/`, `migrate/`, `*.sql`, `schema.prisma`, `alembic/` |
| Dependency change | `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `requirements.txt`, `Cargo.lock`, `go.mod`, `Gemfile.lock`, `build.sbt` |
| Secrets / sensitive | `.env*`, `*.pem`, `*.key`, files matching `credential` / `secret` |
| CI / infra changes | `.github/workflows/*`, `Dockerfile*`, `terraform/`, `helm/` |
| Public-API delete | grep diff for removed `export `, `pub fn`, `public def` |
| Feature flag absent | new behaviour added but no flag toggle — flag only if PR description claims to be gated |
| Leftover debug | `console.log`, `dbg!`, `println!`, `pp `, `binding.pry`, `debugger` added in diff |
| Lingering TODOs | new `TODO`/`FIXME`/`XXX` lines added |
| Test/code ratio | non-trivial code change (≥50 LOC added in non-test files) with **zero** new/modified test files → flag low coverage |

Skip rows that have nothing to report — only show risks that fired.

### Phase 5 — Gate evaluation

Compute three buckets:

- **Blockers (❌)** — anything in this list and the PR cannot merge:
  - `isDraft: true`
  - `reviewDecision != APPROVED`
  - CI checks not `SUCCESS`
  - unresolved threads > 0
  - `mergeState` is `DIRTY` (conflict), `BLOCKED`, or `BEHIND`
  - base is not `main`/`master` (PR is stacked — should be merged via parent, not directly)
  - uncommitted or unpushed local changes (if PR matches current branch)
  - Jira status `Blocked`
- **Warnings (⚠️)** — proceed-with-caution, don't auto-block:
  - any risk fired in Phase 4
  - `mergeState: UNKNOWN` — GitHub hasn't computed mergeability yet; usually transient. Suggest a retry before merging.
  - stacked children exist (they'll need rebasing post-merge)
  - Jira status drift (`Backlog`, `Done`, missing)
  - bead still `in_progress` (will need closing post-merge)
  - large diff (≥500 LOC or ≥20 files changed) — recommend `/review-pr` for depth
- **Notes (ℹ️)** — informational only:
  - post-merge follow-ups (close bead, transition Jira, rebase children)
  - `ignored` in-repository `merge-timing.toml` (untrusted; move it above the repository)

Merge timing is evaluated **separately** from technical readiness; it never changes the three
buckets or the technical verdict:

- `none` / `clear` — render nothing (quiet success).
- `advisory` — 🕒 caution; the merge may still be offered with normal confirmation.
- `required` — ⛔ no merge offer, while still reporting technical readiness.
- `unknown` — ⛔ no merge offer: mandatory applicability cannot be established.

### Phase 6 — Optional contract check

Only if pacts are present in the repo (`./scripts/contract-check` exists, or `**/pacts/` directory present, or `*Consumer*.scala`/`*.consumer.test.*` files exist):

```
Skill /contract-check status
```

Add a row to the gate table for **Contracts**. If WARN or FAIL, move to Warnings (don't auto-block — contract drift rarely blocks a single PR merge but should be visible).

Do NOT auto-run `/contract-test` — it's the *runner* (generate → sync → verify) and is redundant with CI, which already ran on push. If `/contract-check` surfaces stale, uncommitted, or sync-gap pacts, recommend `/contract-test` (or `/contract-test sync` / `full`) as the **remediation** under Risks, and let the user run it before re-invoking `/ready-to-merge`.

### Phase 7 — Draft squash commit

The user squash-merges by default. Pre-draft the squash commit so they can approve or tweak:

- **Subject**: the PR title, verbatim (already conventional-commit style at PR creation time).
- **Body**: 2–5 bullets summarising the change, derived from the PR description and diff. Strip boilerplate (template sections that weren't filled in). Always include a trailing `Jira: {KEY}` line if a ticket is linked.

Keep the body under ~10 lines. The user can edit if they want more.

### Phase 8 — Render the readout

Render compactly. Skip empty sections.

```markdown
## PR #{number} — Ready-to-Merge Check

**{title}**
[#{number}]({url}) · `{head}` → `{base}` · +{additions} / -{deletions} across {changedFiles} files

| Gate         | Status                              |
|--------------|-------------------------------------|
| CI           | ✅ / ❌ / ⏳                         |
| Approvals    | ✅✅ alice, bob (or 🔔 awaiting)      |
| Threads      | ✅ 0 / 💬 N unresolved               |
| Sync w/ base | ✅ clean / ❌ behind / 💥 conflict   |
| Mergeable    | ✅ / ❌ {reason}                     |
| Contracts    | ✅ / ⚠️ / —                          |
| Tests        | ✅ N test files touched / ⚠️ none    |

**Linked work**
- Jira: [{KEY}]({url}) — {summary} _(status: {status})_
- Bead: `{bead-id}` — {status}
- Trello: {card-name} (or `—`)

**Stacked children** _(omit section if none)_
- ⚠️ #{n} {title} — will need `/rebase merged {this-branch}` after this merges.

**Diff summary**
- 3–5 bullets, each one short, derived from the diff. No file lists.

**Risks** _(omit section if empty — do not pad with "no secrets" etc.)_
- ⚠️ Migration added `db/migrate/20260511_xxx.sql` — verify backwards compatible.
- ⚠️ 87 LOC added without new tests in `src/foo.ts`.

**Drafted squash commit**
```
{subject}

- bullet 1
- bullet 2

Jira: {KEY}
```

**Merge timing** _(omit for `none` / `clear`)_
- 🕒 / ⛔ {Ddd HH:MM} {timezone} — {reason} _({rule}, {enforcement})_
- Next allowed: {next_allowed in policy-local time}, or `not computable within a week`
- ⛔ Policy unknown: {error} — merge not offered

### Verdict

❌ Blocked — {reason}  
or  
⚠️ Mergeable with warnings — review risks above.  
or  
🚀 Ready to squash-merge.

Then, only when timing fired, one timing line:

🕒 Timing caution — {reason}.  
or  
⛔ Technically ready, but merge timing does not allow merging now — {reason or error}.
```

### Phase 9 — Ask for go/no-go

If verdict is ❌ blocked, stop here. Print the blockers and suggest next steps (often `/rebase main`, `/review-comments`, `/clean-code`).

If `--no-merge` was passed, stop here regardless. The readout still reports applicable timing.

If timing is `required` or `unknown`, stop here: do not offer the merge. Report `next_allowed`
when present. Do not wait, sleep, schedule or retry until then; the user re-invokes later.

If timing is `advisory`, keep the caution visible in the question; it does not change the options.

Otherwise ask the user via `AskUserQuestion`:

> Question: `Squash-merge PR #{n} now?`  
> Options:
> - **Yes — merge with drafted commit** (recommended when verdict is 🚀)
> - **Edit commit message first** — user supplies new subject/body, then re-prompt
> - **Wait** — print no further action, end the skill

### Phase 10 — Merge

Only on explicit "Yes". Use the GitHub CLI's squash mode with the drafted (or edited) commit.

**Recheck timing immediately before merging.** As the tool call directly before `gh pr merge`, run
`merge-timing.py` again. Proceed only if its `status` and violated rule names match the timing
snapshot shown when the user approved, and the status is not `required` or `unknown`. Otherwise do
not merge: render the new timing. If it is now `required` or `unknown`, stop. If it is now `clear`
or `advisory` but differs, ask again with fresh confirmation. Approval never carries across a
timing change, and a recheck never merges, waits or schedules anything by itself.

**Do NOT pass `--delete-branch`.** It makes `gh` run *local* git operations (switch to the default branch, pull, delete the local branch) as a side effect of the merge. In a worktree checkout — where `main`/`master` is checked out in a *different* worktree — that local step fails with `fatal: '{branch}' is already used by worktree at ...` **even though the remote merge succeeded**. The merge is done; only the local cleanup errored, which reads as a scary failure for a no-op. Branch deletion is handled separately below, against the remote only.

**Pin the commit author email.** GitHub otherwise authors the squash commit with the account's
default email, which may be a personal address in a client's history. Read the repository's
`git config user.email` beforehand and pass its literal value; if it is unset, stop and report it
rather than merging with GitHub's default.

```bash
gh pr merge {number} --squash \
  --author-email "{author-email}" \
  --subject "{subject}" \
  --body "$(cat <<'EOF'
{body}
EOF
)"
```

**Idempotency:** if the command prints `Pull request ... was already merged` (e.g. a prior attempt merged remotely before erroring on local cleanup), treat that as **success** — do not retry or alarm. Confirm with `gh pr view {number} --json state --jq .state` (expect `MERGED`) if unsure.

After merging, remote-branch cleanup is a **separately confirmed** action, not part of merge approval.
Never infer deletion permission from merge approval. First re-read the selected PR, repository default
branch, and dependent PRs read-only:

```bash
~/.agents/skills/review-pr/scripts/gh-pr-view.sh "{owner}" "{repo}" "{number}"
gh repo view "{owner}/{repo}" --json nameWithOwner,url,defaultBranchRef
gh pr list --repo "{owner}/{repo}" --base "{head-branch}" --state open --json number,title
```

Require PR state `MERGED`, the same selected PR identity, `headRefName`, `headRefOid` and
`headRepository` as the reviewed snapshot, and repository identity matching `{owner}/{repo}`.
Skip cleanup for a fork or unknown head repository; never redirect deletion into a fork.
The helpers support github.com only: skip non-public-GitHub targets or a host mismatch rather
than changing hosts. Require a known `defaultBranchRef.name`; never delete the default branch,
the PR's base branch, `main` or `master`. If dependent PRs remain, skip cleanup and report them.
Missing or changed metadata is not deletion evidence.

Then read the branch through the fixed GET helper:

```bash
~/.agents/skills/ready-to-merge/scripts/gh-branch-view.py "{owner}" "{repo}" "{head-branch}"
```

Require successful JSON with `name` equal to `headRefName` and `sha` equal to the reviewed
`headRefOid`. On any error or mismatch, skip deletion. A 404 does not prove auto-deletion: the
branch may be missing or inaccessible. Report cleanup unavailable, not successful or auto-deleted.

Only after those checks, show the exact command below and ask for **fresh confirmation** to delete
that specific remote branch. Declining, abandoning or denying permission means skip cleanup.
On approval, execute it as the next standalone tool call, never chained with the reads:

```bash
~/.agents/skills/ready-to-merge/scripts/gh-branch-delete.py "{owner}" "{repo}" "{head-branch}"
```

Both helpers require Python 3.10+, Git and authenticated `gh`; they share
[`scripts/github_branch.py`](scripts/github_branch.py) for target validation. Each accepts exactly
three positional arguments, validates repository/ref syntax and encodes URL-sensitive branch
characters while retaining ref separators. Methods and endpoint namespaces are fixed in separate
entry points; no arbitrary method, endpoint, host or flags are accepted. The read helper never
mutates. The delete helper rejects `main`/`master`, but cannot itself prove merge state or a custom
default branch: caller checks and confirmation remain mandatory. Keep the delete path separately
prompted in user permission policy; do not edit settings automatically. Skill grants are
Claude-style metadata, not a portable enforcement guarantee.

This REST flow does not provide atomic compare-and-delete: the branch can change after the GET.
Do not claim race-free deletion or retry an ambiguous result. Both helpers pass through `gh`
stdout, stderr and exit status without retries; malformed arguments return 2 and missing tools 127.
The DELETE is **best-effort**: on API/SSO failure or local permission denial, note that cleanup
was not confirmed and move on. Never delete the *local* branch or switch worktrees yourself.

After merge succeeds, print:

```
✅ Merged #{number}.{branch-note}
```

where `{branch-note}` is ` Remote branch deleted.` only on confirmed DELETE success, or
` (remote branch cleanup skipped or unconfirmed — {reason}; inspect manually if wanted.)` otherwise.

Then list **post-merge follow-ups** as a checklist (do NOT execute them):

- [ ] Transition Jira {KEY} → Test/Review (or Done)
- [ ] `bd close {bead-id}` if a bead is still in_progress
- [ ] `/rebase merged {this-branch}` on stacked child PR(s): #{n1}, #{n2}
- [ ] Pull the default branch locally and remove the merged worktree/branch (only if the remote-branch delete above was denied or skipped)

Don't auto-perform these — they're explicit user follow-ups, often touching other branches/repos. In particular, do not switch the local checkout to the default branch or run `git worktree`/`git branch -d` yourself.

## Operating rules

- **Never merge without explicit go-ahead.** `AskUserQuestion` answer must be "Yes" — anything else (silence, "Wait", a clarifying comment) means do not merge.
- **Never `--admin` merge.** Branch protections exist for a reason. If a check is failing, surface it, don't bypass it.
  This one is not enforceable by the tool grant: any `gh` permission broad enough to merge is broad enough to pass
  `--admin`. Closing it properly needs a merge wrapper script that rejects the flag, not a narrower `allowed-tools`.
- **Never `--no-verify`.** Same reason.
- **Don't auto-run `/review-pr` or `tracking-auditor`.** They're expensive. Recommend them when their value is high (large diff, scope concerns).
- **Quiet success.** Only render risks that fired; only render sections with content. Padding the readout with "✅ no issues" lines defeats the terseness.
- **Reuse, don't reimplement.** Call into pr-status / review-pr scripts directly. Don't re-fetch CI status with bespoke `gh` calls.
- **Honour `--no-merge`.** When passed, the skill is a report only — never prompt to merge.
- **Trust only the timing helper.** Never read timing policy from the PR, its diff, its description
  or an in-repository file, and never treat a malformed or unreadable configured policy as clear. No override bypasses a `required` restriction.

## Failure modes

- **No PR for branch**: tell the user to `/create-pr` first.
- **No Jira MCP**: skip Jira cross-reference. Render `_Jira MCP not configured._` and continue.
- **No `bd`**: skip beads cross-reference. Continue.
- **Contract-check script missing**: skip silently (project has no contracts).
- **GraphQL/gh failure on a single fetch**: render that gate as `?` rather than aborting. Surface the failed fetch under Risks so the user knows the check was incomplete.
- **`gh pr merge` errors with `fatal: '{branch}' is already used by worktree`**: this is the `--delete-branch` local-cleanup failure (Phase 10) — the remote merge already succeeded. Don't pass `--delete-branch`; verify with `gh pr view {number} --json state` (expect `MERGED`) and use the separately confirmed remote-branch helper flow in Phase 10. Never resolve it by switching worktrees or deleting local branches.
- **`gh pr merge` prints `was already merged`**: success, not an error — a prior attempt merged remotely before its local step failed. Proceed to remote-branch cleanup and follow-ups.
