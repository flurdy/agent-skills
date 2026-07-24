#!/usr/bin/env python3
"""End-to-end tests for the project-workspace scaffold CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
CLI = REPOSITORY / "scripts" / "project-workspace"


class ProjectWorkspaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.command_log = self.root / "commands.log"
        self.write_command(
            "git",
            'echo "git $*" >> "$COMMAND_LOG"\n'
            'if [[ "$1" == "-C" ]]; then\n'
            '  [[ -f "$2/.git/project-workspace-initialized" ]] && echo true\n'
            "  exit\n"
            "fi\n"
            "mkdir -p .git\n"
            'if [[ "${GIT_FAIL_ONCE:-}" == "1" && ! -f "$COMMAND_LOG.git-failed" ]]; then\n'
            '  touch "$COMMAND_LOG.git-failed"\n'
            "  exit 1\n"
            "fi\n"
            "touch .git/project-workspace-initialized\n",
        )
        self.write_command(
            "bd",
            'echo "bd $*" >> "$COMMAND_LOG"\n'
            "mkdir -p .beads\n"
            'if [[ "${BD_FAIL_ONCE:-}" == "1" && ! -f "$COMMAND_LOG.bd-failed" ]]; then\n'
            '  touch "$COMMAND_LOG.bd-failed"\n'
            "  exit 1\n"
            "fi\n",
        )
        self.environment = os.environ.copy()
        self.environment["COMMAND_LOG"] = str(self.command_log)
        self.environment["PATH"] = f"{self.bin}:{self.environment.get('PATH', '')}"

    def write_command(self, name: str, body: str) -> None:
        command = self.bin / name
        command.write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n{body}", encoding="utf-8")
        command.chmod(0o755)

    def run_cli(
        self, *arguments: str, cwd: Path | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *arguments],
            capture_output=True,
            check=check,
            cwd=cwd or self.root,
            env=self.environment,
            text=True,
        )

    def test_initialises_named_greenfield_workspace_and_reruns_safely(self) -> None:
        workspace = self.root / "example-project"

        result = self.run_cli("init", "Example Project")

        self.assertIn(f"Initialised workspace: {workspace}", result.stdout)
        self.assertTrue((workspace / ".git").is_dir())
        self.assertTrue((workspace / ".beads").is_dir())
        self.assertTrue((workspace / "docs" / "adrs" / ".gitkeep").is_file())
        self.assertTrue((workspace / "infrastructure" / ".gitkeep").is_file())
        manifest = json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))
        self.assertEqual("Example Project", manifest["name"])
        self.assertEqual([], manifest["repositories"])
        self.assertEqual([], manifest["infrastructure"])
        first_commands = self.command_log.read_text(encoding="utf-8")
        self.assertIn("git init -b main", first_commands)
        self.assertIn("bd init --init-if-missing --non-interactive --skip-agents", first_commands)

        rerun = self.run_cli("init", "Example Project")

        self.assertEqual(0, rerun.returncode)
        rerun_commands = self.command_log.read_text(encoding="utf-8")
        self.assertEqual(1, rerun_commands.count("git init -b main"))
        self.assertEqual(2, rerun_commands.count("bd init --init-if-missing"))

    def test_links_existing_repository_without_absorbing_it(self) -> None:
        repository = self.root / "application"
        (repository / ".git").mkdir(parents=True)
        workspace = self.root / "operations"

        self.run_cli("init", "--repo", str(repository), "--output", str(workspace))

        link = workspace / "repos" / "application"
        self.assertTrue(link.is_symlink())
        self.assertEqual(repository, link.resolve())
        self.assertFalse((repository / "workspace.json").exists())
        manifest = json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [{"name": "application", "path": "repos/application", "role": "primary"}],
            manifest["repositories"],
        )
        readme = (workspace / "README.md").read_text(encoding="utf-8")
        self.assertIn("[`repos/application`](repos/application)", readme)

    def test_dry_run_reports_plan_without_writing(self) -> None:
        workspace = self.root / "preview"

        result = self.run_cli(
            "init", "Preview", "--output", str(workspace), "--dry-run"
        )

        self.assertIn("CREATE file workspace.json", result.stdout)
        self.assertIn("RUN git init -b main", result.stdout)
        self.assertIn("RUN bd init", result.stdout)
        self.assertFalse(workspace.exists())
        self.assertFalse(self.command_log.exists())

    def test_conflict_fails_before_other_content_is_created(self) -> None:
        workspace = self.root / "conflict"
        workspace.mkdir()
        readme = workspace / "README.md"
        readme.write_text("keep me\n", encoding="utf-8")

        result = self.run_cli(
            "init", "Conflict", "--output", str(workspace), check=False
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("refusing to overwrite", result.stderr)
        self.assertEqual("keep me\n", readme.read_text(encoding="utf-8"))
        self.assertFalse((workspace / "workspace.json").exists())
        self.assertFalse((workspace / ".git").exists())
        self.assertFalse((workspace / ".beads").exists())

    def test_rejects_workspace_nested_inside_existing_repository(self) -> None:
        repository = self.root / "application"
        (repository / ".git").mkdir(parents=True)

        result = self.run_cli(
            "init",
            "--repo",
            str(repository),
            "--output",
            str(repository / "workspace"),
            check=False,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("must be separate directories", result.stderr)
        self.assertFalse((repository / "workspace").exists())

    def test_rejects_existing_foreign_git_repository_as_output(self) -> None:
        workspace = self.root / "foreign"
        (workspace / ".git").mkdir(parents=True)

        result = self.run_cli(
            "init", "Foreign", "--output", str(workspace), check=False
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("existing Git repository", result.stderr)
        self.assertFalse((workspace / "workspace.json").exists())

    def test_rejects_symlinked_workspace_root_and_managed_directory(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        root_link = self.root / "linked-root"
        root_link.symlink_to(outside, target_is_directory=True)

        root_result = self.run_cli(
            "init", "Linked", "--output", str(root_link), check=False
        )

        self.assertNotEqual(0, root_result.returncode)
        self.assertIn("root must not be a symlink", root_result.stderr)
        self.assertEqual([], list(outside.iterdir()))

        workspace = self.root / "managed-link"
        workspace.mkdir()
        (workspace / "docs").symlink_to(outside, target_is_directory=True)

        directory_result = self.run_cli(
            "init", "Managed Link", "--output", str(workspace), check=False
        )

        self.assertNotEqual(0, directory_result.returncode)
        self.assertIn("managed directory must not be a symlink", directory_result.stderr)
        self.assertEqual([], list(outside.iterdir()))

    def test_recovers_from_partial_git_and_beads_initialisation(self) -> None:
        git_workspace = self.root / "git-recovery"
        self.environment["GIT_FAIL_ONCE"] = "1"

        first_git = self.run_cli(
            "init", "Git Recovery", "--output", str(git_workspace), check=False
        )
        second_git = self.run_cli(
            "init", "Git Recovery", "--output", str(git_workspace)
        )

        self.assertNotEqual(0, first_git.returncode)
        self.assertEqual(0, second_git.returncode)
        commands = self.command_log.read_text(encoding="utf-8")
        self.assertEqual(2, commands.count("git init -b main"))
        self.environment.pop("GIT_FAIL_ONCE")

        beads_workspace = self.root / "beads-recovery"
        self.environment["BD_FAIL_ONCE"] = "1"
        first_beads = self.run_cli(
            "init", "Beads Recovery", "--output", str(beads_workspace), check=False
        )
        second_beads = self.run_cli(
            "init", "Beads Recovery", "--output", str(beads_workspace)
        )

        self.assertNotEqual(0, first_beads.returncode)
        self.assertEqual(0, second_beads.returncode)
        commands = self.command_log.read_text(encoding="utf-8")
        self.assertGreaterEqual(commands.count("bd init --init-if-missing"), 3)

    def test_generated_make_doctor_validates_state_and_links(self) -> None:
        repository = self.root / "doctor-repository"
        (repository / ".git").mkdir(parents=True)
        workspace = self.root / "doctor"
        self.run_cli(
            "init", "--repo", str(repository), "--output", str(workspace)
        )

        result = subprocess.run(
            ["make", "doctor"],
            capture_output=True,
            check=True,
            cwd=workspace,
            env=self.environment,
            text=True,
        )

        self.assertIn("Workspace: PASS", result.stdout)

        (workspace / "repos" / "doctor-repository").unlink()
        failed = subprocess.run(
            ["make", "doctor"],
            capture_output=True,
            check=False,
            cwd=workspace,
            env=self.environment,
            text=True,
        )
        self.assertNotEqual(0, failed.returncode)


if __name__ == "__main__":
    unittest.main()
