---
name: reply-comments
description: Safely publish prepared PR-feedback outcomes through separately confirmed push, reply, and inline-thread resolution gates. Re-fetches normalized identities before every mutation and keeps retries idempotent.
allowed-tools: "Read,Bash(~/.agents/skills/pr-status/scripts/gh-pr-feedback.py:*),Bash(~/.agents/skills/reply-comments/scripts/gh-pr-current-info.sh:*),Bash(~/.agents/skills/reply-comments/scripts/gh-pr-comments.sh:*),Bash(~/.agents/skills/reply-comments/scripts/gh-pr-review-threads.sh:*),Bash(~/.agents/skills/reply-comments/scripts/gh-pr-reply-comment.sh:*),Bash(~/.agents/skills/reply-comments/scripts/gh-pr-conversation-comment.sh:*),Bash(~/.agents/skills/reply-comments/scripts/gh-pr-resolve-thread.sh:*),Bash(gh pr view:*),Bash(git:*),AskUserQuestion"
model-tier: standard
model: sonnet
effort: medium
version: "1.2.1"
author: "flurdy"
---

# Reply to Review Comments

Publish selected, validated feedback outcomes after `/review-comments`. Push, reply posting, and
thread resolution are three separate visible actions, each requiring fresh current-run
confirmation. Never infer remote permission from item selection, validation, a local commit, a
previous run, or approval of another action.

## Usage

```text
/reply-comments                         # PR for the current branch; select eligible items
/reply-comments 123                     # backward-compatible current-repository selector
/reply-comments owner/repo#123          # repository-qualified selector
/reply-comments owner/repo#123 inline:C1 conversation:I2
```

Arguments identify candidates only. They are not permission to push, post, or resolve.

## Instructions

### 1. Resolve the PR and Checkout

Accept `owner/repo#number` or a numeric PR. With no selector, resolve the current branch through:

```bash
~/.agents/skills/reply-comments/scripts/gh-pr-current-info.sh
```

Use the selected owner/repository for every GitHub call. Before offering a push, prove the current
checkout's `origin`, branch, and HEAD correspond to that PR. Do not switch, fetch, reset, clean,
merge, rebase, or overwrite work. A repository mismatch disables the push gate but does not prevent
a separately validated answer/rationale from being prepared.

### 2. Restore Bounded Handled State

Carry forward `/review-comments` state when it exists. Otherwise reconstruct validation and prepared
replies read-only before offering any remote action. Keep at most 500 handled actions keyed by
`repository/PR/identity/updateKey`, recording validation, commit SHA, push result, posted reply ID,
and resolution result.

On retry:

- a recorded successful push, reply, or resolution is not repeated;
- an inline record with a later self reply is treated as already replied;
- an already resolved thread is recorded as complete without another mutation;
- an uncertain or timed-out mutation result is reported as unknown — do not retry automatically;
- if bounded state was lost, announce that idempotency continuity is unavailable and require a
  read-only recheck plus new confirmations. For a top-level response whose prior publication cannot
  be disproved from current self-comments, do not offer another post; return it for manual reconciliation.

Never use body text, author, count, or list position as identity.

### 3. Select and Re-fetch

If no identities were supplied, render eligible records and use `AskUserQuestion` to select exact
stable IDs in batches of at most four. Supplied IDs still require a current-run selection summary.
Skip approvals, automated status/noise, CI annotations without a fix, and resolved, dismissed,
outdated, or self-authored items.

Before preparing remote gates, re-fetch the normalized inventory:

```bash
~/.agents/skills/pr-status/scripts/gh-pr-feedback.py {owner} {repo} {pr_number}
```

Compare each selected stable `identity`, `updateKey`, and `stateKey` with the validated version. If
the inventory is `partial`, do not mutate and name the failed source. If an item is changed,
resolved, outdated, or self-authored, stop that item and return it to selection/validation. Missing
is not resolved. This re-fetch is mandatory even when the previous skill ran moments ago.

### 4. Compose Endpoint-correct Replies

Show the proposed response policy before any confirmation. House style for every reply: terse —
one-liners are fine; friendly when a human is on the other end; never nits, names, or bead IDs.

- **Human request/question:** short, polite, evidence-based reply.
- **AI/bot finding:** terse factual reply only when it adds useful closure; independently validated
  evidence remains authoritative.
