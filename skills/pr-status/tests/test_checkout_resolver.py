from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "scripts" / "gh-pr-checkout.py"
SPEC = importlib.util.spec_from_file_location("gh_pr_checkout", SCRIPT)
assert SPEC and SPEC.loader
CHECKOUT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKOUT)


def git(path: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


class CheckoutResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "widgets"
        self.root.mkdir()
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "Test")
        git(self.root, "config", "user.email", "test@example.com")
        git(self.root, "remote", "add", "origin", "git@github.com:acme/widgets.git")
        (self.root / "README.md").write_text("one\n")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-qm", "initial")
        self.head = git(self.root, "rev-parse", "HEAD")

    def resolve(self, **overrides: Any) -> dict[str, Any]:
        arguments = {
            "repository": "acme/widgets",
            "head_sha": self.head,
            "candidate_paths": [str(self.root)],
            "timeout": 10.0,
        }
        arguments.update(overrides)
        return CHECKOUT.resolve_checkout(**arguments)

    def test_remote_parser_requires_the_exact_github_host(self) -> None:
        accepted = {
            "git@github.com:acme/widgets.git",
            "https://github.com/acme/widgets.git",
            "ssh://git@github.com/acme/widgets.git",
            "github.com/acme/widgets",
        }
        rejected = {
            "git@notgithub.com:acme/widgets.git",
            "https://evil.example/github.com/acme/widgets.git",
            "https://github.com.evil.example/acme/widgets.git",
            "https://github.com/acme/widgets/extra",
        }

        self.assertEqual(
            {"acme/widgets"},
            {CHECKOUT.github_repository(remote) for remote in accepted},
        )
        self.assertEqual(
            {None},
            {CHECKOUT.github_repository(remote) for remote in rejected},
        )

    def test_output_limit_terminates_the_process_group(self) -> None:
        marker = Path(self.temporary.name) / "output-child-survived"
        program = (
            "import pathlib,subprocess,sys,time; "
            f"subprocess.Popen([sys.executable,'-c',\"import pathlib,signal,time; "
            f"signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(0.8); "
            f"pathlib.Path({str(marker)!r}).write_text('alive')\"]); "
            "time.sleep(0.1); print('x' * 2000, flush=True); time.sleep(5)"
        )
        runner = CHECKOUT.CommandRunner(timeout=5.0, max_output_bytes=1_000)

        with self.assertRaisesRegex(RuntimeError, "output exceeded"):
            runner.run([sys.executable, "-c", program])
        time.sleep(1.0)

        self.assertFalse(marker.exists())

    def test_deadline_terminates_the_process_group(self) -> None:
        marker = Path(self.temporary.name) / "deadline-child-survived"
        program = (
            "import pathlib,subprocess,sys,time; "
            f"subprocess.Popen([sys.executable,'-c',\"import pathlib,signal,time; "
            f"signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(0.8); "
            f"pathlib.Path({str(marker)!r}).write_text('alive')\"]); "
            "time.sleep(5)"
        )
        runner = CHECKOUT.CommandRunner(timeout=0.2)

        with self.assertRaisesRegex(TimeoutError, "deadline exceeded"):
            runner.run([sys.executable, "-c", program])
        time.sleep(1.0)

        self.assertFalse(marker.exists())

    def test_resolves_clean_exact_head_checkout(self) -> None:
        result = self.resolve()

        self.assertEqual("verified", result["status"])
        self.assertTrue(result["checkout"]["available"])
        self.assertEqual(str(self.root.resolve()), result["checkout"]["path"])
        self.assertEqual(self.head, result["checkout"]["headSha"])
        self.assertEqual([], result["errors"])

    def test_resolves_repository_scope_from_registered_candidates(self) -> None:
        result = CHECKOUT.resolve_repository_scope(
            candidate_paths=[str(self.root)],
            timeout=10.0,
        )

        self.assertEqual("verified", result["status"])
        self.assertEqual(["acme/widgets"], result["repositories"])
        self.assertEqual([], result["errors"])

    def test_repository_scope_fails_closed_without_github_remotes(self) -> None:
        git(
            self.root,
            "remote",
            "set-url",
            "origin",
            "https://example.com/acme/widgets.git",
        )

        result = CHECKOUT.resolve_repository_scope(
            candidate_paths=[str(self.root)],
            timeout=10.0,
        )

        self.assertEqual("unavailable", result["status"])
        self.assertEqual([], result["repositories"])

    def test_repository_scope_is_partial_when_a_candidate_times_out(self) -> None:
        with mock.patch.object(
            CHECKOUT,
            "inspect_repository",
            side_effect=[
                ("acme/widgets", []),
                (None, [{"source": "remote", "message": "deadline exceeded"}]),
            ],
        ):
            result = CHECKOUT.resolve_repository_scope(
                candidate_paths=[str(self.root), str(self.root) + "-other"],
                timeout=10.0,
            )

        self.assertEqual("partial", result["status"])
        self.assertEqual(["acme/widgets"], result["repositories"])

    def test_repository_scope_reports_candidate_overflow_as_partial(self) -> None:
        with mock.patch.object(CHECKOUT, "MAX_CANDIDATES", 1):
            result = CHECKOUT.resolve_repository_scope(
                candidate_paths=[str(self.root), str(self.root) + "-other"],
                timeout=10.0,
            )

        self.assertEqual("partial", result["status"])
        self.assertEqual(["acme/widgets"], result["repositories"])
        self.assertEqual("scope-candidates", result["errors"][0]["source"])

    def test_rejects_wrong_repository_and_wrong_head(self) -> None:
        wrong_repository = self.resolve(repository="other/widgets")
        wrong_head = self.resolve(head_sha="f" * 40)

        self.assertEqual("repository-not-found", wrong_repository["checkout"]["reason"])
        self.assertEqual("head-not-found", wrong_head["checkout"]["reason"])

    def test_forces_untracked_file_detection(self) -> None:
        git(self.root, "config", "status.showUntrackedFiles", "no")
        (self.root / "UNTRACKED.txt").write_text("dirty\n")

        result = self.resolve()

        self.assertEqual("unavailable", result["status"])
        self.assertEqual("checkout-dirty", result["checkout"]["reason"])

    def test_finds_registered_alternate_worktree_at_exact_head(self) -> None:
        (self.root / "README.md").write_text("two\n")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-qm", "second")
        second_head = git(self.root, "rev-parse", "HEAD")
        worktree = Path(self.temporary.name) / "review-worktree"
        git(self.root, "worktree", "add", "-q", "--detach", str(worktree), self.head)
        self.addCleanup(
            lambda: subprocess.run(
                ["git", "-C", str(self.root), "worktree", "remove", "--force", str(worktree)],
                check=False,
                capture_output=True,
            )
        )

        result = self.resolve(head_sha=self.head)

        self.assertNotEqual(self.head, second_head)
        self.assertEqual("verified", result["status"])
        self.assertEqual(str(worktree.resolve()), result["checkout"]["path"])

    def test_candidate_failures_do_not_hide_a_verified_checkout(self) -> None:
        missing = Path(self.temporary.name) / "missing"

        result = self.resolve(candidate_paths=[str(missing), str(self.root)])

        self.assertEqual("verified", result["status"])
        self.assertTrue(result["checkout"]["available"])
        self.assertEqual(1, len(result["errors"]))

    def test_discovery_uses_only_the_named_members_script(self) -> None:
        runner = mock.Mock()
        runner.run.side_effect = [
            subprocess.CompletedProcess([], 0, stdout=str(self.root) + "\n", stderr=""),
            subprocess.CompletedProcess(
                [],
                0,
                stdout=(
                    "---MARKER---\nmgit\n---ROOT---\n"
                    + str(Path(self.temporary.name))
                    + "\n---REPOS---\nwidgets\n"
                ),
                stderr="",
            ),
        ]

        paths, errors = CHECKOUT.discover_candidate_paths(runner, Path(self.temporary.name))

        self.assertIn(str(self.root.resolve()), paths)
        self.assertEqual([], errors)
        members_call = runner.run.call_args_list[1].args[0]
        self.assertEqual("--members-only", members_call[-1])

    def test_cli_emits_one_json_object(self) -> None:
        completed = subprocess.run(
            [str(SCRIPT), "acme/widgets", self.head],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )

        result = json.loads(completed.stdout)
        self.assertEqual("gh-pr-checkout/v1", result["schemaVersion"])
        self.assertEqual("verified", result["status"])
        self.assertEqual("", completed.stderr)

    def test_scope_cli_emits_registered_github_repositories(self) -> None:
        completed = subprocess.run(
            [str(SCRIPT), "--scope"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )

        result = json.loads(completed.stdout)
        self.assertEqual("gh-pr-checkout/v1", result["schemaVersion"])
        self.assertEqual("verified", result["status"])
        self.assertEqual(["acme/widgets"], result["repositories"])

    def test_cli_has_no_candidate_or_output_limit_escape_hatches(self) -> None:
        help_text = subprocess.run(
            [str(SCRIPT), "--help"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

        self.assertNotIn("--candidate", help_text)
        self.assertNotIn("--max-output-bytes", help_text)


if __name__ == "__main__":
    unittest.main()
