from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock
from pathlib import Path
from typing import Any

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

    def test_failing_source_keeps_healthy_candidates_and_reports_diagnostic(self) -> None:
        workspace = self.create_workspace(
            root_data={
                "ready": [issue("root-task", 2, "task", "2026-01-01T00:00:00Z")]
            },
            repositories={
                "healthy": {
                    "ready": [issue("healthy-task", 1, "task", "2026-01-01T00:00:00Z")]
                },
                "broken": {
                    "ready": [issue("hidden-task", 0, "bug", "2026-01-01T00:00:00Z")],
                    "faults": {"ready": "error"},
                },
            },
        )

        result = self.run_next(workspace, "--json")
        candidates = json.loads(result.stdout)

        self.assertEqual(
            [(candidate["repository"], candidate["id"]) for candidate in candidates],
            [("healthy", "healthy-task"), ("workspace", "root-task")],
        )
        self.assertIn("next-bd: broken: ready: simulated ready failure", result.stderr)
        calls = self.recorded_calls()
        self.assertTrue(all("--readonly" in call["arguments"] for call in calls))
        self.assertFalse(any(call["arguments"][0] == "update" for call in calls))

    def test_late_source_failure_discards_its_partial_results(self) -> None:
        workspace = self.create_workspace(
            root_data={
                "ready": [issue("root-task", 2, "task", "2026-01-01T00:00:00Z")]
            },
            repositories={
                "broken": {
                    "ready": [issue("unsafe-task", 0, "bug", "2026-01-01T00:00:00Z")],
                    "faults": {"blocked": "error"},
                }
            },
        )

        result = self.run_next(workspace, "--json")

        self.assertEqual(
            [candidate["id"] for candidate in json.loads(result.stdout)],
            ["root-task"],
        )
        self.assertIn("broken: blocked: simulated blocked failure", result.stderr)

    def test_malformed_and_unusable_sources_have_concise_diagnostics(self) -> None:
        workspace = self.create_workspace(
            root_data={
                "ready": [issue("root-task", 2, "task", "2026-01-01T00:00:00Z")]
            },
            repositories={
                "malformed": {"faults": {"ready": "invalid-json"}},
                "missing": {},
                "symlinked": {},
            },
        )
        shutil.rmtree(self.base / "sources" / "missing" / ".beads")
        symlinked = self.base / "sources" / "symlinked" / ".beads"
        shutil.rmtree(symlinked)
        symlinked.symlink_to(self.base / "external-beads", target_is_directory=True)

        result = self.run_next(workspace)

        self.assertIn("workspace | root-task", result.stdout)
        self.assertIn("malformed: ready: invalid bd JSON", result.stdout)
        self.assertIn("missing: missing .beads store", result.stdout)
        self.assertIn("symlinked: unusable .beads store: symlink", result.stdout)

    def test_timed_out_source_is_reported_without_hiding_healthy_source(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "next_collect_test", SKILL_DIR / "scripts" / "collect.py"
        )
        collector = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = collector
        spec.loader.exec_module(collector)
        source = collector.Source("slow", "repos/slow", self.base / "slow")

        with mock.patch.object(
            collector.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["bd"], 5),
        ):
            issues, error = collector.load_issues(source, ["list", "--ready"])

        self.assertEqual(issues, [])
        self.assertEqual(error, "timed out after 5 seconds")

        workspace = self.create_workspace(
            repositories={"healthy": {}, "slow": {}}
        )

        def load_fixture(
            source: Any, arguments: list[str]
        ) -> tuple[list[dict[str, Any]], str | None]:
            if source.name == "slow":
                return [], "timed out after 5 seconds"
            if "--ready" in arguments and source.name == "healthy":
                return [issue("healthy-task", 1, "task", "2026-01-01T00:00:00Z")], None
            return [], None

        with mock.patch.object(collector, "load_issues", side_effect=load_fixture):
            payload = collector.collect(workspace)

        self.assertEqual([item["id"] for item in payload["ready"]], ["healthy-task"])
        self.assertEqual(
            payload["diagnostics"], ["slow: ready: timed out after 5 seconds"]
        )

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
