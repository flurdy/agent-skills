from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from typing import Any

from workspace_fixture import SKILL_DIR, WorkspaceFixture, issue

SCRIPT = SKILL_DIR / "scripts" / "next-bd"
SESSION_VARIABLES = ("PI_SESSION_ID", "CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID",
                     "CODEX_SESSION_ID", "CODEX_THREAD_ID")
DATE = "2026-01-01T00:00:00Z"


def claim(directory: Path, issue_id: str, session_id: str) -> dict[str, str]:
    identity = json.dumps({"owning_store": str(directory.resolve()), "session_id": session_id},
                          sort_keys=True, separators=(",", ":"))
    return {"issue_id": issue_id, "text": f"agent-claim:v1 {identity}\nSession activity is unverified."}


def child(issue_id: str, priority: int, **extra: Any) -> dict[str, Any]:
    return {**issue(issue_id, priority, "task", DATE), "parent": "epic", **extra}


def graph() -> dict[str, Any]:
    return {
        "ready": [child("sib-ready", 3), issue("blocker", 1, "bug", DATE),
                  issue("rel", 2, "task", DATE), issue("unrelated", 0, "bug", DATE)],
        "blocked": [child("sib-blocked", 2, blocked_by=["blocker"]),
                    {**issue("next-up", 2, "feature", DATE), "blocked_by": ["focus"]}],
        "in_progress": [child("focus", 2), issue("epic", 2, "epic", DATE),
                        issue("someone-else", 2, "task", DATE)],
        "deferred": [child("sib-deferred", 2, defer_until="2026-01-02T00:00:00Z")],
        "other": [child("sib-closed", 2, status="closed"),
                  {**issue("origin", 2, "task", DATE), "status": "open"},
                  {**issue("found", 3, "chore", DATE), "status": "open"}],
        "deps": [
            *({"from": child, "to": "epic", "type": "parent-child"}
              for child in ("focus", "sib-ready", "sib-blocked", "sib-deferred", "sib-closed")),
            {"from": "focus", "to": "blocker", "type": "blocks"},
            {"from": "sib-blocked", "to": "blocker", "type": "blocks"},
            {"from": "next-up", "to": "focus", "type": "blocks"},
            {"from": "focus", "to": "rel", "type": "relates-to"},
            {"from": "focus", "to": "origin", "type": "discovered-from"},
            {"from": "found", "to": "focus", "type": "discovered-from"},
            {"from": "focus", "to": "unrelated", "type": "supersedes"},
        ],
    }


