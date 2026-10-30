from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


HELPER = Path(__file__).resolve().parents[1] / "scripts" / "retention.py"


class JiraRetentionTests(unittest.TestCase):
    def run_jira(self, issues: list[dict], handoff_date: str = "2026-07-01") -> dict:
        result = subprocess.run(
            [sys.executable, str(HELPER), "jira", "--keys", "ABC-123,ABC-456",
             "--handoff-date", handoff_date, "--today", "2026-08-20", "--days", "14"],
            input=json.dumps({"issues": issues}), text=True, capture_output=True, check=True,
        )
        return json.loads(result.stdout)

    @staticmethod
    def issue(key: str, resolved: str | None, status: str = "done") -> dict:
        return {"key": key, "fields": {"status": {"statusCategory": {"key": status}},
                                       "resolutiondate": resolved}}

    def test_all_done_uses_latest_resolution_and_inclusive_boundary(self) -> None:
        for resolved, expected in (
            ("2026-08-20T10:00:00.000+0000", ""),
            ("2026-08-06T00:00:00Z", ""),
            ("2026-08-05T23:59:59Z", "safe"),
            ("2026-08-05T23:59:59.000+0000", "safe"),
            ("2026-08-05T23:30:00-0200", ""),
            (None, ""), ("bad", ""), ("2026-08-01", ""),
            ("2026-08-01T00:00:00", ""), ("2026-08-21T00:00:00Z", ""),
            ("2000-01-01T00:00:00+00:99", ""), ("2000-01-01T00:00:00-0099", ""),
        ):
            with self.subTest(resolved=resolved):
                actual = self.run_jira([self.issue("ABC-123", "2000-01-01T00:00:00Z"),
                                        self.issue("ABC-456", resolved)])
                self.assertEqual(actual, {"done": True, "archive_class": expected})

    def test_recent_handoff_with_old_resolution_is_retained(self) -> None:
        issues = [self.issue(key, "2000-01-01T00:00:00Z") for key in ("ABC-123", "ABC-456")]
        for date in ("2026-08-20", "2026-08-06", "invalid"):
            with self.subTest(date=date):
                self.assertEqual(self.run_jira(issues, date), {"done": True, "archive_class": ""})

    def test_missing_or_reopened_ticket_is_not_done(self) -> None:
        done = self.issue("ABC-123", "2000-01-01T00:00:00Z")
        for issues in ([done], [done, self.issue("ABC-456", "2000-01-01T00:00:00Z", "indeterminate")], []):
            with self.subTest(issues=issues):
                self.assertEqual(self.run_jira(issues), {"done": False, "archive_class": ""})

    def test_malformed_and_duplicate_jira_rows_fail_closed(self) -> None:
        done = self.issue("ABC-123", "2000-01-01T00:00:00Z")
        for malformed in (
            {"key": []}, {"key": "ABC-456", "fields": "invalid"},
            {"key": "ABC-456", "fields": {"status": "invalid"}},
            {"key": "ABC-456", "fields": {"status": {"statusCategory": None}}},
        ):
            with self.subTest(malformed=malformed):
                self.assertEqual(self.run_jira([done, malformed]), {"done": False, "archive_class": ""})
        duplicate = [done, self.issue("ABC-456", "2000-01-01T00:00:00Z"), self.issue("ABC-456", None, "indeterminate")]
        for rows in (duplicate, list(reversed(duplicate))):
            self.assertEqual(self.run_jira(rows), {"done": False, "archive_class": ""})

    def test_both_consumers_share_completion_clock_and_clear_assisted_flags(self) -> None:
        skill = HELPER.parents[1]
        reference = (skill / "REFERENCE.md").read_text()
        self.assertIn("## §Retention", reference)
        self.assertIn("resolutiondate", reference)
        self.assertIn("retention.py jira", reference)
        self.assertIn("clear both `needs-review` and `needs-age-review`", reference)
        self.assertIn("current-repo and workspace-member", reference)
        for path in (skill / "SKILL.md", skill.parent / "handoffs-tidy" / "SKILL.md"):
            text = path.read_text()
            self.assertIn("--retention-days N", text)
            self.assertIn("REFERENCE §Retention", text)


if __name__ == "__main__":
    unittest.main()
