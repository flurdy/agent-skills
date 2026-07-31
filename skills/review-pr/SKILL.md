---
name: review-pr
description: Review a repository-qualified pull request at an immutable head, compare it with Jira requirements, and return a read-only verdict with explicit evidence completeness.
allowed-tools: "Read,Grep,Glob,Bash(~/.agents/skills/review-pr/scripts/gh-pr-snapshot.py:*),mcp__jira__jira_get,AskUserQuestion"
model-tier: premium
effort: xhigh
version: "2.0.0"
author: "flurdy"
---

# Review Pull Request

Review one immutable GitHub pull-request snapshot. The workflow is read-only: it never submits a
GitHub review, approval, change request, comment, Slack message, Jira mutation, checkout change, or
other external action. No GitHub review is ever submitted by this skill.

## Usage

```text
/review-pr                                      # current branch
/review-pr 123                                  # current-repository shorthand
/review-pr owner/repo#123                       # repository-qualified
/review-pr https://github.com/owner/repo/pull/123  # PR URL
/review-pr owner/repo#123 --automation --premium-established --expected-head SHA
```

Accept a PR URL, `owner/repo#number`, a numeric current-repository shorthand, or no selector. A
qualified selector never derives repository identity from the current working directory.

Optional controls:

- `--expected-head` SHA — require the selected immutable head.
- `--checkout` PATH — consider this local checkout, but use it only after exact verification.
- `--automation` — return the machine-readable contract below and never ask a question.
- `--premium-established` — assert that the caller selected the premium route before automation.
- `--deadline-seconds N` — total attended review budget; default 300 seconds. Record one absolute
  stop deadline at invocation, pass only the remaining seconds to each collector call, and return
  partial evidence when the budget expires.

## 1. Establish the premium route

This skill is `model-tier: premium`.

For a manual invocation below the premium tier, use `AskUserQuestion` once:

- **Continue here** — accept reduced depth for this run.
- **Stop** — switch model or rerun in a premium session.

Skip the question when the user explicitly selected the current model.

For `--automation`, the skill must not prompt. Require `--premium-established` and confirm the
current route satisfies the premium tier. If either condition fails, return `status: failed`,
`reason: premium-route-unavailable`, and no verdict. Frontmatter alone is not route attestation.

## 2. Collect one qualified snapshot

Run the collector once before analysis:

```bash
~/.agents/skills/review-pr/scripts/gh-pr-snapshot.py \
  'owner/repo#123' \
  --expected-head HEAD_SHA_IF_SUPPLIED \
  --checkout CHECKOUT_IF_SUPPLIED \
  --timeout REMAINING_SECONDS \
  --pretty
```

Omit absent options. With numeric or no selector, the collector uses the current checkout only to
resolve the shorthand, then passes explicit owner/repository to every remote request.

The collector returns canonical repository/PR identity, node ID, base/head refs and SHAs, bounded
file patches, exact-head CI rollup, normalized feedback, a review-state key, checkout verification,
limits, and errors.
It disables paging and lazy Git fetching, applies one deadline and command-output cap, and rechecks
base/head identity after collection.

Gate on its status:

- `complete` with `reviewReady: true` — continue.
- `partial` — name every unavailable/truncated source; do not issue a definitive verdict.
- `stale` — stop and report the expected and observed revisions; never present mixed-SHA evidence.
- `failed` — stop and report the bounded error; do not infer that missing evidence is empty.

Draft or closed/merged state remains explicit in `target`; do not treat it as an open review.

## 3. Use local code only after exact checkout proof

A matching checkout is optional. Local repository reads are permitted only when
`checkout.available` is true. That means the origin
matches the selected repository, the working tree is clean, and local HEAD exactly matches the PR
head SHA. Anchor every `Read`, `Grep`, or `Glob` path under `checkout.path`.

When verification fails, state **Local repository search unavailable** with the collector's reason.
Use only the bounded remote patches and metadata. Never search the workspace root or unrelated cwd,
and never switch branches, fetch, reset, clean, create a worktree, or edit files.

## 4. Read feedback before forming an opinion

Read `evidence.feedback.records` before analyzing the patches. Preserve stable `identity`,
`updateKey`, `stateKey`, source, lifecycle, author, targets, and path/line data. Inspect
`evidence.feedback.partial` and its errors before treating absence as none.

Build the unresolved list from:

- unresolved, non-outdated inline-review records;
- current `CHANGES_REQUESTED` reviews only when `target.reviewDecision` still reports changes
  requested;
- substantive current review summaries or conversations whose request remains unmet.

