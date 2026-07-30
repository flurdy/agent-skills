from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest

TEST_DIR = Path(__file__).resolve().parent
SCRIPT = TEST_DIR.parent / "scripts" / "gh-pr-feedback.py"
SPEC = importlib.util.spec_from_file_location("gh_pr_feedback", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {SCRIPT}")
feedback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(feedback)


class FixtureClient:
    def __init__(self, fixture: dict):
        self.fixture = copy.deepcopy(fixture)
        self.connection_calls: list[tuple[int, str, str]] = []
        self.rest_calls: list[str] = []

    def fetch_initial(self, owner: str, repo: str, numbers: list[int], page_size: int) -> dict:
        return copy.deepcopy(self.fixture["initial"])

    def fetch_connection(
        self,
        owner: str,
        repo: str,
        number: int,
        source: str,
        after: str,
        page_size: int,
    ) -> dict:
        self.connection_calls.append((number, source, after))
        value = self.fixture.get("connectionPages", {}).get(f"{number}:{source}:{after}")
        if value is None:
            raise RuntimeError(f"missing fixture page: {number}:{source}:{after}")
        if "error" in value:
            raise RuntimeError(value["error"])
        return copy.deepcopy(value)

    def rest(self, endpoint: str) -> object:
        self.rest_calls.append(endpoint)
        value = self.fixture.get("rest", {}).get(endpoint)
        if value is None:
            raise RuntimeError(f"missing fixture REST response: {endpoint}")
        if isinstance(value, dict) and "error" in value:
            raise RuntimeError(value["error"])
        return copy.deepcopy(value)


def load_fixture(name: str) -> dict:
    return json.loads((TEST_DIR / "fixtures" / name).read_text())


def by_identity(result: dict) -> dict[str, dict]:
    return {record["identity"]: record for record in result["records"]}


class FeedbackInventoryTests(unittest.TestCase):
    def test_normalizes_every_feedback_surface_and_response_target(self) -> None:
        result = feedback.collect_inventory(
            FixtureClient(load_fixture("all-sources.json")),
            "acme",
            "widgets",
            [42],
            feedback.InventoryConfig(body_limit=80),
        )
        records = by_identity(result)

        self.assertEqual(1, result["schemaVersion"])
        self.assertFalse(result["partial"])
        self.assertEqual(
            {"inline_review", "review_summary", "conversation", "check_annotation"},
            {record["source"] for record in records.values()},
        )
        self.assertEqual({"root", "reply"}, {records["inline:C1"]["role"], records["inline:C2"]["role"]})
        self.assertEqual("C1", records["inline:C1"]["nodeId"])
        self.assertEqual(101, records["inline:C1"]["databaseId"])
        self.assertEqual("T1", records["inline:C1"]["threadId"])
        self.assertEqual(101, records["inline:C2"]["targets"]["reply"]["commentId"])
        self.assertEqual("T1", records["inline:C2"]["targets"]["resolveThreadId"])
        self.assertEqual("C1", records["inline:C2"]["replyToNodeId"])
        self.assertTrue(records["inline:C1"]["hasLaterSelfReply"])
        self.assertTrue(records["inline:C1"]["threadHasSelfReply"])
        self.assertEqual(201, records["review:R1"]["databaseId"])
        self.assertEqual(301, records["conversation:I1"]["databaseId"])
        self.assertEqual("conversation", records["conversation:I1"]["targets"]["reply"]["surface"])
        self.assertIsNone(records[next(key for key in records if key.startswith("check_annotation:"))]["targets"]["reply"])

        self.assertEqual("human", records["inline:C1"]["authorKind"])
        self.assertEqual("self", records["inline:C2"]["authorKind"])
        self.assertEqual("bot", records["inline:C3"]["authorKind"])
        self.assertTrue(records["inline:C2"]["selfAuthored"])
        self.assertEqual("suppressed", records["inline:C2"]["actionability"])

        self.assertEqual("unresolved", records["inline:C1"]["lifecycle"])
        self.assertEqual("resolved", records["inline:C3"]["lifecycle"])
        self.assertTrue(records["inline:C3"]["isResolved"])
        self.assertEqual("outdated", records["inline:C4"]["lifecycle"])
        self.assertTrue(records["inline:C4"]["isOutdated"])
        self.assertEqual("dismissed", records["review:R4"]["lifecycle"])
        self.assertNotIn("review:R5", records, "pending draft reviews are not observable inventory")

        self.assertEqual("change_request", records["inline:C1"]["semanticType"])
        self.assertEqual("suggestion", records["inline:C3"]["semanticType"])
        self.assertEqual("security_claim", records["inline:C4"]["semanticType"])
        self.assertEqual("question", records["review:R1"]["semanticType"])
        self.assertEqual("approval", records["review:R2"]["semanticType"])
        self.assertEqual("blocking_claim", records["review:R3"]["semanticType"])
        self.assertEqual("automated_status", records["conversation:I2"]["semanticType"])
        self.assertEqual("noise", records["conversation:I2"]["actionability"])
        self.assertTrue(records["review:R3"]["requiresValidation"])

        self.assertTrue(records["conversation:I1"]["bodyTruncated"])
        self.assertLessEqual(len(records["conversation:I1"]["rawBody"]), 80)
        annotations = [record for record in records.values() if record["source"] == "check_annotation"]
        self.assertEqual({"src/app.py"}, {record["path"] for record in annotations})
        self.assertEqual({"candidate", "informational"}, {record["actionability"] for record in annotations})
        self.assertEqual(13, len(records))

    def test_identity_is_stable_and_update_key_changes_for_an_edit(self) -> None:
        original = load_fixture("all-sources.json")
        first = feedback.collect_inventory(FixtureClient(original), "acme", "widgets", [42])
        repeated = feedback.collect_inventory(FixtureClient(original), "acme", "widgets", [42])
        self.assertEqual(first, repeated)

        edited = copy.deepcopy(original)
        change = load_fixture("edited-comment.json")
        comments = edited["initial"]["data"]["repository"]["pr0"]["reviewThreads"]["nodes"][0]["comments"]["nodes"]
        node = next(item for item in comments if item["id"] == change["nodeId"])
        node["body"] = change["body"]
        node["updatedAt"] = change["updatedAt"]
        after_edit = feedback.collect_inventory(FixtureClient(edited), "acme", "widgets", [42])

        before_record = by_identity(first)["inline:C1"]
        edited_record = by_identity(after_edit)["inline:C1"]
        self.assertEqual(before_record["identity"], edited_record["identity"])
        self.assertNotEqual(before_record["updateKey"], edited_record["updateKey"])
        self.assertEqual(change["updatedAt"], edited_record["updatedAt"])

    def test_state_key_changes_when_thread_lifecycle_changes_without_a_comment_edit(self) -> None:
        original = load_fixture("all-sources.json")
        resolved = copy.deepcopy(original)
        resolved["initial"]["data"]["repository"]["pr0"]["reviewThreads"]["nodes"][0]["isResolved"] = True

        before = by_identity(feedback.collect_inventory(FixtureClient(original), "acme", "widgets", [42]))["inline:C1"]
        after = by_identity(feedback.collect_inventory(FixtureClient(resolved), "acme", "widgets", [42]))["inline:C1"]

        self.assertEqual(before["identity"], after["identity"])
        self.assertEqual(before["updateKey"], after["updateKey"])
        self.assertNotEqual(before["stateKey"], after["stateKey"])
        self.assertEqual("resolved", after["lifecycle"])

    def test_paginates_connections_and_deduplicates_stable_ids(self) -> None:
        client = FixtureClient(load_fixture("pagination.json"))
        result = feedback.collect_inventory(client, "acme", "widgets", [7])

        self.assertFalse(result["partial"])
        self.assertEqual(["inline:PC1", "inline:PC2"], sorted(record["identity"] for record in result["records"]))
        self.assertEqual([(7, "reviewThreads", "threads-1")], client.connection_calls)

    def test_marks_bounded_truncation_without_fetching_beyond_the_cap(self) -> None:
        client = FixtureClient(load_fixture("pagination.json"))
        result = feedback.collect_inventory(
            client,
            "acme",
            "widgets",
            [7],
            feedback.InventoryConfig(max_source_items=1),
        )

        self.assertTrue(result["partial"])
        self.assertEqual([], client.connection_calls)
        self.assertEqual(1, len(result["records"]))
        self.assertIn("truncated", {error["kind"] for error in result["errors"]})

    def test_reports_bounded_rest_annotation_truncation(self) -> None:
        result = feedback.collect_inventory(
            FixtureClient(load_fixture("all-sources.json")),
            "acme",
            "widgets",
            [42],
            feedback.InventoryConfig(max_source_items=1),
        )

        self.assertTrue(result["partial"])
        self.assertIn(
            ("check_annotations", "truncated"),
            {(error["source"], error["kind"]) for error in result["errors"]},
        )
        self.assertEqual(1, sum(record["source"] == "check_annotation" for record in result["records"]))

    def test_preserves_available_records_and_reports_partial_api_failures(self) -> None:
        result = feedback.collect_inventory(
            FixtureClient(load_fixture("partial-failure.json")),
            "acme",
            "widgets",
            [9],
        )

        self.assertTrue(result["partial"])
        self.assertEqual(["inline:FC1"], [record["identity"] for record in result["records"]])
        self.assertEqual({"reviews", "check_runs"}, {error["source"] for error in result["errors"]})
        self.assertTrue(all(error["retryable"] for error in result["errors"]))

    def test_missing_viewer_marks_self_classification_partial(self) -> None:
        fixture = load_fixture("all-sources.json")
        fixture["initial"]["data"]["viewer"] = None

        result = feedback.collect_inventory(FixtureClient(fixture), "acme", "widgets", [42])

        self.assertTrue(result["partial"])
        self.assertIn("viewer", {error["source"] for error in result["errors"]})
        self.assertFalse(by_identity(result)["inline:C2"]["selfAuthored"])

    def test_initial_failure_is_machine_readable(self) -> None:
        class BrokenClient(FixtureClient):
            def fetch_initial(self, owner: str, repo: str, numbers: list[int], page_size: int) -> dict:
                raise RuntimeError("GraphQL unavailable")

        result = feedback.collect_inventory(BrokenClient({}), "acme", "widgets", [1])
        self.assertTrue(result["partial"])
        self.assertEqual([], result["records"])
        self.assertEqual("initial", result["errors"][0]["source"])
        self.assertEqual("api", result["errors"][0]["kind"])


if __name__ == "__main__":
    unittest.main()
