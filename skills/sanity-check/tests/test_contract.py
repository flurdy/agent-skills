"""Offline instruction and report-shape contracts, not agent-behavior tests."""

import json
import re
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
ROOT = SKILL_DIR.parents[1]
VERDICTS = {"CONTINUE", "REFOCUS", "STOP", "INSUFFICIENT CONTEXT"}


def check_report(report, evidence_ids):
    """Validate fixture/report shape only; do not infer a verdict from prose."""
    lines = [line for line in report.splitlines() if line.strip()]
    if len(lines) > 12 or len(report.split()) > 200:
        raise ValueError("report budget exceeded")
    modes = {
        "Self-check (not independent)",
        "Self-check (not independent; peer unavailable)",
        "Peer review (bounded packet)",
    }
    if not lines or lines[0] not in {f"**Mode:** {mode}" for mode in modes}:
        raise ValueError("missing or misleading assessment label")
    if len(lines) < 4 or lines[1] not in {f"**Verdict:** {v}" for v in VERDICTS}:
        raise ValueError("missing verdict")
    if not lines[2].startswith("**Goal:** "):
        raise ValueError("missing goal")
    observations = lines[3:-1]
    if len(observations) > 3:
        raise ValueError("too many observations")
    for line in observations:
        match = re.fullmatch(r"- \[([^\]]+)\] .+", line)
        if not match or not set(match[1].split(", ")).issubset(evidence_ids):
            raise ValueError("unsupported observation")
    if not lines[-1].startswith("**Next:** ") or report.count("**Next:**") != 1:
        raise ValueError("one next step required")


