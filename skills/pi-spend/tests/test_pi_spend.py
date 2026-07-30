#!/usr/bin/env python3
"""Tests for the pi-spend collector."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import pi_spend  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def response(when, provider="anthropic", model="claude-opus-5", cost=1.5,
             response_id=None, input_tokens=100, output_tokens=10):
    usage = {
        "input": input_tokens,
        "output": output_tokens,
        "cacheRead": 5,
        "cacheWrite": 0,
        "reasoning": 3,
    }
    if cost is not None:
        usage["cost"] = {"input": cost, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": cost}
    message = {"role": "assistant", "provider": provider, "model": model, "usage": usage}
    if response_id is not None:
        message["responseId"] = response_id
    return {"type": "message", "timestamp": when.isoformat().replace("+00:00", "Z"), "message": message}


def write_session(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


class PeriodBucketingTest(unittest.TestCase):
    def collect(self, records, policies=None, now=NOW):
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "proj", "session.jsonl"), records)
            return pi_spend.collect(root, policies or {}, now, UTC)

    def test_today_week_and_month_are_nested(self):
        totals, _, _ = self.collect([
            response(NOW - timedelta(hours=1), cost=1.0, response_id="a"),
            response(NOW - timedelta(days=2), cost=2.0, response_id="b"),
            response(NOW - timedelta(days=20), cost=4.0, response_id="c"),
        ])
        self.assertAlmostEqual(totals["today"]["anthropic/claude-opus-5"].cost, 1.0)
        self.assertAlmostEqual(totals["week"]["anthropic/claude-opus-5"].cost, 3.0)
        self.assertAlmostEqual(totals["month"]["anthropic/claude-opus-5"].cost, 7.0)
        self.assertAlmostEqual(totals["all"]["anthropic/claude-opus-5"].cost, 7.0)

    def test_prior_month_excluded_from_month_but_kept_in_all(self):
        totals, _, _ = self.collect([
            response(NOW - timedelta(days=45), cost=9.0, response_id="old"),
        ])
        self.assertNotIn("month", [p for p in totals if totals[p]])
        self.assertEqual(totals["month"], {})
        self.assertAlmostEqual(totals["all"]["anthropic/claude-opus-5"].cost, 9.0)

    def test_week_starts_monday(self):
        monday = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)
        sunday_before = datetime(2026, 7, 26, 23, 0, tzinfo=UTC)
        totals, starts, _ = self.collect([
            response(monday, cost=1.0, response_id="mon"),
            response(sunday_before, cost=1.0, response_id="sun"),
        ])
        self.assertEqual(starts["week"].date(), monday.date())
        self.assertAlmostEqual(totals["week"]["anthropic/claude-opus-5"].cost, 1.0)
        self.assertAlmostEqual(totals["month"]["anthropic/claude-opus-5"].cost, 2.0)

    def test_epoch_millisecond_timestamps_are_accepted(self):
        record = response(NOW, cost=2.0, response_id="ms")
        record["timestamp"] = None
        record["message"]["timestamp"] = int(NOW.timestamp() * 1000)
        totals, _, _ = self.collect([record])
        self.assertAlmostEqual(totals["today"]["anthropic/claude-opus-5"].cost, 2.0)


class DeduplicationTest(unittest.TestCase):
    def test_repeated_response_id_counted_once_across_files(self):
        with tempfile.TemporaryDirectory() as root:
            record = response(NOW, cost=3.0, response_id="dup")
            write_session(os.path.join(root, "proj", "parent.jsonl"), [record])
            write_session(os.path.join(root, "proj", "parent", "child", "run-0", "session.jsonl"), [record])
            totals, _, stats = pi_spend.collect(root, {}, NOW, UTC)
        self.assertEqual(stats["files"], 2)
        self.assertEqual(stats["duplicates"], 1)
        self.assertEqual(totals["today"]["anthropic/claude-opus-5"].requests, 1)
        self.assertAlmostEqual(totals["today"]["anthropic/claude-opus-5"].cost, 3.0)

    def test_responses_without_id_are_all_counted(self):
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [
                response(NOW, cost=1.0), response(NOW, cost=1.0),
            ])
            totals, _, stats = pi_spend.collect(root, {}, NOW, UTC)
        self.assertEqual(stats["duplicates"], 0)
        self.assertEqual(totals["today"]["anthropic/claude-opus-5"].requests, 2)


class BillingClassificationTest(unittest.TestCase):
    def test_policy_marks_metered_and_subscription(self):
        policies = {"anthropic/claude-opus-5": pi_spend.METERED,
                    "openai-codex/gpt-5.6-sol": pi_spend.SUBSCRIPTION}
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [
                response(NOW, cost=5.0, response_id="a"),
                response(NOW, provider="openai-codex", model="gpt-5.6-sol", cost=50.0, response_id="b"),
                response(NOW, provider="google", model="gemini-3.6-flash", cost=1.0, response_id="c"),
            ])
            totals, _, _ = pi_spend.collect(root, policies, NOW, UTC)
        rows = totals["today"]
        self.assertEqual(rows["anthropic/claude-opus-5"].billing, pi_spend.METERED)
        self.assertEqual(rows["openai-codex/gpt-5.6-sol"].billing, pi_spend.SUBSCRIPTION)
        self.assertEqual(rows["google/gemini-3.6-flash"].billing, pi_spend.UNKNOWN)

    def test_load_policies_from_router_config(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"modelPolicies": {
                "anthropic/claude-opus-5": {"metered": True, "consent": "allow"},
                "openai-codex/gpt-5.6-sol": {"metered": False},
                "broken/model": {"consent": "ask"},
            }}, handle)
            path = handle.name
        try:
            policies = pi_spend.load_billing_policies(path)
        finally:
            os.unlink(path)
        self.assertEqual(policies["anthropic/claude-opus-5"], pi_spend.METERED)
        self.assertEqual(policies["openai-codex/gpt-5.6-sol"], pi_spend.SUBSCRIPTION)
        self.assertNotIn("broken/model", policies)

    def test_missing_router_config_yields_no_policies(self):
        self.assertEqual(pi_spend.load_billing_policies("/nonexistent/router.json"), {})


class MissingAndMalformedDataTest(unittest.TestCase):
    def test_absent_cost_is_not_treated_as_zero(self):
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [
                response(NOW, cost=None, response_id="a"),
                response(NOW, cost=2.0, response_id="b"),
            ])
            totals, _, _ = pi_spend.collect(root, {}, NOW, UTC)
        row = totals["today"]["anthropic/claude-opus-5"]
        self.assertEqual(row.requests, 2)
        self.assertEqual(row.cost_missing, 1)
        self.assertAlmostEqual(row.cost, 2.0)

    def test_malformed_lines_are_counted_not_fatal(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "p", "s.jsonl")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('{"message":{"role":"assistant" BROKEN\n')
                handle.write(json.dumps(response(NOW, cost=1.0, response_id="ok")) + "\n")
            totals, _, stats = pi_spend.collect(root, {}, NOW, UTC)
        self.assertEqual(stats["unparsable"], 1)
        self.assertEqual(totals["today"]["anthropic/claude-opus-5"].requests, 1)

    def test_undated_responses_are_skipped_and_counted(self):
        record = response(NOW, cost=1.0, response_id="x")
        record["timestamp"] = "not-a-date"
        record["message"].pop("timestamp", None)
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [record])
            totals, _, stats = pi_spend.collect(root, {}, NOW, UTC)
        self.assertEqual(stats["undated"], 1)
        self.assertEqual(totals["all"], {})

    def test_user_messages_are_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [
                {"timestamp": NOW.isoformat(), "message": {"role": "user", "content": "assistant"}},
                response(NOW, cost=1.0, response_id="a"),
            ])
            totals, _, stats = pi_spend.collect(root, {}, NOW, UTC)
        self.assertEqual(stats["responses"], 1)


class CommandLineTest(unittest.TestCase):
    def run_cli(self, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = pi_spend.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_missing_sessions_dir_exits_two(self):
        code, _, err = self.run_cli(["--sessions-dir", "/nonexistent/pi/sessions"])
        self.assertEqual(code, 2)
        self.assertIn("not found", err)

    def test_json_output_shape(self):
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [
                response(datetime.now(UTC), cost=1.0, response_id="a"),
            ])
            code, out, _ = self.run_cli(["--sessions-dir", root, "--router-config",
                                         "/nonexistent.json", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["schemaVersion"], pi_spend.SCHEMA_VERSION)
        self.assertEqual(payload["costAuthority"], "pi-catalog-estimate")
        self.assertEqual(set(payload["periods"]), set(pi_spend.PERIODS))
        row = payload["periods"]["all"]["rows"][0]
        self.assertEqual(row["provider"], "anthropic")
        self.assertEqual(row["billing"], pi_spend.UNKNOWN)

    def test_metered_only_filters_rows(self):
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [
                response(datetime.now(UTC), cost=1.0, response_id="a"),
                response(datetime.now(UTC), provider="openai-codex", model="gpt-5.6-sol",
                         cost=9.0, response_id="b"),
            ])
            config = os.path.join(root, "router.json")
            with open(config, "w", encoding="utf-8") as handle:
                json.dump({"modelPolicies": {
                    "anthropic/claude-opus-5": {"metered": True},
                    "openai-codex/gpt-5.6-sol": {"metered": False},
                }}, handle)
            code, out, _ = self.run_cli(["--sessions-dir", root, "--router-config", config,
                                         "--json", "--metered-only"])
        self.assertEqual(code, 0)
        rows = json.loads(out)["periods"]["all"]["rows"]
        self.assertEqual([r["provider"] for r in rows], ["anthropic"])

    def test_period_selection_limits_text_output(self):
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [
                response(datetime.now(UTC), cost=1.0, response_id="a"),
            ])
            code, out, _ = self.run_cli(["--sessions-dir", root, "--period", "today"])
        self.assertEqual(code, 0)
        self.assertIn("== TODAY ==", out)
        self.assertNotIn("== MONTH ==", out)

    def test_text_output_states_estimate_disclaimer(self):
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [
                response(datetime.now(UTC), cost=1.0, response_id="a"),
            ])
            code, out, _ = self.run_cli(["--sessions-dir", root])
        self.assertEqual(code, 0)
        self.assertIn("not a provider invoice", out)


if __name__ == "__main__":
    unittest.main()
