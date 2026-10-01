"""Synthetic audit/preview and refresh contracts; no provider or credential access."""
import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


AUDIT = load("migration_audit")
REFRESH = load("catalog_refresh")
NOW = datetime(2026, 1, 10, tzinfo=timezone.utc)
OLD = "openai-codex/example-sol-1"
NEW = "openai-codex/example-sol-2"


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.router = {"enabled": True, "tiers": {"standard": {"selection": "weighted-random", "thinking": "high", "candidates": [
            {"model": OLD, "metered": True, "weight": 25, "enabled": False},
            {"model": OLD, "weight": 75, "enabled": True}]}}, "modelPolicies": {OLD: {"metered": False, "consent": "ask"}}, "unrelated": 123}
        self.panel = {"version": 1, "profiles": {"premium": {"quorum": 2, "consensusQuorum": 2, "routes": [
            {"id": "codex", "kind": "local", "agent": "codex", "model": "example-sol-1", "role": "code"},
            {"id": "claude", "kind": "local", "agent": "claude", "model": "opus", "role": "review"},
            {"id": "native", "kind": "local", "agent": "gemini", "role": "critique"}]}},
            "subscriptionRoutes": {"codex": ["example-sol-1"], "claude": ["opus"]}}
        self.spend = {"schemaVersion": 1, "models": {OLD: [{"billing": "subscription", "effectiveFrom": "2026-01-01T00:00:00Z", "effectiveUntil": None}]}}
        self.dev = {"openai": {"models": {"example-sol-1": {"release_date": "2025-01-01"}, "example-sol-2": {"release_date": "2025-02-01"}}}}
        self.opened = {"openai/example-sol-2": {"id": "openai/example-sol-2", "created": 1}}
        self.pi = {OLD, NEW}
        self.paths = [self.root / name for name in ("router.json", "panel.json", "spend.json")]
        self.base = {"sources": {name: {"status": "ok"} for name in ("routerConfig", "consensusConfig", "piCatalog", "modelsDev", "openRouter")},
                     "configuredModels": [{"model": OLD, "source": "model-tier-router", "metered": None}],
                     "findings": [], "piUpdateAvailable": False, "mode": "hybrid"}
        for name, path in zip(("routerConfig", "consensusConfig"), self.paths, strict=False):
            self.base["sources"][name]["path"] = str(path)
        self.refresh = REFRESH.refresh(False, False, False)

    def evidence(self, before=OLD, after=NEW):
        return {"schemaVersion": 1, "recommendations": [{"from": before, "to": after, "checkedAt": "2026-01-09T00:00:00Z",
            "citations": [{"url": "https://vendor.example/release", "quote": "Explicit successor suitable for this role."}],
            "compatibility": {key: f"Reviewed {key} evidence" for key in AUDIT.COMPATIBILITY},
            "routerPolicy": {"metered": False, "consent": "ask", "evidence": "Confirmed subscription routing"},
            "billing": {"billing": "subscription", "effectiveFrom": "2026-01-11T00:00:00Z", "evidence": "Confirmed activation date"}}]}

    def audit(self, evidence=None):
        for path, payload in zip(self.paths, (self.router, self.panel, self.spend), strict=True):
            path.write_text(json.dumps(payload))
        evidence_path = None
        if evidence is not None:
            evidence_path = self.root / "evidence.json"
            evidence_path.write_text(json.dumps(evidence))
        before = {path: path.read_bytes() for path in self.paths}
        result = AUDIT.enrich(copy.deepcopy(self.base), *map(str, self.paths), evidence_path,
                              (self.dev, self.opened, self.pi), self.refresh, NOW)
        self.assertEqual(before, {path: path.read_bytes() for path in self.paths})
        return result

    def test_inventory_preserves_disabled_weights_false_policy_and_native_aliases(self):
        result = self.audit()
        rows = result["configurationInventory"]
        candidates = [r for r in rows if r["source"] == "routerConfig"]
        self.assertEqual([r["weight"] for r in candidates], [25, 75])
        self.assertEqual([r["enabled"] for r in candidates], [False, True])
        self.assertTrue(all(r["metered"] is False for r in candidates))
        self.assertIs(result["configuredModels"][0]["metered"], False)
        aliases = [r for r in rows if r["resolution"] in {"native-alias", "native-default"}]
        self.assertEqual(len(aliases), 3)
        self.assertTrue(all(r["facts"] is None for r in aliases))
        self.assertEqual(result["recommendations"], [])

    def test_complete_catalog_not_top_eight_and_no_release_name_upgrade(self):
        for n in range(12):
            self.dev["openai"]["models"][f"unrelated-{n}"] = {"release_date": "2026-01-10"}
        self.opened["openai/example-sol-2-pro"] = {"id": "openai/example-sol-2-pro"}
        self.opened["openai/example-sol-2-batch"] = {"id": "openai/example-sol-2-batch"}
        result = self.audit()
        self.assertIn(NEW, {r["identity"] for r in result["catalogCandidates"]})
        self.assertTrue(all(r["status"] == "discovered-not-successor" for r in result["catalogCandidates"]))
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(result["verdict"], "INCOMPLETE EVIDENCE")
        leads = result["discoveryLeads"]
        self.assertIn(NEW, {item["to"] for item in leads})
        self.assertFalse(any(item["to"].endswith(("-pro", "-batch")) for item in leads))

    def test_source_failure_retains_other_candidates_without_false_current(self):
        self.dev = {}
        self.base["sources"]["modelsDev"]["status"] = "error"
        result = self.audit()
        self.assertEqual(result["verdict"], "INCOMPLETE EVIDENCE")
        item = next(r for r in result["catalogCandidates"] if r["identity"] == NEW)
        self.assertIs(item["piAvailable"], True)
        self.assertIsNone(item["liveFound"])
        self.assertIsNotNone(item["crossRouteDiscoveryOnly"])

    def test_cross_route_listing_does_not_prove_pi_or_cli_availability(self):
        self.pi.remove(NEW)
        result = self.audit(self.evidence())
        proposal = result["recommendations"][0]
        self.assertEqual(proposal["status"], "incomplete")
        self.assertEqual(proposal["changes"], [])
        row = next(r for r in result["configurationInventory"] if r["identity"] == "local/codex/example-sol-1")
        self.assertIsNone(row["facts"]["piAvailable"])
        self.assertEqual(row["facts"]["runtimeAvailability"], "unknown")

    def test_preview_exact_paths_keeps_history_and_never_copies_consent(self):
        result = self.audit(self.evidence())
        proposal = result["recommendations"][0]
        self.assertEqual(proposal["status"], "optional-upgrade")
        changes = proposal["changes"]
        self.assertEqual(len(changes), 4)
        self.assertEqual(changes[0]["path"], "/tiers/standard/candidates/0/model")
        self.assertEqual(changes[1]["path"], "/tiers/standard/candidates/1/model")
        self.assertTrue(all(len(c["sourceSha256"]) == 64 for c in changes))
        policy = next(c for c in changes if c["source"] == "billingPolicy")
        self.assertEqual(policy["operation"], "add")
        self.assertEqual(policy["path"], "/models/openai-codex~1example-sol-2")
        self.assertTrue(any(c["consentSensitive"] for c in changes))
        self.assertFalse(result["handoff"]["companionAvailable"])

    def test_missing_billing_and_policy_evidence_remains_unknown(self):
        evidence = self.evidence()
        del evidence["recommendations"][0]["billing"]
        del evidence["recommendations"][0]["routerPolicy"]
        proposal = self.audit(evidence)["recommendations"][0]
        self.assertEqual(proposal["status"], "incomplete")
        self.assertEqual(len(proposal["changes"]), 2)
        self.assertEqual(len(proposal["unresolved"]), 2)

    def test_local_pin_and_allowlist_need_native_evidence(self):
        evidence = self.evidence("local/codex/example-sol-1", "local/codex/example-sol-2")
        self.assertEqual(self.audit(evidence)["recommendations"][0]["changes"], [])
        evidence["recommendations"][0]["nativeAvailability"] = "Verified exact CLI model through native catalog documentation"
        proposal = self.audit(evidence)["recommendations"][0]
        self.assertEqual(proposal["status"], "optional-upgrade")
        self.assertEqual(len(proposal["changes"]), 2)
        allow = next(c for c in proposal["changes"] if c["consentSensitive"])
        self.assertEqual(allow["after"], ["example-sol-1", "example-sol-2"])
        self.assertEqual(allow["path"], "/subscriptionRoutes/codex")

    def test_aliases_are_not_replaced_even_with_evidence(self):
        evidence = self.evidence("local/claude/opus", "local/claude/new-pin")
        evidence["recommendations"][0]["nativeAvailability"] = "verified"
        result = self.audit(evidence)
        self.assertEqual(result["recommendations"][0]["changes"], [])
        self.assertIn("Native aliases", " ".join(result["recommendations"][0]["unresolved"]))

    def test_spend_missing_invalid_uncovered_and_overlap_fail_closed(self):
        self.spend = {"schemaVersion": 1, "models": {OLD: [{"billing": "subscription", "effectiveFrom": "2026-01-20T00:00:00Z", "effectiveUntil": None}]}}
        result = self.audit()
        self.assertTrue(any(f["kind"] == "spend-uncovered" for f in result["findings"]))
        self.spend["models"][OLD].append(self.spend["models"][OLD][0])
        result = self.audit(self.evidence())
        self.assertEqual(result["sources"]["billingPolicy"]["status"], "partial")
        self.assertTrue(any("Repair" in u for u in result["recommendations"][0]["unresolved"]))
        self.spend = {}
        self.assertEqual(self.audit()["sources"]["billingPolicy"]["status"], "invalid")
        payload, metadata = AUDIT.snapshot(self.root / "does-not-exist")
        self.assertEqual(metadata["status"], "missing")
        self.assertEqual(payload, {})

    def test_new_interval_never_changes_existing_intervals(self):
        self.spend["models"][NEW] = [{"billing": "metered", "effectiveFrom": "2025-12-01T00:00:00Z", "effectiveUntil": "2026-01-01T00:00:00Z"}]
        proposal = self.audit(self.evidence())["recommendations"][0]
        change = next(c for c in proposal["changes"] if c["source"] == "billingPolicy")
        self.assertEqual(change["after"][:-1], change["before"])
        self.spend["models"][NEW][0]["effectiveUntil"] = None
        proposal = self.audit(self.evidence())["recommendations"][0]
        self.assertFalse(any(c["source"] == "billingPolicy" for c in proposal["changes"]))
        self.assertTrue(any("overlap" in message for message in proposal["unresolved"]))

    def test_preview_refuses_historical_backfill_even_with_billing_claim(self):
        evidence = self.evidence()
        evidence["recommendations"][0]["billing"]["effectiveFrom"] = "2026-01-01T00:00:00Z"
        proposal = self.audit(evidence)["recommendations"][0]
        self.assertEqual(proposal["status"], "incomplete")
        self.assertFalse(any(c["source"] == "billingPolicy" for c in proposal["changes"]))
        self.assertTrue(any("past" in msg for msg in proposal["unresolved"]))

    def test_duplicate_interval_proposes_no_duplicate(self):
        evidence = self.evidence()
        interval = evidence["recommendations"][0]["billing"]
        self.spend["models"][NEW] = [{"billing": interval["billing"], "effectiveFrom": interval["effectiveFrom"], "effectiveUntil": None}]
        result = self.audit(evidence)
        self.assertFalse(any(c["source"] == "billingPolicy" for c in result["recommendations"][0]["changes"]))

    def test_evidence_stale_malformed_oversized_and_cross_route_rejected(self):
        for field, value in (("checkedAt", "2025-01-01T00:00:00Z"), ("checkedAt", "2027-01-01T00:00:00Z"),
                             ("to", "local/codex/example-sol-2"), ("to", []), ("compatibility", {}), ("citations", []),
                             ("billing", None), ("routerPolicy", None), ("nativeAvailability", None)):
            with self.subTest(field=field, value=value):
                evidence = self.evidence()
                evidence["recommendations"][0][field] = value
                self.assertFalse(AUDIT.validate_evidence(evidence, NOW))
        path = self.root / "oversize.json"
        path.write_text(" " * (AUDIT.MAX_EVIDENCE_BYTES + 1))
        self.assertEqual(AUDIT.snapshot(path, AUDIT.MAX_EVIDENCE_BYTES)[1]["status"], "invalid")
        path.write_text('{"schemaVersion":1,"schemaVersion":2}')
        self.assertEqual(AUDIT.snapshot(path)[1]["status"], "invalid")

    def test_invalid_subscription_allowlist_blocks_preview(self):
        self.panel["subscriptionRoutes"] = {"codex": "not-an-array"}
        result = self.audit(self.evidence())
        self.assertEqual(result["sources"]["consensusConfig"]["status"], "invalid")
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(result["verdict"], "REVIEW CONFIG")

    def test_failed_refresh_keeps_incomplete_verdict_even_after_catalog_read(self):
        self.refresh = {**self.refresh, "status": "failed", "attempted": True}
        result = self.audit()
        self.assertFalse(result["readOnly"])
        self.assertFalse(result["refresh"]["fresh"])
        self.assertEqual(result["verdict"], "INCOMPLETE EVIDENCE")

    def test_native_success_followed_by_bad_enumeration_is_not_fresh(self):
        self.refresh = {**self.refresh, "status": "ok", "attempted": True, "fresh": True}
        self.base["sources"]["piCatalog"]["status"] = "invalid-output"
        result = self.audit()
        self.assertTrue(result["refresh"]["nativeCompleted"])
        self.assertFalse(result["refresh"]["fresh"])

    def test_invalid_policy_type_is_unknown_not_free(self):
        self.router["modelPolicies"][OLD]["consent"] = []
        result = self.audit()
        row = result["configurationInventory"][0]
        self.assertIsNone(row["metered"])
        self.assertEqual(row["policyBasis"], "invalid")
        self.assertTrue(any(f["kind"] == "router-policy-unknown" for f in result["findings"]))

    def test_current_identity_with_unmapped_live_provider_is_incomplete(self):
        self.dev = {}
        self.opened = {}
        self.pi = {OLD}
        result = self.audit()
        self.assertEqual(result["verdict"], "INCOMPLETE EVIDENCE")
        self.assertIn(OLD, " ".join(result["incompleteReasons"]))

    def test_malformed_config_identity_and_policy_fail_closed(self):
        for bad_model in ("/broken", "broken/", "bad model/name"):
            with self.subTest(model=bad_model):
                self.router["tiers"]["standard"]["candidates"][0]["model"] = bad_model
                result = self.audit(self.evidence())
                self.assertEqual(result["sources"]["routerConfig"]["status"], "invalid")
                self.assertFalse(any(c["source"] == "routerConfig" for p in result["recommendations"] for c in p["changes"]))
        self.router["tiers"]["standard"]["candidates"][0]["model"] = OLD
        self.router["modelPolicies"] = None
        proposal = self.audit(self.evidence())["recommendations"][0]
        self.assertEqual(proposal["status"], "incomplete")
        self.assertTrue(any("invalid" in msg for msg in proposal["unresolved"]))

    def test_router_projection_inline_false_conflict_explicit_and_unknown(self):
        router = copy.deepcopy(self.router)
        del router["modelPolicies"]
        router["tiers"]["standard"]["candidates"][0]["metered"] = False
        self.assertEqual(AUDIT.router_policy(router, OLD), (False, "inline", "ask"))
        router["tiers"]["standard"]["candidates"][1]["metered"] = True
        self.assertEqual(AUDIT.router_policy(router, OLD), (True, "inline-conflict", "ask"))
        router["modelPolicies"] = {OLD: {"metered": False}}
        self.assertEqual(AUDIT.router_policy(router, OLD), (False, "modelPolicies", "ask"))
        router["modelPolicies"][OLD]["metered"] = "false"
        self.assertEqual(AUDIT.router_policy(router, OLD), (None, "invalid", None))
        self.assertEqual(AUDIT.router_policy(router, NEW), (None, "unknown", None))


