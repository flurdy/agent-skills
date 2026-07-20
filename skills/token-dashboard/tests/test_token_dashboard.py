import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error


SCRIPT = Path(__file__).parents[1] / "scripts" / "token_dashboard.py"
SPEC = importlib.util.spec_from_file_location("token_dashboard", SCRIPT)
td = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = td
assert SPEC.loader
SPEC.loader.exec_module(td)


class Fixture:
    def __init__(self, root: Path):
        self.root = root
        self.claude = root / ".claude" / "projects"
        self.pi = root / ".pi" / "agent" / "sessions"
        self.codex = root / ".codex" / "sessions"

    def line(self, relative: str, *rows):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return path

    @property
    def roots(self):
        return {"claude": self.claude, "pi": self.pi, "codex": self.codex}


def claude_row(message_id, timestamp, usage, model="claude-test", **extra):
    row = {
        "type": "assistant",
        "timestamp": timestamp,
        "sessionId": "claude-parent",
        "message": {"id": message_id, "model": model, "usage": usage, "content": "PRIVATE_SENTINEL_PROMPT"},
        "response": "PRIVATE_SENTINEL_RESPONSE",
    }
    row.update(extra)
    return row


def pi_message(message_id, timestamp, usage, **extra):
    message = {
        "role": "assistant",
        "provider": "test-provider",
        "model": "pi-test",
        "usage": usage,
        "content": "PRIVATE_SENTINEL_PROMPT",
    }
    message.update(extra.pop("message", {}))
    return {"type": "message", "id": message_id, "timestamp": timestamp, "message": message, **extra}


