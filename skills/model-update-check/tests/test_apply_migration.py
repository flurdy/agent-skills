"""Synthetic preview/apply contract; never touches the user's configuration."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/apply_migration.py"
spec = importlib.util.spec_from_file_location("apply_migration_test", SCRIPT)
apply = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = apply
spec.loader.exec_module(apply)


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        configs = self.root / "configs"
        configs.mkdir()
        self.paths = {name: configs / (name + ".json") for name in ("routerConfig", "consensusConfig", "billingPolicy")}
        self.data = {
            "routerConfig": {"tiers": {"standard": {"selection": "weighted-random", "candidates": [
                {"model": "openai-codex/old", "weight": 3, "enabled": True}]}},
                "modelPolicies": {"openai-codex/old": {"metered": False}}, "unrelated": {"keep": 1}},
            "consensusConfig": {"version": 1, "profiles": {"premium": {"quorum": 1, "consensusQuorum": 1,
                "routes": [{"id": "codex", "kind": "local", "agent": "codex", "model": "old", "role": "review"}],
                "limits": {"maxParallel": 1, "maxPromptBytes": 1024, "maxOutputTokensPerModel": 2000, "defaultTimeoutSeconds": 30}}},
                "subscriptionRoutes": {"codex": ["old"]}},
            "billingPolicy": {"schemaVersion": 1, "models": {"openai-codex/old": [
                {"effectiveFrom": "2026-01-01T00:00:00Z", "effectiveUntil": None, "billing": "subscription"}]}}
        }
        for name, path in self.paths.items():
            path.write_text(json.dumps(self.data[name], indent=2) + "\n")
        self.backups = self.root / "backups"
        self.backups.mkdir(mode=0o700)
        self.now = datetime.now(timezone.utc)
        start = (self.now + timedelta(days=1)).isoformat().replace("+00:00", "Z")
        changes = [
            self.change("routerConfig", "/tiers/standard/candidates/0/model", "replace", "openai-codex/old", "openai-codex/new"),
            self.change("routerConfig", "/modelPolicies/openai-codex~1new", "add", None, {"metered": False, "consent": "ask"}, True),
            self.change("consensusConfig", "/profiles/premium/routes/0/model", "replace", "old", "new"),
            self.change("consensusConfig", "/subscriptionRoutes/codex", "replace", ["old"], ["old", "new"], True),
            self.change("billingPolicy", "/models/openai-codex~1new", "add", None, [
                {"effectiveFrom": start, "effectiveUntil": None, "billing": "subscription"}]),
        ]
        def evidence(before, after, **extra):
            return {"from": before, "to": after,
                    "checkedAt": self.now.isoformat().replace("+00:00", "Z"),
                    "citations": [{"url": "https://example.org/model", "quote": "Reviewed exact model relationship."}],
                    "compatibility": {key: "Reviewed for this role" for key in
                                      ("role", "stability", "reasoning", "modalities", "limits", "pricing", "billingRoute")},
                    **extra}
        self.report = {"schemaVersion": 2, "generatedAt": self.now.isoformat().replace("+00:00", "Z"),
                       "sources": {**{name: {"path": str(path), "sha256": self.sha(path),
                                            "status": "complete" if name == "billingPolicy" else "ok"}
                                      for name, path in self.paths.items()},
                                   "releaseEvidence": {"status": "ok"}},
                       "refresh": {"status": "not-requested"},
                       "recommendations": [{"from": "openai-codex/old", "to": "openai-codex/new",
                                            "status": "optional-upgrade", "unresolved": [],
                                            "evidenceTrust": "reviewed-input-not-independently-verified",
                                            "evidence": evidence("openai-codex/old", "openai-codex/new",
                                                routerPolicy={"metered": False, "consent": "ask", "evidence": "Owner approved exact policy"},
                                                billing={"billing": "subscription", "effectiveFrom": start, "evidence": "Owner approved start"}),
                                            "changes": [changes[0], changes[1], changes[4]]},
                                           {"from": "local/codex/old", "to": "local/codex/new",
                                            "status": "optional-upgrade", "unresolved": [],
                                            "evidenceTrust": "reviewed-input-not-independently-verified",
                                            "evidence": evidence("local/codex/old", "local/codex/new", nativeAvailability="Verified native CLI model"),
                                            "changes": [changes[2], changes[3]]}]}
        self.report_bytes = json.dumps(self.report).encode()

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def change(self, source, pointer, operation, before, after, consent=False):
        return {"source": source, "config": str(self.paths[source]),
                "sourceSha256": self.sha(self.paths[source]), "path": pointer,
                "operation": operation, "before": before, "after": after,
                "consentSensitive": consent, "authorization": "separate-current-run-required"}

    def plan(self, report=None, selection=(1, 2), validator=lambda _: None):
        return apply.prepare(self.report_bytes if report is None else json.dumps(report).encode(),
                             selection, now=self.now, validate=validator)

    def test_preview_is_bound_and_does_not_write_targets(self):
        before = {key: self.sha(path) for key, path in self.paths.items()}
        plan = self.plan()
        self.assertEqual(before, {key: self.sha(path) for key, path in self.paths.items()})
        self.assertEqual(len(plan["files"]), 3)
        self.assertTrue(all(row["unrelatedUnchanged"] for row in plan["files"]))
        self.assertTrue(plan["consentSensitive"])
        self.assertEqual(len(plan["digest"]), 64)
        self.assertEqual(plan["files"][0]["sourceSha256"], before[plan["files"][0]["source"]])
        self.assertTrue(all(row["status"] == "pending" for row in plan["files"]))

    def test_single_selection_keeps_other_file_byte_identical(self):
        plan = self.plan(selection=(1,))
        unchanged = next(row for row in plan["files"] if row["source"] == "consensusConfig")
        self.assertEqual(unchanged["status"], "unchanged")
        self.assertEqual(unchanged["currentSha256"], unchanged["afterSha256"])

    def test_owner_validation_reuses_offline_audit_schema(self):
        with patch.dict(os.environ, {"HOME": str(self.root), "PI_CODING_AGENT_DIR": str(self.root / "empty-agent")}):
            plan = self.plan(validator=apply.owner_validate)
            self.assertEqual(len(plan["files"]), 3)
            self.data["consensusConfig"]["profiles"]["premium"]["limits"]["maxParallel"] = 9
            self.paths["consensusConfig"].write_text(json.dumps(self.data["consensusConfig"], indent=2) + "\n")
            report = copy.deepcopy(self.report)
            report["sources"]["consensusConfig"]["sha256"] = self.sha(self.paths["consensusConfig"])
            for rec in report["recommendations"]:
                for change in rec["changes"]:
                    if change["source"] == "consensusConfig":
                        change["sourceSha256"] = report["sources"]["consensusConfig"]["sha256"]
            with self.assertRaises(apply.Refused):
                self.plan(report, validator=apply.owner_validate)

    def test_denied_or_missing_authority_never_writes(self):
        plan = self.plan()
        before = {key: self.sha(path) for key, path in self.paths.items()}
        with self.assertRaises(apply.Refused):
            apply.apply_plan(plan, self.root / "missing-backups", allowed=set(), confirm=lambda _: True)
        with self.assertRaises(apply.Refused):
            apply.apply_plan(plan, self.backups, allowed={Path(row["realPath"]) for row in plan["files"]}, confirm=lambda _: False)
        self.assertEqual(before, {key: self.sha(path) for key, path in self.paths.items()})

    def test_success_preserves_unrelated_data_and_idempotent_retry(self):
        plan = self.plan()
        allowed = {Path(row["realPath"]) for row in plan["files"]}
        outcome = apply.apply_plan(plan, self.backups, allowed=allowed, confirm=lambda _: True, validate=lambda _: None)
        self.assertEqual(outcome["status"], "applied")
        self.assertEqual([r["status"] for r in outcome["files"]], ["applied"] * 3)
        self.assertTrue(all(Path(r["backup"]).is_file() for r in outcome["files"]))
        self.assertEqual(json.loads(self.paths["routerConfig"].read_text())["unrelated"], {"keep": 1})
        self.assertEqual(json.loads(self.paths["routerConfig"].read_text())["tiers"]["standard"]["candidates"][0]["weight"], 3)
        self.assertEqual(json.loads(self.paths["consensusConfig"].read_text())["profiles"]["premium"]["quorum"], 1)
        self.assertEqual(json.loads(self.paths["billingPolicy"].read_text())["models"]["openai-codex/old"], self.data["billingPolicy"]["models"]["openai-codex/old"])
        retry = self.plan()
        self.assertTrue(all(row["status"] == "already-applied" for row in retry["files"]))
        self.assertTrue(all(row["unrelatedUnchanged"] is None for row in retry["files"]))
        self.assertEqual(apply.apply_plan(retry, self.backups, allowed=allowed, confirm=lambda _: True)["status"], "already-applied")
        self.assertEqual(len(json.loads(self.paths["billingPolicy"].read_text())["models"]["openai-codex/new"]), 1)
        modified = json.loads(self.paths["routerConfig"].read_text())
        modified["unrelated"] = {"newer": 2}
        self.paths["routerConfig"].write_text(json.dumps(modified))
        followup = self.plan()
        row = next(row for row in followup["files"] if row["source"] == "routerConfig")
        self.assertEqual(row["status"], "already-applied")
        self.assertIsNone(row["unrelatedUnchanged"])
        self.assertEqual(apply.apply_plan(followup, self.backups, allowed=allowed, confirm=lambda _: True)["status"], "already-applied")
        self.assertEqual(json.loads(self.paths["routerConfig"].read_text())["unrelated"], {"newer": 2})

    def test_stale_or_invalid_report_fails_closed(self):
        self.paths["routerConfig"].write_text(self.paths["routerConfig"].read_text() + " ")
        with self.assertRaises(apply.Refused):
            self.plan()
        self.paths["routerConfig"].write_text(json.dumps(self.data["routerConfig"], indent=2) + "\n")
        for mutate in (
            lambda report: report.update(schemaVersion=1),
            lambda report: report["recommendations"][0].update(status="incomplete"),
            lambda report: report["recommendations"][0]["changes"][0].update(authorization="none"),
            lambda report: report["recommendations"][0]["changes"][1].update(operation="replace"),
            lambda report: report["recommendations"][0]["changes"][1].update(path="/tiers/standard"),
            lambda report: report["recommendations"][0]["changes"][2]["after"][0].update(effectiveFrom="2020-01-01T00:00:00Z"),
            lambda report: report["recommendations"][0].pop("evidence"),
            lambda report: report["recommendations"][0]["evidence"].pop("billing"),
            lambda report: report["recommendations"][0]["evidence"].pop("routerPolicy"),
            lambda report: report["recommendations"][1]["changes"][1].update(consentSensitive=False),
            lambda report: report["recommendations"][1]["evidence"].pop("nativeAvailability"),
            lambda report: report["recommendations"][1]["changes"][0].update(source="routerConfig"),
            lambda report: report["recommendations"][0]["changes"][2]["after"].insert(0, {"effectiveFrom": "2026-01-01T00:00:00Z", "effectiveUntil": None, "billing": "metered"}),
        ):
            with self.subTest(mutate=mutate):
                report = copy.deepcopy(self.report)
                mutate(report)
                with self.assertRaises(apply.Refused):
                    self.plan(report)

    def test_billing_start_is_rechecked_before_writing(self):
        plan = self.plan()
        allowed = {Path(row["realPath"]) for row in plan["files"]}
        before = {key: self.sha(path) for key, path in self.paths.items()}
        late = self.now + timedelta(days=2)
        class LateClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return late
        with patch.object(apply, "datetime", LateClock), self.assertRaises(apply.Refused):
            apply.apply_plan(plan, self.backups, allowed=allowed, confirm=lambda _: True, validate=lambda _: None)
        self.assertEqual(before, {key: self.sha(path) for key, path in self.paths.items()})

    def test_duplicate_json_keys_and_overlapping_pointers_rejected(self):
        with self.assertRaises(apply.Refused):
            apply.prepare(b'{"schemaVersion":2,"schemaVersion":2}', [1], now=self.now, validate=lambda _: None)
        duplicate = copy.deepcopy(self.report)
        duplicate["recommendations"][0]["changes"].append(copy.deepcopy(duplicate["recommendations"][0]["changes"][0]))
        with self.assertRaises(apply.Refused):
            self.plan(duplicate)

    def test_partial_failure_reports_backups_without_rollback(self):
        plan = self.plan()
        allowed = {Path(row["realPath"]) for row in plan["files"]}
        writes = []
        def writer(path, data, mode):
            writes.append(path)
            if len(writes) == 2:
                raise OSError("injected write failure")
            apply.atomic_write(path, data, mode)
        outcome = apply.apply_plan(plan, self.backups, allowed=allowed, confirm=lambda _: True,
                                   writer=writer, validate=lambda _: None)
        self.assertEqual(outcome["status"], "partial")
        self.assertEqual([row["status"] for row in outcome["files"]], ["applied", "failed", "not-attempted"])
        self.assertTrue(all(Path(row["backup"]).is_file() for row in outcome["files"]))

    def test_noninteractive_cli_apply_refuses_without_touching_configs(self):
        report_file = self.root / "report.json"
        report_file.write_bytes(self.report_bytes)
        before = {key: self.sha(path) for key, path in self.paths.items()}
        with patch.dict(os.environ, {"HOME": str(self.root), "PI_CODING_AGENT_DIR": str(self.root / "empty-agent")}):
            preview = subprocess.run([sys.executable, "-B", str(SCRIPT), "--report", str(report_file),
                                      "--select", "1", "--select", "2"], capture_output=True, text=True, timeout=60)
            self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
            self.assertEqual(len(json.loads(preview.stdout)["files"]), 3)
            denied = subprocess.run([sys.executable, "-B", str(SCRIPT), "--report", str(report_file),
                                     "--select", "1", "--select", "2", "--apply",
                                     *sum((["--allow-target", str(path)] for path in self.paths.values()), [])],
                                    capture_output=True, text=True, timeout=60)
        self.assertEqual(denied.returncode, 2)
        self.assertIn("interactive terminal", denied.stdout)
        self.assertEqual(before, {key: self.sha(path) for key, path in self.paths.items()})

    def test_attended_success_reruns_read_only_audit(self):
        report_file = self.root / "report.json"
        report_file.write_bytes(self.report_bytes)
        expected = self.plan()["digest"]
        class TTY(io.StringIO):
            def isatty(self):
                return True
        output = TTY()
        argv = ["apply_migration.py", "--report", str(report_file), "--select", "1", "--select", "2",
                "--apply", "--backup-root", str(self.backups)]
        for path in self.paths.values():
            argv.extend(["--allow-target", str(path)])
        with (patch.dict(os.environ, {"HOME": str(self.root), "PI_CODING_AGENT_DIR": str(self.root / "empty-agent")}),
              patch.object(sys, "argv", argv), patch.object(sys, "stdin", TTY()),
              patch.object(sys, "stdout", output),
              patch("builtins.input", side_effect=[expected, "CONSENT " + expected])):
            result = apply.main()
        self.assertEqual(result, 0)
        self.assertIn('"status": "applied"', output.getvalue())
        self.assertIn('"audit"', output.getvalue())
        self.assertIn('"billingPolicy": "complete"', output.getvalue())

    def test_symlink_preserved_and_changed_link_target_refused(self):
        target = self.paths["routerConfig"]
        linked = self.root / "router-link.json"
        linked.symlink_to(target)
        report = copy.deepcopy(self.report)
        report["sources"]["routerConfig"]["path"] = str(linked)
        for change in report["recommendations"][0]["changes"]:
            if change["source"] == "routerConfig":
                change["config"] = str(linked)
        plan = self.plan(report)
        self.assertEqual(plan["files"][-1]["realPath"], str(target))
        allowed = {Path(row["realPath"]) for row in plan["files"]}
        outcome = apply.apply_plan(plan, self.backups, allowed=allowed, confirm=lambda _: True, validate=lambda _: None)
        self.assertEqual(outcome["status"], "applied")
        self.assertTrue(linked.is_symlink())
        self.assertEqual(self.sha(linked), self.sha(target))
        other = self.root / "other.json"
        other.write_text(target.read_text())
        linked.unlink()
        linked.symlink_to(other)
        with self.assertRaises(apply.Refused):
            apply.apply_plan(plan, self.backups, allowed=allowed, confirm=lambda _: True, validate=lambda _: None)


if __name__ == "__main__":
    unittest.main()
