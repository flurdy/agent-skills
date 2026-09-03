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
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import pi_spend  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def static_policy(classes=None):
    beginning = datetime.min.replace(tzinfo=UTC)
    models = {
        key: (pi_spend.BillingInterval(beginning, None, billing),)
        for key, billing in (classes or {}).items()
    }
    return pi_spend.BillingPolicy(
        pi_spend.EFFECTIVE_POLICY,
        "complete",
        (),
        models,
    )


def row_for(totals, period, key="anthropic/claude-opus-5"):
    matches = [row for row in totals[period].values() if row.key == key]
    if len(matches) != 1:
        raise AssertionError(f"expected one {key} row in {period}, got {len(matches)}")
    return matches[0]


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
            return pi_spend.collect(root, static_policy(policies), now, UTC)

    def test_today_week_and_month_are_nested(self):
        totals, _, _ = self.collect([
            response(NOW - timedelta(hours=1), cost=1.0, response_id="a"),
            response(NOW - timedelta(days=2), cost=2.0, response_id="b"),
            response(NOW - timedelta(days=20), cost=4.0, response_id="c"),
        ])
        self.assertAlmostEqual(row_for(totals, "today").cost, 1.0)
        self.assertAlmostEqual(row_for(totals, "week").cost, 3.0)
        self.assertAlmostEqual(row_for(totals, "month").cost, 7.0)
        self.assertAlmostEqual(row_for(totals, "all").cost, 7.0)

    def test_prior_month_excluded_from_month_but_kept_in_all(self):
        totals, _, _ = self.collect([
            response(NOW - timedelta(days=45), cost=9.0, response_id="old"),
        ])
        self.assertNotIn("month", [p for p in totals if totals[p]])
        self.assertEqual(totals["month"], {})
        self.assertAlmostEqual(row_for(totals, "all").cost, 9.0)

    def test_week_starts_monday(self):
        monday = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)
        sunday_before = datetime(2026, 7, 26, 23, 0, tzinfo=UTC)
        totals, starts, _ = self.collect([
            response(monday, cost=1.0, response_id="mon"),
            response(sunday_before, cost=1.0, response_id="sun"),
        ])
        self.assertEqual(starts["week"].date(), monday.date())
        self.assertAlmostEqual(row_for(totals, "week").cost, 1.0)
        self.assertAlmostEqual(row_for(totals, "month").cost, 2.0)

    def test_future_response_is_skipped_and_counted(self):
        totals, _, stats = self.collect([
            response(NOW + timedelta(seconds=1), cost=2.0, response_id="future"),
        ])

        self.assertEqual(stats["future"], 1)
        self.assertEqual(stats["responses"], 0)
        self.assertEqual(totals["all"], {})

    def test_local_period_boundaries_use_offset_for_boundary_date(self):
        london = ZoneInfo("Europe/London")
        now = datetime(2026, 10, 30, 12, 0, tzinfo=london)

        starts = pi_spend.period_starts(now)

        self.assertEqual(starts["month"].date(), datetime(2026, 10, 1).date())
        self.assertEqual(starts["month"].utcoffset(), timedelta(hours=1))
        self.assertEqual(now.utcoffset(), timedelta(0))

    def test_local_timezone_prefers_named_tz_database_zone(self):
        local = pi_spend.local_timezone({"TZ": "Europe/London"})

        self.assertEqual(getattr(local, "key", None), "Europe/London")

    def test_local_timezone_matches_copied_zoneinfo_file(self):
        with tempfile.TemporaryDirectory() as root:
            zone_root = os.path.join(root, "zoneinfo")
            copied_zone = os.path.join(zone_root, "Europe", "London")
            os.makedirs(os.path.dirname(copied_zone))
            source_zone = next(
                os.path.join(base, "Europe", "London")
                for base in pi_spend.TZPATH
                if os.path.isfile(os.path.join(base, "Europe", "London"))
            )
            with open(source_zone, "rb") as source, open(copied_zone, "wb") as target:
                target.write(source.read())
            localtime = os.path.join(root, "localtime")
            with open(copied_zone, "rb") as source, open(localtime, "wb") as target:
                target.write(source.read())

            local = pi_spend.local_timezone(
                {},
                localtime_path=localtime,
                timezone_path=os.path.join(root, "missing-timezone"),
                zoneinfo_paths=(zone_root,),
            )

        self.assertEqual(datetime(2026, 1, 1, tzinfo=local).utcoffset(), timedelta(0))
        self.assertEqual(
            datetime(2026, 7, 1, tzinfo=local).utcoffset(), timedelta(hours=1)
        )

    def test_epoch_millisecond_timestamps_are_accepted(self):
        record = response(NOW, cost=2.0, response_id="ms")
        record["timestamp"] = None
        record["message"]["timestamp"] = int(NOW.timestamp() * 1000)
        totals, _, _ = self.collect([record])
        self.assertAlmostEqual(row_for(totals, "today").cost, 2.0)


