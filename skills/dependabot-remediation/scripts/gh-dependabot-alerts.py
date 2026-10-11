#!/usr/bin/env python3
"""Bounded, read-only Dependabot security-alert collector.

Emits one ``dependabot-alerts/v1`` JSON document on stdout. A denied, rate-limited,
failed, truncated or malformed read is reported as ``unavailable`` or ``partial``,
never as zero alerts. Free-text advisory fields are dropped or bounded; nothing
here dismisses, edits or otherwise mutates GitHub state.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit

SCHEMA_VERSION = "dependabot-alerts/v1"
PER_PAGE = 100
MAX_ALERT_FILTERS = 50
SUMMARY_LIMIT = 160
DETAIL_LIMIT = 200
EXIT_COMPLETE, EXIT_PARTIAL, EXIT_UNAVAILABLE, EXIT_USAGE, EXIT_MISSING_TOOL = 0, 2, 3, 64, 127
REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*")
TOKEN_SHAPE = re.compile(r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]+")


class Usage(Exception):
    pass


class MissingTool(Exception):
    pass


def bounded(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    text = TOKEN_SHAPE.sub("[redacted]", " ".join(str(text).split()))
    return text[:limit]


def classify_failure(stderr: str, returncode: int) -> str:
    lower = stderr.lower()
    if "rate limit" in lower or "http 429" in lower:
        return "rate-limited"
    if "http 401" in lower or "http 403" in lower or "not authenticated" in lower or "auth login" in lower:
        return "permission-denied"
    if "http 404" in lower:
        return "not-found"
    if returncode < 0:
        return "timeout"
    return "request-failed"


def run_gh(path: str, timeout: float, *, include: bool = False) -> tuple[str | None, str | None, str | None]:
    """Return (stdout, reason, detail); reason is None on transport success."""
    command = ["gh", "api", "--hostname", "github.com", "--method", "GET", path]
    if include:
        command.append("--include")
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError:
        raise MissingTool("gh is required") from None
    except subprocess.TimeoutExpired:
        return None, "timeout", f"no response within {timeout:g}s"
    if result.returncode != 0:
        return None, classify_failure(result.stderr, result.returncode), bounded(result.stderr, DETAIL_LIMIT) or None
    return result.stdout, None, None


def parse_json(payload: str):
    try:
        return json.loads(payload), None
    except json.JSONDecodeError:
        return None, "malformed-response"


def repository_from_origin() -> tuple[str, str]:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=5, check=False,
        )
    except FileNotFoundError:
        raise MissingTool("git is required") from None
    except subprocess.TimeoutExpired:
        raise Usage("git remote lookup timed out; pass --repo OWNER/REPO") from None
    if result.returncode != 0 or not result.stdout.strip():
        raise Usage("no origin remote; pass --repo OWNER/REPO")
    helper = Path(__file__).resolve().parents[2] / "pr-status" / "scripts"
    if not (helper / "github_remote.py").is_file():
        raise Usage("shared GitHub remote parser unavailable; pass --repo OWNER/REPO")
    sys.path.insert(0, str(helper))
    from github_remote import github_repository

    repository = github_repository(result.stdout)
    if not repository:
        raise Usage("origin is not a github.com repository; pass --repo OWNER/REPO")
    return repository, "origin-remote"


def normalize_alert(repository: str, raw: dict) -> dict:
    dependency = raw.get("dependency") or {}
    package = dependency.get("package") or {}
    vulnerability = raw.get("security_vulnerability") or {}
    advisory = raw.get("security_advisory") or {}
    patched = vulnerability.get("first_patched_version") or {}
    number = raw.get("number")
    return {
        "identity": f"{repository}#{number}",
        "number": number,
        "state": raw.get("state"),
        "severity": vulnerability.get("severity") or advisory.get("severity"),
        "ecosystem": package.get("ecosystem"),
        "package": package.get("name"),
        "manifestPath": dependency.get("manifest_path"),
        "scope": dependency.get("scope"),
        "relationship": dependency.get("relationship"),
        "vulnerableRange": vulnerability.get("vulnerable_version_range"),
        "firstPatchedVersion": patched.get("identifier"),
        "ghsaId": advisory.get("ghsa_id"),
        "cveId": advisory.get("cve_id"),
        "summary": bounded(advisory.get("summary"), SUMMARY_LIMIT),
        "createdAt": raw.get("created_at"),
        "updatedAt": raw.get("updated_at"),
        "fixedAt": raw.get("fixed_at"),
        "dismissedAt": raw.get("dismissed_at"),
        "dismissedReason": raw.get("dismissed_reason"),
        "autoDismissedAt": raw.get("auto_dismissed_at"),
        "htmlUrl": raw.get("html_url"),
    }


def list_response(stdout: str) -> tuple[list, list[str]]:
    """Parse gh --include's HTTP envelope without exposing headers in the report."""
    header, separator, body = stdout.replace("\r\n", "\n").partition("\n\n")
    lines = header.splitlines()
    if not separator or not lines or not re.fullmatch(r"HTTP/[\d.]+ 200(?: .*)?", lines[0]):
        raise ValueError("malformed-response")
    links = []
    for line in lines[1:]:
        name, colon, value = line.partition(":")
        if not colon or not re.fullmatch(r"[A-Za-z0-9-]+", name):
            raise ValueError("malformed-response")
        if name.lower() == "link":
            links.append(value.strip())
    payload, reason = parse_json(body)
    if reason or not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise ValueError("malformed-response")
    return payload, links


