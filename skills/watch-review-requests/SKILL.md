---
name: watch-review-requests
description: >
  Watch for direct GitHub review requests, run one bounded repository-qualified review at a time,
  and pause for private, draft-only, defer, or separately confirmed external dispositions.
allowed-tools: "Read,Grep,Glob,Skill(review-pr),Bash(~/.agents/skills/pr-status/scripts/gh-pr-review-requests.py:*),Bash(~/.agents/skills/pr-status/scripts/gh-pr-checkout.py:*),Bash(~/.agents/skills/review-pr/scripts/gh-pr-snapshot.py:*),Bash(gh pr review:*),AskUserQuestion"
model-tier: premium
model: opus
effort: xhigh
version: "1.0.0"
author: "flurdy"
---

# Watch Review Requests

Watch the authenticated user's inbound GitHub review requests. For each newly actionable direct
request, run the repository-qualified read-only `/review-pr` workflow exactly once, render its
complete report, then pause for disposition. Process one review at a time so analysis, reports,
and questions cannot interleave.

This watcher does not replace `/review-pr`. It composes the bounded queue collector and immutable
review contract. No external action is the default-safe outcome.

## Usage

```text
/watch-review-requests                              # adaptive; stop 18:00; at most 3 reviews
/watch-review-requests 10m 17 --reviews 5          # fixed 10m; stop 17:00; at most 5 reviews
/watch-review-requests reset                       # stop and clear session-local watcher state
/watch-review-requests recheck owner/repo#123      # one immediate selected recheck; no watcher start
/watch-review-requests disposition owner/repo#123  # reopen one deferred or saved draft
/watch-review-requests status                      # show runtime, queue, and budget state
```

Parse at most one positive `\d+m` interval, one stop hour from `0` through `23` (default `18`),
and one `--reviews N` or `--reviews=N` budget from 1 through 20 (default `3`). Reject unknown,
duplicate, missing, or malformed arguments. No interval means adaptive cadence. `reset`,
`recheck owner/repo#123`, `disposition owner/repo#123`, and `status` are user commands, not watcher
starts. Runtime-injected ticks use exactly `tick adaptive|fixed --reviews N --stop-at ISO_8601`;
accept those tokens only in internal tick mode and reject them on a normal start.

Resolve today's deadline in local time. Do not start at or past it. Before scheduling, verify that
the current route satisfies the premium tier; unlike a manual `/review-pr`, this attended watcher
must not fall back to reduced depth. If the route cannot be established, stop without scheduling.
Render this start preflight before the start call:

```text
Premium route: {current premium route}
Cadence: {adaptive | fixed interval}
Stop deadline: {local timestamp}
Review budget: {N premium review attempts}
```

## Safety boundary

Queue collection and review analysis are read-only. Never switch branches, create a checkout,
fetch, edit code, change Git history, mark notifications, alter requested reviewers, submit a
review, or send Slack while polling or analyzing. Never infer permission to communicate from a
verdict or disposition category. Do not run shell, Git, filesystem, workspace, or authentication
preflight probes when starting the watcher; bounded tick collectors report their own failures.

A GitHub submission is permitted only through the separate confirmation sequence below, after
showing the exact text and repository and a fresh immutable-state check. Slack is draft-only in
this watcher; it has no Slack send permission. The safe response to every report is **No external
action**. Never discover or guess a Slack recipient, channel, or workspace.

## Session-local state

Carry structured state in this conversation; never write a cache, repository file, GitHub marker,
notification marker, or Beads item. Retain:

- the collector's bounded queue state verbatim;
- run start/deadline, cadence, configured review budget, and a monotonic `reviewAttempts` count;
- a per-run `completedWorkKeys` set for exactly-once successful reports, reset with
  `reviewAttempts` on a new normal start and therefore capped by the 1–20 attempt budget;
- at most 20 pending dispositions, keyed by repository, PR node, request event, and reviewed head,
  each in `verified-unmarked`, `fresh`, `deferred`, `github-draft`, `slack-draft`, or `stale` state;
- one bounded in-flight record with `workKey`, phase (`analyzing`, `review-complete`,
  `report-rendered`, or `verified-unmarked`), and the complete automation result when available;
- consecutive failure counts per collector/review source and adaptive quiet streak.

Restarting in the same session reuses handled queue work and pending dispositions, but creates a
new run deadline, resets `reviewAttempts` and `completedWorkKeys`, and creates a new count budget.
Queue handled keys still prevent replay. A new session announces a fresh baseline. If an active watch
loses state after context compaction, stop instead of resetting its budget or replaying work; a
manual new start may then announce a fresh baseline.

