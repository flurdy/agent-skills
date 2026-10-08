---
name: pair-programming
description: "Opt-in conversational pairing when the user explicitly asks to pair: the agent writes authorized code in small agreed steps, discussing decisions and results throughout. Not for ordinary implementation requests."
model-tier: standard
effort: high
version: "1.0.0"
author: "flurdy"
---

# Pair Programming

Work as a pair: discuss the change together; the agent writes the authorized code.
The human does not have to type. Keep the connection between domain intent, code,
and evidence visible without turning the conversation into a lesson or examination.

## Activation and scope

Activate only for an explicit pairing request, such as “let's pair on this” or
“pair with me while you implement”, or invocation of this skill by name.
Claude Code: `/pair-programming`; Pi: `/skill:pair-programming`; other clients:
request the skill by name. Mentioning key pairs or asking an ordinary coding
question is not opting in. Loading this file for review is not activation.

Say briefly that you will write the code and pause between agreed steps to discuss
results. Pairing changes interaction, not authority: activation alone grants no
permission to edit, run commands, claim work, install anything, or publish changes.
Discussion-only intent stays read-only until the user explicitly requests implementation;
“sounds right” about an explanation is not that request.

Keep pairing active in the current session across skill handoffs until the user
explicitly exits. It is an interaction layer, not an implementation specialist or
an always-on gate. No extra orchestration, state files, or runtime dependencies are needed.

## Agree on a small step

Use what the user has already told you: the desired outcome, relevant code and domain
constraints, what must remain true, and any settled decisions. Read the relevant
repository evidence rather than guessing. Ask only about missing context that
materially changes the work; no fixed intake questionnaire.

Discuss meaningful alternatives in terms of behavior and trade-offs, and recommend
an approach with reasons. Answer direct questions directly. Do not demand a prediction,
quiz the user, or withhold an answer to test their understanding.

A step is one reviewable outcome plus proportionate verification, not one tool call
and not an entire multi-part feature disguised as a step. Propose that boundary
before starting. If the user already requested a concrete small implementation step,
acknowledge its scope and proceed without asking for the same permission again.
For a broad implementation request, agree on the first step before editing.

## Implement within the agreement

Use [develop](../develop/SKILL.md) before authorized coding, including a discussion-to-code
transition. Follow its routing to [implement-solution](../implement-solution/SKILL.md),
[diagnose-bug](../diagnose-bug/SKILL.md), or [architect](../architect/SKILL.md) as appropriate.
Continue an already-active specialist; do not reload coding entry points for every edit
or restart discovery at every discussion break.

Carry the current step boundary into those workflows. Finish the routine reads, edits,
local design details and checks needed for that step without approval per line or tool.
Investigate and fix expected test failures within scope; they are feedback, not automatic
reasons to hand the work back. Test proportionately using repository-native checks.
Do not add unrelated cleanup or launch delegation/review merely because pairing is active.
If separately authorized delegation is used, give it only the current agreed scope.
Required reviews and source, Git, security, privacy, billing, and production gates still apply;
a step agreement never replaces their separate approvals.

Pause before a consequential unagreed decision: changing public behavior, data/schema,
introducing a dependency, choosing between materially different domain rules, or expanding
the step. Explain the concrete choice and its consequences; offer a recommendation and
wait for the user's decision. Ordinary helper names or equivalent local code shapes do
not need a vote. Specialist recommendations do not silently become user agreement.

Warn immediately about security, privacy, or data-loss risks, before taking the risky
action. Stop that action and resolve the risk under the applicable safeguards; do not
let a dangerous mistake proceed for educational effect.

## Discuss the result before continuing

While pairing, the agreed step is the unit of completion for continuation purposes.
Continue through skill transitions and routine checks inside it; after it, return control
to the user before starting another step, even if the broader feature is authorized.
A progress message followed immediately by more implementation is not a discussion break.

Briefly explain what changed, what the checks actually showed (including failures or
missing evidence), and any important invariant, assumption, or trade-off established.
Show a focused diff or example when it helps. Invite a response about the next meaningful
step and wait; do not silently chain through the rest of the feature after one opening chat.
A reply agreeing to a clear next-step proposal is enough; do not reconfirm it.

The user can redirect, ask questions, or stop. Answer a question without treating it as
permission for the next step. Reconcile a redirect with the new scope before proceeding;
do not carry approval for the old direction into a materially different change.
If context is lost, recover the current agreement rather than inventing it. Preserve the
active pairing mode and agreed boundary in any otherwise-required handoff or summary.

If a tiny task is finished in one step, say so without inventing another step or a quiz.
At a natural end, close concisely with what was built and verified, the understanding or
decisions established, and what remains open. Do not claim the user learned something
that the conversation did not establish.

## Exit

“Stop pairing”, “exit pair-programming”, or an equivalent explicit request ends this
interaction mode. A request to finish autonomously is an explicit exit: acknowledge it
and return to normal workflow for already-authorized work. Exit alone grants no new scope
or permissions. Do not keep imposing pairing checkpoints after exit or persist the mode
into a new session without a fresh request or explicit resume instruction.

## Attribution and checks

Adapted from [Channing Walton's pair-programming skill](https://github.com/channingwalton/skills/tree/main/skills/pair-programming).
Its emphasis on shared understanding, invariants, alternatives, and bounded changes is
retained; its human-types default and prediction questions are not. The upstream MIT
copyright and permission notice are preserved in [LICENSE.upstream](LICENSE.upstream).
Do not follow upstream installation instructions as part of pairing.

Run `make test-pair-programming` from this repository for offline contract checks.
[Scenario review instructions](tests/README.md) distinguish static checks and authored
oracles from observed model behavior. These checks need Python 3.10+ (standard library);
the skill itself adds no executable helper or provider call.
