#!/usr/bin/env python3
"""Read-only local artifact-hygiene proof of concept."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import Any, Iterable
from urllib.parse import urlsplit

SCHEMA_VERSION = "artifact-hygiene/v1"
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
GITLEAKS_CONFIG = SKILL_ROOT / "references" / "gitleaks.toml"
DEFAULT_TIMEOUT_SECONDS = 120.0
MAX_COMMAND_OUTPUT_BYTES = 4_000_000
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 50_000_000
MAX_RECORDS = 100_000

OBJECT_ID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
RULE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
SAFE_REF = re.compile(r"^refs/[A-Za-z0-9._/-]+$")
SAFE_REMOTE_PART = re.compile(r"^[A-Za-z0-9._-]+$")
SESSION_LINK = re.compile(
    rb"https?://(?:chatgpt\.com/share|claude\.ai/share)/[^\s<>\"']+",
    re.IGNORECASE,
)
INLINE_GITLEAKS_ALLOW = re.compile(rb"gitleaks\s*:\s*allow", re.IGNORECASE)
SUPPRESSION_FILES = {".gitleaks.toml", ".gitleaksignore"}


class AuditError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CommandResult:
    stdout: bytes
    returncode: int


@dataclass(frozen=True)
class Candidate:
    path: str
    data: bytes


@dataclass
class Coverage:
    source: str
    status: str = "complete"
    records: int = 0
    bytes: int = 0
    base: str | None = None
    errors: list[str] = field(default_factory=list)

    def partial(self, code: str) -> None:
        self.status = "partial"
        if code not in self.errors:
            self.errors.append(code)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "source": self.source,
            "status": self.status,
            "records": self.records,
            "bytes": self.bytes,
            "limits": [],
            "errors": self.errors,
        }
        if self.base is not None:
            result["base"] = self.base
        return result


class BoundedRunner:
    def __init__(self, deadline: float) -> None:
        self.deadline = deadline

    def run(
        self,
        args: list[str],
        *,
        cwd: Path,
        input_bytes: bytes | None = None,
        allowed_returncodes: Iterable[int] = (0,),
        environment_overrides: dict[str, str] | None = None,
    ) -> CommandResult:
        if monotonic() >= self.deadline:
            raise AuditError("command-timeout")
        environment = sanitized_environment()
        if environment_overrides:
            environment.update(environment_overrides)
        try:
            process = subprocess.Popen(
                args,
                cwd=cwd,
                env=environment,
                stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as error:
            raise AuditError("command-unavailable") from error

        assert process.stdout is not None and process.stderr is not None
        os.set_blocking(process.stdout.fileno(), False)
        os.set_blocking(process.stderr.fileno(), False)
        if process.stdin is not None:
            os.set_blocking(process.stdin.fileno(), False)
        output = bytearray()
        error_output = bytearray()
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, output)
        selector.register(process.stderr, selectors.EVENT_READ, error_output)
        input_view = memoryview(input_bytes or b"")
        input_offset = 0
        if process.stdin is not None:
            if input_view:
                selector.register(process.stdin, selectors.EVENT_WRITE)
            else:
                process.stdin.close()

        def kill_process_group() -> None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.poll() is None:
                process.wait()

        try:
            while selector.get_map():
                remaining = self.deadline - monotonic()
                if remaining <= 0:
                    kill_process_group()
                    raise AuditError("command-timeout")
                events = selector.select(min(remaining, 0.25))
                for key, mask in events:
                    if mask & selectors.EVENT_WRITE:
                        try:
                            written = os.write(
                                key.fd,
                                input_view[input_offset : input_offset + 65_536],
                            )
                        except BlockingIOError:
                            continue
                        except BrokenPipeError:
                            written = len(input_view) - input_offset
                        input_offset += written
                        if input_offset >= len(input_view):
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                        continue

                    try:
                        chunk = os.read(key.fd, 65_536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    key.data.extend(chunk)
                    if len(output) + len(error_output) > MAX_COMMAND_OUTPUT_BYTES:
                        kill_process_group()
                        raise AuditError("command-output-limit")
            returncode = process.wait()
        finally:
            selector.close()
            kill_process_group()
            process.stdout.close()
            process.stderr.close()
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()

        if returncode not in set(allowed_returncodes):
            raise AuditError("command-failed")
        return CommandResult(bytes(output), returncode)


def process_path() -> str:
    entries = [
        entry
        for entry in os.environ.get("PATH", os.defpath).split(os.pathsep)
        if entry and os.path.isabs(entry)
    ]
    return os.pathsep.join(dict.fromkeys(entries)) or os.defpath


def resolve_executable(value: str, repository: Path | None = None) -> str | None:
    candidate = value if os.path.isabs(value) else shutil.which(value, path=process_path())
    if not candidate:
        return None
    try:
        resolved = Path(candidate).resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        return None
    if repository is not None and resolved.is_relative_to(repository):
        raise AuditError("untrusted-executable")
    return str(resolved)


def sanitized_environment() -> dict[str, str]:
    environment = {"PATH": process_path()}
    if "SYSTEMROOT" in os.environ:
        environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    environment.update(
        {
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "cat",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
            "NO_COLOR": "1",
            "PAGER": "cat",
        }
    )
    return environment


def git(
    runner: BoundedRunner,
    repository: Path,
    *arguments: str,
    allowed_returncodes: Iterable[int] = (0,),
) -> CommandResult:
    executable = resolve_executable("git", repository)
    if executable is None:
        raise AuditError("git-unavailable")
    try:
        return runner.run(
            [
                executable,
                "--no-pager",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                "-c",
                "submodule.recurse=false",
                *arguments,
            ],
            cwd=repository,
            allowed_returncodes=allowed_returncodes,
        )
    except AuditError as error:
        if error.code == "command-unavailable":
            raise AuditError("git-unavailable") from error
        raise


def decode_text(value: bytes) -> str:
    return value.decode("utf-8", "replace").strip()


def safe_path(value: str) -> str | None:
    normalized = value.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if not normalized or pure.is_absolute() or ".." in pure.parts:
        return None
    sanitized = "".join(
        "?" if ord(character) < 32 or ord(character) == 127 else character
        for character in normalized
    )
    return sanitized[:500] or None


def safe_ref(value: str) -> str | None:
    return value if SAFE_REF.fullmatch(value) and ".." not in value else None


def occurrence_id(
    category: str,
    source: str,
    path: str,
    line: int | None,
    commit: str | None,
    detector: str,
) -> str:
    material = json.dumps(
        [category, source, path, line, commit, detector],
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "occ:" + hashlib.sha256(material.encode("ascii")).hexdigest()[:24]


def finding(
    *,
    category: str,
    detector: str,
    severity: str,
    confidence: str,
    source: str,
    path: str,
    line: int | None = None,
    commit: str | None = None,
    field_name: str | None = None,
) -> dict[str, Any]:
    evidence_tokens = {
        "secret": "[REDACTED:SECRET]",
        "session-link": "[REDACTED:SESSION-LINK]",
        "suppression-attempt": "[REDACTED:SUPPRESSION-CONTROL]",
    }
    remediation = {
        "secret": "Remove or rotate the credential before publication, then rerun the audit.",
        "session-link": "Remove the private session link or replace it with approved public context.",
        "suppression-attempt": "Review the scanner control; repository controls cannot suppress this audit.",
    }
    decision = "review" if category == "suppression-attempt" else "deny"
    return {
        "occurrenceId": occurrence_id(
            category, source, path, line, commit, detector
        ),
        "familyId": "family:"
        + hashlib.sha256(
            json.dumps([category, detector, path], separators=(",", ":")).encode()
        ).hexdigest()[:20],
        "detector": detector,
        "category": category,
        "severity": severity,
        "confidence": confidence,
        "location": {
            "source": source,
            "path": path,
            "commit": commit,
            "field": field_name,
            "line": line,
        },
        "evidence": {"token": evidence_tokens[category]},
        "policy": {"rule": detector, "decision": decision, "override": None},
        "remediation": remediation[category],
    }


def resolve_repository(runner: BoundedRunner, target: Path) -> tuple[Path, str | None]:
    if not target.exists() or not target.is_dir():
        raise AuditError("repository-unavailable")
    try:
        root_result = git(runner, target, "rev-parse", "--show-toplevel")
    except AuditError as error:
        raise AuditError("not-git-repository") from error
    root_text = decode_text(root_result.stdout)
    if not root_text:
        raise AuditError("not-git-repository")
    root = Path(root_text).resolve()
    head_result = git(
        runner,
        root,
        "rev-parse",
        "--verify",
        "HEAD",
        allowed_returncodes=(0, 1, 128),
    )
    head_text = decode_text(head_result.stdout)
    head = head_text if OBJECT_ID.fullmatch(head_text) else None
    return root, head


def repository_identity(runner: BoundedRunner, repository: Path) -> str:
    result = git(
        runner,
        repository,
        "config",
        "--get",
        "remote.origin.url",
        allowed_returncodes=(0, 1),
    )
    raw = decode_text(result.stdout)
    if not raw:
        return "local-repository"
    host = ""
    path = ""
    if raw.startswith("git@") and ":" in raw:
        host, path = raw[4:].split(":", 1)
    else:
        parsed = urlsplit(raw)
        host = parsed.hostname or ""
        path = parsed.path.lstrip("/")
    parts = path.removesuffix(".git").split("/")
    if (
        SAFE_REMOTE_PART.fullmatch(host)
        and len(parts) == 2
        and all(SAFE_REMOTE_PART.fullmatch(part) for part in parts)
    ):
        return f"{host.lower()}/{parts[0]}/{parts[1]}"
    return "local-repository"


def repository_state(
    runner: BoundedRunner, repository: Path
) -> tuple[bytes, bytes, bytes]:
    head = git(
        runner,
        repository,
        "rev-parse",
        "--verify",
        "HEAD",
        allowed_returncodes=(0, 1, 128),
    ).stdout
    status = git(
        runner,
        repository,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ).stdout
    refs = git(
        runner,
        repository,
        "show-ref",
        "--head",
        allowed_returncodes=(0, 1),
    ).stdout
    return head, status, refs


def read_candidate(repository: Path, relative: str) -> bytes | None:
    target = repository / relative
    try:
        initial = target.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise AuditError("file-read-failed") from error
    if not stat.S_ISREG(initial.st_mode):
        return None

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
    except OSError as error:
        raise AuditError("file-read-failed") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return None
        if (initial.st_dev, initial.st_ino) != (before.st_dev, before.st_ino):
            raise AuditError("file-changed")
        if before.st_size > MAX_FILE_BYTES:
            raise AuditError("file-too-large")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
        after = os.fstat(descriptor)
        if len(data) > MAX_FILE_BYTES:
            raise AuditError("file-too-large")
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise AuditError("file-changed")
        return data
    finally:
        os.close(descriptor)


def collect_candidates(
    runner: BoundedRunner,
    repository: Path,
    coverage: Coverage,
) -> list[Candidate]:
    result = git(
        runner,
        repository,
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
    )
    raw_paths = sorted(set(filter(None, result.stdout.split(b"\0"))))
    if len(raw_paths) > MAX_RECORDS:
        coverage.partial("record-limit")
        raw_paths = raw_paths[:MAX_RECORDS]

    candidates: list[Candidate] = []
    total_bytes = 0
    for raw_path in raw_paths:
        decoded = os.fsdecode(raw_path).replace("\\", "/")
        relative = safe_path(decoded)
        if relative is None or relative != decoded:
            coverage.partial("unsafe-path")
            continue
        if relative == ".artifacts" or relative.startswith(".artifacts/"):
            continue
        try:
            data = read_candidate(repository, relative)
        except AuditError as error:
            coverage.partial(error.code)
            continue
        if data is None or b"\0" in data:
            continue
        if total_bytes + len(data) > MAX_TOTAL_BYTES:
            coverage.partial("byte-limit")
            break
        total_bytes += len(data)
        candidates.append(Candidate(relative, data))
    indexed = git(runner, repository, "ls-files", "--stage", "-z")
    index_records = list(filter(None, indexed.stdout.split(b"\0")))
    if len(index_records) > MAX_RECORDS:
        coverage.partial("record-limit")
        index_records = index_records[:MAX_RECORDS]
    seen = {
        (candidate.path, hashlib.sha256(candidate.data).digest())
        for candidate in candidates
    }
    for record in index_records:
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_id, stage = metadata.split(b" ", 2)
        except ValueError:
            coverage.partial("index-invalid-output")
            continue
        if stage != b"0":
            coverage.partial("unmerged-index")
            continue
        if mode not in {b"100644", b"100755"}:
            continue
        object_text = object_id.decode("ascii", "ignore")
        if not OBJECT_ID.fullmatch(object_text):
            coverage.partial("index-invalid-output")
            continue
        decoded = os.fsdecode(raw_path).replace("\\", "/")
        relative = safe_path(decoded)
        if relative is None or relative != decoded:
            coverage.partial("unsafe-path")
            continue
        if relative == ".artifacts" or relative.startswith(".artifacts/"):
            continue
        try:
            size_result = git(runner, repository, "cat-file", "-s", object_text)
            size = int(decode_text(size_result.stdout))
            if size > MAX_FILE_BYTES:
                coverage.partial("file-too-large")
                continue
            blob = git(runner, repository, "cat-file", "blob", object_text).stdout
        except (AuditError, ValueError):
            coverage.partial("index-read-failed")
            continue
        if len(blob) != size:
            coverage.partial("index-read-failed")
            continue
        if b"\0" in blob:
            continue
        key = (relative, hashlib.sha256(blob).digest())
        if key in seen:
            continue
        if total_bytes + len(blob) > MAX_TOTAL_BYTES:
            coverage.partial("byte-limit")
            break
        seen.add(key)
        total_bytes += len(blob)
        candidates.append(Candidate(relative, blob))

    coverage.records = len(candidates)
    coverage.bytes = total_bytes
    return candidates


def safe_temp_parent(repository: Path) -> Path:
    candidates = [Path(tempfile.gettempdir()), Path("/tmp"), Path("/var/tmp")]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if (
            resolved.is_dir()
            and os.access(resolved, os.W_OK | os.X_OK)
            and not resolved.is_relative_to(repository)
        ):
            return resolved
    raise AuditError("safe-temp-unavailable")


def scanner_version(
    runner: BoundedRunner, repository: Path, executable: str
) -> str | None:
    try:
        result = runner.run([executable, "version"], cwd=repository)
    except AuditError:
        return None
    match = re.search(rb"\b([0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?)\b", result.stdout)
    return match.group(1).decode("ascii") if match else "unknown"


def scanner_arguments(
    executable: str,
    mode: str,
    ignore_path: Path,
    deadline: float,
) -> list[str]:
    timeout = max(1, int(deadline - monotonic()))
    return [
        executable,
        mode,
        "--config",
        str(GITLEAKS_CONFIG),
        "--gitleaks-ignore-path",
        str(ignore_path),
        "--ignore-gitleaks-allow",
        "--redact=100",
        "--report-format",
        "json",
        "--report-path",
        "-",
        "--no-banner",
        "--no-color",
        "--log-level",
        "error",
        "--timeout",
        str(timeout),
    ]


def normalized_rule(value: Any) -> str:
    return value if isinstance(value, str) and RULE_ID.fullmatch(value) else "unknown-rule"


def normalized_line(value: Any) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def parse_scanner_findings(
    output: bytes,
    *,
    source: str,
    fallback_path: str | None,
    fallback_commit: str | None = None,
    field_name: str | None = None,
) -> list[dict[str, Any]]:
    try:
        payload = json.loads(output.decode("utf-8", "replace") or "[]")
    except json.JSONDecodeError as error:
        raise AuditError("scanner-invalid-output") from error
    if not isinstance(payload, list):
        raise AuditError("scanner-invalid-output")

    results: list[dict[str, Any]] = []
    for record in payload:
        if not isinstance(record, dict):
            raise AuditError("scanner-invalid-output")
        path = fallback_path
        if path is None and isinstance(record.get("File"), str):
            path = safe_path(record["File"])
        if path is None:
            path = "[path-unavailable]"
        commit_value = record.get("Commit")
        commit = (
            commit_value
            if isinstance(commit_value, str) and OBJECT_ID.fullmatch(commit_value)
            else fallback_commit
        )
        rule = normalized_rule(record.get("RuleID"))
        results.append(
            finding(
                category="secret",
                detector=f"gitleaks.{rule}",
                severity="high",
                confidence="high",
                source=source,
                path=path,
                line=normalized_line(record.get("StartLine")),
                commit=commit,
                field_name=field_name,
            )
        )
    return results


def scanner_capability_probe(
    runner: BoundedRunner,
    repository: Path,
    executable: str,
    ignore_path: Path,
    deadline: float,
    environment: dict[str, str],
) -> bool:
    alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    random_bytes = secrets.token_bytes(16)
    suffix = bytes(alphabet[value % len(alphabet)] for value in random_bytes)
    canary = b"aws_access_key_id = " + b"AKIA" + suffix + b"\n"
    try:
        result = runner.run(
            scanner_arguments(executable, "stdin", ignore_path, deadline),
            cwd=repository,
            input_bytes=canary,
            allowed_returncodes=(0, 1),
            environment_overrides=environment,
        )
        findings = parse_scanner_findings(
            result.stdout,
            source="capability-probe",
            fallback_path="[capability-probe]",
        )
    except AuditError:
        return False
    return result.returncode == 1 and bool(findings)


def detect_non_secret(
    data: bytes,
    *,
    source: str,
    path: str,
    commit: str | None = None,
    field_name: str | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for match in SESSION_LINK.finditer(data):
        line = data.count(b"\n", 0, match.start()) + 1
        results.append(
            finding(
                category="session-link",
                detector="session.share-link",
                severity="high",
                confidence="high",
                source=source,
                path=path,
                line=line,
                commit=commit,
                field_name=field_name,
            )
        )
    if PurePosixPath(path).name in SUPPRESSION_FILES:
        results.append(
            finding(
                category="suppression-attempt",
                detector="scanner.repository-control",
                severity="info",
                confidence="high",
                source=source,
                path=path,
                commit=commit,
                field_name=field_name,
            )
        )
    for match in INLINE_GITLEAKS_ALLOW.finditer(data):
        line = data.count(b"\n", 0, match.start()) + 1
        results.append(
            finding(
                category="suppression-attempt",
                detector="scanner.inline-allow",
                severity="info",
                confidence="high",
                source=source,
                path=path,
                line=line,
                commit=commit,
                field_name=field_name,
            )
        )
    return results


def resolve_history_range(
    runner: BoundedRunner, repository: Path, coverage: Coverage
) -> str | None:
    head_result = git(
        runner,
        repository,
        "rev-parse",
        "--verify",
        "HEAD",
        allowed_returncodes=(0, 1, 128),
    )
    head = decode_text(head_result.stdout)
    if not OBJECT_ID.fullmatch(head):
        coverage.base = "unborn"
        return None

    candidates: list[str] = []
    symbolic = git(
        runner,
        repository,
        "symbolic-ref",
        "--quiet",
        "refs/remotes/origin/HEAD",
        allowed_returncodes=(0, 1),
    )
    symbolic_ref = safe_ref(decode_text(symbolic.stdout))
    if symbolic_ref:
        candidates.append(symbolic_ref)
    candidates.extend(
        [
            "refs/remotes/origin/main",
            "refs/remotes/origin/master",
        ]
    )

    base_ref: str | None = None
    for candidate in dict.fromkeys(candidates):
        verified = git(
            runner,
            repository,
            "rev-parse",
            "--verify",
            "--quiet",
            f"{candidate}^{{commit}}",
            allowed_returncodes=(0, 1),
        )
        candidate_oid = decode_text(verified.stdout)
        if not OBJECT_ID.fullmatch(candidate_oid):
            continue
        base_ref = candidate
        break

    if base_ref is None:
        coverage.base = "all-reachable"
        if "base-fallback-all-reachable" not in coverage.errors:
            coverage.errors.append("base-fallback-all-reachable")
        return "HEAD --no-ext-diff --no-textconv"

    merge_base = git(
        runner,
        repository,
        "merge-base",
        base_ref,
        "HEAD",
        allowed_returncodes=(0, 1),
    )
    merge = decode_text(merge_base.stdout)
    if not OBJECT_ID.fullmatch(merge):
        coverage.base = "all-reachable"
        if "base-fallback-all-reachable" not in coverage.errors:
            coverage.errors.append("base-fallback-all-reachable")
        return "HEAD --no-ext-diff --no-textconv"
    coverage.base = base_ref
    return f"{merge}..HEAD --no-ext-diff --no-textconv"


def history_commits(
    runner: BoundedRunner,
    repository: Path,
    log_options: str,
    coverage: Coverage,
) -> list[str]:
    revision = log_options.split(" ", 1)[0]
    result = git(runner, repository, "rev-list", "--reverse", revision)
    commits = [line for line in decode_text(result.stdout).splitlines() if line]
    if any(not OBJECT_ID.fullmatch(commit) for commit in commits):
        raise AuditError("git-invalid-output")
    if len(commits) > MAX_RECORDS:
        coverage.partial("record-limit")
        commits = commits[:MAX_RECORDS]
    coverage.records = len(commits)
    return commits


def commit_message(
    runner: BoundedRunner,
    repository: Path,
    commit: str,
) -> bytes:
    size = int(decode_text(git(runner, repository, "cat-file", "-s", commit).stdout))
    if size > MAX_FILE_BYTES:
        raise AuditError("history-record-too-large")
    raw_commit = git(runner, repository, "cat-file", "commit", commit).stdout
    if len(raw_commit) != size:
        raise AuditError("history-read-failed")
    parts = raw_commit.split(b"\n\n", 1)
    return parts[1] if len(parts) == 2 else b""


def commit_paths(
    runner: BoundedRunner,
    repository: Path,
    commit: str,
    coverage: Coverage,
) -> list[str]:
    output = git(
        runner,
        repository,
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--name-only",
        "-z",
        "-r",
        "-m",
        commit,
    ).stdout
    paths: list[str] = []
    for raw_path in dict.fromkeys(filter(None, output.split(b"\0"))):
        decoded = os.fsdecode(raw_path).replace("\\", "/")
        path = safe_path(decoded)
        if path is None or path != decoded:
            coverage.partial("unsafe-path")
            continue
        paths.append(path)
        if len(paths) >= MAX_RECORDS:
            coverage.partial("record-limit")
            break
    return paths


def commit_patch(
    runner: BoundedRunner,
    repository: Path,
    commit: str,
    path: str,
) -> bytes:
    return git(
        runner,
        repository,
        "show",
        "-m",
        "--format=",
        "--no-ext-diff",
        "--no-textconv",
        "--unified=0",
        "--no-renames",
        commit,
        "--",
        path,
    ).stdout


def scan_history_records(
    runner: BoundedRunner,
    repository: Path,
    commits: list[str],
    executable: str,
    ignore_path: Path,
    deadline: float,
    environment: dict[str, str],
    coverage: Coverage,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    total_bytes = 0
    path_records = 0
    for commit in commits:
        try:
            message = commit_message(runner, repository, commit)
        except (AuditError, ValueError):
            coverage.partial("history-read-failed")
            break
        if total_bytes + len(message) > MAX_TOTAL_BYTES:
            coverage.partial("byte-limit")
            break
        total_bytes += len(message)
        findings.extend(
            detect_non_secret(
                message,
                source="branch-history",
                path="[commit-message]",
                commit=commit,
                field_name="message",
            )
        )
        try:
            result = runner.run(
                scanner_arguments(executable, "stdin", ignore_path, deadline),
                cwd=repository,
                input_bytes=message,
                allowed_returncodes=(0, 1),
                environment_overrides=environment,
            )
            findings.extend(
                parse_scanner_findings(
                    result.stdout,
                    source="branch-history",
                    fallback_path="[commit-message]",
                    fallback_commit=commit,
                    field_name="message",
                )
            )
        except AuditError as error:
            coverage.partial(
                "scanner-invalid-output"
                if error.code == "scanner-invalid-output"
                else "scanner-failed"
            )
            break

        try:
            paths = commit_paths(runner, repository, commit, coverage)
        except AuditError:
            coverage.partial("history-read-failed")
            break
        for path in paths:
            path_records += 1
            if path_records > MAX_RECORDS:
                coverage.partial("record-limit")
                break
            try:
                patch = commit_patch(runner, repository, commit, path)
            except AuditError:
                coverage.partial("history-read-failed")
                break
            if total_bytes + len(patch) > MAX_TOTAL_BYTES:
                coverage.partial("byte-limit")
                break
            total_bytes += len(patch)
            findings.extend(
                detect_non_secret(
                    patch,
                    source="branch-history",
                    path=path,
                    commit=commit,
                )
            )
            try:
                result = runner.run(
                    scanner_arguments(executable, "stdin", ignore_path, deadline),
                    cwd=repository,
                    input_bytes=patch,
                    allowed_returncodes=(0, 1),
                    environment_overrides=environment,
                )
                findings.extend(
                    parse_scanner_findings(
                        result.stdout,
                        source="branch-history",
                        fallback_path=path,
                        fallback_commit=commit,
                    )
                )
            except AuditError as error:
                coverage.partial(
                    "scanner-invalid-output"
                    if error.code == "scanner-invalid-output"
                    else "scanner-failed"
                )
                break
        if coverage.status == "partial":
            break
    coverage.bytes = total_bytes
    return findings


def scan(
    repository: Path,
    head: str | None,
    executable: str,
    timeout_seconds: float,
) -> tuple[dict[str, Any], int]:
    deadline = monotonic() + timeout_seconds
    runner = BoundedRunner(deadline)
    identity = repository_identity(runner, repository)
    state_before = repository_state(runner, repository)
    working = Coverage("working-tree")
    history = Coverage("branch-history")
    candidates = collect_candidates(runner, repository, working)
    findings: list[dict[str, Any]] = []
    for candidate in candidates:
        findings.extend(
            detect_non_secret(
                candidate.data,
                source="working-tree",
                path=candidate.path,
            )
        )

    scanner_version_value = scanner_version(runner, repository, executable)
    with tempfile.TemporaryDirectory(
        prefix="artifact-hygiene-", dir=safe_temp_parent(repository)
    ) as temporary:
        temporary_root = Path(temporary)
        temporary_root.chmod(0o700)
        ignore_path = temporary_root / ".gitleaksignore"
        ignore_path.write_text("", encoding="utf-8")
        ignore_path.chmod(0o600)
        scanner_environment = {
            "TMPDIR": str(temporary_root),
            "TMP": str(temporary_root),
            "TEMP": str(temporary_root),
        }

        scanner_ready = (
            scanner_version_value is not None
            and GITLEAKS_CONFIG.is_file()
            and scanner_capability_probe(
                runner,
                repository,
                executable,
                ignore_path,
                deadline,
                scanner_environment,
            )
        )
        if not scanner_ready:
            working.partial("scanner-unavailable")
            history.partial("scanner-unavailable")
        else:
            for candidate in candidates:
                try:
                    result = runner.run(
                        scanner_arguments(
                            executable, "stdin", ignore_path, deadline
                        ),
                        cwd=repository,
                        input_bytes=candidate.data,
                        allowed_returncodes=(0, 1),
                        environment_overrides=scanner_environment,
                    )
                    findings.extend(
                        parse_scanner_findings(
                            result.stdout,
                            source="working-tree",
                            fallback_path=candidate.path,
                        )
                    )
                except AuditError as error:
                    working.partial(
                        "scanner-invalid-output"
                        if error.code == "scanner-invalid-output"
                        else "scanner-failed"
                    )
                    break

            try:
                log_options = resolve_history_range(runner, repository, history)
                commits = (
                    history_commits(runner, repository, log_options, history)
                    if log_options is not None
                    else []
                )
            except AuditError:
                history.partial("history-read-failed")
                commits = []
                log_options = None

            if log_options is not None and commits:
                try:
                    arguments = scanner_arguments(
                        executable, "git", ignore_path, deadline
                    )
                    arguments.extend(["--log-opts", log_options, "."])
                    result = runner.run(
                        arguments,
                        cwd=repository,
                        allowed_returncodes=(0, 1),
                        environment_overrides=scanner_environment,
                    )
                    findings.extend(
                        parse_scanner_findings(
                            result.stdout,
                            source="branch-history",
                            fallback_path=None,
                        )
                    )
                except AuditError as error:
                    history.partial(
                        "scanner-invalid-output"
                        if error.code == "scanner-invalid-output"
                        else "scanner-failed"
                    )
                if history.status == "complete":
                    findings.extend(
                        scan_history_records(
                            runner,
                            repository,
                            commits,
                            executable,
                            ignore_path,
                            deadline,
                            scanner_environment,
                            history,
                        )
                    )

    try:
        if repository_state(runner, repository) != state_before:
            working.partial("repository-changed")
            history.partial("repository-changed")
    except AuditError:
        working.partial("state-recheck-failed")
        history.partial("state-recheck-failed")

    unique_findings = {item["occurrenceId"]: item for item in findings}
    ordered_findings = sorted(
        unique_findings.values(),
        key=lambda item: (
            item["location"]["source"],
            item["location"]["path"],
            item["location"]["line"] or 0,
            item["detector"],
        ),
    )
    coverages = [working, history]
    complete = all(item.status == "complete" for item in coverages)
    status = "complete" if complete else "partial"
    verdict = ("findings" if ordered_findings else "clean") if complete else "partial"
    summary = {level: 0 for level in ("critical", "high", "medium", "low", "info")}
    for item in ordered_findings:
        summary[item["severity"]] += 1
    summary["suppressed"] = 0
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": status,
        "verdict": verdict,
        "target": {
            "repository": identity,
            "head": head,
            "policy": "defaults",
        },
        "provenance": {
            "helperVersion": "0.1.0-poc",
            "secretScanner": {
                "name": "gitleaks",
                "version": scanner_version_value,
                "configSha256": "sha256:"
                + hashlib.sha256(GITLEAKS_CONFIG.read_bytes()).hexdigest()
                if GITLEAKS_CONFIG.is_file()
                else None,
            },
        },
        "coverage": [item.as_dict() for item in coverages],
        "findings": ordered_findings,
        "suppressed": [],
        "summary": summary,
    }
    return payload, 0 if complete else 2


def failed_payload(code: str) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "failed",
        "verdict": "failed",
        "target": {"repository": "unavailable", "head": None, "policy": "defaults"},
        "provenance": {
            "helperVersion": "0.1.0-poc",
            "secretScanner": {"name": "gitleaks", "version": None, "configSha256": None},
        },
        "coverage": [
            {
                "source": "repository",
                "status": "failed",
                "records": 0,
                "bytes": 0,
                "limits": [],
                "errors": [code],
            }
        ],
        "findings": [],
        "suppressed": [],
        "summary": {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "info": 0,
            "suppressed": 0,
        },
    }


def interrupted(_signum: int, _frame: Any) -> None:
    raise AuditError("interrupted")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the local read-only artifact-hygiene proof of concept."
    )
    parser.add_argument("repository", nargs="?", default=".")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    if not 1 <= arguments.timeout <= 600:
        payload = failed_payload("invalid-timeout")
        exit_code = 3
    else:
        initial_runner = BoundedRunner(monotonic() + arguments.timeout)
        handled_signals = [signal.SIGINT, signal.SIGTERM]
        previous_handlers = {
            handled_signal: signal.getsignal(handled_signal)
            for handled_signal in handled_signals
        }
        for handled_signal in handled_signals:
            signal.signal(handled_signal, interrupted)
        try:
            repository, head = resolve_repository(
                initial_runner, Path(arguments.repository).resolve()
            )
            scanner = resolve_executable("gitleaks", repository)
            payload, exit_code = scan(
                repository,
                head,
                scanner or "__artifact_hygiene_missing_gitleaks__",
                arguments.timeout,
            )
        except AuditError as error:
            payload = failed_payload(error.code)
            exit_code = 3
        except Exception:
            payload = failed_payload("internal-error")
            exit_code = 3
        finally:
            for handled_signal, previous_handler in previous_handlers.items():
                signal.signal(handled_signal, previous_handler)
    json.dump(
        payload,
        sys.stdout,
        indent=2 if arguments.pretty else None,
        sort_keys=True,
        separators=None if arguments.pretty else (",", ":"),
    )
    sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
