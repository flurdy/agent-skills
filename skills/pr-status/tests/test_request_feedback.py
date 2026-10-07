from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

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
