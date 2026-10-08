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
projects = ["GE"]
ready_statuses = ["Ready to Work"]
labels = ["FE", "BE"]
next_limit = 5
holding_sprints = ["READY FOR ENGINEERING"]
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

    def test_builds_three_ranked_buckets_from_nested_directory(self) -> None:
        self.write(CONFIG)
        code, output, _ = run(self.nested)
        self.assertEqual(code, 0)
        requests = output["requests"]
        self.assertEqual([r["bucket"] for r in requests], ["active", "next", "backlog"])
        jql = requests[0]["queryParams"]["jql"]
        self.assertIn('project in ("GE")', jql)
        self.assertIn('status in ("Ready to Work")', jql)
        self.assertIn("assignee is EMPTY", jql)
        self.assertIn('issuetype not in ("Epic")', jql)
        self.assertIn('labels in ("FE", "BE")', jql)
        self.assertTrue(jql.endswith("sprint in openSprints() ORDER BY Rank ASC"))
        self.assertIn("sprint not in openSprints()", requests[1]["queryParams"]["jql"])
        self.assertIn("sprint is EMPTY", requests[2]["queryParams"]["jql"])
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
            'project in ("GE") AND assignee = currentUser() AND statusCategory != Done ORDER BY Rank ASC',
        )
        mine_fields = output["mine"]["queryParams"]["fields"].split(",")
        self.assertIn("status", mine_fields)
        self.assertIn("customfield_10020", mine_fields)
        self.assertIn("status: fields.status.name", output["mine"]["jq"])
        self.assertIn("points: fields.customfield_10016", output["mine"]["jq"])
        self.assertEqual(output["config"]["holding_sprints"], ["READY FOR ENGINEERING"])

    def test_label_override_and_all(self) -> None:
        self.write(CONFIG)
        _, output, _ = run(self.root, "--labels", "FS, FE")
        self.assertIn('labels in ("FS", "FE")', output["requests"][0]["queryParams"]["jql"])
        _, output, _ = run(self.root, "--labels", "")
        self.assertNotIn("labels in", output["requests"][0]["queryParams"]["jql"])
        self.assertEqual(output["labels"], [])

    def test_quotes_values(self) -> None:
        self.write('[jira]\nprojects = ["GE"]\nready_statuses = [\'Say "ready"\']\n')
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
            '[jira]\nprojects = ["GE"]\nready_statuses = ["R"]\nnext_limit = 0\n': "next_limit",
            '[jira]\nprojects = ["GE"]\nready_statuses = ["R"]\n[jira.fields]\nsprint = "x"\n': "jira.fields.sprint",
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
