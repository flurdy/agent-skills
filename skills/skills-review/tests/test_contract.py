"""Offline instruction/fixture contracts; no semantic classifier or provider calls."""

import json
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parents[1]


class SkillsReviewContractTests(unittest.TestCase):
    def text(self):
        return " ".join((SKILL / "SKILL.md").read_text().split())

    def test_explicit_read_only_discovery(self):
        raw = (SKILL / "SKILL.md").read_text()
        front = raw.split("---", 2)[1]
        for field in ("name: skills-review", "disable-model-invocation: true", "model-tier: standard", "effort: high"):
            self.assertIn(field, front)
        self.assertNotRegex(front, r"(?m)^model:")
        grants = re.search(r'^allowed-tools: "(.*)"$', front, re.M).group(1)
        self.assertEqual(grants, "Read,Grep,Glob,AskUserQuestion,Skill(triage)")
        for text in ("/skills-review", "/skill:skills-review", "manual", "not a delivery gate", "untrusted data", "never execute"):
            self.assertIn(text, self.text())

    def test_scope_identity_and_honest_coverage(self):
        text = self.text()
        for term in (
            "physical source checkout", "ask for the source", "every top-level entry",
            "canonical SKILL.md path", "raw entries", "unique skills", "outside",
            "private", "third-party", "30,000 characters", "full or partial",
            "unread", "stop at the budget", "not a defect", "No changes needed",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)
        self.assertIn("not proof of aliases", text)
        self.assertIn("Do not infer collection-wide health", text)

    def test_validator_reuse_and_cost_distinction(self):
        text = self.text()
        for term in (
            "scripts/validate-skills.py", '--root "$SOURCE"', "Python 3.10+",
            "trusted", "unavailable", "different root", "not semantic validation",
            "unknown code or recreate", "catalog", "loaded bodies", "hypotheses",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)
        self.assertNotIn("make check", text)

    def test_recommendations_and_separate_tracking_authority(self):
        text = self.text()
        for term in (
            "trim", "fix", "extend", "split", "merge", "retire", "confidence",
            "smallest action", "safety", "consent", "age", "usage data",
            "demonstrated need", "selected", "approves actionable patterns", "triage", "owning store",
            "duplicate", "one pattern", "switch-directory", "stop",
            "No automatic", "model trials", "scheduler", "telemetry",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)
        self.assertNotRegex(text, r"bd (create|update|close)|next-select start|claude -p|codex exec")
        self.assertIn("Return control", text)

    def test_fixture_integrity_not_behavior(self):
        data = json.loads((SKILL / "tests/scenarios.json").read_text())
        self.assertEqual(data["schemaVersion"], "skills-review-scenarios/v1")
        self.assertIn("not observed model behavior", data["purpose"])
        required = {
            "healthy", "prescription-versus-safety", "cross-skill-conflict",
            "missing-evidence", "partial-coverage", "extension-need", "existing-work",
            "unapproved-mutation", "aliases-and-boundaries", "ambiguous-source",
            "validator-failed", "validator-unavailable", "wrong-validator-root",
        }
        cases = data["cases"]
        self.assertEqual(len(cases), len(required))
        self.assertEqual({case["id"] for case in cases}, required)
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertTrue(case["request"])
                self.assertTrue(case["evidence"])
                self.assertEqual(len(case["evidence"]), len({e["id"] for e in case["evidence"]}))
                self.assertTrue(all(e["text"] for e in case["evidence"]))
                self.assertTrue(case["expected"]["observations"])
                self.assertTrue(case["expected"]["next"])
                self.assertEqual(case["permittedMutations"], [])
                for finding in case["expected"]["findings"]:
                    self.assertIn(finding["kind"], {"trim", "fix", "extend", "split", "merge", "retire"})
                    self.assertIn(finding["confidence"], {"high", "medium", "uncertain"})
                    self.assertTrue(finding["smallestAction"])
                    self.assertTrue(finding["evidence"])
                    self.assertLessEqual(set(finding["evidence"]), {e["id"] for e in case["evidence"]})

    def test_documented_evidence_and_test_wiring(self):
        notes = " ".join((SKILL / "tests/README.md").read_text().split())
        self.assertIn("authored expectations", notes)
        self.assertIn("not observed", notes)
        self.assertIn("same-session", notes)
        self.assertIn("never launches", notes)
        makefile = (ROOT / "Makefile").read_text()
        targets = re.search(r"TEST_TARGETS := (.*?)\n\ntest:", makefile, re.S).group(1)
        self.assertIn("test-skills-review", targets)
        self.assertIn("-s skills/skills-review/tests", makefile)


if __name__ == "__main__":
    unittest.main()
