"""Synthetic history only: no real prompts, provider requests or persistent reports."""
import contextlib
from dataclasses import replace
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prompt_patterns.py"
SPEC = importlib.util.spec_from_file_location("prompt_patterns", SCRIPT)
PP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PP
NOW = datetime(2026, 1, 31, 12, tzinfo=timezone.utc)
TIME = "2026-01-20T10:00:00Z"
PROMPT = "Please review the repository configuration carefully and explain the smallest safe changes that would simplify our deployment workflow without altering existing behavior."
PARAPHRASE = "Look through our deployment configuration and suggest a minimal simplification while preserving its present behavior, then explain the trade-offs clearly for review."


def setUpModule():
    SPEC.loader.exec_module(PP)


class PromptPatternsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.roots = {"pi": self.root / "pi", "claude": self.root / "claude"}
        self.templates = self.root / "templates"
        self.templates.mkdir()
        for root in self.roots.values():
            root.mkdir()

    def file(self, source, name, rows, *, recent=False):
        path = self.roots[source] / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        stamp = NOW.timestamp() if recent else NOW.timestamp() - 120
        os.utime(path, (stamp, stamp))
        return path

    def pi(self, text=PROMPT, *, session="parent", cwd="/repo/one", time=TIME, extra=None):
        rows = [{"type": "session", "version": 3, "id": session, "cwd": cwd},
                {"type": "message", "id": "user-1", "timestamp": time,
                 "message": {"role": "user", "content": text}}]
        if extra:
            rows[-1].update(extra)
        return rows

    def claude(self, text=PROMPT, *, session="parent", cwd="/repo/two", time=TIME, extra=None):
        row = {"type": "user", "uuid": "user-" + session, "sessionId": session, "cwd": cwd, "timestamp": time,
               "message": {"role": "user", "content": text}}
        row.update(extra or {})
        return [row]

    def collect(self, **kwargs):
        return PP.collect(self.roots, [self.templates], as_of=NOW, **kwargs)

    def cli(self, *args, input=None):
        return subprocess.run([sys.executable, "-B", str(SCRIPT),
                               "--pi-root", str(self.roots["pi"]), "--claude-root", str(self.roots["claude"]),
                               "--template-root", str(self.templates), "--as-of", NOW.isoformat(), *args],
                              text=True, capture_output=True, input=input)

    def test_supported_human_candidates_deduplicate_and_keep_aggregation_evidence(self):
        rows = self.pi()
        rows.append({**rows[-1], "id": "user-2", "timestamp": "2026-01-21T10:00:00Z"})
        rows.append(rows[-1])  # replay of the same event, not another user prompt
        self.file("pi", "project/one.jsonl", rows)
        self.file("claude", "project/two.jsonl", self.claude())
        self.file("claude", "project/three.jsonl", self.claude(PARAPHRASE, session="third"))
        result = self.collect()
        self.assertEqual(result["summary"]["candidateCount"], 2)
        self.assertEqual(result["summary"]["occurrenceCount"], 4)
        candidate = next(c for c in result["packet"]["candidates"] if c["text"] == PROMPT)
        self.assertEqual(candidate["occurrences"], 3)
        self.assertEqual(len(candidate["sessions"]), 2)
        self.assertEqual(len(candidate["repositories"]), 2)
        self.assertEqual(candidate["firstSeen"], "2026-01-20T10:00:00Z")
        self.assertEqual(candidate["lastSeen"], "2026-01-21T10:00:00Z")
        serialized = json.dumps(result)
        self.assertNotIn("/repo/", serialized)
        self.assertNotIn('"parent"', serialized)
        self.assertIn("heuristic", result["summary"]["provenance"])

    def test_short_slash_injected_expanded_watch_and_nonhuman_messages_are_excluded(self):
        ignored = ["yes", "please continue", "/discuss " + PROMPT,
                   "<skill name=\"review\" location=\"/ignored\">" + PROMPT + "</skill>",
                   "<system-reminder>" + PROMPT + "</system-reminder>",
                   "<command-name>/review</command-name>" + PROMPT,
                   PROMPT + " This is watch-loop protocol 1 tick watch-id/2. Render the full visible dashboard.",
                   "[Request interrupted by user] " + PROMPT]
        for n, text in enumerate(ignored):
            self.file("pi", f"project/ignored-{n}.jsonl", self.pi(text, session=f"ignored-{n}"))
        rows = self.pi()
        rows[-1]["message"]["role"] = "toolResult"
        self.file("pi", "project/tool.jsonl", rows)
        self.file("pi", "project/custom.jsonl", [{"type": "custom_message", "content": PROMPT}])
        for n, flags in enumerate(({"isMeta": True}, {"isCompactSummary": True}, {"isSidechain": True},
                                    {"agentId": "worker"}, {"toolUseResult": {"content": PROMPT}},
                                    {"isMeta": "false"}, {"source": "automation"})):
            self.file("claude", f"project/flags-{n}.jsonl", self.claude(extra=flags))
        self.file("claude", "project/tool-array.jsonl", self.claude([
            {"type": "text", "text": PROMPT}, {"type": "tool_result", "content": PROMPT}]))
        self.assertEqual(self.collect()["summary"]["candidateCount"], 0)

    def test_nested_fork_and_late_child_metadata_veto_entire_files(self):
        self.file("pi", "project/parent/run-id/session.jsonl", self.pi())
        rows = self.pi()
        rows[0]["parentSession"] = "original.jsonl"
        self.file("pi", "project/fork.jsonl", rows)
        self.file("claude", "project/parent/subagents/agent-a.jsonl", self.claude())
        rows = self.claude()
        rows.append({"type": "assistant", "isSidechain": True, "message": {"role": "assistant"}})
        self.file("claude", "project/late-child.jsonl", rows)
        self.assertEqual(self.collect()["summary"]["candidateCount"], 0)

    def test_unknown_origin_flags_duplicate_keys_and_malformed_files_fail_closed(self):
        self.file("claude", "project/unknown-flag.jsonl", self.claude(extra={"isFutureInjectedMessage": True}))
        path = self.file("pi", "project/duplicate-key.jsonl", self.pi())
        with path.open("a") as handle:
            handle.write('{"type":"user","isMeta":true,"isMeta":false}\n')
        os.utime(path, (NOW.timestamp() - 120,) * 2)
        self.assertEqual(self.collect()["summary"]["candidateCount"], 0)

    def test_template_changes_and_scan_limits_invalidate_or_report_coverage(self):
        self.file("pi", "project/parent.jsonl", self.pi())
        summary = json.loads(self.cli().stdout)
        (self.templates / "new.md").write_text("Review the requested changes and report concrete problems only: $ARGUMENTS")
        stale = self.cli("--emit", "--expected-digest", summary["digest"])
        self.assertEqual(stale.returncode, 2)
        self.assertNotIn(PROMPT, stale.stdout + stale.stderr)
        self.file("pi", "project/second.jsonl", self.pi(PARAPHRASE, session="other"))
        for limits in (replace(PP.Limits(), max_files=1), replace(PP.Limits(), max_total_bytes=16),
                       replace(PP.Limits(), max_file_records=1), replace(PP.Limits(), max_scan_seconds=0)):
            with self.subTest(limits=limits):
                self.assertTrue(self.collect(limits=limits)["summary"]["truncation"]["scanLimited"])

    def test_generated_shell_ide_hook_and_future_wrappers_are_not_human_prompts(self):
        for index, tag in enumerate(("bash-input", "bash-stdout", "bash-stderr", "user-memory-input",
                                     "ide_opened_file", "ide_selection", "task-notification", "user-prompt-submit-hook", "future_context")):
            self.file("claude", f"project/wrapper-{index}.jsonl", self.claude(
                f"<{tag}>" + PROMPT + f"</{tag}>", session=f"wrapped-{index}"))
        self.file("claude", "project/mixed-ide.jsonl", self.claude([
            {"type": "text", "text": PROMPT}, {"type": "text", "text": "<ide_selection>private-code-sentinel</ide_selection>"}], session="mixed"))
        result = self.collect()
        self.assertEqual(result["summary"]["candidateCount"], 0)
        self.assertNotIn("private-code-sentinel", json.dumps(result))

    def test_escaped_keys_private_keys_short_flags_and_netrc_are_redacted(self):
        fragments = [r'{\"password\":\"escaped-short-sentinel\"}',
                     'private_key="private-short-sentinel"', 'custom_key="key-short-sentinel"',
                     'pwd: "pwd-short-sentinel"', 'Cookie: cookie-short-sentinel',
                     'curl -u demo:userpass-sentinel', 'mysql -pshort-flag-sentinel',
                     'password netrc-short-sentinel', 'machine example.invalid login demo password inline-netrc-sentinel']
        self.file("pi", "project/more-credentials.jsonl", self.pi(PROMPT + "\n" + "\n".join(fragments)))
        result = self.collect()
        self.assertEqual(result["summary"]["candidateCount"], 1)
        for secret in ("escaped-short-sentinel", "private-short-sentinel", "key-short-sentinel", "pwd-short-sentinel",
                       "cookie-short-sentinel", "userpass-sentinel", "short-flag-sentinel", "netrc-short-sentinel", "inline-netrc-sentinel"):
            self.assertNotIn(secret, json.dumps(result))

    def test_each_source_keeps_a_scan_share_and_child_directories_do_not_fill_it(self):
        filler = [{"type": "assistant", "message": {"role": "assistant", "content": "x" * 1000}}]
        first = self.file("claude", "project/a.jsonl", filler)
        self.file("claude", "project/b.jsonl", filler)
        self.file("pi", "project/parent.jsonl", self.pi())
        limits = replace(PP.Limits(), max_total_bytes=first.stat().st_size * 2 + 10)
        result = self.collect(limits=limits)
        self.assertEqual(result["summary"]["candidateCount"], 1)
        for index in range(5):
            self.file("pi", f"project/parent/subagents/{index}.jsonl", self.pi())
        result = self.collect(limits=replace(PP.Limits(), max_files=2))
        self.assertFalse(result["summary"]["sources"]["pi"]["limitedFiles"])
        self.assertGreater(result["summary"]["sources"]["pi"]["childDirectoriesExcluded"], 0)

    def test_newest_file_priority_does_not_use_mtime_as_window_authority(self):
        old = self.file("pi", "project/old.jsonl", self.pi())
        newest = self.file("pi", "project/new.jsonl", self.pi(PARAPHRASE, session="new"))
        os.utime(old, (NOW.timestamp() - 3600,) * 2)
        result = self.collect(limits=replace(PP.Limits(), max_files=1))
        self.assertEqual(result["packet"]["candidates"][0]["text"], PARAPHRASE)
        os.utime(newest, (NOW.timestamp() - 60 * 86400,) * 2)
        result = self.collect()
        self.assertEqual(result["summary"]["candidateCount"], 2)

    def test_claude_global_uuid_copies_do_not_inflate_distinct_sessions(self):
        original = self.claude(session="original")
        copied = json.loads(json.dumps(original))
        copied[0]["sessionId"] = "copy-with-new-session-id"
        self.file("claude", "project/original.jsonl", original)
        self.file("claude", "project/copy.jsonl", copied)
        result = self.collect()
        self.assertEqual(result["summary"]["occurrenceCount"], 1)
        self.assertEqual(len(result["packet"]["candidates"][0]["sessions"]), 1)

    def test_long_dotted_text_does_not_trigger_quadratic_redaction(self):
        code = "import importlib.util,sys; s=importlib.util.spec_from_file_location('p',sys.argv[1]); m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); m.redact('a.' * 16000)"
        try:
            result = subprocess.run([sys.executable, "-B", "-c", code, str(SCRIPT)], capture_output=True, timeout=3)
        except subprocess.TimeoutExpired:
            self.fail("redaction exceeded the synthetic long-token deadline")
        self.assertEqual(result.returncode, 0)

    def test_window_timestamp_and_active_file_filters(self):
        for n, stamp in enumerate(("2025-12-01T00:00:00Z", NOW.isoformat(), "2026-01-20", "invalid", True)):
            self.file("pi", f"project/date-{n}.jsonl", self.pi(time=stamp))
        self.file("pi", "project/active.jsonl", self.pi(), recent=True)
        self.assertEqual(self.collect()["summary"]["candidateCount"], 0)
        self.file("pi", "project/lower-bound.jsonl", self.pi(time="2026-01-01T12:00:00Z"))
        self.assertEqual(self.collect()["summary"]["candidateCount"], 1)

    def test_known_parameterized_template_expansions_are_excluded_as_data(self):
        body = "Inspect the following requested repository changes carefully and return only concrete actionable review findings: $ARGUMENTS"
        (self.templates / "review.md").write_text("---\ndescription: Review changes\n---\n" + body)
        self.file("pi", "project/template.jsonl", self.pi(body.replace("$ARGUMENTS", "module one")))
        self.file("claude", "project/typed.jsonl", self.claude(PROMPT))
        result = self.collect()
        self.assertEqual(result["summary"]["candidateCount"], 1)
        self.assertEqual(result["summary"]["templateCoverage"]["templatesLoaded"], 1)
        self.assertIn("old", result["summary"]["templateCoverage"]["limitation"])

    def test_credential_shapes_are_redacted_before_any_text_emission(self):
        secrets = ["demo-password-value", "demo-token-value", "sk-" + "a" * 40,
                   "ghp_" + "b" * 36, "AKIA" + "C" * 16, "eyJ" + "d" * 30 + "." + "e" * 30 + "." + "f" * 30,
                   "g" * 48, "demo-cli-password", "private-key-body-sentinel", "demo-url-password"]
        text = PROMPT + '\npassword=demo-password-value\n{"access_token":"demo-token-value"}\n' + secrets[2] + "\n" + secrets[3]
        text += "\n" + secrets[4] + "\nBearer " + secrets[5] + "\nopaque " + secrets[6]
        text += "\n--password demo-cli-password\nhttps://user:demo-url-password@example.invalid/path"
        text += "\n-----BEGIN PRIVATE KEY-----\nprivate-key-body-sentinel\n-----END PRIVATE KEY-----\n"
        self.file("pi", "project/secrets.jsonl", self.pi(text))
        result = self.collect()
        self.assertEqual(result["summary"]["candidateCount"], 1)
        for secret in secrets:
            self.assertNotIn(secret, json.dumps(result))
        summary_run = self.cli()
        self.assertEqual(summary_run.returncode, 0)
        self.assertNotIn("Please review", summary_run.stdout)
        summary = json.loads(summary_run.stdout)
        emitted = self.cli("--emit", "--expected-digest", summary["digest"])
        self.assertEqual(emitted.returncode, 0)
        for secret in secrets:
            self.assertNotIn(secret, emitted.stdout + emitted.stderr + summary_run.stdout + summary_run.stderr)
        self.assertIn("REDACTED", emitted.stdout)

    def test_escaped_quoted_credentials_and_obfuscated_tokens_do_not_leave_suffixes(self):
        secret = 'first\\"second-credential-sentinel'
        token = "sk-" + "q" * 40
        text = PROMPT + '\npassword="' + secret + '"\n--token "' + secret + '"\n'
        text += "unquoted_password=comma,semicolon;credential-sentinel\n" + token[:5] + "\u200b" + token[5:]
        self.file("pi", "project/quoted.jsonl", self.pi(text))
        serialized = json.dumps(self.collect())
        self.assertNotIn("second-credential-sentinel", serialized)
        self.assertNotIn("comma,semicolon;credential-sentinel", serialized)
        self.assertNotIn("q" * 40, serialized)

    def test_cluster_cli_is_digest_bound_statistics_only(self):
        self.file("pi", "project/parent.jsonl", self.pi())
        summary = json.loads(self.cli().stdout)
        packet = json.loads(self.cli("--emit", "--expected-digest", summary["digest"]).stdout)
        mapping = [[packet["candidates"][0]["id"]]]
        result = self.cli("--clusters", "--expected-digest", summary["digest"], input=json.dumps(mapping))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["clusters"][0]["occurrences"], 1)
        self.assertNotIn(PROMPT, result.stdout + result.stderr)
        for raw in ('[["raw-private-sentinel"]]', "x" * 8193):
            result = self.cli("--clusters", "--expected-digest", summary["digest"], input=raw)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("raw-private-sentinel", result.stdout + result.stderr)

    def test_metadata_first_digest_binds_content_templates_options_and_snapshot(self):
        path = self.file("pi", "project/parent.jsonl", self.pi())
        summary = json.loads(self.cli().stdout)
        self.assertEqual(summary["candidateCount"], 1)
        self.assertNotIn(PROMPT, json.dumps(summary))
        output = self.cli("--emit", "--expected-digest", summary["digest"])
        self.assertEqual(len(output.stdout.encode()), summary["payloadBytes"])
        self.assertEqual(json.loads(output.stdout)["candidates"][0]["text"], PROMPT)
        for args in (("--days", "29"), ("--max-candidates", "1")):
            stale = self.cli("--emit", "--expected-digest", summary["digest"], *args)
            self.assertEqual(stale.returncode, 2)
            self.assertNotIn(PROMPT, stale.stdout + stale.stderr)
        path.write_text(path.read_text().replace(PROMPT, PARAPHRASE))
        os.utime(path, (NOW.timestamp() - 120,) * 2)
        stale = self.cli("--emit", "--expected-digest", summary["digest"])
        self.assertEqual(stale.returncode, 2)
        self.assertNotIn(PARAPHRASE, stale.stdout + stale.stderr)

    def test_partial_coverage_diagnostics_and_bounds_never_echo_bad_input(self):
        path = self.file("pi", "project/partial.jsonl", self.pi())
        with path.open("a") as handle:
            handle.write('not-json raw-private-sentinel\n')
        os.utime(path, (NOW.timestamp() - 120,) * 2)
        self.file("claude", "project/large.jsonl", self.claude("x" * 10000))
        result = self.collect(limits=replace(PP.Limits(), max_line_bytes=2048))
        self.assertEqual(result["summary"]["sources"]["pi"]["status"], "partial")
        self.assertGreater(result["summary"]["sources"]["pi"]["malformedRecords"], 0)
        self.assertNotIn("raw-private-sentinel", json.dumps(result))
        result = self.collect(limits=replace(PP.Limits(), max_file_bytes=16))
        self.assertEqual(result["summary"]["candidateCount"], 0)
        self.assertTrue(result["summary"]["truncation"]["scanLimited"])

    def test_candidate_count_and_serialized_byte_limits_are_explicit(self):
        for n in range(8):
            self.file("pi", f"project/{n}.jsonl", self.pi(PROMPT + f" Case number {n}.", session=f"session-{n}"))
        result = self.collect(max_candidates=2)
        self.assertEqual(len(result["packet"]["candidates"]), 2)
        self.assertEqual(result["summary"]["truncation"]["candidateLimitOmitted"], 6)
        result = self.collect(max_bytes=1024)
        self.assertLessEqual(len(PP.encoded(result["packet"])) + 1, 1024)
        self.assertGreater(result["summary"]["truncation"]["byteBudgetOmitted"], 0)
        result = self.collect(max_prompt_chars=100)
        self.assertEqual(result["summary"]["candidateCount"], 0)
        self.assertGreater(result["summary"]["truncation"]["oversizedPrompts"], 0)

    def test_symlink_files_and_root_and_nonregular_files_are_not_read(self):
        outside = self.root / "outside.jsonl"
        outside.write_text('raw-private-sentinel')
        (self.roots["pi"] / "link.jsonl").symlink_to(outside)
        self.roots["claude"].rmdir()
        self.roots["claude"].symlink_to(self.roots["pi"], target_is_directory=True)
        result = self.collect()
        self.assertEqual(result["summary"]["candidateCount"], 0)
        self.assertNotIn("raw-private-sentinel", json.dumps(result))
        self.assertNotEqual(result["summary"]["sources"]["pi"]["status"], "ok")
        self.assertEqual(result["summary"]["sources"]["claude"]["status"], "unavailable")

    def test_model_grouping_metrics_use_unions_not_added_session_counts(self):
        first = self.pi()
        first.append({**first[-1], "id": "user-2", "message": {"role": "user", "content": PARAPHRASE}})
        self.file("pi", "project/one.jsonl", first)
        self.file("claude", "project/two.jsonl", self.claude())
        packet = self.collect()["packet"]
        ids = [c["id"] for c in packet["candidates"]]
        result = PP.cluster_metrics(packet, [ids])
        self.assertEqual(result["clusters"][0]["occurrences"], 3)
        self.assertEqual(result["clusters"][0]["sessionCount"], 2)
        self.assertEqual(result["clusters"][0]["repositoryCount"], 2)
        self.assertEqual(result["ungroupedCandidateCount"], 0)
        self.assertNotIn(PROMPT, json.dumps(result))
        for groups in ([["unknown-id"]], [[ids[0]], [ids[0]]], "invalid", [[]]):
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                PP.cluster_metrics(packet, groups)

    def test_template_alias_cannot_read_a_non_markdown_target(self):
        target = self.root / "private-config.json"
        target.write_text('{"password":"private-config-sentinel-with-a-long-enough-body"}')
        (self.templates / "alias.md").symlink_to(target)
        with patch.object(PP.os, "open", wraps=os.open) as opened:
            _patterns, coverage, _manifest = PP.templates([self.templates], PP.Limits())
        self.assertEqual(coverage["templatesLoaded"], 0)
        self.assertEqual(coverage["rejectedTemplates"], 1)
        opened.assert_not_called()

    def test_snapshot_salted_directory_ids_are_stable_only_for_the_same_snapshot(self):
        path = self.file("pi", "project/parent.jsonl", self.pi())
        first = self.collect()["packet"]["candidates"][0]
        self.assertEqual(first["repositories"], self.collect()["packet"]["candidates"][0]["repositories"])
        self.assertNotIn(PP.opaque("r", "/repo/one"), first["repositories"])
        with path.open("a") as handle:
            handle.write(json.dumps({"type": "message", "message": {"role": "assistant", "content": "Synthetic private snapshot context"}}) + "\n")
        os.utime(path, (NOW.timestamp() - 120,) * 2)
        changed = self.collect()["packet"]["candidates"][0]
        self.assertEqual(first["text"], changed["text"])
        self.assertNotEqual(first["repositories"], changed["repositories"])

    def test_fifo_and_directory_symlinks_are_rejected_without_following_them(self):
        project = self.roots["pi"] / "project"
        project.mkdir()
        os.mkfifo(project / "pipe.jsonl")
        outside = self.root / "outside-directory"
        outside.mkdir()
        (outside / "source.jsonl").write_text("private-file-sentinel")
        (self.roots["pi"] / "linked-project").symlink_to(outside, target_is_directory=True)
        result = self.collect()
        self.assertEqual(result["summary"]["candidateCount"], 0)
        self.assertGreater(result["summary"]["sources"]["pi"]["rejectedFiles"], 0)
        self.assertNotIn("private-file-sentinel", json.dumps(result))

    def test_no_history_files_or_reports_are_written_and_failures_are_generic(self):
        self.file("pi", "project/parent.jsonl", self.pi())
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.collect()
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        out, err = io.StringIO(), io.StringIO()
        with patch.object(PP, "collect", side_effect=ValueError("raw-private-sentinel")), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = PP.main([])
        self.assertEqual(code, 2)
        self.assertNotIn("raw-private-sentinel", out.getvalue() + err.getvalue())
        self.assertNotIn("Traceback", out.getvalue() + err.getvalue())


if __name__ == "__main__":
    unittest.main()
