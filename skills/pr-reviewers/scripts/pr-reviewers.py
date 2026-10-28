#!/usr/bin/env python3
"""Recommend reviewers from a bounded personal PR-history sample; GitHub reads only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time

LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}")
STATES = {"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED"}
SAMPLE_SIZE = 30
SIBLING_SAMPLE_SIZE = 10
MAX_SIBLINGS = 10
MAX_ACCESS_CHECKS = 10
MAX_CANDIDATES = 5
REVIEW_FIELDS = """
reviews(first: 100) {
  pageInfo { hasNextPage }
  nodes { state submittedAt author { __typename login } }
}
"""
PR_FIELDS = "number state author { __typename login } repository { nameWithOwner } " + REVIEW_FIELDS


class CollectionError(Exception):
    """Only fixed, non-sensitive diagnostic messages leave the collector."""


def repository_name(value):
    if (not isinstance(value, str) or not REPO.fullmatch(value)
            or value.split("/")[1] in {".", ".."}):
        raise CollectionError("Expected one GitHub.com owner/repo")
    return value


def human(author):
    if not isinstance(author, dict) or author.get("__typename") != "User":
        return None
    login = author.get("login")
    if not isinstance(login, str) or not LOGIN.fullmatch(login) or login.lower() == "ghost":
        return None
    return login


def connection(value, cap):
    if not isinstance(value, dict):
        raise CollectionError("Missing GitHub connection")
    nodes = value.get("nodes")
    page = value.get("pageInfo")
    if (not isinstance(nodes, list) or len(nodes) > cap
            or not all(isinstance(node, dict) for node in nodes)
            or not isinstance(page, dict) or type(page.get("hasNextPage")) is not bool):
        raise CollectionError("Malformed GitHub connection")
    return nodes, page["hasNextPage"]


def submitted_at(value):
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError
        return date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (AttributeError, TypeError, ValueError) as error:
        raise CollectionError("Missing or invalid review timestamp") from error


def manifest_members(root):
    """Member checkouts declared by workspace.json or .mgit.conf; None without a manifest."""
    manifest = root / "workspace.json"
    config = root / ".mgit.conf"
    try:
        if manifest.is_file():
            entries = json.loads(manifest.read_text(encoding="utf-8")).get("repositories")
            paths = [entry.get("path") for entry in entries if isinstance(entry, dict)]
        elif config.is_file():
            lines = config.read_text(encoding="utf-8").splitlines()
            services = next((line[len("services="):] for line in lines
                             if line.startswith("services=")), "")
            paths = [path.strip() for path in services.split(",")]
        else:
            return None
    except (OSError, UnicodeDecodeError, ValueError, AttributeError, TypeError):
        return []
    members = []
    for path in paths:
        if not isinstance(path, str) or not path or Path(path).is_absolute():
            continue
        member = root / path
        if (member / ".git").exists():
            members.append(member.resolve())
    return members


def find_workspace(start, checkout):
    """Workspace root whose manifest claims the checkout: an ancestor, or a sibling directory."""
    for directory in (start, *start.parents):
        members = manifest_members(directory)
        if members is not None and (directory == checkout or checkout in members):
            return directory, members
        try:
            children = sorted(child for child in directory.iterdir() if child.is_dir())
        except OSError:
            children = []
        for child in children:
            members = manifest_members(child)
            if members is not None and checkout in members:
                return child, members
    return None


def history(prs, repo, viewer, number, errors):
    """Validated (pr number, reviews) pairs for one repository's closed personal PRs."""
    seen = set()
    for pr in prs:
        pr_number = pr.get("number")
        author = human(pr.get("author"))
        identity = pr.get("repository")
        if (type(pr_number) is not int or pr_number < 1 or pr_number in seen
                or not isinstance(identity, dict)
                or str(identity.get("nameWithOwner", "")).casefold() != repo.casefold()
                or not author or author.casefold() != viewer.casefold()
                or pr.get("state") not in {"CLOSED", "MERGED"} or pr_number == number):
            raise CollectionError("Personal history identity mismatch")
        seen.add(pr_number)
        reviews, truncated = connection(pr.get("reviews"), 100)
        if truncated:
            errors.append(f"Reviews truncated on PR #{pr_number}")
        yield pr_number, reviews


