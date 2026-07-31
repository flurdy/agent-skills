#!/usr/bin/env python3
"""Collect a bounded, repository-qualified, immutable PR review snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import selectors
import signal
import subprocess
import sys
from pathlib import Path
from time import monotonic
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
FEEDBACK_COLLECTOR = (
    SCRIPT_DIR.parent.parent / "pr-status" / "scripts" / "gh-pr-feedback.py"
)
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_OUTPUT_BYTES = 4_000_000
DEFAULT_BODY_CHARS = 20_000
DEFAULT_PATCH_CHARS = 20_000
DEFAULT_MAX_FILES = 100

QUALIFIED_SELECTOR = re.compile(
    r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)#(?P<number>[1-9][0-9]*)$"
)
PR_URL = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/"
    r"(?P<repo>[A-Za-z0-9_.-]+)/pull/(?P<number>[1-9][0-9]*)/?$"
)
OBJECT_ID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")

INITIAL_QUERY = """
query ReviewPrSnapshot($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      id
      number
      url
      title
      body
      state
      isDraft
      updatedAt
      reviewDecision
      author { login }
      additions
      deletions
      changedFiles
      baseRefName
      baseRefOid
      headRefName
      headRefOid
      headRepository { nameWithOwner }
      commits(last: 1) {
        nodes {
          commit {
            oid
            statusCheckRollup { state }
          }
        }
      }
    }
  }
}
"""

FINAL_QUERY = """
query ReviewPrSnapshotFinal($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      id
      state
      isDraft
      updatedAt
      reviewDecision
      baseRefOid
      headRefOid
      commits(last: 1) {
        nodes {
          commit {
            oid
            statusCheckRollup { state }
          }
        }
      }
    }
  }
}
"""


class CommandError(RuntimeError):
    """A bounded external command failed."""


class SubprocessRunner:
    """Run commands with one caller-owned deadline and bounded captured output."""

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None,
        deadline: float,
        max_output_bytes: int,
        check: bool = True,
    ) -> str:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise CommandError("review snapshot deadline exceeded")
        environment = os.environ.copy()
        environment.update(
            {
                "GH_PAGER": "cat",
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_OPTIONAL_LOCKS": "0",
                "NO_COLOR": "1",
                "PAGER": "cat",
            }
        )
        try:
            process = subprocess.Popen(
                args,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as error:
            raise CommandError(str(error)) from error
        assert process.stdout is not None and process.stderr is not None

        def kill_process_group() -> None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.poll() is None:
                process.wait()

        output = bytearray()
        errors = bytearray()
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, output)
        selector.register(process.stderr, selectors.EVENT_READ, errors)
        try:
            while selector.get_map():
                remaining = deadline - monotonic()
                if remaining <= 0:
                    kill_process_group()
                    raise CommandError("review snapshot deadline exceeded")
                events = selector.select(min(remaining, 0.25))
                for key, _ in events:
                    chunk = os.read(key.fd, 65_536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    key.data.extend(chunk)
                    if len(output) + len(errors) > max_output_bytes:
                        kill_process_group()
                        raise CommandError(
                            f"command output exceeded {max_output_bytes} bytes"
                        )
            return_code = process.wait()
        finally:
            selector.close()
            kill_process_group()
            process.stdout.close()
            process.stderr.close()

        stdout = output.decode("utf-8", errors="replace")
        stderr = errors.decode("utf-8", errors="replace").strip()
        if check and return_code != 0:
            message = stderr or stdout.strip() or f"command exited {return_code}"
            raise CommandError(message[:500])
        return stdout


def error_record(source: str, message: str, kind: str = "unavailable") -> dict[str, str]:
    return {"source": source, "kind": kind, "message": message[:500]}


def parse_json(output: str, source: str) -> Any:
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise CommandError(f"{source} returned invalid JSON: {error}") from error


def repository_parts(value: str) -> tuple[str, str]:
    parts = value.strip().removesuffix(".git").split("/")
    if len(parts) != 2 or not all(parts):
        raise CommandError("current checkout did not resolve one owner/repository")
    return parts[0], parts[1]


def resolve_target(
    selector: str | None,
    *,
    runner: Any,
    cwd: Path,
    deadline: float,
    max_output_bytes: int,
) -> dict[str, Any]:
    source = "qualified"
    if selector:
        match = QUALIFIED_SELECTOR.fullmatch(selector) or PR_URL.fullmatch(selector)
        if match is not None:
            return {
                "owner": match.group("owner"),
                "repo": match.group("repo"),
                "number": int(match.group("number")),
                "selectorSource": source,
            }
        if not selector.isdigit() or int(selector) <= 0:
            raise CommandError(
                "target must be a PR URL, owner/repo#number, or positive PR number"
            )
        number = int(selector)
        source = "current-repository-number"
    else:
        current = parse_json(
            runner.run(
                ["gh", "pr", "view", "--json", "number,url"],
                cwd=cwd,
                deadline=deadline,
                max_output_bytes=max_output_bytes,
            ),
            "current pull request",
        )
        if not isinstance(current, dict) or not isinstance(current.get("url"), str):
            raise CommandError("current branch did not resolve a pull request")
        match = PR_URL.fullmatch(current["url"])
        if match is None or current.get("number") != int(match.group("number")):
            raise CommandError("current branch returned an invalid pull request URL")
        return {
            "owner": match.group("owner"),
            "repo": match.group("repo"),
            "number": int(match.group("number")),
            "selectorSource": "current-branch",
        }

    repository = parse_json(
        runner.run(
            ["gh", "repo", "view", "--json", "nameWithOwner"],
            cwd=cwd,
            deadline=deadline,
            max_output_bytes=max_output_bytes,
        ),
        "current repository",
    )
    if not isinstance(repository, dict) or not isinstance(
        repository.get("nameWithOwner"), str
    ):
        raise CommandError("current checkout did not resolve a GitHub repository")
    owner, repo = repository_parts(repository["nameWithOwner"])
    return {
        "owner": owner,
        "repo": repo,
        "number": number,
        "selectorSource": source,
    }


def graphql_pull_request(
    query: str,
    target: dict[str, Any],
    *,
    runner: Any,
    cwd: Path,
    deadline: float,
    max_output_bytes: int,
) -> dict[str, Any]:
    payload = parse_json(
        runner.run(
            [
                "gh",
                "api",
                "graphql",
                "-f",
                f"query={query}",
                "-f",
                f"owner={target['owner']}",
                "-f",
                f"repo={target['repo']}",
                "-F",
                f"number={target['number']}",
            ],
            cwd=cwd,
            deadline=deadline,
            max_output_bytes=max_output_bytes,
        ),
        "GitHub GraphQL",
    )
    if not isinstance(payload, dict):
        raise CommandError("GitHub GraphQL response was not an object")
    graph_errors = payload.get("errors")
    if isinstance(graph_errors, list) and graph_errors:
        messages = [
            item.get("message", "unknown GraphQL error")
            for item in graph_errors
            if isinstance(item, dict)
        ]
        raise CommandError("; ".join(messages) or "GitHub GraphQL failed")
    data = payload.get("data")
    repository = data.get("repository") if isinstance(data, dict) else None
    pull_request = (
        repository.get("pullRequest") if isinstance(repository, dict) else None
    )
    if not isinstance(pull_request, dict):
        raise CommandError("pull request was not found in the selected repository")
    return pull_request


def valid_object_id(value: Any) -> str:
    if not isinstance(value, str) or OBJECT_ID.fullmatch(value) is None:
        raise CommandError("pull request returned an invalid Git object ID")
    return value


def normalized_remote(value: str) -> str | None:
    remote = value.strip().removesuffix(".git")
    patterns = (
        r"^(?:git@|ssh://git@)github\.com[:/](?P<repository>[^/]+/[^/]+)$",
        r"^https?://github\.com/(?P<repository>[^/]+/[^/]+)$",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, remote)
        if match is not None:
            return match.group("repository")
    return None


def verify_checkout(
    candidate: Path,
    target: dict[str, Any],
    head_sha: str,
    *,
    runner: Any,
    cwd: Path,
    deadline: float,
    max_output_bytes: int,
) -> dict[str, Any]:
    def git(*arguments: str) -> str:
        return runner.run(
            ["git", "-C", str(candidate), *arguments],
            cwd=cwd,
            deadline=deadline,
            max_output_bytes=max_output_bytes,
        ).strip()

    try:
        root = Path(git("rev-parse", "--show-toplevel")).resolve()
        remote = normalized_remote(git("remote", "get-url", "origin"))
        expected_repositories = {
            target["repository"].casefold(),
            str(target.get("headRepository") or "").casefold(),
        }
        if remote is None or remote.casefold() not in expected_repositories:
            return {
                "available": False,
                "path": str(root),
                "reason": "repository mismatch",
            }
        checkout_head = git("rev-parse", "HEAD")
        if checkout_head != head_sha:
            return {
                "available": False,
                "path": str(root),
                "reason": f"HEAD does not match PR head {head_sha}",
            }
        if git("status", "--porcelain", "--untracked-files=all"):
            return {
                "available": False,
                "path": str(root),
                "reason": "working tree is not clean",
            }
        return {
            "available": True,
            "path": str(root),
            "reason": "repository identity and exact HEAD verified",
        }
    except (CommandError, OSError) as error:
        return {
            "available": False,
            "path": str(candidate),
            "reason": str(error),
        }


def checks_for_pull_request(
    pull_request: dict[str, Any], head_sha: str
) -> dict[str, str | None]:
    commits = pull_request.get("commits")
    commit_nodes = commits.get("nodes") if isinstance(commits, dict) else None
    commit = (
        commit_nodes[0].get("commit")
        if isinstance(commit_nodes, list)
        and commit_nodes
        and isinstance(commit_nodes[0], dict)
        else None
    )
    if not isinstance(commit, dict) or commit.get("oid") != head_sha:
        raise CommandError("check status did not match the PR head SHA")
    rollup = commit.get("statusCheckRollup")
    checks_state = rollup.get("state") if isinstance(rollup, dict) else None
    return {"headSha": head_sha, "state": checks_state or "UNKNOWN"}


def initial_target(
    resolved: dict[str, Any], pull_request: dict[str, Any], body_limit: int
) -> tuple[dict[str, Any], bool]:
    if pull_request.get("number") != resolved["number"]:
        raise CommandError("pull request metadata returned the wrong number")
    if not isinstance(pull_request.get("id"), str) or not pull_request["id"]:
        raise CommandError("pull request metadata omitted its node ID")
    url = pull_request.get("url")
    url_match = PR_URL.fullmatch(url) if isinstance(url, str) else None
    if url_match is None:
        raise CommandError("pull request metadata returned an invalid URL")
    if (
        url_match.group("owner").casefold() != resolved["owner"].casefold()
        or url_match.group("repo").casefold() != resolved["repo"].casefold()
        or int(url_match.group("number")) != resolved["number"]
    ):
        raise CommandError("pull request metadata returned the wrong repository")
    head_sha = valid_object_id(pull_request.get("headRefOid"))
    base_sha = valid_object_id(pull_request.get("baseRefOid"))
    body = pull_request.get("body")
    body_text = body if isinstance(body, str) else ""
    body_truncated = len(body_text) > body_limit
    author = pull_request.get("author")
    checks = checks_for_pull_request(pull_request, head_sha)
    target = {
        "repository": f"{resolved['owner']}/{resolved['repo']}",
        "owner": resolved["owner"],
        "repo": resolved["repo"],
        "number": resolved["number"],
        "selectorSource": resolved["selectorSource"],
        "nodeId": pull_request.get("id"),
        "url": pull_request.get("url"),
        "title": pull_request.get("title"),
        "body": body_text[:body_limit],
        "bodyTruncated": body_truncated,
        "state": pull_request.get("state"),
        "isDraft": pull_request.get("isDraft"),
        "updatedAt": pull_request.get("updatedAt"),
        "reviewDecision": pull_request.get("reviewDecision"),
        "author": author.get("login") if isinstance(author, dict) else None,
        "additions": pull_request.get("additions"),
        "deletions": pull_request.get("deletions"),
        "changedFiles": pull_request.get("changedFiles"),
        "baseRef": pull_request.get("baseRefName"),
        "baseSha": base_sha,
        "headRef": pull_request.get("headRefName"),
        "headSha": head_sha,
        "headRepository": (
            pull_request.get("headRepository", {}).get("nameWithOwner")
            if isinstance(pull_request.get("headRepository"), dict)
            else None
        ),
        "checks": checks,
    }
    return target, body_truncated


def review_state_key(target: dict[str, Any], feedback: dict[str, Any]) -> str:
    records = feedback.get("records")
    record_state = []
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, dict):
                continue
            record_state.append(
                {
                    key: record.get(key)
                    for key in (
                        "identity",
                        "updateKey",
                        "stateKey",
                        "lifecycle",
                        "source",
                    )
                }
            )
    record_state.sort(key=lambda record: str(record.get("identity") or ""))
    state = {
        "target": {
            key: target.get(key)
            for key in (
                "repository",
                "number",
                "nodeId",
                "headSha",
                "baseSha",
                "state",
                "isDraft",
                "updatedAt",
                "reviewDecision",
                "checks",
            )
        },
        "feedback": {
            "partial": feedback.get("partial"),
            "errors": feedback.get("errors"),
            "records": record_state,
        },
    }
    encoded = json.dumps(
        state, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def empty_result(limits: dict[str, int]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "status": "failed",
        "reviewReady": False,
        "target": None,
        "snapshot": {
            "initialHeadSha": None,
            "initialBaseSha": None,
            "finalHeadSha": None,
            "finalBaseSha": None,
            "stateKey": None,
        },
        "checkout": {
            "available": False,
            "path": None,
            "reason": "target metadata unavailable",
        },
        "evidence": {"files": [], "feedback": None},
        "limits": limits,
        "errors": [],
    }


def collect_files(
    resolved: dict[str, Any],
    target: dict[str, Any],
    result: dict[str, Any],
    *,
    runner: Any,
    cwd: Path,
    deadline: float,
    max_output_bytes: int,
    max_files: int,
    patch_limit: int,
) -> None:
    file_payload = parse_json(
        runner.run(
            [
                "gh",
                "api",
                f"repos/{resolved['owner']}/{resolved['repo']}/pulls/"
                f"{resolved['number']}/files?per_page={max_files}&page=1",
            ],
            cwd=cwd,
            deadline=deadline,
            max_output_bytes=max_output_bytes,
        ),
        "pull request files",
    )
    if not isinstance(file_payload, list):
        raise CommandError("pull request files response was not a list")
    files = []
    for item in file_payload[:max_files]:
        if not isinstance(item, dict) or not isinstance(item.get("filename"), str):
            raise CommandError("pull request files response contained an invalid item")
        patch_value = item.get("patch")
        changes = item.get("changes")
        if not isinstance(patch_value, str):
            patch = ""
            patch_unavailable = True
        else:
            patch = patch_value
            patch_unavailable = False
        patch_truncated = len(patch) > patch_limit
        if patch_unavailable:
            result["errors"].append(
                error_record(
                    "files",
                    f"patch for {item['filename']} was unavailable",
                    "unavailable",
                )
            )
        elif patch_truncated:
            result["errors"].append(
                error_record(
                    "files",
                    f"patch for {item['filename']} exceeded {patch_limit} characters",
                    "truncated",
                )
            )
        files.append(
            {
                "path": item["filename"],
                "status": item.get("status"),
                "additions": item.get("additions"),
                "deletions": item.get("deletions"),
                "changes": changes,
                "patch": patch[:patch_limit],
                "patchTruncated": patch_truncated,
                "patchUnavailable": patch_unavailable,
            }
        )
    result["evidence"]["files"] = files
    changed_files = target.get("changedFiles")
    if isinstance(changed_files, int) and changed_files > len(files):
        result["errors"].append(
            error_record(
                "files",
                f"collected {len(files)} of {changed_files} changed files",
                "truncated",
            )
        )


def collect_feedback(
    resolved: dict[str, Any],
    target: dict[str, Any],
    *,
    runner: Any,
    cwd: Path,
    deadline: float,
    max_output_bytes: int,
    body_limit: int,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    feedback = parse_json(
        runner.run(
            [
                str(FEEDBACK_COLLECTOR),
                resolved["owner"],
                resolved["repo"],
                str(resolved["number"]),
                "--body-limit",
                str(min(body_limit, 2_000)),
                "--max-source-items",
                "200",
                "--max-records-per-pr",
                "500",
            ],
            cwd=cwd,
            deadline=deadline,
            max_output_bytes=max_output_bytes,
        ),
        "feedback inventory",
    )
    if not isinstance(feedback, dict):
        raise CommandError("feedback inventory was not an object")
    if feedback.get("repository") != target["repository"] or feedback.get(
        "pullRequests"
    ) != [target["number"]]:
        raise CommandError("feedback inventory returned the wrong pull request")

    errors = []
    if feedback.get("partial") is True:
        feedback_errors = feedback.get("errors")
        message = "feedback inventory was partial"
        if isinstance(feedback_errors, list) and feedback_errors:
            first = feedback_errors[0]
            if isinstance(first, dict):
                message = str(first.get("message") or message)
        errors.append(error_record("feedback", message, "partial"))
    records = feedback.get("records")
    if isinstance(records, list) and any(
        isinstance(record, dict)
        and (
            record.get("bodyTruncated") is True
            or record.get("annotationTitleTruncated") is True
        )
        for record in records
    ):
        errors.append(
            error_record(
                "feedback",
                "one or more feedback records were truncated",
                "truncated",
            )
        )
    return feedback, errors


def collect_snapshot(
    selector: str | None,
    *,
    runner: Any | None = None,
    cwd: Path | None = None,
    expected_head: str | None = None,
    expected_base: str | None = None,
    expected_state_key: str | None = None,
    checkout: Path | None = None,
    verify_only: bool = False,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_files: int = DEFAULT_MAX_FILES,
    body_limit: int = DEFAULT_BODY_CHARS,
    patch_limit: int = DEFAULT_PATCH_CHARS,
    max_output_bytes: int = DEFAULT_OUTPUT_BYTES,
) -> dict[str, Any]:
    runner = runner or SubprocessRunner()
    cwd = (cwd or Path.cwd()).resolve()
    max_files = max(1, min(100, max_files))
    body_limit = max(1, body_limit)
    patch_limit = max(1, patch_limit)
    max_output_bytes = max(1_000, max_output_bytes)
    limits = {
        "deadlineSeconds": max(1, int(timeout)),
        "files": max_files,
        "bodyChars": body_limit,
        "patchCharsPerFile": patch_limit,
        "commandOutputBytes": max_output_bytes,
    }
    result = empty_result(limits)
    deadline = monotonic() + max(0.1, timeout)

    try:
        resolved = resolve_target(
            selector,
            runner=runner,
            cwd=cwd,
            deadline=deadline,
            max_output_bytes=max_output_bytes,
        )
    except CommandError as error:
        result["errors"].append(error_record("target", str(error), "invalid"))
        return result

    result["target"] = {
        "repository": f"{resolved['owner']}/{resolved['repo']}",
        "owner": resolved["owner"],
        "repo": resolved["repo"],
        "number": resolved["number"],
        "selectorSource": resolved["selectorSource"],
    }
    try:
        pull_request = graphql_pull_request(
            INITIAL_QUERY,
            resolved,
            runner=runner,
            cwd=cwd,
            deadline=deadline,
            max_output_bytes=max_output_bytes,
        )
        target, body_truncated = initial_target(resolved, pull_request, body_limit)
    except CommandError as error:
        result["errors"].append(error_record("metadata", str(error)))
        return result

    result["target"] = target
    result["snapshot"]["initialHeadSha"] = target["headSha"]
    result["snapshot"]["initialBaseSha"] = target["baseSha"]
    expected_revisions = (
        ("expected-head", expected_head, target["headSha"]),
        ("expected-base", expected_base, target["baseSha"]),
    )
    for source, expected, actual in expected_revisions:
        if expected is None:
            continue
        if OBJECT_ID.fullmatch(expected) is None:
            result["errors"].append(
                error_record(source, f"{source} was not a Git object ID", "invalid")
            )
            return result
        if expected != actual:
            result["status"] = "stale"
            result["errors"].append(
                error_record(
                    source,
                    f"expected {expected}, found {actual}",
                    "stale",
                )
            )
            return result
    if verify_only and (
        expected_state_key is None
        or re.fullmatch(r"[0-9a-f]{64}", expected_state_key) is None
    ):
        result["errors"].append(
            error_record(
                "expected-state-key",
                "verify-only requires a valid expected state key",
                "invalid",
            )
        )
        return result

    if not verify_only:
        candidate = (checkout or cwd).resolve()
        result["checkout"] = verify_checkout(
            candidate,
            target,
            target["headSha"],
            runner=runner,
            cwd=cwd,
            deadline=deadline,
            max_output_bytes=max_output_bytes,
        )
        if body_truncated:
            result["errors"].append(
                error_record(
                    "metadata",
                    f"PR body exceeded {body_limit} characters",
                    "truncated",
                )
            )

    if not verify_only:
        try:
            collect_files(
                resolved,
                target,
                result,
                runner=runner,
                cwd=cwd,
                deadline=deadline,
                max_output_bytes=max_output_bytes,
                max_files=max_files,
                patch_limit=patch_limit,
            )
        except CommandError as error:
            result["errors"].append(error_record("files", str(error)))

    try:
        feedback, feedback_errors = collect_feedback(
            resolved,
            target,
            runner=runner,
            cwd=cwd,
            deadline=deadline,
            max_output_bytes=max_output_bytes,
            body_limit=body_limit,
        )
        result["evidence"]["feedback"] = feedback
        result["errors"].extend(feedback_errors)
    except CommandError as error:
        feedback = None
        result["errors"].append(error_record("feedback", str(error)))

    try:
        final = graphql_pull_request(
            FINAL_QUERY,
            resolved,
            runner=runner,
            cwd=cwd,
            deadline=deadline,
            max_output_bytes=max_output_bytes,
        )
        final_head = valid_object_id(final.get("headRefOid"))
        final_base = valid_object_id(final.get("baseRefOid"))
        final_checks = checks_for_pull_request(final, final_head)
    except CommandError as error:
        result["errors"].append(error_record("final-head", str(error)))
        result["status"] = "failed"
        return result

    result["snapshot"]["finalHeadSha"] = final_head
    result["snapshot"]["finalBaseSha"] = final_base
    raced = (
        final.get("id") != target["nodeId"]
        or final_head != target["headSha"]
        or final_base != target["baseSha"]
        or final.get("state") != target["state"]
        or final.get("isDraft") != target["isDraft"]
        or final.get("updatedAt") != target["updatedAt"]
        or final.get("reviewDecision") != target["reviewDecision"]
        or final_checks != target["checks"]
    )
    if raced:
        result["status"] = "stale"
        result["errors"].append(
            error_record("final-head", "pull request changed during collection", "stale")
        )
        return result

    if feedback is not None:
        result["snapshot"]["stateKey"] = review_state_key(target, feedback)

    if verify_only:
        if result["errors"] or result["snapshot"]["stateKey"] is None:
            result["status"] = "failed"
            return result
        if result["snapshot"]["stateKey"] != expected_state_key:
            result["status"] = "stale"
            result["errors"].append(
                error_record(
                    "expected-state-key",
                    "pull request review state changed during analysis",
                    "stale",
                )
            )
            return result
        result["status"] = "complete"
        return result

    if result["errors"]:
        result["status"] = "partial"
        return result
    result["status"] = "complete"
    result["reviewReady"] = True
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?")
    parser.add_argument("--expected-head")
    parser.add_argument("--expected-base")
    parser.add_argument("--expected-state-key")
    parser.add_argument("--checkout", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    parser.add_argument("--body-limit", type=int, default=DEFAULT_BODY_CHARS)
    parser.add_argument("--patch-limit", type=int, default=DEFAULT_PATCH_CHARS)
    parser.add_argument("--max-output-bytes", type=int, default=DEFAULT_OUTPUT_BYTES)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    arguments = parse_args(argv)
    result = collect_snapshot(
        arguments.target,
        expected_head=arguments.expected_head,
        expected_base=arguments.expected_base,
        expected_state_key=arguments.expected_state_key,
        checkout=arguments.checkout,
        verify_only=arguments.verify_only,
        timeout=arguments.timeout,
        max_files=arguments.max_files,
        body_limit=arguments.body_limit,
        patch_limit=arguments.patch_limit,
        max_output_bytes=arguments.max_output_bytes,
    )
    json.dump(result, sys.stdout, indent=2 if arguments.pretty else None, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["status"] in {"complete", "partial", "stale"} else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
