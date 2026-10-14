---
name: complete-task
description: "Complete an in-progress task by running clean-code, staging, and committing. Close the bead on trunk, leave it open for PR creation, and protect detached commits. Use after /verify-task."
allowed-tools: "Read,Bash(~/.agents/skills/next/scripts/next-select:*),Bash(~/.agents/skills/complete-task/scripts/jira-review.py:*),Bash(bd -C * close:*),Bash(bd -C * list:*),Bash(bd -C * show:*),Bash(bd -C * update:*),Bash(bd -C * create:*),Bash(bd -C * defer:*),Bash(make:*),Bash(git:*),Bash(npm:*),Grep,Glob,Skill,AskUserQuestion"
model-tier: standard
model: sonnet
effort: high
version: "2.2.1"
author: "flurdy"
---

# Complete Task

Run clean-code, stage, and commit an in-progress task — the finalization phase of development.
Normally a fully verified bead closes on **trunk / direct-commit**, stays open for `/create-pr` in
**PR mode**, and stays open on **detached HEAD** until the commit is safely owned. Applicable project
policy wins. Future-event-only evidence uses the explicit deferred-verification choice in §6, not an
unqualified completion claim.

## When to Use

- Code changes are verified and ready to commit
- After `/verify-task` has passed (or verification is not needed), or returned the qualified
  deferred-verification tracking handoff
- Replacing manual Phase 3 (Commit and Close) steps

## Prerequisites

Run `/verify-task` before this skill to confirm requirements are met and test coverage is adequate.
If you haven't verified yet, do that first. Its **deferred-verification tracking handoff** is the
only incomplete-evidence exception: the verdict remains **Incomplete evidence**, and only the named
future-event check is outstanding. All other requirements and presently executable checks must pass
with unchanged scope. Any failed, stale, not-run check, missing local coverage or ordinary unavailable
evidence blocks this path; never relabel a failure as waiting for a rollout.

Consume the report's requirement rows, revision and pending-event packet; do not infer eligibility
from a clean tree or commit. This exception permits committing authorized implementation and the
confirmed tracking disposition in §6, not claiming full verification.

## Usage

```
/complete-task              # Auto-detect in-progress bead
/complete-task <bead-id>    # Complete a specific bead
```

## Instructions

### 1. Identify the Task

Determine which bead is being completed, then prove which store owns it before reading or
closing anything. Never infer the owning store from the bead ID or the current directory: at a
workspace root the cwd store is the workspace store, not the repository that owns the work.

```bash
# Without a selector, discover usable stores before listing candidates
~/.agents/skills/next/scripts/next-select stores
bd -C <directory> list --status=in_progress

# Resolve the chosen bead to its owning store (read-only)
~/.agents/skills/next/scripts/next-select resolve <bead-id>
```

If multiple beads are in progress, ask the user which one to complete.
If no beads are in progress, ask the user what to do.

Act on the resolver `status`:

| status | action |
|---|---|
| `resolved` | take `directory`; every later `bd` call in this skill uses `bd -C <directory>` |
| `ambiguous` | show `matches[].selector`, ask which `<repo>:<id>` is meant; close nothing |
| `unavailable` | report `failures`; commit as normal but leave the bead untouched and say why |
| `not-found` | ask the user for the right ID; never guess another store or create a bead |

Then read it in its owning store:

```bash
bd -C <directory> show <bead-id>
```

### 2. Run Clean Code

```bash
make clean-code
```

If clean-code fails:

- Fix auto-fixable issues
- Re-run to confirm zero warnings and zero errors
- If issues remain that change behavior, ask the user before fixing

### 3. Select new work or an existing verified commit

Inspect `git status --porcelain=v1 --untracked-files=all` first. Stop if the status command fails.
With task changes, HEAD may be unborn: stage and create the initial commit normally.

