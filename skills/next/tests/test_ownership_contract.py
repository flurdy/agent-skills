"""Instruction-contract fixtures, not a runtime ownership cache or guard test."""
from pathlib import Path
import unittest

SKILLS = Path(__file__).resolve().parents[2]


class OwnershipContractTest(unittest.TestCase):
    def test_read_reuse_and_mutation_scenarios_are_explicit(self):
        baseline = (SKILLS / "beads" / "SKILL.md").read_text()
        scenarios = {
            "Same exact qualified target, unchanged context, more reads in one operation":
                "Reuse actual successful resolution; qualify reads with its directory",
            "Bare selector ambiguous across stores":
                "Stop; ask for an exact owner; no reusable proof",
            "Changed target selector": "Resolve again before reading or writing",
            "Changed repository/store identity or topology/declaration/redirect":
                "Invalidate; resolve again",
            "Changed originating cwd or session, or ended operation": "Invalidate; resolve again",
            "Later failed resolution, including unavailable":
                "Discard earlier success; no fallback writes",
            "Direct bd mutation after reads":
                "Fresh full resolution immediately before that mutation",
            "Helper start with its own resolver":
                "One internal full resolution; no duplicate caller check",
            "Stale or invented proof, later independent write or unrelated target":
                "No authority; obtain fresh full resolution",
        }
        for scenario, disposition in scenarios.items():
            with self.subTest(scenario=scenario):
                self.assertIn(f"| {scenario} | {disposition} |", baseline)
        self.assertIn("instruction-level boundary, not a runtime cache or receipt API", baseline)
        self.assertIn("Stricter repository rules, source/plan guards and sync approvals still apply", baseline)
        self.assertNotIn("Resolve ownership before every read", baseline)

    def test_consumers_share_the_baseline_without_duplicate_write_checks(self):
        for skill in ("next", "triage"):
            text = (SKILLS / skill / "SKILL.md").read_text()
            with self.subTest(skill=skill):
                self.assertIn("../beads/SKILL.md#ownership-proof-lifetime", text)
                self.assertIn("failed resolution", text)
                self.assertIn("caller", text)
                self.assertIn("independent write", text)
        triage = (SKILLS / "triage" / "SKILL.md").read_text()
        apply = triage.split("**R5.", 1)[1].split("### Rules", 1)[0]
        self.assertIn("before each direct", apply)
        self.assertIn("next-select resolve <selector>", apply)
        self.assertLess(apply.index("next-select resolve"), apply.index("bd -C <directory> update"))


if __name__ == "__main__":
    unittest.main()
