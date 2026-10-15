from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

SCRIPT = Path(__file__).parents[2] / "pr-review-requests/scripts/request-feedback.py"


class RequestFeedbackTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "request feedback reducer is missing")
        spec = importlib.util.spec_from_file_location("request_feedback", SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.record = {
            "identity": "conversation:C1", "repository": "acme/widgets", "pr": 42,
            "source": "conversation", "author": "alice", "lifecycle": "active",
            "updatedAt": "2026-07-30T10:00:00Z", "stateKey": "C1@10:active",
            "actionability": "candidate", "gist": "Please check this", "rawBody": "private",
        }

    def reduce(self, records, previous=None, partial=False):
        return self.module.reduce_feedback({
            "inventories": [{"repository": "acme/widgets", "pullRequests": [42],
                             "records": records, "partial": partial,
                             "errors": [{"source": "comments"}] if partial else []}],
            "previous": previous or {}, "keys": ["acme/widgets#42"],
        })

    def collector_result(self, records=None, repo="acme/widgets", numbers=None, partial=False):
        return subprocess.CompletedProcess([], 0, json.dumps({
            "schemaVersion": 1, "repository": repo, "pullRequests": numbers or [42],
            "records": [self.record] if records is None else records, "partial": partial,
            "errors": [{"source": "comments", "kind": "api"}] if partial else [],
        }), "")

    def test_collect_reduces_internally_without_echoing_inventory(self):
        payload = {"keys": ["acme/widgets#42"], "previous": {}}
        with mock.patch.object(self.module, "run_collector", return_value=self.collector_result()) as run:
            result = self.module.collect_feedback(payload)
        self.assertEqual(self.reduce([self.record]), {k: v for k, v in result.items() if k != "deadlineReached"})
        self.assertFalse(result["deadlineReached"])
        self.assertNotIn("rawBody", json.dumps(result))
        self.assertNotIn("private", json.dumps(result))
        self.assertNotIn("inventories", result)
        argv = run.call_args.args[0]
        self.assertEqual(["acme", "widgets", "42"], argv[2:5])
        self.assertEqual("gh-pr-feedback.py", Path(argv[1]).name)
        self.assertNotIn("--compact", argv, "dashboard counts need the full internal inventory")
        self.assertFalse(run.call_args.kwargs.get("shell", False))
        self.assertLessEqual(run.call_args.kwargs["timeout"], 120)

    def test_collect_groups_prs_and_does_not_reannounce_unchanged_feedback(self):
        previous = self.reduce([self.record])["state"]
        payload = {"keys": ["acme/widgets#42", "acme/widgets#43", "acme/other#1"], "previous": previous}
        responses = [self.collector_result(numbers=[42, 43]), self.collector_result([], "acme/other", [1])]
        with mock.patch.object(self.module, "run_collector", side_effect=responses) as run:
            result = self.module.collect_feedback(payload)
        self.assertEqual(2, run.call_count)
        self.assertEqual(["42", "43"], run.call_args_list[0].args[0][4:6])
        self.assertEqual([], result["deltas"])
        self.assertTrue(all(summary["complete"] for summary in result["summaries"].values()))

    def test_collect_preserves_state_on_failure_and_keeps_healthy_groups(self):
        previous = self.reduce([self.record])["state"]
        for failure in (
            subprocess.CompletedProcess([], 1, "", "failure"),
            subprocess.CompletedProcess([], 0, "not JSON", ""),
            self.collector_result([], "outside/repo", [1]),
            subprocess.TimeoutExpired("collector", 120),
            FileNotFoundError("collector unavailable"),
        ):
            with self.subTest(failure=type(failure).__name__):
                with mock.patch.object(self.module, "run_collector", side_effect=[
                    failure, self.collector_result([], "acme/other", [1]),
                ]):
                    result = self.module.collect_feedback({
                        "keys": ["acme/widgets#42", "acme/other#1"], "previous": previous,
                    })
                self.assertEqual(previous["acme/widgets#42"], result["state"]["acme/widgets#42"])
                self.assertFalse(result["summaries"]["acme/widgets#42"]["complete"])
                self.assertTrue(result["summaries"]["acme/other#1"]["complete"])
                self.assertTrue(result["errors"])

    def test_collect_keeps_partial_source_errors_and_missing_identities(self):
        previous = self.reduce([self.record])["state"]
        with mock.patch.object(self.module, "run_collector", return_value=self.collector_result([], partial=True)):
            result = self.module.collect_feedback({"keys": ["acme/widgets#42"], "previous": previous})
        self.assertEqual(previous, result["state"])
        self.assertFalse(result["summaries"]["acme/widgets#42"]["complete"])
        self.assertEqual("comments", result["errors"][0]["source"])

    def test_malformed_observation_preserves_previous_reusable_state(self):
        previous = self.reduce([self.record])["state"]
        for field, value in (("updatedAt", []), ("stateKey", {})):
            with self.subTest(field=field):
                malformed = {**self.record, field: value}
                with mock.patch.object(self.module, "run_collector", return_value=self.collector_result([malformed])):
                    result = self.module.collect_feedback({"keys": ["acme/widgets#42"], "previous": previous})
                self.assertFalse(result["summaries"]["acme/widgets#42"]["complete"])
                self.assertEqual(previous, result["state"])
                self.assertEqual([], self.reduce([self.record], result["state"])["deltas"])

    @unittest.skipUnless(os.name == "posix", "collector process groups require POSIX")
    def test_collect_timeout_terminates_descendant_github_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gh = root / "gh"
            gh.write_text(
                f"#!{sys.executable}\n"
                "from pathlib import Path\nimport time\n"
                f"Path({str(root / 'started')!r}).touch()\n"
                "time.sleep(1)\n"
                f"Path({str(root / 'survived')!r}).touch()\n"
            )
            gh.chmod(0o700)
            with mock.patch.dict(os.environ, {"PATH": f"{directory}{os.pathsep}{os.environ['PATH']}"}):
                result = self.module.collect_feedback(
                    {"keys": ["acme/widgets#42"]}, datetime.now(timezone.utc) + timedelta(seconds=0.5),
                )
            self.assertTrue((root / "started").exists(), "fixture must reach its descendant before timeout")
            time.sleep(1.1)
            self.assertFalse((root / "survived").exists(), "timed-out collector left gh running")
            self.assertFalse(result["summaries"]["acme/widgets#42"]["complete"])
            self.assertEqual("timeout", result["errors"][0]["kind"])

    def test_collect_validates_all_input_before_any_fetch(self):
        for payload in (
            {"keys": ["acme/widgets#42", "bad"]},
            {"keys": ["acme/widgets#42", "acme/widgets#42"]},
            {"keys": ["acme/widgets#42"], "previous": {"acme/widgets#42": "bad"}},
            {"keys": ["acme/widgets#42"], "inventories": []},
        ):
            with self.subTest(payload=payload), mock.patch.object(self.module, "run_collector") as run:
                with self.assertRaises(ValueError):
                    self.module.collect_feedback(payload)
                run.assert_not_called()

    def test_collect_deadline_stops_before_next_group_and_bounds_timeout(self):
        deadline = datetime(2026, 10, 15, 18, tzinfo=timezone.utc)
        before = datetime(2026, 10, 15, 17, 59, 50, tzinfo=timezone.utc)
        with mock.patch.object(self.module, "datetime", wraps=datetime) as clock:
            clock.now.side_effect = [before, deadline, deadline]
            with mock.patch.object(self.module, "run_collector", return_value=self.collector_result()) as run:
                result = self.module.collect_feedback({"keys": ["acme/widgets#42", "acme/other#1"]}, deadline)
        self.assertEqual(1, run.call_count)
        self.assertLessEqual(run.call_args.kwargs["timeout"], 10)
        self.assertTrue(result["deadlineReached"])
        self.assertFalse(result["summaries"]["acme/other#1"]["complete"])
        self.assertTrue(result["summaries"]["acme/widgets#42"]["complete"])

    def test_collect_expired_deadline_and_empty_scope_never_spawn(self):
        with mock.patch.object(self.module, "run_collector") as run:
            empty = self.module.collect_feedback({"keys": []})
            expired = self.module.collect_feedback(
                {"keys": ["acme/widgets#42"]}, datetime(2000, 1, 1, tzinfo=timezone.utc),
            )
        run.assert_not_called()
        self.assertEqual({}, empty["state"])
        self.assertTrue(expired["deadlineReached"])
        self.assertFalse(expired["summaries"]["acme/widgets#42"]["complete"])

    def test_collect_cli_handles_empty_scope_and_rejects_invalid_deadline(self):
        for flags, expected in ((["--collect"], 0), (["--collect", "--deadline", "bad"], 2),
                                (["--collect", "--deadline", "2026-10-15T18:00:00"], 2),
                                (["--deadline", "2026-10-15T18:00:00Z"], 2)):
            with self.subTest(flags=flags):
                result = subprocess.run([sys.executable, str(SCRIPT), *flags], input='{"keys":[]}',
                                        text=True, capture_output=True, check=False)
                self.assertEqual(expected, result.returncode, result.stderr)
                if not expected:
                    self.assertEqual({}, json.loads(result.stdout)["state"])

    def test_collect_cli_runs_real_collector_and_reducer_with_fixture_github(self):
        fixture = Path(__file__).parent / "fixtures/all-sources.json"
        with tempfile.TemporaryDirectory() as directory:
            gh = Path(directory) / "gh"
            gh.write_text(
                f"#!{sys.executable}\n"
                "import json, sys\n"
                f"with open({str(fixture)!r}) as stream: fixture = json.load(stream)\n"
                "endpoint = sys.argv[2]\n"
                "json.dump(fixture['initial'] if endpoint == 'graphql' else fixture['rest'][endpoint], sys.stdout)\n"
            )
            gh.chmod(0o700)
            environment = {**os.environ, "PATH": f"{directory}{os.pathsep}{os.environ['PATH']}"}
            payload = {"keys": ["acme/widgets#42"], "previous": {}}
            results = []
            for _ in range(2):
                completed = subprocess.run(
                    [sys.executable, str(SCRIPT), "--collect"], input=json.dumps(payload),
                    text=True, capture_output=True, check=False, env=environment, timeout=30,
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                result = json.loads(completed.stdout)
                self.assertTrue(result["summaries"]["acme/widgets#42"]["complete"])
                self.assertNotIn("rawBody", completed.stdout)
                self.assertNotIn("inventories", result)
                payload["previous"] = result["state"]
                results.append(result)
            self.assertEqual(["gh"], [path.name for path in Path(directory).iterdir()])
        self.assertEqual(13, len(results[0]["deltas"]))
        self.assertEqual([], results[1]["deltas"])
        self.assertEqual(results[0]["state"], results[1]["state"])

    def test_stable_comment_edits_are_announced_once(self):
        first = self.reduce([self.record])
        self.assertEqual("new", first["deltas"][0]["change"])
        self.assertEqual([], self.reduce([self.record], first["state"])["deltas"])
        edited = {**self.record, "updatedAt": "2026-07-30T11:00:00Z", "stateKey": "C1@11:active"}
        second = self.reduce([edited], first["state"])
        self.assertEqual("edited", second["deltas"][0]["change"])
        self.assertEqual("conversation:C1", second["deltas"][0]["identity"])
        self.assertEqual([], self.reduce([edited], second["state"])["deltas"])
        self.assertNotIn("private", str(second["state"]))

    def test_partial_does_not_erase_missing_feedback_or_claim_completeness(self):
        first = self.reduce([self.record])
        partial = self.reduce([], first["state"], partial=True)
        self.assertFalse(partial["summaries"]["acme/widgets#42"]["complete"])
        self.assertEqual(first["state"], partial["state"])
        self.assertEqual([], self.reduce([self.record], partial["state"])["deltas"])

    def test_thread_counts_use_unique_active_threads_and_lifecycle_changes(self):
        root = {**self.record, "source": "inline_review", "role": "root",
                "threadId": "T1", "lifecycle": "unresolved", "identity": "inline:C1"}
        reply = {**root, "identity": "inline:C2", "role": "reply"}
        first = self.reduce([root, reply])
        self.assertEqual(1, first["summaries"]["acme/widgets#42"]["threads"])
        resolved = {**root, "lifecycle": "resolved", "actionability": "suppressed",
                    "stateKey": "C1@10:resolved"}
        changed = self.reduce([resolved], first["state"])
        self.assertEqual(0, changed["summaries"]["acme/widgets#42"]["threads"])
        self.assertEqual("state", changed["deltas"][0]["change"])
        self.assertFalse(changed["deltas"][0]["candidate"])

    def test_missing_source_and_out_of_scope_data_fail_closed(self):
        result = self.module.reduce_feedback({"inventories": [], "previous": {},
                                              "keys": ["acme/widgets#42"]})
        self.assertFalse(result["summaries"]["acme/widgets#42"]["complete"])
        with self.assertRaises(ValueError):
            self.module.reduce_feedback({"inventories": [{"repository": "outside/repo",
                "pullRequests": [1], "records": [self.record], "partial": False}],
                "keys": ["acme/widgets#42"]})

    def test_state_caps_are_explicit_and_preserve_known_identities(self):
        records = [{**self.record, "identity": f"comment:{index}"} for index in range(501)]
        first = self.reduce([self.record])
        result = self.reduce(records, first["state"])
        self.assertLessEqual(len(result["state"]["acme/widgets#42"]), 500)
        self.assertIn(self.record["identity"], result["state"]["acme/widgets#42"])
        self.assertFalse(result["summaries"]["acme/widgets#42"]["complete"])
        self.assertTrue(result["errors"])

    def test_malformed_state_is_rejected_without_retaining_arbitrary_bodies(self):
        with self.assertRaises(ValueError):
            self.reduce([], {"acme/widgets#42": {"conversation:C1": "invalid"}})
        with self.assertRaises(ValueError):
            self.reduce([], {"acme/widgets#42": {"conversation:C1": {
                "updatedAt": "2026-07-30T10:00:00Z", "stateKey": "key", "rawBody": "private"}}})

    def test_cli_handles_empty_and_malformed_input_without_writes(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)], input=json.dumps({"keys": [], "inventories": []}),
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual({}, json.loads(completed.stdout)["state"])
        for raw in ("not json", "[]", json.dumps({"keys": [42]})):
            with self.subTest(raw=raw):
                failed = subprocess.run(
                    [sys.executable, str(SCRIPT)], input=raw,
                    text=True, capture_output=True, check=False,
                )
                self.assertEqual(1, failed.returncode)
                self.assertEqual("failed", json.loads(failed.stdout)["status"])

    def test_scope_changes_drop_feedback_state_for_removed_requests(self):
        first = self.reduce([self.record])
        result = self.module.reduce_feedback({"keys": [], "inventories": [],
                                              "previous": first["state"]})
        self.assertEqual({}, result["state"])

    def test_self_and_suppressed_records_do_not_become_action_suggestions(self):
        suppressed = {**self.record, "selfAuthored": True, "actionability": "suppressed"}
        result = self.reduce([suppressed])
        self.assertFalse(result["deltas"][0]["candidate"])
        self.assertEqual(0, result["summaries"]["acme/widgets#42"]["candidateCount"])
        self.assertEqual(1, result["summaries"]["acme/widgets#42"]["conversationCount"])
