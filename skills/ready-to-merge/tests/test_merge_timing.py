"""Evaluate merge-timing policies offline with fixed clocks and temporary repositories."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "merge-timing.py"

BUSINESS = """
timezone = "Europe/London"

[[rule]]
name = "business-hours"
enforcement = "required"
days = ["mon", "tue", "wed", "thu", "fri"]
start = "09:00"
end = "17:30"
"""

AFTERNOON = """
[[rule]]
name = "late-afternoon"
enforcement = "advisory"
end = "16:00"
end_by_day = { fri = "12:00" }
"""


class MergeTimingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="merge timing ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "client" / "repo"
        self.repo.mkdir(parents=True)
        self.git("init", "-q", "-b", "main")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.invalid",
                 "commit", "-q", "--allow-empty", "-m", "init")

    def git(self, *args, cwd=None):
        subprocess.run(["git", *args], cwd=cwd or self.repo, check=True, capture_output=True)

    def policy(self, text, where=None):
        path = (where or self.root / "client") / "merge-timing.toml"
        path.write_text(text)
        return path

    def run_helper(self, now, repo=None, tz="UTC"):
        env = {**os.environ, "TZ": tz}
        result = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--repo", str(repo or self.repo), "--now", now],
            env=env, text=True, capture_output=True, timeout=30,
        )
        return result.returncode, json.loads(result.stdout) if result.stdout else None, result.stderr

    def evaluate(self, now, **kwargs):
        code, data, stderr = self.run_helper(now, **kwargs)
        self.assertIn(code, (0, 3), stderr)
        return data

    def test_absent_policy_is_none(self):
        self.assertEqual(self.evaluate("2026-10-16T17:00:00+01:00"), {"status": "none"})

    def test_business_hours_inside_and_outside(self):
        self.policy(BUSINESS)
        inside = self.evaluate("2026-10-14T10:00:00+01:00")
        self.assertEqual(inside["status"], "clear")
        self.assertEqual(inside["violations"], [])
        self.assertIsNone(inside["next_allowed"])
        outside = self.evaluate("2026-10-14T18:00:00+01:00")
        self.assertEqual(outside["status"], "required")
        self.assertEqual(outside["local_time"], "2026-10-14T18:00+01:00")
        self.assertEqual(outside["weekday"], "wed")
        self.assertEqual(outside["violations"][0]["rule"], "business-hours")
        self.assertIn("17:30", outside["violations"][0]["reason"])
        self.assertEqual(outside["next_allowed"], "2026-10-15T09:00+01:00")

    def test_precise_window_boundaries(self):
        self.policy(BUSINESS)
        for local, status in (("08:59", "required"), ("09:00", "clear"),
                              ("17:29", "clear"), ("17:30", "required")):
            with self.subTest(local=local):
                self.assertEqual(self.evaluate(f"2026-10-14T{local}:00+01:00")["status"], status)

    def test_ordinary_and_friday_cutoffs_are_advisory(self):
        self.policy('timezone = "Europe/London"\n' + AFTERNOON)
        for now, status in (("2026-10-15T15:59:00+01:00", "clear"),
                            ("2026-10-15T16:00:00+01:00", "advisory"),
                            ("2026-10-16T11:59:00+01:00", "clear"),
                            ("2026-10-16T12:00:00+01:00", "advisory")):
            with self.subTest(now=now):
                self.assertEqual(self.evaluate(now)["status"], status)
        friday = self.evaluate("2026-10-16T12:00:00+01:00")
        self.assertIn("12:00", friday["violations"][0]["reason"])
        self.assertIn("Fri", friday["violations"][0]["reason"])

    def test_required_beats_advisory_and_rolls_over_the_weekend(self):
        self.policy(BUSINESS + AFTERNOON)
        data = self.evaluate("2026-10-16T17:45:00+01:00")
        self.assertEqual(data["status"], "required")
        self.assertEqual([v["rule"] for v in data["violations"]], ["business-hours", "late-afternoon"])
        self.assertEqual(data["next_allowed"], "2026-10-19T09:00+01:00")

    def test_all_friday_restriction(self):
        self.policy('timezone = "Europe/London"\n[[rule]]\nname = "no-friday"\n'
                    'enforcement = "required"\ndays = ["mon", "tue", "wed", "thu"]\n')
        data = self.evaluate("2026-10-16T10:00:00+01:00")
        self.assertEqual(data["status"], "required")
        self.assertIn("Fri is not an allowed merge day", data["violations"][0]["reason"])
        self.assertEqual(data["next_allowed"], "2026-10-19T00:00+01:00")

    def test_machine_timezone_does_not_change_the_result(self):
        self.policy(BUSINESS)
        now = "2026-10-14T16:30:00+00:00"  # 17:30 in London
        results = {tz: self.evaluate(now, tz=tz) for tz in ("UTC", "Pacific/Auckland", "America/Los_Angeles")}
        self.assertEqual(len({json.dumps(r, sort_keys=True) for r in results.values()}), 1, results)
        self.assertEqual(results["UTC"]["status"], "required")

    def test_daylight_saving_transitions(self):
        self.policy('timezone = "Europe/London"\n[[rule]]\nenforcement = "required"\n'
                    'start = "09:00"\nend = "17:30"\n')
        for now, status, local in (("2026-03-28T08:30:00+00:00", "required", "2026-03-28T08:30+00:00"),
                                   ("2026-03-29T08:30:00+00:00", "clear", "2026-03-29T09:30+01:00"),
                                   ("2026-10-24T08:30:00+00:00", "clear", "2026-10-24T09:30+01:00"),
                                   ("2026-10-25T08:30:00+00:00", "required", "2026-10-25T08:30+00:00")):
            with self.subTest(now=now):
                data = self.evaluate(now)
                self.assertEqual((data["status"], data["local_time"]), (status, local))
        self.assertEqual(self.evaluate("2026-03-28T18:00:00+00:00")["next_allowed"], "2026-03-29T09:00+01:00")
        self.assertEqual(self.evaluate("2026-10-24T17:00:00+00:00")["next_allowed"], "2026-10-25T09:00+00:00")

    def test_time_crossing_a_cutoff_between_report_and_execution(self):
        self.policy('timezone = "Europe/London"\n[[rule]]\nenforcement = "required"\n'
                    'end_by_day = { fri = "12:00" }\n')
        self.assertEqual(self.evaluate("2026-10-16T11:59:59+01:00")["status"], "clear")
        self.assertEqual(self.evaluate("2026-10-16T12:00:00+01:00")["status"], "required")

    def test_malformed_policy_is_unknown(self):
        cases = {
            "toml": "timezone = \n",
            "unknown top key": 'timezone = "UTC"\nenforcment = "required"\n[[rule]]\nenforcement = "advisory"\nend = "16:00"\n',
            "unknown rule key": 'timezone = "UTC"\n[[rule]]\nenforcement = "advisory"\nends = "16:00"\n',
            "missing timezone": '[[rule]]\nenforcement = "advisory"\nend = "16:00"\n',
            "bad timezone": 'timezone = "Mars/Olympus"\n[[rule]]\nenforcement = "advisory"\nend = "16:00"\n',
            "missing enforcement": 'timezone = "UTC"\n[[rule]]\nend = "16:00"\n',
            "bad enforcement": 'timezone = "UTC"\n[[rule]]\nenforcement = "strict"\nend = "16:00"\n',
            "no rules": 'timezone = "UTC"\n',
            "empty rule": 'timezone = "UTC"\n[[rule]]\nenforcement = "required"\n',
            "bad time": 'timezone = "UTC"\n[[rule]]\nenforcement = "required"\nend = "4pm"\n',
            "start after end": 'timezone = "UTC"\n[[rule]]\nenforcement = "required"\nstart = "17:00"\nend = "09:00"\n',
            "empty days": 'timezone = "UTC"\n[[rule]]\nenforcement = "required"\ndays = []\n',
            "bad day": 'timezone = "UTC"\n[[rule]]\nenforcement = "required"\ndays = ["friday"]\n',
            "cutoff on disallowed day": 'timezone = "UTC"\n[[rule]]\nenforcement = "required"\n'
                                        'days = ["mon"]\nend_by_day = { fri = "12:00" }\n',
            "duplicate names": 'timezone = "UTC"\n[[rule]]\nname = "a"\nenforcement = "required"\nend = "16:00"\n'
                               '[[rule]]\nname = "a"\nenforcement = "advisory"\nend = "15:00"\n',
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                self.policy(text)
                code, data, _ = self.run_helper("2026-10-14T10:00:00+01:00")
                self.assertEqual(code, 3)
                self.assertEqual(data["status"], "unknown")
                self.assertTrue(data["error"])

    def test_unavailable_policy_is_unknown(self):
        (self.root / "client" / "merge-timing.toml").mkdir()
        code, data, _ = self.run_helper("2026-10-14T10:00:00+01:00")
        self.assertEqual((code, data["status"]), (3, "unknown"))

    @unittest.skipIf(os.geteuid() == 0, "root can read any file")
    def test_unreadable_policy_is_unknown(self):
        path = self.policy(BUSINESS)
        path.chmod(0)
        self.addCleanup(path.chmod, 0o600)
        code, data, _ = self.run_helper("2026-10-14T10:00:00+01:00")
        self.assertEqual((code, data["status"]), (3, "unknown"))

    def test_in_repository_policy_cannot_relax_trusted_policy(self):
        self.policy(BUSINESS)
        self.policy('timezone = "UTC"\n[[rule]]\nenforcement = "advisory"\nend = "24:00"\n', where=self.repo)
        data = self.evaluate("2026-10-14T18:00:00+01:00")
        self.assertEqual(data["status"], "required")
        self.assertEqual(data["policy"], str(self.root / "client" / "merge-timing.toml"))
        self.assertEqual(data["ignored"], [str(self.repo / "merge-timing.toml")])

    def test_in_repository_policy_alone_is_reported_but_not_applied(self):
        self.policy(BUSINESS, where=self.repo)
        self.assertEqual(self.evaluate("2026-10-14T18:00:00+01:00"),
                         {"status": "none", "ignored": [str(self.repo / "merge-timing.toml")]})

    def test_policy_inside_another_checkout_of_the_same_repository_is_unknown(self):
        worktree = self.repo / ".worktrees" / "topic"
        self.git("worktree", "add", "-q", "-b", "topic", str(worktree))
        self.policy(BUSINESS, where=self.repo)
        code, data, _ = self.run_helper("2026-10-14T10:00:00+01:00", repo=worktree)
        self.assertEqual((code, data["status"]), (3, "unknown"))
        self.assertIn("same repository", data["error"])

    def test_nearest_trusted_policy_wins(self):
        self.policy('timezone = "UTC"\n[[rule]]\nenforcement = "required"\nend = "01:00"\n', where=self.root)
        self.policy(BUSINESS)
        self.assertEqual(self.evaluate("2026-10-14T10:00:00+01:00")["status"], "clear")

    def test_outside_a_repository_is_unknown(self):
        outside = self.root / "plain"
        outside.mkdir()
        code, data, _ = self.run_helper("2026-10-14T10:00:00+01:00", repo=outside)
        self.assertEqual((code, data["status"]), (3, "unknown"))

    def test_naive_now_is_rejected(self):
        code, _, stderr = self.run_helper("2026-10-14T10:00:00")
        self.assertEqual(code, 2)
        self.assertIn("offset", stderr)


if __name__ == "__main__":
    unittest.main()
