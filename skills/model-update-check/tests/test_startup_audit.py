"""Startup configuration facts only: no launches, credentials or user config writes."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from test_migration_audit import AUDIT, NEW, NOW, OLD, REFRESH


class StartupAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = {name: self.root / (name + ".json") for name in (
            "routerConfig", "consensusConfig", "billingPolicy", "launcherConfig", "piSettings")}
        self.router = {"enabled": True, "tiers": {"premium": {"candidates": [
            {"model": OLD, "enabled": False}, {"model": NEW, "enabled": True}]}},
            "modelPolicies": {OLD: {"metered": False}, NEW: {"metered": False}}}
        self.settings = {"defaultProvider": "openai-codex", "defaultModel": "example-sol-0",
                         "defaultThinkingLevel": "medium", "enabledModels": [NEW]}
        self.launcher = {"defaultModel": OLD, "defaultThinking": "high"}
        self.write("routerConfig", self.router)
        self.write("consensusConfig", {"profiles": {}})
        self.write("billingPolicy", {"schemaVersion": 1, "models": {}})
        self.write("launcherConfig", self.launcher)
        self.write("piSettings", self.settings)
        self.base = {"sources": {name: {"status": "ok"} for name in (
            "routerConfig", "consensusConfig", "piCatalog", "modelsDev", "openRouter")},
            "configuredModels": [], "findings": [], "piUpdateAvailable": False}
        for name in ("routerConfig", "consensusConfig"):
            self.base["sources"][name]["path"] = str(self.paths[name])

    def write(self, name, value):
        self.paths[name].write_text(json.dumps(value))

    def audit(self, required=False):
        before = {p: p.read_bytes() for p in self.paths.values() if p.exists()}
        result = AUDIT.enrich(
            copy.deepcopy(self.base), self.paths["routerConfig"], self.paths["consensusConfig"],
            self.paths["billingPolicy"], None, ({}, {}, {OLD, NEW}),
            REFRESH.refresh(False, False, False), NOW,
            startup_paths={name: {"snapshot": str(self.paths[name]), "path": "/selected/" + name + ".json",
                                  "required": required} for name in ("launcherConfig", "piSettings")})
        self.assertEqual(before, {p: p.read_bytes() for p in self.paths.values() if p.exists()})
        return result

    def test_reports_drift_and_source_provenance_without_migration_changes(self):
        result = self.audit()
        audit = result["startupAudit"]
        self.assertEqual(audit["defaults"]["launcherConfig"]["identity"], OLD)
        self.assertEqual(audit["defaults"]["piSettings"]["identity"], "openai-codex/example-sol-0")
        self.assertEqual(audit["defaults"]["launcherConfig"]["routerMembership"], "disabled-candidate")
        self.assertEqual(audit["defaults"]["piSettings"]["routerMembership"], "not-configured")
        self.assertEqual(audit["defaults"]["piSettings"]["enabledModelsMembership"], "not-exactly-listed")
        self.assertIn("startup-defaults-disagree", {f["code"] for f in audit["findings"]})
        self.assertEqual(result["interaction"]["primaryAction"]["kind"], "inspect-startup")
        self.assertEqual(result["verdict"], "REVIEW CONFIG")
        for name in ("launcherConfig", "piSettings"):
            meta = result["sources"][name]
            self.assertEqual(meta["status"], "ok")
            self.assertEqual(meta["path"], "/selected/" + name + ".json")
            self.assertEqual(meta["sha256"], hashlib.sha256(self.paths[name].read_bytes()).hexdigest())
            self.assertEqual(audit["defaults"][name]["config"], meta["path"])
        self.assertEqual(result["recommendations"], [])
        self.assertFalse(any(r["source"] in {"launcherConfig", "piSettings"}
                             for r in result["configurationInventory"]))

    def test_healthy_defaults_match_enabled_router_and_scope(self):
        self.launcher["defaultModel"] = NEW
        self.settings["defaultModel"] = NEW.split("/", 1)[1]
        self.write("launcherConfig", self.launcher)
        self.write("piSettings", self.settings)
        audit = self.audit()["startupAudit"]
        self.assertEqual(audit["findings"], [])
        for row in audit["defaults"].values():
            self.assertEqual(row["enabledModelsMembership"], "exact-match")
            self.assertEqual(row["routerMembership"], "enabled-candidate")
        self.assertTrue(audit["auditOnly"])

    def test_launch_paths_do_not_guess_resume_or_orca_model(self):
        paths = {row["path"]: row for row in self.audit()["startupAudit"]["launchPaths"]}
        self.assertEqual(paths["fresh-pl"]["configuredSelection"], OLD)
        self.assertEqual(paths["plain-pi"]["firstEnabledExpression"], NEW)
        for name in ("plain-pi", "resume-continue", "orca"):
            self.assertIsNone(paths[name]["runtimeModel"])
        self.assertIn("project", paths["plain-pi"]["selectionRule"])
        self.assertIn("session", paths["resume-continue"]["selectionRule"])
        self.assertIn("host", paths["orca"]["selectionRule"])

    def test_scope_patterns_suffixes_and_bare_ids_stay_unresolved(self):
        for pattern in ("openai-codex/*", "example-sol", NEW + ":high", "EXAMPLE-SOL-2", "[a-z]*"):
            with self.subTest(pattern=pattern):
                self.settings["enabledModels"] = [pattern]
                self.write("piSettings", self.settings)
                audit = self.audit()["startupAudit"]
                self.assertEqual(audit["defaults"]["launcherConfig"]["enabledModelsMembership"], "unresolved-patterns")
                self.assertNotIn("startup-default-not-listed", {f["code"] for f in audit["findings"]})
        self.settings["enabledModels"] = ["openai-codex/*", OLD]
        self.write("piSettings", self.settings)
        self.assertEqual(self.audit()["startupAudit"]["defaults"]["launcherConfig"]["enabledModelsMembership"], "exact-match")

    def test_case_variants_are_unresolved_not_absent(self):
        self.settings["enabledModels"] = [OLD.upper()]
        self.write("piSettings", self.settings)
        row = self.audit()["startupAudit"]["defaults"]["launcherConfig"]
        self.assertEqual(row["enabledModelsMembership"], "unresolved-patterns")

    def test_empty_and_missing_scope_are_unrestricted(self):
        for value in ([], None):
            if value is None:
                self.settings.pop("enabledModels", None)
            else:
                self.settings["enabledModels"] = value
            self.write("piSettings", self.settings)
            self.assertEqual(self.audit()["startupAudit"]["defaults"]["launcherConfig"]["enabledModelsMembership"], "unrestricted")

    def test_aliases_and_incomplete_default_identity_are_not_compared(self):
        self.launcher["defaultModel"] = "sonnet:high"
        self.settings.pop("defaultProvider")
        self.write("launcherConfig", self.launcher)
        self.write("piSettings", self.settings)
        audit = self.audit()["startupAudit"]
        for row in audit["defaults"].values():
            self.assertIsNone(row["identity"])
            self.assertEqual(row["enabledModelsMembership"], "unknown")
        self.assertNotIn("startup-defaults-disagree", {f["code"] for f in audit["findings"]})

    def test_router_disabled_or_unavailable_is_not_default_drift(self):
        for state in ("disabled", "missing"):
            if state == "disabled":
                self.router["enabled"] = False
                self.write("routerConfig", self.router)
            else:
                self.paths["routerConfig"].unlink()
            audit = self.audit()["startupAudit"]
            for row in audit["defaults"].values():
                self.assertEqual(row["routerMembership"], "router-disabled" if state == "disabled" else "unknown")
            self.assertNotIn("startup-not-router-enabled", {f["code"] for f in audit["findings"]})

    def test_missing_default_sources_do_not_become_invalid_or_guess_builtins(self):
        self.paths["launcherConfig"].unlink()
        self.paths["piSettings"].unlink()
        result = self.audit()
        for name in ("launcherConfig", "piSettings"):
            self.assertEqual(result["sources"][name]["status"], "missing")
            self.assertIsNone(result["startupAudit"]["defaults"][name]["identity"])
        self.assertEqual(result["startupAudit"]["findings"], [])
        result = self.audit(required=True)
        self.assertEqual(result["interaction"]["primaryAction"]["kind"], "inspect-startup")

    def test_invalid_files_and_fields_are_redacted_and_preserve_digests(self):
        cases = ('{"defaultModel":', '{"defaultModel":"a","defaultModel":"b"}',
                 '{"ignored":NaN}', '[]', '{"defaultModel":true}',
                 '{"defaultModel":"SECRET\\nVALUE"}', '{"defaultThinking":"SECRET"}')
        for raw in cases:
            with self.subTest(raw=raw):
                self.paths["launcherConfig"].write_text(raw)
                result = self.audit()
                self.assertEqual(result["sources"]["launcherConfig"]["status"], "invalid")
                self.assertEqual(result["sources"]["launcherConfig"]["sha256"], hashlib.sha256(raw.encode()).hexdigest())
                self.assertIsNone(result["startupAudit"]["defaults"]["launcherConfig"]["identity"])
                self.assertNotIn("SECRET", json.dumps(result))
                self.assertEqual(result["interaction"]["primaryAction"]["kind"], "inspect-startup")
        self.paths["launcherConfig"].write_bytes(b" " * (AUDIT.MAX_CONFIG_BYTES + 1))
        self.assertEqual(self.audit()["sources"]["launcherConfig"]["status"], "invalid")

    def test_invalid_scope_and_thinking_fields_are_not_emitted(self):
        for field, value in (("enabledModels", True), ("enabledModels", ["SECRET\nVALUE"]),
                             ("enabledModels", [NEW] * 257), ("defaultThinkingLevel", "SECRET"),
                             ("defaultProvider", 3)):
            with self.subTest(field=field):
                self.write("piSettings", {**self.settings, field: value})
                result = self.audit()
                self.assertEqual(result["sources"]["piSettings"]["status"], "invalid")
                self.assertNotIn("SECRET", json.dumps(result))

    def test_unrelated_settings_and_credentials_are_not_exposed(self):
        self.write("piSettings", {**self.settings, "apiKey": "SECRET", "mcp": {"token": "SECRET"}})
        result = self.audit()
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertNotIn("apiKey", json.dumps(result))

    def test_same_model_on_different_provider_is_distinct(self):
        self.launcher["defaultModel"] = "different/example-sol-0"
        self.settings["enabledModels"] = ["openai-codex/example-sol-0"]
        self.write("launcherConfig", self.launcher)
        self.write("piSettings", self.settings)
        audit = self.audit()["startupAudit"]
        self.assertEqual(audit["defaults"]["launcherConfig"]["enabledModelsMembership"], "not-exactly-listed")
        self.assertIn("startup-defaults-disagree", {f["code"] for f in audit["findings"]})

    def test_directory_is_unreadable_not_missing(self):
        self.paths["launcherConfig"].unlink()
        self.paths["launcherConfig"].mkdir()
        # Direct source projection avoids treating a directory as a fixture file.
        sources = copy.deepcopy(self.base["sources"])
        result = AUDIT.STARTUP.audit(
            {name: {"snapshot": str(self.paths[name]), "path": str(self.paths[name])}
             for name in ("launcherConfig", "piSettings")},
            AUDIT.snapshot, sources, self.router, [])
        self.assertEqual(sources["launcherConfig"]["status"], "invalid")
        self.assertTrue(any(f["code"] == "startup-config-unavailable" for f in result["findings"]))

    def test_supplied_preview_stays_primary_without_hiding_startup_findings(self):
        result = self.audit()
        interaction = AUDIT.interaction_plan(result["sources"], [], [{"status": "optional-upgrade"}],
                                              [], [], result["findings"])
        self.assertEqual(interaction["primaryAction"]["kind"], "review-preview")
        self.assertTrue(interaction["startupFindings"])

    def test_offline_catalog_does_not_hide_known_startup_drift(self):
        self.base["sources"]["piCatalog"]["status"] = "error"
        self.base["sources"]["modelsDev"]["status"] = "skipped"
        result = self.audit()
        self.assertEqual(result["verdict"], "REVIEW CONFIG")
        self.assertIn("piCatalog", result["incompleteSources"])
        self.assertEqual(result["interaction"]["primaryAction"]["kind"], "inspect-startup")


if __name__ == "__main__":
    unittest.main()
