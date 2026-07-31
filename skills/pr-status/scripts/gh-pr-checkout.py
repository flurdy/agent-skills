#!/usr/bin/env python3
"""Find a clean exact-head GitHub checkout using bounded, read-only Git commands."""

from __future__ import annotations

import argparse
import json
import os
import re
import selectors
import signal
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from urllib.parse import urlparse

SCHEMA_VERSION = "gh-pr-checkout/v1"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_OUTPUT_BYTES = 1_000_000
MAX_CANDIDATES = 100
REPOSITORY_PATTERN = re.compile(r"^[^/\s]+/[^/\s]+$")
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")


class CommandRunner:
    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        self.deadline = monotonic() + max(0.1, timeout)
        self.max_output_bytes = max(1_000, max_output_bytes)
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_PAGER": "cat",
                "PAGER": "cat",
                "NO_COLOR": "1",
            }
        )

    @staticmethod
    def _group_exists(group_id: int) -> bool:
        try:
            os.killpg(group_id, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    @classmethod
    def _stop(cls, process: subprocess.Popen[bytes]) -> None:
        group_id = process.pid
        try:
            os.killpg(group_id, signal.SIGTERM)
        except ProcessLookupError:
            process.wait()
            return
        grace_deadline = monotonic() + 0.2
        while monotonic() < grace_deadline and cls._group_exists(group_id):
            sleep(0.01)
        if cls._group_exists(group_id):
            try:
                os.killpg(group_id, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait()

    def run(
        self, arguments: list[str], cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        if self.deadline - monotonic() <= 0:
            raise TimeoutError("checkout discovery deadline exceeded")
        process = subprocess.Popen(
            arguments,
            cwd=str(cwd) if cwd else None,
            env=self.environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        assert process.stdout and process.stderr
        streams = {process.stdout: [], process.stderr: []}
        selected = selectors.DefaultSelector()
        for stream in streams:
            selected.register(stream, selectors.EVENT_READ)
        total = 0
        try:
            while selected.get_map():
                remaining = self.deadline - monotonic()
                if remaining <= 0:
                    self._stop(process)
                    raise TimeoutError("checkout discovery deadline exceeded")
                events = selected.select(timeout=min(remaining, 0.1))
                if not events and process.poll() is not None:
                    events = [(key, selectors.EVENT_READ) for key in selected.get_map().values()]
                for key, _ in events:
                    chunk = os.read(key.fileobj.fileno(), 65_536)
                    if not chunk:
                        selected.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    total += len(chunk)
                    if total > self.max_output_bytes:
                        self._stop(process)
                        raise RuntimeError("checkout discovery output exceeded its limit")
                    streams[key.fileobj].append(chunk)
            return_code = process.wait(timeout=max(0.1, self.deadline - monotonic()))
        except subprocess.TimeoutExpired as error:
            self._stop(process)
            raise TimeoutError("checkout discovery deadline exceeded") from error
        finally:
            selected.close()
            for stream in streams:
                if not stream.closed:
                    stream.close()
        stdout = b"".join(streams[process.stdout]).decode(errors="replace")
        stderr = b"".join(streams[process.stderr]).decode(errors="replace")
        return subprocess.CompletedProcess(arguments, return_code, stdout, stderr)


def error_record(source: str, message: str, path: str | None = None) -> dict[str, str]:
    result = {"source": source, "message": message[:500]}
    if path:
        result["path"] = path
    return result


def github_repository(remote_url: str) -> str | None:
    value = remote_url.strip()
    scp = re.fullmatch(
        r"(?:[^@/:]+@)?github\.com:([^/\s]+)/([^/\s]+?)(?:\.git)?/?",
        value,
        flags=re.IGNORECASE,
    )
    if scp:
        repository = f"{scp.group(1)}/{scp.group(2)}"
        return repository if REPOSITORY_PATTERN.fullmatch(repository) else None

    parsed = urlparse(value if "://" in value else f"https://{value}")
    if parsed.hostname is None or parsed.hostname.casefold() != "github.com":
        return None
    if parsed.query or parsed.fragment or parsed.params:
        return None
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2:
        return None
    owner, repository = parts
    if repository.endswith(".git"):
        repository = repository[:-4]
    result = f"{owner}/{repository}"
    return result if REPOSITORY_PATTERN.fullmatch(result) else None


def parse_members(output: str) -> list[str]:
    root = None
    section = None
    members = []
    for line in output.splitlines():
        if line == "---ROOT---":
            section = "root"
            continue
        if line == "---REPOS---":
            section = "repos"
            continue
        if line.startswith("---"):
            section = None
            continue
        if section == "root":
            root = line
            section = None
        elif section == "repos" and root and line:
            members.append(str((Path(root) / line).resolve()))
    return members


def discover_candidate_paths(
    runner: CommandRunner, cwd: Path
) -> tuple[list[str], list[dict[str, str]]]:
    candidates = []
    errors = []
    try:
        current = runner.run(["git", "rev-parse", "--show-toplevel"], cwd)
        if current.returncode == 0 and current.stdout.strip():
            candidates.append(str(Path(current.stdout.strip()).resolve()))
    except (RuntimeError, TimeoutError) as error:
        errors.append(error_record("current-repository", str(error)))

    members_script = Path(__file__).parents[2] / "wrap-up" / "scripts" / "multirepo.sh"
    try:
        members = runner.run([str(members_script), "--members-only"], cwd)
        if members.returncode == 0:
            candidates.extend(parse_members(members.stdout))
        else:
            message = members.stderr.strip() or "workspace member discovery failed"
            errors.append(error_record("workspace-members", message))
    except (RuntimeError, TimeoutError) as error:
        errors.append(error_record("workspace-members", str(error)))

    return sorted(set(candidates))[:MAX_CANDIDATES], errors


def worktree_paths(
    runner: CommandRunner, seeds: list[str]
) -> tuple[list[str], list[dict[str, str]]]:
    paths = set()
    errors = []
    for seed in seeds[:MAX_CANDIDATES]:
        resolved = str(Path(seed).expanduser().resolve())
        try:
            result = runner.run(
                ["git", "-C", resolved, "worktree", "list", "--porcelain"]
            )
        except (RuntimeError, TimeoutError) as error:
            errors.append(error_record("worktrees", str(error), resolved))
            continue
        if result.returncode != 0:
            message = result.stderr.strip() or "not a readable Git checkout"
            errors.append(error_record("worktrees", message, resolved))
            continue
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                paths.add(str(Path(line.removeprefix("worktree ")).resolve()))
    return sorted(paths)[:MAX_CANDIDATES], errors


def inspect_candidate(
    runner: CommandRunner, path: str
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    commands = {
        "remote": ["git", "-C", path, "remote", "get-url", "origin"],
        "head": ["git", "-C", path, "rev-parse", "HEAD"],
        "status": [
            "git",
            "-C",
            path,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
    }
    values = {}
    errors = []
    for source, command in commands.items():
        try:
            result = runner.run(command)
        except (RuntimeError, TimeoutError) as error:
            errors.append(error_record(source, str(error), path))
            return None, errors
        if result.returncode != 0:
            message = result.stderr.strip() or f"git {source} failed"
            errors.append(error_record(source, message, path))
            return None, errors
        values[source] = result.stdout
    repository = github_repository(values["remote"].strip())
    if not repository:
        return None, errors
    return (
        {
            "path": path,
            "repository": repository,
            "headSha": values["head"].strip(),
            "clean": values["status"] == "",
        },
        errors,
    )


def unavailable_checkout(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "path": None,
        "reason": reason,
        "repository": None,
        "headSha": None,
        "clean": None,
    }


def resolve_checkout(
    repository: str,
    head_sha: str,
    *,
    candidate_paths: list[str] | None = None,
    cwd: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> dict[str, Any]:
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise ValueError("repository must look like owner/repo")
    if not SHA_PATTERN.fullmatch(head_sha):
        raise ValueError("head SHA must contain 40 to 64 hexadecimal characters")

    runner = CommandRunner(timeout=timeout, max_output_bytes=max_output_bytes)
    errors = []
    if candidate_paths is None:
        seeds, discovery_errors = discover_candidate_paths(
            runner, Path(cwd or os.getcwd()).resolve()
        )
        errors.extend(discovery_errors)
    else:
        seeds = candidate_paths[:MAX_CANDIDATES]
    paths, worktree_errors = worktree_paths(runner, seeds)
    errors.extend(worktree_errors)

    records = []
    for path in paths:
        record, candidate_errors = inspect_candidate(runner, path)
        errors.extend(candidate_errors)
        if record:
            records.append(record)

    repository_matches = [
        record
        for record in records
        if record["repository"].casefold() == repository.casefold()
    ]
    head_matches = [
        record
        for record in repository_matches
        if record["headSha"].casefold() == head_sha.casefold()
    ]
    clean_matches = [record for record in head_matches if record["clean"]]

    if clean_matches:
        selected = min(clean_matches, key=lambda record: (len(record["path"]), record["path"]))
        checkout = {
            "available": True,
            "path": selected["path"],
            "reason": None,
            "repository": selected["repository"],
            "headSha": selected["headSha"],
            "clean": True,
        }
        status = "verified"
    elif not repository_matches:
        checkout = unavailable_checkout("repository-not-found")
        status = "unavailable"
    elif not head_matches:
        checkout = unavailable_checkout("head-not-found")
        status = "unavailable"
    elif any(not record["clean"] for record in head_matches):
        checkout = unavailable_checkout("checkout-dirty")
        status = "unavailable"
    else:
        checkout = unavailable_checkout("checkout-unavailable")
        status = "unavailable"

    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": status,
        "target": {"repository": repository, "headSha": head_sha},
        "checkout": checkout,
        "candidatesChecked": len(paths),
        "errors": errors,
        "limits": {
            "maxCandidates": MAX_CANDIDATES,
            "timeoutSeconds": timeout,
            "maxOutputBytes": max_output_bytes,
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository")
    parser.add_argument("head_sha")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    arguments = parse_args(argv)
    try:
        result = resolve_checkout(
            arguments.repository,
            arguments.head_sha,
            timeout=min(30.0, max(0.1, arguments.timeout)),
            max_output_bytes=DEFAULT_MAX_OUTPUT_BYTES,
        )
        exit_code = 0
    except (RuntimeError, TimeoutError, ValueError) as error:
        result = {
            "schemaVersion": SCHEMA_VERSION,
            "status": "failed",
            "target": {
                "repository": arguments.repository,
                "headSha": arguments.head_sha,
            },
            "checkout": unavailable_checkout("invalid-or-failed"),
            "errors": [error_record("resolver", str(error))],
        }
        exit_code = 1
    json.dump(result, sys.stdout, indent=2 if arguments.pretty else None, sort_keys=True)
    sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
