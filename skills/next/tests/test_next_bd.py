from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).parents[1] / "scripts" / "next-bd"


def issue(
    issue_id: str,
    priority: int,
    issue_type: str,
    created_at: str,
    *,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": issue_id,
        "title": f"Title for {issue_id}",
        "priority": priority,
        "issue_type": issue_type,
        "labels": labels or [],
        "created_at": created_at,
    }


class NextBdTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.fake_bin = self.base / "bin"
        self.fake_bin.mkdir()
        fake_bd = self.fake_bin / "bd"
        fake_bd.write_text(
            """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

payload = json.loads((Path.cwd() / '.beads' / 'fixture.json').read_text())
arguments = sys.argv[1:]
if arguments[0] == 'blocked':
    key = 'blocked'
elif '--ready' in arguments:
    key = 'ready'
elif '--status=in_progress' in arguments:
    key = 'in_progress'
else:
    raise SystemExit(2)
print(json.dumps(payload[key]))
""",
            encoding="utf-8",
        )
        fake_bd.chmod(0o755)
        self.environment = os.environ.copy()
        self.environment["PATH"] = f"{self.fake_bin}:{self.environment['PATH']}"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create_store(
        self,
        directory: Path,
        *,
        ready: list[dict[str, Any]] | None = None,
        blocked: list[dict[str, Any]] | None = None,
        in_progress: list[dict[str, Any]] | None = None,
    ) -> None:
        directory.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "-q", "--initial-branch=main"],
            cwd=directory,
            check=True,
        )
        beads = directory / ".beads"
        beads.mkdir()
        (beads / "fixture.json").write_text(
            json.dumps(
                {
                    "ready": ready or [],
                    "blocked": blocked or [],
                    "in_progress": in_progress or [],
                }
            ),
            encoding="utf-8",
        )

    def create_workspace(
        self,
        *,
        root_data: dict[str, list[dict[str, Any]]] | None = None,
        repositories: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
    ) -> Path:
        root = self.base / "workspace"
        self.create_store(root, **(root_data or {}))
        (root / "repos").mkdir()
        (root / "infrastructure").mkdir()
        for relative_path in (
            "docs/prds",
            "docs/adrs",
            "docs/architecture",
            "docs/runbooks",
        ):
            (root / relative_path).mkdir(parents=True)
        (root / "AGENTS.md").write_text("# Fixture agents\n", encoding="utf-8")
        (root / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")

        entries = []
        for index, (name, data) in enumerate((repositories or {}).items()):
            target = self.base / "sources" / name
            self.create_store(target, **data)
            link = root / "repos" / name
            link.symlink_to(os.path.relpath(target, link.parent), target_is_directory=True)
            entries.append(
                {
                    "name": name,
                    "path": f"repos/{name}",
                    "role": "primary" if index == 0 else "service",
                }
            )

        manifest = {
            "version": 1,
            "name": "Fixture Workspace",
            "repositories": entries,
            "infrastructure": [],
        }
        (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
        repository_lines = "\n".join(
            f"- `{entry['name']}` — [`{entry['path']}`]({entry['path']}) ({entry['role']})"
            for entry in entries
        ) or "_No repositories are registered yet._"
        (root / "README.md").write_text(
            "# Fixture Workspace\n\n"
            "<!-- project-workspace:repositories:start -->\n"
            f"{repository_lines}\n"
            "<!-- project-workspace:repositories:end -->\n\n"
            "<!-- project-workspace:infrastructure:start -->\n"
            "_No infrastructure references are registered yet._\n"
            "<!-- project-workspace:infrastructure:end -->\n",
            encoding="utf-8",
        )
        return root

    def run_next(self, directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPT), *arguments],
            cwd=directory,
            env=self.environment,
            capture_output=True,
            check=True,
            text=True,
        )

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
