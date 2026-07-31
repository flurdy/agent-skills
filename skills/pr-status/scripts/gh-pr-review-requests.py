#!/usr/bin/env python3
"""Collect and reduce a bounded, read-only GitHub review-request queue.

The returned state is intended for session/watch-local retention. This command never
writes state, marks notifications, submits reviews, or changes GitHub review requests.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from time import monotonic
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_OUTPUT_BYTES = 4_000_000


@dataclass(frozen=True)
class QueueLimits:
    page_size: int = 50
    max_candidates: int = 100
    max_state_entries: int = 200
    max_history: int = 200
    max_prs_per_query: int = 20

    def normalized(self) -> QueueLimits:
        return QueueLimits(
            page_size=max(1, min(100, self.page_size)),
            max_candidates=max(1, self.max_candidates),
            max_state_entries=max(1, self.max_state_entries),
            max_history=max(1, self.max_history),
            max_prs_per_query=max(1, min(50, self.max_prs_per_query)),
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "pageSize": self.page_size,
            "maxCandidates": self.max_candidates,
            "maxStateEntries": self.max_state_entries,
            "maxHistoryPerPullRequest": self.max_history,
            "maxPullRequestsPerQuery": self.max_prs_per_query,
        }


class CollectionError(RuntimeError):
    pass


def empty_state(viewer_login: str) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "viewerLogin": viewer_login,
        "sequence": 0,
        "entries": [],
    }


def entry_key(repository: str, number: int) -> str:
    return f"{repository}#{number}"


def work_key(node_id: str, request_event_id: str, head_sha: str) -> str:
    return f"{node_id}|{request_event_id}|{head_sha}"


def validate_state(state: dict[str, Any], viewer_login: str) -> None:
    if state.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("unsupported review-request state schema")
    if str(state.get("viewerLogin", "")).casefold() != viewer_login.casefold():
        raise ValueError("review-request state belongs to a different GitHub user")
    if not isinstance(state.get("entries"), list):
        raise ValueError("review-request state entries must be a list")


def latest(items: list[dict[str, Any]], timestamp: str) -> dict[str, Any] | None:
    usable = [item for item in items if isinstance(item.get(timestamp), str)]
    if not usable:
        return None
    return max(usable, key=lambda item: (item[timestamp], str(item.get("id", ""))))


def matching_request_events(
    snapshot: dict[str, Any], source: str, viewer_login: str, reviewers: set[str]
) -> list[dict[str, Any]]:
    matches = []
    for event in snapshot.get("requestEvents", []):
        if not isinstance(event, dict) or event.get("sourceKind") != source:
            continue
        reviewer = str(event.get("reviewer", ""))
        if source == "direct" and reviewer.casefold() != viewer_login.casefold():
            continue
        if source == "team" and reviewer not in reviewers:
            continue
        matches.append(event)
    return matches


def current_request_source(
    snapshot: dict[str, Any], viewer_login: str
) -> tuple[str | None, set[str], set[str]]:
    direct = set()
    teams = set()
    for request in snapshot.get("currentRequests", []):
        if not isinstance(request, dict):
            continue
        kind = request.get("sourceKind")
        reviewer = str(request.get("reviewer", ""))
        if kind == "direct" and reviewer.casefold() == viewer_login.casefold():
            direct.add(reviewer)
        elif kind == "team" and reviewer:
            teams.add(reviewer)
    if direct:
        return "direct", direct, teams
    if teams:
        return "team", teams, teams
    return None, set(), set()


def current_team_events(
    snapshot: dict[str, Any], reviewers: set[str]
) -> dict[str, dict[str, Any]]:
    events = {}
    for reviewer in reviewers:
        event = latest(
            [
                item
                for item in snapshot.get("requestEvents", [])
                if isinstance(item, dict)
                and item.get("sourceKind") == "team"
                and item.get("reviewer") == reviewer
            ],
            "createdAt",
        )
        if event:
            events[reviewer] = {
                "id": event.get("id"),
                "createdAt": event.get("createdAt"),
                "requester": event.get("requester"),
            }
    return events


def new_team_events(
    current: dict[str, dict[str, Any]], previous: dict[str, Any] | None
) -> list[tuple[str, dict[str, Any]]]:
    previous_events = previous.get("teamRequestEvents", {}) if previous else {}
    force_current = previous is None or not previous.get("currentRequested")
    changed = []
    for reviewer, event in sorted(current.items()):
        prior = previous_events.get(reviewer)
        event_is_newer = prior and (
            event.get("id") != prior.get("id")
            and str(event.get("createdAt") or "")
            > str(prior.get("createdAt") or "")
        )
        if force_current or prior is None or event_is_newer:
            changed.append((reviewer, event))
    return changed


def latest_viewer_review(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    return latest(
        [
            review
            for review in snapshot.get("viewerReviews", [])
            if isinstance(review, dict) and review.get("submittedAt")
        ],
        "submittedAt",
    )


def item_from_entry(
    entry: dict[str, Any],
    transition: str,
    *,
    actionable: bool,
    explicit_rerequest: bool,
) -> dict[str, Any]:
    request_event = None
    if entry.get("requestEventId"):
        request_event = {
            "id": entry["requestEventId"],
            "createdAt": entry.get("requestEventAt"),
            "requester": entry.get("requester"),
        }
    return {
        "key": entry["key"],
        "repository": entry["repository"],
        "number": entry["number"],
        "nodeId": entry.get("nodeId"),
        "url": entry.get("url"),
        "author": entry.get("author"),
        "state": entry.get("state"),
        "isDraft": entry.get("isDraft"),
        "headSha": entry.get("headSha"),
        "requestSource": entry.get("requestSource"),
        "requestReviewers": entry.get("requestReviewers", []),
        "teamRequests": entry.get("teamRequests", []),
        "requestEvent": request_event,
        "requestHistoryCount": entry.get("requestHistoryCount", 0),
        "reRequestCount": entry.get("reRequestCount", 0),
        "explicitReRequest": explicit_rerequest
        or bool(entry.get("explicitReRequest", False)),
        "priorReview": entry.get("priorReview"),
        "workKey": entry.get("workKey"),
        "transition": transition,
        "actionable": actionable,
    }


def team_transition_item(
    entry: dict[str, Any], reviewer: str, event: dict[str, Any]
) -> dict[str, Any]:
    team_entry = copy.deepcopy(entry)
    team_entry.update(
        {
            "requestSource": "team",
            "requestReviewers": [reviewer],
            "requestEventId": event.get("id"),
            "requestEventAt": event.get("createdAt"),
            "requester": event.get("requester"),
            "workKey": None,
        }
    )
    return item_from_entry(
        team_entry,
        "team_requested",
        actionable=False,
        explicit_rerequest=False,
    )


def terminal_transition(snapshot: dict[str, Any]) -> str | None:
    if snapshot.get("merged") is True or snapshot.get("state") == "MERGED":
        return "merged"
    if snapshot.get("state") == "CLOSED":
        return "closed"
    return None


def ended_request_transition(
    previous: dict[str, Any], review: dict[str, Any] | None
) -> str:
    previous_review = previous.get("priorReview") or {}
    review_is_new = review and review.get("id") != previous_review.get("id")
    if (
        previous.get("requestSource") == "direct"
        and review_is_new
        and previous.get("requestEventAt")
        and review.get("submittedAt", "") > previous["requestEventAt"]
    ):
        return "review_submitted"
    return "request_removed"


def prune_entries(
    entries: list[dict[str, Any]], limit: int, protected_keys: set[str]
) -> tuple[list[dict[str, Any]], set[str]]:
    if len(entries) <= limit:
        return entries, set()
    candidates = sorted(
        (entry for entry in entries if entry["key"] not in protected_keys),
        key=lambda entry: (
            0 if not entry.get("tracking", False) else 1,
            int(entry.get("observation", 0)),
            entry["key"],
        ),
    )
    remove_count = len(entries) - limit
    if len(candidates) < remove_count:
        raise ValueError("active review-request state exceeds its bounded capacity")
    removed_keys = {entry["key"] for entry in candidates[:remove_count]}
    return [entry for entry in entries if entry["key"] not in removed_keys], removed_keys


def reduce_queue(
    previous_state: dict[str, Any],
    snapshots: list[dict[str, Any]],
    *,
    viewer_login: str,
    mode: str = "normal",
    failed_repositories: set[str] | None = None,
    state_limit: int = 200,
) -> dict[str, Any]:
    if mode not in {"normal", "reset", "recheck"}:
        raise ValueError(f"unsupported queue mode: {mode}")
    validate_state(previous_state, viewer_login)
    if len(previous_state["entries"]) > max(1, state_limit):
        raise ValueError("review-request state exceeds its bounded capacity")
    state = empty_state(viewer_login) if mode == "reset" else copy.deepcopy(previous_state)
    previous_entries = {entry["key"]: entry for entry in state["entries"]}
    next_entries = copy.deepcopy(previous_entries)
    failed = failed_repositories or set()
    transitions = []
    queue = []
    errors = []
    sequence = int(state.get("sequence", 0))

    for snapshot in sorted(
        snapshots, key=lambda item: (item["repository"].casefold(), item["number"])
    ):
        repository = snapshot["repository"]
        if repository in failed:
            continue
        key = entry_key(repository, int(snapshot["number"]))
        previous = previous_entries.get(key)
        terminal = terminal_transition(snapshot)
        if snapshot.get("historyComplete") is not True:
            errors.append(
                {
                    "source": "history",
                    "repository": repository,
                    "number": snapshot["number"],
                    "kind": "truncated",
                    "message": "review-request history was incomplete",
                }
            )
            if terminal is None:
                continue

        sequence += 1
        source, reviewers, team_reviewers = current_request_source(
            snapshot, viewer_login
        )
        if terminal:
            source, reviewers, team_reviewers = None, set(), set()
        team_events = current_team_events(snapshot, team_reviewers)
        missing_team_events = team_reviewers - set(team_events)
        if missing_team_events:
            errors.append(
                {
                    "source": "history",
                    "repository": repository,
                    "number": snapshot["number"],
                    "kind": "missing",
                    "message": "one or more team requests had no bounded request event",
                }
            )
        request_events = (
            matching_request_events(snapshot, source, viewer_login, reviewers)
            if source
            else []
        )
        request_event = latest(request_events, "createdAt")
        missing_identity = source is not None and (
            not snapshot.get("nodeId")
            or not snapshot.get("headSha")
            or request_event is None
            or not request_event.get("id")
        )
        if source and (request_event is None or missing_identity):
            errors.append(
                {
                    "source": "history",
                    "repository": repository,
                    "number": snapshot["number"],
                    "kind": "missing",
                    "message": "current review request had no complete bounded identity",
                }
            )
            continue

        viewer_request_events = matching_request_events(
            snapshot, "direct", viewer_login, {viewer_login}
        )
        review = latest_viewer_review(snapshot)
        event_id = request_event.get("id") if request_event else None
        event_at = request_event.get("createdAt") if request_event else None
        current_work_key = (
            work_key(str(snapshot["nodeId"]), str(event_id), str(snapshot["headSha"]))
            if source == "direct" and event_id
            else None
        )
        prior_handled_event = previous.get("handledRequestEventId") if previous else None
        prior_handled_head = previous.get("handledHeadSha") if previous else None
        retained_source = source or (previous.get("requestSource") if previous else None)
        retained_event_id = event_id or (
            previous.get("requestEventId") if previous else None
        )
        retained_event_at = event_at or (
            previous.get("requestEventAt") if previous else None
        )
        retained_work_key = (
            current_work_key
            if source is not None
            else previous.get("workKey")
            if previous
            else None
        )
        entry = {
            "key": key,
            "repository": repository,
            "number": int(snapshot["number"]),
            "nodeId": snapshot.get("nodeId"),
            "url": snapshot.get("url"),
            "author": snapshot.get("author"),
            "state": snapshot.get("state"),
            "isDraft": bool(snapshot.get("isDraft")),
            "headSha": snapshot.get("headSha"),
            "requestSource": retained_source,
            "requestReviewers": sorted(reviewers)
            if source
            else previous.get("requestReviewers", [])
            if previous
            else [],
            "teamRequests": sorted(team_reviewers)
            if source
            else previous.get("teamRequests", [])
            if previous
            else [],
            "teamRequestEvents": team_events
            if source
            else previous.get("teamRequestEvents", {})
            if previous
            else {},
            "requestEventId": retained_event_id,
            "requestEventAt": retained_event_at,
            "requester": request_event.get("requester")
            if request_event
            else previous.get("requester")
            if previous
            else None,
            "requestHistoryCount": max(
                len(viewer_request_events),
                int(previous.get("requestHistoryCount", 0)) if previous else 0,
            ),
            "reRequestCount": max(
                max(0, len(viewer_request_events) - 1),
                int(previous.get("reRequestCount", 0)) if previous else 0,
            ),
            "explicitReRequest": len(viewer_request_events) > 1
            if source == "direct"
            else bool(previous.get("explicitReRequest", False))
            if previous
            else False,
            "priorReview": review or (previous.get("priorReview") if previous else None),
            "workKey": retained_work_key,
            "currentRequested": source is not None,
            "tracking": source is not None and terminal is None,
            "handledWorkKey": previous.get("handledWorkKey") if previous else None,
            "handledRequestEventId": prior_handled_event,
            "handledHeadSha": prior_handled_head,
            "localReviewReported": previous.get("localReviewReported", True)
            if previous
            else True,
            "observation": sequence,
        }

        transition = None
        transition_entry = entry
        extra_transitions = [
            team_transition_item(entry, reviewer, event)
            for reviewer, event in new_team_events(team_events, previous)
        ]
        explicit_rerequest = False
        if terminal:
            if previous is None or previous.get("tracking", False):
                transition = terminal
            entry["tracking"] = False
            entry["currentRequested"] = False
        elif source is None:
            if previous and previous.get("currentRequested"):
                transition = ended_request_transition(previous, review)
            entry["tracking"] = False
        elif source == "team":
            if (
                previous
                and previous.get("requestSource") == "direct"
                and previous.get("currentRequested")
            ):
                transition = ended_request_transition(previous, review)
                transition_entry = copy.deepcopy(previous)
                transition_entry.update(
                    {
                        "state": entry["state"],
                        "isDraft": entry["isDraft"],
                        "headSha": entry["headSha"],
                        "teamRequests": entry["teamRequests"],
                        "teamRequestEvents": entry["teamRequestEvents"],
                        "priorReview": review or previous.get("priorReview"),
                        "currentRequested": False,
                        "tracking": False,
                    }
                )
        else:
            history_rerequest = len(viewer_request_events) > 1
            if mode == "recheck":
                transition = "recheck"
            elif previous is None:
                transition = "re_requested" if history_rerequest else "newly_requested"
                explicit_rerequest = history_rerequest
            elif previous.get("requestSource") != "direct":
                transition = "re_requested" if history_rerequest else "newly_requested"
                explicit_rerequest = history_rerequest
                entry["explicitReRequest"] = history_rerequest
            elif previous.get("requestEventId") != event_id:
                transition = "re_requested"
                explicit_rerequest = True
                entry["explicitReRequest"] = True
            elif previous.get("isDraft") and not entry["isDraft"]:
                transition = "ready"
            elif not previous.get("isDraft") and entry["isDraft"]:
                transition = "draft"
            elif previous.get("headSha") != entry["headSha"]:
                transition = "head_changed"
            elif (
                entry.get("handledWorkKey") == current_work_key
                and not entry.get("localReviewReported", True)
            ):
                transition = "reviewed_locally"
                entry["localReviewReported"] = True

        handled_current = entry.get("handledWorkKey") == current_work_key
        head_changed_after_handled_request = (
            prior_handled_event == event_id
            and prior_handled_head is not None
            and prior_handled_head != entry.get("headSha")
        )
        actionable = (
            source == "direct"
            and terminal is None
            and not entry["isDraft"]
            and (
                mode == "recheck"
                or (not handled_current and not head_changed_after_handled_request)
            )
        )
        if transition:
            item = item_from_entry(
                transition_entry,
                transition,
                actionable=actionable if transition_entry is entry else False,
                explicit_rerequest=explicit_rerequest,
            )
            transitions.append(item)
        transitions.extend(extra_transitions)
        if actionable:
            queue.append(
                item_from_entry(
                    entry,
                    transition or "pending",
                    actionable=True,
                    explicit_rerequest=explicit_rerequest,
                )
            )
        next_entries[key] = entry

    protected_keys = {
        key
        for key in previous_entries
        if next_entries.get(key, {}).get("tracking", False)
    }
    entries, pruned_keys = prune_entries(
        list(next_entries.values()), max(1, state_limit), protected_keys
    )
    if pruned_keys:
        dropped_active_keys = {
            key for key in pruned_keys if next_entries[key].get("tracking", False)
        }
        transitions = [
            item for item in transitions if item["key"] not in dropped_active_keys
        ]
        queue = [item for item in queue if item["key"] not in dropped_active_keys]
        if dropped_active_keys:
            errors.append(
                {
                    "source": "state",
                    "kind": "state-capacity",
                    "message": "new review requests exceeded bounded session-state capacity",
                }
            )
    result_state = {
        "schemaVersion": SCHEMA_VERSION,
        "viewerLogin": viewer_login,
        "sequence": sequence,
        "entries": sorted(entries, key=lambda entry: entry["key"].casefold()),
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "partial" if errors or failed else "complete",
        "mode": mode,
        "queue": queue,
        "transitions": transitions,
        "errors": errors,
        "failedRepositories": sorted(failed),
        "state": result_state,
    }


def mark_reviewed(state: dict[str, Any], reviewed_work_key: str) -> dict[str, Any]:
    viewer_login = str(state.get("viewerLogin", ""))
    validate_state(state, viewer_login)
    updated = copy.deepcopy(state)
    for entry in updated["entries"]:
        if entry.get("workKey") != reviewed_work_key:
            continue
        if entry.get("requestSource") != "direct" or not entry.get("currentRequested"):
            raise ValueError("work key is not a current direct review request")
        entry["handledWorkKey"] = reviewed_work_key
        entry["handledRequestEventId"] = entry.get("requestEventId")
        entry["handledHeadSha"] = entry.get("headSha")
        entry["localReviewReported"] = False
        return updated
    raise ValueError("work key is not present in review-request state")


class GhClient:
    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        self.deadline = monotonic() + max(0.1, timeout)
        self.max_output_bytes = max(1_000, max_output_bytes)
        self._viewer_login: str | None = None

    def _run(self, arguments: list[str]) -> Any:
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise CollectionError("GitHub collection deadline exceeded")
        environment = os.environ.copy()
        environment.update({"GH_PAGER": "cat", "PAGER": "cat", "NO_COLOR": "1"})
        try:
            completed = subprocess.run(
                ["gh", "api", *arguments],
                check=False,
                capture_output=True,
                text=True,
                timeout=remaining,
                env=environment,
            )
        except subprocess.TimeoutExpired as error:
            raise CollectionError("GitHub collection deadline exceeded") from error
        output_bytes = len(completed.stdout.encode()) + len(completed.stderr.encode())
        if output_bytes > self.max_output_bytes:
            raise CollectionError("GitHub response exceeded the output limit")
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "gh api failed"
            raise CollectionError(message[:500])
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise CollectionError(f"gh api returned invalid JSON: {error}") from error

    def viewer_login(self) -> str:
        response = self._run(["user"])
        login = response.get("login") if isinstance(response, dict) else None
        if not isinstance(login, str) or not login:
            raise CollectionError("GitHub viewer login was unavailable")
        self._viewer_login = login
        return login

    def search_page(self, viewer: str, after: str | None, first: int) -> dict[str, Any]:
        query = """
        query($searchQuery: String!, $first: Int!, $after: String) {
          search(type: ISSUE, query: $searchQuery, first: $first, after: $after) {
            nodes {
              ... on PullRequest {
                number
                repository { nameWithOwner }
              }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
        """
        arguments = [
            "graphql",
            "-f",
            f"query={query}",
            "-f",
            f"searchQuery=review-requested:{viewer} is:pr is:open archived:false",
            "-F",
            f"first={first}",
        ]
        if after:
            arguments.extend(["-f", f"after={after}"])
        response = self._run(arguments)
        if isinstance(response, dict) and response.get("errors"):
            raise CollectionError(graphql_error_message(response["errors"]))
        try:
            connection = response["data"]["search"]
        except (KeyError, TypeError) as error:
            raise CollectionError("GitHub search response was incomplete") from error
        nodes = []
        for node in connection.get("nodes") or []:
            try:
                nodes.append(
                    {
                        "repository": node["repository"]["nameWithOwner"],
                        "number": int(node["number"]),
                    }
                )
            except (KeyError, TypeError, ValueError) as error:
                raise CollectionError("GitHub search returned an invalid pull request") from error
        return {"nodes": nodes, "pageInfo": connection.get("pageInfo") or {}}

    def fetch_repository(
        self,
        repository: str,
        numbers: list[int],
        *,
        page_size: int,
        max_history: int,
        max_prs_per_query: int,
    ) -> list[dict[str, Any]]:
        owner, repo = split_repository(repository)
        snapshots = []
        connection_page_size = min(page_size, max_history)
        for start in range(0, len(numbers), max_prs_per_query):
            batch = numbers[start : start + max_prs_per_query]
            response = self._fetch_initial_batch(
                owner, repo, batch, connection_page_size
            )
            for index, number in enumerate(batch):
                pull_request = response.get(f"pr{index}")
                if not isinstance(pull_request, dict):
                    raise CollectionError(f"{repository}#{number} was unavailable")
                complete = True
                for connection_name in ("reviewRequests", "timelineItems"):
                    connection = pull_request.get(connection_name)
                    if not isinstance(connection, dict):
                        raise CollectionError(
                            f"{repository}#{number} {connection_name} was unavailable"
                        )
                    nodes, connection_complete = self._complete_connection(
                        owner,
                        repo,
                        number,
                        connection_name,
                        connection,
                        connection_page_size,
                        max_history,
                    )
                    pull_request[connection_name] = {"nodes": nodes}
                    complete = complete and connection_complete
                if self._viewer_login is None:
                    raise CollectionError("GitHub viewer login was not resolved")
                snapshots.append(
                    normalize_pull_request(
                        repository,
                        pull_request,
                        complete,
                        self._viewer_login,
                    )
                )
        return snapshots

    def _fetch_initial_batch(
        self, owner: str, repo: str, numbers: list[int], page_size: int
    ) -> dict[str, Any]:
        aliases = []
        for index, number in enumerate(numbers):
            aliases.append(
                f"pr{index}: pullRequest(number: {number}) {{ {PULL_REQUEST_FIELDS} }}"
            )
        query = f"""
        query($owner: String!, $repo: String!, $pageSize: Int!) {{
          repository(owner: $owner, name: $repo) {{
            {''.join(aliases)}
          }}
        }}
        """
        response = self._run(
            [
                "graphql",
                "-f",
                f"query={query}",
                "-f",
                f"owner={owner}",
                "-f",
                f"repo={repo}",
                "-F",
                f"pageSize={page_size}",
            ]
        )
        if isinstance(response, dict) and response.get("errors"):
            raise CollectionError(graphql_error_message(response["errors"]))
        try:
            repository = response["data"]["repository"]
        except (KeyError, TypeError) as error:
            raise CollectionError(f"{owner}/{repo} response was incomplete") from error
        if not isinstance(repository, dict):
            raise CollectionError(f"{owner}/{repo} was unavailable")
        return repository

    def _complete_connection(
        self,
        owner: str,
        repo: str,
        number: int,
        connection_name: str,
        initial: dict[str, Any],
        page_size: int,
        maximum: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        nodes = [node for node in initial.get("nodes") or [] if isinstance(node, dict)]
        initial_overflow = len(nodes) > maximum
        page_info = initial.get("pageInfo") or {}
        while page_info.get("hasNextPage") and len(nodes) < maximum:
            cursor = page_info.get("endCursor")
            if not isinstance(cursor, str) or not cursor:
                return nodes[:maximum], False
            page = self._fetch_connection_page(
                owner,
                repo,
                number,
                connection_name,
                cursor,
                min(page_size, maximum - len(nodes)),
            )
            nodes.extend(
                node for node in page.get("nodes") or [] if isinstance(node, dict)
            )
            page_info = page.get("pageInfo") or {}
        return (
            nodes[:maximum],
            not initial_overflow and not bool(page_info.get("hasNextPage")),
        )

    def _fetch_connection_page(
        self,
        owner: str,
        repo: str,
        number: int,
        connection_name: str,
        after: str,
        page_size: int,
    ) -> dict[str, Any]:
        fields = CONNECTION_FIELDS[connection_name]
        query = f"""
        query($owner: String!, $repo: String!, $number: Int!, $pageSize: Int!, $after: String!) {{
          repository(owner: $owner, name: $repo) {{
            pullRequest(number: $number) {{
              {connection_name}(first: $pageSize, after: $after){fields}
            }}
          }}
        }}
        """
        response = self._run(
            [
                "graphql",
                "-f",
                f"query={query}",
                "-f",
                f"owner={owner}",
                "-f",
                f"repo={repo}",
                "-F",
                f"number={number}",
                "-F",
                f"pageSize={page_size}",
                "-f",
                f"after={after}",
            ]
        )
        if isinstance(response, dict) and response.get("errors"):
            raise CollectionError(graphql_error_message(response["errors"]))
        try:
            connection = response["data"]["repository"]["pullRequest"][connection_name]
        except (KeyError, TypeError) as error:
            raise CollectionError(
                f"{owner}/{repo}#{number} {connection_name} page was incomplete"
            ) from error
        if not isinstance(connection, dict):
            raise CollectionError(
                f"{owner}/{repo}#{number} {connection_name} page was invalid"
            )
        return connection


REVIEWER_FIELDS = """
{
  __typename
  ... on User { id login }
  ... on Bot { id login }
  ... on Mannequin { id login }
  ... on Team { id name slug organization { login } }
  ... on EnterpriseTeam { id }
}
"""

REVIEW_REQUEST_FIELDS = f"""
{{
  nodes {{ id requestedReviewer {REVIEWER_FIELDS} }}
  pageInfo {{ hasNextPage endCursor }}
}}
"""

TIMELINE_FIELDS = f"""
{{
  nodes {{
    __typename
    ... on ReviewRequestedEvent {{
      id createdAt actor {{ login }} requestedReviewer {REVIEWER_FIELDS}
    }}
    ... on PullRequestReview {{
      id submittedAt state author {{ login }} commit {{ oid }}
    }}
  }}
  pageInfo {{ hasNextPage endCursor }}
}}
"""

CONNECTION_FIELDS = {
    "reviewRequests": REVIEW_REQUEST_FIELDS,
    "timelineItems": TIMELINE_FIELDS,
}

PULL_REQUEST_FIELDS = f"""
  id
  number
  url
  state
  isDraft
  merged
  headRefOid
  author {{ login }}
  reviewRequests(first: $pageSize) {REVIEW_REQUEST_FIELDS}
  timelineItems(
    first: $pageSize
    itemTypes: [
      REVIEW_REQUESTED_EVENT
      PULL_REQUEST_REVIEW
    ]
  ) {TIMELINE_FIELDS}
"""


def graphql_error_message(errors: Any) -> str:
    if not isinstance(errors, list):
        return "GitHub GraphQL request failed"
    return "; ".join(
        str(error.get("message", "GraphQL error"))
        if isinstance(error, dict)
        else str(error)
        for error in errors
    )[:500]


def split_repository(repository: str) -> tuple[str, str]:
    parts = repository.split("/", 1)
    if len(parts) != 2 or not all(parts):
        raise CollectionError(f"invalid repository identity: {repository}")
    return parts[0], parts[1]


def reviewer_identity(reviewer: Any) -> tuple[str, str] | None:
    if not isinstance(reviewer, dict):
        return None
    typename = reviewer.get("__typename")
    if typename == "User":
        login = reviewer.get("login")
        return ("direct", str(login)) if login else None
    if typename == "Team":
        organization = reviewer.get("organization") or {}
        owner = organization.get("login")
        slug = reviewer.get("slug") or reviewer.get("name")
        if slug:
            return "team", f"{owner}/{slug}" if owner else str(slug)
    if typename == "EnterpriseTeam":
        identifier = reviewer.get("id")
        if identifier:
            return "team", f"enterprise-team:{identifier}"
    login = reviewer.get("login")
    if login:
        return "other", str(login)
    return None


def normalize_pull_request(
    repository: str,
    pull_request: dict[str, Any],
    history_complete: bool,
    viewer_login: str,
) -> dict[str, Any]:
    current_requests = []
    for request in pull_request.get("reviewRequests", {}).get("nodes", []):
        identity = reviewer_identity(request.get("requestedReviewer"))
        if identity:
            current_requests.append(
                {"sourceKind": identity[0], "reviewer": identity[1]}
            )

    request_events = []
    viewer_reviews = []
    timeline_nodes = pull_request.get("timelineItems", {}).get("nodes", [])
    for event in timeline_nodes:
        typename = event.get("__typename")
        if typename == "ReviewRequestedEvent":
            identity = reviewer_identity(event.get("requestedReviewer"))
            if not identity:
                continue
            request_events.append(
                {
                    "id": event.get("id"),
                    "createdAt": event.get("createdAt"),
                    "sourceKind": identity[0],
                    "reviewer": identity[1],
                    "requester": (event.get("actor") or {}).get("login"),
                }
            )
        elif typename == "PullRequestReview" and event.get("submittedAt"):
            author = (event.get("author") or {}).get("login")
            if not isinstance(author, str) or author.casefold() != viewer_login.casefold():
                continue
            viewer_reviews.append(
                {
                    "id": event.get("id"),
                    "author": author,
                    "submittedAt": event.get("submittedAt"),
                    "state": event.get("state"),
                    "headSha": (event.get("commit") or {}).get("oid"),
                }
            )

    return {
        "repository": repository,
        "number": int(pull_request["number"]),
        "nodeId": pull_request.get("id"),
        "url": pull_request.get("url"),
        "author": (pull_request.get("author") or {}).get("login"),
        "state": pull_request.get("state"),
        "isDraft": bool(pull_request.get("isDraft")),
        "merged": bool(pull_request.get("merged")),
        "headSha": pull_request.get("headRefOid"),
        "currentRequests": current_requests,
        "requestEvents": request_events,
        "viewerReviews": viewer_reviews,
        "historyComplete": history_complete,
    }


def tracked_targets(state: dict[str, Any]) -> dict[str, set[int]]:
    targets: dict[str, set[int]] = {}
    for entry in state.get("entries", []):
        if entry.get("tracking"):
            targets.setdefault(entry["repository"], set()).add(int(entry["number"]))
    return targets


def collect_queue(
    client: Any,
    *,
    previous_state: dict[str, Any] | None = None,
    mode: str = "normal",
    limits: QueueLimits | None = None,
) -> dict[str, Any]:
    limits = (limits or QueueLimits()).normalized()
    try:
        viewer_login = client.viewer_login()
    except (CollectionError, RuntimeError) as error:
        state = previous_state or empty_state("")
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "failed",
            "mode": mode,
            "viewerLogin": None,
            "queue": [],
            "transitions": [],
            "errors": [
                {"source": "viewer", "kind": "unavailable", "message": str(error)}
            ],
            "failedRepositories": [],
            "limits": limits.as_dict(),
            "state": state,
        }

    prior = previous_state or empty_state(viewer_login)
    try:
        validate_state(prior, viewer_login)
        if len(prior["entries"]) > limits.max_state_entries:
            raise ValueError("review-request state exceeds its bounded capacity")
    except ValueError as error:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "failed",
            "mode": mode,
            "viewerLogin": viewer_login,
            "queue": [],
            "transitions": [],
            "errors": [
                {"source": "state", "kind": "invalid", "message": str(error)}
            ],
            "failedRepositories": [],
            "limits": limits.as_dict(),
            "state": prior,
        }
    collection_state = empty_state(viewer_login) if mode == "reset" else prior
    targets = tracked_targets(collection_state)
    errors = []
    after = None
    candidate_count = 0
    search_failed = False
    while candidate_count < limits.max_candidates:
        first = min(limits.page_size, limits.max_candidates - candidate_count)
        try:
            page = client.search_page(viewer_login, after, first)
        except (CollectionError, RuntimeError) as error:
            errors.append(
                {"source": "search", "kind": "unavailable", "message": str(error)}
            )
            search_failed = True
            break
        nodes = page.get("nodes")
        page_info = page.get("pageInfo")
        if not isinstance(nodes, list) or not isinstance(page_info, dict):
            errors.append(
                {
                    "source": "search",
                    "kind": "invalid",
                    "message": "GitHub search page was malformed",
                }
            )
            search_failed = True
            break
        for node in nodes:
            try:
                repository = str(node["repository"])
                number = int(node["number"])
            except (KeyError, TypeError, ValueError):
                errors.append(
                    {
                        "source": "search",
                        "kind": "invalid",
                        "message": "GitHub search item was malformed",
                    }
                )
                search_failed = True
                continue
            targets.setdefault(repository, set()).add(number)
        candidate_count += len(nodes)
        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")
        if not isinstance(after, str) or not after:
            errors.append(
                {
                    "source": "search",
                    "kind": "invalid",
                    "message": "GitHub search pagination cursor was unavailable",
                }
            )
            search_failed = True
            break
    else:
        errors.append(
            {
                "source": "search",
                "kind": "truncated",
                "message": f"candidate search exceeded {limits.max_candidates} pull requests",
            }
        )

    snapshots = []
    failed_repositories = set()
    for repository in sorted(targets, key=str.casefold):
        numbers = sorted(targets[repository])
        try:
            fetched = client.fetch_repository(
                repository,
                numbers,
                page_size=limits.page_size,
                max_history=limits.max_history,
                max_prs_per_query=limits.max_prs_per_query,
            )
            found = {int(item["number"]) for item in fetched}
            if found != set(numbers):
                raise CollectionError("one or more requested pull requests were unavailable")
            snapshots.extend(fetched)
        except (CollectionError, RuntimeError) as error:
            failed_repositories.add(repository)
            errors.append(
                {
                    "source": "pull-requests",
                    "repository": repository,
                    "kind": "unavailable",
                    "message": str(error),
                }
            )

    reduced = reduce_queue(
        prior,
        snapshots,
        viewer_login=viewer_login,
        mode=mode,
        failed_repositories=failed_repositories,
        state_limit=limits.max_state_entries,
    )
    reduced["viewerLogin"] = viewer_login
    reduced["limits"] = limits.as_dict()
    reduced["errors"] = errors + reduced["errors"]
    reduced["failedRepositories"] = sorted(failed_repositories)
    if reduced["errors"]:
        reduced["status"] = (
            "failed"
            if search_failed and not snapshots and not collection_state.get("entries")
            else "partial"
        )
    return reduced


def parse_state(arguments: argparse.Namespace) -> dict[str, Any] | None:
    if arguments.state_json and arguments.state_stdin:
        raise ValueError("choose either --state-json or --state-stdin")
    raw = sys.stdin.read() if arguments.state_stdin else arguments.state_json
    if raw is None:
        return None
    try:
        state = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"state was not valid JSON: {error}") from error
    if not isinstance(state, dict):
        raise ValueError("state must be a JSON object")
    return state


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-json")
    parser.add_argument("--state-stdin", action="store_true")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--reset", action="store_true")
    modes.add_argument("--recheck", action="store_true")
    parser.add_argument("--mark-reviewed", metavar="WORK_KEY")
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--max-candidates", type=int, default=100)
    parser.add_argument("--max-state-entries", type=int, default=200)
    parser.add_argument("--max-history", type=int, default=200)
    parser.add_argument("--max-prs-per-query", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-output-bytes", type=int, default=DEFAULT_MAX_OUTPUT_BYTES)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    arguments = parse_args(argv)
    try:
        state = parse_state(arguments)
        if arguments.mark_reviewed:
            if state is None:
                raise ValueError("--mark-reviewed requires session state")
            result = {
                "schemaVersion": SCHEMA_VERSION,
                "status": "complete",
                "mode": "mark-reviewed",
                "state": mark_reviewed(state, arguments.mark_reviewed),
            }
        else:
            mode = "reset" if arguments.reset else "recheck" if arguments.recheck else "normal"
            result = collect_queue(
                GhClient(
                    timeout=arguments.timeout,
                    max_output_bytes=arguments.max_output_bytes,
                ),
                previous_state=state,
                mode=mode,
                limits=QueueLimits(
                    page_size=arguments.page_size,
                    max_candidates=arguments.max_candidates,
                    max_state_entries=arguments.max_state_entries,
                    max_history=arguments.max_history,
                    max_prs_per_query=arguments.max_prs_per_query,
                ),
            )
    except ValueError as error:
        result = {
            "schemaVersion": SCHEMA_VERSION,
            "status": "failed",
            "mode": "invalid",
            "errors": [{"source": "arguments", "kind": "invalid", "message": str(error)}],
        }
    json.dump(result, sys.stdout, indent=2 if arguments.pretty else None, sort_keys=True)
    sys.stdout.write("\n")
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
