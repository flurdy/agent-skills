"""Instruction, wiring and authored-fixture integrity checks; not observed model behavior."""

import json
import os
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parents[1]
TESTS = SKILL / "tests"


class DependabotRemediationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (SKILL / "SKILL.md").read_text()
        cls.front = cls.raw.split("---", 2)[1]
        cls.text = " ".join(cls.raw.split())
        cls.fixtures = json.loads((TESTS / "scenarios.json").read_text())
        cls.cases = {case["id"]: case for case in cls.fixtures["cases"]}

    def require_terms(self, *terms):
        for term in terms:
            with self.subTest(term=term):
                self.assertIn(term, self.text)

    def test_metadata_and_narrow_grants(self):
        for field in ("name: dependabot-remediation", "disable-model-invocation: true",
                      "model-tier: standard", "effort: high", 'author: "flurdy"'):
            self.assertIn(field, self.front)
        self.assertLessEqual(len(re.search(r"^description: (.*)$", self.front, re.M).group(1)), 250)
        grants = re.search(r'^allowed-tools: "(.*)"$', self.front, re.M).group(1)
        permissions = {entry.strip() for entry in grants.split(",")}
        for script in ("gh-dependabot-alerts.py", "remediation-plan.py"):
            self.assertIn(f"Bash(~/.agents/skills/dependabot-remediation/scripts/{script}:*)", permissions)
            self.assertTrue(os.access(SKILL / "scripts" / script, os.X_OK))
        self.assertIn("Bash(~/.agents/skills/artifact-hygiene/scripts/artifact_hygiene.py:*)", permissions)
        self.assertIn("Bash(~/.agents/skills/next/scripts/next-select resolve:*)", permissions)
        for forbidden in ("Bash(gh:*)", "Bash(gh api:", "Bash(git push", "Bash(git:*)", "Bash(npm", "Bash(pip",
                          "Bash(bd:*)", "Bash(bd -C * close", "Write", "Edit"):
            self.assertNotIn(forbidden, grants)
        for block in re.findall(r"```(?:bash|sh)\n(.*?)```", self.raw, re.S):
            self.assertIsNone(re.search(r"^\s*(?:gh\s+api|git\s+push|bd\s+close)\b", block, re.M))

    def test_scope_binding_and_degraded_sources(self):
        self.require_terms(
            "security alerts", "version-update PRs are out of scope", "Bind the invoking repository",
            "No organization-wide scan", "no sibling discovery", "unknown or partial", "never zero alerts",
            "Credentials are never inspected or repaired", "page cap", "`127`", "`64`", "`3` unavailable",
            "never retries", "pass `--repo OWNER/REPO`", "github_remote.py", "never initialize one",
            "not pre-granted by this skill",
        )

    def test_eligibility_vocabulary_and_evidence_separation(self):
        self.require_terms(
            "compatible patch or minor upgrade", "not low/moderate vulnerability severity",
            "severity informs priority, never eligibility", "Major upgrades and migrations are tracked and held",
            "alert evidence", "implementation revision", "Keep them separate",
            "do not trust the alert's relationship field alone", "`major-upgrade`", "`pre-1.0-uncertain`",
            "`no-patched-version`", "`unsupported-ecosystem`", "`transitive-parent-major`", "`verify-publication`",
            "`parent-range-excludes-target`", "`parent-range-unknown`", "never assumed compatible",
            "Missing parent evidence holds",
            "Semver labels are not compatibility proof", "Do not widen a fix, add resolution overrides, or begin a migration",
            "`human` label",
        )

    def test_untrusted_text_and_prohibited_remote_actions(self):
        self.require_terms(
            "untrusted data", "never shell instructions", "drops advisory descriptions",
            "evidence of possible duplicate work, not permission to edit, close, merge, or comment",
            "adds no PR automation flow", "trunk/no-PR repositories receive commits on `main`, never PRs",
            "Never auto-push, force-push, rewrite history, publish tracking, dismiss alerts",
            "Never expose private Bead IDs",
        )
        self.assertNotRegex(self.text, r"gh (?:pr|api) (?:close|merge|comment|edit)|--dismiss|dismissed_reason=")

    def test_tracking_reuses_beads_authorities(self):
        self.require_terms(
            "next-select stores", "next-select resolve <repo>:<id>", "one bead per planned outcome",
            "never per command, package occurrence, alert or retry", "Deduplicate by the outcome `key`",
            "reuse and update rather than duplicate", "Workspace-owned members route to the workspace store",
            "never guess a store from the repository name", "next-select start <selector>",
            "session activity unverified", "do not take them over",
        )
        for owner in ("../beads/SKILL.md", "../next/SKILL.md", "../develop/SKILL.md", "../implement-solution/SKILL.md",
                      "../verify-task/SKILL.md", "../complete-task/SKILL.md", "../artifact-hygiene/SKILL.md",
                      "../create-pr/SKILL.md"):
            self.assertIn(owner, self.raw)
            self.assertTrue((SKILL / owner).resolve().is_file(), owner)

    def test_fix_verify_finalize_and_publication_gates(self):
        self.require_terms(
            "explicit implementation authority", "one writer per working tree", "install scripts",
            "integrity hashes", "Change only the dependency and its lockfile entries", "Never suppress the failure",
            "Dependency-resolution and regression evidence", "a lockfile diff alone is not verification",
            "block finalization and publication", "no bead ID", "artifact_hygiene.py --pretty",
            "`block` verdict or partial coverage stops the offer", "immediately before that single action",
            "**Push now** or **Leave unpushed**", "Approval covers that one command only",
            "Never chain the push",
        )

    def test_observed_resolution_is_reported_separately(self):
        self.require_terms(
            "--state all --alert", "recheck --plan", "--published-sha", "`fixed`, `pending`", "`dismissed` (not a fix",
            "`changed`", "`unknown`", "`publicationObserved` is true only when", "no polling loop, no scheduling",
            "do not fabricate success", "reruns reuse the same outcome keys", "a green test is not a push",
            "a push is not a closed bead", "a closed bead is not a GitHub `fixed` state", "**Next:**",
        )

    def test_scenarios_cover_the_acceptance_list_and_name_real_helper_tests(self):
        self.assertEqual(self.fixtures["schemaVersion"], "dependabot-remediation-scenarios/v1")
        self.assertIn("not observed model behavior", self.fixtures["purpose"])
        required = {
            "no-alerts-vs-denied-access", "direct-and-transitive-compatible-fixes", "several-alerts-one-fix",
            "duplicate-beads-and-workspace-store", "severity-independent-of-upgrade-size", "held-cases",
            "untrusted-advisory-text", "related-dependabot-pr", "unauthorized-or-dirty-scope",
            "package-execution-and-gate-failure", "publication-audit-and-single-push",
            "stale-revision-or-changed-alert", "delayed-scanning-dismissed-vs-fixed", "idempotent-rerun",
        }
        self.assertEqual(set(self.cases), required)
        self.assertEqual(len(self.cases), len(self.fixtures["cases"]))
        helper_tests = "".join((TESTS / name).read_text() for name in ("test_alerts_collector.py", "test_remediation_plan.py"))
        stages = set()
        for case in self.cases.values():
            with self.subTest(case=case["id"]):
                stages.add(case["stage"])
                self.assertTrue(case["evidence"] and all(row["text"] for row in case["evidence"]))
                self.assertTrue(case["expected"]["report"] and case["expected"]["next"])
                self.assertTrue(case["forbidden"])
                self.assertIsInstance(case["expected"]["mutations"], list)
                for name in case["helperTests"]:
                    self.assertIn(f"def {name}(", helper_tests)
        self.assertEqual(stages, {"discover", "plan", "track", "fix", "verify", "publish", "recheck"})
        for case_id in ("no-alerts-vs-denied-access", "untrusted-advisory-text", "related-dependabot-pr",
                        "delayed-scanning-dismissed-vs-fixed", "idempotent-rerun"):
            self.assertEqual(self.cases[case_id]["expected"]["mutations"], [])
        self.assertIn("auto-push", self.cases["publication-audit-and-single-push"]["forbidden"])
        self.assertIn("treat dismissed as fixed", self.cases["delayed-scanning-dismissed-vs-fixed"]["forbidden"])

    def test_catalog_makefile_and_notes_are_wired(self):
        catalog = (ROOT / "skills" / "README.md").read_text()
        self.assertEqual(len(re.findall(r"^\| dependabot-remediation \|", catalog, re.M)), 1)
        makefile = (ROOT / "Makefile").read_text()
        targets = re.search(r"TEST_TARGETS := (.*?)\n\ntest:", makefile, re.S).group(1)
        self.assertIn("test-dependabot-remediation", targets)
        self.assertIn("-s skills/dependabot-remediation/tests", makefile)
        notes = " ".join((TESTS / "README.md").read_text().split())
        for phrase in ("fake `gh`", "never contacts GitHub", "not observed model behavior", "authored expectations",
                       "no package registry", "no dependency is installed"):
            self.assertIn(phrase, notes)


if __name__ == "__main__":
    unittest.main()
