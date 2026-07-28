# Project-brief synthesis fixture validation

**Bead:** `agents-esz.3`

This is a bounded contract regression suite for `/project-brief`, not a benchmark or a
claim that every model will render identical output.

## Coverage

The frozen evidence/output pairs under
`skills/project-brief/tests/fixtures/synthesis/` cover:

- coherent requirement-to-delivery linkage with release explicitly unassessed;
- missing project intent containing hostile source instructions;
- Jira, Beads, PR, and PRD contradictions;
- blocker-first `Next` ordering over reconciliation and communication actions;
- truncated topology, document, and Beads evidence;
- successful CI evidence whose SHA does not match the current PR head.

`test_evaluation.py` derives the expected verdict and complete action order from raw
fixture facts such as active decision blockers, Jira-Done/open-work contradictions, missing
intent, truncation, and exact-head CI mismatches. It also checks required collector sections,
evidenced header/scope values, explicit intent-to-work-to-PR links, confidence-row semantics,
per-action citations and allowed verbs, recorded communication channels, truncation caps/counts,
hostile-action leakage, synthetic completion claims, and five-row/action bounds.

Run both the collector and synthesis checks with:

```bash
make test-project-brief
```

## Interpretation boundary

The scenarios, expected invariants, and frozen outputs were authored in the same change.
They prove that the documented contract and checked examples are internally consistent;
they do not measure model quality, establish a treatment effect, or guarantee future
runtime behavior. A model can still vary wording, omit evidence, or mis-rank an action.
The final epic slice therefore retains real workspace dogfood and human review as a
separate acceptance gate.

When recapturing an output for a new model or contract revision, preserve the evidence
packet, record the runtime/model externally, inspect the full response, and update an
expectation only when the contract itself intentionally changed. Never weaken an
invariant merely to turn a model response green.