`reset` first stops an armed/running/paused watcher, then clears queue state, pending dispositions,
completed keys, review attempts, in-flight state, run deadline, cadence, budget, failure counts,
and quiet streak. It
does not mutate GitHub. `status` reports `/watch-status` when protocol v1 exists, state size, pending
dispositions by state, current phase, failures, deadline, and budget. `recheck owner/repo#123` makes
one bounded queue call with `--recheck`, selects only that qualified PR, and performs the serial
review flow below; a draft remains non-actionable. It does not schedule a watcher or treat other
recheck rows as new. `disposition owner/repo#123` reopens one deferred or saved-draft record without
rerunning analysis. A GitHub draft record retains its exact kind, body, quoted heredoc command, and
immutable target; reopening resumes at **Verify for submission**. A Slack draft record retains its
exact paste-ready text and target; reopening shows Keep private or Keep draft only.

A deferred or saved-draft record remains listed but is not automatically prompted on later ticks.
It never blocks a different PR. A `fresh` disposition is offered before new work; after Defer it
moves to `deferred`, allowing the next queued PR to proceed serially. Resolve an older pending
record before starting another report for the same PR.

## Start behavior

Normal invocations start an attended recurring watcher. The first tick lands after about one
minute. Premium route, deadline, and review budget must be visible first.

### Pi protocol v1

This section is Pi-only. In Claude Code, skip directly to **Claude Code fallback** without probing,
searching for, or discussing Pi. Harness selection comes from the current tool surface; never use
the shell to detect another harness or executable.

If the current harness directly exposes `watch_loop`, use this branch before Claude scheduling:

1. Call `watch_loop` with `action: status` and require `protocolVersion: 1`. If another watch is
   `armed`, `running`, or `paused`, do not replace it; show status and point to `/watch-status`,
   `/watch-stop`, or `/watch-resume`. Stop on a protocol mismatch.
2. Convert the local deadline to ISO-8601 with its timezone offset for `stopAt`.
3. Use this self-contained tick prompt. Substitute every brace before starting; do not leave the
   tick dependent on prose from the initiating turn:

   ```text
   Load and follow the skill named `watch-review-requests` now in `tick` mode. This is one attended inbound-review tick, not a watcher start. Cadence is {cadence_mode}; the immutable run stop deadline is {deadline_iso}; the configured premium-review attempt budget is {review_budget}; derive the remaining review count from that budget minus the session-local reviewAttempts count. Preserve the session-local collector state, pending dispositions, completedWorkKeys, reviewAttempts, in-flight record, failures, and quiet streak. The premium route {premium_route} was established before launch; verify it still satisfies premium before invoking Skill(review-pr). If required state is unavailable, stop rather than resetting the budget or replaying work. Collect the bounded requested-review queue, use only the allowlisted gh-pr-checkout helper for optional local discovery, never run ad-hoc shell probes, process direct actionable work strictly one review at a time, render every complete immutable review before marking it locally reviewed, reverify it before every disposition stage, and wait for each answer. Never submit to GitHub without showing the exact draft and receiving the separate final confirmation followed by immutable verification; Slack is draft-only and never sends. An open question blocks the tick: do not call watch_loop complete while waiting. Do not start another premium invocation when the deadline or review budget is reached; always finish a retained or newly returned complete result through rendering, verification, local completion, and disposition, then stop. After visible output and the final next-tick line, call the matching protocol-v1 watch_loop action: complete. Use outcome: continue and adaptive delaySeconds from that line, or omit delaySeconds in fixed mode; use outcome: stop for a handoff, external send, deadline/budget exhaustion, lost state, or terminal failure.
   ```

4. Adaptive start:

   ```yaml
   action: start
   protocolVersion: 1
   label: Review requests
   mode: adaptive
   initialDelaySeconds: 60
   missedCompletionPolicy: pause
   stopAt: <today's local deadline as ISO-8601>
   tickPrompt: <prompt above>
   ```

5. Fixed start adds the selected interval in seconds:

   ```yaml
   action: start
   protocolVersion: 1
   label: Review requests
   mode: fixed
   initialDelaySeconds: <interval seconds>
   intervalSeconds: <interval seconds>
   missedCompletionPolicy: pause
   stopAt: <today's local deadline as ISO-8601>
   tickPrompt: <prompt above>
   ```

The runtime clamps intervals to 60–3600 seconds. A successful start ends the initiating turn. The
pause policy is mandatory: an unanswered, interrupted, or malformed attended tick must never retry
itself. Only a completed tick may call `action: complete`.

