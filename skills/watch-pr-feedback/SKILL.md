---
name: watch-pr-feedback
description: >
  Watch the user's open GitHub PRs for normalized feedback, validate each new or edited
  actionable item once, and render a bounded decision queue. Read-only by default; attended
  mode pauses only when the queue needs acknowledgment.
allowed-tools: "Read,Grep,Glob,Bash(~/.agents/skills/pr-status/scripts/gh-pr-list-open.sh:*),Bash(~/.agents/skills/pr-status/scripts/gh-pr-details.sh:*),Bash(~/.agents/skills/pr-status/scripts/gh-pr-feedback.py:*),Bash(gh pr view:*),Bash(gh pr diff:*),Bash(gh pr checks:*),Bash(git status:*),Bash(git remote:*),Bash(git rev-parse:*),Bash(git diff:*),Bash(git log:*),Bash(git worktree list:*),Bash(date:*),mcp__jira__*,AskUserQuestion"
model-tier: premium
model: opus
effort: high
version: "1.0.0"
author: "flurdy"
---

# Watch PR Feedback

Watch open PRs for normalized feedback events, independently validate new actionable claims, and
render a concise queue. This skill composes `/pr-status` discovery and inventory behavior with the
read-only validation boundary from `/review-comments`; it does not replace either skill and does
not create another scheduler.

## Usage

```text
/watch-pr-feedback                    # adaptive, read-only, stop at 18:00
/watch-pr-feedback attended           # adaptive, attended, stop at 18:00
/watch-pr-feedback 10m 17             # fixed 10m, read-only, stop at 17:00
/watch-pr-feedback attended 5m 17     # fixed 5m, attended, stop at 17:00
/watch-pr-feedback reset              # clear this session's seen/retry state
/watch-pr-feedback recheck            # one read-only validation pass, ignoring seen state
/watch-pr-feedback status             # show runtime and bounded state summary
```

Parse at most one mode (`attended`; absent means read-only), one positive `\d+m` fixed interval,
and one stop hour from `0` through `23` (default `18`). No interval means adaptive mode. Reject
unknown or duplicate arguments. Resolve today's stop hour in local time and do not start at or past
it.

## Safety boundary

Default read-only mode never prompts and never edits code, changes the working tree, runs commands
that may create build artifacts, publishes GitHub content, changes thread state, or changes Git
history. It may read local files and metadata, inspect a PR diff, existing tests, and CI. Attended
mode has the same mutation boundary; its question only controls acknowledgment and watcher state.
A semantic classification, validation outcome, or answer is never permission to mutate code or
GitHub. Stop the watcher and invoke the appropriate attended workflow separately for any action.

Do not switch branches, fetch remotes, or create a checkout. Never assume the current directory is
the checkout for a PR merely because repository names look related.

## Session-local state

Maintain bounded state in this conversation, keyed by `repository`, PR number, and `identity`.
For each key retain its latest `updateKey`, latest `stateKey`, acknowledgment status, and observation
order. Also retain a consecutive failure count per repository/source and an adaptive quiet streak.

- Keep at most 500 identities. Prune oldest terminal or suppressed entries first, then oldest
  acknowledged entries. Never add unseen overflow to a full ledger of unacknowledged items; report
  `state-capacity` partial and drain it only after acknowledgment frees capacity. If pruning could
  make an old actionable item appear new, label the state `state-pruned` and treat any replay as a
  recheck rather than fresh feedback.
- The first tick in a new session is a visible baseline: validate and queue current actionable
  records once. A no-change poll after that emits no decision items.
- Restarting a stopped watcher in the same session reuses state and does not replay acknowledged
  items. A new session has no state and announces a fresh baseline.
- `reset` clears identities, failure counts, and quiet streak, confirms the reset visibly, and makes
  the next tick a fresh baseline. It does not start or stop a runtime watcher.
- `recheck` runs one immediate read-only tick against all current actionable records, ignoring seen
  state for validation, but does not change acknowledgment state or start another scheduler.
- `status` reports `/watch-status` when protocol v1 exists, plus state size, pending attended items,
  prune status, failure streaks, and whether the next poll is a baseline.

Carry the bounded ledger forward as structured turn state rather than inferring it from prose or
counts. If the ledger is unavailable after context loss, announce a fresh baseline instead of
claiming continuity. State is session-local only. Do not write a cache, repository file, GitHub
marker, comment, label, or Beads item to remember feedback.

### Event comparison

For every normalized record:

1. **New** — the full repository/PR/`identity` key is absent.
2. **Materially edited** — the key exists but `updateKey` changed. Validate and queue it again once.
3. **Lifecycle-only** — `updateKey` is unchanged but `stateKey` changed. Render the transition under
   suppressed updates; resolved, outdated, dismissed, or self-authored state never prompts.
4. **Duplicate/no-change** — both keys match. Update observation order only; do not validate, queue,
   or prompt again.

