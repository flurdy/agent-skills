---
name: review-comments
description: Address PR review feedback through explicit item selection, independent validation, focused local fixes, verification, and a local commit. Never publishes remote actions; use reply-comments for separately confirmed push, reply, and resolution gates.
allowed-tools: "Read,Edit,Grep,Glob,Bash(~/.agents/skills/pr-status/scripts/gh-pr-feedback.py:*),Bash(~/.agents/skills/review-comments/scripts/gh-pr-current-info.sh:*),Bash(~/.agents/skills/review-comments/scripts/gh-pr-view-reviews.sh:*),Bash(~/.agents/skills/review-comments/scripts/gh-pr-comments.sh:*),Bash(gh pr view:*),Bash(gh pr diff:*),Bash(gh pr checks:*),Bash(git status:*),Bash(git diff:*),Bash(git add:*),Bash(git commit:*),Bash(git log:*),Bash(git rev-parse:*),Bash(git branch --show-current),Bash(make:*),Bash(npm:*),Bash(npx:*),Bash(sbt:*),AskUserQuestion"
model-tier: premium
model: opus
effort: high
version: "1.2.0"
author: "flurdy"
---

# Address Review Comments

Select and independently validate PR feedback before making focused local changes. This skill owns
only the attended local phase: selection, validation, edits, tests, and a local commit. It never
publishes a branch, GitHub reply, or thread resolution. `/reply-comments` owns those separately
confirmed remote actions.

## Usage

```text
/review-comments                         # PR for the current branch
/review-comments 123                     # backward-compatible current-repository selector
/review-comments owner/repo#123          # repository-qualified selector from the watcher
/review-comments owner/repo#123 inline:C1 conversation:I2
```

Trailing stable identities preselect candidates but never authorize an edit or reply.

## Instructions

### 1. Resolve the PR and Checkout

Accept `owner/repo#number` or a numeric PR. With no selector, resolve the current branch through:

```bash
~/.agents/skills/review-comments/scripts/gh-pr-current-info.sh
```

For a numeric selector, derive owner/repository from the current checkout. For a repository-qualified
selector, use its owner/repository for every GitHub call. Fetch PR metadata, head SHA, branch, body,
and changed files read-only.

Before offering a local fix, prove that the current directory is a matching checkout:

1. `origin` resolves to the selected owner/repository;
2. the current branch/HEAD represents the selected PR head;
3. the working tree's pre-existing changes are understood and will not be overwritten.

Never switch branches, create a checkout, fetch, reset, clean, or overwrite unrelated work. If no
matching checkout exists, validation and reply preparation may continue from the PR diff, but local
fix actions are unavailable. Tell the user which checkout is required.

### 2. Fetch the Normalized Inventory

Use one bounded read-only call:

```bash
~/.agents/skills/pr-status/scripts/gh-pr-feedback.py {owner} {repo} {pr_number}
```

Read `records`, `partial`, and `errors`. Preserve each candidate's stable `identity`, `updatedAt`,
`updateKey`, `stateKey`, source, lifecycle, author kind, and `targets` throughout the run. Never use
body text or counts as identity. Pending draft review comments are not observable and must not be
invented.

If `partial` is true, show available records and failed sources. The user may select an available
record, but do not infer that an absent record is handled. If the helper is unavailable, the
existing `gh-pr-view-reviews.sh` and `gh-pr-comments.sh` wrappers remain a compatibility fallback;
label stable identity and race protection unavailable and do not combine both fetch paths.

### 3. Apply Source and Lifecycle Policy

Group factual records by author kind, source, lifecycle, semantic type, and collector actionability.
These are triage hints, not proof; semantic validity remains agent judgment against evidence.

- **Human requests/questions:** validate independently; prepare short, polite, evidence-based
  replies when selected.
- **AI/bot findings:** validate exactly like human claims; use a terse factual reply only when it
  adds useful closure. Bot confidence is not evidence.
- **Top-level conversation or review summary:** any response is prepared as a new top-level PR
  comment, never an inline reply.
- **Inline review:** retain the root reply target and thread ID. Only this source can later resolve
  a review thread.
