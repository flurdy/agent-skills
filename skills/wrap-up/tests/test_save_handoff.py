from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "save-handoff.py"
LIST_SCRIPT = SKILL_DIR.parent / "handoffs" / "scripts" / "list.sh"
CONTEXT_GATHER = os.environ.get("HANDOFF_CONTEXT_GATHER")


def resume_block(
    slug: str = "save-proof",
    date: str = "2026-09-13",
    time: str = "09:42",
    context: str = "The exact rendered handoff.",
    repo: Path | None = None,
) -> bytes:
    repo_line = f"**Repo root:** `{repo}`\n" if repo is not None else ""
    return (
        f"# Resume: {slug} — {date} {time}\n\n"
        f"**Where to pick up:** `{repo or '/tmp/project'}` on branch `main`\n"
        f"{repo_line}"
        "**Jira:** —\n"
        "**Beads:** `example-task`\n"
        "**Deliverable:** `example-task`\n"
        "**PRs:** —\n\n"
        "**Context:**\n"
        f"- {context}\n\n"
        "**Decisions so far:**\n"
        "- Save and verify in one operation.\n\n"
        "**Working-copy risks:**\n"
        "- None.\n\n"
        "**Open threads:**\n"
        "- Verify launcher discovery.\n\n"
        "**Suggested next step:**\n"
        "- Resume safely.\n"
    ).encode()


class SaveHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.home = self.root / "home"
        self.home.mkdir()
        specification = importlib.util.spec_from_file_location("save_handoff", SCRIPT)
        self.helper = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(self.helper)

    def run_save(
        self,
        content: bytes,
        *extra: str,
        date: str = "2026-09-13",
        time: str = "09:42",
        slug: str = "save-proof",
    ) -> tuple[subprocess.CompletedProcess[bytes], dict[str, object]]:
        self.assertTrue(SCRIPT.is_file(), f"missing deterministic save helper: {SCRIPT}")
        environment = os.environ.copy()
        environment["HOME"] = str(self.home)
        completed = subprocess.run(
            [str(SCRIPT), date, time, slug, *extra],
            input=content,
            capture_output=True,
            env=environment,
            check=False,
        )
        payload = json.loads(completed.stdout)
        return completed, payload

    @property
    def target(self) -> Path:
        return self.home / ".claude" / "handoffs" / "2026-09-13-save-proof.md"

    def test_new_save_writes_and_verifies_exact_regular_file(self) -> None:
        content = resume_block(context="Literal `code` and $(not-expanded).")
        completed, payload = self.run_save(content)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["schemaVersion"], "wrap-up-save/v1")
        self.assertEqual(payload["status"], "saved")
        self.assertEqual(payload["path"], str(self.target))
        self.assertEqual(payload["bytes"], len(content))
        self.assertEqual(payload["sha256"], hashlib.sha256(content).hexdigest())
        self.assertTrue(self.target.is_file())
        self.assertFalse(self.target.is_symlink())
        self.assertEqual(self.target.read_bytes(), content)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.target.parent.glob(".wrap-up-*")), [])

    def test_path_only_invocation_cannot_report_stale_file_as_saved(self) -> None:
        original = resume_block()
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(original)
        completed, payload = self.run_save(b"")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["status"], "failure")
        self.assertEqual(payload["reason"], "empty-input")
        self.assertNotIn("sha256", payload)
        self.assertEqual(self.target.read_bytes(), original)

    def test_rejects_empty_partial_wrong_header_and_oversized_input(self) -> None:
        cases = {
            "empty-input": b"",
            "header-mismatch": resume_block(slug="wrong"),
            "incomplete-block": "# Resume: save-proof — 2026-09-13 09:42\n\n**Context:**\n- partial\n".encode(),
            "input-too-large": resume_block() + b"x" * 65_536,
            "invalid-utf8": resume_block() + b"\xff",
            "nul-byte": resume_block() + b"\0",
        }
        for reason, content in cases.items():
            with self.subTest(reason=reason):
                completed, payload = self.run_save(content)
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(payload["status"], "failure")
                self.assertEqual(payload["reason"], reason)
                self.assertFalse(self.target.exists())
                self.assertNotIn("partial", completed.stdout.decode(errors="replace"))

    def test_rejects_empty_required_values_and_truncated_last_section(self) -> None:
        for removed in (
            b"- Resume safely.", b"- The exact rendered handoff.",
            b"`/tmp/project` on branch `main`", b"- Verify launcher discovery.",
        ):
            with self.subTest(removed=removed):
                completed, payload = self.run_save(resume_block().replace(removed, b""))
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(payload["reason"], "incomplete-block")
                self.assertFalse(self.target.exists())

    def test_rejects_invalid_date_time_and_slug_without_writing(self) -> None:
        cases = (
            {"date": "2026-02-30"},
            {"date": "../../etc"},
            {"time": "25:00"},
            {"slug": "../escape"},
            {"slug": "double--hyphen"},
            {"slug": "Uppercase"},
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                completed, payload = self.run_save(resume_block(), **arguments)
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(payload["status"], "failure")
                self.assertEqual(payload["reason"], "invalid-arguments")
        self.assertFalse((self.home / ".claude" / "handoffs").exists())

    def test_collision_preserves_existing_file_and_suggests_next_slug(self) -> None:
        original = resume_block(context="Original block.")
        first, _ = self.run_save(original)
        self.assertEqual(first.returncode, 0)

        replacement = resume_block(context="Replacement block.")
        completed, payload = self.run_save(replacement)

        self.assertEqual(completed.returncode, 3)
        self.assertEqual(payload["status"], "collision")
        self.assertEqual(payload["path"], str(self.target))
        self.assertEqual(payload["existingSha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(payload["suggestedSlug"], "save-proof-2")
        self.assertEqual(self.target.read_bytes(), original)

    def test_collision_rename_saves_distinct_verified_handoff(self) -> None:
        first, _ = self.run_save(resume_block())
        self.assertEqual(first.returncode, 0)
        renamed = resume_block(slug="save-proof-2")

        completed, payload = self.run_save(renamed, slug="save-proof-2")

        renamed_target = self.target.with_name("2026-09-13-save-proof-2.md")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["path"], str(renamed_target))
        self.assertEqual(renamed_target.read_bytes(), renamed)
        self.assertEqual(self.target.read_bytes(), resume_block())

    def test_symlink_and_non_regular_targets_are_refused(self) -> None:
        self.target.parent.mkdir(parents=True)
        outside = self.root / "outside"
        outside.write_text("leave unchanged", encoding="utf-8")
        self.target.symlink_to(outside)

        completed, payload = self.run_save(resume_block())
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["reason"], "target-symlink")
        self.assertEqual(outside.read_text(encoding="utf-8"), "leave unchanged")

        self.target.unlink()
        self.target.mkdir()
        completed, payload = self.run_save(resume_block())
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["reason"], "target-not-regular")

    def test_hash_bound_overwrite_replaces_only_approved_regular_file(self) -> None:
        original = resume_block(context="Original block.")
        first, first_payload = self.run_save(original)
        self.assertEqual(first.returncode, 0)
        original_inode = self.target.stat().st_ino
        replacement = resume_block(context="Approved replacement.")

        completed, payload = self.run_save(
            replacement,
            "--overwrite-sha256",
            str(first_payload["sha256"]),
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["status"], "saved")
        self.assertEqual(payload["mode"], "overwrite")
        self.assertNotEqual(self.target.stat().st_ino, original_inode)
        self.assertEqual(self.target.read_bytes(), replacement)

    def test_stale_hash_missing_target_and_symlink_overwrite_are_refused(self) -> None:
        original = resume_block(context="Original block.")
        first, first_payload = self.run_save(original)
        self.assertEqual(first.returncode, 0)
        stale_hash = "0" * 64
        replacement = resume_block(context="Replacement block.")

        completed, payload = self.run_save(
            replacement,
            "--overwrite-sha256",
            stale_hash,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["reason"], "overwrite-mismatch")
        self.assertEqual(self.target.read_bytes(), original)

        self.target.unlink()
        completed, payload = self.run_save(
            replacement,
            "--overwrite-sha256",
            str(first_payload["sha256"]),
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["reason"], "target-missing")

        outside = self.root / "outside"
        outside.write_text("leave unchanged", encoding="utf-8")
        self.target.symlink_to(outside)
        completed, payload = self.run_save(
            replacement,
            "--overwrite-sha256",
            str(first_payload["sha256"]),
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["reason"], "target-symlink")
        self.assertEqual(outside.read_text(encoding="utf-8"), "leave unchanged")

    def test_directory_creation_failure_is_bounded_and_does_not_echo_content(self) -> None:
        (self.home / ".claude").write_text("not a directory", encoding="utf-8")
        content = resume_block(context="PRIVATE-SENTINEL")

        completed, payload = self.run_save(content)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["reason"], "directory-unavailable")
        self.assertLessEqual(len(str(payload["detail"])), 200)
        self.assertNotIn("PRIVATE-SENTINEL", completed.stdout.decode())
        self.assertNotIn("PRIVATE-SENTINEL", completed.stderr.decode())

    def test_verification_failure_removes_new_file(self) -> None:
        module = self.helper
        with mock.patch.object(module, "verify_saved_file", side_effect=module.SaveFailure("verify-failed")):
            result = module.save_handoff(
                "2026-09-13",
                "09:42",
                "save-proof",
                resume_block(),
                self.home,
                None,
            )

        self.assertEqual(result.status, "failure")
        self.assertEqual(result.reason, "verify-failed")
        self.assertFalse(self.target.exists())

    def test_overwrite_verification_failure_restores_approved_file(self) -> None:
        original = resume_block(context="Original block.")
        first, first_payload = self.run_save(original)
        self.assertEqual(first.returncode, 0)
        module = self.helper
        with mock.patch.object(module, "verify_saved_file", side_effect=module.SaveFailure("verify-failed")):
            result = module.save_handoff(
                "2026-09-13",
                "09:42",
                "save-proof",
                resume_block(context="Replacement block."),
                self.home,
                str(first_payload["sha256"]),
            )

        self.assertEqual(result.status, "failure")
        self.assertEqual(result.reason, "verify-failed")
        self.assertEqual(self.target.read_bytes(), original)

    def test_io_or_sync_failure_keeps_original_recoverable(self) -> None:
        original = resume_block(context="Original block.")
        replacement = resume_block(context="Replacement block.")
        for stage in ("verify_saved_file", "sync_directory"):
            with self.subTest(stage=stage):
                home = self.home / stage
                first = self.helper.save_handoff("2026-09-13", "09:42", "save-proof", original, home, None)
                self.assertEqual(first.status, "saved")
                with mock.patch.object(self.helper, stage, side_effect=OSError("simulated I/O error")):
                    result = self.helper.save_handoff(
                        "2026-09-13", "09:42", "save-proof", replacement, home, first.digest,
                    )
                self.assertEqual(result.status, "failure")
                backup = result.payload().get("backupPath")
                recovery = Path(backup) if backup else first.path
                self.assertEqual(recovery.read_bytes(), original)

    def test_failed_rollback_retains_and_reports_backup(self) -> None:
        original = resume_block(context="Original block.")
        first = self.helper.save_handoff("2026-09-13", "09:42", "save-proof", original, self.home, None)
        replace = self.helper.os.replace

        def fail_restore(source, destination):
            if "backup" in Path(source).name:
                raise OSError("restore failed")
            return replace(source, destination)

        with (
            mock.patch.object(self.helper, "verify_saved_file", side_effect=OSError("verify failed")),
            mock.patch.object(self.helper.os, "replace", side_effect=fail_restore),
        ):
            result = self.helper.save_handoff(
                "2026-09-13", "09:42", "save-proof", resume_block(context="Replacement."), self.home, first.digest,
            )
        self.assertEqual(result.status, "failure")
        self.assertIn("backupPath", result.payload())
        self.assertEqual(Path(result.payload()["backupPath"]).read_bytes(), original)

    def test_concurrent_change_is_not_overwritten_during_rollback(self) -> None:
        original = resume_block(context="Original block.")
        first = self.helper.save_handoff("2026-09-13", "09:42", "save-proof", original, self.home, None)
        concurrent = resume_block(context="Concurrent edit must not be replaced.")

        def concurrent_edit(path, *_):
            path.write_bytes(concurrent)
            raise self.helper.SaveFailure("verify-failed")

        with mock.patch.object(self.helper, "verify_saved_file", side_effect=concurrent_edit):
            result = self.helper.save_handoff(
                "2026-09-13", "09:42", "save-proof", resume_block(context="Replacement."), self.home, first.digest,
            )
        self.assertEqual(result.status, "failure")
        self.assertEqual(first.path.read_bytes(), concurrent)
        self.assertIn("backupPath", result.payload())
        self.assertEqual(Path(result.payload()["backupPath"]).read_bytes(), original)

    def test_new_file_io_and_sync_failures_do_not_report_saved(self) -> None:
        for stage in ("verify_saved_file", "sync_directory"):
            with self.subTest(stage=stage):
                with mock.patch.object(self.helper, stage, side_effect=OSError("simulated failure")):
                    result = self.helper.save_handoff(
                        "2026-09-13", "09:42", stage.replace("_", "-"), resume_block(slug=stage.replace("_", "-")), self.home, None,
                    )
                self.assertEqual(result.status, "failure")
                self.assertFalse(result.path.exists())

    def test_real_verifier_rejects_wrong_bytes_identity_and_symlink(self) -> None:
        content = resume_block()
        completed, _ = self.run_save(content)
        self.assertEqual(completed.returncode, 0)
        identity = (self.target.stat().st_dev, self.target.stat().st_ino)
        self.helper.verify_saved_file(self.target, content, identity)
        for wrong in (content[:-1], content + b"extra", resume_block(context="Different content.")):
            with self.subTest(content=wrong[-20:]):
                with self.assertRaises(self.helper.SaveFailure):
                    self.helper.verify_saved_file(self.target, wrong, identity)
        with self.assertRaises(self.helper.SaveFailure):
            self.helper.verify_saved_file(self.target, content, (identity[0], identity[1] + 1))
        link = self.target.with_name("symlink.md")
        link.symlink_to(self.target)
        with self.assertRaises(self.helper.SaveFailure):
            self.helper.verify_saved_file(link, content, identity)

    def test_verifier_rechecks_the_path_after_reading(self) -> None:
        content = resume_block()
        completed, _ = self.run_save(content)
        self.assertEqual(completed.returncode, 0)
        identity = (self.target.stat().st_dev, self.target.stat().st_ino)
        read = self.helper.os.read

        def move_after_read(descriptor, size):
            chunk = read(descriptor, size)
            if self.target.exists():
                self.target.rename(self.target.with_suffix(".moved"))
            return chunk

        with mock.patch.object(self.helper.os, "read", side_effect=move_after_read):
            with self.assertRaises(self.helper.SaveFailure):
                self.helper.verify_saved_file(self.target, content, identity)

    def test_relative_home_is_refused_before_writing(self) -> None:
        completed = subprocess.run(
            [str(SCRIPT), "2026-09-13", "09:42", "save-proof"],
            input=resume_block(), capture_output=True, cwd=self.root,
            env={**os.environ, "HOME": "relative-home"}, check=False,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "failure")
        self.assertEqual(result["reason"], "home-unavailable")
        self.assertFalse((self.root / "relative-home").exists())

    def test_new_save_never_clobbers_target_created_after_inspection(self) -> None:
        link = self.helper.os.link
        concurrent = b"Concurrent fixture"

        def create_then_link(source, target, **kwargs):
            Path(target).write_bytes(concurrent)
            return link(source, target, **kwargs)

        with mock.patch.object(self.helper.os, "link", side_effect=create_then_link):
            result = self.helper.save_handoff("2026-09-13", "09:42", "save-proof", resume_block(), self.home, None)
        self.assertEqual(result.status, "failure")
        self.assertEqual(result.path.read_bytes(), concurrent)

    def create_repository(self) -> Path:
        repo = self.root / "repo"
        subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"], check=True, capture_output=True)
        return repo

    def test_saved_handoff_is_discoverable_by_handoff_inventory(self) -> None:
        repo = self.create_repository()
        content = resume_block(repo=repo)
        completed, _ = self.run_save(content)
        self.assertEqual(completed.returncode, 0)
        environment = os.environ.copy()
        environment["HOME"] = str(self.home)

        inventory = subprocess.run(
            [str(LIST_SCRIPT)],
            cwd=repo,
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        ).stdout

        self.assertIn("2026-09-13-save-proof.md|2026-09-13|save-proof|", inventory)
        self.assertIn("|09:42|", inventory)

    @unittest.skipUnless(CONTEXT_GATHER, "set HANDOFF_CONTEXT_GATHER for external launcher integration")
    def test_both_launchers_discover_only_after_verified_save(self) -> None:
        repo = self.create_repository()
        bin_directory = self.root / "bin"
        bin_directory.mkdir()
        gh = bin_directory / "gh"
        gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        gh.chmod(0o755)
        environment = {
            **os.environ, "HOME": str(self.home), "PATH": f"{bin_directory}:{os.environ['PATH']}",
            "XDG_CACHE_HOME": str(self.root / "cache"), "AI_HANDOFF_LIST": str(LIST_SCRIPT),
        }

        def handoff_rows(agent):
            completed = subprocess.run(
                [CONTEXT_GATHER, f"--agent={agent}", "--list"], cwd=repo,
                env=environment, text=True, capture_output=True, check=True, timeout=30,
            )
            return [row.split("\t") for row in completed.stdout.splitlines() if "\thandoff\t" in row]

        # Metadata alone never creates a launcher entry.
        failed, _ = self.run_save(b"")
        self.assertNotEqual(failed.returncode, 0)
        for agent in ("claude", "pi"):
            self.assertEqual(handoff_rows(agent), [])
        completed, _ = self.run_save(resume_block(repo=repo))
        self.assertEqual(completed.returncode, 0)
        for agent in ("claude", "pi"):
            with self.subTest(agent=agent):
                rows = handoff_rows(agent)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0][2], str(repo))
                self.assertEqual(rows[0][5], str(self.target))
                self.assertIn("2026-09-13 09:42", rows[0][0])


if __name__ == "__main__":
    unittest.main()
