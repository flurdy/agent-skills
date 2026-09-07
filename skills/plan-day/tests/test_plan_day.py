from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import date
from pathlib import Path

SKILL_DIR = Path(__file__).parents[1]
SCRIPT = SKILL_DIR / "scripts" / "plan_day.py"

PA_TOML = """
[schedule]
timezone = "Europe/London"
work_days = ["mon", "tue", "wed", "thu", "fri"]
work_hours = "09:00-17:30"
blocks = ["work", "project-session", "evening", "skip"]

[plans]
directory = "plans"
retention_days = 3

[priority]
jira = { Highest = 0, High = 1, Medium = 2, Low = 3, Lowest = 4 }
trello_labels = { urgent = 0 }
trello_default = 2
thoughtbox_default = 3

[[clients]]
name = "acme"
workspace = "repos/acme-workspace"
hours = "work"

[[projects]]
name = "hobby"
workspace = "repos/hobby"
hours = "project-session"

[sources]
jira = true
beads = true
trello = false
"""


def load_module():
    spec = importlib.util.spec_from_file_location("plan_day", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def item(**overrides):
    base = {
        "source": "beads",
        "id": "acme-1",
        "title": "Do the thing",
        "priority": 2,
        "due": None,
        "status": "open",
        "url": "",
        "repository": "acme-workspace",
        "delegable": False,
    }
    base.update(overrides)
    return base


class WorkspaceCase(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "workspace.json").write_text('{"version": 1}')
        (self.root / "pa.toml").write_text(PA_TOML)
        for member in ("repos/acme-workspace", "repos/hobby", ".artifacts/plan-day", "plans"):
            (self.root / member).mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_collector(self, name: str, items: list[dict]) -> None:
        (self.root / ".artifacts/plan-day" / f"{name}.json").write_text(json.dumps(items))

    def workspace(self):
        return self.module.load_workspace(self.root)


class PlanDayTest(WorkspaceCase):

    def test_find_root_searches_upward_and_fails_closed(self) -> None:
        nested = self.root / "repos/hobby/src"
        nested.mkdir()
        self.assertEqual(self.module.find_root(nested), self.root.resolve())
        with self.assertRaises(self.module.PlanDayError):
            self.module.find_root(Path(self.tmp.name).parent)

    def test_config_rejects_missing_member_directory(self) -> None:
        (self.root / "pa.toml").write_text(PA_TOML.replace("repos/hobby", "repos/missing"))
        with self.assertRaises(self.module.PlanDayError) as raised:
            self.module.load_config(self.root)
        self.assertIn("projects.hobby.workspace", str(raised.exception))

    def test_config_rejects_priority_out_of_range(self) -> None:
        (self.root / "pa.toml").write_text(PA_TOML.replace("Lowest = 4", "Lowest = 5"))
        with self.assertRaises(self.module.PlanDayError):
            self.module.load_config(self.root)

    def test_validate_item_reports_each_contract_breach(self) -> None:
        bad = item(priority=True, due="soon", extra=1)
        del bad["url"]
        errors = self.module.validate_item(bad, "x")
        self.assertTrue(any("missing field 'url'" in error for error in errors))
        self.assertTrue(any("unknown field 'extra'" in error for error in errors))
        self.assertTrue(any("'priority' has wrong type" in error for error in errors))
        self.assertEqual(self.module.validate_item(item(), "x"), [])

    def test_merge_sorts_annotates_hours_and_reports_sources(self) -> None:
        self.write_collector(
            "beads",
            [
                item(id="late", priority=2, due="2026-02-01", repository="hobby"),
                item(id="soon", priority=2, due="2026-01-01"),
                item(id="urgent", priority=0, repository=""),
            ],
        )
        workspace = self.module.load_workspace(self.root)
        merged = self.module.merge(workspace)
        self.assertEqual([entry["id"] for entry in merged["items"]], ["urgent", "soon", "late"])
        self.assertEqual([entry["hours"] for entry in merged["items"]], [None, "work", "project-session"])
        self.assertEqual(merged["missing_sources"], ["jira"])
        self.assertIn("trello", merged["disabled_sources"])

    def test_merge_fails_closed_on_invalid_collector_output(self) -> None:
        self.write_collector("jira", [item(source="nope")])
        workspace = self.module.load_workspace(self.root)
        with self.assertRaises(self.module.PlanDayError):
            self.module.merge(workspace)

    def test_plan_files_finds_previous_and_stale(self) -> None:
        for day in ("2026-01-01", "2026-01-05", "2026-01-07", "2026-01-09"):
            (self.root / "plans" / f"{day}.md").write_text("plan")
        (self.root / "plans" / "README.md").write_text("not a plan")
        workspace = self.module.load_workspace(self.root)
        result = self.module.plan_files(workspace, date(2026, 1, 9))
        self.assertTrue(result["today"].endswith("plans/2026-01-09.md"))
        self.assertTrue(result["previous"].endswith("2026-01-07.md"))
        self.assertEqual([Path(p).name for p in result["stale"]], ["2026-01-01.md", "2026-01-05.md"])
        self.module.prune(result["stale"])
        self.assertFalse((self.root / "plans/2026-01-01.md").exists())
        self.assertTrue((self.root / "plans/README.md").exists())

    def test_main_validate_reports_errors_on_stderr(self) -> None:
        path = self.root / "bad.json"
        path.write_text(json.dumps({"not": "a list"}))
        buffer = io.StringIO()
        with redirect_stderr(buffer):
            code = self.module.main(["validate", str(path)])
        self.assertEqual(code, 1)
        self.assertIn("JSON array", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()


FAKE_NEXT_BD = """#!/usr/bin/env python3
import json
import os
print(json.dumps([
    {"id": "acme-1", "title": "Ready and specified", "priority": 1, "status": "open",
     "description": "d", "acceptance_criteria": "a", "labels": [], "repository": "acme-workspace"},
    {"id": "acme-2", "title": "Needs a human", "priority": 0, "status": "open",
     "description": "d", "acceptance_criteria": "a", "labels": ["human"], "repository": "workspace"},
]))
"""

FAKE_NEXT_SELECT = """#!/usr/bin/env python3
import json, os
root = os.environ["FAKE_ROOT"]
print(json.dumps({"workspace": True, "stores": [
    {"repository": "workspace", "directory": root, "usable": True, "error": None},
    {"repository": "broken", "directory": root, "usable": False, "error": "no store"},
]}))
"""

FAKE_BD = """#!/usr/bin/env python3
import json
import os
print(json.dumps([{"id": "acme-9", "title": "Claimed", "priority": 2, "status": "in_progress",
                   "description": "d", "acceptance_criteria": "a", "labels": []}]))
"""

FAKE_THOUGHTBOX = """#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
if args[0] == "context":
    repo = args[args.index("--repo") + 1]
    if repo.endswith("hobby"):
        print(json.dumps({"schemaVersion": 1, "ok": False,
                          "error": {"code": "NO_CONTEXT", "message": "unmapped"}}))
        sys.exit(1)
    print(json.dumps({"schemaVersion": 1, "ok": True, "data": {
        "contextId": "c1", "profile": "default", "workingDirectory": repo, "triageDirectory": repo}}))
else:
    print(json.dumps({"schemaVersion": 1, "ok": True, "data": [
        {"id": "t1", "text": "  Ship   the thing\\nsoon ", "status": "inbox"},
        {"id": "t2", "text": "resolved", "status": "done"},
        {"id": "t3", "kind": "diagnostic", "diagnostic": {"message": "bad"}},
    ]}))
"""


class CollectorTest(WorkspaceCase):
    def setUp(self) -> None:
        super().setUp()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name, body in (
            ("next-bd", FAKE_NEXT_BD),
            ("next-select", FAKE_NEXT_SELECT),
            ("bd", FAKE_BD),
            ("thoughtbox", FAKE_THOUGHTBOX),
        ):
            script = self.bin / name
            script.write_text(body)
            script.chmod(0o755)
        self.module.NEXT_SCRIPTS = self.bin
        self.environ = dict(os.environ)
        os.environ["PATH"] = f"{self.bin}{os.pathsep}{os.environ['PATH']}"
        os.environ["FAKE_ROOT"] = str(self.root)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.environ)
        super().tearDown()

    def test_beads_collector_merges_ready_and_in_progress_and_flags_delegable(self) -> None:
        result = self.module.collect_beads(self.workspace())
        by_id = {item["id"]: item for item in result["items"]}
        self.assertEqual(set(by_id), {"acme-1", "acme-2", "acme-9"})
        self.assertTrue(by_id["acme-1"]["delegable"])
        self.assertFalse(by_id["acme-2"]["delegable"], "human label blocks delegation")
        self.assertFalse(by_id["acme-9"]["delegable"], "in-progress work is not delegable")
        self.assertEqual(by_id["acme-9"]["status"], "in_progress")
        self.assertEqual(result["diagnostics"], ["broken: no store"])

    def test_jira_collector_normalises_raw_search_response(self) -> None:
        source = self.root / "jira.raw.json"
        source.write_text(
            json.dumps(
                {
                    "issues": [
                        {
                            "key": "GE-1",
                            "fields": {
                                "summary": "Fix it",
                                "status": {"name": "In Progress"},
                                "priority": {"name": "High"},
                                "duedate": "2026-03-01",
                            },
                        }
                    ]
                }
            )
        )
        (self.root / "pa.toml").write_text(
            PA_TOML.replace('hours = "work"', 'hours = "work"\njira = { base_url = "https://x.atlassian.net/" }')
        )
        result = self.module.collect_jira(self.workspace(), "acme", source)
        self.assertEqual(
            result["items"],
            [
                {
                    "source": "jira",
                    "id": "GE-1",
                    "title": "Fix it",
                    "priority": 1,
                    "due": "2026-03-01",
                    "status": "In Progress",
                    "url": "https://x.atlassian.net/browse/GE-1",
                    "repository": "acme-workspace",
                    "delegable": False,
                }
            ],
        )

    def test_jira_collector_fails_closed_on_unmapped_priority(self) -> None:
        source = self.root / "jira.json"
        source.write_text(json.dumps([{"key": "GE-2", "summary": "x", "priority": "Blocker"}]))
        with self.assertRaises(self.module.PlanDayError) as raised:
            self.module.collect_jira(self.workspace(), "acme", source)
        self.assertIn("Blocker", str(raised.exception))

    def test_thoughtbox_collector_keeps_inbox_only_and_reports_unmapped_members(self) -> None:
        result = self.module.collect_thoughtbox(self.workspace())
        self.assertEqual([item["id"] for item in result["items"]], ["t1"])
        self.assertEqual(result["items"][0]["title"], "Ship the thing soon")
        self.assertEqual(result["items"][0]["priority"], 3)
        self.assertEqual(
            result["diagnostics"],
            ["acme-workspace: malformed thought t3", "hobby: thoughtbox: NO_CONTEXT: unmapped"],
        )

    def test_collect_writes_validated_artifact_that_merge_reads(self) -> None:
        args = self.module.parse_args(["collect", "beads"])
        summary = self.module.collect(self.workspace(), args)
        self.assertEqual(summary["count"], 3)
        self.assertTrue((self.root / ".artifacts/plan-day/beads.json").is_file())
        merged = self.module.merge(self.workspace())
        self.assertNotIn("beads", merged["missing_sources"])
        self.assertEqual(merged["items"][0]["id"], "acme-2")
