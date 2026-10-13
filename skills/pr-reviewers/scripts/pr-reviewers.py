#!/usr/bin/env python3
"""Recommend reviewers from a bounded personal PR-history sample; GitHub reads only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import time

LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}")
STATES = {"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED"}
SAMPLE_SIZE = 30
REVIEW_FIELDS = """
reviews(first: 100) {
  pageInfo { hasNextPage }
  nodes { state submittedAt author { __typename login } }
}
"""


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


def recommend(response, repo, viewer, number=None):
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
        "candidates": [], "errors": [],
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
            result["errors"].append(f"Reviews truncated on PR #{pr_number}")
        for review in reviews:
            login = human(review.get("author"))
            if not login or login.casefold() in excluded or review.get("state") not in STATES:
                continue
            date = submitted_at(review.get("submittedAt"))
            row = candidates.setdefault(login.casefold(), {"login": login, "prs": {}})
            row["prs"][pr_number] = max(date, row["prs"].get(pr_number, ""))
    if result["errors"]:
        result["status"] = "partial"
        return result
    for row in candidates.values():
        history = sorted(row["prs"].items(), key=lambda pair: (pair[1], pair[0]), reverse=True)
        result["candidates"].append({
            "login": row["login"], "reviewedPRs": len(history), "lastReviewed": history[0][1],
            "examples": [f"https://github.com/{repo}/pull/{n}" for n, _ in history[:3]],
        })
    # Stable sorts express count > recency > login without inventing a weighted score.
    rows = result["candidates"]
    rows.sort(key=lambda row: row["login"].casefold())
    rows.sort(key=lambda row: row["lastReviewed"], reverse=True)
    rows.sort(key=lambda row: row["reviewedPRs"], reverse=True)
    result["candidates"] = rows[:5]
    return result


class GhClient:
    def __init__(self):
        self.deadline = time.monotonic() + 90

    def run(self, arguments):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise CollectionError("GitHub collection deadline exceeded")
        env = os.environ.copy()
        env.pop("GH_REPO", None)
        env.pop("GH_DEBUG", None)
        env.update(GH_HOST="github.com", GH_PAGER="cat", PAGER="cat", NO_COLOR="1",
                   GH_PROMPT_DISABLED="1")
        try:
            completed = subprocess.run(["gh", *arguments], capture_output=True, text=True,
                                       timeout=remaining, env=env, check=False)
        except subprocess.TimeoutExpired as error:
            raise CollectionError("GitHub collection deadline exceeded") from error
        except OSError as error:
            raise CollectionError("GitHub CLI unavailable") from error
        if completed.returncode:
            raise CollectionError("GitHub request failed; check gh authentication and repository access")
        if len(completed.stdout.encode()) + len(completed.stderr.encode()) > 2_000_000:
            raise CollectionError("GitHub response exceeded output limit")
        try:
            return json.loads(completed.stdout)
        except ValueError as error:
            raise CollectionError("GitHub returned invalid JSON") from error

    def collect(self, repo, number):
        if repo is None:
            identity = self.run(["repo", "view", "--json", "nameWithOwner,url"])
            if not isinstance(identity, dict):
                raise CollectionError("Repository unavailable")
            repo = repository_name(identity.get("nameWithOwner"))
            if identity.get("url") != f"https://github.com/{repo}":
                raise CollectionError("Only GitHub.com repositories are supported")
        else:
            repo = repository_name(repo)
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
        query = """query($owner: String!, $name: String!, $search: String!"""
        query += ", $number: Int!" if number else ""
        query += ") { repository(owner: $owner, name: $name) { nameWithOwner " + target + " }"
        query += """ search(type: ISSUE, query: $search, first: 30) {
          issueCount pageInfo { hasNextPage }
          nodes { ... on PullRequest {
            number state author { __typename login } repository { nameWithOwner }
            """ + REVIEW_FIELDS + " } } } }"
        owner, name = repo.split("/")
        args = ["api", "--hostname", "github.com", "graphql", "-f", f"query={query}",
                "-f", f"owner={owner}", "-f", f"name={name}", "-f",
                f"search=repo:{repo} is:pr is:closed author:{viewer} sort:updated-desc"]
        if number:
            args.extend(["-F", f"number={number}"])
        return recommend(self.run(args), repo, viewer, number)


def positive_number(value):
    if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 2_147_483_647:
        raise argparse.ArgumentTypeError("PR number must be a positive 32-bit integer")
    return int(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="One GitHub.com owner/repo; defaults to the current checkout")
    parser.add_argument("--pr", type=positive_number, help="Your open PR; omit for repository-level advice")
    args = parser.parse_args(argv)
    try:
        result = GhClient().collect(args.repo, args.pr)
    except CollectionError as error:
        result = {"schemaVersion": 1, "status": "failed", "candidates": [], "errors": [str(error)]}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
