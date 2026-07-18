# Skill-effectiveness pilot

This is a deliberately small, directional evaluation of whether selected shared skills
change outcomes relative to the same bare-agent task. It is not a gate for every skill
change and does not adopt Bigpowers' fixed score threshold.

## Design

- **Runtime:** Pi in noninteractive mode, with a model passed explicitly to the runner.
- **Skills:** `simplify-solution` and `diagnose-bug`.
- **Scenarios:** one calibration and one held-out scenario for each skill.
- **Matrix:** three repetitions for every scenario in baseline and with-skill conditions
  (24 isolated agent sessions total).
- **Control:** baseline uses `--no-skills`; treatment uses the same options and prompt,
  plus exactly one explicit `--skill` path.
- **Isolation:** each cell runs in a newly copied fixture with no session, context files,
  or extensions. The runner removes that workspace after recording its output.
- **Grading:** deterministic output checks are frozen in
  [`tests/fixtures/skill-pilot/scenarios.json`](../../tests/fixtures/skill-pilot/scenarios.json).
  A non-zero Pi exit or empty output is `invalid`, never a pass.

Calibration scenarios exercise fixture and grader mechanics. Hold-out scenarios are
kept separate from the maintain/no-maintain conclusion. Equal arm outcomes are
reported as non-discriminating; no universal score threshold is applied.

## Run

First verify the runner without invoking a model:

```bash
python3 -m unittest tests/test_run_skill_pilot.py
python3 scripts/run-skill-pilot.py --dry-run
```

Run the full, pinned 24-cell matrix:

```bash
python3 scripts/run-skill-pilot.py --model openai-codex/gpt-5.6-luna
```

Raw cell records are written to `docs/evaluations/skill-effectiveness-pilot-runs/` and
include the command, model, timing, stdout, stderr, exit status, and per-check grader
outcome. The generated summary is
[`skill-effectiveness-pilot-results.md`](skill-effectiveness-pilot-results.md).

## Interpretation

Inspect raw paired outputs before drawing a conclusion. A small pilot can expose obvious
mechanical flaws or directional differences, but it cannot establish a stable effect
size. Document model/runtime configuration, invalid runs, and any observed variation;
then decide whether maintaining a broader harness is justified.
