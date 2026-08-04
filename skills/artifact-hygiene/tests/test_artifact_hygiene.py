from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "artifact_hygiene.py"


class RepositoryFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.run("init", "-b", "main")
        self.run("config", "user.email", "test@example.com")
        self.run("config", "user.name", "Test User")

    def run(self, *arguments: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout

    def write(self, path: str, content: str) -> Path:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def commit_all(self, message: str) -> None:
        self.run("add", "--all")
        self.run("commit", "-m", message)

    def mark_base(self) -> None:
        self.run("update-ref", "refs/remotes/origin/main", "HEAD")
        self.run("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")

    def state(self) -> tuple[str, str, str]:
        return (
            self.run("status", "--porcelain=v1", "--untracked-files=all"),
            self.run("rev-parse", "HEAD"),
            self.run("for-each-ref", "--format=%(refname) %(objectname)"),
        )


def load_helper_module():
    spec = importlib.util.spec_from_file_location("artifact_hygiene_test_target", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load artifact-hygiene helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def add_command_links(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required for tests")
    (directory / "git").symlink_to(git)
    (directory / "python3").symlink_to(sys.executable)


def make_fake_gitleaks(directory: Path) -> tuple[Path, Path]:
    add_command_links(directory)
    executable = directory / "gitleaks"
    log = directory / "invocations.jsonl"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
import time

root = os.path.dirname(os.path.abspath(__file__))
log_path = os.path.join(root, "invocations.jsonl")
mode_path = os.path.join(root, "fake-mode")
with open(log_path, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({
        "argv": sys.argv[1:],
        "configEnv": {key: value for key, value in os.environ.items() if key.startswith("GITLEAKS_")},
        "gitExternalDiff": os.environ.get("GIT_EXTERNAL_DIFF"),
        "gitNoLazyFetch": os.environ.get("GIT_NO_LAZY_FETCH"),
        "gitNoReplaceObjects": os.environ.get("GIT_NO_REPLACE_OBJECTS"),
        "rawEnv": os.environ.get("RAW_ENV_SENTINEL"),
        "tempDir": os.environ.get("TMPDIR"),
    }) + "\\n")

command = sys.argv[1] if len(sys.argv) > 1 else ""
if command == "version":
    print("8.30.1")
    raise SystemExit(0)
mode = open(mode_path, encoding="utf-8").read().strip() if os.path.exists(mode_path) else ""
if command == "stdin" and mode == "sleep-scan":
    with open(os.path.join(root, "child-pid"), "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    time.sleep(60)
if command == "git" and mode == "fail-history":
    print("RAW_CHILD_ERROR", file=sys.stderr)
    raise SystemExit(2)

payload = sys.stdin.buffer.read() if command == "stdin" else b"HISTORY_FINDING_MARKER"
if b"FINDING_MARKER" not in payload and b"AKIA" not in payload:
    print("[]")
    raise SystemExit(0)
raw = payload.decode("utf-8", "replace")
print(json.dumps([{
    "RuleID": "fake-secret",
    "StartLine": 1,
    "EndLine": 1,
    "File": "history.txt" if command == "git" else "-",
    "Commit": "a" * 40 if command == "git" else "",
    "Secret": raw,
    "Match": raw,
    "Message": raw,
    "Author": raw,
    "Email": "raw@example.invalid",
    "Fingerprint": raw,
    "UnknownField": raw,
}]))
print("RAW_CHILD_ERROR " + raw, file=sys.stderr)
raise SystemExit(1)
""",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable, log


def make_noop_gitleaks(directory: Path) -> Path:
    add_command_links(directory)
    executable = directory / "gitleaks"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "print('8.30.1' if sys.argv[1:2] == ['version'] else '[]')\n",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable


class ArtifactHygieneCliTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.repository = RepositoryFixture(root / "repository")
        self.fake_gitleaks, self.invocation_log = make_fake_gitleaks(root / "fake-bin")
        self.missing_bin = root / "missing-bin"
        add_command_links(self.missing_bin)
        self.noop_gitleaks = make_noop_gitleaks(root / "noop-bin")

    def run_audit(
        self,
        *,
        extra_environment: dict[str, str] | None = None,
        scanner: Path | None = None,
        fake_mode: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PATH"] = str((scanner or self.fake_gitleaks).parent)
        if extra_environment:
            environment.update(extra_environment)
        mode_path = self.fake_gitleaks.with_name("fake-mode")
        if fake_mode:
            mode_path.write_text(fake_mode, encoding="utf-8")
        else:
            mode_path.unlink(missing_ok=True)
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.repository.root),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=20,
        )

    def real_scanner(self, name: str) -> Path:
        executable = shutil.which("gitleaks")
        if executable is None:
            raise RuntimeError("gitleaks is required")
        directory = Path(self.temporary.name) / name
        add_command_links(directory)
        (directory / "gitleaks").symlink_to(executable)
        return directory / "gitleaks"

    def prepare_coverage_repository(self) -> list[str]:
        sentinels = [
            "INHERITED_FINDING_MARKER",
            "STAGED_FINDING_MARKER",
            "INDEX_ONLY_FINDING_MARKER",
            "UNSTAGED_FINDING_MARKER",
            "UNTRACKED_FINDING_MARKER",
            "IGNORED_FINDING_MARKER",
            "RAW_SESSION_SENTINEL",
            "BINARY_FINDING_MARKER",
            "SYMLINK_FINDING_MARKER",
            "ARTIFACT_TRACKED_FINDING_MARKER",
            "ARTIFACT_UNTRACKED_FINDING_MARKER",
            "ARTIFACT_IGNORED_FINDING_MARKER",
            "BACKSLASH_WORKTREE_FINDING_MARKER",
            "BACKSLASH_INDEX_FINDING_MARKER",
            "BACKSLASH_HISTORY_SESSION_SENTINEL",
        ]
        self.repository.write(".gitignore", "ignored.txt\n.artifacts/ignored.txt\n")
        self.repository.write("inherited.txt", sentinels[0] + " # gitleaks:allow\n")
        self.repository.write("tracked.txt", "clean\n")
        self.repository.write("index-only.txt", "clean\n")
        self.repository.write(".artifacts/tracked.txt", sentinels[9] + "\n")
        self.repository.write(r"index\path.txt", "clean\n")
        (self.repository.root / "binary.bin").write_bytes(b"\0" + sentinels[7].encode())
        outside = self.repository.root.parent / "outside-secret.txt"
        outside.write_text(sentinels[8] + "\n", encoding="utf-8")
        (self.repository.root / "symlink.txt").symlink_to(outside)
        self.repository.write(".gitleaks.toml", "[allowlist]\npaths = ['.*']\n")
        self.repository.write(".gitleaksignore", "fake-secret:ignored\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.run("switch", "-c", "feature")
        self.repository.write("history.txt", "HISTORY_FINDING_MARKER\n")
        self.repository.write(
            r"history\path.txt",
            "https://chatgpt.com/share/" + sentinels[14] + "\n",
        )
        self.repository.commit_all("history")
        (self.repository.root / r"history\path.txt").unlink()
        self.repository.commit_all("remove backslash history path")
        self.repository.write("staged.txt", sentinels[1] + "\n")
        self.repository.run("add", "staged.txt")
        self.repository.write("index-only.txt", sentinels[2] + "\n")
        self.repository.run("add", "index-only.txt")
        self.repository.write("index-only.txt", "clean after staging\n")
        self.repository.write("tracked.txt", sentinels[3] + "\n")
        self.repository.write("untracked.txt", sentinels[4] + "\n")
        self.repository.write("ignored.txt", sentinels[5] + "\n")
        self.repository.write(".artifacts/untracked.txt", sentinels[10] + "\n")
        self.repository.write(".artifacts/ignored.txt", sentinels[11] + "\n")
        self.repository.write(r"worktree\path.txt", sentinels[12] + "\n")
        self.repository.write(r"index\path.txt", sentinels[13] + "\n")
        self.repository.run("add", r"index\path.txt")
        self.repository.write(r"index\path.txt", "clean after staging\n")
        self.repository.write(
            "session.txt",
            "https://chatgpt.com/share/" + sentinels[6] + "\n",
        )
        return sentinels

    def test_full_publishable_tree_history_suppression_and_redaction_contract(self) -> None:
        sentinels = self.prepare_coverage_repository()
        before = self.repository.state()

        completed = self.run_audit(
            extra_environment={
                "GITLEAKS_CONFIG": str(self.repository.root / ".gitleaks.toml"),
                "GITLEAKS_CONFIG_TOML": "[allowlist]\npaths = ['.*']",
                "GIT_EXTERNAL_DIFF": "must-not-run",
                "RAW_ENV_SENTINEL": "must-not-reach-child",
                "TMPDIR": str(self.repository.root),
                "ARTIFACT_HYGIENE_TESTING": "1",
                "ARTIFACT_HYGIENE_TEST_GITLEAKS": str(self.noop_gitleaks),
            }
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["schemaVersion"], "artifact-hygiene/v1")
        self.assertEqual(payload["status"], "complete")
        self.assertEqual(payload["verdict"], "findings")
        coverage = {entry["source"]: entry for entry in payload["coverage"]}
        self.assertEqual(coverage["working-tree"]["status"], "complete")
        self.assertEqual(coverage["branch-history"]["status"], "complete")

        paths = {
            finding["location"]["path"]
            for finding in payload["findings"]
            if finding["category"] == "secret"
        }
        self.assertTrue(
            {
                "inherited.txt",
                "staged.txt",
                "index-only.txt",
                "tracked.txt",
                "untracked.txt",
                ".artifacts/tracked.txt",
                ".artifacts/untracked.txt",
                r"worktree\path.txt",
                r"index\path.txt",
            }.issubset(paths)
        )
        self.assertNotIn("ignored.txt", paths)
        self.assertNotIn(".artifacts/ignored.txt", paths)
        self.assertNotIn("binary.bin", paths)
        self.assertNotIn("symlink.txt", paths)
        self.assertIn("session-link", {item["category"] for item in payload["findings"]})
        self.assertTrue(
            any(
                item["category"] == "session-link"
                and item["location"]["source"] == "branch-history"
                and item["location"]["path"] == r"history\path.txt"
                for item in payload["findings"]
            )
        )
        self.assertIn("suppression-attempt", {item["category"] for item in payload["findings"]})

        serialized = json.dumps(payload, sort_keys=True)
        for sentinel in [*sentinels, "RAW_CHILD_ERROR", "raw@example.invalid"]:
            self.assertNotIn(sentinel, serialized)
        self.assertEqual(self.repository.state(), before)

        invocations = [json.loads(line) for line in self.invocation_log.read_text().splitlines()]
        serialized_invocations = json.dumps(invocations, sort_keys=True)
        for sentinel in sentinels:
            self.assertNotIn(sentinel, serialized_invocations)
        scan_invocations = [item for item in invocations if item["argv"][0] in {"stdin", "git"}]
        self.assertTrue(scan_invocations)
        for invocation in scan_invocations:
            arguments = invocation["argv"]
            self.assertIn("--config", arguments)
            config_path = Path(arguments[arguments.index("--config") + 1])
            self.assertEqual(config_path, SKILL_ROOT / "references" / "gitleaks.toml")
            self.assertIn("--gitleaks-ignore-path", arguments)
            ignore_path = Path(arguments[arguments.index("--gitleaks-ignore-path") + 1])
            self.assertNotEqual(ignore_path, self.repository.root / ".gitleaksignore")
            self.assertFalse(ignore_path.is_relative_to(self.repository.root))
            self.assertFalse(ignore_path.exists())
            self.assertIn("--ignore-gitleaks-allow", arguments)
            self.assertNotIn("--baseline-path", arguments)
            self.assertEqual(invocation["configEnv"], {})
            self.assertIsNone(invocation["gitExternalDiff"])
            self.assertEqual(invocation["gitNoLazyFetch"], "1")
            self.assertEqual(invocation["gitNoReplaceObjects"], "1")
            self.assertIsNone(invocation["rawEnv"])
            scanner_temp = Path(invocation["tempDir"])
            self.assertFalse(scanner_temp.is_relative_to(self.repository.root))
            self.assertFalse(scanner_temp.exists())
        history_arguments = next(item["argv"] for item in scan_invocations if item["argv"][0] == "git")
        log_options = history_arguments[history_arguments.index("--log-opts") + 1]
        self.assertIn("--no-ext-diff", log_options)
        self.assertIn("--no-textconv", log_options)

    def test_runner_reaps_child_across_setup_failures(self) -> None:
        helper = load_helper_module()
        real_popen = subprocess.Popen
        for failure in ("pipe", "selector"):
            with self.subTest(failure=failure):
                spawned: list[subprocess.Popen[bytes]] = []

                def capture_process(*args, **kwargs):
                    process = real_popen(*args, **kwargs)
                    spawned.append(process)
                    return process

                setup_patch = (
                    mock.patch.object(
                        helper.os,
                        "set_blocking",
                        side_effect=OSError("RAW_SETUP_ERROR"),
                    )
                    if failure == "pipe"
                    else mock.patch.object(
                        helper.selectors,
                        "DefaultSelector",
                        side_effect=RuntimeError("RAW_SETUP_ERROR"),
                    )
                )
                caught: BaseException | None = None
                try:
                    with (
                        mock.patch.object(
                            helper.subprocess,
                            "Popen",
                            side_effect=capture_process,
                        ),
                        setup_patch,
                    ):
                        try:
                            helper.BoundedRunner(helper.monotonic() + 5).run(
                                [
                                    sys.executable,
                                    "-c",
                                    "import time; time.sleep(60)",
                                ],
                                cwd=self.repository.root,
                            )
                        except BaseException as error:
                            caught = error

                    self.assertIsInstance(caught, helper.AuditError)
                    self.assertEqual(caught.code, "command-setup-failed")
                    self.assertNotIn("RAW_SETUP_ERROR", str(caught))
                    self.assertEqual(len(spawned), 1)
                    self.assertIsNotNone(
                        spawned[0].poll(),
                        "child process survived setup failure",
                    )
                finally:
                    for process in spawned:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()

    def test_runner_reaps_child_on_runtime_timeout_and_output_failures(self) -> None:
        helper = load_helper_module()
        real_selector = selectors.DefaultSelector
        real_popen = subprocess.Popen

        class SelectFailingSelector:
            def __init__(self) -> None:
                self.inner = real_selector()

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def select(self, _timeout=None):
                raise RuntimeError("RAW_RUNTIME_ERROR")

        cases = (
            (
                "runtime",
                [sys.executable, "-c", "import time; time.sleep(60)"],
                5.0,
                "command-failed",
            ),
            (
                "timeout",
                [sys.executable, "-c", "import time; time.sleep(60)"],
                0.05,
                "command-timeout",
            ),
            (
                "output",
                [
                    sys.executable,
                    "-c",
                    "import os; os.write(1, b'x' * 4100000)",
                ],
                5.0,
                "command-output-limit",
            ),
        )
        for failure, command, timeout, expected_code in cases:
            with self.subTest(failure=failure):
                spawned: list[subprocess.Popen[bytes]] = []

                def capture_process(*args, **kwargs):
                    process = real_popen(*args, **kwargs)
                    spawned.append(process)
                    return process

                selector_patch = (
                    mock.patch.object(
                        helper.selectors,
                        "DefaultSelector",
                        side_effect=SelectFailingSelector,
                    )
                    if failure == "runtime"
                    else contextlib.nullcontext()
                )
                caught: BaseException | None = None
                try:
                    with (
                        mock.patch.object(
                            helper.subprocess,
                            "Popen",
                            side_effect=capture_process,
                        ),
                        selector_patch,
                    ):
                        try:
                            helper.BoundedRunner(helper.monotonic() + timeout).run(
                                command,
                                cwd=self.repository.root,
                            )
                        except BaseException as error:
                            caught = error

                    self.assertIsInstance(caught, helper.AuditError)
                    self.assertEqual(caught.code, expected_code)
                    self.assertNotIn("RAW_", str(caught))
                    self.assertEqual(len(spawned), 1)
                    self.assertIsNotNone(
                        spawned[0].poll(),
                        "child process survived runner failure",
                    )
                finally:
                    for process in spawned:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()

    def test_selector_close_failure_does_not_override_command_result(self) -> None:
        helper = load_helper_module()
        real_selector = selectors.DefaultSelector
        real_popen = subprocess.Popen
        spawned: list[subprocess.Popen[bytes]] = []

        class CloseFailingSelector:
            def __init__(self) -> None:
                self.inner = real_selector()

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def close(self) -> None:
                self.inner.close()
                raise RuntimeError("RAW_CLOSE_ERROR")

        def capture_process(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            spawned.append(process)
            return process

        with (
            mock.patch.object(
                helper.subprocess,
                "Popen",
                side_effect=capture_process,
            ),
            mock.patch.object(
                helper.selectors,
                "DefaultSelector",
                side_effect=CloseFailingSelector,
            ),
        ):
            result = helper.BoundedRunner(helper.monotonic() + 5).run(
                [sys.executable, "-c", "print('ok')"],
                cwd=self.repository.root,
            )

        self.assertEqual(result.stdout, b"ok\n")
        self.assertEqual(len(spawned), 1)
        self.assertIsNotNone(spawned[0].poll())
        self.assertTrue(spawned[0].stdout.closed)
        self.assertTrue(spawned[0].stderr.closed)

    def test_runner_reaps_child_when_signal_arrives_after_popen(self) -> None:
        helper = load_helper_module()
        real_popen = subprocess.Popen
        spawned: list[subprocess.Popen[bytes]] = []

        def spawn_then_interrupt(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            spawned.append(process)
            os.kill(os.getpid(), signal.SIGTERM)
            return process

        caught: BaseException | None = None
        previous_handler = signal.signal(signal.SIGTERM, helper.interrupted)
        try:
            with mock.patch.object(
                helper.subprocess,
                "Popen",
                side_effect=spawn_then_interrupt,
            ):
                try:
                    helper.BoundedRunner(helper.monotonic() + 5).run(
                        [sys.executable, "-c", "import time; time.sleep(60)"],
                        cwd=self.repository.root,
                    )
                except BaseException as error:
                    caught = error

            self.assertIsInstance(caught, helper.AuditError)
            self.assertEqual(caught.code, "interrupted")
            self.assertEqual(len(spawned), 1)
            self.assertIsNotNone(
                spawned[0].poll(),
                "child process survived post-Popen interruption",
            )
        finally:
            signal.signal(signal.SIGTERM, previous_handler)
            for process in spawned:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()

    def test_interruption_reaps_scanner_and_private_temp_directory(self) -> None:
        mode_path = self.fake_gitleaks.with_name("fake-mode")
        mode_path.write_text("sleep-scan", encoding="utf-8")
        environment = os.environ.copy()
        environment["PATH"] = str(self.fake_gitleaks.parent)
        audit = subprocess.Popen(
            [sys.executable, str(SCRIPT), str(self.repository.root)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        child_pid_path = self.fake_gitleaks.with_name("child-pid")
        child_pid: int | None = None
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not child_pid_path.exists():
                time.sleep(0.01)
            self.assertTrue(child_pid_path.exists(), "scanner child did not start")
            child_pid = int(child_pid_path.read_text(encoding="utf-8"))
            invocations = [
                json.loads(line) for line in self.invocation_log.read_text().splitlines()
            ]
            scanner_temp = Path(
                next(item["tempDir"] for item in invocations if item["argv"][0] == "stdin")
            )
            self.assertTrue(scanner_temp.exists())

            audit.send_signal(signal.SIGTERM)
            stdout, stderr = audit.communicate(timeout=10)

            self.assertIn(audit.returncode, {2, 3})
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertIn(payload["status"], {"partial", "failed"})
            self.assertFalse(scanner_temp.exists())
            with self.assertRaises(ProcessLookupError):
                os.kill(child_pid, 0)
        finally:
            if audit.poll() is None:
                audit.kill()
                audit.wait()
            if child_pid is not None:
                try:
                    os.killpg(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_custom_detector_caps_dense_records_and_output(self) -> None:
        sentinel = "DENSE_RAW_VALUE"
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        dense = (f"gitleaks:allow {sentinel}\n" * 5_000)
        for index in range(3):
            self.repository.write(f"dense-{index}.txt", dense)

        completed = self.run_audit()

        self.assertEqual(completed.returncode, 2, completed.stdout)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["verdict"], "partial")
        working = next(
            item for item in payload["coverage"] if item["source"] == "working-tree"
        )
        self.assertIn("custom-finding-limit", working["errors"])
        self.assertIn("finding-limit", working["errors"])
        self.assertIn("custom-finding-limit", working["limits"])
        self.assertIn("finding-limit", working["limits"])
        self.assertLessEqual(len(payload["findings"]), 2_000)
        self.assertLess(len(completed.stdout.encode()), 4_000_000)
        self.assertNotIn(sentinel, completed.stdout)
        self.assertNotIn(sentinel, self.invocation_log.read_text())

    def test_report_output_cap_handles_worst_case_escaped_paths(self) -> None:
        helper = load_helper_module()
        path = "\U0001f600" * 500
        findings = [
            helper.finding(
                category="session-link",
                detector="session.share-link",
                severity="high",
                confidence="high",
                source="working-tree",
                path=path,
                line=line,
            )
            for line in range(1, helper.MAX_FINDINGS + 1)
        ]
        for pretty in (False, True):
            with self.subTest(pretty=pretty):
                payload = helper.failed_payload("unused")
                payload["status"] = "complete"
                payload["verdict"] = "findings"
                payload["coverage"] = [
                    helper.Coverage("working-tree").as_dict(),
                    helper.Coverage("branch-history").as_dict(),
                ]
                payload["findings"] = findings
                payload["summary"] = helper.summarize_findings(findings)

                rendered, exit_code = helper.render_payload(payload, pretty=pretty)

                self.assertEqual(exit_code, 2)
                self.assertLessEqual(
                    len((rendered + "\n").encode()), helper.MAX_REPORT_OUTPUT_BYTES
                )
                self.assertEqual(payload["status"], "partial")
                self.assertEqual(payload["verdict"], "partial")
                self.assertLess(len(payload["findings"]), helper.MAX_FINDINGS)
                for entry in payload["coverage"]:
                    self.assertEqual(entry["status"], "partial")
                    self.assertIn("report-output-limit", entry["limits"])
                    self.assertIn("report-output-limit", entry["errors"])

    def test_custom_detector_honors_deadline_during_matching(self) -> None:
        helper = load_helper_module()
        coverage = helper.Coverage("working-tree")
        data = (
            b"https://chatgpt.com/share/FIRST\n"
            b"https://chatgpt.com/share/SECOND\n"
        )
        with mock.patch.object(helper, "monotonic", side_effect=[0.0, 0.0, 2.0]):
            findings = helper.detect_non_secret(
                data,
                source="working-tree",
                path="lines.txt",
                deadline=1.0,
                coverage=coverage,
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(coverage.status, "partial")
        self.assertIn("custom-detector-timeout", coverage.errors)
        self.assertIn("custom-detector-timeout", coverage.limits)

    def test_custom_detector_preserves_line_attribution(self) -> None:
        sentinel = "LINE_RAW_VALUE"
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.write(
            "lines.txt",
            "first\n"
            f"https://chatgpt.com/share/{sentinel}\n"
            "third\n"
            "gitleaks:\n allow\n",
        )

        completed = self.run_audit()

        self.assertEqual(completed.returncode, 0, completed.stdout)
        payload = json.loads(completed.stdout)
        lines = {
            item["detector"]: item["location"]["line"]
            for item in payload["findings"]
            if item["location"]["path"] == "lines.txt"
        }
        self.assertEqual(lines["session.share-link"], 2)
        self.assertEqual(lines["scanner.inline-allow"], 4)
        self.assertNotIn(sentinel, completed.stdout)

    def test_noop_scanner_fails_capability_probe_and_cannot_report_clean(self) -> None:
        self.repository.write("tracked.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()

        completed = self.run_audit(scanner=self.noop_gitleaks)

        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["verdict"], "partial")
        self.assertTrue(
            all("scanner-unavailable" in entry["errors"] for entry in payload["coverage"])
        )

    def test_missing_scanner_is_partial_not_clean(self) -> None:
        self.repository.write("tracked.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()

        completed = self.run_audit(scanner=self.missing_bin / "gitleaks")

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["verdict"], "partial")
        self.assertEqual(
            {entry["status"] for entry in payload["coverage"]},
            {"partial"},
        )
        self.assertTrue(
            all("scanner-unavailable" in entry["errors"] for entry in payload["coverage"])
        )

    def test_history_scanner_failure_is_partial_and_never_leaks_child_error(self) -> None:
        self.prepare_coverage_repository()

        completed = self.run_audit(fake_mode="fail-history")

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["verdict"], "partial")
        history = next(item for item in payload["coverage"] if item["source"] == "branch-history")
        self.assertEqual(history["status"], "partial")
        self.assertIn("scanner-failed", history["errors"])
        self.assertNotIn("RAW_CHILD_ERROR", completed.stdout)

    @unittest.skipUnless(shutil.which("gitleaks"), "gitleaks is not installed")
    def test_missing_remote_base_scans_all_messages_and_patches(self) -> None:
        history_key = "".join(("AKIA", "ABCDEFGHIJKLMNOP"))
        message_key = "".join(("AKIA", "QRSTUVWXYZABCDEF"))
        session_url = "https://chatgpt.com/share/" + "HISTORY_SESSION_SENTINEL"
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.write(
            "history-only.txt",
            f"aws_access_key_id = {history_key}\n{session_url}\n",
        )
        self.repository.run("add", "history-only.txt")
        message_file = self.repository.root.parent / "commit-message.txt"
        message_file.write_text(f"credential in message {message_key}\n", encoding="utf-8")
        self.repository.run("commit", "-F", str(message_file))
        (self.repository.root / "history-only.txt").unlink()
        self.repository.commit_all("remove historical content")
        self.repository.run("switch", "-c", "feature")
        self.repository.write("feature.txt", "clean\n")
        self.repository.commit_all("feature")

        completed = self.run_audit(scanner=self.real_scanner("history-real-bin"))

        self.assertEqual(completed.returncode, 0, completed.stdout)
        payload = json.loads(completed.stdout)
        history = next(item for item in payload["coverage"] if item["source"] == "branch-history")
        self.assertEqual(history["status"], "complete")
        self.assertEqual(history["base"], "all-reachable")
        self.assertIn("base-fallback-all-reachable", history["errors"])
        self.assertEqual(history["records"], 4)
        history_findings = [
            item for item in payload["findings"] if item["location"]["source"] == "branch-history"
        ]
        self.assertTrue(
            any(
                item["category"] == "secret"
                and item["location"]["path"] == "[commit-message]"
                and item["location"]["field"] == "message"
                for item in history_findings
            )
        )
        self.assertTrue(
            any(
                item["category"] == "session-link"
                and item["location"]["path"] == "history-only.txt"
                for item in history_findings
            )
        )
        self.assertNotIn(history_key, completed.stdout)
        self.assertNotIn(message_key, completed.stdout)
        self.assertNotIn(session_url, completed.stdout)

    @unittest.skipUnless(shutil.which("gitleaks"), "gitleaks is not installed")
    def test_real_gitleaks_ignores_repository_and_inline_suppression(self) -> None:
        access_key = "".join(("AKIA", "ABCDEFGHIJKLMNOP"))
        branch_key = "".join(("AKIA", "QRSTUVWXYZABCDEF"))
        self.repository.write(".gitignore", "ignored.txt\n")
        self.repository.write(
            ".gitleaks.toml",
            "[allowlist]\nregexTarget = 'match'\nregexes = ['AKIA[A-Z0-9]{16}']\n",
        )
        self.repository.write(
            ".gitleaksignore",
            "-:aws-access-token:1\ninherited.txt:aws-access-token:1\n"
            "feature.txt:aws-access-token:1\n",
        )
        self.repository.write(
            "inherited.txt",
            f"aws_access_key_id = {access_key} # gitleaks:allow\n",
        )
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.run("switch", "-c", "feature")
        self.repository.write(
            "feature.txt",
            f"aws_access_key_id = {branch_key} # gitleaks:allow\n",
        )
        self.repository.commit_all("feature")

        completed = self.run_audit(
            scanner=self.real_scanner("real-bin"),
            extra_environment={
                "GITLEAKS_CONFIG": str(self.repository.root / ".gitleaks.toml"),
                "GITLEAKS_CONFIG_TOML": "[allowlist]\npaths = ['.*']",
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stdout)
        payload = json.loads(completed.stdout)
        secrets = [item for item in payload["findings"] if item["category"] == "secret"]
        self.assertIn("inherited.txt", {item["location"]["path"] for item in secrets})
        history_secrets = [
            item for item in secrets if item["location"]["source"] == "branch-history"
        ]
        self.assertIn(
            "feature.txt",
            {item["location"]["path"] for item in history_secrets},
            completed.stdout,
        )
        self.assertNotIn(access_key, completed.stdout)
        self.assertNotIn(branch_key, completed.stdout)


if __name__ == "__main__":
    unittest.main()
