# Skill-effectiveness pilot

This is a deliberately small, directional evaluation of whether selected shared skills
change outcomes relative to the same bare-agent task. It is not a gate for every skill
change and does not adopt Bigpowers' fixed score threshold.

## Design

- **Runtime:** Pi in noninteractive mode, with a model passed explicitly to the runner.
- **Skills:** `implement-solution` and `diagnose-bug`. Earlier recorded runs retain the former `simplify-solution` name.
- **Scenarios:** one calibration and one held-out scenario for each skill.
- **Matrix:** three repetitions for every scenario in baseline and with-skill conditions
  (24 agent sessions total).
- **Control:** baseline uses `--no-skills`; treatment uses the same options and prompt,
  plus exactly one explicit `--skill` path.
- **Cell setup:** each cell starts from a newly copied fixture as its working directory,
  with no session, context files, or extensions. The runner removes that workspace after
  recording its output.

### What the runner does and does not confine

The per-cell working directory gives **reproducibility, not containment**. Each cell runs
`pi` with `bash` enabled and no sandbox, so a command the model emits executes as the
invoking user with that user's full filesystem and credential access — the copied
workspace is where the agent starts, not a boundary it is held inside. Pi documents this
directly: project trust "is not a sandbox and it does not restrict what the model can ask
tools to do", and Pi ships no built-in sandbox or tool-permission prompt.

Two consequences worth stating plainly:

- `--approve` in the runner's command grants **project trust** — it loads project-local
  settings for the run. It is not tool auto-approval, because Pi has no tool prompt to
  bypass in the first place.
- The 24 cells run unattended. Anyone extending this beyond the pinned in-repo scenarios —
  new fixtures, prompts from elsewhere, an untrusted repository — should run the whole
  `pi` process inside a container or VM, which is Pi's own guidance for unattended
  automation.

`bash` stays in `--tools` deliberately: the diagnosis scenarios may run a reproduction,
and the tool set is part of the pinned matrix that earlier recorded runs are comparable
against. Changing it changes what is being measured.
- **Grading:** deterministic output checks are frozen in
  [`tests/fixtures/skill-pilot/scenarios.json`](../tests/fixtures/skill-pilot/scenarios.json).
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

Raw cell records are written to ignored `.artifacts/skill-effectiveness-pilot/runs/` and
include the command, model, timing, stdout, stderr, exit status, and per-check grader
outcome. The generated summary is `.artifacts/skill-effectiveness-pilot/results.md`.
These outputs are local and disposable by default; retaining a run as durable evidence
requires a separate documentation-retention decision.

## Interpretation

Inspect raw paired outputs before drawing a conclusion. A small pilot can expose obvious
mechanical flaws or directional differences, but it cannot establish a stable effect
size. Document model/runtime configuration, invalid runs, and any observed variation;
then decide whether maintaining a broader harness is justified.
