# Pi PR-feedback action gates pilot — 2026-07-31

## Scope

Validate that `reply-comments` keeps push, reply publication, and inline-thread resolution as three
separate attended actions; re-fetches normalized feedback before mutations; routes inline and
top-level responses to different endpoints; and prevents duplicate or forceful behavior.

## Environment

- Pi 0.82.1
- model: `openai-codex/gpt-5.6-sol:minimal`
- skill: reviewed local `skills/reply-comments/SKILL.md` v1.2.0
- guarded fixture: `/tmp/skills-y0s.3-uat/`
- selected PR: `acme/widgets#42`
- selected identities: `inline:C1`, `conversation:I2`

The fixture contained a clean local branch one verified commit ahead of its simulated PR head. A
fake `git` accepted only the confirmed push and delegated every read to the real binary. A fake
`gh` served normalized feedback and recorded reply/resolution calls without contacting GitHub. It
updated its response after each action so the next inventory re-fetch observed the published reply
or resolved thread.

## Evidence

### Separate confirmations

Pi asked three distinct questions in order:

1. `Push commit (Recommended)` / `Not now` / `Stop`
2. `Post selected replies (Recommended)` / `Edit drafts` / `Skip replies` / `Stop`
3. `Resolve selected threads (Recommended)` / `Leave open` / `Stop`

No `agent_settled` event occurred while any question was open. Each mutation timestamp was later
than its matching answer event; no prior selection or earlier answer was reused as permission.

### Visible guarded actions

The guarded actions occurred in this order:

1. branch push of `fix/feedback`;
2. inline response to
   `repos/acme/widgets/pulls/42/comments/101/replies`;
3. top-level response to `repos/acme/widgets/issues/42/comments`;
4. GraphQL resolution of thread `T1`.

No force option was present. The skill fetched the normalized inventory four times: before remote
gates, immediately before replies, before the resolution preview, and after its confirmation.
The inline re-fetch observed the self reply before resolution.

### Final per-item summary

The final table mapped both stable identities through the whole workflow:

- `inline:C1`: confirmed defect → verified local commit → pushed SHA → inline reply ID `102` →
  thread `T1` resolved.
- `conversation:I2`: validated question → same visible commit → top-level comment ID `202` →
  resolution not applicable.

The fixture working tree remained clean and no compaction occurred.

## Additional coverage

`make test-pr-feedback-actions` enforces:

- selection before validation and local action;
- validation outcomes and the security/architecture/scope/uncertainty return-to-user boundary;
- happy/sad/edge verification and local-commit-only ownership in `review-comments`;
- independent push/reply/resolution questions;
- changed/resolved/outdated/self race handling and bounded idempotency state;
- human, AI/bot, inline, top-level, review-summary, CI, approval, noise, and false-positive policies;
- exact inline, top-level conversation, and GraphQL resolution helper endpoints;
- helper arity failures and absence of force-push instructions.

`make test-pr-feedback` retains the nine normalized-inventory fixtures, including edited records,
resolution/outdating, self replies, pagination, partial failure, and stable deduplication.

Full temporary evidence remains outside the repository:

- `/tmp/skills-y0s.3-uat/summary.json`
- `/tmp/skills-y0s.3-uat/events.jsonl`
- `/tmp/skills-y0s.3-uat/mutations.jsonl`
- `/tmp/skills-y0s.3-uat/gh.jsonl`
- `/tmp/skills-y0s.3-uat/tui.raw`
