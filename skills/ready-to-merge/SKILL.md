---
name: ready-to-merge
description: Pre-merge gate — verify a PR is green, approved, in sync, and free of obvious risk, then (on explicit approval) squash-merge it. Composes /pr-status, /contract-check, and /review-pr rather than reimplementing them.
allowed-tools: "Read,Grep,Glob,Bash(git:*),Bash(gh:*),Bash(~/.claude/skills/pr-status/scripts/gh-pr-list-open.sh:*),Bash(~/.claude/skills/pr-status/scripts/gh-pr-details.sh:*),Bash(~/.claude/skills/pr-status/scripts/gh-pr-checks.sh:*),Bash(~/.claude/skills/pr-status/scripts/gh-pr-reviews.sh:*),Bash(~/.claude/skills/pr-status/scripts/gh-pr-threads.sh:*),Bash(~/.claude/skills/pr-status/scripts/gh-pr-merge-state.sh:*),Bash(~/.claude/skills/review-pr/scripts/gh-pr-view.sh:*),Bash(~/.claude/skills/review-pr/scripts/gh-pr-diff.sh:*),Bash(~/.claude/skills/review-pr/scripts/gh-pr-current-number.sh:*),Bash(./scripts/contract-check:*),Bash(./scripts/trello-api:*),Bash(bd:*),Bash(date:*),Bash(wc:*),Skill,AskUserQuestion,mcp__jira__*"
model: sonnet
effort: medium
version: "0.1.0"
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

## Procedure

### Phase 1 — Resolve PR

```bash
# If no number given:
~/.claude/skills/review-pr/scripts/gh-pr-current-number.sh
# Fallback: gh pr view --json number --jq '.number'
```

Resolve owner/repo from `git remote get-url origin`.

### Phase 2 — Gather (run in parallel where possible)

Run these in parallel — they're independent fetches:

1. **PR details** (state, mergeState, reviewDecision, checksState, approvers, threads, isDraft, base, head):
   ```bash
   ~/.claude/skills/pr-status/scripts/gh-pr-details.sh {owner} {repo} {pr}
   ```
2. **PR view** (title, body, additions, deletions, changedFiles, files):
   ```bash
   ~/.claude/skills/review-pr/scripts/gh-pr-view.sh {pr}
   ```
3. **Diff**:
   ```bash
   ~/.claude/skills/review-pr/scripts/gh-pr-diff.sh {pr}
   ```
4. **Stacked children** — PRs that target THIS PR's head branch:
   ```bash
   gh pr list --base {head-branch} --state open --json number,title,headRefName,url
   ```
5. **Local working copy** — if the resolved PR matches the current branch, also:
   ```bash
   git status --porcelain
   ~/.claude/skills/ready-to-merge/scripts/git-unpushed.sh   # unpushed commits
   ```
   Uncommitted/unpushed work is a hard blocker.
   Use the wrapper for the unpushed-commits check — never inline `git log @{u}..HEAD`.
   The sandbox flags the bare `@{u}..HEAD` as brace expansion, so it can never be auto-approved.

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

**Trello**: only if `./scripts/trello-api` exists in the repo. Look for a card matching the branch or ticket — best effort, skip silently if none found.

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
- ⚠️ #{n} {title} — will need `/rebase-merged-parent` after this merges.

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

### Verdict

❌ Blocked — {reason}  
or  
⚠️ Mergeable with warnings — review risks above.  
or  
🚀 Ready to squash-merge.
```

### Phase 9 — Ask for go/no-go

If verdict is ❌ blocked, stop here. Print the blockers and suggest next steps (often `/rebase-main`, `/review-comments`, `/clean-code`).

If `--no-merge` was passed, stop here regardless.

Otherwise ask the user via `AskUserQuestion`:

> Question: `Squash-merge PR #{n} now?`  
> Options:
> - **Yes — merge with drafted commit** (recommended when verdict is 🚀)
> - **Edit commit message first** — user supplies new subject/body, then re-prompt
> - **Wait** — print no further action, end the skill

### Phase 10 — Merge

Only on explicit "Yes". Use the GitHub CLI's squash mode with the drafted (or edited) commit:

```bash
gh pr merge {number} --squash \
  --subject "{subject}" \
  --body "$(cat <<'EOF'
{body}
EOF
)" \
  --delete-branch
```

After merge succeeds, print:

```
✅ Merged #{number}.
```

Then list **post-merge follow-ups** as a checklist (do NOT execute them):

- [ ] Transition Jira {KEY} → Test/Review (or Done)
- [ ] `bd close {bead-id}` if a bead is still in_progress
- [ ] `/rebase-merged-parent` on stacked child PR(s): #{n1}, #{n2}
- [ ] Pull main locally and delete the merged branch from any worktrees

Don't auto-perform these — they're explicit user follow-ups, often touching other branches/repos.

## Operating rules

- **Never merge without explicit go-ahead.** `AskUserQuestion` answer must be "Yes" — anything else (silence, "Wait", a clarifying comment) means do not merge.
- **Never `--admin` merge.** Branch protections exist for a reason. If a check is failing, surface it, don't bypass it.
- **Never `--no-verify`.** Same reason.
- **Don't auto-run `/review-pr` or `tracking-auditor`.** They're expensive. Recommend them when their value is high (large diff, scope concerns).
- **Quiet success.** Only render risks that fired; only render sections with content. Padding the readout with "✅ no issues" lines defeats the terseness.
- **Reuse, don't reimplement.** Call into pr-status / review-pr scripts directly. Don't re-fetch CI status with bespoke `gh` calls.
- **Honour `--no-merge`.** When passed, the skill is a report only — never prompt to merge.

## Failure modes

- **No PR for branch**: tell the user to `/create-pr` first.
- **No Jira MCP**: skip Jira cross-reference. Render `_Jira MCP not configured._` and continue.
- **No `bd`**: skip beads cross-reference. Continue.
- **Contract-check script missing**: skip silently (project has no contracts).
- **GraphQL/gh failure on a single fetch**: render that gate as `?` rather than aborting. Surface the failed fetch under Risks so the user knows the check was incomplete.