Treat approvals, dismissed/outdated/resolved records, self-authored messages, and automated status
noise separately. Bot findings require the same independent validation as human findings.

## 5. Load Jira context when linked

Find the first Jira key in title, body, or head branch using `[A-Z][A-Z0-9]{1,9}-[0-9]+`.

- No key: record `jira.status: not-linked` and continue without an AC checklist.
- Key found and lookup succeeds: extract summary, description, status, issue type, and acceptance
  criteria with the read-only Jira get tool.
- Key found but Jira is unavailable, malformed, or missing the acceptance field: record
  `jira.status: unavailable`, include the error, and never claim requirements are satisfied.

Do not use any Jira mutation tool.

## 6. Analyze the exact-head evidence

Use `target`, `evidence.files`, feedback, CI state, and verified local reads when available.

Before Jira lookup and before each analysis phase, check the one invocation deadline. On expiry,
return `partial` with `budget-expired`; do not start another tool call. The caller should also impose
its normal turn/runtime budget so interruption does not depend on model compliance.

For each changed file, assess:

- alignment with linked acceptance criteria;
- correctness, security, compatibility, and scope;
- test coverage including happy, sad, and edge paths;
- whether current patches address unresolved feedback;
- deletions and repository-wide references, but only when checkout verification permits the search.

If file patches, feedback, checks, Jira requirements, or repository-wide evidence needed for a
claim are unavailable, make the limitation explicit. Missing evidence is never evidence of absence.

## 7. Recheck the immutable revisions

Immediately before writing any verdict, run the fast verifier using the original snapshot SHAs:

```bash
~/.agents/skills/review-pr/scripts/gh-pr-snapshot.py \
  'owner/repo#123' \
  --expected-head ORIGINAL_HEAD_SHA \
  --expected-base ORIGINAL_BASE_SHA \
  --expected-state-key ORIGINAL_STATE_KEY \
  --verify-only \
  --timeout REMAINING_SECONDS
```

The state key covers PR lifecycle, draft/review decision, exact-head CI state, and stable feedback
identities/update state. If verification returns anything except `complete`, return `stale` or
`failed` and suppress the verdict. Never reuse approval from a previous invocation or head SHA.

## 8. Render unresolved comments before the verdict

Every human-readable review must include this exact section before any assessment or verdict:

```markdown
### Unresolved Reviewer Comments

- author — path:line — request — whether it remains valid at the reviewed head
```

If genuinely empty, emit:

```markdown
### Unresolved Reviewer Comments

- None.
```

## 9. Output contract

### Manual output

```markdown
## owner/repo#123 Review

**Head:** {immutable head SHA}
**Base:** {immutable base SHA}
**Snapshot:** complete
**Jira:** {key and summary | Not linked | Unavailable}
**CI:** {exact-head rollup state}
**Local checkout:** {verified path | unavailable reason}

### Changes Overview
- ...

### Unresolved Reviewer Comments
- ...

### AC Checklist
| AC | Status | Evidence |
|----|--------|----------|
| ... | pass/fail/partial | ... |

### Concerns
- ...

### Verdict
{Safe to merge | Needs changes | Needs discussion}
```

Verdict rules:

- **Needs changes** for unmet ACs, failing exact-head CI, or a valid blocking concern.
- **Needs discussion** for conflicting evidence or a substantive unresolved question.
- **Safe to merge** only when the snapshot is complete, exact-head CI succeeds, Jira ACs are met
  when linked, and unresolved comments are `None.`.
- No definitive verdict for `partial`, `stale`, or `failed` snapshots.

### Automation output

For `--automation`, emit one JSON object and no conversational prompt or surrounding prose:

```json
{
  "schemaVersion": "review-pr/v1",
  "status": "complete|partial|stale|failed",
  "target": {
    "repository": "owner/repo",
    "number": 123,
    "nodeId": "...",
    "headSha": "...",
    "baseSha": "...",
    "stateKey": "..."
  },
  "evidence": {
    "snapshotComplete": true,
    "checkout": "verified|unavailable",
    "jira": "available|not-linked|unavailable",
    "ci": "SUCCESS|FAILURE|PENDING|UNKNOWN",
    "errors": []
  },
  "unresolvedComments": [],
  "acChecklist": [],
  "concerns": [],
  "verdict": "safe-to-merge|needs-changes|needs-discussion|null"
}
```

The watcher may consume a verdict only when `status` is `complete`, the final revision recheck
succeeded, and `verdict` is non-null. This output authorizes no GitHub review or other external
communication.
