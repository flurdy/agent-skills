import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1]
AUTHORITY = SKILL / "scripts" / "release-gates"
HEADER = "service|unpushed|uncommitted|ci|ciBranch|gitBranch|head|deploy|tag|age|ciRevision|ciExpectedRevision"
ORDER = "---SOURCE---\nprovider=none\ngraph=none\n---GRAPH---\n---DRIFT---\nstatus: not-applicable\n"
CONTRACTS = """## Staleness Report
OK web -> api
SUMMARY stale=0 ok=1 missing_provider=0 total=1
## Uncommitted Pact Files
CLEAN All pact files are committed across 1 provider services
SUMMARY uncommitted=0 services_checked=1
## Sync Coverage (consumer test → built pact → provider)
OK web -> api
SUMMARY ok=1 not_built=0 not_synced=0 total=1
## CI Verification Coverage
OK api style=tag synced=1 verified
SUMMARY ok=1 gaps=0 providers=1
## Contract Relationship Matrix
| Consumer | Provider | Sources |
|----------|----------|---------|
| web | api | consumer provider |
TOTAL 1 relationships
"""


def evidence(text):
    return {"status": "ok", "text": text}


def snapshot(*, dirty=False, unpushed=1, ci="success", deploy="1/1", manifest=""):
    row = f"web|{unpushed}|{str(dirty).lower()}|{ci}|main|main|abc1234|{deploy}|v2|2h|upstream|upstream"
    return {
        "schemaVersion": 1,
        "digest": evidence("---META---\nciProvider=github-actions\nci=available\n---SERVICES---\n" + HEADER + "\n" + row + "\n---TOGGLES---\nFLAG=false\n"),
        "order": evidence(ORDER),
        "contracts": {"status": "absent", "reason": "no adapter"},
        "manifest": evidence(manifest) if manifest else {"status": "absent", "reason": "not configured"},
        "state": {"status": "absent", "reason": "no state"},
    }


def add_api(data, *, unpushed=0, deploy="1/1", tag="v2"):
    text = data["digest"]["text"]
    data["digest"]["text"] = text.replace("---TOGGLES---", f"api|{unpushed}|false|success|main|main|def5678|{deploy}|{tag}|1h|upstream|upstream\n---TOGGLES---")
    data["order"] = evidence("---SOURCE---\nprovider=manifest\ngraph=manual\n---GRAPH---\nweb: [api]\n---DRIFT---\nstatus: not-applicable\n")
    return data


