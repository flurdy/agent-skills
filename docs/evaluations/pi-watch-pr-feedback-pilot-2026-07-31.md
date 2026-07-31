# Pi `watch-pr-feedback` pilot — 2026-07-31

## Scope

Validate the protocol-v1 scheduling boundary, read-only multi-repository tick, bounded session
state, duplicate suppression, reset behavior, and attended acknowledgment for
`watch-pr-feedback` without changing a repository or GitHub.

## Environment

- Pi 0.82.1
- model: `openai-codex/gpt-5.6-sol:minimal`
- extension: reviewed local `ai-tools/pi/watch-loop`
- skill: reviewed local `skills/watch-pr-feedback/SKILL.md`
- local timezone: BST (`+01:00`)
- guarded fixture: `/tmp/skills-y0s.2-uat/`

The fixture exposed two open PRs in separate repositories through a fake read-only `gh` command:

- `acme/widgets#42`: one actionable inline request, one resolved thread, one approval, and one bot
  status comment. Its diff and test change already handled the request.
- `acme/gadgets#7`: one human question about a timeout change whose requirement remained
  uncertain.

The fake command wrote a sentinel and failed if it observed a GitHub mutation form. The fixture
working tree was checked after the run.

## Evidence

### Protocol start and completion

`/watch-pr-feedback 1m 23` produced this protocol-v1 start:

```yaml
label: PR feedback
mode: fixed
initialDelaySeconds: 60
intervalSeconds: 60
missedCompletionPolicy: retry
stopAt: 2026-07-31T23:00:00+01:00
```

Generation 1 completed with the matching watch ID, `outcome: continue`, and no adaptive delay.
The visible dashboard preceded completion.

### First read-only tick

The first tick made one normalized inventory call for each repository and rendered both candidates
in one bounded queue with repository/PR, author/source, feedback type, lifecycle, validation
outcome, evidence, confidence, and recommended response.

- `acme/widgets#42` → `false positive/already handled`, high confidence, citing the `None` guard,
  regression test, and passing CI.
- `acme/gadgets#7` → `question needing an answer`, medium confidence, citing the diff, stated
  fail-fast intent, missing slow-client requirement, and passing CI.

The resolved thread, approval, and bot status report were counted under suppressed updates. No
question was asked in default read-only mode.

### Duplicate, reset, and attended behavior

A second manual tick in the same session returned:

```text
Decision queue: No new actionable feedback.
```

It retained five identities and incremented the quiet streak without revalidating or prompting.
After `/watch-pr-feedback reset`, an attended tick treated the same records as a fresh baseline and
asked exactly one grouped question with:

1. `Acknowledge (Recommended)`
2. `Recheck next tick`
3. `Stop watcher`

No `agent_settled` event occurred while the question was open. Selecting acknowledgment left zero
pending attended items.

### Safety and boundedness

- GitHub mutation sentinel: absent
- fixture working tree after run: clean
- compactions: 0
- default-mode questions: 0
- identities retained: 5 of 500
- decision rows: 2 of 20
- all GitHub calls: search, GraphQL/REST reads, PR metadata, and PR diffs only

The full summary and event/raw captures remain outside the repository:

- `/tmp/skills-y0s.2-uat/summary.json`
- `/tmp/skills-y0s.2-uat/events.jsonl`
- `/tmp/skills-y0s.2-uat/tui.raw`
- `/tmp/skills-y0s.2-uat/gh.log`

## Additional coverage

`make test-watch-pr-feedback` statically enforces the no-change/new/edit/lifecycle comparison
contract, validation outcomes, partial-fetch handling, three-failure bound, reset/recheck/restart
semantics, multi-repository grouping, read-only versus attended behavior, and Pi/Claude scheduling
branches. The shared inventory's fixture suite supplies edited-comment, resolution/outdating,
pagination, partial-failure, self-reply, stable-deduplication, and source classification coverage.

A real grouped read-only GitHub inventory call against the three open
`flurdy/letterbox-recipient` PRs also returned `partial: false`, no errors, and zero feedback
records. No deployment, publication, reply, resolution, checkout, or repository mutation was
needed for this pilot.