class RefreshTests(unittest.TestCase):
    @patch.object(REFRESH, "run_native")
    def test_default_denied_offline_and_invalid_confirmation_never_run(self, native):
        for requested, confirmed, offline, expected in ((False, False, False, "not-requested"),
                (False, False, True, "not-requested"), (True, False, False, "authorization-required"),
                (True, True, True, "offline-conflict"), (False, True, False, "invalid-confirmation")):
            result = REFRESH.refresh(requested, confirmed, offline)
            self.assertEqual(result["status"], expected)
            self.assertFalse(result["attempted"])
        native.assert_not_called()

    @patch.object(REFRESH, "run_native")
    def test_only_exact_models_command_after_capability_check(self, native):
        native.side_effect = [("ok", "  --models  Refresh model catalogs only\n"), ("ok", "secret must never be shown")]
        result = REFRESH.refresh(True, True, False)
        self.assertTrue(result["fresh"])
        self.assertTrue(result["attempted"])
        self.assertNotIn("secret", json.dumps(result))
        self.assertEqual([call.args[0] for call in native.call_args_list], [["pi", "update", "--help"], ["pi", "update", "--models"]])

    @patch.object(REFRESH, "run_native")
    def test_unsupported_timeout_failure_do_not_claim_freshness_or_fallback(self, native):
        native.return_value = ("ok", "pi update --all")
        self.assertEqual(REFRESH.refresh(True, True, False)["status"], "unsupported")
        self.assertEqual(native.call_count, 1)
        for status in ("timeout", "failed", "unavailable"):
            native.reset_mock()
            native.side_effect = [("ok", " --models Refresh model catalogs only"), (status, "")]
            result = REFRESH.refresh(True, True, False)
            self.assertFalse(result["fresh"])
            self.assertEqual(result["status"], status)
            self.assertEqual(native.call_count, 2)

    def test_real_subprocess_timeout_and_missing_executable(self):
        status, output = REFRESH.run_native([sys.executable, "-c", "import time; time.sleep(5)"], 0.05)
        self.assertEqual((status, output), ("timeout", ""))
        self.assertEqual(REFRESH.run_native(["/nonexistent/audit-command"], 1), ("unavailable", ""))

    @patch.object(REFRESH.Path, "is_file", return_value=True)
    @patch.object(REFRESH, "run_native")
    def test_enumeration_is_offline_and_disables_executable_resources(self, native, _exists):
        native.side_effect = [("ok", "0.87.1"), ("ok", "provider model context max-out thinking images\nexample model 1M 32K yes yes\n")]
        result = REFRESH.collect_catalog()
        self.assertEqual(result["models"], [{"provider": "example", "model": "model"}])
        command = native.call_args_list[1].args[0]
        self.assertIn("--offline", command)
        self.assertIn("--no-extensions", command)
        self.assertIn("--no-approve", command)
        self.assertNotIn("update", command)

    @patch.object(REFRESH.Path, "is_file", return_value=True)
    @patch.object(REFRESH, "run_native")
    def test_malformed_enumeration_does_not_become_empty_success(self, native, _exists):
        native.side_effect = [("ok", "0.87.1"), ("ok", "unexpected output")]
        self.assertEqual(REFRESH.collect_catalog()["status"], "invalid-output")

    @patch.object(REFRESH, "run_native", return_value=("ok", "unexpected-native-output"))
    def test_unexpected_version_is_not_echoed(self, native):
        result = REFRESH.collect_catalog()
        self.assertEqual(result["status"], "invalid-version")
        self.assertNotIn("unexpected-native-output", json.dumps(result))
        self.assertEqual(native.call_count, 1)

    @patch.object(REFRESH.Path, "is_file", return_value=False)
    @patch.object(REFRESH, "run_native", return_value=("ok", "0.87.1"))
    def test_missing_native_auth_store_prevents_implicit_creation(self, native, _exists):
        self.assertEqual(REFRESH.collect_catalog()["status"], "auth-store-absent")
        self.assertEqual(native.call_count, 1)


if __name__ == "__main__":
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    unittest.main()
