#!/usr/bin/env python3
"""Focused regression tests for the bounded skill-effectiveness pilot runner."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


RUNNER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run-skill-pilot.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("run_skill_pilot", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load skill-pilot runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


class RunSkillPilotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = RUNNER.load_scenarios()[0]

    def test_known_good_output_passes(self) -> None:
        output = "Reuse render_user_badge and add a conditional for is_new."
        graded = RUNNER.grade_output(output, 0, self.scenario)
        self.assertEqual("passed", graded["status"])

    def test_known_bad_output_fails(self) -> None:
        graded = RUNNER.grade_output("Add a new service.", 0, self.scenario)
        self.assertEqual("failed", graded["status"])

    def test_failed_agent_execution_is_invalid_not_pass(self) -> None:
        output = "render_user_badge is_new conditional existing"
        graded = RUNNER.grade_output(output, 1, self.scenario)
        self.assertEqual("invalid", graded["status"])

    def test_timed_out_agent_execution_is_invalid_not_pass(self) -> None:
        output = "render_user_badge is_new conditional existing"
        graded = RUNNER.grade_output(output, 124, self.scenario)
        self.assertEqual("invalid", graded["status"])

    def test_run_cell_executes_both_conditions(self) -> None:
        completed = RUNNER.subprocess.CompletedProcess([], 0, "render_user_badge is_new conditional reuse", "")
        with patch.object(RUNNER.subprocess, "run", return_value=completed) as execute:
            baseline = RUNNER.run_cell(self.scenario, "baseline", 1, "openai-codex/gpt-5.6-luna")
            treatment = RUNNER.run_cell(self.scenario, "with_skill", 1, "openai-codex/gpt-5.6-luna")

        self.assertEqual("passed", baseline["grader"]["status"])
        self.assertEqual("passed", treatment["grader"]["status"])
        self.assertEqual(2, execute.call_count)
        baseline_command = execute.call_args_list[0].args[0]
        treatment_command = execute.call_args_list[1].args[0]
        self.assertNotIn("--skill", baseline_command)
        self.assertIn("--skill", treatment_command)

    def test_treatment_differs_only_by_explicit_skill_load(self) -> None:
        baseline = RUNNER.pi_command(self.scenario, "baseline", "openai-codex/gpt-5.6-luna", Path("."))
        treatment = RUNNER.pi_command(self.scenario, "with_skill", "openai-codex/gpt-5.6-luna", Path("."))
        treatment_without_skill = treatment.copy()
        index = treatment_without_skill.index("--skill")
        del treatment_without_skill[index : index + 2]
        self.assertEqual(baseline, treatment_without_skill)

    def test_report_does_not_claim_benefit_for_equal_results(self) -> None:
        run = {
            "scenario": "example",
            "split": "holdout",
            "skill": "skills/example",
            "condition": "baseline",
            "grader": {"status": "passed"},
        }
        baseline = run
        treatment = {**run, "condition": "with_skill"}
        report = RUNNER.report_markdown([baseline, treatment])
        self.assertIn("equal literal-check outcomes; no benefit claim", report)

    def test_saved_result_round_trips_raw_output(self) -> None:
        result = {
            "scenario": "example",
            "condition": "baseline",
            "repetition": 1,
            "stdout": "raw output",
        }
        with tempfile.TemporaryDirectory() as temporary:
            target = RUNNER.save_result(Path(temporary), result)
            self.assertEqual(result, json.loads(target.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