class RelatedViewTest(WorkspaceFixture):
    def setUp(self) -> None:
        super().setUp()
        for variable in SESSION_VARIABLES:
            self.environment.pop(variable, None)

    def run_next(self, directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return self.run_script(SCRIPT, directory, *arguments, check=False)

    def assert_read_only(self) -> None:
        calls = self.recorded_calls()
        self.assertTrue(calls)
        self.assertTrue(all("--readonly" in call["arguments"] for call in calls), calls)

    def test_explicit_selector_shows_one_hop_graph_in_rank_order(self) -> None:
        workspace = self.create_workspace(repositories={"repo-a": graph()})
        local = self.base / "local"
        self.create_store(local, **graph())
        for directory, selector, owner in ((workspace, "repo-a:focus", "repo-a | "),
                                           (workspace, "focus", "repo-a | "),
                                           (local, "focus", "")):
            with self.subTest(selector=selector, workspace=bool(owner)):
                result = self.run_next(directory, f"--related={selector}")
                self.assertEqual(result.returncode, 0, result.stderr)
                output = result.stdout
                heading = "repo-a:focus" if owner else "focus"
                self.assertIn(f"## Related to {heading} (9 beads)", output)
                self.assertIn("Focus: explicit selector.", output)
                self.assertEqual("| Relation | Repo |" in output, bool(owner))
                expected = [
                    ("parent (1/5 children closed)", "epic", "in_progress"),
                    ("blocked by", "blocker", "ready"),
                    ("unblocks", "next-up", "blocked by focus"),
                    ("sibling", "sib-blocked", "blocked by blocker"),
                    ("sibling", "sib-deferred", "deferred until 2026-01-02T00:00:00Z ⏰ elapsed"),
                    ("sibling", "sib-ready", "ready"),
                    ("related", "rel", "ready"),
                    ("discovered from", "origin", "open"),
                ]
                positions = []
                for relation, bead, status in expected:
                    row = next((line for line in output.splitlines()
                                if line.startswith(f"| {relation} | {owner}{bead} |")), None)
                    self.assertIsNotNone(row, f"{relation} {bead}\n{output}")
                    self.assertTrue(row.endswith(f"| {status} |"), row)
                    positions.append(output.index(row))
                self.assertEqual(positions, sorted(positions))
                self.assertIn("| discovered here | " + owner + "found |", output)
                self.assertIn(f"| sibling | {owner}sib-ready | P3 | task | - | Title for sib-ready | epic | ready |",
                              output)
                self.assertIn(f"| parent (1/5 children closed) | {owner}epic | P2 | epic | - | Title for epic | — |",
                              output)
                self.assertIn("⏰ 1 elapsed wake date", output)
                for absent in ("## Ready to Work", "| # |", "Pick a number", "unrelated",
                               "sib-closed", "someone-else", "## In Progress"):
                    self.assertNotIn(absent, output)
        self.assert_read_only()

    def test_session_claims_select_only_this_sessions_beads(self) -> None:
        workspace = self.create_workspace(repositories={"repo-a": graph()})
        member = self.base / "sources" / "repo-a"
        fixture = member / ".beads" / "fixture.json"
        data = json.loads(fixture.read_text())
        data["comments"] = [claim(member, "focus", "this-session"),
                            claim(member, "someone-else", "other-session"),
                            claim(workspace, "epic", "this-session")]
        fixture.write_text(json.dumps(data))
        self.environment["PI_SESSION_ID"] = "this-session"

        result = self.run_next(workspace, "--related")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Focus: in-progress beads claimed by this session", result.stdout)
        self.assertIn("## Related to repo-a:focus", result.stdout)
        self.assertNotIn("## Related to repo-a:epic", result.stdout)
        self.assertNotIn("## Related to repo-a:someone-else", result.stdout)
        self.assert_read_only()

    def test_session_focus_without_claims_or_session_asks_for_a_bead(self) -> None:
        local = self.base / "local"
        self.create_store(local, **graph())
        result = self.run_next(local, "--related")
        self.assertEqual(result.returncode, 4)
        self.assertIn("No harness session ID", result.stdout)
        self.assertIn("/next related <bead>", result.stdout)

        self.environment["PI_SESSION_ID"] = "this-session"
        result = self.run_next(local, "--related")
        self.assertEqual(result.returncode, 4)
        self.assertIn("No in-progress bead carries this session's claim attribution", result.stdout)
        self.assertNotIn("## Related to", result.stdout)
        self.assert_read_only()

    def test_ambiguous_and_unavailable_owners_render_no_tables(self) -> None:
        workspace = self.create_workspace(repositories={
            "repo-a": {"ready": [issue("dup", 2, "task", DATE)]},
            "repo-b": {"ready": [issue("dup", 2, "task", DATE)]},
        })
        result = self.run_next(workspace, "--related=dup")
        self.assertEqual(result.returncode, 3)
        self.assertIn("repo-a:dup", result.stdout)
        self.assertIn("repo-b:dup", result.stdout)
        self.assertNotIn("| Relation |", result.stdout)

        fixture = self.base / "sources" / "repo-b" / ".beads" / "fixture.json"
        data = json.loads(fixture.read_text())
        data["faults"] = {"probe": "dolt-down", "in_progress": "dolt-down"}
        fixture.write_text(json.dumps(data))
        result = self.run_next(workspace, "--related=dup")
        self.assertEqual(result.returncode, 5)
        self.assertIn("**repo-b**", result.stdout)
        self.assertNotIn("| Relation |", result.stdout)

        self.environment["PI_SESSION_ID"] = "this-session"
        result = self.run_next(workspace, "--related")
        self.assertEqual(result.returncode, 5)
        self.assertTrue(result.stdout.startswith("## ⚠️ Beads store unavailable (1)"), result.stdout)
        self.assertIn("could not be checked", result.stdout)
        self.assert_read_only()

    def test_session_focus_survives_an_unrelated_unavailable_store(self) -> None:
        workspace = self.create_workspace(repositories={
            "repo-a": graph(), "down": {"faults": {"in_progress": "dolt-down"}},
        })
        member = self.base / "sources" / "repo-a"
        fixture = member / ".beads" / "fixture.json"
        data = json.loads(fixture.read_text())
        data["comments"] = [claim(member, "focus", "this-session")]
        fixture.write_text(json.dumps(data))
        self.environment["PI_SESSION_ID"] = "this-session"

        result = self.run_next(workspace, "--related")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("## ⚠️ Beads store unavailable (1)"), result.stdout)
        self.assertIn("**down**", result.stdout)
        self.assertIn("## Related to repo-a:focus", result.stdout)

    def test_workspace_owned_member_routes_through_the_shared_resolver(self) -> None:
        workspace = self.create_workspace(root_data=graph(), repositories={"delegated": {}})
        self.declare_tracking(workspace, delegated="workspace")
        shutil.rmtree(self.base / "sources" / "delegated" / ".beads")

        hinted = self.run_next(workspace, "--related=delegated:focus")
        self.assertEqual(hinted.returncode, 4)
        self.assertIn("workspace:focus", hinted.stdout)
        self.assertNotIn("| Relation |", hinted.stdout)

        result = self.run_next(workspace, "--related=workspace:focus")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| sibling | workspace | sib-ready |", result.stdout)
        self.assertTrue(all(Path(call["directory"]) == workspace.resolve()
                            for call in self.recorded_calls()))

    def test_json_and_help_contracts_are_unchanged(self) -> None:
        local = self.base / "local"
        self.create_store(local, **graph())
        self.assertEqual(self.run_next(local, "--related=focus", "--json").stdout,
                         self.run_next(local, "--json").stdout)
        self.assertIn("--related[=BEAD]", self.run_next(local, "--help").stdout)

    def test_related_instructions_are_read_only_without_picker(self) -> None:
        skill = (SKILL_DIR / "SKILL.md").read_text()
        self.assertIn("/next related", skill.split("## What This Skill Does", 1)[0])
        section = skill.split("## Related Mode", 1)[1].split("\n## ", 1)[0]
        for required in ("next-bd --related", "agent-claim:v1", "Never mark", "no picker prompt",
                         "not liveness"):
            self.assertIn(required, section)


if __name__ == "__main__":
    unittest.main()