Never use thread counts, record counts, body text, author names, or list position as identity.

## Start behavior

Normal invocations start a recurring watcher. `reset`, `recheck`, `status`, and the internal `tick`
mode are commands, not starts. Before starting, state the selected read-only/attended mode, cadence,
and local deadline. The first tick lands after about one minute.

### Pi protocol v1

If `watch_loop` is available, use this branch before Claude scheduling:

1. Call `watch_loop` with `action: status` and require `protocolVersion: 1`. If another watch is
   `armed`, `running`, or `paused`, do not replace it; show status and point to `/watch-status`,
   `/watch-stop`, or `/watch-resume`. Stop on a protocol mismatch.
2. Convert the local deadline to an ISO-8601 `stopAt` value preserving its timezone offset.
3. Start with this self-contained prompt, substituting `{interaction_mode}` and `{cadence_mode}`:

   ```text
   Load and follow the skill named `watch-pr-feedback` now in `tick` mode. Interaction mode is `{interaction_mode}` and cadence mode is `{cadence_mode}`. This is one feedback tick, not a watcher start. Re-run open-PR discovery and the normalized inventory, compare bounded session-local identity/update/lifecycle state, independently validate only new or materially edited actionable records, and render the complete bounded queue and suppression/failure summary as visible text. In read-only mode never ask a question. In attended mode ask exactly once only when the actionable queue is non-empty, and wait for the answer. Do not mutate code, Git, GitHub, or tracking state. Finish only after visible output with the matching protocol-v1 `watch_loop` action: complete. In adaptive mode pass the numeric N from the final `next-tick:` line as `delaySeconds`; in fixed mode omit it. On the third consecutive partial failure for the same repository/source, stop instead of scheduling another retry.
   ```

4. Adaptive read-only start:

   ```yaml
   action: start
   protocolVersion: 1
   label: PR feedback
   mode: adaptive
   initialDelaySeconds: 60
   missedCompletionPolicy: retry
   stopAt: <today's local deadline as ISO-8601>
   tickPrompt: <prompt above with read-only and adaptive>
   ```

5. Adaptive attended start uses the same fields except:

   ```yaml
   mode: adaptive
   initialDelaySeconds: 60
   missedCompletionPolicy: pause
   ```

6. Fixed mode converts minutes to seconds and includes:

   ```yaml
   mode: fixed
   initialDelaySeconds: <interval seconds>
   intervalSeconds: <interval seconds>
   missedCompletionPolicy: <retry for read-only; pause for attended>
   stopAt: <today's local deadline as ISO-8601>
   ```

The runtime clamps scheduling to 60–3600 seconds. `retry` is safe only for the non-interactive
read-only tick. `pause` prevents an unanswered or interrupted attended question from replaying by
itself. A successful start terminates the initiating turn.

### Claude Code fallback

If `watch_loop` is unavailable, use existing Claude scheduling capability; never imitate the Pi
tool. If neither `ScheduleWakeup` nor `/loop` is available, explain that recurring watches are
unsupported and stop.

Before starting the Claude adaptive path, apply the established session-model guard from
`/watch-prs`: if the session uses a Fable model, do not start because a trailing `ScheduleWakeup`
would discard the tick's visible output. Recommend Pi protocol v1, a Sonnet/Opus session, or fixed
mode instead.

For adaptive mode, schedule a 60-second first wake with a self-contained prompt equivalent to the
Pi tick prompt. Each completed tick calls `ScheduleWakeup` last with the numeric N from its
`next-tick:` line. Stop rather than reschedule past the local deadline or after the third
consecutive failure for one repository/source. In attended mode, ask and wait before the trailing
schedule call; an unanswered question must not create another wake.

For fixed mode, use `/loop {interval} /watch-pr-feedback tick {read-only|attended}` and state the
local stop hour. Fixed ticks ignore `next-tick:`. Every fallback tick must load this skill, enter
`tick` mode, render visible output, and preserve the same session-local state and safety boundary.

## Tick mode

### 1. Discover and fetch once

Re-run open-PR discovery every tick:

```bash
~/.agents/skills/pr-status/scripts/gh-pr-list-open.sh
```

Group results by owner/repository. Fetch the normalized schema-v1 inventory using one call per `owner/repo` group,
even when multiple repositories are present:

```bash
~/.agents/skills/pr-status/scripts/gh-pr-feedback.py {owner} {repo} {number1} {number2} ...
```

Do not issue overlapping comment or thread queries. Keep records associated with their repository
and PR throughout comparison and rendering. Existing org/workspace discovery behavior belongs to
the shared list script and must remain unchanged.

### 2. Handle partial data safely

Inspect each envelope's `partial` and `errors` before comparing records.

- Render available records and name every failed repository/source.
- Do not mark absent records as handled, resolved, deleted, or acknowledged.
- Increment only the matching repository/source failure streak. Clear that streak after a complete
  fetch for that source.