Only on the existing-commit path, require `git rev-parse HEAD` to succeed; stop if it does not.
If there is nothing to commit, do not create an empty commit. This includes a rerun after preserving
an earlier detached commit on a branch. Confirm that HEAD is the exact task commit, the working tree
is clean, and verification evidence applies to that commit; rerun `/verify-task` if evidence is
missing or HEAD changed (the qualified pending-event report is sufficient only for the exception
below). Show the SHA and ask **Finalize this verified commit** or **Stop**. Only after confirmation,
skip staging and committing and continue to §5. If HEAD or task identity is uncertain, leave the bead
open; an empty diff is not proof that the task is complete.

For an existing pending-event commit, show the SHA as **not fully verified** and use the single §6
choice instead of the ordinary existing-commit confirmation. Skip staging/committing, then classify
in §5; no tracking writes before that explicit choice. Before §6, ensure the report still describes
the committed contents and record the resulting SHA. Changed task content requires fresh verification.

#### Stage changes for a new commit

Stage only the files changed for this task:

```bash
git add <specific-files>
```

**Rules:**

- Never use `git add -A` or `git add .`
- Never stage root folders only (e.g., `git add src/`)
- Stage specific files or small subdirectories
- Exclude unrelated changes — if unrelated changes exist, leave them unstaged
- Exclude files that likely contain secrets (.env, credentials, etc.)

### 4. Commit

For staged task changes only, create a commit using conventional commit format:

```bash
git commit -m "$(cat <<'EOF'
<type>: <concise description>
EOF
)"
```

**Commit message rules:**

- Use conventional commit prefix: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `perf:`, `test:`
- Infer the type from the bead type (feature → `feat:`, bug → `fix:`, task → contextual)
- Keep the message concise (1-2 sentences) focused on the "why"
- Do not push to remote

### 5. Detect the Workflow Mode

Require either a successful new commit or an explicitly confirmed existing verified commit from §3,
or its existing pending-event commit awaiting §6 confirmation. Then classify the current checkout;
no path bypasses detached-HEAD protection. For attached checkouts, explicit project guidance takes
precedence over the branch/remote heuristics below; a heuristic is not a delivery-boundary declaration.
Never infer a PR workflow where project policy declares trunk delivery, or close before that policy's
required integration/merge has actually happened.

```bash
# Default branch (origin/HEAD, falling back to local main/master)
default_branch=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
if [ -z "$default_branch" ]; then
  for c in main master; do git show-ref --verify --quiet "refs/heads/$c" && default_branch=$c && break; done
fi
current_branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)
head_sha=$(git rev-parse HEAD)
git remote   # empty output = no remote
```

Classify in this order:

- **Detached mode** — `current_branch` is empty. The commit exists at `head_sha` but no branch owns
  it, regardless of remotes or default-branch detection.
- **Trunk / direct-commit mode** — attached `current_branch` equals `default_branch`, or there is no
  remote. The commit itself is the deliverable.
- **PR mode** — attached feature branch (`current_branch` differs from `default_branch`) with a
  remote. The PR is the next lifecycle step.

### 6. Finalize the Bead

