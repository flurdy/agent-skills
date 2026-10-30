from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "pickup.py"
spec = importlib.util.spec_from_file_location("pickup", SCRIPT)
pickup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pickup)

CONFIG = """
[jira]
projects = ["ABC"]
ready_statuses = ["Ready to Work"]
labels = ["FE", "BE"]
next_limit = 5
holding_sprints = ["Ready Queue"]
"""


def run(workspace: Path, *args: str) -> tuple[int, dict | None, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = pickup.main(["--workspace", str(workspace), *args])
    return code, json.loads(stdout.getvalue()) if code == 0 else None, stderr.getvalue()


class PickupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.nested = self.root / "repos" / "service"
        self.nested.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, text: str) -> None:
        (self.root / "pickup.toml").write_text(text)

    def test_builds_ranked_buckets_from_nested_directory(self) -> None:
        self.write(CONFIG)
        code, output, _ = run(self.nested)
        self.assertEqual(code, 0)
        requests = output["requests"]
        self.assertEqual(
            [r["bucket"] for r in requests], ["active", "next", "holding", "backlog"]
        )
        jql = requests[0]["queryParams"]["jql"]
        self.assertIn('project in ("ABC")', jql)
        self.assertIn('status in ("Ready to Work")', jql)
        self.assertIn("assignee is EMPTY", jql)
        self.assertIn('issuetype not in ("Epic")', jql)
        self.assertIn('labels in ("FE", "BE")', jql)
        self.assertTrue(jql.endswith("sprint in openSprints() ORDER BY Rank ASC"))
        self.assertIn("sprint not in openSprints()", requests[1]["queryParams"]["jql"])
        self.assertIn("sprint is EMPTY", requests[-1]["queryParams"]["jql"])
        self.assertEqual(requests[1]["queryParams"]["maxResults"], "5")
        self.assertIn("customfield_10021", requests[0]["queryParams"]["fields"])
        self.assertIn("fields.customfield_10016", requests[0]["jq"])
        self.assertIn("parent", requests[0]["queryParams"]["fields"].split(","))
        self.assertIn("parent: fields.parent.fields.summary", requests[0]["jq"])
        self.assertIn("start: startDate", requests[0]["jq"])
        self.assertIn("parent_key: fields.parent.key", requests[0]["jq"])
        mine = output["mine"]["queryParams"]["jql"]
        self.assertEqual(
            mine,
            'project in ("ABC") AND assignee = currentUser() AND statusCategory != Done ORDER BY Rank ASC',
        )
        mine_fields = output["mine"]["queryParams"]["fields"].split(",")
        self.assertIn("status", mine_fields)
        self.assertIn("customfield_10020", mine_fields)
        self.assertIn("status: fields.status.name", output["mine"]["jq"])
        self.assertIn("status_category: fields.status.statusCategory.key", output["mine"]["jq"])
        self.assertIn("points: fields.customfield_10016", output["mine"]["jq"])
        self.assertEqual(output["config"]["holding_sprints"], ["Ready Queue"])

    def test_holding_sprints_are_fetched_separately_after_real_future_sprints(self) -> None:
        self.write(CONFIG.replace('["Ready Queue"]', '["Ready Queue", "Parking"]'))
        _, output, _ = run(self.root)
        requests = output["requests"]
        self.assertEqual(
            [(r["bucket"], r.get("sprint")) for r in requests],
            [
                ("active", None),
                ("next", None),
                ("holding", "Ready Queue"),
                ("holding", "Parking"),
                ("backlog", None),
            ],
        )
        self.assertIn(
            'sprint not in openSprints() AND sprint not in ("Ready Queue", "Parking")',
            requests[1]["queryParams"]["jql"],
        )
        holding = requests[2]["queryParams"]
        self.assertIn(
            'sprint in ("Ready Queue") AND sprint not in openSprints() ORDER BY Rank ASC',
            holding["jql"],
        )
        self.assertIn('labels in ("FE", "BE")', holding["jql"])
        self.assertEqual(holding["maxResults"], "5")

    def test_without_holding_sprints_next_covers_every_future_sprint(self) -> None:
        self.write(CONFIG.replace('holding_sprints = ["Ready Queue"]', ""))
        _, output, _ = run(self.root)
        requests = output["requests"]
        self.assertEqual([r["bucket"] for r in requests], ["active", "next", "backlog"])
        self.assertNotIn('sprint not in ("', requests[1]["queryParams"]["jql"])

    def test_every_search_exposes_paging_state(self) -> None:
        self.write(CONFIG)
        _, output, _ = run(self.root, "--parents", "ABC-1", "--linked", "ABC-2")
        for request in (*output["requests"], output["mine"], output["follow_on"]):
            with self.subTest(jql=request["queryParams"]["jql"]):
                self.assertTrue(
                    request["jq"].startswith(
                        "{isLast: isLast, nextPageToken: nextPageToken, issues: issues[*].{"
                    )
                )
                self.assertTrue(request["jq"].endswith("}}"))

    def test_follow_on_request_targets_my_epics_and_linked_tickets(self) -> None:
        self.write(CONFIG)
        _, output, _ = run(self.root, "--parents", "ABC-10, ABC-11,ABC-10", "--linked", "ABC-20,ABC-21")
        follow_on = output["follow_on"]
        jql = follow_on["queryParams"]["jql"]
        self.assertIn("assignee is EMPTY", jql)
        self.assertIn('status in ("Ready to Work")', jql)
        self.assertIn('labels in ("FE", "BE")', jql)
        self.assertIn(
            "(sprint in openSprints() OR sprint in futureSprints() OR sprint is EMPTY)", jql
        )
        self.assertIn(
            '(parent in ("ABC-10", "ABC-11") OR issue in linkedIssues("ABC-20") '
            'OR issue in linkedIssues("ABC-21")) ORDER BY Rank ASC',
            jql,
        )
        self.assertEqual(follow_on["queryParams"]["maxResults"], "50")
        self.assertEqual(follow_on["jq"], output["requests"][0]["jq"])

    def test_follow_on_with_one_kind_of_key(self) -> None:
        self.write(CONFIG)
        _, output, _ = run(self.root, "--linked", "ABC-20")
        self.assertIn('(issue in linkedIssues("ABC-20")) ORDER BY', output["follow_on"]["queryParams"]["jql"])
        _, output, _ = run(self.root, "--parents", "ABC-10")
        self.assertIn('(parent in ("ABC-10")) ORDER BY', output["follow_on"]["queryParams"]["jql"])

    def test_no_follow_on_without_keys(self) -> None:
        self.write(CONFIG)
        _, output, _ = run(self.root)
        self.assertIsNone(output["follow_on"])
        _, output, _ = run(self.root, "--parents", "", "--linked", " ")
        self.assertIsNone(output["follow_on"])

    def test_follow_on_keys_fail_closed(self) -> None:
        self.write(CONFIG)
        too_many = ",".join(f"ABC-{n}" for n in range(1, 102))
        cases = {
            ('--parents', 'ABC-1") OR project = "X'): "invalid issue key",
            ("--linked", "abc-1"): "invalid issue key",
            ("--linked", too_many): "at most 100",
        }
        for args, message in cases.items():
            with self.subTest(args=args):
                code, _, error = run(self.root, *args)
                self.assertEqual(code, 1)
                self.assertIn(message, error)

    def test_skill_documents_paging_follow_ons_and_truncation(self) -> None:
        skill = (SCRIPT.parents[1] / "SKILL.md").read_text()
        for phrase in ("nextPageToken", "isLast", "more in Jira", "--parents", "--linked", "follow_on"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)

    def test_label_override_and_all(self) -> None:
        self.write(CONFIG)
        _, output, _ = run(self.root, "--labels", "FS, FE")
        self.assertIn('labels in ("FS", "FE")', output["requests"][0]["queryParams"]["jql"])
        _, output, _ = run(self.root, "--labels", "")
        self.assertNotIn("labels in", output["requests"][0]["queryParams"]["jql"])
        self.assertEqual(output["labels"], [])

    def test_quotes_values(self) -> None:
        self.write('[jira]\nprojects = ["ABC"]\nready_statuses = [\'Say "ready"\']\n')
        _, output, _ = run(self.root)
        self.assertIn('status in ("Say \\"ready\\"")', output["requests"][0]["queryParams"]["jql"])

    def test_custom_fields_feed_projection(self) -> None:
        self.write(CONFIG + '\n[jira.fields]\nflagged = "customfield_99"\n')
        _, output, _ = run(self.root)
        self.assertIn("fields.customfield_99[*].value", output["requests"][0]["jq"])
        self.assertIn("customfield_10020", output["requests"][0]["jq"])

    def test_story_points_override_feeds_mine(self) -> None:
        self.write(CONFIG + '\n[jira.fields]\nstory_points = "customfield_10024"\n')
        _, output, _ = run(self.root)
        self.assertIn("customfield_10024", output["mine"]["queryParams"]["fields"].split(","))
        self.assertIn("points: fields.customfield_10024", output["mine"]["jq"])

    def test_fails_closed(self) -> None:
        cases = {
            "": "missing [jira]",
            '[jira]\nready_statuses = ["R"]\n': "jira.projects is required",
            '[jira]\nprojects = ["ABC"]\nready_statuses = ["R"]\nnext_limit = 0\n': "next_limit",
            '[jira]\nprojects = ["ABC"]\nready_statuses = ["R"]\n[jira.fields]\nsprint = "x"\n': "jira.fields.sprint",
            "[jira\n": "pickup.toml",
        }
        for text, message in cases.items():
            with self.subTest(text=text):
                self.write(text)
                code, _, error = run(self.root)
                self.assertEqual(code, 1)
                self.assertIn(message, error)

    def test_missing_config(self) -> None:
        code, _, error = run(self.nested)
        self.assertEqual(code, 1)
        self.assertIn("no pickup.toml", error)


if __name__ == "__main__":
    unittest.main()