def codex_token(timestamp, total, last):
    return {
        "timestamp": timestamp,
        "type": "event_msg",
        "payload": {"type": "token_count", "info": {"total_token_usage": total, "last_token_usage": last}},
    }


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = Fixture(Path(self.temp.name))
        self.now = td.parse_time("2026-07-20T12:00:00Z")

    def dashboard(self, **kwargs):
        env = {"HOME": self.temp.name}
        env.update(kwargs.pop("environ", {}))
        return td.build_dashboard(
            self.now,
            self.fixture.roots,
            kwargs.pop("offline", True),
            kwargs.pop("base_url", "https://example.invalid"),
            0.2,
            kwargs.pop("explicit_session", None),
            env,
        )

    def test_claude_parent_subagent_background_global_dedup_and_nested_exclusion(self):
        usage = {"input_tokens": 10, "output_tokens": 4, "cache_creation_input_tokens": 3, "cache_read_input_tokens": 2}
        parent = claude_row("m-parent", "2026-07-20T01:00:00Z", usage)
        duplicate = claude_row("m-parent", "2026-07-20T01:00:01Z", {**usage, "output_tokens": 5})
        child = claude_row("m-child", "2026-07-20T01:01:00Z", {"input_tokens": 7, "output_tokens": 2, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0})
        background = claude_row("m-bg", "2026-07-20T01:02:00Z", {"input_tokens": 8, "output_tokens": 3, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0})
        request_duplicate = claude_row(None, "2026-07-20T01:02:10Z", {"input_tokens": 6, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}, requestId="request-1")
        fallback_duplicate = claude_row(None, "2026-07-20T01:02:20Z", {"input_tokens": 9, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0})
        nested = {
            "type": "user",
            "timestamp": "2026-07-20T01:03:00Z",
            "toolUseResult": {"type": "assistant", "message": {"usage": {"input_tokens": 99999}}},
            "journal": {"usage": {"input_tokens": 99999}},
        }
        self.fixture.line(".claude/projects/project/claude-parent.jsonl", parent, request_duplicate, fallback_duplicate, nested)
        self.fixture.line(".claude/projects/project/claude-parent/subagents/agent-a.jsonl", child, duplicate, request_duplicate, fallback_duplicate)
        self.fixture.line(".claude/projects/project/claude-parent/extra-agents/agent-b.jsonl", background)

        result = td.collect_claude(self.fixture.claude)
        self.assertEqual(len(result.events), 5)
        self.assertEqual(result.conflicts, 0)
        rows = td.aggregate_events(result.events, "week")
        self.assertEqual(sum(row["input"] for row in rows), 40)
        self.assertEqual(sum(row["output"] or 0 for row in rows), 10)
        self.assertEqual(sum(row["requests"] for row in rows), 5)
        self.assertEqual(result.status, "ok")

    def test_claude_incompatible_duplicate_snapshot_is_partial(self):
        first = claude_row("m", "2026-07-20T01:00:00Z", {"input_tokens": 10, "output_tokens": 4})
        incompatible = claude_row("m", "2026-07-20T01:00:01Z", {"input_tokens": 9, "output_tokens": 5})
        self.fixture.line(".claude/projects/project/session.jsonl", first, incompatible)

        result = td.collect_claude(self.fixture.claude)
        self.assertEqual(result.conflicts, 1)
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.events[0].usage["input"], 10)
        self.assertEqual(result.events[0].usage["output"], 5)

    def test_pi_parent_and_structurally_nested_child_are_selected_once(self):
        parent_header = {"type": "session", "id": "pi-parent"}
        child_header = {"type": "session", "id": "pi-child"}
        usage = {"input": 5, "output": 7, "cacheRead": 2, "cacheWrite": 1, "reasoning": 3, "totalTokens": 13}
        self.fixture.line(".pi/agent/sessions/encoded-cwd/pi-parent.jsonl", parent_header, pi_message("p1", "2026-07-20T02:00:00Z", usage))
        self.fixture.line(".pi/agent/sessions/encoded-cwd/pi-parent/run-id/run-1/session.jsonl", child_header, pi_message("c1", "2026-07-20T02:01:00Z", usage))
        self.fixture.line(".pi/agent/sessions/encoded-cwd/pi-parent/run-id/run-2/session.jsonl", child_header, pi_message("c1", "2026-07-20T02:01:00Z", usage), {
            "type": "message", "message": {"role": "toolResult", "usage": {"input": 10000}, "content": "PRIVATE_SENTINEL_TOOL_OUTPUT"}
        })

        dashboard = self.dashboard(environ={"PI_CODING_AGENT": "true", "PI_SUBAGENT_PARENT_SESSION": "pi-parent"})
        rows = [row for row in dashboard["usage"] if row["scope"] == "current-session" and row["source"] == "pi-local"]
        self.assertEqual(sum(row["requests"] for row in rows), 2)
        self.assertEqual(sum(row["input"] for row in rows), 10)
        self.assertTrue(all(row["semantics"]["reasoningSubsetOfOutput"] for row in rows))
        self.assertEqual(dashboard["periods"]["current-session"]["selection"]["sources"]["pi-local"]["precision"], "runtime-match")
        self.assertEqual(dashboard["periods"]["current-session"]["completeness"], "complete")

        estimated = self.dashboard()
        estimated_rows = [row for row in estimated["usage"] if row["scope"] == "current-session" and row["source"] == "pi-local"]
        self.assertEqual(sum(row["requests"] for row in estimated_rows), 2)
        self.assertEqual(estimated["periods"]["current-session"]["selection"]["sources"]["pi-local"]["precision"], "estimated")

    def test_codex_cumulative_duplicates_do_not_inflate(self):
        header = {"type": "session_meta", "payload": {"id": "codex-session", "model": "gpt-test"}}
        first = {"input_tokens": 10, "cached_input_tokens": 3, "output_tokens": 4, "reasoning_output_tokens": 1, "total_tokens": 14}
        second = {"input_tokens": 15, "cached_input_tokens": 5, "output_tokens": 7, "reasoning_output_tokens": 2, "total_tokens": 22}
        self.fixture.line(".codex/sessions/a.jsonl", header, codex_token("2026-07-20T03:00:00Z", first, first), codex_token("2026-07-20T03:01:00Z", second, {"input_tokens": 5, "cached_input_tokens": 2, "output_tokens": 3, "reasoning_output_tokens": 1, "total_tokens": 8}))
        self.fixture.line(".codex/sessions/copied/a.jsonl", header, codex_token("2026-07-20T03:00:00Z", first, first), codex_token("2026-07-20T03:02:00Z", second, second))

        result = td.collect_codex(self.fixture.codex)
        rows = td.aggregate_events(result.events, "week")
        self.assertEqual(sum(row["requests"] for row in rows), 2)
        self.assertEqual(sum(row["input"] for row in rows), 15)
        self.assertEqual(sum(row["output"] for row in rows), 7)
        self.assertEqual(sum(row["total"] for row in rows), 22)
        self.assertTrue(rows[0]["semantics"]["cacheReadSubsetOfInput"])

    def test_missing_token_fields_stay_null(self):
        self.fixture.line(
            ".pi/agent/sessions/a.jsonl",
            {"type": "session", "id": "p"},
            pi_message("m1", "2026-07-20T04:00:00Z", {"input": 2, "output": 3}),
            pi_message("m2", "2026-07-20T04:01:00Z", {"input": 4}),
        )
        row = td.aggregate_events(td.collect_pi(self.fixture.pi).events, "week")[0]
        self.assertEqual(row["input"], 6)
        self.assertIsNone(row["output"])
        self.assertEqual(row["exactness"], "partial")
        self.assertEqual(row["unavailableReasons"]["output"], "not_recorded_by_source")

    def test_missing_and_malformed_roots_degrade_without_failure(self):
        self.fixture.line(".claude/projects/a.jsonl", {"not": "usage"})
        (self.fixture.claude / "bad.jsonl").write_text("not-json\n", encoding="utf-8")
        dashboard = self.dashboard()
        sources = {source["id"]: source for source in dashboard["sources"]}
        self.assertEqual(sources["claude-local"]["status"], "partial")
        self.assertEqual(sources["pi-local"]["status"], "unavailable")
        self.assertEqual(sources["codex-local"]["status"], "unavailable")

    def test_utc_week_is_monday_through_next_monday_and_sunday_is_included(self):
        start, end = td.week_bounds(td.parse_time("2026-07-26T23:59:59Z"))
        self.assertEqual(start.isoformat(), "2026-07-20T00:00:00+00:00")
        self.assertEqual(end.isoformat(), "2026-07-27T00:00:00+00:00")
        self.fixture.line(
            ".pi/agent/sessions/a.jsonl",
            {"type": "session", "id": "p"},
            pi_message("m0", "2026-07-19T23:59:59Z", {"input": 100}),
            pi_message("m1", "2026-07-20T00:00:00Z", {"input": 1}),
            pi_message("m2", "2026-07-26T23:59:59Z", {"input": 2}),
            pi_message("m3", "2026-07-27T00:00:00Z", {"input": 100}),
        )
        self.now = td.parse_time("2026-07-26T23:59:59Z")
        rows = [row for row in self.dashboard()["usage"] if row["scope"] == "week" and row["source"] == "pi-local"]
        self.assertEqual(sum(row["input"] for row in rows), 3)

    def test_sentinel_transcript_and_secret_never_appear_in_json_or_terminal(self):
        sentinel_secret = "sk-management-PRIVATE_SENTINEL_SECRET"
        self.fixture.line(".claude/projects/a.jsonl", claude_row("m", "2026-07-20T05:00:00Z", {"input_tokens": 1}, model="bad\x1bmodel", agentName="PRIVATE_SENTINEL_PROMPT\n"))
        dashboard = self.dashboard(environ={"OPENROUTER_MANAGEMENT_API_KEY": sentinel_secret})
        json_text = json.dumps(dashboard)
        terminal = td.render_terminal(dashboard)
        for forbidden in ("PRIVATE_SENTINEL_PROMPT", "PRIVATE_SENTINEL_RESPONSE", "PRIVATE_SENTINEL_TOOL_OUTPUT", sentinel_secret, "\x1b"):
            self.assertNotIn(forbidden, json_text)
            self.assertNotIn(forbidden, terminal)

    def test_active_pi_excludes_unrelated_harness_sessions(self):
        self.fixture.line(".pi/agent/sessions/work/pi-active.jsonl", {"type": "session", "id": "pi-active"}, pi_message("p", "2026-07-20T01:00:00Z", {"input": 2}))
        self.fixture.line(".claude/projects/work/claude.jsonl", claude_row("c", "2026-07-20T11:00:00Z", {"input_tokens": 100}))
        codex_total = {"input_tokens": 200, "total_tokens": 200}
        self.fixture.line(".codex/sessions/codex.jsonl", {"type": "session_meta", "payload": {"id": "codex"}}, codex_token("2026-07-20T11:30:00Z", codex_total, codex_total))

        dashboard = self.dashboard(environ={"PI_CODING_AGENT": "true", "PI_SESSION_ID": "pi-active"})
        current = [row for row in dashboard["usage"] if row["scope"] == "current-session"]
        self.assertEqual({row["source"] for row in current}, {"pi-local"})
        self.assertEqual(current[0]["input"], 2)

    def test_missing_timestamp_is_excluded_from_week_and_marks_source_partial(self):
        self.fixture.line(
            ".pi/agent/sessions/a.jsonl",
            {"type": "session", "id": "p"},
            pi_message("valid", "2026-07-20T04:00:00Z", {"input": 2}),
            pi_message("invalid", "not-a-time", {"input": 100}),
        )
        dashboard = self.dashboard()
        week = [row for row in dashboard["usage"] if row["scope"] == "week" and row["source"] == "pi-local"]
        source = next(item for item in dashboard["sources"] if item["id"] == "pi-local")
        self.assertEqual(sum(row["input"] for row in week), 2)
        self.assertEqual(source["status"], "partial")
        self.assertIn("1 usage rows without valid timestamps", source["detail"])
        self.assertEqual(dashboard["periods"]["week"]["completeness"], "partial")

    def test_symlinked_and_oversized_telemetry_are_controlled_partial_records(self):
        target = self.fixture.line("outside.jsonl", pi_message("outside", "2026-07-20T04:00:00Z", {"input": 999}))
        self.fixture.pi.mkdir(parents=True, exist_ok=True)
        (self.fixture.pi / "linked.jsonl").symlink_to(target)
        (self.fixture.pi / "oversized.jsonl").write_bytes(b"{" + b"x" * (td.MAX_LOCAL_LINE_BYTES + 1) + b"}\n")

        result = td.collect_pi(self.fixture.pi)
        self.assertEqual(result.events, [])
        self.assertEqual(result.file_errors, 1)
        self.assertEqual(result.malformed, 1)
        self.assertEqual(result.status, "partial")

    def test_file_open_error_marks_source_partial(self):
        self.fixture.line(".pi/agent/sessions/a.jsonl", {"type": "session", "id": "p"}, pi_message("m", "2026-07-20T04:00:00Z", {"input": 2}))
        with mock.patch.object(Path, "open", side_effect=PermissionError("private path detail")):
            result = td.collect_pi(self.fixture.pi)
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.exactness, "partial")
        self.assertEqual(result.file_errors, 1)
        self.assertNotIn("private path", result.detail)

    def test_symlinked_telemetry_root_is_rejected(self):
        outside = self.fixture.root / "outside-root"
        self.fixture.line("outside-root/a.jsonl", {"type": "session", "id": "outside"}, pi_message("m", "2026-07-20T04:00:00Z", {"input": 999}))
        self.fixture.pi.parent.mkdir(parents=True, exist_ok=True)
        self.fixture.pi.symlink_to(outside, target_is_directory=True)

        result = td.collect_pi(self.fixture.pi)
        self.assertEqual(result.events, [])
        self.assertEqual(result.file_errors, 1)
        self.assertEqual(result.status, "partial")

    def test_usage_rows_include_actual_period_boundaries(self):
        self.fixture.line(".pi/agent/sessions/a.jsonl", {"type": "session", "id": "p"}, pi_message("m", "2026-07-20T04:00:00Z", {"input": 2}))
        dashboard = self.dashboard()
        week = next(row for row in dashboard["usage"] if row["scope"] == "week" and row["source"] == "pi-local")
        self.assertEqual(week["period"]["start"], "2026-07-20T00:00:00Z")
        self.assertEqual(week["period"]["end"], "2026-07-20T12:00:00Z")
        self.assertEqual(week["period"]["boundaryEnd"], "2026-07-27T00:00:00Z")
        self.assertEqual(week["period"]["timezone"], "UTC")

    def test_explicit_missing_session_does_not_silently_infer(self):
        self.fixture.line(".pi/agent/sessions/a.jsonl", {"type": "session", "id": "actual"}, pi_message("m", "2026-07-20T04:00:00Z", {"input": 2}))
        dashboard = self.dashboard(explicit_session="missing")
        current_pi = [row for row in dashboard["usage"] if row["scope"] == "current-session" and row["source"] == "pi-local"]
        self.assertEqual(current_pi, [])
        selection = dashboard["periods"]["current-session"]["selection"]["sources"]["pi-local"]
        self.assertEqual(selection["precision"], "unavailable")