def recommend(response, repo, viewer, number=None, workspace=None, has_access=None):
    if not isinstance(response, dict) or response.get("errors"):
        raise CollectionError("GitHub GraphQL response failed; no ranking produced")
    data = response.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("repository"), dict):
        raise CollectionError("Repository unavailable")
    repository = data["repository"]
    if str(repository.get("nameWithOwner", "")).casefold() != repo.casefold():
        raise CollectionError("Repository identity mismatch")
    prs, more = connection(data.get("search"), SAMPLE_SIZE)
    total = data["search"].get("issueCount")
    if type(total) is not int or total < len(prs):
        raise CollectionError("Invalid history count")
    result = {
        "schemaVersion": 1, "status": "complete", "repository": repo, "viewer": viewer,
        "target": f"https://github.com/{repo}/pull/{number}" if number else None,
        "sample": {"prs": len(prs), "limit": SAMPLE_SIZE, "matchingPRs": total,
                   "moreHistory": more},
        "workspace": None, "candidates": [], "errors": [],
    }
    excluded = {viewer.casefold()}
    if number:
        target = repository.get("pullRequest")
        if (not isinstance(target, dict) or target.get("number") != number
                or target.get("state") != "OPEN"):
            raise CollectionError("Target PR unavailable or not open")
        author = human(target.get("author"))
        if not author or author.casefold() != viewer.casefold():
            raise CollectionError("Target PR must belong to the authenticated user")
        reviews, truncated = connection(target.get("reviews"), 100)
        requests, requests_truncated = connection(target.get("reviewRequests"), 100)
        if truncated or requests_truncated:
            result["errors"].append("Target reviewer data truncated")
        excluded.update(login.casefold() for node in reviews
                        if node.get("state") in STATES and (login := human(node.get("author"))))
        excluded.update(login.casefold() for node in requests
                        if (login := human(node.get("requestedReviewer"))))

    candidates = {}

    def record(reviews, key, sibling):
        for review in reviews:
            login = human(review.get("author"))
            if not login or login.casefold() in excluded or review.get("state") not in STATES:
                continue
            date = submitted_at(review.get("submittedAt"))
            row = candidates.setdefault(login.casefold(),
                                        {"login": login, "own": {}, "sibling": {}})
            bucket = row["sibling" if sibling else "own"]
            bucket[key] = max(date, bucket.get(key, ""))

    for pr_number, reviews in history(prs, repo, viewer, number, result["errors"]):
        record(reviews, pr_number, sibling=False)
    if workspace is not None:
        sampled = 0
        more_sibling_history = False
        for index, sibling in enumerate(workspace["siblings"]):
            nodes, more = connection(data.get(f"s{index}"), SIBLING_SAMPLE_SIZE)
            more_sibling_history = more_sibling_history or more
            sampled += len(nodes)
            for pr_number, reviews in history(nodes, sibling, viewer, None, result["errors"]):
                record(reviews, (sibling, pr_number), sibling=True)
        result["workspace"] = {**workspace, "prs": sampled, "moreHistory": more_sibling_history,
                               "accessChecks": 0}
    if result["errors"]:
        result["status"] = "partial"
        return result

    rows = []
    for row in candidates.values():
        own = sorted(row["own"].items(), key=lambda pair: (pair[1], pair[0]), reverse=True)
        sibling = sorted(row["sibling"].items(), key=lambda pair: (pair[1], pair[0]), reverse=True)
        examples = [f"https://github.com/{repo}/pull/{n}" for n, _ in own]
        examples += [f"https://github.com/{name}/pull/{n}" for (name, n), _ in sibling]
        rows.append({
            "login": row["login"], "reviewedPRs": len(own), "siblingPRs": len(sibling),
            "lastReviewed": max(date for _, date in own + sibling),
            "examples": examples[:3],
            "siblingRepositories": sorted({name for (name, _), _ in sibling}),
        })
    # Stable sorts express own count > sibling count > recency > login without a weighted score.
    rows.sort(key=lambda row: row["login"].casefold())
    rows.sort(key=lambda row: row["lastReviewed"], reverse=True)
    rows.sort(key=lambda row: row["siblingPRs"], reverse=True)
    rows.sort(key=lambda row: row["reviewedPRs"], reverse=True)

    checks = 0
    for row in rows:
        if len(result["candidates"]) == MAX_CANDIDATES:
            break
        if not row["reviewedPRs"]:
            # Reviewing a target PR proves access; sibling-only evidence does not.
            if checks == MAX_ACCESS_CHECKS:
                break
            checks += 1
            try:
                allowed = has_access(row["login"])
            except CollectionError as error:
                result.update(status="partial", candidates=[], errors=[str(error)])
                break
            if not allowed:
                continue
        result["candidates"].append(row)
    if result["workspace"] is not None:
        result["workspace"]["accessChecks"] = checks
    return result


