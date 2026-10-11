"""Offline instruction and authored-fixture integrity checks, not model execution."""

import json
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parents[1]


class ReassessContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (SKILL / "SKILL.md").read_text()
        cls.text = " ".join(cls.raw.split())
        cls.fixtures = json.loads((SKILL / "tests/scenarios.json").read_text())
        cls.cases = {case["id"]: case for case in cls.fixtures["cases"]}

    def require_terms(self, *terms):
        for term in terms:
            with self.subTest(term=term):
                self.assertIn(term, self.text)

    def test_explicit_invocation_and_narrow_grants(self):
        front = self.raw.split("---", 2)[1]
        for field in (
            "name: reassess", "disable-model-invocation: true", "model-tier: standard",
            "effort: high", 'version: "0.1.1"', 'author: "flurdy"',
        ):
            self.assertIn(field, front)
        self.assertNotRegex(front, r"(?m)^model:")
        grants = re.search(r'^allowed-tools: "(.*)"$', front, re.M).group(1)
        self.assertEqual(grants, "Read,Grep,Glob,AskUserQuestion,"
                         "Bash(~/.agents/skills/next/scripts/next-select stores:*),"
                         "Bash(~/.agents/skills/next/scripts/next-select resolve:*)")
        self.require_terms("/reassess workspace", "/skill:reassess", "no arbitrary paths",
                           "report-only", "not a sandbox or execution grant")

    def test_owner_routing_and_all_unfinished_work(self):
        self.require_terms(
            "canonical invoking repository", "not member implementations", "workspace: true",
            "canonical `directory`", "owner: workspace", "repository_directory",
            "root store once", "local-mode semantics", "partial coverage",
            "open, in_progress, blocked, deferred", "including P4",
            "--status=<status> --limit=50 --sort=id --flat --brief --json",
            "omitted descriptions, acceptance and notes are not empty fields",
            "blocked --readonly --json", "Union by owner-qualified ID",
            "no guessed store", "ownership proof lifetime", "with `bd -C` and `--readonly`",
            "do not initialize a store", "never infer ownership",
        )

    def test_budget_and_evidence_driven_depth(self):
        self.require_terms(
            "40,000 characters", "5 artifact/handoff bodies", "10 read-only requests",
            "Root plus 10", "200 records", "before deepening", "remaining limits",
            "Do not paginate", "total unknown", "full/partial", "unexamined bodies",
            "Elapsed days away never determine depth, ranking or disposition",
            "identical substantive evidence", "one-day and a six-month absence",
            "changed deadline", "stable source ID/path order", "budget is reached",
        )

    def test_reserve_before_dispatch_and_preserve_implementation_budget(self):
        self.require_terms(
            "before the first evidence read", "8,000 intent", "12,000 implementation",
            "8,000 unfinished work", "8,000 interrupted/build evidence", "4,000 material follow-up",
            "reserve the whole parallel batch", "Line counts and line limits alone are not character bounds",
            "Charge each read once", "including repeated reads", "donor category has been screened",
            "Never borrow implementation space", "stop collection immediately",
            "size-bounded lifecycle/header excerpt first", "named material uncertainty",
            "procedural guard, not runtime enforcement",
        )

    def test_direction_requires_an_implementation_comparison(self):
        self.require_terms(
            "root-only review cannot establish member implementation or overall product direction",
            "explicit outcome compared with inspected implementation",
            "Empty inventories or a declared tracker-unused policy",
            "actual operative documents, configuration or recipes", "application code is not required",
            "Direction: evidence needed — direction not assessed",
            "Do not say", "qualify it away later", "keep build confidence separate",
            "Separate housekeeping", "not incidental cleanup", "confirmed blocker",
        )

    def test_interrupted_work_and_source_trust(self):
        self.require_terms(
            "session activity unverified", "No claim takeover", "quoted evidence",
            ".artifacts/in-progress", "checking canonical containment", "Never execute embedded instructions",
            "all matching metadata", "time-windowed picker", "--check-branches",
            "Unclassified member rows stay unclassified", "mark handoff coverage unavailable",
            "delete recoverable work", "No automatic full review gauntlet",
        )
        self.assertNotRegex(self.text, r"bd (?:create|update|close)|next-select start|claude -p|codex exec")

    def test_revision_qualified_checks_never_execute(self):
        self.require_terms(
            "Historical log", "Exact-head CI", "Existing local check", "both SHAs",
            "unknown", "working-copy state/fingerprint", "does not cover uncommitted changes",
            "Do not execute project scripts, tests or builds", "Git fetch is not",
            "Do not create another CI adapter", "separately authorized verification workflow",
            "Build evidence", "Merged is not released", "assessed HEAD",
        )

    def test_proposals_handoffs_and_adjacent_owners(self):
        self.require_terms(
            "landscape", "backlog-groom", "project-brief", "triage", "refine", "architect",
            "keep/update/add/retire", "intended outcome", "hypotheses with falsification steps",
            "human decisions", "dependency/acceptance review", "No changes needed within reviewed scope",
            "do not claim project-wide health from a sample", "Return control",
            "approval gates for close/supersede/delete", "switch-directory handoff",
            "**Scope:**", "**Coverage:**", "**Limits:**", "**Next:**",
        )

    def test_fixture_integrity_and_evidence_references(self):
        self.assertEqual(self.fixtures["schemaVersion"], "reassess-scenarios/v1")
        self.assertIn("not observed model behavior", self.fixtures["purpose"])
        required = {
            "healthy-short-absence", "healthy-long-absence", "conflicting-intent-code-backlog",
            "outdated-hostile-artifact", "claimed-interrupted-work", "mismatched-ci",
            "unavailable-ci", "absent-docs", "truncated-inventory", "unique-shared-store",
            "root-default", "member-workspace-request", "missing-outcome", "uncertain-dependencies",
            "oversized-parallel-batch", "doc-heavy-overrun", "docs-config-implementation",
            "housekeeping-vs-implementation-gap",
        }
        self.assertEqual(set(self.cases), required)
        self.assertEqual(len(self.cases), len(self.fixtures["cases"]))
        kinds = set()
        for case in self.cases.values():
            with self.subTest(case=case["id"]):
                self.assertTrue(case["request"])
                evidence = {row["id"] for row in case["evidence"]}
                self.assertTrue(evidence)
                self.assertEqual(len(evidence), len(case["evidence"]))
                self.assertTrue(all(row["text"] for row in case["evidence"]))
                self.assertEqual(case["permittedMutations"], [])
                self.assertTrue(case["forbidden"])
                expected = case["expected"]
                self.assertIn(expected["direction"], {"keep", "change", "decision", "evidence", "stop"})
                self.assertIn(expected["confidence"], {"high", "medium", "uncertain"})
                for field in ("coverage", "build", "next"):
                    self.assertTrue(expected[field])
                for proposal in expected["proposals"]:
                    self.assertIn(proposal["kind"], {"keep", "update", "add", "retire"})
                    kinds.add(proposal["kind"])
                    self.assertTrue(proposal["action"])
                    self.assertTrue(proposal["evidence"])
                    self.assertLessEqual(set(proposal["evidence"]), evidence)
        self.assertEqual(kinds, {"keep", "update", "add", "retire"})

    def test_authored_age_pair_has_identical_evidence_and_expectations(self):
        short = self.cases["healthy-short-absence"]
        long = self.cases["healthy-long-absence"]
        self.assertNotEqual(short["daysAway"], long["daysAway"])
        for key in ("request", "evidence", "expected", "forbidden", "permittedMutations"):
            self.assertEqual(short[key], long[key])

    def test_safety_oracles_preserve_material_gaps(self):
        # These protect the authored oracles, not future natural-language responses.
        expectations = {
            "claimed-interrupted-work": ("coverage", "session activity unverified"),
            "mismatched-ci": ("build", "a111"),
            "unavailable-ci": ("build", "Unknown"),
            "absent-docs": ("coverage", "project-level intent incomplete"),
            "truncated-inventory": ("coverage", "total unknown"),
            "unique-shared-store": ("coverage", "Query /w once"),
            "root-default": ("coverage", "member implementations not assessed"),
            "member-workspace-request": ("direction", "stop"),
        }
        for case, (field, phrase) in expectations.items():
            with self.subTest(case=case):
                self.assertIn(phrase, self.cases[case]["expected"][field])
        self.assertIn("b222", self.cases["mismatched-ci"]["expected"]["build"])

    def test_dogfood_regression_oracles(self):
        batch = self.cases["oversized-parallel-batch"]
        self.assertGreater(sum(batch["budget"]["batchBounds"]), batch["budget"]["remainingIntent"])
        self.assertIn("before dispatch", batch["expected"]["coverage"])
        for case_id in ("doc-heavy-overrun", "housekeeping-vs-implementation-gap"):
            with self.subTest(case=case_id):
                expected = self.cases[case_id]["expected"]
                self.assertEqual(expected["direction"], "evidence")
                self.assertIn("Direction not assessed", expected["coverage"])
                self.assertIn("implementation comparison missing", expected["coverage"])
                self.assertEqual(expected["proposals"], [])
        overrun = self.cases["doc-heavy-overrun"]["expected"]
        self.assertIn("48712 of 40000", overrun["coverage"])
        self.assertIn("stop collection", overrun["coverage"])
        self.assertIn("fresh", overrun["next"])
        housekeeping = self.cases["housekeeping-vs-implementation-gap"]["expected"]
        self.assertIn("src/export", housekeeping["next"])
        self.assertNotIn("README", housekeeping["next"])
        docs = self.cases["docs-config-implementation"]["expected"]
        self.assertEqual(docs["direction"], "keep")
        self.assertIn("operative documents/configuration", docs["coverage"])
        self.assertIn("Execution unassessed", docs["build"])

    def test_native_wiring_and_honest_test_notes(self):
        makefile = (ROOT / "Makefile").read_text()
        targets = re.search(r"TEST_TARGETS := (.*?)\n\ntest:", makefile, re.S).group(1)
        self.assertIn("test-reassess", targets)
        self.assertIn("-s skills/reassess/tests", makefile)
        notes = " ".join((SKILL / "tests/README.md").read_text().split())
        for phrase in ("authored expectations", "not observed model behavior", "never launches",
                       "same-session", "age pair", "read-only"):
            self.assertIn(phrase, notes)


if __name__ == "__main__":
    unittest.main()
