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

    def test_help_prints_supported_options_without_collecting(self) -> None:
        result = self.run_next(self.base, "--help")

        self.assertIn("Usage: next-bd [OPTIONS]", result.stdout)
        for option in ("--list", "--in-progress", "--avoid-busy", "--json", "--type=TYPE"):
            self.assertIn(option, result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.recorded_calls(), [])

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
        self.assertIn(
            "Tracker status: in progress (session activity unverified):", markdown
        )
        self.assertNotIn("other sessions", markdown)
        self.assertIn('[repo-a] `active-a`', markdown)

    def test_full_listing_renders_complete_non_selectable_tables(self) -> None:
        data = {
            category: [
                issue(f"{category}-{index}", 2 if category == "ready" else 4,
                      "task", "2026-01-01T00:00:00Z", labels=["scope"])
                for index in range(55)
            ]
            for category in ("ready", "in_progress", "blocked", "deferred")
        }
        data["blocked"][0]["blocked_by"] = ["dep-a", "dep-b"]
        data["blocked"][1]["blocked_by_count"] = 3
        data["deferred"][0]["defer_until"] = "2026-10-01T12:00:00Z"
        workspace = self.create_workspace(repositories={"repo-a": data})
        local = self.base / "local"
        self.create_store(local, **data)

        for directory, owner in ((workspace, "repo-a | "), (local, "")):
            with self.subTest(workspace=bool(owner)):
                result = self.run_next(directory, "--list")
                self.assertEqual(result.stderr, "")
                self.assertIn("## Ready to Work (55 beads)", result.stdout)
                for heading in ("In Progress", "Blocked", "Deferred"):
                    self.assertIn(f"## {heading} (55 beads; not selectable)", result.stdout)
                self.assertIn("session activity unverified", result.stdout)
                self.assertIn("| Blocked by |", result.stdout)
                self.assertIn("| Defer until |", result.stdout)
                self.assertIn("dep-a, dep-b", result.stdout)
                self.assertIn("3 blockers", result.stdout)
                self.assertIn("2026-10-01T12:00:00Z", result.stdout)
                for category in ("in_progress", "blocked", "deferred"):
                    for index in range(55):
                        self.assertIn(f"| {owner}{category}-{index} | P4 |", result.stdout)
                self.assertIn(f"| {owner}deferred-1 | P4 | task | scope | Title for deferred-1 | — |", result.stdout)
                self.assertEqual("| Repo |" in result.stdout, bool(owner))
                self.assertEqual(result.stdout.count("| # |"), 1)
                self.assertEqual(result.stdout.count("| 1 |"), 1)
                combined = self.run_next(directory, "--list", "--in-progress").stdout
                self.assertEqual(combined, result.stdout)
                candidates = self.run_next(directory, "--json").stdout
                self.assertEqual(self.run_next(directory, "--list", "--json").stdout, candidates)
                self.assertEqual(len(json.loads(candidates)), 55)

        calls = self.recorded_calls()
        self.assertTrue(all("--readonly" in call["arguments"] for call in calls))
        for call in calls:
            if call["arguments"][0] == "list":
                self.assertIn("--limit=0", call["arguments"])
        self.assertTrue(any("--status=deferred" in call["arguments"] for call in calls))

    def test_full_listing_shows_empty_categories(self) -> None:
        workspace = self.create_workspace()
        local = self.base / "local"
        self.create_store(local)
        for directory in (workspace, local):
            with self.subTest(directory=directory):
                markdown = self.run_next(directory, "--list").stdout
                self.assertIn("## Ready to Work (0 beads)", markdown)
                for heading in ("In Progress", "Blocked", "Deferred"):
                    self.assertIn(f"## {heading} (0 beads; not selectable)", markdown)
                self.assertEqual(markdown.count("_None._"), 3)

    def test_every_category_failure_discards_source_including_local(self) -> None:
        categories = ("ready", "blocked", "in_progress", "deferred")
        for category in categories:
            for fault in ("error", "invalid-json"):
                with self.subTest(category=category, fault=fault):
                    broken = {
                        key: [issue(f"unsafe-{key}", 0, "bug", "2026-01-01T00:00:00Z")]
                        for key in categories
                    }
                    broken["faults"] = {category: fault}
                    local = self.base / f"{category}-{fault}"
                    self.create_store(local, **broken)
                    result = self.run_next(local, "--list")
                    self.assertNotIn("unsafe-", result.stdout)
                    self.assertIn(f"local: {category}:", result.stdout)
                    result = self.run_next(local, "--json")
                    self.assertEqual(json.loads(result.stdout), [])
                    self.assertIn(f"local: {category}:", result.stderr)

        workspace = self.create_workspace(
            root_data={"ready": [issue("healthy", 2, "task", "2026-01-01T00:00:00Z")]},
            repositories={"broken": broken},
        )
        for category in categories:
            for fault in ("error", "invalid-json"):
                with self.subTest(workspace=True, category=category, fault=fault):
                    broken["faults"] = {category: fault}
                    (self.base / "sources/broken/.beads/fixture.json").write_text(json.dumps(broken))
                    result = self.run_next(workspace, "--list")
                    self.assertIn("| workspace | healthy |", result.stdout)
                    self.assertNotIn("unsafe-", result.stdout)
                    self.assertIn(f"broken: {category}:", result.stdout)
                    result = self.run_next(workspace, "--json")
                    self.assertEqual([row["id"] for row in json.loads(result.stdout)], ["healthy"])
                    self.assertIn(f"broken: {category}:", result.stderr)

    def test_full_listing_preserves_ready_index_resolution(self) -> None:
        data = {
            "ready": [
                issue("task", 2, "task", "2026-01-01T00:00:00Z"),
                issue("bug", 1, "bug", "2026-01-02T00:00:00Z"),
            ],
            "in_progress": [issue("claimed", 0, "bug", "2026-01-01T00:00:00Z")],
            "blocked": [issue("blocked", 0, "bug", "2026-01-01T00:00:00Z")],
            "deferred": [issue("deferred", 0, "bug", "2026-01-01T00:00:00Z")],
        }
        workspace = self.create_workspace(repositories={"repo-a": data})
        local = self.base / "local"
        self.create_store(local, **data)
        for directory, owner in ((workspace, "repo-a | "), (local, "")):
            markdown = self.run_next(directory, "--list").stdout
            for index, issue_id in enumerate(("bug", "task"), 1):
                with self.subTest(directory=directory, index=index):
                    self.assertIn(f"| {index} | {owner}{issue_id} |", markdown)
                    result = self.run_script(
                        SKILL_DIR / "scripts/next-select", directory,
                        "resolve", str(index), "--expect-id", issue_id,
                    )
                    self.assertEqual(json.loads(result.stdout)["id"], issue_id)

    def test_listing_instructions_require_all_sections(self) -> None:
        skill = (SKILL_DIR / "SKILL.md").read_text()
        listing = skill.split("## Listing Mode (default and `list`)", 1)[1].split("## Handling Edge Cases", 1)[0]
        for required in ("next-bd --list", "all four sections", "in-progress, blocked, and deferred",
                         "_None._", "non-selectable", "never picker indexes"):
            self.assertIn(required, listing)

    def test_non_ready_cells_cannot_split_markdown_rows(self) -> None:
        local = self.base / "local"
        row = issue("blocked", 2, "task", "2026-01-01T00:00:00Z")
        row["title"] = "first | second\nthird"
        row["blocked_by"] = ["dep|one", "dep\ntwo"]
        self.create_store(local, blocked=[row])
        markdown = self.run_next(local, "--list").stdout
        self.assertIn("first &#124; second third", markdown)
        self.assertIn("dep&#124;one, dep two", markdown)

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
            in_progress=[
                issue("local-claimed", 2, "bug", "2026-01-02T00:00:00Z")
            ],
        )

        candidates = json.loads(self.run_next(local, "--json").stdout)
        self.assertEqual(candidates[0]["id"], "local-task")
        self.assertEqual(candidates[0]["rank"], 6)
        self.assertNotIn("repository", candidates[0])
        self.assertNotIn("repository_path", candidates[0])
        self.assertNotIn("selector", candidates[0])

        markdown = self.run_next(local, "--in-progress").stdout
        self.assertIn("| # | ID | Pri | Type | Labels | Title |", markdown)
        self.assertNotIn("| Repo |", markdown)
        self.assertIn(
            "Tracker status: in progress (session activity unverified):", markdown
        )
        self.assertNotIn("other sessions", markdown)
        self.assertIn('`local-claimed` (P2 bug)', markdown)


if __name__ == "__main__":
    unittest.main()