class GhClient:
    def __init__(self):
        self.deadline = time.monotonic() + 90

    def execute(self, argv, cwd=None):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise CollectionError("GitHub collection deadline exceeded")
        env = os.environ.copy()
        env.pop("GH_REPO", None)
        env.pop("GH_DEBUG", None)
        env.update(GH_HOST="github.com", GH_PAGER="cat", PAGER="cat", NO_COLOR="1",
                   GH_PROMPT_DISABLED="1")
        try:
            completed = subprocess.run(argv, capture_output=True, text=True, timeout=remaining,
                                       env=env, cwd=cwd, check=False)
        except subprocess.TimeoutExpired as error:
            raise CollectionError("GitHub collection deadline exceeded") from error
        except OSError as error:
            raise CollectionError(f"{argv[0]} unavailable") from error
        if len(completed.stdout.encode()) + len(completed.stderr.encode()) > 2_000_000:
            raise CollectionError("GitHub response exceeded output limit")
        return completed

    def run(self, arguments, cwd=None):
        completed = self.execute(["gh", *arguments], cwd)
        if completed.returncode:
            raise CollectionError("GitHub request failed; check gh authentication and repository access")
        try:
            return json.loads(completed.stdout)
        except ValueError as error:
            raise CollectionError("GitHub returned invalid JSON") from error

    def has_access(self, repo, login):
        completed = self.execute(["gh", "api", "--hostname", "github.com",
                                  f"repos/{repo}/collaborators/{login}/permission"])
        try:
            body = json.loads(completed.stdout)
        except ValueError:
            body = None
        if isinstance(body, dict):
            permission = body.get("permission")
            if not completed.returncode and permission in {"admin", "write", "read"}:
                return True
            if (not completed.returncode and permission == "none") or body.get("status") == "404":
                return False
        raise CollectionError("Target repository access could not be verified for sibling reviewers")

    def checkout_repository(self, cwd=None):
        identity = self.run(["repo", "view", "--json", "nameWithOwner,url"], cwd)
        if not isinstance(identity, dict):
            raise CollectionError("Repository unavailable")
        repo = repository_name(identity.get("nameWithOwner"))
        if identity.get("url") != f"https://github.com/{repo}":
            raise CollectionError("Only GitHub.com repositories are supported")
        return repo

    def checkout_root(self):
        completed = self.execute(["git", "rev-parse", "--show-toplevel"])
        if completed.returncode or not completed.stdout.strip():
            return None
        return Path(completed.stdout.strip()).resolve()

    def siblings(self, repo, root, discover):
        """Sibling member repositories from an explicit or discovered workspace manifest."""
        checkout = None
        if root is not None:
            root = root.resolve()
            members = manifest_members(root)
            if members is None:
                raise CollectionError("Workspace manifest unavailable")
        elif discover and (checkout := self.checkout_root()):
            found = find_workspace(Path.cwd().resolve(), checkout)
            if found is None:
                return None
            root, members = found
        else:
            return None
        siblings = []
        unavailable = 0
        for member in members:
            if member == checkout:
                continue
            try:
                identity = self.checkout_repository(member)
            except CollectionError:
                unavailable += 1
                continue
            if identity.casefold() != repo.casefold() and identity not in siblings:
                siblings.append(identity)
        return {"root": str(root), "siblings": siblings[:MAX_SIBLINGS],
                "omittedSiblings": max(0, len(siblings) - MAX_SIBLINGS),
                "unavailableMembers": unavailable}

    def collect(self, repo, number, workspace_root=None):
        discovered = repo is None
        repo = self.checkout_repository() if discovered else repository_name(repo)
        workspace = self.siblings(repo, workspace_root, discovered)
        user = self.run(["api", "--hostname", "github.com", "user"])
        viewer = user.get("login") if isinstance(user, dict) else None
        if not isinstance(viewer, str) or not LOGIN.fullmatch(viewer):
            raise CollectionError("Authenticated user unavailable")
        target = ""
        if number:
            target = """pullRequest(number: $number) {
              number state author { __typename login }
              """ + REVIEW_FIELDS + """
              reviewRequests(first: 100) {
                pageInfo { hasNextPage }
                nodes { requestedReviewer { __typename ... on User { login } } }
              }
            }"""
        siblings = workspace["siblings"] if workspace else []
        query = "query($owner: String!, $name: String!, $search: String!"
        query += ", $number: Int!" if number else ""
        query += "".join(f", $s{index}: String!" for index in range(len(siblings)))
        query += ") { repository(owner: $owner, name: $name) { nameWithOwner " + target + " }"
        query += (" search(type: ISSUE, query: $search, first: 30) {"
                  " issueCount pageInfo { hasNextPage } nodes { ... on PullRequest { "
                  + PR_FIELDS + " } } }")
        for index in range(len(siblings)):
            query += (f" s{index}: search(type: ISSUE, query: $s{index},"
                      f" first: {SIBLING_SAMPLE_SIZE}) {{ pageInfo {{ hasNextPage }}"
                      " nodes { ... on PullRequest { " + PR_FIELDS + " } } }")
        query += " }"
        owner, name = repo.split("/")
        args = ["api", "--hostname", "github.com", "graphql", "-f", f"query={query}",
                "-f", f"owner={owner}", "-f", f"name={name}", "-f",
                f"search=repo:{repo} is:pr is:closed author:{viewer} sort:updated-desc"]
        for index, sibling in enumerate(siblings):
            args.extend(["-f", f"s{index}=repo:{sibling} is:pr is:closed author:{viewer}"
                               " sort:updated-desc"])
        if number:
            args.extend(["-F", f"number={number}"])
        return recommend(self.run(args), repo, viewer, number, workspace,
                         lambda login: self.has_access(repo, login))


def positive_number(value):
    if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 2_147_483_647:
        raise argparse.ArgumentTypeError("PR number must be a positive 32-bit integer")
    return int(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="One GitHub.com owner/repo; defaults to the current checkout")
    parser.add_argument("--pr", type=positive_number, help="Your open PR; omit for repository-level advice")
    parser.add_argument("--workspace", type=Path, metavar="ROOT",
                        help="Workspace root holding workspace.json or .mgit.conf; "
                             "discovered from the current checkout when --repo is omitted")
    args = parser.parse_args(argv)
    try:
        result = GhClient().collect(args.repo, args.pr, args.workspace)
    except CollectionError as error:
        result = {"schemaVersion": 1, "status": "failed", "candidates": [], "errors": [str(error)]}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
