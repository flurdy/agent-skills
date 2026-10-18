import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SKILL = Path(__file__).resolve().parents[1]
AUTHORITY = SKILL / "scripts" / "release-gates"
sys.path.insert(0, str(SKILL / "scripts"))
import release_gates  # noqa: E402
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


UPTAKE_HEADER = "resource|context|namespace|workload|desired|applied|consumed|rolloutState|template"
DECLARATION = ("config_uptake:\n  web-config:\n    service: web\n    resource: configmap/web-config\n"
               "    context: prod\n    namespace: apps\n    workload: deployment/web\n    reload: startup\n")


def uptake(*rows):
    return evidence("---META---\nprovider=kubernetes\n---UPTAKE---\n" + UPTAKE_HEADER + "\n" + "".join(row + "\n" for row in rows))


def observation(*, resource="configmap/web-config", context="prod", namespace="apps", workload="deployment/web",
                desired="c2", applied="c2", consumed="c1", state="settled", template="c2"):
    return f"{resource}|{context}|{namespace}|{workload}|{desired}|{applied}|{consumed}|{state}|{template}"


def add_api(data, *, unpushed=0, dirty=False, deploy="1/1", tag="v2"):
    text = data["digest"]["text"]
    data["digest"]["text"] = text.replace("---TOGGLES---", f"api|{unpushed}|{str(dirty).lower()}|success|main|main|def5678|{deploy}|{tag}|1h|upstream|upstream\n---TOGGLES---")
    data["order"] = evidence("---SOURCE---\nprovider=manifest\ngraph=manual\n---GRAPH---\nweb: [api]\n---DRIFT---\nstatus: not-applicable\n")
    return data


class AuthorityTestCase(unittest.TestCase):
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


