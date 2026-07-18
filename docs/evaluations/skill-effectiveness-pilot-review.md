# Skill-effectiveness pilot review

**Verdict:** do **not** promote this pilot into a general maintained harness yet.
Keep the runner and raw records as a reproducible experiment, but repeat with a
pre-validated semantic grader and a larger, independently authored hold-out set before
using results to change shared-skill policy.

## Execution record

- **Runtime:** Pi noninteractive mode with `openai-codex/gpt-5.6-luna` pinned for both
  arms.
- **Matrix:** 24 real sessions: two skills × calibration/hold-out scenarios × baseline/
  with-skill × three repetitions.
- **Period:** 2026-07-18T12:44:02Z–12:57:51Z; cumulative wall time 866.753 seconds
  (20.190–64.650 seconds per run).
- **Isolation:** each run used a copied fixture, `--no-session`, `--no-context-files`,
  and `--no-extensions`. Baselines used `--no-skills`; treatments had the identical
  command plus exactly one `--skill` path.
- **Raw evidence:** [`skill-effectiveness-pilot-runs/`](skill-effectiveness-pilot-runs/)
  contains all 24 commands, outputs, stderr, durations, exit codes, and grader records.
  Every run exited successfully; no result was marked `invalid`.

The runner's unit test verifies that baseline and treatment execute the same command
shape except for target-skill injection. The recorded commands and non-empty outputs
show that both modes actually ran in the 24-cell matrix.

## Automated grading result

The frozen literal-check summary is in
[`skill-effectiveness-pilot-results.md`](skill-effectiveness-pilot-results.md). It reports
19 passes and 5 failures, but those failures are **grader false negatives**, not task
failures:

- Four otherwise-correct `simplify-holdout` responses referred to `slug.py` and the
  correct `None`/blank-slug behavior without spelling the function name `slugify`.
- One otherwise-correct `diagnose-calibration` response used a `Finding` section rather
  than the literal phrase `root cause`.

The pilot preserves these raw outcomes rather than rewriting the frozen post-run scores.
They demonstrate that a keyword-only grader is too brittle for this advice/diagnosis
work and must not support a treatment-effect claim by itself.

## Condition-blind hold-out review

A condition-blind review shuffled the 12 hold-out responses and removed arm labels and
automated scores before assessment. Each response was assessed against this explicit
four-point rubric:

| Scenario kind | Required observations |
|---|---|
| `simplify-holdout` | Preserve `None → "untitled"`; reject blank/whitespace input; recommend a local readable change; give no-edit verification. |
| `diagnose-holdout` | Reproduce the zero/default discrepancy; locate `int(raw) or 30`; distinguish mechanism from unverified caller behavior; give a bounded safe next step without editing. |

All 12 blinded responses met their scenario rubric (4/4). Because every hold-out response
was semantically adequate, the qualitative outcome is **non-discriminating**: this small
sample provides no reliable evidence that loading either skill improves the selected
model's result.

## Limitations and decision

- Three repetitions and one hold-out per skill expose variance but cannot estimate a
  stable effect size.
- The fixture prompts and literal grader were authored in the same change as the runner;
  future hold-outs should be authored and validated independently before execution.
- The blind review was condition-blind but not independently staffed; it should be
  calibrated against a second reviewer before making any policy decision.
- Token/cost telemetry was not available from Pi's text output and is recorded as not
  observable rather than inferred.

**Decision:** retain this bounded pilot as evidence that isolation, raw-record capture,
and invalid-run handling work. Do not build a general benchmark framework or gate skill
changes until a second pilot has independently validated semantic grading and produces a
meaningful hold-out difference.
