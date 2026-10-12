# Peer-session evidence

Run `make test-peer-session` from the repository root (Python 3.10+, standard library
only). These offline instruction contracts check permissions, transport selection,
native binding and ping consent, message bounds, evidence wording, the preserved Orca
path and suite wiring. They do not call `ListAgents`, send messages, start Orca or
execute a model, so they are not live-delivery evidence.

## Manual native pilot

Needs Claude Code with cross-session messaging (v2.1.224+; v2.1.236+ in every session
for idle notices) and at least two disposable local sessions in one project. Every send,
pings included, keeps the skill's per-send approval.

1. From a third session, run `/peer-session tell <project> <status>`. Confirm self is
   excluded, nothing is guessed, and the numbered ping batch is approved before it is sent.
2. Choose one candidate and approve the final message. Confirm exactly one `SendMessage`,
   with no automatic resend or Orca fallback.
3. Run `/peer-session ask <project> <question>`. Confirm the reply's first line carries
   the request ID and that an idle notice alone is reported as response unverified.
4. Set one recipient's `crossSessionInbound` to `refuse`. Confirm the outcome is reported
   as refused or unverified and is never retried.
5. Repeat one Orca `ask` from Pi to confirm that path is unchanged.

Record the date, Claude Code and Orca versions, observed results and gaps in the owning
task. Static tests and same-session self-review never count as observed delivery.