def next_cursor(links: list[str], repository: str) -> str | None:
    """Only extract a cursor from the exact repository's GitHub API list endpoint."""
    cursor = None
    for header in links:
        for entry in header.split(","):
            match = re.fullmatch(r'\s*<([^<>\s]+)>\s*;\s*rel="([^"]+)"\s*', entry)
            if not match:
                raise ValueError("malformed-pagination")
            if "next" not in match[2].split():
                continue
            if cursor is not None:
                raise ValueError("malformed-pagination")
            try:
                url = urlsplit(match[1])
                if (url.scheme != "https" or url.netloc != "api.github.com"
                        or url.path != f"/repos/{repository}/dependabot/alerts" or url.fragment
                        or re.search(r"%(?![A-Fa-f0-9]{2})", url.query)):
                    raise ValueError
                query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True, errors="strict")
                values = query.get("after", [])
                if len(values) != 1 or not values[0] or len(values[0]) > 2048:
                    raise ValueError
                cursor = values[0]
                if any(ord(char) < 33 or ord(char) > 126 for char in cursor):
                    raise ValueError
            except ValueError:
                raise ValueError("malformed-pagination") from None
    return cursor


def collect_pages(repository: str, state: str, max_pages: int, timeout: float, report: dict) -> list[dict]:
    alerts: list[dict] = []
    parameters = {"state": state} if state != "all" else {}
    parameters["per_page"] = PER_PAGE
    seen_cursors: set[str] = set()
    for page in range(1, max_pages + 1):
        query = urlencode(parameters)
        stdout, reason, detail = run_gh(f"repos/{repository}/dependabot/alerts?{query}", timeout, include=True)
        report["pages"] = page
        if reason:
            report.update(status="unavailable", reason=reason, detail=detail)
            return []
        try:
            payload, links = list_response(stdout or "")
            cursor = next_cursor(links, repository)
            if cursor in seen_cursors:
                raise ValueError("malformed-pagination")
        except ValueError as error:
            report.update(status="unavailable", reason=str(error))
            return []
        alerts.extend(normalize_alert(repository, item) for item in payload)
        if cursor is None:
            report["status"] = "complete"
            return alerts
        seen_cursors.add(cursor)
        parameters["after"] = cursor
    report.update(status="partial", reason="page-cap-reached")
    return alerts