- **Inline review:** reply to `targets.reply.commentId` through the inline endpoint.
- **Top-level conversation:** create a new top-level PR comment through the conversation endpoint.
- **Review summary:** respond through the same top-level conversation endpoint; it is not an inline
  comment.
- **CI annotation:** fix-only; no reply or resolution endpoint.
- **Approval or automated status/noise:** no response.
- **False positive or intentional trade-off:** concise rationale, explicitly no fix; never resolve
  it as fixed.
- **Resolved, outdated, dismissed, or self-authored:** skip.

A reply claiming a fix must map to a verified local commit. If that commit is not visible on the PR,
the push gate must succeed before its reply can be posted. Questions and rationale-only responses
may skip the push gate.

### 5. Push Confirmation

If no selected reply depends on an unpushed local fix, render `Push state: not applicable` and skip
this section's question.

Otherwise show checkout, branch, commit SHA, upstream state, verification evidence, and the exact
non-force command. Use `AskUserQuestion` to request explicit permission immediately before the
push. Permission from item selection, fixing, committing, or an earlier run does not count.

- **Push commit (Recommended)** — on this answer, make the standalone `git push` invocation as the
  next tool call. Do not hide it in a script or command chain.
- **Not now** — leave the commit local and suppress any reply that claims the fix is published.
- **Stop** — perform no remote action.

Never force-push, amend, or push another branch/tag. If the push fails or the branch moved, stop;
do not retry or proceed to fixed-item replies. Record the pushed SHA only after success.

### 6. Reply Confirmation

Build a preview keyed by feedback ID with the exact reply body and exact surface (`inline review` or
`top-level conversation`). Do not include CI annotations, approvals, noise, or skipped lifecycle
records.

Use one `AskUserQuestion` confirmation for the preview:

- **Post selected replies (Recommended)**
- **Edit drafts**
- **Skip replies**
- **Stop**

After **Post selected replies**, re-fetch immediately before posting. Compare `identity`,
`updateKey`, `stateKey`, lifecycle, and later-self-reply state again. Skip every raced item and ask
for fresh validation rather than posting stale text. If the re-fetch is partial, post nothing.

For each still-current confirmed item, use exactly one endpoint:

**Inline review** — root comment target:

```bash
~/.agents/skills/reply-comments/scripts/gh-pr-reply-comment.sh {owner} {repo} {pr_number} {targets.reply.commentId} "{body}"
```

**Top-level conversation or review summary** — new PR conversation comment:

```bash
~/.agents/skills/reply-comments/scripts/gh-pr-conversation-comment.sh {owner} {repo} {pr_number} "{body}"
```

Record the returned reply/comment ID before moving to the next item. If a result is ambiguous, stop
that item and do not retry automatically. Never send a top-level record to the inline endpoint or
an inline record to the conversation endpoint.

### 7. Resolution Confirmation

Resolve only inline review threads. First re-fetch the inventory again and retain the selected
record's `targets.resolveThreadId`. Exclude any thread that raced, is already resolved/outdated, has
no confirmed reply, or has an unknown reply result.

A verified and published fix may be presented as resolution-eligible. A question or rationale may
be eligible only when the exact reply was posted and the user explicitly resolves it as answered or
not applicable. A false positive is never described or resolved as fixed. CI annotations,
conversation comments, and review summaries cannot resolve.

Show feedback ID, thread ID, validation outcome, reply ID, and proposed resolution meaning. Use a
new `AskUserQuestion` confirmation, separate from reply permission:

- **Resolve selected threads (Recommended)**
- **Leave open**
- **Stop**

After confirmation, re-fetch once more. For each still-current unresolved thread, call visibly:

```bash
~/.agents/skills/reply-comments/scripts/gh-pr-resolve-thread.sh {targets.resolveThreadId}
```

Record success per thread. Do not retry an unknown result automatically and never resolve a thread
whose reply failed or was skipped.

### 8. Summary

Render every selected identity, including races, deferrals, and failures:

| Feedback ID | Validation | Files/tests/commit | Push state | Reply | Resolution |
|---|---|---|---|---|---|

For remote actions include `not applicable`, `declined`, `failed`, `unknown`, or the successful
SHA/reply ID/thread result. Explicitly name items returned to validation because of an edit or
lifecycle race. Preserve the bounded handled ledger so an immediate retry skips successful actions.
