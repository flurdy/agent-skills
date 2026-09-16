#!/usr/bin/env python3
"""Read-only GitHub identity/visibility gate. Never creates, adopts, repairs, or deletes a repository."""
import argparse
import json
import re
import subprocess
from urllib.parse import quote

OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")


class GateError(Exception):
    pass


def request(endpoint):
    try:
        result = subprocess.run(
            ["gh", "api", "--hostname", "github.com", "--method", "GET", "--include", endpoint],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        raise GateError("github-transport-unavailable") from None
    if len(result.stdout) > 1_000_000:
        raise GateError("github-response-too-large")
    headers, separator, body = result.stdout.replace("\r\n", "\n").partition("\n\n")
    match = re.fullmatch(r"HTTP/\S+ (\d{3})(?: [^\n]*)?", headers.split("\n")[0])
    if not separator or not match:
        raise GateError("invalid-github-response")
    status = int(match[1])
    if (status, result.returncode) not in ((200, 0), (404, 1)):
        raise GateError("github-request-failed")
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        raise GateError("invalid-github-json") from None
    if not isinstance(data, dict):
        raise GateError("invalid-github-json")
    return status, data


def inspect(repository, *, after_create=False, expected_id=None):
    report = {"schemaVersion": "beads-setup-github/v1", "state": "blocked"}
    parts = repository.split("/")
    if len(parts) != 2 or not OWNER.fullmatch(parts[0]) or not NAME.fullmatch(parts[1]):
        return report | {"reason": "invalid-repository-name"}
    if expected_id is not None and (not after_create or type(expected_id) is not int or expected_id <= 0):
        return report | {"reason": "invalid-expected-id"}
    owner, name = parts
    report["repository"] = repository
    try:
        status, user = request("user")
        login = user.get("login")
        if status != 200 or not isinstance(login, str) or not OWNER.fullmatch(login):
            raise GateError("github-auth-unverified")
        if login.casefold() != owner.casefold():
            status, membership = request("user/memberships/orgs/" + owner)
            org = membership.get("organization")
            if (status != 200 or membership.get("state") != "active" or membership.get("role") != "admin"
                    or not isinstance(org, dict) or str(org.get("login", "")).casefold() != owner.casefold()):
                raise GateError("github-owner-authority-unverified")
        endpoint = "repos/" + repository
        status, repo = request(endpoint)
        if status == 404:
            if after_create:
                raise GateError("created-repository-not-visible")
            return report | {"state": "not-visible", "absenceProven": False,
                             "reason": "404-is-not-proof-of-absence"}
        identity = repo.get("owner")
        if (type(repo.get("id")) is not int or repo["id"] <= 0
                or not isinstance(identity, dict) or str(identity.get("login", "")).casefold() != owner.casefold()
                or str(repo.get("name", "")).casefold() != name.casefold()
                or str(repo.get("full_name", "")).casefold() != repository.casefold()
                or type(repo.get("private")) is not bool):
            raise GateError("repository-identity-unverified")
        report["id"] = repo["id"]
        if not after_create:
            return report | {"state": "exists", "reason": "new-setup-refuses-existing-repository"}
        if expected_id is not None and repo["id"] != expected_id:
            raise GateError("repository-identity-changed")
        if not repo["private"] or any(repo.get(key) is not False for key in ("fork", "archived", "disabled")):
            raise GateError("created-repository-not-private-fresh-active")
        branch = repo.get("default_branch")
        if not isinstance(branch, str) or not branch or len(branch) > 255:
            raise GateError("created-repository-has-no-branch")
        status, head = request(endpoint + "/branches/" + quote(branch, safe=""))
        commit = head.get("commit")
        sha = commit.get("sha") if isinstance(commit, dict) else None
        if status != 200 or head.get("name") != branch or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", sha):
            raise GateError("created-branch-head-unverified")
        return report | {"state": "created", "private": True, "defaultBranch": branch, "gitHead": sha}
    except GateError as error:
        return report | {"reason": str(error)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", help="explicit GitHub OWNER/NAME, not a URL")
    parser.add_argument("--after-create", action="store_true", help="verify only after separately confirmed creation")
    parser.add_argument("--expected-id", type=int, help="revalidate the recorded created repository ID")
    args = parser.parse_args()
    report = inspect(args.repository, after_create=args.after_create, expected_id=args.expected_id)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["state"] in ("not-visible", "created") else 2


if __name__ == "__main__":
    raise SystemExit(main())