def collect_numbers(repository: str, numbers: list[int], timeout: float, report: dict) -> list[dict]:
    alerts: list[dict] = []
    missing: list[int] = []
    unavailable: list[int] = []
    for number in numbers:
        stdout, reason, detail = run_gh(f"repos/{repository}/dependabot/alerts/{number}", timeout)
        if reason == "not-found":
            missing.append(number)
            continue
        if reason:
            unavailable.append(number)
            report.setdefault("detail", detail)
            report["reason"] = reason
            continue
        payload, reason = parse_json(stdout or "")
        if reason or not isinstance(payload, dict):
            unavailable.append(number)
            report["reason"] = reason or "malformed-response"
            continue
        alerts.append(normalize_alert(repository, payload))
    report["missing"] = missing
    report["unavailable"] = unavailable
    report["status"] = "unavailable" if unavailable else "complete"
    return alerts


def default_branch_head(repository: str, timeout: float) -> dict:
    head: dict = {"name": None, "headSha": None, "status": "unavailable", "reason": None}
    stdout, reason, _ = run_gh(f"repos/{repository}", timeout)
    payload, parse_reason = parse_json(stdout or "") if stdout is not None else (None, None)
    name = payload.get("default_branch") if isinstance(payload, dict) else None
    if reason or parse_reason or not isinstance(name, str) or not name:
        head["reason"] = reason or parse_reason or "malformed-response"
        return head
    head["name"] = name
    stdout, reason, _ = run_gh(f"repos/{repository}/commits/{quote(name, safe='')}", timeout)
    payload, parse_reason = parse_json(stdout or "") if stdout is not None else (None, None)
    sha = payload.get("sha") if isinstance(payload, dict) else None
    if reason or parse_reason or not isinstance(sha, str):
        head["reason"] = reason or parse_reason or "malformed-response"
        return head
    head.update(headSha=sha, status="complete")
    return head


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="OWNER/REPO on github.com; defaults to the origin remote")
    parser.add_argument("--state", choices=("open", "all"), default="open")
    parser.add_argument("--alert", action="append", type=int, default=[], help="re-read one alert number (repeatable)")
    parser.add_argument("--max-pages", type=int, default=10, help="page cap at 100 alerts per page (1-50)")
    parser.add_argument("--timeout", type=float, default=30.0, help="per-request seconds (1-120)")
    parser.add_argument("--no-head", action="store_true", help="skip the default-branch head lookup")
    args = parser.parse_args(argv)
    if args.repo is not None and not REPOSITORY.fullmatch(args.repo):
        parser.error("--repo must be OWNER/REPO")
    if not 1 <= args.max_pages <= 50:
        parser.error("--max-pages must be between 1 and 50")
    if not 1 <= args.timeout <= 120:
        parser.error("--timeout must be between 1 and 120 seconds")
    if any(number < 1 for number in args.alert):
        parser.error("--alert numbers must be positive")
    if len(args.alert) > MAX_ALERT_FILTERS:
        parser.error(f"at most {MAX_ALERT_FILTERS} --alert filters")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repository, source = (args.repo, "argument") if args.repo else repository_from_origin()
    report: dict = {
        "schemaVersion": SCHEMA_VERSION,
        "repository": repository,
        "repositorySource": source,
        "state": args.state,
        "status": "unavailable",
        "reason": None,
        "detail": None,
        "pages": 0,
        "maxPages": args.max_pages,
        "requested": sorted(set(args.alert)),
        "missing": [],
        "unavailable": [],
        "defaultBranch": None,
        "alerts": [],
    }
    if args.alert:
        report["alerts"] = collect_numbers(repository, report["requested"], args.timeout, report)
    else:
        report["alerts"] = collect_pages(repository, args.state, args.max_pages, args.timeout, report)
    if not args.no_head:
        report["defaultBranch"] = default_branch_head(repository, args.timeout)
    json.dump(report, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")
    return {"complete": EXIT_COMPLETE, "partial": EXIT_PARTIAL}.get(report["status"], EXIT_UNAVAILABLE)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Usage as error:
        print(f"gh-dependabot-alerts: {error}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
    except MissingTool as error:
        print(f"gh-dependabot-alerts: {error}", file=sys.stderr)
        raise SystemExit(EXIT_MISSING_TOOL) from None