class ReleaseGatesTests(unittest.TestCase):
    def run_snapshot(self, data, service=None):
        self.assertTrue(AUTHORITY.is_file(), "one executable release-gates authority must exist")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_text(json.dumps(data))
            args = [str(AUTHORITY), "--snapshot", str(path)]
            if service:
                args += [service]
            result = subprocess.run(args, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def web(self, data):
        result = self.run_snapshot(data)
        return next(row for row in result["services"] if row["service"] == "web")

    def test_false_flag_is_activation_followup_not_shipping_block(self):
        data = snapshot(manifest="toggles:\n  FLAG:\n    service: web\n    flip_when: after validation\n")
        row = self.web(data)
        self.assertEqual(row["verdict"], "READY")
        self.assertEqual(row["gates"]["toggle"]["result"], "pass")
        self.assertTrue(any("activation" in note for note in row["notes"]))

    def test_dirty_tree_holds_deploying_and_non_deploying_repositories(self):
        for manifest in ["", "non_deploying: [web]\n"]:
            with self.subTest(manifest=manifest):
                row = self.web(snapshot(dirty=True, manifest=manifest))
                self.assertEqual(row["verdict"], "HOLD")
                self.assertEqual(row["gates"]["work"]["result"], "hold")

    def test_no_work_and_failed_ci_take_precedence_over_holds(self):
        self.assertEqual(self.web(snapshot(dirty=True, unpushed=0))["verdict"], "NOT READY")
        self.assertEqual(self.web(snapshot(dirty=True, ci="failed"))["verdict"], "NOT READY")

    def test_exact_upstream_ci_is_required(self):
        for old, new in [("|upstream|upstream", "|old|upstream"), ("|main|main|", "|feature|main|"), ("|upstream|upstream", "|-|-"), ("ci=available", "ci=unavailable")]:
            with self.subTest(new=new):
                data = snapshot()
                data["digest"]["text"] = data["digest"]["text"].replace(old, new)
                self.assertEqual(self.web(data)["verdict"], "HOLD")
        self.assertEqual(self.web(snapshot(ci="running"))["verdict"], "HOLD")

    def test_absent_order_is_not_a_valid_empty_graph(self):
        data = snapshot()
        self.assertEqual(self.web(data)["verdict"], "READY")
        data["order"] = {"status": "absent", "reason": "missing adapter"}
        self.assertEqual(self.web(data)["verdict"], "HOLD")

    def test_non_deploying_exempts_only_ci_order_and_deployment(self):
        data = snapshot(ci="unknown", manifest="non_deploying:\n  - web\n")
        data["order"] = {"status": "absent", "reason": "missing adapter"}
        self.assertEqual(self.web(data)["verdict"], "READY")
        data["contracts"] = evidence(CONTRACTS.replace("OK web -> api", "STALE web -> api"))
        self.assertEqual(self.web(data)["verdict"], "NOT READY")

    def test_active_missing_and_malformed_toggle_values_hold(self):
        for value in ["", "FLAG=unknown", "FLAG=false\nFLAG=true"]:
            data = snapshot(manifest="toggles:\n  FLAG:\n    service: web\n")
            data["digest"]["text"] = data["digest"]["text"].replace("FLAG=false", value)
            self.assertEqual(self.web(data)["verdict"], "HOLD")

    def test_parked_and_dark_release_flags_are_informational(self):
        for status in ["parked", "dark-release"]:
            data = snapshot(manifest=f"toggles:\n  FLAG:\n    service: web\n    status: {status}\n")
            data["digest"]["text"] = data["digest"]["text"].replace("FLAG=false", "")
            self.assertEqual(self.web(data)["verdict"], "READY")
        data = snapshot(manifest="toggles:\n  FLAG:\n    service: web\nparked:\n  FLAG:\n    superseded_by: successor\n")
        self.assertEqual(self.web(data)["verdict"], "READY")

    def test_applicable_contract_gap_holds_and_staleness_blocks(self):
        data = add_api(snapshot())
        data["contracts"] = evidence(CONTRACTS)
        self.assertEqual(self.web(data)["verdict"], "READY")
        for finding, verdict in [("STALE", "NOT READY"), ("DIFFERS", "NOT READY"), ("MISSING_PROVIDER", "NOT READY"), ("NOT_BUILT", "NOT READY"), ("NOT_SYNCED", "NOT READY")]:
            data["contracts"] = evidence(CONTRACTS.replace("OK web -> api", f"{finding} web -> api"))
            self.assertEqual(self.web(data)["verdict"], verdict)
        data["contracts"] = evidence(CONTRACTS.replace("OK api style=tag synced=1 verified", "GAP api not-verified=web").replace("ok=1 gaps=0", "ok=0 gaps=1"))
        api = self.run_snapshot(data, "api")["services"][0]
        self.assertEqual(api["gates"]["contracts"]["result"], "hold")

    def test_known_contract_relation_requires_expected_evidence(self):
        data = add_api(snapshot())
        data["order"]["text"] = data["order"]["text"].replace("provider=manifest", "provider=pact")
        self.assertEqual(self.web(data)["verdict"], "HOLD")
        data["contracts"] = evidence(CONTRACTS + "\nSUMMARY status=error\n")
        self.assertEqual(self.web(data)["verdict"], "HOLD")

    def test_scoped_result_still_evaluates_prerequisites(self):
        for unpushed, deploy, expected in [(1, "1/1", "block"), (0, "0/1", "block"), (0, "cron:rollout", "block"), (0, "unknown", "hold"), (0, "1/1", "pass")]:
            data = add_api(snapshot(), unpushed=unpushed, deploy=deploy)
            rows = self.run_snapshot(data, "web")["services"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["gates"]["order"]["result"], expected)

    def test_rollout_confirmation_requires_baseline_movement_and_settlement(self):
        for baseline, deploy, tag, expected in [(None, "1/1", "v2", "hold"), ("v2", "1/1", "v2", "block"), ("v1", "0/1", "v2", "block"), ("v1", "1/1", "v2", "pass")]:
            data = add_api(snapshot(), deploy=deploy, tag=tag)
            data["state"] = evidence(json.dumps({"rolloutWatch": {"api": {"sha": "def5678", "fromTag": baseline}}}))
            self.assertEqual(self.web(data)["gates"]["order"]["result"], expected)

    def test_missing_dependency_cannot_be_inferred_live(self):
        data = snapshot()
        data["order"] = add_api(copy.deepcopy(data))["order"]
        self.assertEqual(self.web(data)["verdict"], "HOLD")

    def test_deploy_unavailable_is_optional_but_overlap_holds(self):
        self.assertEqual(self.web(snapshot(deploy="unknown"))["verdict"], "READY")
        self.assertEqual(self.web(snapshot(deploy="0/1"))["verdict"], "HOLD")
        self.assertEqual(self.web(snapshot(deploy="cron:rollout"))["verdict"], "HOLD")

    def test_malformed_policy_holds_instead_of_becoming_empty_defaults(self):
        for manifest in ["toggles: &flags {}\n", "non_deploying: web\n", "toggles:\n  FLAG:\n    service: web\n    flip_when: |\n      later\n", "ignore: [web\n"]:
            self.assertEqual(self.web(snapshot(manifest=manifest))["verdict"], "HOLD")
        self.assertEqual(self.web(snapshot(manifest='toggles:\n  FLAG:\n    service: "web"\n    flip_when: "after # validation"\n'))["verdict"], "READY")

    def test_bad_digest_and_snapshot_never_emit_ready(self):
        for change in [lambda d: d.update(schemaVersion=2), lambda d: d.update(unexpected=True), lambda d: d.update(digest=evidence("bad header"))]:
            data = snapshot()
            change(data)
            result = self.run_snapshot(data)
            self.assertEqual(result["verdict"], "HOLD")
            self.assertEqual(result["services"], [])
            self.assertTrue(result["errors"])

    def test_invalid_and_duplicate_service_rows_fail_closed(self):
        for old, new in [("|false|success|", "|maybe|success|"), ("web|1|", "web|-1|"), ("---TOGGLES---", "web|1|false|success|main|main|abc|1/1|v2|1h|up|up\n---TOGGLES---")]:
            data = snapshot()
            data["digest"]["text"] = data["digest"]["text"].replace(old, new)
            self.assertEqual(self.run_snapshot(data)["services"], [])

    def test_missing_git_identity_is_not_ready(self):
        for old, new in [("abc1234", "-"), ("|main|main|", "|unknown|unknown|"), ("|upstream|upstream", "|unknown|unknown")]:
            data = snapshot()
            data["digest"]["text"] = data["digest"]["text"].replace(old, new)
            self.assertEqual(self.web(data)["verdict"], "HOLD")

    def test_malformed_state_does_not_discard_possible_rollout(self):
        for state in ["not json", json.dumps({"rolloutWatch": {"api": "broken"}})]:
            data = add_api(snapshot())
            data["state"] = evidence(state)
            self.assertEqual(self.web(data)["verdict"], "HOLD")

    def test_missing_order_metadata_and_unsupported_policy_fail_closed(self):
        data = snapshot()
        data["order"]["text"] = data["order"]["text"].replace("graph=none\n", "")
        self.assertEqual(self.web(data)["verdict"], "HOLD")
        for manifest in ["<<: *policy\n", "  toggles:\n    FLAG:\n      service: web\n", "\ttoggles:\n", '"toggles": *policy\n', "toggles:\n  FLAG:\n    service: typo\n"]:
            self.assertEqual(self.web(snapshot(manifest=manifest))["verdict"], "HOLD")

    def test_missing_contract_findings_do_not_override_nonzero_summary(self):
        data = add_api(snapshot())
        data["contracts"] = evidence(CONTRACTS.replace("stale=0", "stale=1"))
        self.assertEqual(self.web(data)["verdict"], "HOLD")

    def test_actual_adapter_spacing_and_uncommitted_findings(self):
        data = add_api(snapshot())
        data["contracts"] = evidence(CONTRACTS.replace("SUMMARY ", "SUMMARY  ").replace("TOTAL ", "TOTAL  "))
        self.assertEqual(self.web(data)["verdict"], "READY")
        data["contracts"]["text"] = data["contracts"]["text"].replace("CLEAN All pact files are committed across 1 provider services", "UNCOMMITTED  web  modified: pact.json").replace("uncommitted=0", "uncommitted=1")
        self.assertEqual(self.web(data)["verdict"], "NOT READY")

    def test_consistent_gap_holds_named_unverified_consumers_too(self):
        data = add_api(snapshot())
        data["contracts"] = evidence(CONTRACTS.replace("OK api style=tag synced=1 verified", "GAP api style=enum synced=1 not-verified=web").replace("ok=1 gaps=0", "ok=0 gaps=1"))
        row = self.web(data)
        self.assertEqual(row["verdict"], "HOLD")
        self.assertEqual(row["gates"]["contracts"]["evidence"], ["contract coverage GAP"])

    def test_provider_wide_gap_holds_known_consumers(self):
        data = add_api(snapshot())
        data["contracts"] = evidence(CONTRACTS.replace("OK api style=tag synced=1 verified", "GAP api no .circleci/config.yml (cannot verify 1 consumer(s))").replace("ok=1 gaps=0", "ok=0 gaps=1"))
        self.assertEqual(self.web(data)["gates"]["contracts"]["evidence"], ["contract coverage GAP"])

    def test_unknown_provider_keeps_other_evidence_and_holds_only_ci(self):
        for manifest, expected in [("", "HOLD"), ("non_deploying: [web]", "READY")]:
            data = snapshot(manifest=manifest)
            data["digest"]["text"] = data["digest"]["text"].replace("ciProvider=github-actions", "ciProvider=jenkins")
            self.assertEqual(self.web(data)["verdict"], expected)

    def test_optional_adapter_absence_and_unmanaged_order_stay_visible(self):
        data = snapshot()
        result = self.run_snapshot(data)
        self.assertTrue(any("contracts:" in error for error in result["errors"]))
        data["order"]["text"] = data["order"]["text"].replace("provider=none", "provider=pact").replace("graph=none", "graph=live").replace("status: not-applicable", "status: unmanaged (no release manifest)")
        self.assertIn("status: unmanaged (no release manifest)", self.run_snapshot(data)["drift"])

    def test_ignored_services_are_not_candidates(self):
        data = snapshot(manifest="ignore: [web]\n")
        self.assertEqual(self.run_snapshot(data)["services"], [])
        self.assertTrue(self.run_snapshot(data, "web")["errors"])

    def test_collector_uses_only_fixed_read_only_commands_and_does_not_write_state(self):
        self.assertTrue(AUTHORITY.is_file())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            for name, output, allowed_args in [("release-digest", snapshot()["digest"]["text"], ""), ("release-order", ORDER, ""), ("contract-check", CONTRACTS, "all")]:
                path = scripts / name
                path.write_text(f"#!/bin/sh\n[ \"$*\" = '{allowed_args}' ] || exit 9\nprintf '%s' '{output}'\n")
                path.chmod(0o755)
            state = root / ".release-state.json"
            state.write_text('{"configApply":{"keep":"untouched"}}')
            result = subprocess.run([str(AUTHORITY), "--project-root", str(root)], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["services"][0]["verdict"], "READY")
            self.assertEqual(state.read_text(), '{"configApply":{"keep":"untouched"}}')
            self.assertEqual(sorted(path.name for path in root.iterdir()), [".release-state.json", "scripts"])

    def test_collector_missing_commands_and_timeout_fail_closed(self):
        self.assertTrue(AUTHORITY.is_file())
        with tempfile.TemporaryDirectory() as directory:
            args = [str(AUTHORITY), "--project-root", directory]
            result = subprocess.run(args, capture_output=True, text=True, check=False)
            self.assertEqual(json.loads(result.stdout)["verdict"], "HOLD")
            scripts = Path(directory) / "scripts"
            scripts.mkdir()
            path = scripts / "release-digest"
            path.write_text("#!/bin/sh\nsleep 10\n")
            path.chmod(0o755)
            result = subprocess.run(args, env={**os.environ, "RELEASE_GATES_TIMEOUT": "1"}, capture_output=True, text=True, timeout=4, check=False)
            self.assertEqual(json.loads(result.stdout)["verdict"], "HOLD")
            self.assertIn("timeout", result.stdout)


if __name__ == "__main__":
    unittest.main()