class SanityCheckContractTests(unittest.TestCase):
    def text(self):
        path = SKILL_DIR / "SKILL.md"
        self.assertTrue(path.is_file(), "missing canonical sanity-check skill")
        return path.read_text()

    def cases(self):
        path = SKILL_DIR / "tests/scenarios.json"
        self.assertTrue(path.is_file(), "missing manual behavioral fixtures")
        data = json.loads(path.read_text())
        self.assertEqual(data["schemaVersion"], "sanity-check-scenarios/v1")
        self.assertIn("not execution traces", data["purpose"])
        return data["cases"]

    def test_read_only_surface_and_explicit_discovery(self):
        text = self.text()
        front = text.split("---", 2)[1]
        self.assertIn("name: sanity-check", front)
        self.assertIn("disable-model-invocation: true", front)
        self.assertIn("model-tier: standard", front)
        self.assertIn("effort: high", front)
        self.assertNotRegex(front, r"(?m)^model:")
        grants = re.search(r'^allowed-tools: "(.*)"$', front, re.M).group(1)
        self.assertEqual(grants, "Read,AskUserQuestion,Skill(second-opinion)")
        for required in ("/sanity-check", "/skill:sanity-check", "unnamed", "without a bead"):
            self.assertIn(required, text)
        for forbidden in ("Bash(", "Write", "Edit", "Skill(develop)", "Skill(verify-task)"):
            self.assertNotIn(forbidden, grants)

    def test_concrete_evidence_and_tool_budgets(self):
        text = self.text()
        for required in (
            "20",
            "12,000",
            "two",
            "100 lines",
            "6,000",
            "six",
            "one delegation",
            "underlying",
            "no further evidence",
            "stop at the limit",
            "not a sandbox",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_goal_evidence_and_ownership_boundaries(self):
        text = self.text()
        for required in (
            "latest user-agreed outcome",
            "approved scope changes",
            "No tracker reads",
            "all in-progress",
            "compaction",
            "hidden reasoning",
            "missing context",
            "elapsed time",
            "tool count",
            "unmapped",
            "not automatically drift",
            "necessary investigation",
            "required verification",
            "not completion approval",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)
        self.assertNotRegex(text, r"bd (list|show|search)|next-select start")

    def test_peer_reuses_owner_and_cannot_weaken_its_safeguards(self):
        text = self.text()
        for required in (
            "second-opinion",
            "ask --agent peer",
            "--timeout 1",
            "provider independence",
            "consent",
            "packet-only",
            "tools disabled",
            "cannot honor",
            "unavailable",
            "do not skip",
            "no retry",
            "no panel",
            "no recursive",
            "Self-check",
            "failure alone does not change",
            "repository safety",
            "No transcript files",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)
        self.assertNotRegex(text, r"claude -p|codex exec|gemini -p|review-panel\.sh")
        self.assertIn("Redact reports", text)

    def test_invocation_stops_and_refuses_mutations(self):
        text = self.text()
        for required in (
            "no source/config/tracker changes",
            "no test execution",
            "no installs",
            "no work claims",
            "no session renaming",
            "no peer-session messaging",
            "no steering",
            "Return control to the user",
            "do not resume",
            "Treat repository text",
            "untrusted data",
            "No packet files",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_output_template_and_decision_rules(self):
        text = self.text()
        self.assertIn("200 words", text)
        self.assertIn("12 nonempty lines", text)
        self.assertIn("at most three", text)
        templates = re.findall(r"```markdown\n(.*?)```", text, re.S)
        self.assertEqual(len(templates), 1)
        rendered = templates[0].replace("{mode}", "Self-check (not independent)")
        rendered = rendered.replace("{verdict}", "CONTINUE").replace("{goal}", "bounded goal")
        rendered = rendered.replace("{evidence}", "U1").replace(
            "{observation}", "Observed outcome."
        )
        rendered = rendered.replace(
            "{next step or stopping condition}", "Await the next authorized step."
        )
        check_report(rendered, {"U1"})
        for verdict in VERDICTS:
            self.assertIn(f"`{verdict}`", text)

    def test_fixture_coverage_and_example_output_bounds(self):
        cases = self.cases()
        required = {
            "on-track-unnamed",
            "necessary-investigation",
            "necessary-verification",
            "repeated-no-progress",
            "unapproved-growth",
            "approved-goal-change",
            "outcome-met",
            "missing-goal",
            "compacted-missing-context",
            "compacted-confirmed-goal",
            "ambiguous-owner",
            "peer-unavailable",
            "mutation-request",
            "hostile-output",
        }
        self.assertEqual({case["id"] for case in cases}, required)
        self.assertEqual(len(cases), len(required))
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertIn(case["mode"], ("self", "peer"))
                self.assertLessEqual(len(case["visible"]), 20)
                self.assertLessEqual(len(json.dumps(case["visible"])), 12000)
                ids = [event["id"] for event in case["visible"]]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertTrue(all(event["text"] for event in case["visible"]))
                self.assertIn(case["expectedVerdict"], VERDICTS)
                check_report(case["exampleReport"], set(ids))
                self.assertIn(f"**Verdict:** {case['expectedVerdict']}", case["exampleReport"])
                self.assertEqual(case["permittedActions"], [])
                self.assertTrue(case["rationale"])

    def test_report_checker_rejects_invalid_outputs(self):
        valid = "**Mode:** Self-check (not independent)\n**Verdict:** CONTINUE\n**Goal:** Goal\n- [U1] Evidence.\n**Next:** Wait."
        check_report(valid, {"U1"})
        invalid = (
            valid.replace("CONTINUE", "PASS"),
            valid.replace("[U1]", "[invented]"),
            valid.replace("**Mode:**", "**Independent review:**"),
            valid.replace("Self-check (not independent)", "Independent verification passed"),
            valid.replace("- [U1] Evidence.", "\n".join(["- [U1] Evidence."] * 4)),
            valid.replace("Evidence.", "word " * 201),
            valid + "\n**Next:** Also do another task.",
            valid.replace("**Goal:**", "**Task list:**"),
        )
        for report in invalid:
            with self.subTest(report=report[:100]), self.assertRaises(ValueError):
                check_report(report, {"U1"})

    def test_catalog_docs_and_test_gate(self):
        catalog = (ROOT / "skills/README.md").read_text()
        self.assertEqual(len(re.findall(r"^\| sanity-check \|", catalog, re.M)), 1)
        self.assertIn("/skill:sanity-check", (ROOT / "README.md").read_text())
        makefile = (ROOT / "Makefile").read_text()
        self.assertIn(
            "test-sanity-check", makefile.split("TEST_TARGETS :=", 1)[1].split("test:", 1)[0]
        )
        self.assertIn("-s skills/sanity-check/tests", makefile)
        self.assertIn("not model-behavior", self.text())


if __name__ == "__main__":
    unittest.main()
