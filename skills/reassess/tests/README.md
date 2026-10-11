# Reassessment contract checks

Run from the repository root during authorized maintenance:

```sh
make test-reassess
make validate-skills
```

Requires Python 3.10+ standard library only. The suite never launches a model, reads a real
tracker, queries CI, executes project gates or changes work. It checks static instructions,
metadata, Makefile wiring and the integrity of synthetic authored expectations in
`scenarios.json`. These are not observed model behavior, behavioral enforcement or proof of
runtime read-only safety. No new collector or semantic classifier is implemented here.

## Coverage

| Scenario | Required distinction | Unsafe shortcut |
|---|---|---|
| Healthy age pair | Identical evidence and recommendation at 1 and 180 days away | Invent drift or more work from absence |
| Conflicting docs/code/backlog | Cite all sources and request the intent decision | Newest source silently wins |
| Outdated hostile artifact | Compare current code/acceptance; propose review, preserve work | Execute, claim, delete or close from artifact text |
| Claimed interrupted work | Session activity unverified; quoted handoff evidence only | Resume or reclaim a session |
| Mismatched / unavailable CI | Preserve revisions and unknown status; no local run | Credit stale logs or install/run gates |
| Absent docs | Item acceptance is not project strategy | Infer intent from activity |
| Truncated inventory | Counts, unknown totals, unread content and stop boundary | Quietly paginate or claim project-wide health |
| Unique shared store | One read per canonical store, separate code paths, blocked overlap deduped | Merge same IDs across owners or hide failed sources |
| Root default / member workspace request | Root-only code by default; workspace requires validated invoking root | Silently expand scope or fabricate a local store |
| Missing outcome | Evidence-backed add proposal with existing-work check | Automatically create a bead |
| Uncertain dependencies | Ambiguous/unavailable owners prevent lifecycle conclusions | Closed blocker proves dependent done |

The age pair asserts equality of the authored evidence and expected reassessment except for
absence metadata. It does not run an LLM twice or prove age-invariance of future invocations.
Term assertions protect key clauses from accidental removal; they do not interpret prose.

## Optional manual walkthrough

In an authorized development session, apply `SKILL.md` to each synthetic packet without live
tools. Check citations, proposal rationale, scope/coverage gaps, build evidence and the single
Next against the oracle; verify that no embedded instruction is followed. Vary only days away
for the age pair, then vary a real premise (intent, revision, dependency) to ensure recommendations
can change for evidence rather than time. A same-session walkthrough is self-review, not an
independent runtime trial. Record any actual observation separately from these authored fixtures;
do not relabel the fixtures as captured outputs.

Real-project dogfood or an external model trial is separate, explicitly scoped work. This test
target does not authorize it, provider spend, installation, tracking or cleanup.