class DeduplicationTest(unittest.TestCase):
    def test_repeated_response_id_counted_once_across_files(self):
        with tempfile.TemporaryDirectory() as root:
            record = response(NOW, cost=3.0, response_id="dup")
            write_session(os.path.join(root, "proj", "parent.jsonl"), [record])
            write_session(os.path.join(root, "proj", "parent", "child", "run-0", "session.jsonl"), [record])
            totals, _, stats = pi_spend.collect(root, static_policy(), NOW, UTC)
        self.assertEqual(stats["files"], 2)
        self.assertEqual(stats["duplicates"], 1)
        self.assertEqual(row_for(totals, "today").requests, 1)
        self.assertAlmostEqual(row_for(totals, "today").cost, 3.0)

    def test_responses_without_id_are_all_counted(self):
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [
                response(NOW, cost=1.0), response(NOW, cost=1.0),
            ])
            totals, _, stats = pi_spend.collect(root, static_policy(), NOW, UTC)
        self.assertEqual(stats["duplicates"], 0)
        self.assertEqual(row_for(totals, "today").requests, 2)


class EffectiveDatedBillingPolicyTest(unittest.TestCase):
    def write_policy(self, payload):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(payload, handle)
        handle.close()
        self.addCleanup(lambda: os.path.exists(handle.name) and os.unlink(handle.name))
        return handle.name

    def test_classifies_exact_model_at_utc_interval_boundaries(self):
        path = self.write_policy({
            "schemaVersion": 1,
            "models": {
                "provider/model-a": [
                    {
                        "effectiveFrom": "2026-01-01T00:00:00Z",
                        "effectiveUntil": "2026-02-01T00:00:00Z",
                        "billing": "metered",
                    },
                    {
                        "effectiveFrom": "2026-02-01T00:00:00Z",
                        "effectiveUntil": None,
                        "billing": "subscription",
                    },
                ],
                "provider/model-b": [
                    {
                        "effectiveFrom": "2026-01-01T00:00:00Z",
                        "effectiveUntil": None,
                        "billing": "subscription",
                    }
                ],
            },
        })

        policy = pi_spend.load_billing_policy(path)

        self.assertEqual(policy.status, "complete")
        self.assertEqual(
            policy.classify("provider", "model-a", datetime(2026, 1, 31, tzinfo=UTC)),
            (pi_spend.METERED, pi_spend.EFFECTIVE_POLICY),
        )
        self.assertEqual(
            policy.classify("provider", "model-a", datetime(2026, 2, 1, tzinfo=UTC)),
            (pi_spend.SUBSCRIPTION, pi_spend.EFFECTIVE_POLICY),
        )
        self.assertEqual(
            policy.classify("other", "model-a", datetime(2026, 2, 1, tzinfo=UTC)),
            (pi_spend.UNKNOWN, pi_spend.UNKNOWN_POLICY),
        )
        self.assertEqual(
            policy.classify("provider", "model-a", datetime(2025, 12, 31, tzinfo=UTC)),
            (pi_spend.UNKNOWN, pi_spend.UNKNOWN_POLICY),
        )

    def test_duplicate_keys_and_nonstandard_constants_invalidate_policy(self):
        for raw in (
            '{"schemaVersion":1,"models":{"provider/model":[],"provider/model":[]}}',
            '{"schemaVersion":1,"models":{"provider/model":NaN}}',
            '{"schemaVersion":true,"models":{}}',
        ):
            with self.subTest(raw=raw):
                handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
                handle.write(raw)
                handle.close()
                self.addCleanup(
                    lambda path=handle.name: os.path.exists(path) and os.unlink(path)
                )

                policy = pi_spend.load_billing_policy(handle.name)

                self.assertEqual(policy.status, "invalid")
                self.assertIn("billing-policy-invalid", policy.diagnostics)
                self.assertEqual(
                    policy.classify("provider", "model", NOW),
                    (pi_spend.UNKNOWN, pi_spend.UNKNOWN_POLICY),
                )

    def test_overlap_and_malformed_intervals_fail_closed_per_model(self):
        path = self.write_policy({
            "schemaVersion": 1,
            "models": {
                "provider/valid": [
                    {
                        "effectiveFrom": "2026-01-01T00:00:00Z",
                        "effectiveUntil": None,
                        "billing": "metered",
                    }
                ],
                "provider/overlap": [
                    {
                        "effectiveFrom": "2026-01-01T00:00:00Z",
                        "effectiveUntil": None,
                        "billing": "metered",
                    },
                    {
                        "effectiveFrom": "2026-02-01T00:00:00Z",
                        "effectiveUntil": None,
                        "billing": "subscription",
                    },
                ],
                "provider/local-time": [
                    {
                        "effectiveFrom": "2026-01-01T00:00:00+01:00",
                        "effectiveUntil": None,
                        "billing": "metered",
                    }
                ],
                "provider/missing-until": [
                    {
                        "effectiveFrom": "2026-01-01T00:00:00Z",
                        "billing": "metered",
                    }
                ],
                "provider/unhashable-billing": [
                    {
                        "effectiveFrom": "2026-01-01T00:00:00Z",
                        "effectiveUntil": None,
                        "billing": [],
                    }
                ],
            },
        })

        policy = pi_spend.load_billing_policy(path)

        self.assertEqual(policy.status, "partial")
        self.assertIn("overlapping-intervals", policy.diagnostics)
        self.assertIn("invalid-interval", policy.diagnostics)
        self.assertEqual(
            policy.classify("provider", "valid", NOW),
            (pi_spend.METERED, pi_spend.EFFECTIVE_POLICY),
        )
        self.assertEqual(
            policy.classify("provider", "overlap", NOW),
            (pi_spend.UNKNOWN, pi_spend.UNKNOWN_POLICY),
        )
        self.assertEqual(
            policy.classify("provider", "local-time", NOW),
            (pi_spend.UNKNOWN, pi_spend.UNKNOWN_POLICY),
        )
        self.assertEqual(
            policy.classify("provider", "missing-until", NOW),
            (pi_spend.UNKNOWN, pi_spend.UNKNOWN_POLICY),
        )
        self.assertEqual(
            policy.classify("provider", "unhashable-billing", NOW),
            (pi_spend.UNKNOWN, pi_spend.UNKNOWN_POLICY),
        )

    def test_collect_preserves_historical_classification_rows(self):
        path = self.write_policy({
            "schemaVersion": 1,
            "models": {
                "anthropic/claude-opus-5": [
                    {
                        "effectiveFrom": "2026-01-01T00:00:00Z",
                        "effectiveUntil": "2026-02-01T00:00:00Z",
                        "billing": "metered",
                    },
                    {
                        "effectiveFrom": "2026-02-01T00:00:00Z",
                        "effectiveUntil": None,
                        "billing": "subscription",
                    },
                ]
            },
        })
        policy = pi_spend.load_billing_policy(path)
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [
                response(datetime(2026, 1, 15, tzinfo=UTC), cost=1.0, response_id="old"),
                response(datetime(2026, 2, 15, tzinfo=UTC), cost=2.0, response_id="new"),
            ])
            totals, _, stats = pi_spend.collect(root, policy, NOW, UTC)

        rows = list(totals["all"].values())
        self.assertEqual({row.billing for row in rows},
                         {pi_spend.METERED, pi_spend.SUBSCRIPTION})
        self.assertEqual({row.billing_source for row in rows},
                         {pi_spend.EFFECTIVE_POLICY})
        self.assertEqual(stats["billingUnknownResponses"], 0)
        self.assertEqual(stats["legacyProjectedResponses"], 0)

    def test_missing_policy_and_legacy_router_are_explicit(self):
        missing = pi_spend.load_billing_policy("/nonexistent/billing-policy.json")
        self.assertEqual(missing.status, "missing")
        self.assertEqual(missing.classify("provider", "model", NOW),
                         (pi_spend.UNKNOWN, pi_spend.UNKNOWN_POLICY))

        path = self.write_policy({"modelPolicies": {
            "provider/model": {"metered": True},
            "other/model": {"metered": False},
            "model": {"metered": True},
        }})
        legacy = pi_spend.load_legacy_router_policy(path)
        self.assertEqual(legacy.source, pi_spend.LEGACY_POLICY)
        self.assertEqual(legacy.classify("provider", "model", NOW),
                         (pi_spend.METERED, pi_spend.LEGACY_POLICY))
        self.assertEqual(legacy.classify("third", "model", NOW),
                         (pi_spend.UNKNOWN, pi_spend.UNKNOWN_POLICY))


    def test_malformed_response_identity_never_matches_policy(self):
        policy = static_policy({
            "unknown/claude-opus-5": pi_spend.METERED,
            "123/claude-opus-5": pi_spend.METERED,
        })
        missing_provider = response(NOW, response_id="missing")
        missing_provider["message"].pop("provider")
        numeric_provider = response(NOW, response_id="numeric")
        numeric_provider["message"]["provider"] = 123
        with tempfile.TemporaryDirectory() as root:
            write_session(
                os.path.join(root, "p", "s.jsonl"),
                [missing_provider, numeric_provider],
            )
            totals, _, stats = pi_spend.collect(root, policy, NOW, UTC)

        self.assertEqual(stats["billingUnknownResponses"], 2)
        self.assertEqual(
            {row.billing for row in totals["all"].values()},
            {pi_spend.UNKNOWN},
        )


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
            totals, _, _ = pi_spend.collect(root, static_policy(policies), NOW, UTC)
        self.assertEqual(row_for(totals, "today").billing, pi_spend.METERED)
        self.assertEqual(
            row_for(totals, "today", "openai-codex/gpt-5.6-sol").billing,
            pi_spend.SUBSCRIPTION,
        )
        self.assertEqual(
            row_for(totals, "today", "google/gemini-3.6-flash").billing,
            pi_spend.UNKNOWN,
        )

