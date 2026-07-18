# Automated skill-effectiveness pilot results

This is a directional paired pilot, not a universal quality threshold. Each result file
contains the raw model output, command, timing, and deterministic grader checks. Literal
text checks are mechanical diagnostics; interpret them only alongside the blinded review.

| Scenario | Split | Skill | Baseline | With skill | Invalid | Interpretation |
|---|---|---|---:|---:|---:|---|
| diagnose-calibration | calibration | skills/diagnose-bug | 3/3 | 2/3 | 0 | literal-check regression; inspect blind review |
| diagnose-holdout | holdout | skills/diagnose-bug | 3/3 | 3/3 | 0 | equal literal-check outcomes; no benefit claim |
| simplify-calibration | calibration | skills/simplify-solution | 3/3 | 3/3 | 0 | equal literal-check outcomes; no benefit claim |
| simplify-holdout | holdout | skills/simplify-solution | 0/3 | 2/3 | 0 | literal-check treatment delta; inspect blind review |

## Validity notes

- Raw run statuses: {'failed': 5, 'passed': 19}.
- A grader failure, empty output, timeout, or non-zero Pi exit is `invalid`, never a pass.
- Equal outcomes are reported as non-discriminating rather than evidence that either arm is better.
- Calibration scenarios are for fixture/grader checks; hold-out scenarios are the evidence used for the maintain/no-maintain decision.
