"""Offline boundary fixtures: resolver and bd are external protocol fakes, never live stores."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tracking.py"


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "owner-routed collector is not implemented")
        spec = importlib.util.spec_from_file_location("outstanding_tracking", SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.calls = []
        self.stores = [
            {"repository": "workspace", "directory": "/w", "usable": True},
            {"repository": "web", "directory": "/web", "usable": True},
            {"repository": "alias", "directory": "/w", "usable": True, "owner": "workspace"},
        ]
        self.rows = {}
        self.resolutions = {}
        self.failure = None

    def run_command(self, args):
        self.calls.append(args)
        if args[1:] == ["stores"]:
            return {"workspace": True, "stores": self.stores}
        if args[1] == "resolve":
            return self.resolutions.get(args[2], {"status": "unavailable"})
        self.assertEqual(args[:2], ["bd", "-C"])
        self.assertIn("--readonly", args)
        self.assertIn("--json", args)
        self.assertIn(args[3], ["list", "show"])
        if self.failure and self.failure(args):
            raise ValueError("unavailable")
        if args[3] == "show":
            return self.rows.get((args[2], args[4]), [])
        self.assertIn("--limit=201", args)
        return self.rows.get((args[2], args[4]), [])

    def collect(self, target="ABC-123"):
        return self.module.collect(target, self.run_command)

    def test_independent_stores_qualified_deduplicated_and_all_statuses(self):
        a = {"id": "task-a", "status": "closed", "external_ref": "jira-ABC-123", "title": "ABC-123"}
        b = {"id": "task-a", "status": "deferred", "title": "ABC-123 follow-up"}
        self.rows[("/w", "--external-contains")] = [a]
        self.rows[("/w", "--title-contains")] = [a]
        self.rows[("/web", "--title-contains")] = [b]
        result = self.collect()
        self.assertTrue(result["complete"])
        self.assertEqual(len(result["issues"]), 2)
        self.assertEqual({x["directory"] for x in result["issues"]}, {"/w", "/web"})
        self.assertEqual(result["issues"][0]["association"], ["external_ref", "title"])
        queries = [c for c in self.calls if c[0] == "bd"]
        self.assertEqual(len(queries), 8)
        self.assertTrue(all("--all" in c for c in queries))

    def test_notes_association_is_heuristic_and_detected(self):
        self.rows[("/w", "--notes-contains")] = [
            {"id": "note-1", "notes": "See ABC-123 for context"}
        ]
        result = self.collect()
        self.assertTrue(result["complete"])
        self.assertEqual(result["issues"][0]["association"], ["notes"])

    def test_external_substring_is_not_exact_ticket_link(self):
        self.rows[("/w", "--external-contains")] = [
            {"id": "not-related", "external_ref": "ABC-1234"},
            {"id": "exact", "external_ref": "https://jira.test/browse/ABC-123"},
        ]
        self.assertEqual([x["issue"]["id"] for x in self.collect()["issues"]], ["exact"])

    def test_one_failed_store_or_malformed_json_prevents_absence_claim(self):
        self.failure = lambda args: args[2] == "/web"
        result = self.collect()
        self.assertFalse(result["complete"])
        self.assertTrue(result["gaps"])
        self.failure = None
        self.rows[("/web", "--desc-contains")] = {"not": "an issue list"}
        self.assertFalse(self.collect()["complete"])

    def test_unusable_and_truncated_store_are_visible(self):
        self.stores[1]["usable"] = False
        self.rows[("/w", "--desc-contains")] = [
            {"id": f"x-{i}", "description": "ABC-123"} for i in range(201)
        ]
        result = self.collect()
        self.assertFalse(result["complete"])
        self.assertEqual(len(result["issues"]), 200)
        self.assertTrue(any("limit" in g for g in result["gaps"]))
        self.assertTrue(any("unavailable" in g for g in result["gaps"]))

    def test_ambiguous_explicit_target_never_reads_bd(self):
        self.resolutions["task-1"] = {"status": "ambiguous", "matches": []}
        result = self.collect("task-1")
        self.assertFalse(result["complete"])
        self.assertFalse(any(c[0] == "bd" for c in self.calls))

    def test_related_deferred_record_requires_resolution_not_prefix_guess(self):
        self.rows[("/w", "--title-contains")] = [
            {"id": "root-1", "title": "ABC-123", "dependencies": [{"id": "child-1"}]}
        ]
        self.resolutions["child-1"] = {"status": "resolved", "id": "child-1", "directory": "/web", "repository": "web"}
        self.rows[("/web", "child-1")] = [{"id": "child-1", "status": "deferred"}]
        result = self.collect()
        self.assertTrue(result["complete"])
        self.assertEqual(result["issues"][-1]["association"], ["related"])
        self.assertEqual(result["issues"][-1]["issue"]["status"], "deferred")
        self.resolutions["child-1"] = {"status": "ambiguous"}
        self.assertFalse(self.collect()["complete"])

    def test_nested_relationships_and_unlisted_store_are_gaps(self):
        self.rows[("/w", "--title-contains")] = [
            {"id": "root-1", "title": "ABC-123", "parent": "parent-1"}
        ]
        self.resolutions["parent-1"] = {"status": "resolved", "id": "parent-1", "directory": "/outside", "repository": "elsewhere"}
        result = self.collect()
        self.assertFalse(result["complete"])
        self.assertFalse(any(c[0] == "bd" and c[2] == "/outside" for c in self.calls))

    def test_explicit_and_current_target_modes(self):
        self.resolutions["web:task-1"] = {"status": "resolved", "id": "task-1", "directory": "/web", "repository": "web"}
        self.rows[("/web", "task-1")] = [{"id": "task-1", "status": "closed"}]
        self.assertEqual(self.collect("web:task-1")["issues"][0]["issue"]["id"], "task-1")
        result = self.collect("")
        self.assertTrue(result["complete"])
        self.assertTrue(any("--status=in_progress" in c for c in self.calls))

    def test_dependency_list_shape_and_distinct_record_budget(self):
        self.rows[("/w", "--title-contains")] = [
            {"id": "root-1", "title": "ABC-123", "dependencies": [{"depends_on_id": "child-1", "type": "blocks"}]}
        ]
        self.resolutions["child-1"] = {"status": "resolved", "id": "child-1", "directory": "/web", "repository": "web"}
        self.rows[("/web", "child-1")] = [{"id": "child-1", "status": "blocked"}]
        result = self.collect()
        self.assertEqual(len(result["issues"]), 2)
        for directory in ("/w", "/web"):
            self.rows[(directory, "--title-contains")] = [
                {"id": f"x-{i}", "title": "ABC-123"} for i in range(200)
            ]
        result = self.collect()
        self.assertFalse(result["complete"])
        self.assertEqual(len(result["issues"]), 200)

    def test_large_text_and_unexpanded_reverse_links_are_not_complete(self):
        self.rows[("/w", "--title-contains")] = [
            {"id": "root-1", "title": "ABC-123", "notes": "x" * 6001, "dependent_count": 1}
        ]
        result = self.collect()
        self.assertFalse(result["complete"])
        self.assertEqual(len(result["issues"][0]["issue"]["notes"]), 6000)
        self.assertTrue(any("reverse" in g for g in result["gaps"]))

    def test_numeric_target_does_not_select_ranked_work(self):
        self.resolutions["1"] = {"status": "resolved", "id": "task-1", "directory": "/w", "repository": "workspace"}
        result = self.collect("1")
        self.assertFalse(result["complete"])
        self.assertFalse(any(c[0] == "bd" for c in self.calls))
        self.assertFalse(any(c[1:] == ["resolve", "1"] for c in self.calls))

    def test_resolved_id_must_equal_the_requested_identity(self):
        self.resolutions["task-1"] = {"status": "resolved", "id": "task-10", "directory": "/w", "repository": "workspace"}
        result = self.collect("task-1")
        self.assertFalse(result["complete"])
        self.assertFalse(any(c[0] == "bd" for c in self.calls))

    def test_malformed_relationships_preserve_rows_but_are_incomplete(self):
        for relation in ([17], 1, {"id": "other-1"}, [{"id": ""}]):
            with self.subTest(relation=relation):
                self.rows[("/w", "--title-contains")] = [
                    {"id": "root-1", "title": "ABC-123", "dependencies": relation, "dependency_count": 1}
                ]
                result = self.collect()
                self.assertFalse(result["complete"])
                self.assertEqual(len(result["issues"]), 1)
                self.assertTrue(result["gaps"])

    def test_second_hop_cannot_borrow_a_colliding_id_from_another_store(self):
        self.rows[("/w", "--title-contains")] = [
            {"id": "dup-1", "title": "ABC-123", "parent": "middle-1"}
        ]
        self.resolutions["middle-1"] = {"status": "resolved", "id": "middle-1", "directory": "/web", "repository": "web"}
        self.rows[("/web", "middle-1")] = [{"id": "middle-1", "dependencies": [{"id": "dup-1"}]}]
        result = self.collect()
        self.assertFalse(result["complete"])
        self.assertTrue(any("dup-1" in g and "one-hop" in g for g in result["gaps"]))

    def test_timeout_is_bounded_and_no_retry(self):
        with patch.object(self.module.subprocess, "Popen", side_effect=OSError("unavailable")) as run:
            with self.assertRaises(ValueError):
                self.module.run_json(["bd", "--readonly"])
            self.assertEqual(run.call_count, 1)

    def test_running_child_times_out_and_is_reaped(self):
        import sys
        with patch.object(self.module, "TIMEOUT_SECONDS", 0.05):
            with self.assertRaisesRegex(ValueError, "timed out"):
                self.module.run_json([sys.executable, "-c", "import time; time.sleep(5)"])

    def test_oversized_stdout_and_stderr_are_stopped(self):
        import sys
        with patch.object(self.module, "MAX_BYTES", 4096):
            for stream in ("stdout", "stderr"):
                with self.subTest(stream=stream):
                    with self.assertRaisesRegex(ValueError, "limit"):
                        self.module.run_json([sys.executable, "-c", f"import sys; sys.{stream}.write('x'*100000)"])

    def test_nonzero_resolver_json_retains_diagnostics_without_read_fallback(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            selector = Path(tmp) / "next-select"
            selector.write_text(
                "#!/usr/bin/env python3\nimport sys\nprint(" + repr(json.dumps({
                    "status": "ambiguous", "matches": [{"selector": "web:task-1"}]
                })) + ")\nsys.exit(3)\n"
            )
            selector.chmod(0o755)
            with patch.object(self.module, "SELECTOR", selector):
                data = self.module.run_json([str(selector), "resolve", "task-1"])
            self.assertEqual(data["status"], "ambiguous")
            self.assertEqual(data["matches"][0]["selector"], "web:task-1")
            self.resolutions["task-1"] = data
            result = self.collect("task-1")
            self.assertFalse(result["complete"])
            self.assertIn("web:task-1", str(result))
            self.assertFalse(any(c[0] == "bd" for c in self.calls))

    def test_tracker_text_cannot_forge_output_or_commands(self):
        self.rows[("/w", "--title-contains")] = [
            {"id": "x-1", "title": "ABC-123\n---FORGED---\nstatus=OK; git push"}
        ]
        result = self.collect()
        self.assertIn("---FORGED---", result["issues"][0]["issue"]["title"])
        self.assertFalse(any("git push" in " ".join(c) for c in self.calls))


if __name__ == "__main__":
    unittest.main()