class MissingAndMalformedDataTest(unittest.TestCase):
    def test_absent_cost_is_not_treated_as_zero(self):
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [
                response(NOW, cost=None, response_id="a"),
                response(NOW, cost=2.0, response_id="b"),
            ])
            totals, _, _ = pi_spend.collect(root, static_policy(), NOW, UTC)
        row = next(iter(totals["today"].values()))
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
            totals, _, stats = pi_spend.collect(root, static_policy(), NOW, UTC)
        self.assertEqual(stats["unparsable"], 1)
        self.assertEqual(row_for(totals, "today").requests, 1)

    def test_naive_response_timestamp_is_undated(self):
        record = response(NOW, cost=1.0, response_id="naive")
        record["timestamp"] = "2026-07-30T12:00:00"
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [record])
            totals, _, stats = pi_spend.collect(root, static_policy(), NOW, UTC)

        self.assertEqual(stats["undated"], 1)
        self.assertEqual(totals["all"], {})

    def test_undated_responses_are_skipped_and_counted(self):
        record = response(NOW, cost=1.0, response_id="x")
        record["timestamp"] = "not-a-date"
        record["message"].pop("timestamp", None)
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [record])
            totals, _, stats = pi_spend.collect(root, static_policy(), NOW, UTC)
        self.assertEqual(stats["undated"], 1)
        self.assertEqual(totals["all"], {})

    def test_user_messages_are_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [
                {"timestamp": NOW.isoformat(), "message": {"role": "user", "content": "assistant"}},
                response(NOW, cost=1.0, response_id="a"),
            ])
            totals, _, stats = pi_spend.collect(root, static_policy(), NOW, UTC)
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

    def test_json_output_reports_effective_policy_source_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [
                response(datetime.now(UTC), cost=1.0, response_id="a"),
            ])
            missing = os.path.join(root, "missing-billing-policy.json")
            code, out, _ = self.run_cli([
                "--sessions-dir", root,
                "--billing-policy", missing,
                "--json",
            ])

        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["schemaVersion"], 2)
        self.assertEqual(payload["billingPolicy"]["source"], pi_spend.EFFECTIVE_POLICY)
        self.assertEqual(payload["billingPolicy"]["status"], "missing")
        self.assertIn("billing-policy-missing", payload["billingPolicy"]["diagnostics"])
        row = payload["periods"]["all"]["rows"][0]
        self.assertEqual(row["billing"], pi_spend.UNKNOWN)
        self.assertEqual(row["billingSource"], pi_spend.UNKNOWN_POLICY)

    def test_explicit_legacy_router_mode_is_visible(self):
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [
                response(datetime.now(UTC), cost=1.0, response_id="a"),
            ])
            router = os.path.join(root, "router.json")
            with open(router, "w", encoding="utf-8") as handle:
                json.dump({"modelPolicies": {
                    "anthropic/claude-opus-5": {"metered": True}
                }}, handle)
            code, out, _ = self.run_cli([
                "--sessions-dir", root,
                "--router-config", router,
                "--json",
            ])

        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["billingPolicy"]["source"], pi_spend.LEGACY_POLICY)
        self.assertEqual(payload["stats"]["legacyProjectedResponses"], 1)
        row = payload["periods"]["all"]["rows"][0]
        self.assertEqual(row["billing"], pi_spend.METERED)
        self.assertEqual(row["billingSource"], pi_spend.LEGACY_POLICY)

    def test_text_output_prominently_labels_legacy_projection(self):
        with tempfile.TemporaryDirectory() as root:
            write_session(
                os.path.join(root, "p", "s.jsonl"),
                [response(datetime.now(UTC), cost=1.0, response_id="a")],
            )
            router = os.path.join(root, "router.json")
            with open(router, "w", encoding="utf-8") as handle:
                json.dump(
                    {"modelPolicies": {"anthropic/claude-opus-5": {"metered": True}}},
                    handle,
                )
            code, out, _ = self.run_cli(
                ["--sessions-dir", root, "--router-config", router]
            )

        self.assertEqual(code, 0)
        self.assertIn("legacy-current-router-policy", out)
        self.assertIn("LEGACY:", out)
        self.assertIn("may relabel history", out)

    def test_json_output_shape(self):
        with tempfile.TemporaryDirectory() as root:
            write_session(os.path.join(root, "p", "s.jsonl"), [
                response(datetime.now(UTC), cost=1.0, response_id="a"),
            ])
            code, out, _ = self.run_cli(
                [
                    "--sessions-dir",
                    root,
                    "--billing-policy",
                    "/nonexistent.json",
                    "--json",
                ]
            )
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
