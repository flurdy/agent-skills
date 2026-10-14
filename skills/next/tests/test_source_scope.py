from __future__ import annotations

import json
import shutil
import subprocess
import unittest

from workspace_fixture import SKILL_DIR, WorkspaceFixture, issue


class SourceScopeTest(WorkspaceFixture):
    def test_safe_packet_keeps_undeclared_and_label_conflicts(self) -> None:
        free = issue("free", 2, "task", "2026-01-01")
        free["metadata"] = {"source_scope": {"version": 1, "complete": True, "roots": ["repos/api"]}}
        busy = issue("busy", 2, "task", "2026-01-02", labels=["claimed"])
        workspace = self.create_workspace(
            root_data={"ready": [free, busy], "in_progress": [issue("active", 2, "task", "2026-01-01", labels=["claimed"])]},
            repositories={"api": {}},
        )
        result = self.run_script(SKILL_DIR / "scripts/next-bd", workspace, "--safe-json")
        packet = json.loads(result.stdout)
        self.assertEqual(packet["version"], 1)
        rows = packet["candidates"]
        self.assertEqual([row["id"] for row in rows], ["free", "busy"])
        self.assertEqual(rows[0]["source_scope"]["state"], "declared")
        self.assertEqual(rows[0]["source_scope"]["roots"], [str((workspace / "repos/api").resolve())])
        self.assertEqual(rows[1]["source_scope"]["state"], "unknown")
        self.assertEqual(packet["in_progress"][0]["id"], "active")
        self.assertTrue(all("--readonly" in row["arguments"] for row in self.recorded_calls()))

    def test_workspace_owned_scope_is_explicit_and_redirected_bases_are_unknown(self) -> None:
        declared = issue("declared", 2, "task", "2026-01-01")
        declared["metadata"] = {"source_scope": {"version": 1, "complete": True, "roots": ["repos/api"]}}
        undeclared = issue("undeclared", 2, "task", "2026-01-02")
        workspace = self.create_workspace(root_data={"ready": [declared, undeclared]}, repositories={"api": {}})
        manifest_path = workspace / "workspace.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["repositories"][0]["beadsStore"] = "workspace"
        manifest_path.write_text(json.dumps(manifest))
        shutil.rmtree(workspace / "repos/api/.beads")
        packet = json.loads(self.run_script(SKILL_DIR / "scripts/next-bd", workspace, "--safe-json").stdout)
        self.assertEqual(packet["candidates"][0]["source_scope"]["roots"], [str((workspace / "repos/api").resolve())])
        self.assertEqual(packet["candidates"][1]["source_scope"]["roots"], [])
        (workspace / ".beads/redirect").write_text("elsewhere")
        packet = json.loads(self.run_script(SKILL_DIR / "scripts/next-bd", workspace, "--safe-json").stdout)
        self.assertEqual(packet["candidates"][0]["source_scope"]["state"], "unavailable")

    @unittest.skipUnless(shutil.which("node") and shutil.which("lslocks"), "optional Node/Linux observer adapter")
    def test_native_adapter_reloads_declarations_and_never_claims(self) -> None:
        row = issue("a", 2, "task", "2026-01-01")
        row["metadata"] = {"source_scope": {"version": 1, "complete": True, "roots": ["."]}}
        root = self.base / "native"
        self.create_store(root, ready=[row])
        module = (SKILL_DIR / "pi/lease-selection.mjs").as_uri()
        code = f"""
          import assert from 'node:assert/strict';
          import {{readFile,writeFile}} from 'node:fs/promises';
          import {{inspectCandidates,collectCandidates}} from {json.dumps(module)};
          const cwd = {json.dumps(str(root))};
          const loadObserver = async () => async roots => roots.map(root => ({{kind:'free',root}}));
          assert.equal((await inspectCandidates(cwd, {{loadObserver}})).eligible.length, 1);
          const unavailable = await inspectCandidates(cwd);
          assert.equal(unavailable.eligible.length, 0);
          assert.equal(unavailable.unavailable.length, 1);
          const fixturePath = cwd + '/.beads/fixture.json';
          const fixture = JSON.parse(await readFile(fixturePath,'utf8'));
          fixture.ready[0].metadata.source_scope.complete = false;
          await writeFile(fixturePath,JSON.stringify(fixture));
          const checked = await inspectCandidates(cwd, {{selector:'local:a',loadObserver}});
          assert.equal(checked.eligible.length, 0);
          assert.equal(checked.unknown.length, 1);
          await assert.rejects(inspectCandidates(cwd, {{selector:'local:missing',loadObserver}}));
          const controller = new AbortController(); controller.abort();
          await assert.rejects(collectCandidates(cwd, controller.signal), /aborted/);
          await assert.rejects(collectCandidates(cwd, undefined, 1), /timed out/);
        """
        result = subprocess.run(["node", "--input-type=module", "-e", code], env=self.environment, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all("--readonly" in call["arguments"] for call in self.recorded_calls()))

    def test_scope_validation_and_portable_degradation(self) -> None:
        declarations = [
            None,
            {"version": 1, "complete": False, "roots": ["."]},
            {"version": 1, "complete": True, "roots": [".", "alias"]},
            {"version": 1, "complete": True, "roots": ["/tmp"]},
            {"version": 1, "complete": True, "roots": ["missing"]},
            {"version": 2, "complete": True, "roots": ["."]},
        ]
        rows = []
        for index, declaration in enumerate(declarations):
            row = issue(f"case-{index}", 2, "task", f"2026-01-0{index + 1}")
            if declaration is not None:
                row["metadata"] = {"source_scope": declaration}
            rows.append(row)
        root = self.base / "local"
        self.create_store(root, ready=rows)
        (root / "alias").symlink_to(root, target_is_directory=True)
        packet = json.loads(self.run_script(SKILL_DIR / "scripts/next-bd", root, "--safe-json").stdout)
        scopes = [row["source_scope"] for row in packet["candidates"]]
        self.assertEqual([s["state"] for s in scopes], ["unknown", "partial", "declared", "invalid", "unavailable", "invalid"])
        self.assertEqual(scopes[2]["roots"], [str(root)])
        self.assertEqual(packet["candidates"][2]["selector"], "local:case-2")
        fallback = self.run_script(SKILL_DIR / "scripts/next-bd", root, "--safe")
        self.assertIn("no in-process Pi observer", fallback.stdout)
        self.assertIn("case-2", fallback.stdout)
        self.assertIn("No candidates certified", fallback.stdout)
        ordinary = json.loads(self.run_script(SKILL_DIR / "scripts/next-bd", root, "--json").stdout)
        self.assertTrue(all("source_scope" not in row for row in ordinary))
