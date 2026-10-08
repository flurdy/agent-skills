"""Offline prose and fixture contracts; these do not execute an agent."""

import json
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parents[1]


class PairProgrammingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (SKILL / "SKILL.md").read_text()
        cls.front = cls.text.split("---", 2)[1]
        cls.fixtures = json.loads((SKILL / "tests/scenarios.json").read_text())

    def assert_phrases(self, *phrases):
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

    def test_metadata_and_opt_in(self):
        self.assertIn("name: pair-programming", self.front)
        self.assertIn("model-tier: standard", self.front)
        self.assertIn("effort: high", self.front)
        self.assertNotRegex(self.front, r"(?m)^(model|context|allowed-tools):")
        self.assert_phrases(
            "Activate only for an explicit pairing request",
            "Loading this file for review is not activation",
            "/pair-programming",
            "/skill:pair-programming",
            "The human does not have to type",
            "Discussion-only intent stays read-only",
            "activation alone grants no",
        )

    def test_step_boundary_and_continuation(self):
        self.assert_phrases(
            "one reviewable outcome plus proportionate verification",
            "agree on the first step before editing",
            "without asking for the same permission again",
            "without approval per line or tool",
            "expected test failures within scope",
            "the agreed step is the unit of completion",
            "return control\nto the user before starting another step",
            "even if the broader feature is authorized",
            "A progress message followed immediately by more implementation is not",
            "do not reconfirm it",
            "Reconcile a redirect with the new scope",
        )

    def test_workflow_and_safety_ownership(self):
        for owner in ("develop", "implement-solution", "diagnose-bug", "architect"):
            self.assertIn(f"../{owner}/SKILL.md", self.text)
        self.assert_phrases(
            "interaction layer, not an implementation specialist",
            "Continue an already-active specialist",
            "Do not add unrelated cleanup or launch delegation/review",
            "Required reviews and source, Git, security, privacy, billing, and production gates still apply",
            "Pause before a consequential unagreed decision",
            "Specialist recommendations do not silently become user agreement",
            "Warn immediately about security, privacy, or data-loss risks",
            "Stop that action",
        )

    def test_conversation_and_exit(self):
        self.assert_phrases(
            "no fixed intake questionnaire",
            "Answer direct questions directly",
            "Do not demand a prediction",
            "what the checks actually showed",
            "Do not claim the user learned something",
            "recover the current agreement rather than inventing it",
            "without inventing another step or a quiz",
            "Exit alone grants no new scope",
            "Do not keep imposing pairing checkpoints after exit",
        )

    def test_upstream_attribution(self):
        self.assertIn(
            "https://github.com/channingwalton/skills/tree/main/skills/pair-programming",
            self.text,
        )
        license_text = (SKILL / "LICENSE.upstream").read_text()
        for clause in (
            "MIT License",
            "Copyright (c) 2026 Channing Walton",
            "Permission is hereby granted, free of charge",
            "The above copyright notice and this permission notice shall be included",
            'THE SOFTWARE IS PROVIDED "AS IS"',
            "OUT OF OR IN CONNECTION WITH THE SOFTWARE",
        ):
            self.assertIn(clause, license_text)
        self.assert_phrases("Do not follow upstream installation instructions")

    def test_scenario_coverage_and_rule_references(self):
        self.assertEqual(self.fixtures["schemaVersion"], "pair-programming-scenarios/v1")
        self.assertIn("not execution traces", self.fixtures["purpose"])
        cases = self.fixtures["cases"]
        expected_ids = {
            "activation-only", "discussion-only", "bounded-loop-and-redirect",
            "routine-work-and-red-test", "consequential-decision", "direct-question",
            "specialist-boundary", "risk-before-action", "explicit-exit",
            "exit-without-authority", "tiny-task-close", "ordinary-request",
            "lost-agreement",
        }
        self.assertEqual({case["id"] for case in cases}, expected_ids)
        self.assertEqual(len(cases), len(expected_ids))
        headings = set(re.findall(r"^## (.+)$", self.text, re.M))
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertIn(case["rule"], headings)
                self.assertTrue(case["turns"])
                self.assertTrue(case["expected"])
                self.assertTrue(case["reject"])
                for turn in case["turns"] + case.get("continuation", []):
                    self.assertIn(
                        turn["role"], {"user", "assistant", "observation", "expected-assistant"}
                    )
                    self.assertTrue(turn["text"])
        loop = next(case for case in cases if case["id"] == "bounded-loop-and-redirect")
        self.assertEqual(
            [turn["role"] for turn in loop["turns"]],
            ["user", "assistant", "user", "observation"],
        )
        self.assertEqual(
            [turn["role"] for turn in loop["continuation"]],
            ["user", "expected-assistant", "user", "observation", "expected-assistant"],
        )

    def test_catalog_test_gate_and_evidence_limits(self):
        catalog = (ROOT / "skills/README.md").read_text()
        self.assertEqual(len(re.findall(r"^\| pair-programming \|", catalog, re.M)), 1)
        makefile = (ROOT / "Makefile").read_text()
        self.assertIn(
            "test-pair-programming",
            makefile.split("TEST_TARGETS :=", 1)[1].split("test:", 1)[0],
        )
        self.assertIn("-s skills/pair-programming/tests", makefile)
        readme = (SKILL / "tests/README.md").read_text()
        for limitation in ("not model-behavior", "authored", "same-session", "separately authorized"):
            self.assertIn(limitation, readme)


if __name__ == "__main__":
    unittest.main()
