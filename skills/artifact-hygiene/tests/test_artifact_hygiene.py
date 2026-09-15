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
# Assembled at runtime so this file does not itself match the detectors it exercises.
ALLOW_CONTROL = "gitleaks" + ":allow"
SHARE_LINK = "https://chatgpt.com/" + "share/"


class RepositoryFixture:
    def __init__(self, root: Path, object_format: str = "sha1") -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.run("init", "-b", "main", f"--object-format={object_format}")
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


def make_capture(real_popen, spawned):
    """Bind the collector explicitly so the closure cannot capture a rebound
    loop variable from an enclosing subTest loop."""

    def capture_process(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        spawned.append(process)
        return process

    return capture_process


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
payload = sys.stdin.buffer.read() if command == "stdin" else b""
with open(log_path, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"argv": ["payload-size"], "bytes": len(payload)}) + "\\n")
if mode == "fail-history" and payload == b"history\\n":
    print("RAW_CHILD_ERROR", file=sys.stderr)
    raise SystemExit(2)
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
    "Secret": "REDACTED" if mode == "redacted-output" else raw,
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
        self.repository.write("inherited.txt", sentinels[0] + f" # {ALLOW_CONTROL}\n")
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
            SHARE_LINK + sentinels[14] + "\n",
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
            SHARE_LINK + sentinels[6] + "\n",
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
        self.assertEqual(payload["schemaVersion"], "artifact-hygiene/v2")
        self.assertEqual(payload["status"], "complete")
        self.assertEqual(payload["verdict"], "block")
        coverage = {entry["source"]: entry for entry in payload["coverage"]}
        self.assertEqual(coverage["working-tree"]["status"], "complete")
        self.assertEqual(coverage["branch-history"]["status"], "complete")
        self.assertEqual(coverage["custom-detectors"]["status"], "complete")
        self.assertEqual(coverage["custom-detectors"]["records"], 6)

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
            self.assertIn("--redact=0", arguments)
            self.assertNotIn("--redact=100", arguments)
            self.assertNotIn("--baseline-path", arguments)
            self.assertEqual(invocation["configEnv"], {})
            self.assertIsNone(invocation["gitExternalDiff"])
            self.assertEqual(invocation["gitNoLazyFetch"], "1")
            self.assertEqual(invocation["gitNoReplaceObjects"], "1")
            self.assertIsNone(invocation["rawEnv"])
            scanner_temp = Path(invocation["tempDir"])
            self.assertFalse(scanner_temp.is_relative_to(self.repository.root))
            self.assertFalse(scanner_temp.exists())
        self.assertTrue(all(item["argv"][0] == "stdin" for item in scan_invocations))

    def test_runner_reaps_child_across_setup_failures(self) -> None:
        helper = load_helper_module()
        real_popen = subprocess.Popen
        for failure in ("pipe", "selector"):
            with self.subTest(failure=failure):
                spawned: list[subprocess.Popen[bytes]] = []

                capture_process = make_capture(real_popen, spawned)

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

                capture_process = make_capture(real_popen, spawned)

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
        dense = (f"{ALLOW_CONTROL} {sentinel}\n" * 5_000)
        for index in range(3):
            self.repository.write(f"dense-{index}.txt", dense)

        completed = self.run_audit()

        self.assertEqual(completed.returncode, 2, completed.stdout)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["verdict"], "block")
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
                payload["verdict"] = "block"
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
                self.assertEqual(payload["verdict"], "block")
                self.assertLess(len(payload["findings"]), helper.MAX_FINDINGS)
                for entry in payload["coverage"]:
                    self.assertEqual(entry["status"], "partial")
                    self.assertIn("report-output-limit", entry["limits"])
                    self.assertIn("report-output-limit", entry["errors"])

    def test_added_patch_content_excludes_diff_metadata_context_and_removals(self) -> None:
        helper = load_helper_module()
        patch = (
            b"diff --git a/publishable.txt b/publishable.txt\n"
            b"index abc..def 100644\n"
            b"--- a/publishable.txt\n"
            b"+++ b/publishable.txt\n"
            b"@@ -1,2 +1,2 @@\n"
            b" context\n"
            b"-removed@example.invalid\n"
            b"+added@example.invalid\n"
        )

        self.assertEqual(helper.added_patch_content(patch), b"added@example.invalid\n")

    def test_clean_repository_reports_complete_clean_coverage(self) -> None:
        self.repository.write("tracked.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()

        completed = self.run_audit()

        self.assertEqual(completed.returncode, 0, completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "complete")
        self.assertEqual(payload["verdict"], "clean")
        self.assertEqual(payload["findings"], [])
        self.assertEqual(
            {entry["status"] for entry in payload["coverage"]},
            {"complete"},
        )

    def test_custom_detectors_report_redacted_bead_pii_and_ai_findings(self) -> None:
        helper = load_helper_module()
        coverage = helper.Coverage("branch-history")
        bead = "skills" + "-9yx"
        email = "canary" + "@acme.dev"
        name = "Canary" + " Person"
        ai_attribution = "Generated with " + "Claude Code"
        data = (
            f"bead: {bead}\n"
            f"email: {email}\n"
            f"ask {name}\n"
            f"{ai_attribution}\n"
        ).encode()

        findings = helper.detect_non_secret(
            data,
            source="branch-history",
            path="publishable.txt",
            deadline=helper.monotonic() + 5,
            coverage=coverage,
        )

        self.assertEqual(coverage.status, "complete")
        self.assertEqual(
            {(item["category"], item["detector"]) for item in findings},
            {
                ("bead-reference", "beads.reference"),
                ("personal-data", "pii.email"),
                ("personal-data", "pii.name"),
                ("ai-attribution", "ai.attribution"),
            },
        )
        self.assertEqual(
            {item["detector"]: item["location"]["line"] for item in findings},
            {
                "beads.reference": 1,
                "pii.email": 2,
                "pii.name": 3,
                "ai.attribution": 4,
            },
        )
        serialized = json.dumps(findings, sort_keys=True)
        for value in (bead, email, name, ai_attribution):
            self.assertNotIn(value, serialized)
        self.assertEqual(
            {item["evidence"]["token"] for item in findings},
            {
                "[REDACTED:BEAD-REFERENCE]",
                "[REDACTED:PERSONAL-DATA]",
                "[REDACTED:AI-ATTRIBUTION]",
            },
        )

    def test_privacy_detectors_do_not_rescan_published_working_tree(self) -> None:
        helper = load_helper_module()
        coverage = helper.Coverage("working-tree")
        data = (
            "bead: skills" + "-9yx\n"
            "ask Philip\n"
            "private" + "@acme.dev\n"
            "Generated with " + "Claude Code\n"
            + SHARE_LINK + "PUBLICATION_SENTINEL\n"
        ).encode()

        findings = helper.detect_non_secret(
            data,
            source="working-tree",
            path="published.txt",
            deadline=helper.monotonic() + 5,
            coverage=coverage,
        )

        self.assertEqual(
            {(item["category"], item["detector"]) for item in findings},
            {("session-link", "session.share-link")},
        )

    def test_dependency_lockfiles_skip_bead_and_maintainer_pii_noise(self) -> None:
        helper = load_helper_module()
        coverage = helper.Coverage("branch-history")
        package = "source" + "-map"
        email = "maintainer" + "@example.invalid"
        name = "Package" + " Maintainer"

        findings = helper.detect_non_secret(
            f'"name": "{package}", "email": "{email}", "author": "{name}"\n'.encode(),
            source="branch-history",
            path="package-lock.json",
            deadline=helper.monotonic() + 5,
            coverage=coverage,
        )

        self.assertEqual(findings, [])
        self.assertEqual(coverage.status, "complete")

    def test_personal_data_requires_context_and_ignores_human_trailers(self) -> None:
        helper = load_helper_module()
        coverage = helper.Coverage("branch-history")
        mention = "@" + "robyi"
        direct_email = "private" + "@acme.dev"
        trailer_email = "author" + "@acme.dev"
        placeholder_email = "fixture" + "@example.invalid"
        data = (
            "Technical Design Document\n"
            "Need to ask Philip before release\n"
            f"Please check with {mention}\n"
            f"Email {direct_email}\n"
            f"Email {placeholder_email}\n"
            f"Author: Human Person <{trailer_email}>\n"
            f"Co-authored-by: Human Person <{trailer_email}>\n"
            f"Signed-off-by: Human Person <{trailer_email}>\n"
        ).encode()

        findings = helper.detect_non_secret(
            data,
            source="branch-history",
            path="[commit-message]",
            deadline=helper.monotonic() + 5,
            coverage=coverage,
            field_name="message",
        )

        pii = [item for item in findings if item["category"] == "personal-data"]
        self.assertEqual(
            [(item["detector"], item["location"]["line"]) for item in pii],
            [("pii.email", 4), ("pii.name", 2), ("pii.name", 3)],
        )
        serialized = json.dumps(pii, sort_keys=True)
        for value in (
            "Philip",
            mention,
            direct_email,
            trailer_email,
            placeholder_email,
            "Human Person",
        ):
            self.assertNotIn(value, serialized)

    def test_bead_jsonl_attribution_fields_do_not_report_email_addresses(self) -> None:
        helper = load_helper_module()
        coverage = helper.Coverage("branch-history")
        contact = "contact" + "@acme.dev"
        nested_owner = "nested-owner" + "@acme.dev"
        case_variant = "case-variant" + "@acme.dev"
        malformed_owner = "malformed-owner" + "@acme.dev"
        duplicate_owner = "duplicate-owner" + "@acme.dev"
        data = json.dumps(
            {
                "owner": "owner" + "@acme.dev",
                "created_by": "creator" + "@acme.dev",
                "assignee": "assignee" + "@acme.dev",
                "email": contact,
                "metadata": {"owner": nested_owner},
                "Owner": case_variant,
            }
        ).encode() + (
            f'\n{{"owner":"{malformed_owner}","invalid":NaN}}'
            f'\n{{"owner":"first-owner@acme.dev","owner":"{duplicate_owner}"}}'
        ).encode()

        findings = helper.detect_non_secret(
            data,
            source="branch-history",
            path=".beads/issues.jsonl",
            deadline=helper.monotonic() + 5,
            coverage=coverage,
        )

        self.assertEqual(
            [(item["detector"], item["location"]["line"]) for item in findings],
            [
                ("pii.email", 1),
                ("pii.email", 1),
                ("pii.email", 1),
                ("pii.email", 2),
                ("pii.email", 3),
                ("pii.email", 3),
            ],
        )
        serialized = json.dumps(findings, sort_keys=True)
        for email in (
            contact,
            nested_owner,
            case_variant,
            malformed_owner,
            duplicate_owner,
        ):
            self.assertNotIn(email, serialized)

    def test_local_secret_fingerprint_allowlist_is_content_bound(self) -> None:
        self.repository.write("tracked.txt", "FINDING_MARKER original\n")
        self.repository.commit_all("base")
        self.repository.mark_base()

        initial = self.run_audit()

        self.assertEqual(initial.returncode, 0, initial.stdout)
        initial_payload = json.loads(initial.stdout)
        secret_findings = [
            item
            for item in initial_payload["findings"]
            if item["category"] == "secret"
        ]
        self.assertEqual(len(secret_findings), 1)
        allow_id = secret_findings[0]["allowId"]
        self.assertRegex(allow_id, r"^ah1:[0-9a-f]{32}$")

        self.repository.run(
            "config",
            "--local",
            "--add",
            "artifactHygiene.allowSecretFingerprints",
            allow_id,
        )
        allowed = self.run_audit()

        self.assertEqual(allowed.returncode, 0, allowed.stdout)
        allowed_payload = json.loads(allowed.stdout)
        self.assertEqual(allowed_payload["verdict"], "clean")
        self.assertEqual(allowed_payload["findings"], [])
        self.assertEqual(len(allowed_payload["suppressed"]), 1)
        self.assertEqual(allowed_payload["suppressed"][0]["allowId"], allow_id)
        self.assertEqual(allowed_payload["summary"]["suppressed"], 1)
        self.assertEqual(
            allowed_payload["target"]["policy"],
            "defaults+allow-secret-fingerprints",
        )

        self.repository.write("tracked.txt", "FINDING_MARKER replacement\n")
        replacement = self.run_audit()

        self.assertEqual(replacement.returncode, 0, replacement.stdout)
        replacement_payload = json.loads(replacement.stdout)
        replacement_findings = [
            item
            for item in replacement_payload["findings"]
            if item["category"] == "secret"
        ]
        self.assertEqual(len(replacement_findings), 1)
        self.assertNotEqual(replacement_findings[0]["allowId"], allow_id)
        self.assertTrue(
            any(
                item.get("allowId") == allow_id
                for item in replacement_payload["suppressed"]
            )
        )

    def test_allowed_worktree_key_does_not_hide_staged_replacement(self) -> None:
        original = "FINDING_MARKER original\n"
        replacement = "FINDING_MARKER replacement\n"
        self.repository.write("tracked.txt", original)
        self.repository.commit_all("base")
        self.repository.mark_base()
        initial = json.loads(self.run_audit().stdout)
        allow_id = next(
            item["allowId"]
            for item in initial["findings"]
            if item["category"] == "secret"
        )
        self.repository.run(
            "config",
            "--local",
            "--add",
            "artifactHygiene.allowSecretFingerprints",
            allow_id,
        )
        self.repository.write("tracked.txt", replacement)
        self.repository.run("add", "tracked.txt")
        self.repository.write("tracked.txt", original)

        completed = self.run_audit()

        self.assertEqual(completed.returncode, 0, completed.stdout)
        payload = json.loads(completed.stdout)
        active_secret_ids = {
            item["allowId"]
            for item in payload["findings"]
            if item["category"] == "secret"
        }
        self.assertEqual(len(active_secret_ids), 1)
        self.assertNotIn(allow_id, active_secret_ids)
        self.assertTrue(
            any(item.get("allowId") == allow_id for item in payload["suppressed"])
        )

    def test_secret_fingerprint_allowlist_ignores_nonlocal_sources_and_invalid_ids(
        self,
    ) -> None:
        self.repository.write("tracked.txt", "FINDING_MARKER original\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        initial = json.loads(self.run_audit().stdout)
        allow_id = next(
            item["allowId"]
            for item in initial["findings"]
            if item["category"] == "secret"
        )
        included_config = self.repository.write(
            "artifact-hygiene.inc",
            f"[artifactHygiene]\nallowSecretFingerprints = {allow_id}\n",
        )
        self.repository.run("add", "artifact-hygiene.inc")
        self.repository.run("config", "--local", "--add", "include.path", str(included_config))
        self.repository.run(
            "config",
            "--local",
            "--add",
            "artifactHygiene.allowSecretFingerprints",
            "occ:not-a-secret-fingerprint",
        )

        completed = self.run_audit(
            extra_environment={
                "ARTIFACT_HYGIENE_ALLOW_SECRET_FINGERPRINTS": allow_id
            }
        )

        self.assertEqual(completed.returncode, 0, completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["target"]["policy"], "defaults")
        self.assertEqual(payload["suppressed"], [])
        self.assertTrue(any(item["category"] == "secret" for item in payload["findings"]))

    def test_scanner_without_raw_secret_makes_coverage_partial(self) -> None:
        self.repository.write("tracked.txt", "FINDING_MARKER original\n")
        self.repository.commit_all("base")
        self.repository.mark_base()

        completed = self.run_audit(fake_mode="redacted-output")

        self.assertEqual(completed.returncode, 2, completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["verdict"], "block")
        self.assertEqual(payload["suppressed"], [])
        scanner_coverage = [
            item
            for item in payload["coverage"]
            if item["source"] in {"working-tree", "branch-history"}
        ]
        self.assertTrue(scanner_coverage)
        self.assertTrue(
            all("scanner-unavailable" in item["errors"] for item in scanner_coverage)
        )

    def test_local_bead_override_is_private_and_visible_in_policy(self) -> None:
        bead = "skills" + "-9yx"
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.run("switch", "-c", "feature")
        self.repository.write("publishable.txt", f"bead: {bead}\n")
        self.repository.commit_all("feature")
        self.repository.run(
            "config", "--local", "artifactHygiene.allowBeadReferences", "true"
        )

        completed = self.run_audit()

        self.assertEqual(completed.returncode, 0, completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["target"]["policy"], "defaults+allow-bead-references")
        self.assertNotIn(
            "bead-reference",
            {item["category"] for item in payload["findings"]},
        )
        self.assertNotIn(bead, completed.stdout)

    def test_environment_can_enable_local_bead_override(self) -> None:
        bead = "skills" + "-9yx"
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.run("switch", "-c", "feature")
        self.repository.write("tracked.txt", f"bead: {bead}\n")
        self.repository.commit_all("feature")

        completed = self.run_audit(
            extra_environment={"ARTIFACT_HYGIENE_ALLOW_BEAD_REFERENCES": "1"}
        )

        self.assertEqual(completed.returncode, 0, completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["target"]["policy"], "defaults+allow-bead-references")
        self.assertNotIn(
            "bead-reference",
            {item["category"] for item in payload["findings"]},
        )

    def test_custom_detectors_scan_unpublished_messages_and_added_lines(self) -> None:
        bead = "skills" + "-9yx"
        email = "canary" + "@acme.dev"
        name = "Canary" + " Person"
        ai_attribution = "Generated with " + "Claude Code"
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.run("switch", "-c", "feature")
        self.repository.write("publishable.txt", f"bead: {bead}\nemail: {email}\n")
        message_path = self.repository.root.parent / "commit-message.txt"
        message_path.write_text(
            f"Need to ask {name}\n{ai_attribution}\n",
            encoding="utf-8",
        )
        self.repository.run("add", "publishable.txt")
        self.repository.run("commit", "-F", str(message_path))

        completed = self.run_audit()

        self.assertEqual(completed.returncode, 0, completed.stdout)
        payload = json.loads(completed.stdout)
        history_findings = [
            item
            for item in payload["findings"]
            if item["location"]["source"] == "branch-history"
        ]
        self.assertTrue(
            {
                ("bead-reference", "publishable.txt"),
                ("personal-data", "publishable.txt"),
                ("personal-data", "[commit-message]"),
                ("ai-attribution", "[commit-message]"),
            }.issubset(
                {(item["category"], item["location"]["path"]) for item in history_findings}
            )
        )
        for value in (bead, email, name, ai_attribution):
            self.assertNotIn(value, completed.stdout)

    def test_missing_custom_detector_makes_coverage_partial(self) -> None:
        helper = load_helper_module()

        coverage = helper.custom_detector_coverage(
            helper.monotonic() + 5, helper.DEFAULT_DETECTORS[:-1]
        )

        self.assertEqual(coverage.source, "custom-detectors")
        self.assertEqual(coverage.status, "partial")
        self.assertIn("custom-detector-unavailable", coverage.errors)

    def test_generic_bead_shape_ignores_hyphenated_words(self) -> None:
        helper = load_helper_module()
        coverage = helper.Coverage("branch-history")
        words = ("dry-run", "watch-prs", "diagnose-bug", "python-3.14", "x-abcdefghi1")
        ids = ("agents" + "-c56", "inbox" + "-n424", "ai-tools" + "-dw1", "skills" + "-ip3.3")
        data = "\n".join(words + ids).encode() + b"\n"

        findings = helper.detect_non_secret(
            data,
            source="branch-history",
            path="notes.md",
            deadline=helper.monotonic() + 5,
            coverage=coverage,
        )

        self.assertEqual(
            [item["location"]["line"] for item in findings],
            [len(words) + 1 + offset for offset in range(len(ids))],
        )
        self.assertTrue(all(item["detector"] == "beads.reference" for item in findings))

    def test_known_prefixes_match_digitless_ids_and_only_widen(self) -> None:
        helper = load_helper_module()
        coverage = helper.Coverage("branch-history")
        detector = helper.build_bead_detector(("skills", "ai-tools"))
        data = b"skills-shy\nother-shy\nother-a1b\nai-tools-shy\nskillset-shy\n"

        findings = helper.detect_non_secret(
            data,
            source="branch-history",
            path="notes.md",
            deadline=helper.monotonic() + 5,
            coverage=coverage,
            detectors=helper.active_detectors(detector),
        )

        self.assertEqual([item["location"]["line"] for item in findings], [1, 3, 4])
        self.assertTrue(
            helper.custom_detector_capability_probe(
                helper.monotonic() + 5, helper.active_detectors(detector)
            )
        )

    def test_bead_prefixes_come_from_clone_config_environment_and_store(self) -> None:
        helper = load_helper_module()
        runner = helper.BoundedRunner(helper.monotonic() + 5)
        self.assertEqual(helper.bead_prefixes(runner, self.repository.root), ((), "generic"))

        self.repository.write(".beads/config.yaml", 'issue-prefix: "skills"\n')
        self.repository.write(
            ".beads/issues.jsonl", '{"id":"ai-tools-dw1"}\n{"id":"Bad Prefix-x1"}\n'
        )
        self.assertEqual(
            helper.bead_prefixes(runner, self.repository.root),
            (("skills", "ai-tools"), "repository"),
        )

        self.repository.run("config", "--local", "artifactHygiene.beadPrefixes", "router, agents")
        with mock.patch.dict(os.environ, {"ARTIFACT_HYGIENE_BEAD_PREFIXES": "inbox"}):
            prefixes, source = helper.bead_prefixes(runner, self.repository.root)
        self.assertEqual(source, "configured")
        self.assertEqual(prefixes, ("router", "agents", "inbox", "skills", "ai-tools"))

    def test_email_detector_skips_scp_style_git_urls(self) -> None:
        helper = load_helper_module()
        coverage = helper.Coverage("branch-history")
        data = b"git@github.com:owner/repo.git\nmaintainer@" + b"acme.dev\n"

        findings = helper.detect_non_secret(
            data,
            source="branch-history",
            path="script.sh",
            deadline=helper.monotonic() + 5,
            coverage=coverage,
        )

        self.assertEqual([(i["detector"], i["location"]["line"]) for i in findings], [("pii.email", 2)])

    def test_email_detector_skips_url_userinfo(self) -> None:
        helper = load_helper_module()
        coverage = helper.Coverage("branch-history")
        data = (
            b'remote: "git+ssh://git@github.com/owner/repo.git"\n'
            b"contact: mailto:maintainer@" + b"acme.dev\n"
        )

        findings = helper.detect_non_secret(
            data,
            source="branch-history",
            path=".beads/config.yaml",
            deadline=helper.monotonic() + 5,
            coverage=coverage,
        )

        self.assertEqual([(i["detector"], i["location"]["line"]) for i in findings], [("pii.email", 2)])

    def test_known_prefix_beads_repository_name_is_not_a_bead_reference(self) -> None:
        helper = load_helper_module()
        coverage = helper.Coverage("branch-history")
        detector = helper.build_bead_detector(("letterbox",))
        data = b"flurdy/letterbox-beads.git\nletterbox" + b"-shy\nletterbox" + b"-beads7\n"

        findings = helper.detect_non_secret(
            data,
            source="branch-history",
            path=".beads/config.yaml",
            deadline=helper.monotonic() + 5,
            coverage=coverage,
            detectors=helper.active_detectors(detector),
        )

        self.assertEqual(
            [i["location"]["line"] for i in findings if i["detector"] == "beads.reference"], [2, 3]
        )
        self.assertTrue(
            helper.custom_detector_capability_probe(
                helper.monotonic() + 5, helper.active_detectors(detector)
            )
        )

    def test_name_detector_ignores_camel_case_identifiers(self) -> None:
        helper = load_helper_module()
        coverage = helper.Coverage("branch-history")
        data = b"only then call ScheduleWakeup as the last action\nthen ask " + b"Philip\n"

        findings = helper.detect_non_secret(
            data,
            source="branch-history",
            path="SKILL.md",
            deadline=helper.monotonic() + 5,
            coverage=coverage,
        )

        self.assertEqual([(i["detector"], i["location"]["line"]) for i in findings], [("pii.name", 2)])

    def test_audit_skill_paths_are_exempt_from_non_secret_detectors(self) -> None:
        helper = load_helper_module()
        coverage = helper.Coverage("branch-history")
        data = b"ask " + b"Philip\nbead: skills" + b"-9yx\n" + ALLOW_CONTROL.encode() + b"\n"

        exempt = helper.detect_non_secret(
            data,
            source="branch-history",
            path="skills/artifact-hygiene/tests/fixture.py",
            deadline=helper.monotonic() + 5,
            coverage=coverage,
        )
        reported = helper.detect_non_secret(
            data,
            source="branch-history",
            path="skills/other/tests/fixture.py",
            deadline=helper.monotonic() + 5,
            coverage=coverage,
        )

        self.assertEqual(exempt, [])
        self.assertEqual(len(reported), 3)

    def test_custom_detector_honors_deadline_during_matching(self) -> None:
        helper = load_helper_module()
        coverage = helper.Coverage("working-tree")
        data = (
            f"{SHARE_LINK}FIRST\n".encode()
            + f"{SHARE_LINK}SECOND\n".encode()
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
        self.assertIn("deadline-exceeded", coverage.errors)
        self.assertIn("deadline-exceeded", coverage.limits)

    def test_custom_detector_preserves_line_attribution(self) -> None:
        sentinel = "LINE_RAW_VALUE"
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.write(
            "lines.txt",
            "first\n"
            f"{SHARE_LINK}{sentinel}\n"
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
        self.assertEqual(payload["verdict"], "block")
        scanner_coverage = [
            entry
            for entry in payload["coverage"]
            if entry["source"] in {"working-tree", "branch-history"}
        ]
        self.assertTrue(
            all("scanner-unavailable" in entry["errors"] for entry in scanner_coverage)
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
        self.assertEqual(payload["verdict"], "block")
        scanner_coverage = [
            entry
            for entry in payload["coverage"]
            if entry["source"] in {"working-tree", "branch-history"}
        ]
        self.assertEqual({entry["status"] for entry in scanner_coverage}, {"partial"})
        self.assertTrue(
            all("scanner-unavailable" in entry["errors"] for entry in scanner_coverage)
        )

    def large_blob(self, path: str = "large.txt", content: str = "x\n") -> str:
        self.repository.write(path, content * 600_000)
        return self.repository.run("hash-object", "--no-filters", "--", path).strip()

    def assert_size_decision(self, payload, blob, decision, reason):
        self.assertIn("sizeDecisions", payload)
        entries = [item for item in payload["sizeDecisions"] if item["blobId"] == blob]
        self.assertTrue(entries, payload)
        for item in entries:
            self.assertEqual(item["decision"], decision)
            self.assertEqual(item["reason"], reason)
            self.assertGreater(item["size"], 1_000_000)
            self.assertEqual(item["location"]["path"], "large.txt")
        return entries

    def test_large_published_blob_is_visibly_skipped(self) -> None:
        blob = self.large_blob()
        self.repository.commit_all("base")
        self.repository.mark_base()
        before = self.repository.state()
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, payload)
        self.assertEqual(payload["verdict"], "clean")
        self.assert_size_decision(payload, blob, "skipped-by-policy", "published-base-history")
        self.assertEqual(self.repository.state(), before)
        invocations = [json.loads(line) for line in self.invocation_log.read_text().splitlines()]
        self.assertFalse(any(item["argv"][0] == "git" for item in invocations))
        self.assertTrue(all(item.get("bytes", 0) <= 1_000_000 for item in invocations))

    def test_large_blob_in_older_remote_history_is_skipped_after_rename(self) -> None:
        blob = self.large_blob("old.txt")
        self.repository.commit_all("original asset")
        (self.repository.root / "old.txt").unlink()
        self.repository.commit_all("remove asset")
        self.repository.mark_base()
        self.large_blob()
        self.repository.commit_all("reintroduce asset")
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, payload)
        entries = self.assert_size_decision(
            payload, blob, "skipped-by-policy", "published-base-history"
        )
        self.assertIn("branch-history", {item["location"]["source"] for item in entries})

    def test_new_large_blob_denies_and_exact_local_allowance_skips(self) -> None:
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        blob = self.large_blob()
        for stage in ("untracked", "staged", "committed"):
            with self.subTest(stage=stage):
                if stage == "staged":
                    self.repository.run("add", "large.txt")
                elif stage == "committed":
                    self.repository.run("commit", "-m", "add asset")
                completed = self.run_audit()
                payload = json.loads(completed.stdout)
                self.assertEqual(completed.returncode, 2, payload)
                entries = self.assert_size_decision(payload, blob, "deny", "unapproved-large-blob")
                for item in entries:
                    self.assertIn("artifactHygiene.allowLargeBlobs", item["remediation"])
                    self.assertIn(blob, item["remediation"])
        self.repository.run("config", "--local", "--add", "artifactHygiene.allowLargeBlobs", blob)
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, payload)
        self.assertIn("allow-large-blobs", payload["target"]["policy"])
        self.assert_size_decision(payload, blob, "skipped-by-policy", "local-blob-allowance")
        changed = self.large_blob(content="y\n")
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 2, payload)
        self.assert_size_decision(payload, changed, "deny", "unapproved-large-blob")
        self.assert_size_decision(payload, blob, "skipped-by-policy", "local-blob-allowance")

    def test_modified_published_large_blob_does_not_inherit_exemption(self) -> None:
        original = self.large_blob()
        self.repository.commit_all("base")
        self.repository.mark_base()
        changed = self.large_blob(content="y\n")
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 2, payload)
        self.assert_size_decision(payload, changed, "deny", "unapproved-large-blob")
        self.assert_size_decision(payload, original, "skipped-by-policy", "published-base-history")

    def test_large_blob_allowance_rejects_environment_global_and_included_config(self) -> None:
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        blob = self.large_blob()
        config = self.repository.write(
            "allowance.config", f"[artifactHygiene]\nallowLargeBlobs = {blob}\n"
        )
        self.repository.run("config", "--local", "include.path", str(config))
        for value in ("*", "large.txt", "0" * 64):
            self.repository.run("config", "--local", "--add", "artifactHygiene.allowLargeBlobs", value)
        completed = self.run_audit(extra_environment={
            "ARTIFACT_HYGIENE_ALLOW_LARGE_BLOBS": blob,
            "GIT_CONFIG_GLOBAL": str(config),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "artifactHygiene.allowLargeBlobs",
            "GIT_CONFIG_VALUE_0": blob,
        })
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 2, payload)
        self.assertNotIn("allow-large-blobs", payload["target"]["policy"])
        self.assert_size_decision(payload, blob, "deny", "unapproved-large-blob")

    def test_missing_base_or_local_symbolic_target_cannot_prove_publication(self) -> None:
        blob = self.large_blob()
        self.repository.commit_all("asset")
        for target in (None, "refs/heads/main"):
            with self.subTest(target=target):
                if target:
                    self.repository.run("symbolic-ref", "refs/remotes/origin/HEAD", target)
                completed = self.run_audit()
                payload = json.loads(completed.stdout)
                self.assertEqual(completed.returncode, 2, payload)
                self.assert_size_decision(payload, blob, "deny", "unapproved-large-blob")

    def test_large_predecessor_deletion_and_shrink_do_not_build_huge_patches(self) -> None:
        self.large_blob(content="x" * 100 + "\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.write("large.txt", "small\n")
        self.repository.commit_all("shrink asset")
        (self.repository.root / "large.txt").unlink()
        self.repository.commit_all("delete asset")
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, payload)
        self.assertEqual(payload["verdict"], "clean")

    def test_oversized_history_remains_denied_after_local_deletion(self) -> None:
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        blob = self.large_blob()
        self.repository.commit_all("asset")
        (self.repository.root / "large.txt").unlink()
        self.repository.commit_all("remove asset")
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 2, payload)
        entries = self.assert_size_decision(payload, blob, "deny", "unapproved-large-blob")
        self.assertEqual({item["location"]["source"] for item in entries}, {"branch-history"})

    def test_large_skip_never_suppresses_scanner_or_history_read_failure(self) -> None:
        helper = load_helper_module()
        blob = self.large_blob()
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.write("small.txt", "clean\n")
        self.repository.commit_all("local addition")
        real_run = helper.BoundedRunner.run

        def fail_scan(runner, args, **kwargs):
            if kwargs.get("input_bytes") == b"clean\n":
                raise helper.AuditError("command-failed")
            return real_run(runner, args, **kwargs)

        for failing in ("scanner", "history"):
            with self.subTest(failing=failing):
                if failing == "scanner":
                    patch = mock.patch.object(helper.BoundedRunner, "run", fail_scan)
                else:
                    patch = mock.patch.object(
                        helper, "commit_message", side_effect=helper.AuditError("command-failed")
                    )
                with patch:
                    payload, code = helper.scan(
                        self.repository.root, self.repository.run("rev-parse", "HEAD").strip(),
                        str(self.fake_gitleaks), time.monotonic() + 20,
                    )
                self.assertEqual(code, 2, payload)
                errors = {error for item in payload["coverage"] for error in item["errors"]}
                self.assertIn("scanner-failed" if failing == "scanner" else "history-read-failed", errors)
                self.assert_size_decision(payload, blob, "skipped-by-policy", "published-base-history")

    def test_large_published_binary_above_total_budget_is_skipped(self) -> None:
        target = self.repository.root / "large.txt"
        with target.open("wb") as handle:
            handle.truncate(51_000_000)
        blob = self.repository.run("hash-object", "--no-filters", "--", "large.txt").strip()
        self.repository.commit_all("base")
        self.repository.mark_base()
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, payload)
        self.assert_size_decision(payload, blob, "skipped-by-policy", "published-base-history")
        self.assertEqual(payload["verdict"], "clean")

    def test_large_sha256_blob_allows_exact_repo_format_id(self) -> None:
        self.repository = RepositoryFixture(self.repository.root.parent / "sha256", "sha256")
        blob = self.large_blob()
        self.assertEqual(len(blob), 64)
        self.repository.run("config", "--local", "artifactHygiene.allowLargeBlobs", blob)
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, payload)
        self.assert_size_decision(payload, blob, "skipped-by-policy", "local-blob-allowance")

    def test_publication_proof_does_not_enumerate_base_objects(self) -> None:
        helper = load_helper_module()
        blob = self.large_blob()
        self.repository.commit_all("base")
        self.repository.mark_base()
        real_git = helper.git
        find_calls = 0

        def bounded_proof(*args, **kwargs):
            nonlocal find_calls
            if "--objects" in args:
                raise helper.AuditError("command-output-limit")
            if any(
                isinstance(argument, str) and argument.startswith("--find-object=")
                for argument in args
            ):
                find_calls += 1
            return real_git(*args, **kwargs)

        with mock.patch.object(helper, "git", bounded_proof):
            payload, code = helper.scan(
                self.repository.root, self.repository.run("rev-parse", "HEAD").strip(),
                str(self.fake_gitleaks), time.monotonic() + 20,
            )
        self.assertEqual(code, 0, payload)
        self.assertEqual(find_calls, 0)
        self.assert_size_decision(payload, blob, "skipped-by-policy", "published-base-history")

    def test_failed_publication_proof_cannot_be_overridden(self) -> None:
        helper = load_helper_module()
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        blob = self.large_blob()
        self.repository.run("config", "--local", "artifactHygiene.allowLargeBlobs", blob)
        real_git = helper.git

        def failed_proof(*args, **kwargs):
            if any(
                isinstance(argument, str) and argument.startswith("--find-object=")
                for argument in args
            ):
                raise helper.AuditError("command-output-limit")
            return real_git(*args, **kwargs)

        with mock.patch.object(helper, "git", failed_proof):
            payload, code = helper.scan(
                self.repository.root, self.repository.run("rev-parse", "HEAD").strip(),
                str(self.fake_gitleaks), time.monotonic() + 20,
            )
        self.assertEqual(code, 2, payload)
        self.assertIn("publication-proof-failed", payload["coverage"][0]["errors"])
        self.assert_size_decision(payload, blob, "deny", "publication-proof-failed")

    def test_publication_proof_ignores_repository_log_configuration(self) -> None:
        blob = self.large_blob()
        self.repository.commit_all("base")
        self.repository.mark_base()
        for key, value in (
            ("log.showRoot", "false"),
            ("log.diffMerges", "first-parent"),
            ("diff.renames", "copies"),
            ("diff.relative", "true"),
            ("format.pretty", "medium"),
            ("color.ui", "always"),
            ("core.commitGraph", "true"),
        ):
            self.repository.run("config", "--local", key, value)
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, payload)
        self.assert_size_decision(payload, blob, "skipped-by-policy", "published-base-history")

    def test_publication_proof_finds_blob_introduced_by_merge(self) -> None:
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("root")
        self.repository.run("switch", "-c", "side")
        blob = self.large_blob()
        self.repository.commit_all("side asset")
        self.repository.run("switch", "main")
        self.repository.write("main.txt", "clean\n")
        self.repository.commit_all("main addition")
        self.repository.run("merge", "--no-ff", "side", "-m", "merge asset")
        self.repository.mark_base()
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, payload)
        self.assert_size_decision(payload, blob, "skipped-by-policy", "published-base-history")

    def test_sanitized_environment_disables_git_grafts(self) -> None:
        helper = load_helper_module()
        self.assertEqual(helper.sanitized_environment()["GIT_GRAFT_FILE"], os.devnull)

    def test_unpublished_merge_large_blob_is_denied(self) -> None:
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.run("switch", "-c", "side")
        blob = self.large_blob()
        self.repository.commit_all("asset")
        self.repository.run("switch", "main")
        self.repository.write("main.txt", "clean\n")
        self.repository.commit_all("main addition")
        self.repository.run("merge", "--no-ff", "side", "-m", "merge asset")
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 2, payload)
        entries = self.assert_size_decision(payload, blob, "deny", "unapproved-large-blob")
        self.assertEqual(len([item for item in entries if item["location"]["source"] == "branch-history"]), 2)

    def test_history_attributes_and_literal_path_cannot_hide_small_content(self) -> None:
        self.repository.write(".gitattributes", "* -diff\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.write(":(exclude)hidden.txt", "FINDING_MARKER\n")
        self.repository.commit_all("add content")
        (self.repository.root / ":(exclude)hidden.txt").unlink()
        self.repository.commit_all("remove content")
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, payload)
        self.assertTrue(any(
            item["category"] == "secret" and item["location"]["path"] == ":(exclude)hidden.txt"
            for item in payload["findings"]
        ), payload)

    def test_large_hash_rejects_replaced_path_and_expired_deadline(self) -> None:
        helper = load_helper_module()
        self.large_blob()
        policy = helper.SizePolicy(
            helper.BoundedRunner(time.monotonic() + 20), self.repository.root,
            "sha1", frozenset(), None,
        )
        real_fstat = helper.os.fstat
        calls = 0

        def replace_path(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                (self.repository.root / "large.txt").unlink()
                self.large_blob(content="y\n")
            return real_fstat(descriptor)

        with mock.patch.object(helper.os, "fstat", replace_path):
            with self.assertRaises(helper.AuditError) as caught:
                helper.read_candidate(self.repository.root, "large.txt", policy)
            self.assertEqual(caught.exception.code, "file-changed")
        policy.runner.deadline = time.monotonic() - 1
        with self.assertRaises(helper.AuditError) as caught:
            helper.read_candidate(self.repository.root, "large.txt", policy)
        self.assertEqual(caught.exception.code, "command-timeout")

    def assert_deadline_payload(self, payload, code):
        self.assertEqual(code, 2, payload)
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["verdict"], "block")
        errors = {
            entry["source"]: set(entry["errors"])
            for entry in payload["coverage"]
        }
        for source in ("working-tree", "branch-history"):
            self.assertIn("deadline-exceeded", errors[source])
        misleading = {
            "command-timeout", "scanner-failed", "history-read-failed",
            "state-recheck-failed", "index-read-failed", "publication-proof-failed",
        }
        self.assertFalse(misleading & set().union(*errors.values()), errors)
        self.assertIs(payload["summary"]["truncated"], True)

    def test_scanner_deadline_is_not_relabelled(self) -> None:
        helper = load_helper_module()
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        real_run = helper.BoundedRunner.run

        def expire_scanner(runner, args, **kwargs):
            if kwargs.get("input_bytes") == b"clean\n":
                runner.deadline = time.monotonic() - 1
                raise helper.AuditError("command-timeout")
            return real_run(runner, args, **kwargs)

        with mock.patch.object(helper.BoundedRunner, "run", expire_scanner):
            payload, code = helper.scan(
                self.repository.root, self.repository.run("rev-parse", "HEAD").strip(),
                str(self.fake_gitleaks), time.monotonic() + 20,
            )
        self.assert_deadline_payload(payload, code)

    def test_history_deadline_is_not_relabelled(self) -> None:
        helper = load_helper_module()
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.write("feature.txt", "clean feature\n")
        self.repository.commit_all("feature deadline sentinel")

        def expire_history(runner, repository, commit):
            runner.deadline = time.monotonic() - 1
            raise helper.AuditError("command-timeout")

        with mock.patch.object(helper, "commit_message", expire_history):
            payload, code = helper.scan(
                self.repository.root, self.repository.run("rev-parse", "HEAD").strip(),
                str(self.fake_gitleaks), time.monotonic() + 20,
            )
        self.assert_deadline_payload(payload, code)

    def test_state_recheck_deadline_is_not_relabelled(self) -> None:
        helper = load_helper_module()
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        real_state = helper.repository_state
        calls = 0

        def expire_recheck(runner, repository):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise helper.AuditError("command-timeout")
            return real_state(runner, repository)

        with mock.patch.object(helper, "repository_state", expire_recheck):
            payload, code = helper.scan(
                self.repository.root, self.repository.run("rev-parse", "HEAD").strip(),
                str(self.fake_gitleaks), time.monotonic() + 20,
            )
        self.assert_deadline_payload(payload, code)

    def test_default_deadline_supports_large_repositories(self) -> None:
        helper = load_helper_module()
        self.assertEqual(helper.DEFAULT_TIMEOUT_SECONDS, 600.0)

    def test_grading_tip_lookup_is_cached_and_fails_closed(self) -> None:
        helper = load_helper_module()
        self.repository.write("first.txt", "FIRST_FINDING_MARKER\n")
        self.repository.write("second.txt", "SECOND_FINDING_MARKER\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.run("config", "--local", "artifactHygiene.remoteVisibility", "private")
        real_git = helper.git
        tip_calls = 0

        def count_tip(*args, **kwargs):
            nonlocal tip_calls
            if "ls-tree" in args:
                tip_calls += 1
            if any(isinstance(arg, str) and arg.startswith("--find-object=") for arg in args):
                raise helper.AuditError("unexpected-history-walk")
            return real_git(*args, **kwargs)

        with mock.patch.object(helper, "git", count_tip):
            payload, code = helper.scan(self.repository.root, None, str(self.fake_gitleaks), time.monotonic() + 20)
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["verdict"], "advisory")
        self.assertEqual(tip_calls, 1)

        def fail_tip(*args, **kwargs):
            if "ls-tree" in args:
                raise helper.AuditError("command-output-limit")
            return real_git(*args, **kwargs)

        with mock.patch.object(helper, "git", fail_tip):
            payload, code = helper.scan(self.repository.root, None, str(self.fake_gitleaks), time.monotonic() + 20)
        self.assertEqual(code, 2, payload)
        self.assertEqual(payload["verdict"], "block")
        self.assertTrue(all(item["policy"]["grade"] == "block" for item in payload["findings"]))
        self.assertTrue(all(item["location"]["publication"] == "unknown" for item in payload["findings"]))

    def test_grading_historical_blob_reintroduced_at_new_path(self) -> None:
        self.repository.write("old.txt", "FINDING_MARKER\n")
        self.repository.commit_all("original")
        (self.repository.root / "old.txt").unlink()
        self.repository.commit_all("remove original")
        self.repository.mark_base()
        self.repository.run("config", "--local", "artifactHygiene.remoteVisibility", "private")
        self.repository.write("new.txt", "FINDING_MARKER\n")
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, payload)
        self.assertEqual(payload["verdict"], "advisory")
        self.assertEqual(len(payload["findings"]), 1)
        self.assertEqual(payload["findings"][0]["location"]["publication"], "already-published")
        self.repository.commit_all("reintroduce content")
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["verdict"], "block")
        self.assertTrue(any(item["location"]["publication"] == "branch-history" and item["policy"]["grade"] == "block"
                            for item in payload["findings"]))

    def test_grading_unknown_object_identity_cannot_use_allowance(self) -> None:
        helper = load_helper_module()
        self.repository.write("base.txt", "clean\n")
        self.repository.commit_all("base")
        base = self.repository.run("rev-parse", "HEAD").strip()
        invalid = "b" * 64
        policy = helper.SizePolicy(helper.BoundedRunner(time.monotonic() + 20), self.repository.root,
                                   "sha1", frozenset({invalid}), base)
        coverage = helper.Coverage("working-tree")
        policy.record(helper.LargeBlob(invalid, 2_000_000), "large.txt", coverage)
        self.assertEqual(coverage.errors, ["publication-proof-failed"])
        self.assertEqual(policy.decisions[0]["decision"], "deny")

    def test_grading_full_local_history_has_no_spurious_coverage_errors(self) -> None:
        self.repository.write("file.txt", "clean\n")
        self.repository.commit_all("root")
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, payload)
        self.assertEqual(payload["verdict"], "clean")
        history = next(item for item in payload["coverage"] if item["source"] == "branch-history")
        self.assertEqual(history["base"], "all-reachable")
        self.assertEqual(history["errors"], [])

    def test_grading_matrix_preserves_publication_floor(self) -> None:
        helper = load_helper_module()
        self.assertTrue(callable(getattr(helper, "finding_grade", None)))
        benign = {"bead-reference", "ai-attribution", "suppression-attempt"}
        for category in ("secret", "session-link", "personal-data", *sorted(benign)):
            for publication in ("working-tree", "branch-history", "already-published"):
                for visibility in ("private", "public", "unknown"):
                    for confidence in ("high", "medium", "low"):
                        with self.subTest(category=category, publication=publication,
                                          visibility=visibility, confidence=confidence):
                            item = helper.finding(
                                category=category, detector="fixture.rule", severity="high",
                                confidence=confidence, source="working-tree", path="file.txt",
                            )
                            item["location"]["publication"] = publication
                            expected = "block"
                            if publication == "already-published" and (visibility == "private" or category in benign):
                                expected = "advisory"
                            self.assertEqual(helper.finding_grade(item, visibility), expected)
                            item["severity"] = "critical"
                            self.assertEqual(helper.finding_grade(item, visibility), "block")
        item = helper.finding(
            category="suppression-attempt", detector="scanner.inline-allow", severity="info",
            confidence="high", source="working-tree", path="file.txt",
        )
        self.assertEqual(helper.finding_grade(item, "unknown"), "advisory")
        for field, value in (("category", "future-category"), ("severity", "invalid"), ("confidence", "invalid")):
            invalid = {**item, field: value}
            self.assertEqual(helper.finding_grade(invalid, "private"), "block")
        self.assertEqual(helper.finding_grade(item, "invalid"), "block")
        item["location"]["publication"] = "unknown"
        self.assertEqual(helper.finding_grade(item, "private"), "block")

    def test_graded_private_published_secret_is_visible_advisory(self) -> None:
        self.repository.write("key.txt", "FINDING_MARKER\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.run("config", "--local", "artifactHygiene.remoteVisibility", "private")
        before = self.repository.state()
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, payload)
        self.assertEqual(payload["schemaVersion"], "artifact-hygiene/v2")
        self.assertEqual(payload["verdict"], "advisory")
        self.assertEqual(payload["target"]["remoteVisibility"], "private")
        self.assertIn("remote-visibility-private", payload["target"]["policy"])
        self.assertEqual(len(payload["findings"]), 1)
        item = payload["findings"][0]
        self.assertEqual(item["policy"]["grade"], "advisory")
        self.assertNotIn("decision", item["policy"])
        self.assertEqual(item["severity"], "high")
        self.assertEqual(item["location"]["publication"], "already-published")
        self.assertEqual(item["location"]["blobId"], self.repository.run("rev-parse", "HEAD:key.txt").strip())
        self.assertEqual(self.repository.state(), before)
        self.assertNotIn("FINDING_MARKER", completed.stdout)

    def test_graded_new_and_index_only_secrets_still_block_private(self) -> None:
        self.repository.write("key.txt", "OLD_FINDING_MARKER\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.run("config", "--local", "artifactHygiene.remoteVisibility", "private")
        self.repository.write("key.txt", "NEW_FINDING_MARKER\n")
        self.repository.run("add", "key.txt")
        self.repository.write("key.txt", "OLD_FINDING_MARKER\n")
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, payload)
        self.assertEqual(payload["verdict"], "block")
        self.assertEqual({item["policy"]["grade"] for item in payload["findings"]}, {"advisory", "block"})
        self.assertEqual({item["location"]["publication"] for item in payload["findings"]}, {"already-published", "working-tree"})
        self.repository.run("commit", "-m", "local key")
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["verdict"], "block")
        historical = [item for item in payload["findings"] if item["location"]["source"] == "branch-history"]
        self.assertTrue(historical)
        self.assertTrue(all(item["policy"]["grade"] == "block" for item in historical))

    def test_grading_does_not_deduplicate_new_index_content_against_published_file(self) -> None:
        self.repository.write("link.txt", SHARE_LINK + "original\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.run("config", "--local", "artifactHygiene.remoteVisibility", "private")
        self.repository.write("link.txt", SHARE_LINK + "new\n")
        self.repository.run("add", "link.txt")
        self.repository.write("link.txt", SHARE_LINK + "original\n")
        completed = self.run_audit()
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, payload)
        self.assertEqual(payload["verdict"], "block")
        links = [item for item in payload["findings"] if item["category"] == "session-link"]
        self.assertEqual(len(links), 2)
        self.assertEqual({item["policy"]["grade"] for item in links}, {"advisory", "block"})
        self.assertEqual(len({item["occurrenceId"] for item in links}), 2)

    def test_graded_visibility_is_clone_local_only(self) -> None:
        self.repository.write("key.txt", "FINDING_MARKER\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        config = self.repository.write("visibility.config", "[artifactHygiene]\nremoteVisibility = private\n")
        self.repository.run("config", "--local", "include.path", str(config))
        for visibility in (None, "public", "invalid", "private"):
            with self.subTest(visibility=visibility):
                if visibility:
                    self.repository.run("config", "--local", "artifactHygiene.remoteVisibility", visibility)
                completed = self.run_audit(extra_environment={
                    "ARTIFACT_HYGIENE_REMOTE_VISIBILITY": "private",
                    "GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "artifactHygiene.remoteVisibility", "GIT_CONFIG_VALUE_0": "private",
                })
                payload = json.loads(completed.stdout)
                self.assertEqual(completed.returncode, 0, payload)
                expected = "private" if visibility == "private" else "public" if visibility == "public" else "unknown"
                self.assertEqual(payload["target"]["remoteVisibility"], expected)
                self.assertEqual(payload["verdict"], "advisory" if expected == "private" else "block")

    def test_graded_incomplete_sources_override_advisory(self) -> None:
        helper = load_helper_module()
        self.assertTrue(callable(getattr(helper, "graded_verdict", None)))
        advisory = [{"policy": {"grade": "advisory"}}]
        for status in ("partial", "failed", "unknown"):
            self.assertEqual(helper.graded_verdict(advisory, status), "block")
            self.assertEqual(helper.graded_verdict([], status), "block")
        self.assertEqual(helper.graded_verdict([], "complete"), "clean")
        self.assertEqual(helper.graded_verdict(advisory, "complete"), "advisory")
        self.assertEqual(helper.graded_verdict([{"policy": {"grade": "block"}}], "complete"), "block")
        self.repository.write("key.txt", "FINDING_MARKER\n")
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.run("config", "--local", "artifactHygiene.remoteVisibility", "private")
        completed = self.run_audit(scanner=self.noop_gitleaks)
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 2, payload)
        self.assertEqual(payload["verdict"], "block")

    def test_history_scanner_failure_is_partial_and_never_leaks_child_error(self) -> None:
        self.prepare_coverage_repository()

        completed = self.run_audit(fake_mode="fail-history")

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["verdict"], "block")
        history = next(item for item in payload["coverage"] if item["source"] == "branch-history")
        self.assertEqual(history["status"], "partial")
        self.assertIn("scanner-failed", history["errors"])
        self.assertNotIn("RAW_CHILD_ERROR", completed.stdout)

    @unittest.skipUnless(shutil.which("gitleaks"), "gitleaks is not installed")
    def test_missing_remote_base_scans_all_messages_and_patches(self) -> None:
        history_key = "".join(("AKIA", "ABCDEFGHIJKLMNOP"))
        message_key = "".join(("AKIA", "QRSTUVWXYZABCDEF"))
        session_url = SHARE_LINK + "HISTORY_SESSION_SENTINEL"
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
        self.assertEqual(history["errors"], [])
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
        session_findings = [
            item
            for item in history_findings
            if item["category"] == "session-link"
            and item["location"]["path"] == "history-only.txt"
        ]
        # Reported once, for the commit that added it; the removal patch is not re-reported.
        self.assertEqual(len(session_findings), 1, session_findings)
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
            f"aws_access_key_id = {access_key} # {ALLOW_CONTROL}\n",
        )
        self.repository.commit_all("base")
        self.repository.mark_base()
        self.repository.run("switch", "-c", "feature")
        self.repository.write(
            "feature.txt",
            f"aws_access_key_id = {branch_key} # {ALLOW_CONTROL}\n",
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