Never close a bead if the commit failed or changes are still uncommitted. Apply the
[Beads ownership rules](../beads/SKILL.md#ownership-proof-lifetime): resolve the exact target freshly
before every independent write and use its proven directory. A failed resolution writes nothing.

**Detached mode** — never close the bead. Report the detached commit SHA, leave the bead `in_progress`,
and offer the exact preservation command without running it automatically:

```bash
git switch -c {branch-name}
```

After the user creates an attached branch, `/complete-task` may be rerun to classify the workflow
and finalize the bead. Detached commits cannot enter the deferred-verification exception below.

#### Future-event-only verification

Use the [shared deferred-verification rule](../beads/SKILL.md#deferred-verification), not a second
policy. Only a qualified report from the prerequisites enters this branch: failed, stale or ordinary
unavailable evidence is not eligible. This branch precedes normal finalization and cannot use its
**Close the bead anyway** escape hatch to bypass the declared-boundary gate.

Show the report, committed SHA, applicable project guidance and delivery evidence, the exact proposed
follow-up or original-bead note using the shared checklist, wake date, provenance link, and honest
close reason. Resolve any missing date/check/environment detail before requesting a choice; do not
invent one. Ask one `AskUserQuestion` for explicit confirmation of the displayed proposal:

- **Snooze the original (Recommended)** — keep the evidence obligation on this bead and defer it to
  the agreed date; always available for eligible future-event-only work.
- **Close implementation + deferred follow-up** — offer only when an explicit project declaration
  separates delivery from future verification and its boundary has been reached. Cite both. A merge
  boundary not yet reached means snooze only; do not reinterpret PR mode as delivered implementation.
- **Stop** — no lifecycle changes; preserve the verification gap in the report.

No tracking writes on declined, abandoned or incomplete approval. This single choice also confirms
an existing pending-event commit from §3. Neither choosing nor loading this skill authorizes a new
rollout, job, remote sync, policy edit or unavailable test. A changed proposal needs fresh confirmation.

#### A. Close implementation + deferred follow-up

Check for an existing verification follow-up in the proven store, including closed/deferred rows
and their actual `discovered-from` links to this bead. Match revision, check and environment, not
just the title. Read its full record; reuse a matching outstanding record only after confirming it
with the user. A closed match, multiple matches or an unreadable inventory requires reconciliation,
not a new duplicate. For a new record, check the installed `bd create --help` and `bd defer --help`
contracts. Preserve the original's exact Jira `external_ref` via `--external-ref` when present;
omit that flag otherwise. Never guess a key or drop an association to make creation succeed.

Re-resolve the original immediately before creating in that same store:

```bash
~/.agents/skills/next/scripts/next-select resolve <bead-id>
bd -C <directory> create --type task --title="<verification outcome>" --description="<verification-note>" --status=deferred --defer="<wake-date>" --deps="discovered-from:<bead-id>" --json
```

The note carries the shared checklist and provenance; add the approved external reference if present.
Resolve the returned ID, confirm it belongs to the same store, and read back (also for a reused record):

```bash
~/.agents/skills/next/scripts/next-select resolve <follow-up-selector>
bd -C <directory> show <follow-up-id> --json
```

Require the saved status `deferred`, future `defer_until`, exact check/revision/environment,
`discovered-from` link and external reference to match the proposal. A failed readback or an ambiguous
create result means the original stays open; report any returned ID and do not create another on retry
without reconciling. Never silently repair the saved record or fall through to normal closure.

Only after that verification, freshly resolve the original again and close with the actual follow-up ID:

```bash
~/.agents/skills/next/scripts/next-select resolve <bead-id>
bd -C <directory> close <bead-id> --reason="implemented at <sha>; <check> unverified, tracked in <follow-up-id>"
```

If the close fails or is uncertain, retain the follow-up and report both records; a rerun reuses that
record after reconciliation, not another create. Successful pending-verification closure must skip §6a;
continue to §7. It proves implementation delivery only, never runtime verification.

#### B. Snooze the original

Use the shared verification checklist as `<verification-note>`, including the committed SHA, check,
event, environment, pass criteria, evidence destination and failure disposition. Check current
`bd defer --help`, then freshly resolve before this one write:

```bash
~/.agents/skills/next/scripts/next-select resolve <bead-id>
bd -C <directory> defer <bead-id> --until="<wake-date>" --reason="<verification-note>"
```

Then read back the original and verify its saved `deferred` status, `defer_until` and note. On failure
or uncertainty, report the actual remaining state; do not claim it was deferred or retry automatically.
No follow-up is created and nothing is closed. After successful snoozing, skip §6a and continue to §7.

#### Normal finalization

Only fully verified work (or checks evidenced as inapplicable) reaches these paths; pending-event
work cannot fall through. The project's required delivery boundary must still be satisfied.

**Trunk mode** — close the bead now when the verified commit satisfies the project's deliverable:

```bash
~/.agents/skills/next/scripts/next-select resolve <bead-id>
bd -C <directory> close <bead-id> --reason="<brief summary of what was done>"
```

Then continue to §6a.

**PR mode** — do **not** close the bead here. By convention the bead is closed one step later, at the `/create-pr` stage (and reopened if review demands major changes); closing at commit time would be premature, before the PR even exists. Instead, tell the user a PR workflow was detected (on branch `{current_branch}`) and the bead is being left `in_progress`, then offer the next step with `AskUserQuestion`:

- **Create the PR now (recommended)** — invoke the `/create-pr` skill via `Skill`. It pushes, opens the PR, and closes the bead.
- **Not yet** — leave the branch committed and the bead `in_progress`; remind the user to run `/create-pr` when ready.
- **Close the bead anyway** — only for an actually trunk-based repo with its declared integration
  boundary already satisfied; close it as in trunk mode, never as a pending-evidence bypass.

### 6a. Offer Jira review (opt-in)

Only after this run's fully verified trunk-mode close succeeds, follow the shared
[Jira review procedure](references/jira-review.md), starting with:

```bash
~/.agents/skills/complete-task/scripts/jira-review.py plan --bead <bead-id> --store <directory> --milestone trunk-commit
```

Add `--repo <path>` when the repository is not the current directory. Detached mode, PR mode and
**Close the bead anyway** never offer it: none is a configured delivery milestone. Without a policy
the helper is silent. Deferred-verification closures and snoozes skip this offer even in trunk mode:
never claim verification and post no Jira comment. Preserve the association on a follow-up so later
Jira inventory still sees unfinished work. A later evidence-only closure does not automatically
invoke this procedure; it needs a separate explicit user request. A transition still needs its own
fresh **Move to review** approval, and a Jira skip or failure never reopens the bead or undoes the commit.

### 7. Check for Follow-Up Work

After finalizing:

- Report §6's confirmed deferred disposition, verification gap, wake date and original/follow-up ID;
  do not create a second verification follow-up here. Resume/failure handling belongs to the shared
  [Beads lifecycle](../beads/SKILL.md#deferred-verification).
- If implementation revealed unrelated issues or TODOs, mention them to the user.
- Suggest creating unrelated follow-up beads if appropriate (but don't auto-create).

### 8. Report

Summarize what was done:

- Workflow mode and resulting bead state — fully verified **closed**, **implementation closed;
  verification deferred in <id>**, **original deferred until <date>**, or **left `in_progress`**
  with its explicit blocker/decision. Do not describe pending evidence as verified.
- If a PR was created via the handoff, its URL
- The Jira review outcome, separately from local completion (nothing when disabled)
- Commit hash and message
- Files changed count
- Any follow-up items noted

## Handling Edge Cases

- **No in-progress beads**: Ask user if they want to complete uncommitted work without a bead, or create one first
- **Multiple in-progress beads**: List them and ask user to pick
- **Clean-code fails repeatedly**: After 2 attempts, ask user for guidance
- **No changes to commit**: use the existing-commit path in §3, then the same classification in §5 and finalization in §6; never close directly from an empty diff.
- **Unrelated unstaged changes**: Warn user about them; suggest creating a separate bead/commit
- **Commit hook fails**: Investigate the hook failure, fix the underlying issue, and create a new commit (never amend, never skip hooks)
- **Feature branch but non-PR repo**: follow explicit project policy before branch heuristics; never
  use **Close the bead anyway** before the required integration boundary or with pending verification.
- **Detached HEAD**: preserve the reported commit with `git switch -c {branch-name}`; never close the bead while no branch owns the commit.
- **PR already exists for this branch**: still leave the bead open; `/create-pr` (or the user) handles the existing PR. Don't open a duplicate.

## Rules

- Never use `--no-verify` or skip git hooks
- Never push to remote yourself — pushing happens via the `/create-pr` handoff, not in this skill
- Never amend existing commits
- Never close a bead with uncommitted changes
- Never close a bead from a detached HEAD
- Never transition Jira outside the §6a procedure and its explicit approval
- In PR mode, do not close the bead — that happens at `/create-pr` (reopen later if review demands major changes)
- Always stage specific files, never bulk-add
- If any step fails, stop and inform the user rather than forcing through