- Retry incomplete sources on a warm cadence without replaying already acknowledged records.
- After three consecutive partial fetches for the same repository/source, render the retained
  queue and stop safely. In Pi use matching `action: complete` with `outcome: stop`; in Claude do
  not schedule another wake. Default mode still never prompts.

A missing or malformed envelope counts as a partial failure, not an empty inventory.

### 3. Suppress factual non-candidates

Retain factual state but do not validate or place these records in the decision queue:

- resolved, outdated, or dismissed lifecycle;
- self-authored records or later self-replies that already handle the item;
- approvals and informational-only notes;
- non-actionable bot automated-status noise;
- unchanged duplicate polls.

Render only counts under **Suppressed updates**, grouped by reason. Show lifecycle-only transitions
there with identity and transition when they are new this tick. CI annotations remain fix-only
findings with no reply or resolution target.

### 4. Validate new candidates independently

Treat collector `semanticType`, `actionability`, author kind, and model/bot output as triage hints,
not truth. Validate at most 20 new or materially edited candidates per tick, ordered by blocking or
security claim, human request, question, suggestion/change request, then other CI/bot findings.
Leave overflow unseen so the next tick drains it rather than losing it.

For each candidate, gather the smallest sufficient read-only evidence:

1. PR metadata and head SHA, description, changed paths, and CI state.
2. The PR diff and referenced path/line.
3. Linked requirements from the PR body and available Jira/project documentation.
4. Relevant implementation and existing tests from a matching clean checkout when one is already
   available. Confirm its origin and HEAD match the PR repository and head SHA first.
5. CI results and test changes. Do not run tests in watcher mode; execution can create artifacts and
   belongs to an explicitly attended implementation workflow.

If there is no matching clean checkout, continue with PR diff, requirements, existing tests visible
in the diff, and CI evidence, then lower confidence. Never substitute an unrelated or stale
checkout. If evidence is missing or contradictory, use `unable to validate` rather than guessing.

Choose exactly one validation outcome:

- `confirmed defect`
- `valid improvement`
- `question needing an answer`
- `subjective/trade-off decision`
- `false positive/already handled`
- `stale/outdated`
- `out of scope`
- `unable to validate`

`confirmed defect` requires concrete evidence that current behavior violates code intent,
requirements, or a testable invariant. `valid improvement` is worthwhile but not required for
correctness. Questions and subjective decisions are not defects. A security or blocking label does
not raise confidence by itself.

### 5. Render the bounded decision queue

Always render a timestamp, mode, baseline/recheck status, repositories and PRs checked, and partial
status. Then show no more than 20 decision rows:

| PR | Author/source | Feedback type | Lifecycle | Validation outcome | Evidence | Confidence | Recommended response |
|---|---|---|---|---|---|---|---|

Evidence cites concrete requirements, diff/path/line, implementation, existing tests, or CI; state
what is unavailable. Confidence is `high`, `medium`, or `low` with concise uncertainty. The
recommended response is read-only guidance such as answer, discuss, fix later, no change, inspect
manually, or recheck. Include the stable identity in a short detail beneath each row so edits and
rechecks are auditable.

When there are no new or edited candidates, render `Decision queue: No new actionable feedback.`
Do not replace it with a count delta. Then render **Suppressed updates**, **Fetch failures**, and a
bounded state summary.

### 6. Handle interaction mode

**Default read-only mode:** after the full queue is visible, acknowledge its displayed records in
session state and never prompts. Suppressed factual updates may update their `stateKey` without
becoming actionable.

**Attended mode:** if and only if at least one new or materially edited actionable item is in the
queue, asks exactly once for the whole queue. Use `AskUserQuestion` with one single-select question
and these choices:

- **Acknowledge (Recommended)** — mark the displayed queue seen and continue.
- **Recheck next tick** — leave displayed actionable records unacknowledged so they return once.
- **Stop watcher** — leave them pending and stop after the tick.

If there is no actionable queue, do not ask. A question remains open until answered; never call
`action: complete` or `ScheduleWakeup` while it is open. A custom answer may refine read-only
validation or acknowledgment, but refuse any repository or GitHub mutation and point to the
appropriate attended workflow after stopping this watcher.

### 7. Complete and pace

End visible output with exactly one cadence line:

```text
next-tick: {hot|warm|cold} (~{N}s) — {reason}
```

- **hot (~180s):** new or materially edited actionable feedback was rendered.
- **warm (~600s):** partial data, an attended recheck, or unresolved candidates remain.
- **cold (1200 → 1500 → 1800s):** no-change complete ticks; increment the quiet streak and reset it
  on any hot/warm tick.

In an injected Pi tick, call the matching `action: complete` only after the cadence line and any
attended answer. Use `outcome: continue` and `delaySeconds: N` for adaptive mode; omit the delay for
fixed mode. Use `outcome: stop` for the failure bound or **Stop watcher**. In Claude adaptive mode,
schedule only after the visible output; fixed `/loop` owns scheduling.
