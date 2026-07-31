from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any


SCRIPT = Path(__file__).parents[1] / "scripts" / "gh-pr-review-requests.py"
SPEC = importlib.util.spec_from_file_location("gh_pr_review_requests", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {SCRIPT}")
QUEUE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = QUEUE
SPEC.loader.exec_module(QUEUE)

HEAD_A = "a" * 40
HEAD_B = "b" * 40


def request_event(
    event_id: str,
    created_at: str,
    *,
    kind: str = "direct",
    reviewer: str = "ivar",
    requester: str = "alice",
) -> dict[str, Any]:
    return {
        "id": event_id,
        "createdAt": created_at,
        "sourceKind": kind,
        "reviewer": reviewer,
        "requester": requester,
    }


def snapshot(
    repository: str = "acme/widgets",
    number: int = 42,
    *,
    node_id: str | None = None,
    head: str = HEAD_A,
    state: str = "OPEN",
    draft: bool = False,
    merged: bool = False,
    current_kind: str | None = "direct",
    current_reviewer: str = "ivar",
    events: list[dict[str, Any]] | None = None,
    reviews: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    current_requests = []
    if current_kind is not None:
        current_requests.append(
            {
                "sourceKind": current_kind,
                "reviewer": current_reviewer,
            }
        )
    return {
        "repository": repository,
        "number": number,
        "nodeId": node_id or f"PR_{repository}_{number}",
        "url": f"https://github.com/{repository}/pull/{number}",
        "author": "alice",
        "state": state,
        "isDraft": draft,
        "merged": merged,
        "headSha": head,
        "currentRequests": current_requests,
        "requestEvents": events
        if events is not None
        else [request_event(f"REQ_{repository}_{number}", "2026-07-30T10:00:00Z")],
        "viewerReviews": reviews or [],
        "historyComplete": True,
    }


def transition_names(result: dict[str, Any]) -> list[str]:
    return [item["transition"] for item in result["transitions"]]


class FakeClient:
    def __init__(
        self,
        *,
        pages: dict[str | None, dict[str, Any]],
        snapshots: dict[str, dict[str, Any]],
        failures: set[str] | None = None,
    ) -> None:
        self.pages = pages
        self.snapshots = snapshots
        self.failures = failures or set()
        self.search_calls: list[str | None] = []
        self.repository_calls: list[tuple[str, tuple[int, ...]]] = []
        self.viewer_calls = 0

    def viewer_login(self) -> str:
        self.viewer_calls += 1
        return "ivar"

    def search_page(self, viewer: str, after: str | None, first: int) -> dict[str, Any]:
        self.search_calls.append(after)
        return self.pages[after]

    def fetch_repository(
        self,
        repository: str,
        numbers: list[int],
        *,
        page_size: int,
        max_history: int,
        max_prs_per_query: int,
    ) -> list[dict[str, Any]]:
        self.repository_calls.append((repository, tuple(numbers)))
        if repository in self.failures:
            raise RuntimeError(f"{repository} unavailable")
        return [self.snapshots[f"{repository}#{number}"] for number in numbers]


class QueueTransitionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.empty = QUEUE.empty_state("ivar")

    def test_direct_requests_use_repository_qualified_work_identity(self) -> None:
        snapshots = [
            snapshot("acme/widgets", 42, node_id="PR_A"),
            snapshot("other/widgets", 42, node_id="PR_B"),
        ]

        result = QUEUE.reduce_queue(self.empty, snapshots, viewer_login="ivar")

        self.assertEqual("complete", result["status"])
        self.assertEqual(["newly_requested", "newly_requested"], transition_names(result))
        self.assertEqual(2, len(result["queue"]))
        self.assertEqual(
            {"acme/widgets#42", "other/widgets#42"},
            {item["key"] for item in result["queue"]},
        )
        self.assertEqual(2, len({item["workKey"] for item in result["queue"]}))
        self.assertTrue(all(item["requestSource"] == "direct" for item in result["queue"]))

        repeated = QUEUE.reduce_queue(
            result["state"], snapshots, viewer_login="ivar"
        )
        self.assertEqual([], repeated["transitions"])
        self.assertEqual(
            {item["workKey"] for item in result["queue"]},
            {item["workKey"] for item in repeated["queue"]},
        )
        self.assertTrue(all(item["transition"] == "pending" for item in repeated["queue"]))

    def test_incomplete_history_or_identity_is_partial_and_not_queued(self) -> None:
        incomplete = snapshot()
        incomplete["historyComplete"] = False
        missing_identity = snapshot("other/widgets", 7)
        missing_identity["headSha"] = None

        result = QUEUE.reduce_queue(
            self.empty,
            [incomplete, missing_identity],
            viewer_login="ivar",
        )

        self.assertEqual("partial", result["status"])
        self.assertEqual([], result["queue"])
        self.assertEqual([], result["state"]["entries"])
        self.assertEqual(
            {"truncated", "missing"},
            {error["kind"] for error in result["errors"]},
        )

    def test_direct_request_reports_coexisting_team_requests_separately(self) -> None:
        current = snapshot()
        current["currentRequests"].append(
            {"sourceKind": "team", "reviewer": "acme/platform"}
        )

        result = QUEUE.reduce_queue(
            self.empty,
            [current],
            viewer_login="ivar",
        )

        self.assertEqual("direct", result["queue"][0]["requestSource"])
        self.assertEqual(["acme/platform"], result["queue"][0]["teamRequests"])

    def test_team_requests_are_reported_but_not_actionable(self) -> None:
        team_event = request_event(
            "TEAM_REQ",
            "2026-07-30T10:00:00Z",
            kind="team",
            reviewer="acme/platform",
        )

        result = QUEUE.reduce_queue(
            self.empty,
            [
                snapshot(
                    current_kind="team",
                    current_reviewer="acme/platform",
                    events=[team_event],
                )
            ],
            viewer_login="ivar",
        )

        self.assertEqual([], result["queue"])
        self.assertEqual(["team_requested"], transition_names(result))
        self.assertEqual("team", result["transitions"][0]["requestSource"])
        self.assertFalse(result["transitions"][0]["actionable"])

    def test_source_changes_do_not_create_false_rerequests_or_team_requests(self) -> None:
        direct_event = request_event("DIRECT_REQ", "2026-07-30T10:00:00Z")
        team_event = request_event(
            "TEAM_REQ",
            "2026-07-30T09:00:00Z",
            kind="team",
            reviewer="acme/platform",
        )
        both = snapshot(events=[team_event, direct_event])
        both["currentRequests"].append(
            {"sourceKind": "team", "reviewer": "acme/platform"}
        )
        initial_direct = QUEUE.reduce_queue(
            self.empty,
            [both],
            viewer_login="ivar",
        )
        team_only = snapshot(
            current_kind="team",
            current_reviewer="acme/platform",
            events=[team_event, direct_event],
        )

        direct_removed = QUEUE.reduce_queue(
            initial_direct["state"],
            [team_only],
            viewer_login="ivar",
        )

        self.assertEqual(["request_removed"], transition_names(direct_removed))
        self.assertEqual("direct", direct_removed["transitions"][0]["requestSource"])
        self.assertEqual(
            "team",
            direct_removed["state"]["entries"][0]["requestSource"],
        )

        initial_team = QUEUE.reduce_queue(
            self.empty,
            [team_only],
            viewer_login="ivar",
        )
        direct_after_team = QUEUE.reduce_queue(
            initial_team["state"],
            [both],
            viewer_login="ivar",
        )

        self.assertEqual(["newly_requested"], transition_names(direct_after_team))
        self.assertFalse(direct_after_team["queue"][0]["explicitReRequest"])
        self.assertEqual(0, direct_after_team["queue"][0]["reRequestCount"])

        removed_state = QUEUE.reduce_queue(
            initial_direct["state"],
            [snapshot(current_kind=None, events=[direct_event])],
            viewer_login="ivar",
        )
        later_team = QUEUE.reduce_queue(
            removed_state["state"],
            [team_only],
            viewer_login="ivar",
        )
        self.assertEqual(["team_requested"], transition_names(later_team))

    def test_team_changes_are_reported_while_direct_request_remains_current(self) -> None:
        initial = QUEUE.reduce_queue(
            self.empty,
            [snapshot()],
            viewer_login="ivar",
        )
        handled = QUEUE.mark_reviewed(
            initial["state"], initial["queue"][0]["workKey"]
        )
        settled = QUEUE.reduce_queue(
            handled,
            [snapshot()],
            viewer_login="ivar",
        )["state"]
        team_event = request_event(
            "TEAM_REQ",
            "2026-07-30T11:00:00Z",
            kind="team",
            reviewer="acme/platform",
        )
        with_team = snapshot(
            events=[
                request_event(
                    "REQ_acme/widgets_42",
                    "2026-07-30T10:00:00Z",
                ),
                team_event,
            ]
        )
        with_team["currentRequests"].append(
            {"sourceKind": "team", "reviewer": "acme/platform"}
        )

        result = QUEUE.reduce_queue(
            settled,
            [with_team],
            viewer_login="ivar",
        )

        self.assertEqual(["team_requested"], transition_names(result))
        self.assertEqual("team", result["transitions"][0]["requestSource"])
        self.assertEqual("TEAM_REQ", result["transitions"][0]["requestEvent"]["id"])
        self.assertEqual([], result["queue"])

    def test_newer_team_event_survives_direct_request_removal(self) -> None:
        direct_event = request_event("DIRECT_REQ", "2026-07-30T10:00:00Z")
        first_team_event = request_event(
            "TEAM_REQ_1",
            "2026-07-30T09:00:00Z",
            kind="team",
            reviewer="acme/platform",
        )
        both = snapshot(events=[first_team_event, direct_event])
        both["currentRequests"].append(
            {"sourceKind": "team", "reviewer": "acme/platform"}
        )
        initial = QUEUE.reduce_queue(
            self.empty,
            [both],
            viewer_login="ivar",
        )
        second_team_event = request_event(
            "TEAM_REQ_2",
            "2026-07-30T12:00:00Z",
            kind="team",
            reviewer="acme/platform",
        )
        team_only = snapshot(
            current_kind="team",
            current_reviewer="acme/platform",
            events=[direct_event, first_team_event, second_team_event],
        )

        result = QUEUE.reduce_queue(
            initial["state"],
            [team_only],
            viewer_login="ivar",
        )

        self.assertEqual(
            ["request_removed", "team_requested"],
            transition_names(result),
        )
        self.assertEqual(
            "TEAM_REQ_2",
            result["transitions"][1]["requestEvent"]["id"],
        )

    def test_removing_one_of_multiple_team_requests_is_not_a_new_request(self) -> None:
        team_a = request_event(
            "TEAM_A",
            "2026-07-30T09:00:00Z",
            kind="team",
            reviewer="acme/platform",
        )
        team_b = request_event(
            "TEAM_B",
            "2026-07-30T10:00:00Z",
            kind="team",
            reviewer="acme/security",
        )
        both = snapshot(
            current_kind="team",
            current_reviewer="acme/platform",
            events=[team_a, team_b],
        )
        both["currentRequests"].append(
            {"sourceKind": "team", "reviewer": "acme/security"}
        )
        initial = QUEUE.reduce_queue(
            self.empty,
            [both],
            viewer_login="ivar",
        )
        only_a = snapshot(
            current_kind="team",
            current_reviewer="acme/platform",
            events=[team_a, team_b],
        )

        result = QUEUE.reduce_queue(
            initial["state"],
            [only_a],
            viewer_login="ivar",
        )

        self.assertEqual([], result["transitions"])
        self.assertEqual([], result["queue"])
        self.assertEqual(
            ["acme/platform"],
            result["state"]["entries"][0]["requestReviewers"],
        )

    def test_draft_becoming_ready_is_newly_actionable(self) -> None:
        initial = QUEUE.reduce_queue(
            self.empty,
            [snapshot(draft=True)],
            viewer_login="ivar",
        )
        self.assertEqual([], initial["queue"])

        ready = QUEUE.reduce_queue(
            initial["state"],
            [snapshot(draft=False)],
            viewer_login="ivar",
        )

        self.assertEqual(["ready"], transition_names(ready))
        self.assertEqual(1, len(ready["queue"]))
        self.assertTrue(ready["queue"][0]["actionable"])

    def test_removed_and_submitted_reviews_are_distinct(self) -> None:
        initial = QUEUE.reduce_queue(
            self.empty,
            [snapshot()],
            viewer_login="ivar",
        )
        removed = QUEUE.reduce_queue(
            initial["state"],
            [snapshot(current_kind=None)],
            viewer_login="ivar",
        )
        self.assertEqual(["request_removed"], transition_names(removed))
        self.assertEqual(
            "REQ_acme/widgets_42",
            removed["transitions"][0]["requestEvent"]["id"],
        )

        review = {
            "id": "REVIEW_1",
            "submittedAt": "2026-07-30T11:00:00Z",
            "state": "APPROVED",
            "headSha": HEAD_A,
        }
        submitted = QUEUE.reduce_queue(
            initial["state"],
            [snapshot(current_kind=None, reviews=[review])],
            viewer_login="ivar",
        )
        self.assertEqual(["review_submitted"], transition_names(submitted))
        self.assertEqual("APPROVED", submitted["transitions"][0]["priorReview"]["state"])

        already_observed = QUEUE.reduce_queue(
            self.empty,
            [snapshot(reviews=[review])],
            viewer_login="ivar",
        )
        later_removed = QUEUE.reduce_queue(
            already_observed["state"],
            [snapshot(current_kind=None, reviews=[review])],
            viewer_login="ivar",
        )
        self.assertEqual(["request_removed"], transition_names(later_removed))

    def test_explicit_rerequest_requires_a_new_request_event(self) -> None:
        first_event = request_event("REQ_1", "2026-07-30T10:00:00Z")
        second_event = request_event("REQ_2", "2026-07-30T12:00:00Z", requester="bob")
        initial = QUEUE.reduce_queue(
            self.empty,
            [snapshot(events=[first_event])],
            viewer_login="ivar",
        )

        rerequested = QUEUE.reduce_queue(
            initial["state"],
            [snapshot(events=[first_event, second_event])],
            viewer_login="ivar",
        )

        self.assertEqual(["re_requested"], transition_names(rerequested))
        item = rerequested["queue"][0]
        self.assertTrue(item["explicitReRequest"])
        self.assertEqual("REQ_2", item["requestEvent"]["id"])
        self.assertEqual("bob", item["requestEvent"]["requester"])
        self.assertEqual(1, item["reRequestCount"])

    def test_head_change_is_not_an_explicit_rerequest(self) -> None:
        initial = QUEUE.reduce_queue(
            self.empty,
            [snapshot()],
            viewer_login="ivar",
        )
        work_key = initial["queue"][0]["workKey"]
        handled = QUEUE.mark_reviewed(initial["state"], work_key)

        changed = QUEUE.reduce_queue(
            handled,
            [snapshot(head=HEAD_B)],
            viewer_login="ivar",
        )

        self.assertEqual(["head_changed"], transition_names(changed))
        self.assertFalse(changed["transitions"][0]["explicitReRequest"])
        self.assertFalse(changed["transitions"][0]["actionable"])
        self.assertEqual([], changed["queue"])

    def test_local_review_is_reported_once_and_handled_work_does_not_reappear(self) -> None:
        initial = QUEUE.reduce_queue(
            self.empty,
            [snapshot()],
            viewer_login="ivar",
        )
        work_key = initial["queue"][0]["workKey"]
        handled = QUEUE.mark_reviewed(initial["state"], work_key)

        first_poll = QUEUE.reduce_queue(
            handled,
            [snapshot()],
            viewer_login="ivar",
        )
        second_poll = QUEUE.reduce_queue(
            first_poll["state"],
            [snapshot()],
            viewer_login="ivar",
        )

        self.assertEqual(["reviewed_locally"], transition_names(first_poll))
        self.assertEqual([], first_poll["queue"])
        self.assertEqual([], second_poll["transitions"])
        self.assertEqual([], second_poll["queue"])

    def test_closed_and_merged_requests_become_terminal(self) -> None:
        initial = QUEUE.reduce_queue(
            self.empty,
            [snapshot()],
            viewer_login="ivar",
        )
        scenarios = {
            "closed": snapshot(state="CLOSED", current_kind=None),
            "merged": snapshot(state="MERGED", merged=True, current_kind=None),
        }
        for expected, current in scenarios.items():
            with self.subTest(expected=expected):
                result = QUEUE.reduce_queue(
                    initial["state"],
                    [current],
                    viewer_login="ivar",
                )
                self.assertEqual([expected], transition_names(result))
                self.assertEqual([], result["queue"])
                self.assertFalse(result["state"]["entries"][0]["tracking"])

    def test_incomplete_history_still_records_a_terminal_transition(self) -> None:
        initial = QUEUE.reduce_queue(
            self.empty,
            [snapshot()],
            viewer_login="ivar",
        )
        closed = snapshot(state="CLOSED", current_kind=None)
        closed["historyComplete"] = False

        result = QUEUE.reduce_queue(
            initial["state"],
            [closed],
            viewer_login="ivar",
        )

        self.assertEqual("partial", result["status"])
        self.assertEqual(["closed"], transition_names(result))
        self.assertFalse(result["state"]["entries"][0]["tracking"])
        self.assertEqual("truncated", result["errors"][0]["kind"])

    def test_state_capacity_never_evicts_active_existing_work(self) -> None:
        initial = QUEUE.reduce_queue(
            self.empty,
            [snapshot("acme/widgets", 42)],
            viewer_login="ivar",
            state_limit=1,
        )

        overflow = QUEUE.reduce_queue(
            initial["state"],
            [snapshot("acme/widgets", 42), snapshot("other/widgets", 7)],
            viewer_login="ivar",
            state_limit=1,
        )

        self.assertEqual("partial", overflow["status"])
        self.assertEqual(
            ["acme/widgets#42"],
            [entry["key"] for entry in overflow["state"]["entries"]],
        )
        self.assertEqual(["acme/widgets#42"], [item["key"] for item in overflow["queue"]])
        self.assertEqual("state-capacity", overflow["errors"][0]["kind"])

    def test_terminal_transition_survives_safe_state_pruning(self) -> None:
        initial = QUEUE.reduce_queue(
            self.empty,
            [snapshot("acme/widgets", 42)],
            viewer_login="ivar",
            state_limit=1,
        )

        result = QUEUE.reduce_queue(
            initial["state"],
            [
                snapshot(
                    "acme/widgets",
                    42,
                    state="CLOSED",
                    current_kind=None,
                ),
                snapshot("other/widgets", 7),
            ],
            viewer_login="ivar",
            state_limit=1,
        )

        self.assertEqual("complete", result["status"])
        self.assertEqual(
            ["closed", "newly_requested"],
            transition_names(result),
        )
        self.assertEqual(
            ["other/widgets#7"],
            [entry["key"] for entry in result["state"]["entries"]],
        )

    def test_reset_and_recheck_have_explicit_local_state_semantics(self) -> None:
        initial = QUEUE.reduce_queue(
            self.empty,
            [snapshot()],
            viewer_login="ivar",
        )
        handled = QUEUE.mark_reviewed(initial["state"], initial["queue"][0]["workKey"])
        settled = QUEUE.reduce_queue(handled, [snapshot()], viewer_login="ivar")

        normal = QUEUE.reduce_queue(settled["state"], [snapshot()], viewer_login="ivar")
        recheck = QUEUE.reduce_queue(
            settled["state"],
            [snapshot()],
            viewer_login="ivar",
            mode="recheck",
        )
        reset = QUEUE.reduce_queue(
            settled["state"],
            [snapshot()],
            viewer_login="ivar",
            mode="reset",
        )

        self.assertEqual([], normal["queue"])
        self.assertEqual(["recheck"], transition_names(recheck))
        self.assertEqual(1, len(recheck["queue"]))
        self.assertEqual(["newly_requested"], transition_names(reset))
        self.assertEqual(1, len(reset["queue"]))


class CommandContractTest(unittest.TestCase):
    def test_mark_reviewed_cli_updates_only_returned_session_state(self) -> None:
        initial = QUEUE.reduce_queue(
            QUEUE.empty_state("ivar"),
            [snapshot()],
            viewer_login="ivar",
        )
        work_key = initial["queue"][0]["workKey"]
        output = io.StringIO()

        with redirect_stdout(output):
            status = QUEUE.main(
                [
                    "--state-json",
                    json.dumps(initial["state"]),
                    "--mark-reviewed",
                    work_key,
                ]
            )

        result = json.loads(output.getvalue())
        self.assertEqual(0, status)
        self.assertEqual("mark-reviewed", result["mode"])
        self.assertEqual(
            work_key,
            result["state"]["entries"][0]["handledWorkKey"],
        )

    def test_cli_exposes_reset_and_recheck_without_mutation_commands(self) -> None:
        help_text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('modes.add_argument("--reset"', help_text)
        self.assertIn('modes.add_argument("--recheck"', help_text)
        self.assertNotIn("mutation {", help_text)
        self.assertNotIn("/notifications", help_text)
        self.assertNotIn("requested_reviewers", help_text)


class NormalizationTest(unittest.TestCase):
    def test_normalization_keeps_only_the_viewers_submitted_reviews(self) -> None:
        pull_request = {
            "id": "PR_A",
            "number": 42,
            "url": "https://github.com/acme/widgets/pull/42",
            "state": "OPEN",
            "isDraft": False,
            "merged": False,
            "headRefOid": HEAD_A,
            "author": {"login": "alice"},
            "reviewRequests": {
                "nodes": [
                    {
                        "requestedReviewer": {
                            "__typename": "User",
                            "id": "U1",
                            "login": "ivar",
                        }
                    }
                ]
            },
            "timelineItems": {
                "nodes": [
                    {
                        "__typename": "ReviewRequestedEvent",
                        "id": "REQ_1",
                        "createdAt": "2026-07-30T10:00:00Z",
                        "actor": {"login": "alice"},
                        "requestedReviewer": {
                            "__typename": "User",
                            "id": "U1",
                            "login": "ivar",
                        },
                    },
                    {
                        "__typename": "PullRequestReview",
                        "id": "OTHER_REVIEW",
                        "submittedAt": "2026-07-30T11:00:00Z",
                        "state": "APPROVED",
                        "author": {"login": "someone-else"},
                        "commit": {"oid": HEAD_A},
                    },
                    {
                        "__typename": "PullRequestReview",
                        "id": "MY_REVIEW",
                        "submittedAt": "2026-07-30T12:00:00Z",
                        "state": "COMMENTED",
                        "author": {"login": "ivar"},
                        "commit": {"oid": HEAD_A},
                    },
                ]
            },
        }

        normalized = QUEUE.normalize_pull_request(
            "acme/widgets", pull_request, True, "ivar"
        )

        self.assertEqual(["MY_REVIEW"], [review["id"] for review in normalized["viewerReviews"]])
        self.assertEqual("alice", normalized["requestEvents"][0]["requester"])


class QueueCollectionTest(unittest.TestCase):
    def test_history_pagination_reports_truncation_at_the_cap(self) -> None:
        class PagingClient(QUEUE.GhClient):
            def __init__(self) -> None:
                self.pages = [
                    {
                        "nodes": [{"id": "REQ_2"}],
                        "pageInfo": {"hasNextPage": True, "endCursor": "next"},
                    }
                ]

            def _fetch_connection_page(self, *args: Any) -> dict[str, Any]:
                return self.pages.pop(0)

        nodes, complete = PagingClient()._complete_connection(
            "acme",
            "widgets",
            42,
            "timelineItems",
            {
                "nodes": [{"id": "REQ_1"}],
                "pageInfo": {"hasNextPage": True, "endCursor": "page-2"},
            },
            page_size=1,
            maximum=2,
        )

        self.assertEqual(["REQ_1", "REQ_2"], [node["id"] for node in nodes])
        self.assertFalse(complete)

    def test_search_pagination_and_duplicate_numbers_are_bounded(self) -> None:
        snapshots = {
            "acme/widgets#42": snapshot("acme/widgets", 42, node_id="PR_A"),
            "other/widgets#42": snapshot("other/widgets", 42, node_id="PR_B"),
        }
        client = FakeClient(
            pages={
                None: {
                    "nodes": [{"repository": "acme/widgets", "number": 42}],
                    "pageInfo": {"hasNextPage": True, "endCursor": "page-2"},
                },
                "page-2": {
                    "nodes": [{"repository": "other/widgets", "number": 42}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                },
            },
            snapshots=snapshots,
        )
        limits = QUEUE.QueueLimits(page_size=1, max_candidates=2)

        result = QUEUE.collect_queue(client, limits=limits)

        self.assertEqual("complete", result["status"])
        self.assertEqual(1, client.viewer_calls)
        self.assertEqual([None, "page-2"], client.search_calls)
        self.assertEqual(2, len(result["queue"]))
        self.assertEqual(
            [("acme/widgets", (42,)), ("other/widgets", (42,))],
            client.repository_calls,
        )

    def test_repository_failure_is_partial_and_preserves_prior_state(self) -> None:
        failed_snapshot = snapshot("acme/widgets", 42, node_id="PR_A")
        healthy_snapshot = snapshot("other/widgets", 7, node_id="PR_B")
        prior = QUEUE.reduce_queue(
            QUEUE.empty_state("ivar"),
            [failed_snapshot],
            viewer_login="ivar",
        )["state"]
        client = FakeClient(
            pages={
                None: {
                    "nodes": [
                        {"repository": "acme/widgets", "number": 42},
                        {"repository": "other/widgets", "number": 7},
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            },
            snapshots={"other/widgets#7": healthy_snapshot},
            failures={"acme/widgets"},
        )

        result = QUEUE.collect_queue(client, previous_state=prior)

        self.assertEqual("partial", result["status"])
        self.assertEqual(["acme/widgets"], result["failedRepositories"])
        self.assertEqual("acme/widgets", result["errors"][0]["repository"])
        entries = {entry["key"]: entry for entry in result["state"]["entries"]}
        self.assertIn("acme/widgets#42", entries)
        self.assertIn("other/widgets#7", entries)
        self.assertTrue(entries["acme/widgets#42"]["tracking"])


if __name__ == "__main__":
    unittest.main()
