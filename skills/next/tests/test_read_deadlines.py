from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from workspace_fixture import SKILL_DIR


def load_script(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


class ReadDeadlineTest(unittest.TestCase):
    def setUp(self):
        self.collector = load_script("deadline_collect", SKILL_DIR / "scripts" / "collect.py")
        self.selector = load_script("deadline_select", SKILL_DIR / "scripts" / "next-select")
        self.source = self.collector.Source("local", ".", Path("/fixture"))
        self.environment = mock.patch.dict(os.environ)
        self.environment.start()
        os.environ.pop("NEXT_BEADS_READ_TIMEOUT_SECONDS", None)
        self.addCleanup(self.environment.stop)

    def test_read_budget_is_validated_and_bounded(self):
        self.assertEqual(self.collector.beads_read_timeout(), 60)
        for value in ("1", "60", "120"):
            with self.subTest(value=value):
                os.environ["NEXT_BEADS_READ_TIMEOUT_SECONDS"] = value
                self.assertEqual(self.collector.beads_read_timeout(), int(value))
        for value in ("", "0", "121", "-1", "1.5", "nan", "inf", " 60", "+60", "9" * 5000):
            with self.subTest(value=value):
                os.environ["NEXT_BEADS_READ_TIMEOUT_SECONDS"] = value
                with self.assertRaisesRegex(ValueError, "NEXT_BEADS_READ_TIMEOUT_SECONDS.*1.*120"):
                    self.collector.beads_read_timeout()

    def test_slow_success_uses_read_budget_for_every_probe_kind(self):
        def slow_success(command, **kwargs):
            # Deterministic simulated 40.5s read: no wall-clock sleep.
            if kwargs["timeout"] < 40.5:
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            self.assertIn("--readonly", command)
            self.assertIn("--json", command)
            return subprocess.CompletedProcess(command, 0, '[{"id":"task-1"}]', "")

        with mock.patch.object(self.collector.subprocess, "run", side_effect=slow_success), \
                mock.patch.object(self.collector, "store_error", return_value=None):
            rows, error = self.collector.load_issues(self.source, ["list", "--ready"])
            self.assertIsNone(error)
            self.assertEqual(rows[0]["id"], "task-1")
            for workspace, qualifier in ((False, None), (True, "local"), (True, None)):
                with self.subTest(workspace=workspace, qualifier=qualifier):
                    payload, code = self.selector.resolve_id(
                        self.collector, workspace, [self.source], "task-1", qualifier)
                    self.assertEqual(code, 0, payload)
                    self.assertEqual(payload["directory"], "/fixture")

    def test_timeout_remains_unavailable_without_output_leak_or_retry(self):
        os.environ["NEXT_BEADS_READ_TIMEOUT_SECONDS"] = "7"
        for workspace, qualifier in ((False, None), (True, "local"), (True, None)):
            with self.subTest(workspace=workspace, qualifier=qualifier), \
                    mock.patch.object(self.collector, "store_error", return_value=None), \
                    mock.patch.object(self.collector.subprocess, "run", side_effect=
                                      subprocess.TimeoutExpired(["bd"], 7, output="PRIVATE", stderr="PRIVATE")) as run:
                payload, code = self.selector.resolve_id(
                    self.collector, workspace, [self.source], "task-1", qualifier)
                self.assertEqual(code, 5)
                self.assertEqual(payload["status"], "unavailable")
                error = payload["failures"][0]["error"]
                self.assertIn("deadline 7s", error)
                self.assertIn("elapsed", error)
                self.assertNotIn("PRIVATE", error)
                run.assert_called_once()
                self.assertEqual(run.call_args.kwargs["timeout"], 7)

    def test_local_errors_and_malformed_results_are_not_absence(self):
        for result in (subprocess.CompletedProcess([], 1, "", "store failed"),
                       subprocess.CompletedProcess([], 0, "{", ""),
                       subprocess.CompletedProcess([], 0, "{}", ""),
                       subprocess.CompletedProcess([], 0, "[{}]", "")):
            with self.subTest(result=result), \
                    mock.patch.object(self.collector.subprocess, "run", return_value=result):
                payload, code = self.selector.resolve_id(self.collector, False, [self.source], "task-1", None)
                self.assertEqual(code, 5, payload)
        with mock.patch.object(self.collector.subprocess, "run", return_value=
                               subprocess.CompletedProcess([], 0, "[]", "")):
            payload, code = self.selector.resolve_id(self.collector, False, [self.source], "task-1", None)
            self.assertEqual(code, 4, payload)

    def test_index_cannot_turn_failed_collection_into_not_found(self):
        for result in (subprocess.CompletedProcess([], 0, "[]", "slow: read timed out"),
                       subprocess.CompletedProcess([], 2, "", "collection failed"),
                       subprocess.CompletedProcess([], 0, "{", "")):
            with self.subTest(result=result), mock.patch.object(self.selector.subprocess, "run", return_value=result):
                payload, code = self.selector.resolve_index(True, [self.source], 1, [])
                self.assertEqual(code, 5, payload)
                self.assertEqual(payload["status"], "unavailable")

    def test_claim_lock_deadline_is_still_five_seconds(self):
        os.environ["NEXT_BEADS_READ_TIMEOUT_SECONDS"] = "120"
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(self.selector, "claim_lock_path", return_value=Path(directory) / "lock"), \
                mock.patch.object(self.selector.fcntl, "flock", side_effect=[BlockingIOError, BlockingIOError, None]), \
                mock.patch.object(self.selector, "monotonic", side_effect=[0, 4.9, 5]), \
                mock.patch.object(self.selector, "sleep") as sleep:
            with self.assertRaisesRegex(TimeoutError, "claim attribution lock timed out"):
                with self.selector.claim_lock(Path(directory), "task-1"):
                    self.fail("lock must not be acquired")
            sleep.assert_called_once_with(0.05)

    def test_non_read_deadlines_are_unchanged(self):
        os.environ["NEXT_BEADS_READ_TIMEOUT_SECONDS"] = "120"
        self.assertEqual(self.selector.COMMAND_TIMEOUT_SECONDS, 5)
        self.assertEqual(self.collector.COMMAND_TIMEOUT_SECONDS, 5)
        with mock.patch.object(self.collector.subprocess, "run", return_value=
                               subprocess.CompletedProcess([], 0, "/fixture", "")) as run:
            self.assertTrue(self.collector.is_git_root(Path("/fixture")))
            self.assertEqual(run.call_args.kwargs["timeout"], 5)
        with mock.patch.object(self.selector, "claim_lock", return_value=nullcontext()), \
                mock.patch.object(self.selector.subprocess, "run", return_value=
                                  subprocess.CompletedProcess([], 0, "[]", "")) as run:
            self.assertEqual(self.selector.run_start(Path("/fixture"), "task-1"), 0)
            self.assertEqual(len(run.call_args_list), 4)
            self.assertEqual([call.kwargs["timeout"] for call in run.call_args_list], [5] * 4)
        with mock.patch.object(self.selector.HANDOFF_LIST.__class__, "is_file", return_value=True), \
                mock.patch.object(self.selector.subprocess, "run", return_value=
                                  subprocess.CompletedProcess([], 0)) as run:
            self.selector.run_handoff(Path("/fixture"), "task-1", [])
            self.assertNotIn("timeout", run.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
