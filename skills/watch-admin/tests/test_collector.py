import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "collect.py"
SPEC = importlib.util.spec_from_file_location("watch_admin_collect", SCRIPT)
collector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = collector
assert SPEC.loader
SPEC.loader.exec_module(collector)

NOW = "2026-08-05T09:00:00Z"


class CollectorTest(unittest.TestCase):
    def workspace(self, count=1):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        repositories = []
        for index in range(count):
            path = root / f"repo-{index}"
            path.mkdir()
            repositories.append({"name": f"repo-{index}", "path": path.name, "role": "service"})
        (root / "workspace.json").write_text(
            json.dumps({"version": 1, "name": "Fixture", "repositories": repositories, "infrastructure": []}),
            encoding="utf-8",
        )
        return root

    def test_workspace_validation_is_rooted_and_bounded(self):
        root = self.workspace(2)
        repositories = collector.load_workspace(root)
        self.assertEqual(["workspace", "repo-0", "repo-1"], [repo.name for repo in repositories])

        oversized = self.workspace(11)
        with self.assertRaisesRegex(collector.CollectorError, "at most 10"):
            collector.load_workspace(oversized)

    def test_git_inventory_projection_is_stable_and_material(self):
        root = self.workspace()
        text = "\n".join(
            [
                "=== GIT INVENTORY ===",
                "repo-0 (repo-0) | branch main | worktree /tmp/repo-0 | checkout registered | upstream origin/main | ahead 2 | behind 1 | dirty 3 | last 2026-08-05 | age 0d | freshness unclassified",
                "repo-0 (repo-0) | branch old | worktree — | checkout — | upstream — | ahead — | behind — | dirty — | last 2026-08-01 | age 4d | freshness unclassified",
            ]
        )
        refs = {"repo-0": {"main": "abc", "old": "def"}, "workspace": {}}

        records = collector.parse_git_inventory(text, refs, {"repo-0": {"/tmp/repo-0": "checkout-head"}})

        self.assertEqual(["repo-0:branch:old", "repo-0:worktree:/tmp/repo-0"], [row["id"] for row in records])
        current = records[1]
        self.assertEqual("checkout-head", current["head"])
        self.assertTrue(current["dirty"])
        self.assertTrue(current["upstream"])
        self.assertEqual(2, current["ahead"])
        self.assertEqual(1, current["behind"])
        self.assertTrue(current["present"])

    def test_malformed_git_inventory_fails_instead_of_becoming_empty(self):
        with self.assertRaisesRegex(collector.CollectorError, "malformed git inventory"):
            collector.parse_git_inventory("repo | nonsense", {"workspace": {}})

    def test_bead_projection_keeps_dependency_identity_and_store(self):
        issue = {
            "id": "agents-l1i",
            "status": "in_progress",
            "priority": 2,
            "dependencies": [
                {"id": "agents-mu9", "dependency_type": "blocks"},
                {"id": "agents-5wm", "dependency_type": "related"},
            ],
        }

        record = collector.project_bead(issue, "workspace")

        self.assertEqual("workspace:agents-l1i", record["id"])
        self.assertEqual(["workspace:agents-mu9"], record["blockers"])
        self.assertEqual(["workspace:agents-5wm", "workspace:agents-mu9"], record["dependencies"])
        self.assertEqual("workspace", record["owningStore"])

    def test_record_and_byte_caps_are_partial_and_deterministic(self):
        records = [{"id": f"repo-{index:04}", "entityType": "repository", "head": "x" * 200} for index in range(1200)]

        first = collector.make_envelope("git", records, NOW)
        second = collector.make_envelope("git", list(reversed(records)), NOW)

        self.assertEqual("partial", first["status"])
        self.assertEqual(first, second)
        self.assertLessEqual(len(json.dumps(first, separators=(",", ":")).encode()), collector.ENVELOPE_BYTES)
        self.assertEqual(first["coverage"]["total"], 1200)
        self.assertGreater(first["coverage"]["omitted"], 0)

    def test_hostile_or_oversized_strings_fail_source(self):
        for value in ("bad\u0000id", "x" * 257):
            with self.subTest(value=value[:10]):
                result = collector.make_envelope("git", [{"id": value}], NOW)
                self.assertEqual("error", result["status"])
                self.assertLessEqual(len(result["error"].encode()), collector.DIAGNOSTIC_BYTES)

    def test_source_failures_are_isolated(self):
        root = self.workspace()
        with (
            mock.patch.object(collector, "collect_git", side_effect=collector.CollectorError("git timeout")),
            mock.patch.object(collector, "collect_beads", return_value=[{"id": "a", "status": "open", "priority": 3, "blockers": [], "dependencies": [], "owningStore": "workspace"}]),
        ):
            result = collector.collect(root, ("git", "beads"), NOW)

        self.assertEqual("error", result["git"]["status"])
        self.assertEqual("complete", result["beads"]["status"])
        self.assertEqual("a", result["beads"]["records"][0]["id"])

    def test_missing_dependency_and_timeout_are_bounded_errors(self):
        with mock.patch.object(collector.shutil, "which", side_effect=lambda name: None if name == "bd" else f"/bin/{name}"):
            with self.assertRaisesRegex(collector.CollectorError, "missing required command: bd"):
                collector.check_dependencies(("beads",))

        with mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired(["git"], 1)):
            with self.assertRaisesRegex(collector.CollectorError, "timed out"):
                collector.run_command(["git", "status"], timeout=1)

    def test_local_deadline_is_future_and_timezone_qualified(self):
        now = collector.datetime.fromisoformat("2026-08-05T09:00:00+01:00")
        self.assertEqual("2026-08-05T17:00:00+01:00", collector.resolve_deadline("17:00", now))
        with self.assertRaisesRegex(collector.CollectorError, "future"):
            collector.resolve_deadline("08:00", now)
        with self.assertRaisesRegex(collector.CollectorError, "HH:MM"):
            collector.resolve_deadline("17", now)

    def route_fixture(self, events):
        root = self.workspace(0)
        repositories = []
        for name, (relative, role) in sorted(collector.APPROVED_UAT_REPOSITORIES.items()):
            (root / relative).mkdir(parents=True)
            repositories.append({"name": name, "path": relative, "role": role})
        (root / "workspace.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "name": collector.APPROVED_UAT_WORKSPACE,
                    "repositories": repositories,
                    "infrastructure": [],
                }
            ),
            encoding="utf-8",
        )
        session = root / "session.jsonl"
        session.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")
        agent_dir = root / "agent"
        agent_dir.mkdir()
        (agent_dir / "model-tier-router.json").write_text(
            json.dumps(
                {
                    "enabled": True,
                    "tiers": {
                        "standard": {
                            "rank": 20,
                            "thinking": "high",
                            "selection": "weighted-random",
                            "candidates": [{"model": "openai-codex/gpt-5.6-terra", "weight": 1}],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        return root, session, agent_dir

    @staticmethod
    def stable_route_events():
        return [
            {"type": "session", "id": "session-1"},
            {"type": "model_change", "provider": "openai-codex", "modelId": "gpt-5.6-terra"},
            {"type": "thinking_level_change", "thinkingLevel": "medium"},
            {"type": "message", "message": {"role": "user"}},
            {"type": "message", "message": {"role": "assistant"}},
        ]

    def validate_route(self, root, session, agent_dir, *, model="gpt-5.6-terra", approved_path=None):
        collector.validate_route_stability(
            session,
            "session-1",
            "openai-codex",
            model,
            "medium",
            agent_dir,
            root,
            True,
            root,
            approved_path or root,
        )

    def test_route_stability_accepts_fresh_unchanged_standard_route(self):
        root, session, agent_dir = self.route_fixture(self.stable_route_events())
        self.validate_route(root, session, agent_dir)

    def test_production_route_stability_rejects_fabricated_blc_path(self):
        root, session, agent_dir = self.route_fixture(self.stable_route_events())
        with self.assertRaisesRegex(collector.CollectorError, "approved BLC UAT path"):
            collector.validate_route_stability(
                session,
                "session-1",
                "openai-codex",
                "gpt-5.6-terra",
                "medium",
                agent_dir,
                root,
                True,
                root,
            )

    def test_route_stability_rejects_symlink_alias_of_approved_path(self):
        root, session, agent_dir = self.route_fixture(self.stable_route_events())
        alias = root / "alias"
        alias.symlink_to(root, target_is_directory=True)

        with self.assertRaisesRegex(collector.CollectorError, "approved BLC UAT path"):
            collector.validate_route_stability(
                session,
                "session-1",
                "openai-codex",
                "gpt-5.6-terra",
                "medium",
                agent_dir,
                root,
                True,
                root,
                root,
                alias,
            )

    def test_route_stability_rejects_project_router_override(self):
        root, session, agent_dir = self.route_fixture(self.stable_route_events())
        (root / ".pi").mkdir()
        (root / ".pi" / "model-tier-router.json").write_text('{"enabled": false}', encoding="utf-8")

        with self.assertRaisesRegex(collector.CollectorError, "project model-tier overrides"):
            self.validate_route(root, session, agent_dir)

    def test_route_stability_rejects_non_blc_workspace_or_malformed_standard_tier(self):
        root, session, agent_dir = self.route_fixture(self.stable_route_events())
        manifest = json.loads((root / "workspace.json").read_text(encoding="utf-8"))
        manifest["name"] = "not-blc"
        (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(collector.CollectorError, "approved BLC"):
            self.validate_route(root, session, agent_dir)

        for field, value in (("path", "wrong/path"), ("role", "primary")):
            with self.subTest(field=field):
                root, session, agent_dir = self.route_fixture(self.stable_route_events())
                manifest = json.loads((root / "workspace.json").read_text(encoding="utf-8"))
                manifest["repositories"][0][field] = value
                (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(collector.CollectorError, "approved BLC"):
                    self.validate_route(root, session, agent_dir)

        root, session, agent_dir = self.route_fixture(self.stable_route_events())
        (agent_dir / "model-tier-router.json").write_text(
            json.dumps(
                {
                    "enabled": True,
                    "tiers": {
                        "standard": {
                            "thinking": "high",
                            "selection": "weighted-random",
                            "candidates": [{"model": "openai-codex/gpt-5.6-terra", "weight": 1}],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(collector.CollectorError, "invalid rank"):
            self.validate_route(root, session, agent_dir)

    def test_route_stability_rejects_changed_nonstandard_or_resumed_session(self):
        scenarios = [
            [
                {"type": "session", "id": "session-1"},
                {"type": "model_change", "provider": "openai-codex", "modelId": "gpt-5.6-sol"},
                {"type": "model_change", "provider": "openai-codex", "modelId": "gpt-5.6-terra"},
                {"type": "thinking_level_change", "thinkingLevel": "medium"},
                {"type": "message", "message": {"role": "user"}},
                {"type": "message", "message": {"role": "assistant"}},
            ],
            [
                {"type": "session", "id": "session-1"},
                {"type": "model_change", "provider": "openai-codex", "modelId": "gpt-5.6-sol"},
                {"type": "thinking_level_change", "thinkingLevel": "medium"},
                {"type": "message", "message": {"role": "user"}},
                {"type": "message", "message": {"role": "assistant"}},
            ],
            [
                *CollectorTest.stable_route_events(),
                {"type": "message", "message": {"role": "user"}},
            ],
            [
                {"type": "session", "id": "session-1"},
                {"type": "model_change", "provider": "openai-codex", "modelId": "gpt-5.6-terra"},
                {"type": "thinking_level_change", "thinkingLevel": "high"},
                {"type": "thinking_level_change", "thinkingLevel": "medium"},
                {"type": "message", "message": {"role": "user"}},
                {"type": "message", "message": {"role": "assistant"}},
            ],
        ]
        for events in scenarios:
            with self.subTest(events=events):
                root, session, agent_dir = self.route_fixture(events)
                with self.assertRaisesRegex(collector.CollectorError, "route|fresh"):
                    self.validate_route(root, session, agent_dir, model=events[1]["modelId"])

    def test_route_stability_requires_pi_session_and_uat_evidence(self):
        with self.assertRaisesRegex(collector.CollectorError, "UAT authorization"):
            root = self.workspace()
            collector.validate_route_stability(None, None, None, None, None, None, root, False, None)

    def test_command_output_cap_rejects_malformed_dependency_output(self):
        completed = subprocess.CompletedProcess(["bd"], 0, stdout="x" * (collector.COMMAND_OUTPUT_BYTES + 1), stderr="")
        with mock.patch.object(subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(collector.CollectorError, "output exceeded"):
                collector.run_command(["bd", "list"])


if __name__ == "__main__":
    unittest.main()