- **CI annotation:** fix-only; it has no reply or resolution endpoint.
- **Approval or automated status/noise:** no action or response.
- **False positive or intentional trade-off:** a concise rationale may be prepared, but never claim
  a fix and do not mark it resolved as fixed.
- **Resolved, outdated, dismissed, or self-authored:** skip by default and show separately.

### 4. Select Items

Render a numbered candidate table with PR, stable feedback ID, author/source, lifecycle, bounded
gist, and triage hint. No code change occurs before explicit item selection.

Use `AskUserQuestion` to select identities. When there are four or fewer, use one multi-select
question with one option per identity. For a larger inventory, ask in priority batches of at most
four and leave unselected items untouched; the user may type an exact list of IDs. Preselected IDs
from arguments still require this current-run confirmation. Selecting an item authorizes only
read-only validation, not a fix or publication.

### 5. Validate Selected Items

For each selected identity, read the full record, referenced path/line, current implementation,
relevant PR diff, requirements, existing tests, and CI. Do not trust the reviewer wording. Choose
one outcome and cite concrete evidence:

- `confirmed defect`
- `valid improvement`
- `question needing an answer`
- `subjective/trade-off decision`
- `false positive/already handled`
- `stale/outdated`
- `out of scope`
- `unable to validate`

State confidence as high, medium, or low and name missing evidence. Security, architecture,
scope-changing, ambiguous, or low-confidence feedback always returns to the user; never auto-fix
it. Re-read the item against current code before any later edit. If the feedback became stale,
outdated, resolved, or already handled, update the outcome and do not edit.

### 6. Choose a Local Action

Show the validation result first. Then use `AskUserQuestion` for each item, batching at most four
questions per call, with only eligible choices:

- **Fix and verify (Recommended)** — available only for a confirmed defect or accepted valid
  improvement in a matching checkout.
- **Prepare reply** — draft an evidence-based response but do not post it.
- **Acknowledge only** — record the item as reviewed in bounded session state; no repository or
  GitHub action.
- **Defer / skip with rationale** — leave it pending or retain a concise reason.

Questions and trade-offs default to **Prepare reply** or defer. Security, architecture,
scope-changing, ambiguous, and low-confidence items offer discussion/defer choices only. A custom
answer may narrow a requested fix but is not remote-action permission.

### 7. Implement, Verify, and Commit Locally

For each approved fix or coherent selected group:

1. Define expected behavior and proportional test evidence before editing.
2. Add a focused failing regression test when practical.
3. Make the smallest change that addresses the validated claim.
4. Cover the relevant happy path, sad path, and edge case; explain when one is not applicable.
5. Run focused verification first, then the repository's required lint/type/test checks.
6. Review the diff and confirm unrelated pre-existing work is excluded.
7. Stage explicit paths only and commit locally with a concise conventional message.

Do not skip verification, bypass hooks, amend unrelated commits, or claim a fix without a successful
local commit. If tests fail, stop and keep remote actions unavailable. If multiple items require
unrelated changes, use separate commits. This skill does not publish the commit.

### 8. Prepare the Remote Handoff

Draft replies only for selected items. Keep a bounded session ledger keyed by
`repository/PR/identity/updateKey` with validation, files/tests, commit SHA, intended reply surface,
prepared body, and resolution eligibility.

- Humans receive short polite responses with evidence.
- AI/bots receive terse factual responses when useful.
- A fixed item may reference the verified local commit without claiming it is pushed.
- A rationale must say no change was made.
- CI annotations, approvals, status noise, and skipped lifecycle records have no reply.

Do not call a reply, conversation-comment, or resolution helper here. Render the exact next command:

```text
/reply-comments owner/repo#123 identity1 identity2 ...
```

`/reply-comments` must independently re-fetch and reconfirm push, posting, and resolution.

### 9. Summary

Map every selected record, including deferred and skipped items:

| Feedback ID | Validation | Files/tests/commit | Push state | Reply | Resolution |
|---|---|---|---|---|---|

Use `local only` for a new commit, `not applicable` when no change was made, `prepared/not posted`
for drafts, and `not attempted` for remote actions. Include unresolved uncertainty and the
repository-qualified `/reply-comments` handoff when anything is prepared.