### Claude Code fallback

In Claude Code, enter this branch directly. Do not inspect the filesystem, PATH, process list, or
installed binaries to decide whether Pi exists, and do not include Pi capability commentary in the
start preflight. Use Claude's existing scheduling capability. If neither `ScheduleWakeup` nor
`/loop` is available, explain that recurring watches are unsupported and stop.

For adaptive mode, apply the established Fable session-model guard: Fable must not start an
adaptive watcher because its trailing scheduling call can discard visible output. Recommend a
Sonnet/Opus session or fixed mode. Otherwise schedule the first tick after 60
seconds with the same self-contained contract. Each completed tick renders first, waits for every
answer, and calls `ScheduleWakeup` last using the numeric N from `next-tick:`. Never schedule while
a question is open. Stop instead of scheduling past the deadline or after a terminal outcome.

For fixed mode use:

```text
/loop {interval} /watch-review-requests tick fixed --reviews {N} --stop-at {deadline_iso}
```

Substitute the resolved interval, budget, and deadline before launch. Fixed ticks ignore adaptive
delay recommendations. Every fallback
tick must load this skill, preserve session-local state, and obey the same serial and confirmation
boundaries.

## Tick mode

### 1. Enforce run bounds

Before collection and before each tool/model phase, compare local time with the run deadline and
check the remaining review count (`budget - reviewAttempts`). Do not begin another expensive
review unless at least 30 seconds and one attempt remain. Zero remaining attempts blocks only a
new `Skill(review-pr)` invocation: a retained or newly returned complete result must still be
persisted, rendered, verified, marked, and offered for disposition. A budget or deadline stop
preserves other unhandled queue work for a later start. A pending disposition may still be resolved
without spending another review count, but the watcher then stops.

Before collection or selection, recover in-flight state in this strict order:

1. `verified-unmarked` — reverify, then repeat the idempotent local-completion transaction.
2. `report-rendered` — reverify the retained complete result, then continue local completion.
3. `review-complete` — render the retained automation result; never invoke `/review-pr` again.
4. `analyzing` without a complete result — treat the charged attempt as interrupted, clear only
   that phase, and retry later only if deadline and another attempt remain.

A complete retained automation result always wins over its older phase label. This recovery path
prevents a second successful premium run even when interruption occurs before or during rendering.

### 2. Collect transitions once

Pass prior collector state as the bounded `--state-json` argument to one call:

```bash
~/.agents/skills/pr-status/scripts/gh-pr-review-requests.py \
  --state-json 'PRIOR_STATE_JSON' --timeout REMAINING_COLLECTION_SECONDS
```

On the first tick omit `--state-json`. Preserve the returned `state` even when no review runs.
Inspect `status`, `errors`, `failedRepositories`, `transitions`, and `queue` before acting.

- `failed`: show the bounded error, increment its failure streak, and do not review or mark work.
- `partial`: render every failed source and continue only with fully identified queue items.
- After three consecutive failures for the same source, stop with retained state.
- Complete data clears only the matching failure streak.

Draft requests wait until their explicit `ready` transition; a qualified recheck does not override
the collector's draft exclusion. Render team requests separately as informational; never treat them as personal
direct requests. Render `re_requested`, `head_changed`, request removal, submitted review,
closed/merged, and draft/ready transitions explicitly. A new commit alone is not a re-request.

When no pending disposition, transition, or direct queue item needs attention, render only a
header, checked/partial counts, bounded-state summary, and:

```text
No new actionable direct review requests.
```

### 3. Select serial work

Sort actionable direct queue items by request-event time, then repository and PR number. Select
only the first item. Multiple requests remain queued and are processed serially after the current
report is resolved or deferred. Never process a team request. Use the queue `workKey` unchanged.

Offer a `fresh` pending disposition before spending budget on new work. Do not automatically offer
`deferred`, `github-draft`, or `slack-draft` records; list them in the summary and let
`disposition owner/repo#123` reopen one. They do not block a different PR. If any unresolved record
already belongs to the selected PR, skip that PR until its disposition is resolved. When 20 pending
dispositions are retained, do not start or mark another review; report `pending-capacity` and stop
without evicting or suppressing queue work.

Resolve an optional local checkout with exactly one allowlisted helper call:

```bash
~/.agents/skills/pr-status/scripts/gh-pr-checkout.py OWNER/REPO HEAD_SHA \
  --timeout REMAINING_SECONDS
```

This helper alone may enumerate registered workspace members and Git worktrees. Never improvise a
shell loop or run `ls`, `find`, `git -C`, `git worktree`, remote, or HEAD probes. When
`checkout.available` is true, pass its path to `/review-pr`; otherwise state remote-only evidence
and continue without local reads.

