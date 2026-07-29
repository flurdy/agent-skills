from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from workspace_fixture import SKILL_DIR, WorkspaceFixture, issue

SCRIPT = SKILL_DIR / "scripts" / "next-select"

FAKE_HANDOFF_LIST = """#!/usr/bin/env bash
set -euo pipefail
echo "---HANDOFF-CWD---"
pwd -P
echo "---HANDOFF-ARGS---"
printf '%s\\n' "$@"
"""


class NextSelectTest(WorkspaceFixture):
    def run_select(
        self, directory: Path, *arguments: str, script: Path = SCRIPT
    ) -> subprocess.CompletedProcess[str]:
        return self.run_script(script, directory, *arguments, check=False)

    def colliding_workspace(self) -> Path:
        return self.create_workspace(
            root_data={"ready": [issue("root-task", 3, "task", "2026-01-04T00:00:00Z")]},
            repositories={
                "repo-a": {
                    "ready": [issue("dup-1", 2, "task", "2026-01-02T00:00:00Z")],
                    "other": [issue("only-a", 2, "task", "2026-01-01T00:00:00Z")],
                },
                "repo-b": {
                    "ready": [issue("dup-1", 1, "bug", "2026-01-01T00:00:00Z")]
                },
            },
        )

    def update_calls(self) -> list[dict[str, object]]:
        return [
            call for call in self.recorded_calls() if call["arguments"][0] == "update"
        ]

    def test_index_selection_resolves_the_owning_store(self) -> None:
        workspace = self.colliding_workspace()

        result = self.run_select(workspace, "resolve", "1")

        self.assertEqual(result.returncode, 0)
        resolved = json.loads(result.stdout)
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["repository"], "repo-b")
        self.assertEqual(resolved["repository_path"], "repos/repo-b")
        self.assertEqual(
            Path(resolved["directory"]),
            (self.base / "sources" / "repo-b").resolve(),
        )
        self.assertEqual(self.update_calls(), [])

    def test_out_of_range_index_resolves_to_nothing(self) -> None:
        workspace = self.colliding_workspace()

        result = self.run_select(workspace, "resolve", "99")

        self.assertEqual(result.returncode, 4)
        self.assertEqual(json.loads(result.stdout)["status"], "not-found")
        self.assertEqual(self.update_calls(), [])

    def test_colliding_bare_id_is_rejected_before_mutation(self) -> None:
        workspace = self.colliding_workspace()

        for command in ("resolve", "start"):
            result = self.run_select(workspace, command, "dup-1")

            self.assertEqual(result.returncode, 3)
            rejected = json.loads(result.stdout)
            self.assertEqual(rejected["status"], "ambiguous")
            self.assertEqual(
                sorted(match["selector"] for match in rejected["matches"]),
                ["repo-a:dup-1", "repo-b:dup-1"],
            )
        self.assertEqual(self.update_calls(), [])

    def test_qualified_selector_starts_only_in_the_owning_store(self) -> None:
        workspace = self.colliding_workspace()

        result = self.run_select(workspace, "start", "repo-b:dup-1")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            [
                (Path(str(call["directory"])), call["arguments"])
                for call in self.update_calls()
            ],
            [
                (
                    (self.base / "sources" / "repo-b").resolve(),
                    ["update", "dup-1", "--status=in_progress"],
                )
            ],
        )

    def test_unqualified_id_outside_the_ready_list_resolves_to_its_owner(self) -> None:
        workspace = self.colliding_workspace()

        result = self.run_select(workspace, "resolve", "only-a")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["repository"], "repo-a")

    def test_qualifier_that_does_not_own_the_bead_is_rejected(self) -> None:
        workspace = self.colliding_workspace()

        for selector in ("repo-b:only-a", "nosuch:dup-1"):
            result = self.run_select(workspace, "start", selector)

            self.assertEqual(result.returncode, 4)
            rejected = json.loads(result.stdout)
            self.assertEqual(rejected["status"], "not-found")
            self.assertEqual(rejected["selector"], selector)
        self.assertEqual(self.update_calls(), [])

    def test_index_whose_bead_moved_is_rejected_before_mutation(self) -> None:
        workspace = self.colliding_workspace()

        result = self.run_select(workspace, "start", "1", "--expect-id", "root-task")

        self.assertEqual(result.returncode, 6)
        stale = json.loads(result.stdout)
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["expected"], "root-task")
        self.assertEqual(stale["actual"], "dup-1")
        self.assertEqual(self.update_calls(), [])

    def test_bare_id_probe_failure_is_unavailable_before_mutation(self) -> None:
        workspace = self.create_workspace(
            repositories={
                "healthy": {
                    "other": [issue("healthy-only", 2, "task", "2026-01-01T00:00:00Z")]
                },
                "broken": {"faults": {"probe": "error"}},
            }
        )

        result = self.run_select(workspace, "start", "healthy-only")

        self.assertEqual(result.returncode, 5)
        unavailable = json.loads(result.stdout)
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertEqual(unavailable["matches"][0]["selector"], "healthy:healthy-only")
        self.assertEqual(unavailable["failures"][0]["repository"], "broken")
        self.assertIn("simulated probe failure", unavailable["failures"][0]["error"])
        self.assertEqual(self.update_calls(), [])

    def test_qualified_and_index_selection_keep_healthy_source_usable(self) -> None:
        workspace = self.create_workspace(
            root_data={
                "ready": [issue("root-task", 2, "task", "2026-01-01T00:00:00Z")]
            },
            repositories={
                "healthy": {
                    "other": [issue("healthy-only", 2, "task", "2026-01-01T00:00:00Z")]
                },
                "broken": {
                    "faults": {"ready": "error", "probe": "error"}
                },
            },
        )

        qualified = self.run_select(workspace, "start", "healthy:healthy-only")
        indexed = self.run_select(
            workspace, "start", "1", "--expect-id", "root-task"
        )

        self.assertEqual(qualified.returncode, 0)
        self.assertEqual(indexed.returncode, 0)
        self.assertEqual(
            [Path(str(call["directory"])) for call in self.update_calls()],
            [(self.base / "sources" / "healthy").resolve(), workspace.resolve()],
        )

    def test_qualified_source_probe_failure_is_unavailable(self) -> None:
        workspace = self.create_workspace(
            repositories={"broken": {"faults": {"probe": "invalid-json"}}}
        )

        result = self.run_select(workspace, "start", "broken:any-id")

        self.assertEqual(result.returncode, 5)
        unavailable = json.loads(result.stdout)
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertEqual(unavailable["failures"][0]["repository"], "broken")
        self.assertIn("invalid bd JSON", unavailable["failures"][0]["error"])
        self.assertEqual(self.update_calls(), [])

    def test_handoff_lookup_runs_in_the_owning_repository(self) -> None:
        workspace = self.colliding_workspace()
        skills_root = self.base / "skills"
        shutil.copytree(SKILL_DIR, skills_root / "next")
        handoff_list = skills_root / "handoffs" / "scripts" / "list.sh"
        handoff_list.parent.mkdir(parents=True)
        handoff_list.write_text(FAKE_HANDOFF_LIST, encoding="utf-8")
        handoff_list.chmod(0o755)

        result = self.run_select(
            workspace,
            "handoff",
            "repo-b:dup-1",
            "--check-branches",
            script=skills_root / "next" / "scripts" / "next-select",
        )

        self.assertEqual(result.returncode, 0)
        cwd_line, arguments = result.stdout.split("---HANDOFF-ARGS---")
        self.assertEqual(
            Path(cwd_line.splitlines()[1]),
            (self.base / "sources" / "repo-b").resolve(),
        )
        self.assertEqual(arguments.split(), ["--bead", "dup-1", "--check-branches"])
        self.assertEqual(self.update_calls(), [])

    def test_local_mode_keeps_shorthand_and_store_fallback_behavior(self) -> None:
        local = self.base / "local-compat"
        self.create_store(
            local, ready=[issue("local-task", 2, "task", "2026-01-01T00:00:00Z")]
        )

        shorthand = self.run_select(local, "resolve", "task")
        self.assertEqual(shorthand.returncode, 0)
        self.assertEqual(json.loads(shorthand.stdout)["id"], "task")

        beads_target = self.base / "local-beads"
        shutil.move(local / ".beads", beads_target)
        (local / ".beads").symlink_to(beads_target, target_is_directory=True)
        candidates = self.run_script(
            SKILL_DIR / "scripts" / "next-bd", local, "--json"
        )
        symlinked = self.run_select(local, "resolve", "task")
        self.assertEqual([item["id"] for item in json.loads(candidates.stdout)], ["local-task"])
        self.assertEqual(symlinked.returncode, 0)

        (local / ".beads").unlink()
        missing = self.run_select(local, "resolve", "local-task")
        self.assertEqual(missing.returncode, 4)
        self.assertEqual(json.loads(missing.stdout)["status"], "not-found")
        self.assertEqual(self.update_calls(), [])

    def test_local_mode_routes_to_the_current_store(self) -> None:
        local = self.base / "local"
        self.create_store(
            local, ready=[issue("local-task", 2, "task", "2026-01-01T00:00:00Z")]
        )

        resolved = json.loads(self.run_select(local, "resolve", "local-task").stdout)
        self.assertEqual(resolved["workspace"], False)
        self.assertEqual(resolved["repository"], "local")
        self.assertEqual(Path(resolved["directory"]), local.resolve())

        self.assertEqual(self.run_select(local, "start", "1").returncode, 0)
        self.assertEqual(
            [Path(str(call["directory"])) for call in self.update_calls()],
            [local.resolve()],
        )


if __name__ == "__main__":
    unittest.main()
