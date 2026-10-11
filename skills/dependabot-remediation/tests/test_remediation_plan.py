"""Deterministic planning and recheck fixtures; no model, tracker or network."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "remediation-plan.py"
SPEC = importlib.util.spec_from_file_location("remediation_plan", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
REPO = "acme/widgets"


def alert(number, package="lodash", patched="4.17.21", severity="high", ecosystem="npm",
          manifest="package.json", relationship="direct", state="open"):
    return {
        "identity": f"{REPO}#{number}", "number": number, "state": state, "severity": severity,
        "ecosystem": ecosystem, "package": package, "manifestPath": manifest, "scope": "runtime",
        "relationship": relationship, "vulnerableRange": None, "firstPatchedVersion": patched,
    }


def document(alerts, status="complete", head="deadbeef", **extra):
    return {
        "schemaVersion": "dependabot-alerts/v1", "repository": REPO, "status": status, "reason": None,
        "requested": [], "missing": [], "unavailable": [],
        "defaultBranch": {"name": "main", "headSha": head, "status": "complete", "reason": None},
        "alerts": alerts, **extra,
    }


def dependency(package="lodash", installed="4.17.20", ecosystem="npm", manifest="package.json", **extra):
    return {"ecosystem": ecosystem, "package": package, "manifestPath": manifest, "installedVersion": installed, **extra}


def local(*dependencies, dirty=False):
    return {"revision": "1111111", "dirty": dirty, "dependencies": list(dependencies)}


class PlanTests(unittest.TestCase):
    def outcome(self, alerts, *dependencies, **kwargs):
        plan = MODULE.build_plan(document(alerts, **kwargs), local(*dependencies))
        self.assertEqual(len(plan["outcomes"]), 1, plan)
        return plan["outcomes"][0]

    def test_direct_patch_upgrade_with_local_evidence_is_eligible(self):
        outcome = self.outcome([alert(1)], dependency())
        self.assertEqual(outcome["decision"], "eligible")
        self.assertEqual(outcome["upgrade"], {"from": "4.17.20", "to": "4.17.21", "kind": "patch"})
        self.assertEqual((outcome["severity"], outcome["priority"]), ("high", "P2"))
        self.assertEqual(outcome["alerts"], [f"{REPO}#1"])
        self.assertEqual(outcome["titleHint"], "Upgrade lodash to >= 4.17.21 (package.json)")

    def test_transitive_minor_upgrade_is_eligible_when_every_parent_range_allows_it(self):
        outcome = self.outcome([alert(2, patched="4.18.0", relationship="transitive")],
                               dependency(relationship="transitive", parentRanges=["^4.17.0"]))
        self.assertEqual((outcome["decision"], outcome["upgrade"]["kind"]), ("eligible", "minor"))

    def test_transitive_fix_outside_a_parent_range_is_held(self):
        # Expire regression: Firestore pins @grpc/grpc-js ~1.9.0, which excludes the 1.13.6 fix.
        outcome = self.outcome(
            [alert(130, package="@grpc/grpc-js", patched="1.13.6", relationship="transitive", manifest="package-lock.json")],
            dependency(package="@grpc/grpc-js", installed="1.9.16", manifest="package-lock.json",
                       relationship="transitive", parentRanges=["~1.9.0"]))
        self.assertEqual((outcome["decision"], outcome["reasons"]), ("hold", ["parent-range-excludes-target"]))
        self.assertEqual(outcome["upgrade"]["kind"], "minor")

    def test_every_parent_range_must_allow_the_patch(self):
        def brace(ranges):
            return self.outcome([alert(128, package="brace-expansion", patched="5.0.10", relationship="transitive")],
                                dependency(package="brace-expansion", installed="5.0.9", relationship="transitive",
                                           parentRanges=ranges))
        self.assertEqual(brace(["^5.0.8", "^5.0.2"])["decision"], "eligible")
        self.assertEqual(brace(["^5.0.8", "5.0.9"])["reasons"], ["parent-range-excludes-target"])
        self.assertEqual(brace(["^5.0.8", "latest"])["reasons"], ["parent-range-unknown"])

    def test_transitive_without_mechanical_parent_evidence_is_held(self):
        cases = {
            "missing": {}, "empty": {"parentRanges": []}, "not a list": {"parentRanges": "^4.17.0"},
            "non-string": {"parentRanges": [4]}, "hyphen": {"parentRanges": ["4.17.0 - 4.18.0"]},
            "tag": {"parentRanges": ["latest"]}, "partial inequality": {"parentRanges": [">=4"]},
            "prerelease": {"parentRanges": ["^4.17.21-rc.1"]}, "protocol": {"parentRanges": ["workspace:*"]},
            "major bump flag false only": {"parentRequiresMajorBump": False},
        }
        for name, evidence in cases.items():
            with self.subTest(case=name):
                outcome = self.outcome([alert(23, relationship="transitive")],
                                       dependency(relationship="transitive", **evidence))
                self.assertEqual((outcome["decision"], outcome["reasons"]), ("hold", ["parent-range-unknown"]))

    def test_non_npm_transitive_needs_explicit_parent_evidence(self):
        def pip(**evidence):
            return self.outcome([alert(24, package="urllib3", patched="2.2.2", ecosystem="pip",
                                       manifest="requirements.txt", relationship="transitive")],
                                dependency(package="urllib3", installed="2.2.1", ecosystem="pip",
                                           manifest="requirements.txt", relationship="transitive", **evidence))
        self.assertEqual(pip(parentRanges=["^2.2.0"])["reasons"], ["parent-range-unknown"])
        self.assertEqual(pip(parentAllowsTarget=True)["decision"], "eligible")
        self.assertEqual(pip(parentAllowsTarget=False)["reasons"], ["parent-range-excludes-target"])
        self.assertEqual(pip(parentAllowsTarget="yes")["reasons"], ["parent-range-unknown"])

    def test_transitive_fix_requiring_parent_major_bump_is_held(self):
        outcome = self.outcome([alert(2, relationship="transitive")],
                               dependency(relationship="transitive", parentRequiresMajorBump=True))
        self.assertEqual((outcome["decision"], outcome["reasons"]), ("hold", ["transitive-parent-major"]))

    def test_multiple_alerts_on_one_dependency_form_one_outcome_at_the_highest_patch(self):
        alerts = [alert(3, patched="4.17.19", severity="low"), alert(4, patched="4.17.21", severity="critical")]
        outcome = self.outcome(alerts, dependency(installed="4.17.0"))
        self.assertEqual(outcome["alerts"], [f"{REPO}#3", f"{REPO}#4"])
        self.assertEqual(outcome["upgrade"]["to"], "4.17.21")
        self.assertEqual((outcome["severity"], outcome["priority"], outcome["decision"]), ("critical", "P1", "eligible"))

    def test_independent_dependencies_keep_distinct_outcomes_in_stable_order(self):
        alerts = [alert(5, package="minimist", patched="1.2.6"), alert(6), alert(7, package="minimist", patched="1.2.6", manifest="tools/package.json")]
        plan = MODULE.build_plan(document(alerts), local(dependency(), dependency(package="minimist", installed="1.2.5")))
        keys = [o["key"] for o in plan["outcomes"]]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(keys), 3)
        self.assertEqual(plan["summary"], {"alerts": 3, "eligible": 2, "hold": 1, "verify-publication": 0})

    def test_severity_informs_priority_but_never_eligibility(self):
        critical_major = self.outcome([alert(8, patched="5.0.0", severity="critical")], dependency())
        self.assertEqual((critical_major["decision"], critical_major["priority"]), ("hold", "P1"))
        self.assertIn("major-upgrade", critical_major["reasons"])
        low_patch = self.outcome([alert(9, severity="low")], dependency())
        self.assertEqual((low_patch["decision"], low_patch["priority"]), ("eligible", "P3"))

    def test_uncertain_or_breaking_cases_are_held_with_named_reasons(self):
        cases = {
            "pre-1.0-uncertain": ([alert(10, package="semver-ish", patched="0.9.3")], dependency(package="semver-ish", installed="0.9.1")),
            "no-patched-version": ([alert(11, patched=None)], dependency()),
            "uncertain-version": ([alert(12, patched="latest")], dependency()),
            "unsupported-ecosystem": ([alert(13, ecosystem="actions", package="actions/checkout", patched="4", manifest=".github/workflows/ci.yml")], dependency(ecosystem="actions", package="actions/checkout", installed="3", manifest=".github/workflows/ci.yml")),
            "local-version-unknown": ([alert(14)],),
            "relationship-unknown": ([alert(15, relationship="inconclusive")], dependency()),
        }
        for reason, (alerts, *dependencies) in cases.items():
            with self.subTest(reason=reason):
                outcome = self.outcome(alerts, *dependencies)
                self.assertEqual(outcome["decision"], "hold")
                self.assertIn(reason, outcome["reasons"])

    def test_unpatched_alert_does_not_block_a_patched_sibling_fix(self):
        plan = MODULE.build_plan(document([alert(16), alert(17, patched=None)]), local(dependency()))
        decisions = {o["key"].rsplit(":", 1)[-1]: o["decision"] for o in plan["outcomes"]}
        self.assertEqual(decisions, {"patched": "eligible", "unpatched": "hold"})

    def test_locally_patched_dependency_needs_publication_verification_not_a_fix(self):
        outcome = self.outcome([alert(18)], dependency(installed="4.17.21"))
        self.assertEqual((outcome["decision"], outcome["upgrade"]["kind"]), ("verify-publication", "none"))

    def test_dirty_worktree_and_partial_evidence_are_blockers_not_silent(self):
        plan = MODULE.build_plan(document([alert(19)], status="partial"), local(dependency(), dirty=True))
        self.assertEqual(plan["blockers"], ["dirty-worktree", "alert-evidence-partial"])
        self.assertEqual(plan["local"], {"revision": "1111111", "dirty": True})
        self.assertEqual(plan["alertEvidence"]["defaultBranchHeadSha"], "deadbeef")

    def test_unavailable_evidence_yields_no_outcomes_and_nonzero_exit(self):
        plan = MODULE.build_plan(document([], status="unavailable"), {})
        self.assertEqual((plan["outcomes"], plan["blockers"]), ([], ["alert-evidence-unavailable"]))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "alerts.json"
            path.write_text(json.dumps(document([], status="unavailable")))
            result = subprocess.run([sys.executable, "-I", str(SCRIPT), "plan", "--alerts", str(path)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 3)
            self.assertEqual(json.loads(result.stdout)["blockers"], ["alert-evidence-unavailable"])

    def test_non_open_alerts_are_not_planned_and_planning_is_idempotent(self):
        doc = document([alert(20, state="fixed"), alert(21, state="dismissed"), alert(22)])
        first = MODULE.build_plan(doc, local(dependency()))
        second = MODULE.build_plan(doc, local(dependency()))
        self.assertEqual(first, second)
        self.assertEqual(first["summary"]["alerts"], 1)
        self.assertEqual(first["outcomes"][0]["alerts"], [f"{REPO}#22"])

    def test_cli_rejects_foreign_documents(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "other.json"
            path.write_text(json.dumps({"schemaVersion": "artifact-hygiene/v2"}))
            result = subprocess.run([sys.executable, "-I", str(SCRIPT), "plan", "--alerts", str(path)], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")


class NpmRangeTests(unittest.TestCase):
    def test_supported_ranges_follow_npm_semantics(self):
        cases = [
            ("~1.9.0", (1, 13, 6), False), ("~1.9.0", (1, 9, 20), True), ("~1.9", (1, 10, 0), False),
            ("~1", (1, 13, 6), True), ("^5.0.8", (5, 0, 10), True), ("^5.0.8", (5, 0, 7), False),
            ("^5.0.8", (6, 0, 0), False), ("^0.2.2", (0, 5, 0), False), ("^0.2.2", (0, 2, 9), True),
            ("^0.0.3", (0, 0, 4), False), ("^0.0", (0, 0, 9), True), ("^0.0", (0, 1, 0), False),
            ("^0", (0, 9, 0), True), ("^1.x", (1, 9, 0), True), ("1.2.3", (1, 2, 3), True),
            ("=1.2.3", (1, 2, 4), False), ("v1.2.3", (1, 2, 3), True), ("1.x", (1, 9, 0), True),
            ("1.2.x", (1, 3, 0), False), ("1", (2, 0, 0), False), ("*", (9, 9, 9), True), ("x", (0, 0, 1), True),
            (">=1.2.3 <2.0.0", (1, 9, 0), True), (">=1.2.3 <2.0.0", (2, 0, 0), False),
            (">1.2.3", (1, 2, 3), False), ("<=1.2.3", (1, 2, 3), True),
            ("^1.0.0 || ^2.0.0", (2, 1, 0), True), ("^1.0.0 || ^2.0.0", (3, 0, 0), False),
            ("^1.0.0 || latest", (1, 5, 0), True),
        ]
        for text, version, expected in cases:
            with self.subTest(range=text, version=version):
                self.assertIs(MODULE.npm_range_allows(text, version), expected)

    def test_unsupported_ranges_are_unknown_never_allowed(self):
        for text in ("", "latest", "1.2.3 - 2.0.0", ">=1.2", "<2", "^1.0.0-beta.1", "workspace:*",
                     "npm:foo@^1", "file:../x", "1.2.3.4", ">= 1.2.3", "^1.0.0 || latest", None, 1):
            with self.subTest(range=text):
                self.assertIsNone(MODULE.npm_range_allows(text, (3, 0, 0)))


class RecheckTests(unittest.TestCase):
    def setUp(self):
        self.plan = MODULE.build_plan(document([alert(1), alert(2, package="minimist", patched="1.2.6")]),
                                      local(dependency(), dependency(package="minimist", installed="1.2.5")))

    def recheck(self, alerts, published="deadbeef", **kwargs):
        fresh = document(alerts, requested=[1, 2], **kwargs)
        return MODULE.build_recheck(self.plan, fresh, published)

    def test_fixed_alerts_on_the_published_revision_are_observed_as_fixed(self):
        result = self.recheck([alert(1, state="fixed"), alert(2, package="minimist", state="fixed")])
        self.assertTrue(result["allFixed"])
        self.assertTrue(result["publicationObserved"])
        self.assertEqual({o["resolution"] for o in result["outcomes"]}, {"fixed"})

    def test_dismissed_is_not_fixed_and_open_is_pending(self):
        result = self.recheck([alert(1, state="dismissed"), alert(2, package="minimist")])
        resolutions = {o["key"].split(":")[2]: o["resolution"] for o in result["outcomes"]}
        self.assertEqual(resolutions, {"lodash": "dismissed", "minimist": "pending"})
        self.assertFalse(result["allFixed"])

    def test_missing_alerts_are_changed_and_unavailable_reads_are_unknown(self):
        changed = self.recheck([alert(2, package="minimist", state="fixed")], missing=[1])
        self.assertEqual(changed["outcomes"][0]["resolution"], "changed")
        unknown = self.recheck([], status="unavailable")
        self.assertEqual({o["resolution"] for o in unknown["outcomes"]}, {"unknown"})
        self.assertFalse(unknown["allFixed"])
        self.assertEqual(unknown["alertEvidence"]["status"], "unavailable")
        partial = self.recheck([alert(1, state="fixed")], unavailable=[2])
        self.assertEqual({o["key"].split(":")[2]: o["resolution"] for o in partial["outcomes"]}, {"lodash": "fixed", "minimist": "unknown"})

    def test_publication_mismatch_and_unknown_head_are_explicit(self):
        mismatch = self.recheck([alert(1, state="fixed"), alert(2, package="minimist", state="fixed")], published="feedface")
        self.assertFalse(mismatch["publicationObserved"])
        self.assertTrue(mismatch["allFixed"])
        unknown = self.recheck([alert(1, state="fixed"), alert(2, package="minimist", state="fixed")], head=None)
        self.assertIsNone(unknown["publicationObserved"])
        no_sha = MODULE.build_recheck(self.plan, document([alert(1, state="fixed"), alert(2, package="minimist", state="fixed")], requested=[1, 2]), None)
        self.assertIsNone(no_sha["publicationObserved"])


if __name__ == "__main__":
    unittest.main()
