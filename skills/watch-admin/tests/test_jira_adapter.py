import importlib.util
import json
from pathlib import Path
import sys
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "jira_adapter.py"
SPEC = importlib.util.spec_from_file_location("watch_admin_jira", SCRIPT)
adapter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = adapter
assert SPEC.loader
SPEC.loader.exec_module(adapter)

NOW = "2026-08-05T09:00:00Z"


def issue(key="GE-1", **fields):
    values = {
        "status": {"name": "In Progress"},
        "priority": {"name": "Medium"},
        "assignee": {"accountId": "ivar"},
        "customfield_10020": [
            {"id": 38, "name": "GE Sprint 38", "state": "future", "startDate": "2026-08-12"},
            {"id": 37, "name": "GE Sprint 37", "state": "active", "startDate": "2026-08-05"},
        ],
        "duedate": "2026-08-20",
    }
    values.update(fields)
    return {"key": key, "fields": values}


class JiraAdapterTest(unittest.TestCase):
    def test_projects_exact_fields_and_active_sprint(self):
        jira_issue = issue()
        jira_issue["expand"] = "renderedFields,names,schema"
        envelope = adapter.adapt({"issues": [jira_issue], "isLast": True}, NOW)

        self.assertEqual("complete", envelope["status"])
        self.assertEqual(
            {
                "id": "GE-1",
                "status": "In Progress",
                "priority": "Medium",
                "assignee": "ivar",
                "sprint": "GE Sprint 37",
                "due": "2026-08-20",
            },
            envelope["records"][0],
        )

    def test_next_page_or_overflow_is_partial_and_stably_truncated(self):
        payload = {"issues": [issue(f"GE-{index:03}") for index in range(120)], "nextPageToken": "more"}

        envelope = adapter.adapt(payload, NOW)

        self.assertEqual("partial", envelope["status"])
        self.assertEqual(adapter.RECORD_CAP, envelope["coverage"]["included"])
        self.assertEqual("GE-000", envelope["records"][0]["id"])
        self.assertGreater(envelope["coverage"]["omitted"], 0)
        self.assertLessEqual(len(json.dumps(envelope, separators=(",", ":")).encode()), adapter.ENVELOPE_BYTES)

    def test_malformed_duplicate_and_hostile_payloads_are_errors(self):
        payloads = [
            {"issues": "not-an-array"},
            {"issues": [issue(), issue()]},
            {"issues": [issue("GE-\u0000")]},
            {"issues": [{"key": "GE-1", "fields": {"unknown": "field"}}]},
        ]
        for payload in payloads:
            with self.subTest(payload=str(payload)[:40]):
                envelope = adapter.adapt(payload, NOW)
                self.assertEqual("error", envelope["status"])
                self.assertEqual([], envelope["records"])
                self.assertLessEqual(len(envelope["error"].encode()), adapter.DIAGNOSTIC_BYTES)

    def test_error_payload_is_source_error_without_raw_body(self):
        envelope = adapter.adapt({"error": "PRIVATE\nstack trace"}, NOW)
        self.assertEqual("error", envelope["status"])
        self.assertNotIn("PRIVATE", envelope["error"])


if __name__ == "__main__":
    unittest.main()