### 4. Invoke the immutable review

Require the still-premium route and invoke `Skill(review-pr)` non-interactively with the selected
qualified identity and exact queue head:

```text
/review-pr owner/repo#123 --automation --premium-established \
  --expected-head HEAD_SHA --deadline-seconds REMAINING_REVIEW_SECONDS \
  [--checkout VERIFIED_HELPER_PATH]
```

Pass `--checkout` only from a `checkout.available: true` helper result. The review snapshot verifies
it again. Never create or update a checkout. Impose the normal runtime/turn bound in addition to the skill deadline.

Accept a report only when schema is `review-pr/v1`, status is `complete`, target repository/number,
node ID, and head match the queue item, the final revision check succeeded, and verdict is non-null.
Require the automation fields used below: `changesOverview`, evidence status/reasons and Jira
identity, `unresolvedComments`, `acChecklist`, `concerns`, and `verdict`. Never reconstruct missing
sections by rerunning analysis or guessing.

`partial`, `stale`, `failed`, malformed, timed-out, or interrupted runs remain unhandled and
retryable. Do not add a completed key or call `--mark-reviewed`. Show their errors and use warm
cadence; an explicit stale result enters the stale flow.

Persist the bounded in-flight record and increment `reviewAttempts` immediately before invoking
`Skill(review-pr)`. Every premium invocation consumes one attempt, including a failed, stale,
timed-out, or interrupted run. If analysis is interrupted before a complete result, retry later
only when another attempt remains. Immediately after accepting a complete automation result,
persist it and set phase `review-complete` before rendering any report text. Retain that exact
result with each later phase transition. If the report
is already visibly present at the **report-rendered checkpoint**, do not run duplicate successful
analysis: reverify that result and continue the idempotent local-completion transaction. If visible
output continuity is uncertain, stop and ask for an explicit recheck rather than claiming completion.

### 5. Render the complete review report

Render the complete human-readable review before any disposition question, including:

- repository/PR, immutable head/base, request event/requester, and author;
- snapshot, exact-head CI, Jira, checkout, and evidence-completeness status;
- changes overview and unresolved reviewer comments;
- AC checklist, every concern with evidence, and verdict.

Set the phase to the **report-rendered checkpoint** only after all sections are visible. A summary
or verdict alone is not a completed report.

### 6. Reverify after rendering

Before recording completion or offering approve/comment/request-changes, call:

```bash
~/.agents/skills/review-pr/scripts/gh-pr-snapshot.py 'owner/repo#123' \
  --expected-head REVIEWED_HEAD --expected-base REVIEWED_BASE \
  --expected-state-key REVIEWED_STATE_KEY --verify-only \
  --timeout REMAINING_SECONDS
```

Anything except `complete` makes the rendered report stale. Do not mark it complete and do not
offer GitHub approval, comment, or request-changes submission. Enter the stale flow.

### 7. Mark locally reviewed

Treat local completion as an idempotent transaction keyed by `workKey`:

1. Before collector marking, create or replace the matching pending record in
   `verified-unmarked` state with the complete result and set the in-flight phase likewise. If
   pending capacity is unavailable, do not mark.
2. Run the local state reducer:

   ```bash
   ~/.agents/skills/pr-status/scripts/gh-pr-review-requests.py \
     --state-json 'PRIOR_STATE_JSON' --mark-reviewed 'WORK_KEY'
   ```

3. Retain its returned collector state, add `workKey` to `completedWorkKeys`, change the pending
   record to `fresh`, and clear in-flight state. Adding the same key is idempotent. Do not change
   `reviewAttempts` here; the attempt was charged before analysis.

This order makes interruption recovery safe. A `verified-unmarked` record is always reverified,
then the idempotent mark command may be repeated before completing the same keyed transaction. A
collector state that already names the same `handledWorkKey` is success, not another completion.
Never mark or add a completed key for a failed, partial, stale, malformed, or interrupted report.
The reducer changes only supplied session state; it does not write GitHub.

### 8. Ask for disposition

Ask for disposition only after local completion. Use `AskUserQuestion` with one single-select
question and these four choices:

- **Keep private (Recommended)** — resolve the pending disposition with no message or GitHub action.
- **Prepare GitHub draft** — proceed to the draft-type question below; this does not submit.
- **Prepare Slack draft** — render a paste-ready summary; this does not send.
- **Defer** — retain the pending disposition for a later tick without rerunning the review.

