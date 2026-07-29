from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from workspace_fixture import SKILL_DIR, WorkspaceFixture, issue

SCRIPT = SKILL_DIR / "scripts" / "next-bd"


class NextBdTest(WorkspaceFixture):
    def run_next(self, directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return self.run_script(SCRIPT, directory, *arguments)

    def test_workspace_candidates_are_globally_ranked_and_owned(self) -> None:
        workspace = self.create_workspace(
            root_data={
                "ready": [
                    issue("root-task", 2, "task", "2026-01-04T00:00:00Z"),
                    issue("root-blocked", 2, "task", "2026-01-01T00:00:00Z"),
                    issue("root-p4", 4, "bug", "2026-01-01T00:00:00Z"),
                ],
                "blocked": [issue("root-blocked", 2, "task", "2026-01-01T00:00:00Z")],
            },
            repositories={
                "repo-a": {
                    "ready": [issue("repo-feature", 1, "feature", "2026-01-03T00:00:00Z")]
                },
                "repo-b": {
                    "ready": [
                        issue("repo-bug", 2, "bug", "2026-01-02T00:00:00Z"),
                        issue("root-blocked", 2, "task", "2026-01-03T00:00:00Z"),
                    ]
                },
            },
        )

        candidates = json.loads(self.run_next(workspace, "--json").stdout)

        self.assertEqual(
            [(candidate["repository"], candidate["id"]) for candidate in candidates],
            [
                ("repo-b", "repo-bug"),
                ("repo-a", "repo-feature"),
                ("repo-b", "root-blocked"),
                ("workspace", "root-task"),
            ],
        )
        self.assertTrue(
            all(
                candidate["selector"] == f"{candidate['repository']}:{candidate['id']}"
                and candidate["repository_path"] in {".", "repos/repo-a", "repos/repo-b"}
                for candidate in candidates
            )
        )

    def test_safe_filter_and_in_progress_output_are_owner_scoped(self) -> None:
        workspace = self.create_workspace(
            repositories={
                "repo-a": {
                    "ready": [
                        issue(
                            "same-owner-busy",
                            2,
                            "task",
                            "2026-01-01T00:00:00Z",
                            labels=["shared"],
                        ),
                        issue("unlabelled", 2, "task", "2026-01-02T00:00:00Z"),
                    ],
                    "in_progress": [
                        issue(
                            "active-a",
                            2,
                            "feature",
                            "2026-01-01T00:00:00Z",
                            labels=["shared"],
                        )
                    ],
                },
                "repo-b": {
                    "ready": [
                        issue(
                            "other-owner-ready",
                            2,
                            "task",
                            "2026-01-01T00:00:00Z",
                            labels=["shared"],
                        )
                    ]
                },
            }
        )

        candidates = json.loads(
            self.run_next(workspace, "--json", "--avoid-busy").stdout
        )
        self.assertEqual(
            {(candidate["repository"], candidate["id"]) for candidate in candidates},
            {("repo-a", "unlabelled"), ("repo-b", "other-owner-ready")},
        )

        markdown = self.run_next(workspace, "--in-progress").stdout
        self.assertIn("| # | Repo | ID | Pri | Type | Labels | Title |", markdown)
        self.assertIn('[repo-a] `active-a`', markdown)

    def test_bug_filter_preserves_global_ranking(self) -> None:
        workspace = self.create_workspace(
            root_data={
                "ready": [issue("root-bug", 3, "bug", "2026-01-01T00:00:00Z")]
            },
            repositories={
                "repo-a": {
                    "ready": [issue("feature", 1, "feature", "2026-01-01T00:00:00Z")]
                },
                "repo-b": {
                    "ready": [issue("repo-bug", 2, "bug", "2026-01-02T00:00:00Z")]
                },
            },
        )

        candidates = json.loads(
            self.run_next(workspace, "--json", "--type=bug").stdout
        )
        self.assertEqual(
            [(candidate["repository"], candidate["id"]) for candidate in candidates],
            [("repo-b", "repo-bug"), ("workspace", "root-bug")],
        )

    def test_invalid_workspace_lookalike_falls_back_to_root_store(self) -> None:
        workspace = self.create_workspace(
            root_data={
                "ready": [issue("root-task", 2, "task", "2026-01-01T00:00:00Z")]
            },
            repositories={
                "repo-a": {
                    "ready": [issue("repo-task", 1, "task", "2026-01-01T00:00:00Z")]
                }
            },
        )
        readme = workspace / "README.md"
        valid_readme = readme.read_text(encoding="utf-8")
        readme.write_text(valid_readme.replace("`repo-a`", "`other`", 1), encoding="utf-8")

        candidates = json.loads(self.run_next(workspace, "--json").stdout)
        self.assertEqual([candidate["id"] for candidate in candidates], ["root-task"])
        self.assertNotIn("repository", candidates[0])

        readme.write_text(valid_readme, encoding="utf-8")
        agents = workspace / "AGENTS.md"
        agents.unlink()
        candidates = json.loads(self.run_next(workspace, "--json").stdout)
        self.assertEqual([candidate["id"] for candidate in candidates], ["root-task"])
        self.assertNotIn("repository", candidates[0])

        agents.write_text("# Fixture agents\n", encoding="utf-8")
        docs = workspace / "docs"
        shutil.rmtree(docs)
        docs_target = self.base / "docs-target"
        for name in ("prds", "adrs", "architecture", "runbooks"):
            (docs_target / name).mkdir(parents=True)
        docs.symlink_to(os.path.relpath(docs_target, docs.parent), target_is_directory=True)
        candidates = json.loads(self.run_next(workspace, "--json").stdout)
        self.assertEqual([candidate["id"] for candidate in candidates], ["root-task"])
        self.assertNotIn("repository", candidates[0])

    def test_single_store_output_remains_compatible(self) -> None:
        local = self.base / "local"
        self.create_store(
            local,
            ready=[issue("local-task", 2, "task", "2026-01-01T00:00:00Z")],
        )

        candidates = json.loads(self.run_next(local, "--json").stdout)
        self.assertEqual(candidates[0]["id"], "local-task")
        self.assertEqual(candidates[0]["rank"], 6)
        self.assertNotIn("repository", candidates[0])
        self.assertNotIn("repository_path", candidates[0])
        self.assertNotIn("selector", candidates[0])

        markdown = self.run_next(local).stdout
        self.assertIn("| # | ID | Pri | Type | Labels | Title |", markdown)
        self.assertNotIn("| Repo |", markdown)


if __name__ == "__main__":
    unittest.main()