class OpenRouterTests(unittest.TestCase):
    def setUp(self):
        self.start = td.parse_time("2026-07-20T00:00:00Z")
        self.end = td.parse_time("2026-07-27T00:00:00Z")

    def collect(self, env=None, offline=False):
        return td.collect_openrouter(self.start, self.end, offline, "https://analytics.test/base", 0.2, env or {})

    def test_management_success_uses_official_envelope_numeric_strings_and_time_range(self):
        meta = {"data": {"metrics": list(td.REMOTE_METRICS), "dimensions": ["model", "provider"]}}
        metrics = {"request_count": "2", "tokens_total": "30", "tokens_prompt": "20", "tokens_completion": "10", "reasoning_tokens": "3", "cached_tokens": "4"}
        query = {"data": {"data": [{"model": "m", "provider": "p", **metrics}], "metadata": {"truncated": False}}}
        with mock.patch.object(td, "request_json", side_effect=[meta, query]) as request:
            source, rows = self.collect({"OPENROUTER_MANAGEMENT_API_KEY": "secret"})
        self.assertEqual(source.status, "ok")
        self.assertEqual(rows[0]["total"], 30)
        self.assertEqual(rows[0]["requests"], 2)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].args[0], "https://analytics.test/base/api/v1/analytics/meta")
        self.assertEqual(request.call_args_list[1].args[0], "https://analytics.test/base/api/v1/analytics/query")
        posted = request.call_args_list[1].args[3]
        self.assertEqual(posted["dimensions"], ["model", "provider"])
        self.assertEqual(posted["time_range"], {"start": "2026-07-20T00:00:00Z", "end": "2026-07-27T00:00:00Z"})
        self.assertEqual(posted["limit"], td.REMOTE_ROW_LIMIT)
        self.assertNotIn("start_date", posted)

    def test_query_uses_only_live_supported_metrics_and_dimensions(self):
        meta = {"data": {"metrics": ["request_count", "tokens_total", "unsupported"], "dimensions": ["model", "unsupported"]}}
        response = {"data": {"data": [{"dimensions": {"model": "m"}, "metrics": {"request_count": 1, "tokens_total": 2}}], "metadata": {"truncated": False}}}
        with mock.patch.object(td, "request_json", side_effect=[meta, response]) as request:
            source, _ = self.collect({"OPENROUTER_MANAGEMENT_API_KEY": "secret"})
        self.assertEqual(source.status, "ok")
        posted = request.call_args_list[1].args[3]
        self.assertEqual(posted["metrics"], ["request_count", "tokens_total"])
        self.assertEqual(posted["dimensions"], ["model"])

    def test_truncation_and_malformed_rows_propagate_partial_exactness(self):
        meta = {"data": {"metrics": ["request_count", "tokens_total"], "dimensions": ["model"]}}
        response = {"data": {"data": [
            {"dimensions": {"model": "m"}, "metrics": {"request_count": "1", "tokens_total": "2"}},
            {"dimensions": {"model": "bad\u200bmodel"}, "metrics": {"request_count": "not-a-number", "tokens_total": "2"}},
            "malformed",
        ], "metadata": {"truncated": True}}}
        with mock.patch.object(td, "request_json", side_effect=[meta, response]):
            source, rows = self.collect({"OPENROUTER_MANAGEMENT_API_KEY": "secret"})
        self.assertEqual(source.status, "partial")
        self.assertEqual(source.exactness, "partial")
        self.assertEqual(source.malformed, 2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["exactness"], "partial")

    def test_malformed_metadata_does_not_send_query(self):
        with mock.patch.object(td, "request_json", return_value={"data": {}}) as request:
            source, rows = self.collect({"OPENROUTER_MANAGEMENT_API_KEY": "secret"})
        self.assertEqual(source.status, "malformed")
        self.assertEqual(rows, [])
        self.assertEqual(request.call_count, 1)

    def test_inference_only_key_is_insufficient_scope_without_request(self):
        with mock.patch.object(td, "request_json") as request:
            source, rows = self.collect({"OPENROUTER_API_KEY": "inference-secret"})
        self.assertEqual(source.status, "insufficient_scope")
        self.assertEqual(rows, [])
        request.assert_not_called()

    def test_no_key_is_not_configured_without_request(self):
        with mock.patch.object(td, "request_json") as request:
            source, _ = self.collect()
        self.assertEqual(source.status, "not_configured")
        request.assert_not_called()

    def test_offline_never_requests_even_with_management_key(self):
        with mock.patch.object(td, "request_json") as request:
            source, _ = self.collect({"OPENROUTER_MANAGEMENT_API_KEY": "secret"}, offline=True)
        self.assertEqual(source.status, "offline")
        request.assert_not_called()

    def test_http_errors_are_sanitized(self):
        expected = {401: "unauthorized", 403: "insufficient_scope", 429: "rate_limited"}
        for code, status in expected.items():
            error = urllib.error.HTTPError("https://analytics.test", code, "PRIVATE_RAW_ERROR", {}, None)
            with self.subTest(code=code), mock.patch.object(td, "request_json", side_effect=error):
                source, rows = self.collect({"OPENROUTER_MANAGEMENT_API_KEY": "PRIVATE_SECRET"})
                self.assertEqual(source.status, status)
                self.assertEqual(rows, [])
                self.assertNotIn("PRIVATE", source.detail)
            error.close()

    def test_malformed_and_network_errors_are_sanitized(self):
        for error, status in ((ValueError("PRIVATE_RAW_BODY"), "malformed"), (urllib.error.URLError("PRIVATE_NETWORK_DETAIL"), "network_error")):
            with self.subTest(status=status), mock.patch.object(td, "request_json", side_effect=error):
                source, _ = self.collect({"OPENROUTER_MANAGEMENT_API_KEY": "secret"})
                self.assertEqual(source.status, status)
                self.assertNotIn("PRIVATE", source.detail)

    def test_request_sets_user_agent_and_bounds_response(self):
        class Response:
            headers = {"Content-Length": str(td.MAX_REMOTE_BYTES + 1)}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        opener = mock.Mock()
        opener.open.return_value = Response()
        with mock.patch.object(td.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(ValueError):
                td.request_json("https://analytics.test", "GET", "secret", None, 0.2)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"), td.USER_AGENT)
        self.assertIsNone(td.NoRedirectHandler().redirect_request(None, None, 302, "redirect", {}, "https://elsewhere.test"))


class CliTests(unittest.TestCase):
    def test_no_argument_fixture_cli_renders_both_sections(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.line(".pi/agent/sessions/a.jsonl", {"type": "session", "id": "p"}, pi_message("m", "2026-07-20T04:00:00Z", {"input": 2}))
            env = {**os.environ, "HOME": temporary}
            for name in ("OPENROUTER_MANAGEMENT_API_KEY", "OPENROUTER_API_KEY", "PI_SUBAGENT_PARENT_SESSION", "PI_SESSION_ID"):
                env.pop(name, None)
            completed = subprocess.run([str(SCRIPT)], env=env, text=True, capture_output=True, check=False, timeout=5)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Current session", completed.stdout)
        self.assertIn("Week", completed.stdout)
        self.assertIn("timezone UTC", completed.stdout)
        self.assertIn("openrouter-analytics | not_configured", completed.stdout)

    def test_json_cli_is_normalized_and_contains_no_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.line(".pi/agent/sessions/private-path/a.jsonl", {"type": "session", "id": "PRIVATE_RAW_ID"}, pi_message("m", "2026-07-20T04:00:00Z", {"input": 2}))
            env = {**os.environ, "HOME": temporary}
            for name in ("OPENROUTER_MANAGEMENT_API_KEY", "OPENROUTER_API_KEY", "PI_SUBAGENT_PARENT_SESSION", "PI_SESSION_ID"):
                env.pop(name, None)
            completed = subprocess.run([str(SCRIPT), "--json", "--offline", "--now", "2026-07-20T12:00:00Z"], env=env, text=True, capture_output=True, check=False, timeout=5)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["schemaVersion"], "1")
        self.assertNotIn("private-path", completed.stdout)
        self.assertNotIn("PRIVATE_RAW_ID", completed.stdout)


if __name__ == "__main__":
    unittest.main()