A custom answer may refine draft wording but is not permission to send. When the answer returns,
reverify the immutable head/base/state before applying any choice; a question may have remained
open while the PR changed. On a revision/state mismatch, ignore the selected action, change the
record to `stale`, and enter the stale flow. An unavailable or failed verifier also blocks the
choice but retains `fresh` state for bounded retry. This recheck is mandatory before exposing
GitHub review kinds.

A verified Keep private removes the pending record. A verified Defer changes it to `deferred` and
allows the next queued PR to proceed if time and budget remain.

#### GitHub draft

After that fresh verification, ask a second single-select question with **Approve**, **Comment**,
and **Request changes**. Generate concise text grounded only in the rendered review; show the exact
repository, PR, review kind, and body. Save the immutable target, selected kind, exact body, and later shown quoted-heredoc command
in `github-draft` state. Then ask:

- **Keep draft (Recommended)** — no external action.
- **Verify for submission** — run the immutable verifier again; this is not submission permission.

If verification succeeds, show the exact target/kind/body again and ask a final question with
**Submit now** and **Keep draft (Recommended)**. Only **Submit now** authorizes submission. When the
Submit now answer returns, reverify the immutable head/base/state once more because the final
question may have remained open. On anything except `complete`, do not send and enter the stale or
bounded retry flow. On success, immediately run the following command without another tool call or
content change:

```bash
gh pr review PR_NUMBER --repo OWNER/REPO REVIEW_KIND_FLAG --body-file - <<'UNIQUE_REVIEW_BODY'
EXACT_SHOWN_BODY
UNIQUE_REVIEW_BODY
```

Map `REVIEW_KIND_FLAG` to exactly one of `--approve`, `--comment`, or `--request-changes`. Before the
final prompt, choose and show a quoted high-entropy heredoc delimiter absent from the body; include
the final newline in the shown draft. Quoting the delimiter disables shell interpolation, and
`--body-file -` preserves the shown body as one value. After post-answer verification, execute that
exact already-shown command without rebuilding it. No other answer may submit. Keep draft retains `github-draft` without automatic re-prompting. A successful submission
removes the pending record; a failed attempt retains it as `github-draft`. Stop the watcher after
either bounded submission result.

#### Slack draft

Render a paste-ready terse summary with PR URL, reviewed head, verdict, key evidence, and requested
next step, then retain it in `slack-draft`. Do not infer a destination. This watcher deliberately
has no Slack send tool or Skill permission and never sends. Default to **Keep draft (Recommended)**
and name the separate configured Slack workflow, if one exists, as the only handoff. That later
workflow must show the exact destination and text and obtain its own **Send now** confirmation
immediately before sending; this watcher supplies no send authorization.

### 9. Handle stale reports

Label the report stale with expected and observed state. Do not offer GitHub
approve/comment/request-changes choices. For a review that became stale before local completion,
do not call `--mark-reviewed` or add its key. For an already marked pending report that became
stale while its question was open, keep the old reviewed-head key as historical completion but
change the pending record to `stale`; the new head has a different work identity and is not
complete. Never attempt to unmark collector state.

Ask one single-select question:

- **Rerun current head (Recommended)** — retire the old pending record while preserving its
  historical completed key, then, if deadline and budget allow, collect with `--recheck`, select
  only this qualified PR, and repeat the serial flow against its new exact head. This removes the
  same-PR gate and keeps `disposition owner/repo#123` unambiguous. If it is a draft, render that it
  still waits and do not invoke `/review-pr`.
- **Keep private** — remove the stale pending record; the new head remains unreviewed.
- **Defer** — retain it in `stale` state without automatically prompting again.

A stale rerun consumes another premium attempt and adds a completion only for the new `workKey`,
after its complete report is rendered, verified, and marked. The old and new immutable-head
identities are never conflated.

### 10. Complete and pace

Never call a scheduler while an `AskUserQuestion` is open. End visible tick output with exactly one:

```text
next-tick: {hot|warm|cold} (~{N}s) — {reason}
```

- hot (~180s): actionable direct work remains and time/budget allow;
- warm (~600s): partial/failure retry, deferred disposition, stale rerun, or interrupted work;
- cold (1200 → 1500 → 1800s): complete no-change ticks, increasing the quiet streak.

Reset the quiet streak on hot/warm work. In adaptive Pi ticks, call `action: complete` with
`outcome: continue` and `delaySeconds: N`; fixed mode omits the delay. Use `outcome: stop` after the
deadline, review budget exhaustion after the current complete result and disposition finish,
third consecutive failure, external send attempt, or explicit stop/handoff. A no-change poll
remains concise and never asks a question.
