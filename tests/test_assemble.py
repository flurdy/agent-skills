#!/usr/bin/env python3
"""Filesystem-isolated tests for the shared skill assembler."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
ASSEMBLER = REPOSITORY / "assemble.sh"
MAKEFILE = REPOSITORY / "Makefile"
MANAGED_ENV = (
    "SKILLS_DIR",
    "CLAUDE_SKILLS_DIR",
    "LEGACY_CODEX_SKILLS_DIR",
    "AGENTS_DIR",
    "SKIP_AGENTS",
    "LAYERS_ORDER",
    "MACHINE",
    "CLIENTS",
    "PI_SETTINGS_FILE",
)


class AssembleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.shared = self.root / "shared"
        self.private = self.root / "private"
        self.home.mkdir()
        self.shared.mkdir()
        self.private.mkdir()
        self.skill(self.shared / "skills", "alpha", "shared")
        self.agent(self.shared / "agents", "reviewer.md", "shared")

    @property
    def canonical(self) -> Path:
        return self.home / ".agents" / "skills"

    @property
    def claude(self) -> Path:
        return self.home / ".claude" / "skills"

    @property
    def codex(self) -> Path:
        return self.home / ".codex" / "skills"

    @property
    def agents(self) -> Path:
        return self.home / ".claude" / "agents"

    def skill(self, root: Path, name: str, marker: str) -> Path:
        path = root / name
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {marker}\n---\n", encoding="utf-8"
        )
        return path

    def agent(self, root: Path, name: str, marker: str) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        path = root / name
        path.write_text(marker, encoding="utf-8")
        return path

    def environment(self, **overrides: str) -> dict[str, str]:
        environment = os.environ.copy()
        for name in MANAGED_ENV:
            environment.pop(name, None)
        environment.update(
            {
                "HOME": str(self.home),
                "SHARED_REPO": str(self.shared),
                "PRIVATE_REPO": str(self.private),
                "MACHINE": "test-machine",
            }
        )
        environment.update(overrides)
        return environment

    def run_assembler(
        self, *arguments: str, check: bool = True, **environment: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(ASSEMBLER), *arguments],
            capture_output=True,
            check=check,
            env=self.environment(**environment),
            text=True,
        )

    def run_make(
        self, target: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "make",
                "-f",
                str(MAKEFILE),
                target,
                f"SHARED_REPO={self.shared}",
                f"PRIVATE_REPO={self.private}",
            ],
            capture_output=True,
            check=check,
            cwd=REPOSITORY,
            env=self.environment(),
            text=True,
        )

    def assert_link(self, path: Path, target: Path) -> None:
        self.assertTrue(path.is_symlink(), f"expected symlink: {path}")
        self.assertEqual(str(target), os.readlink(path))

    def test_fresh_apply_uses_canonical_root_and_preserves_user_content(self) -> None:
        self.claude.mkdir(parents=True)
        (self.claude / "claude-only").mkdir()
        self.codex.mkdir(parents=True)
        (self.codex / ".system").mkdir()
        (self.codex / "alpha").symlink_to(self.shared / "skills" / "alpha")
        self.canonical.mkdir(parents=True)
        (self.canonical / "personal").mkdir()

        self.run_assembler("apply")

        self.assert_link(self.canonical / "alpha", self.shared / "skills" / "alpha")
        self.assert_link(self.claude / "alpha", self.canonical / "alpha")
        self.assert_link(self.agents / "reviewer.md", self.shared / "agents" / "reviewer.md")
        self.assertTrue((self.canonical / "personal").is_dir())
        self.assertTrue((self.claude / "claude-only").is_dir())
        self.assertTrue((self.codex / ".system").is_dir())
        self.assertFalse((self.codex / "alpha").exists())
        self.assertFalse((self.codex / "alpha").is_symlink())

    def test_layer_overrides_are_shared_by_canonical_and_claude_paths(self) -> None:
        private = self.skill(self.private / "skills", "alpha", "private")
        machine = self.skill(
            self.private / "machines" / "test-machine" / "skills", "alpha", "machine"
        )
        client = self.skill(
            self.private / "clients" / "acme" / "skills", "alpha", "client"
        )

        self.run_assembler("apply", "--clients", "acme")

        self.assertNotEqual(private, machine)
        self.assert_link(self.canonical / "alpha", client)
        self.assert_link(self.claude / "alpha", self.canonical / "alpha")
        self.assertEqual(client / "SKILL.md", (self.claude / "alpha" / "SKILL.md").resolve())

    def test_collision_preflight_leaves_existing_installation_unchanged(self) -> None:
        self.run_assembler("apply")
        canonical_target = os.readlink(self.canonical / "alpha")
        (self.claude / "alpha").unlink()
        (self.claude / "alpha").mkdir()
        sentinel = self.claude / "alpha" / "sentinel"
        sentinel.write_text("keep", encoding="utf-8")

        result = self.run_assembler("apply", check=False)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Collision", result.stderr)
        self.assertEqual(canonical_target, os.readlink(self.canonical / "alpha"))
        self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))

    def test_symlinked_destination_root_is_rejected_without_traversal(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_text("keep", encoding="utf-8")
        self.canonical.parent.mkdir(parents=True)
        self.canonical.symlink_to(outside, target_is_directory=True)

        result = self.run_assembler("apply", check=False)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("is a symlink", result.stderr)
        self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))
        self.assertFalse(self.claude.exists())

    def test_clean_removes_dangling_managed_links_in_safe_order(self) -> None:
        self.run_assembler("apply")
        shutil.rmtree(self.shared / "skills" / "alpha")
        self.assertTrue((self.canonical / "alpha").is_symlink())
        self.assertTrue((self.claude / "alpha").is_symlink())

        self.run_assembler("clean")

        self.assertFalse((self.claude / "alpha").is_symlink())
        self.assertFalse((self.canonical / "alpha").is_symlink())
        self.assertFalse((self.agents / "reviewer.md").is_symlink())

    def test_apply_is_idempotent_and_clean_preserves_unmanaged_entries(self) -> None:
        self.canonical.mkdir(parents=True)
        personal = self.canonical / "personal"
        personal.mkdir()

        self.run_assembler("apply")
        self.run_assembler("apply")
        self.run_assembler("doctor")
        self.run_assembler("clean")

        self.assertTrue(personal.is_dir())
        self.assertEqual([personal], list(self.canonical.iterdir()))

    def test_third_party_symlinks_are_preserved(self) -> None:
        self.canonical.mkdir(parents=True)
        personal = self.canonical / "personal"
        personal.mkdir()
        bookmark = self.canonical / "bookmark"
        bookmark.symlink_to(personal, target_is_directory=True)

        self.run_assembler("apply")
        self.codex.mkdir(parents=True, exist_ok=True)
        codex_alias = self.codex / "personal-alpha"
        codex_alias.symlink_to(self.canonical / "alpha")
        self.run_assembler("clean")

        self.assertTrue(bookmark.is_symlink())
        self.assertEqual(str(personal), os.readlink(bookmark))
        self.assertTrue(codex_alias.is_symlink())
        self.assertEqual(str(self.canonical / "alpha"), os.readlink(codex_alias))

    def test_all_links_stage_before_existing_installation_is_replaced(self) -> None:
        self.run_assembler("apply")
        existing_target = os.readlink(self.canonical / "alpha")
        self.skill(self.shared / "skills", "beta", "new")
        self.claude.chmod(0o500)
        self.addCleanup(self.claude.chmod, 0o700)

        result = self.run_assembler("apply", check=False)

        self.assertNotEqual(0, result.returncode)
        self.assertEqual(existing_target, os.readlink(self.canonical / "alpha"))
        self.assertFalse((self.canonical / "beta").exists())
        self.assertFalse((self.canonical / "beta").is_symlink())

    def test_physical_root_alias_cannot_overlap_agents_root(self) -> None:
        home_alias = self.root / "home-alias"
        home_alias.symlink_to(self.home, target_is_directory=True)

        result = self.run_assembler(
            "apply",
            check=False,
            AGENTS_DIR=str(home_alias / ".agents" / "skills"),
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("AGENTS_DIR must differ", result.stderr)

    def test_destination_cannot_overlap_source_repository(self) -> None:
        destination = self.shared / "skills" / "installed"

        result = self.run_assembler(
            "apply", check=False, SKILLS_DIR=str(destination)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("overlaps a source repository", result.stderr)
        self.assertFalse(destination.exists())

    def test_codex_make_target_uses_shared_root_without_agents(self) -> None:
        self.run_make("apply-codex")

        self.assert_link(self.canonical / "alpha", self.shared / "skills" / "alpha")
        self.assert_link(self.claude / "alpha", self.canonical / "alpha")
        self.assertFalse(self.agents.exists())

    def test_clean_dry_run_is_read_only_and_clean_migrates_legacy_link(self) -> None:
        self.run_assembler("apply")
        self.codex.mkdir(parents=True, exist_ok=True)
        legacy = self.codex / "alpha"
        legacy.symlink_to(self.shared / "skills" / "alpha")

        self.run_assembler("clean", "--dry-run")
        self.assertTrue((self.canonical / "alpha").is_symlink())
        self.assertTrue((self.claude / "alpha").is_symlink())
        self.assertTrue(legacy.is_symlink())

        self.run_assembler("clean")
        self.assertFalse((self.canonical / "alpha").is_symlink())
        self.assertFalse((self.claude / "alpha").is_symlink())
        self.assertFalse(legacy.is_symlink())

    def test_dry_run_reports_migration_without_writing(self) -> None:
        result = self.run_assembler("apply", "--dry-run")

        self.assertIn("DRY: mkdir -p", result.stdout)
        self.assertIn(str(self.canonical), result.stdout)
        self.assertFalse((self.home / ".agents").exists())
        self.assertFalse((self.home / ".claude").exists())

    def test_doctor_reports_legacy_codex_links_and_pi_duplicate_setting(self) -> None:
        self.codex.mkdir(parents=True)
        (self.codex / "alpha").symlink_to(self.shared / "skills" / "alpha")
        settings = self.home / ".pi" / "agent" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(
            '{"skills":["' + str(self.claude) + '/"]}\n', encoding="utf-8"
        )

        result = self.run_assembler("doctor", check=False)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("legacy managed Codex link", result.stdout)
        self.assertIn("Pi settings still load", result.stdout)
        self.assertIn("Doctor: FAIL", result.stdout)

    def test_doctor_rejects_incorrect_claude_alias_target(self) -> None:
        self.run_assembler("apply")
        (self.claude / "alpha").unlink()
        (self.claude / "alpha").symlink_to(self.shared / "skills" / "alpha")

        result = self.run_assembler("doctor", check=False)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Incorrect link target", result.stdout)


if __name__ == "__main__":
    unittest.main()