class ReleaseGatesTests(AuthorityTestCase):
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

    def test_dirty_prerequisite_alone_does_not_hold_consumer_and_stays_visible(self):
        for manifest in ("", "ignore: [api]\n"):
            for selected in (None, "web"):
                with self.subTest(manifest=manifest, selected=selected):
                    clean = self.run_snapshot(add_api(snapshot(manifest=manifest)), selected)
                    result = self.run_snapshot(add_api(snapshot(manifest=manifest), dirty=True), selected)
                    row = next(row for row in result["services"] if row["service"] == "web")
                    clean_row = next(row for row in clean["services"] if row["service"] == "web")
                    self.assertEqual(row["verdict"], "READY")
                    self.assertEqual(row["gates"], clean_row["gates"])
                    self.assertFalse(row["uncommitted"])
                    self.assertIn("api: uncommitted local changes are not deployed", row["notes"])
                    if selected is None and not manifest:
                        api = next(row for row in result["services"] if row["service"] == "api")
                        self.assertTrue(api["uncommitted"])
                    else:
                        self.assertEqual([row["service"] for row in result["services"]], ["web"])

    def test_consumer_dirt_still_holds_with_a_dirty_settled_prerequisite(self):
        row = self.web(add_api(snapshot(dirty=True), dirty=True))
        self.assertEqual(row["verdict"], "HOLD")
        self.assertEqual(row["gates"]["work"]["result"], "hold")
        self.assertEqual(row["gates"]["order"]["result"], "pass")

    def test_dirty_prerequisite_does_not_bypass_other_gates(self):
        data = add_api(snapshot(), dirty=True)
        data["contracts"] = evidence(CONTRACTS.replace("OK web -> api", "STALE web -> api"))
        row = self.web(data)
        self.assertEqual(row["verdict"], "NOT READY")
        self.assertEqual(row["gates"]["contracts"]["result"], "block")
        data = add_api(snapshot(), dirty=True)
        data["state"] = evidence(json.dumps({"publishing": {"api": {"uncertain": True}}}))
        row = self.web(data)
        self.assertEqual(row["verdict"], "HOLD")
        self.assertEqual(row["gates"]["publication"]["result"], "hold")

    def test_ignored_prerequisite_with_unpushed_commits_still_blocks_consumer(self):
        row = self.web(add_api(snapshot(manifest="ignore: [api]\n"), unpushed=1, dirty=True))
        self.assertEqual(row["gates"]["order"]["result"], "block")
        self.assertEqual(row["verdict"], "NOT READY")

    def test_scoped_result_still_evaluates_prerequisites(self):
        for dirty in (False, True):
            for unpushed, deploy, expected in [(1, "1/1", "block"), (0, "0/1", "block"), (0, "cron:rollout", "block"), (0, "unknown", "hold"), (0, "1/1", "pass")]:
                with self.subTest(dirty=dirty, unpushed=unpushed, deploy=deploy):
                    data = add_api(snapshot(), unpushed=unpushed, deploy=deploy, dirty=dirty)
                    rows = self.run_snapshot(data, "web")["services"]
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["gates"]["order"]["result"], expected)

    def test_rollout_confirmation_requires_baseline_movement_and_settlement(self):
        for dirty in (False, True):
            for baseline, deploy, tag, expected in [(None, "1/1", "v2", "hold"), ("v2", "1/1", "v2", "block"), ("v1", "0/1", "v2", "block"), ("v1", "1/1", "v2", "pass")]:
                with self.subTest(dirty=dirty, baseline=baseline, deploy=deploy, tag=tag):
                    data = add_api(snapshot(), deploy=deploy, tag=tag, dirty=dirty)
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

    def test_section_names_may_contain_digits(self):
        data = snapshot()
        data["digest"]["text"] = data["digest"]["text"].replace("---TOGGLES---", "---K8S---\npresent=true\n---TOGGLES---")
        self.assertEqual(self.web(data)["verdict"], "READY")

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

    def test_pending_publication_record_holds_every_service(self):
        record = {"sha": "a" * 40, "fromTag": "v1", "session": "s", "deploying": True}
        for entry in (record, {**record, "uncertain": True}):
            data = add_api(snapshot())
            data["state"] = evidence(json.dumps({"publishing": {"api": entry}}))
            web = self.web(data)
            self.assertEqual(web["verdict"], "HOLD")
            self.assertEqual(web["gates"]["publication"]["result"], "hold")
            self.assertIn("api", " ".join(web["gates"]["publication"]["evidence"]))
        data = add_api(snapshot())
        data["state"] = evidence(json.dumps({"publishing": {}}))
        self.assertNotIn("publication", self.web(data)["gates"])
        data["state"] = evidence(json.dumps({"publishing": []}))
        self.assertEqual(self.web(data)["verdict"], "HOLD")

    def test_own_publication_record_can_be_excluded_without_hiding_others(self):
        record = {"id": "1" * 32, "sha": "a" * 40, "fromTag": "v1", "session": "s", "deploying": True}
        data = add_api(snapshot())
        data["state"] = evidence(json.dumps({"publishing": {"web": record}}))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_text(json.dumps(data))
            run = lambda *extra: json.loads(subprocess.run([str(AUTHORITY), "--snapshot", str(path), *extra], capture_output=True, text=True, check=True).stdout)
            self.assertEqual(next(row for row in run()["services"] if row["service"] == "web")["verdict"], "HOLD")
            web = next(row for row in run("--exclude-publication", "1" * 32)["services"] if row["service"] == "web")
            self.assertEqual(web["verdict"], "READY")
            self.assertNotIn("publication", web["gates"])
            data["state"] = evidence(json.dumps({"publishing": {"web": record, "api": {**record, "id": "2" * 32}}}))
            path.write_text(json.dumps(data))
            web = next(row for row in run("--exclude-publication", "1" * 32)["services"] if row["service"] == "web")
            self.assertEqual(web["verdict"], "HOLD")

    def test_unreadable_publication_state_holds_non_deploying_services(self):
        manifest = "non_deploying: [web]\n"
        for text in ("not json", json.dumps({"rolloutWatch": {"api": "broken"}, "publishing": {"api": {"sha": "a" * 40}}})):
            data = snapshot(manifest=manifest)
            data["state"] = evidence(text)
            web = self.web(data)
            self.assertEqual(web["verdict"], "HOLD", text)
            self.assertEqual(web["gates"]["publication"]["result"], "hold", text)

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
            for name, output, allowed_args in [("release-digest", snapshot()["digest"]["text"], ""), ("release-order", ORDER, ""), ("contract-check", CONTRACTS, "all"), ("release-config-uptake", uptake(observation())["text"], "")]:
                path = scripts / name
                path.write_text(f"#!/bin/sh\n[ \"$*\" = '{allowed_args}' ] || exit 9\nprintf '%s' '{output}'\n")
                path.chmod(0o755)
            state = root / ".release-state.json"
            state.write_text('{"configApply":{"keep":"untouched"}}')
            result = subprocess.run([str(AUTHORITY), "--project-root", str(root)], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["services"][0]["verdict"], "READY")
            self.assertEqual(json.loads(result.stdout)["uptake"]["status"], "ok")
            self.assertEqual(json.loads(result.stdout)["uptake"]["unmapped"], ["configmap/web-config prod/apps deployment/web"])
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
            self.assertIn("release-digest timeout after 1s budget", json.loads(result.stdout)["errors"])

    def test_collection_budgets_default_per_source_and_clamp_overrides(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("RELEASE_GATES_TIMEOUT", None)
            self.assertEqual(release_gates.budget_seconds("release-digest"), 90)
            self.assertEqual(release_gates.budget_seconds("release-order"), 20)
            self.assertEqual(release_gates.budget_seconds("contract-check"), 20)
            self.assertEqual(release_gates.budget_seconds("release-config-uptake"), 20)
        for value, expected in [("5", 5), ("500", 120), ("0", 1), ("nope", 90)]:
            with self.subTest(value=value), mock.patch.dict(os.environ, {"RELEASE_GATES_TIMEOUT": value}):
                self.assertEqual(release_gates.budget_seconds("release-digest"), expected)


class ConfigUptakeTests(AuthorityTestCase):
    """Advisory config uptake: desired, controller-applied and application-effective stay distinct; no gate changes."""

    def entry(self, data):
        row = self.web(data)
        self.assertEqual(len(row["configUptake"]), 1)
        return row, row["configUptake"][0]

    def assert_readiness_unchanged(self, data, baseline=None):
        baseline = baseline or snapshot()
        result, expected = self.run_snapshot(data), self.run_snapshot(baseline)
        self.assertEqual(result["services"][0]["gates"], expected["services"][0]["gates"])
        self.assertEqual(result["services"][0]["verdict"], expected["services"][0]["verdict"])
        self.assertEqual(result["errors"], expected["errors"])
        return result

    def test_absent_capability_is_unknown_and_keeps_readiness(self):
        for source, status in [(None, "not-captured"), ({"status": "absent", "reason": "release-config-uptake adapter missing"}, "absent"),
                               ({"status": "unavailable", "reason": "release-config-uptake timeout after 20s budget"}, "unavailable")]:
            with self.subTest(status=status):
                data = snapshot(manifest=DECLARATION)
                if source:
                    data["uptake"] = source
                result = self.assert_readiness_unchanged(data)
                self.assertEqual(result["uptake"]["status"], status)
                row = result["services"][0]
                entry = row["configUptake"][0]
                self.assertEqual((entry["state"], entry["maintenance"], entry["effective"], entry["desired"]), ("unknown", None, None, None))
                self.assertEqual(entry["reload"], "startup")
                self.assertTrue(any(note.startswith("config web-config: unknown") for note in row["notes"]), row["notes"])
        plain = self.run_snapshot(snapshot())
        self.assertEqual(plain["services"][0]["configUptake"], [])
        self.assertEqual(plain["uptake"], {"status": "not-captured", "unmapped": [], "diagnostics": []})
        self.assertFalse(any(note.startswith("config ") for note in plain["services"][0]["notes"]))

    def test_mismatched_identity_and_unmapped_observations_stay_unknown(self):
        data = snapshot(manifest=DECLARATION)
        data["uptake"] = uptake(observation(workload="deployment/other"), observation(resource="configmap/orphan", consumed="c2"))
        result = self.assert_readiness_unchanged(data)
        entry = result["services"][0]["configUptake"][0]
        self.assertEqual((entry["state"], entry["maintenance"]), ("unknown", None))
        self.assertIn("identity", entry["evidence"])
        self.assertIn("deployment/other", entry["evidence"])
        self.assertEqual(result["uptake"]["unmapped"], ["configmap/web-config prod/apps deployment/other", "configmap/orphan prod/apps deployment/web"])
        data["uptake"] = uptake(observation(), observation(consumed="c2"))
        _, entry = self.entry(data)
        self.assertEqual((entry["state"], entry["maintenance"]), ("unknown", None))
        self.assertIn("conflicting", entry["evidence"])

    def test_missing_or_lagging_revisions_never_recommend_restart(self):
        for kwargs, state in [(dict(applied="c1"), "pending"), (dict(desired="-"), "unknown"), (dict(applied="-"), "unknown")]:
            with self.subTest(**kwargs):
                data = snapshot(manifest=DECLARATION)
                data["uptake"] = uptake(observation(**kwargs))
                row, entry = self.entry(data)
                self.assertEqual((entry["state"], entry["maintenance"]), (state, None))
                self.assertEqual(entry["effective"], "c1")
                self.assertEqual(row["verdict"], "READY")
        data = snapshot(manifest=DECLARATION)
        data["uptake"] = uptake(observation(applied="c1"))
        _, entry = self.entry(data)
        self.assertEqual((entry["desired"], entry["applied"]), ("c2", "c1"))
        self.assertIn("controller applied c1", entry["evidence"])

    def test_restart_requires_startup_reload_applied_config_and_a_delivering_template(self):
        for reload, action in [("startup", "restart"), ("dynamic", "investigate"), ("unknown", "investigate")]:
            with self.subTest(reload=reload):
                data = snapshot(manifest=DECLARATION.replace("reload: startup", f"reload: {reload}"))
                data["uptake"] = uptake(observation())
                row, entry = self.assert_readiness_unchanged(data)["services"][0], None
                entry = row["configUptake"][0]
                self.assertEqual((entry["state"], entry["effective"], entry["maintenance"]["action"]), ("applied", "c1", action))
                self.assertEqual(entry["maintenance"]["workload"], "deployment/web in prod/apps")
                if action == "restart":
                    self.assertEqual(entry["maintenance"]["command"], "/release-maintenance restart web")
                    self.assertIn("config web-config: restart deployment/web in prod/apps required — /release-maintenance restart web", row["notes"])
                else:
                    self.assertNotIn("command", entry["maintenance"])
                    self.assertFalse(any("restart" in note and "required" in note for note in row["notes"]))
        data = snapshot(manifest=DECLARATION.replace("    reload: startup\n", ""))
        data["uptake"] = uptake(observation())
        _, entry = self.entry(data)
        self.assertEqual((entry["reload"], entry["maintenance"]["action"]), ("unknown", "investigate"))
        for reload in ("startup", "dynamic", "unknown"):
            with self.subTest(effective=reload):
                data = snapshot(manifest=DECLARATION.replace("reload: startup", f"reload: {reload}"))
                data["uptake"] = uptake(observation(consumed="c2", state="rolling", template="c1"))
                row, entry = self.entry(data)
                self.assertEqual((entry["state"], entry["effective"], entry["maintenance"]), ("effective", "c2", None))
                self.assertFalse(any(note.startswith("config ") for note in row["notes"]))

    def test_matching_rollout_defers_and_unrelated_rollout_does_not_satisfy_uptake(self):
        cases = [
            (dict(state="rolling", template="c2"), "rolling", None),
            (dict(state="rolling", template="c1"), "applied", "investigate"),
            (dict(state="rolling", template="-"), "applied", "investigate"),
            (dict(state="unknown", template="c2"), "applied", "investigate"),
            (dict(state="settled", template="c1"), "applied", "investigate"),
            (dict(state="settled", template="-"), "applied", "investigate"),
            (dict(state="settled", consumed="-"), "applied", "investigate"),
            (dict(state="settled", consumed="c1", template="c2"), "applied", "restart"),
        ]
        for kwargs, state, action in cases:
            with self.subTest(**kwargs):
                data = snapshot(manifest=DECLARATION)
                data["uptake"] = uptake(observation(**kwargs))
                row, entry = self.entry(data)
                self.assertEqual(entry["state"], state)
                self.assertEqual(entry["maintenance"] and entry["maintenance"]["action"], action)
                self.assertEqual(entry["rolloutState"], kwargs["state"])
                self.assertEqual(row["verdict"], "READY")
                if state == "rolling":
                    self.assertIn("config web-config: rolling — rollout in progress delivers c2", row["notes"])

    def test_uptake_evidence_never_changes_gates_errors_or_legacy_handling(self):
        malformed = [
            "garbage",
            "---META---\nprovider=kubernetes\n---UPTAKE---\nwrong|header\n",
            "---META---\n---UPTAKE---\n" + UPTAKE_HEADER + "\n",
            uptake(observation(consumed="password=hunter2"))["text"],
            uptake(observation(template="has space"))["text"],
            uptake(observation(state="maybe"))["text"],
            uptake(observation(workload="-"))["text"],
            uptake("too|few")["text"],
        ]
        for text in malformed:
            with self.subTest(text=text[:40]):
                data = snapshot(manifest=DECLARATION)
                data["uptake"] = evidence(text)
                result = self.assert_readiness_unchanged(data)
                self.assertEqual(result["uptake"]["status"], "malformed")
                self.assertTrue(result["uptake"]["reason"])
                self.assertNotIn("hunter2", json.dumps(result))
                self.assertNotIn("has space", json.dumps(result))
                self.assertEqual(result["services"][0]["configUptake"][0]["state"], "unknown")
        data = snapshot(manifest=DECLARATION)
        data["digest"]["text"] = data["digest"]["text"].replace("---TOGGLES---", "---CONFIG---\nweb-config|configmap|12345|true|web|web\n---TOGGLES---")
        data["state"] = evidence(json.dumps({"configApply": {"web-config": "12345"}, "restartPending": ["web"], "restartWatch": {}}))
        result = self.assert_readiness_unchanged(data)
        self.assertEqual(result["uptake"]["status"], "not-captured")
        self.assertEqual((result["services"][0]["configUptake"][0]["state"], result["services"][0]["configUptake"][0]["maintenance"]), ("unknown", None))
        data = snapshot(dirty=True, manifest=DECLARATION)
        data["uptake"] = uptake(observation())
        row = self.assert_readiness_unchanged(data, snapshot(dirty=True))["services"][0]
        self.assertEqual((row["verdict"], row["configUptake"][0]["maintenance"]["action"]), ("HOLD", "restart"))
        data = snapshot()
        data["uptake"] = {"status": "ok"}
        self.assertEqual(self.run_snapshot(data)["services"], [])

    def test_declaration_problems_are_diagnostics_not_policy_holds(self):
        for manifest in [DECLARATION.replace("reload: startup", "reload: sometimes"), DECLARATION.replace("service: web", "service: nope"),
                         DECLARATION.replace("    workload: deployment/web\n", ""), "config_uptake: [web]\n", "config_uptake:\n  web-config: nested\n",
                         "toggles:\n  FLAG:\n    service: web\n    config_uptake: nested\n" + DECLARATION]:
            with self.subTest(manifest=manifest):
                data = snapshot(manifest=manifest)
                data["uptake"] = uptake(observation())
                result = self.run_snapshot(data)
                row = result["services"][0]
                self.assertNotIn("policy", row["gates"])
                self.assertEqual(row["verdict"], "READY")
                self.assertEqual(row["configUptake"], [])
                self.assertTrue(result["uptake"]["diagnostics"])
                self.assertEqual(result["errors"], self.run_snapshot(snapshot())["errors"])
        data = snapshot(manifest="toggles:\n  FLAG:\n    service: web\n" + DECLARATION)
        data["uptake"] = uptake(observation(consumed="c2"))
        row, entry = self.entry(data)
        self.assertEqual((row["gates"]["toggle"]["result"], entry["state"]), ("pass", "effective"))
        data = add_api(snapshot(manifest=DECLARATION))
        data["uptake"] = uptake(observation())
        self.assertEqual(self.run_snapshot(data, "api")["services"][0]["configUptake"], [])
        self.assertEqual(self.run_snapshot(data, "web")["services"][0]["configUptake"][0]["state"], "applied")


if __name__ == "__main__":
    unittest.main()
