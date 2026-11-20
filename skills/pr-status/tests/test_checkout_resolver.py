from __future__ import annotations

import importlib.util
import json
import os
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
github_repository = sys.modules["github_remote"].github_repository
ENTERPRISE = "ghe.example.com"


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
        environment = mock.patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("GH_HOST", None)
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

    def test_remote_parser_accepts_only_github_and_supported_ssh_aliases(self) -> None:
        accepted = {
            "git@github.com:acme/widgets.git",
            "git@work.github.com:acme/widgets.git",
            "git@corp.github.com:acme/widgets.git",
            "ssh://git@corp.github.com/acme/widgets.git",
            "https://github.com/acme/widgets.git",
            "ssh://git@github.com/acme/widgets.git",
            "ssh://git@work.github.com/acme/widgets.git",
            "github.com/acme/widgets",
        }
        rejected = {
            "git@nested.work.github.com:acme/widgets.git",
            "git@notgithub.com:acme/widgets.git",
            "https://evil.example/github.com/acme/widgets.git",
            "https://github.com.evil.example/acme/widgets.git",
            "https://github.com/acme/widgets/extra",
            "https://work.github.com/acme/widgets.git",
            "http://corp.github.com/acme/widgets.git",
            "git@github-work:acme/widgets.git",
            "git@github.com.evil.example:acme/widgets.git",
            "ftp://github.com/acme/widgets.git",
        }

        self.assertEqual(
            {"acme/widgets"},
            {github_repository(remote) for remote in accepted},
        )
        self.assertEqual(
            {None},
            {github_repository(remote) for remote in rejected},
        )

    def test_remote_parser_rejects_malformed_urls(self) -> None:
        self.assertIsNone(github_repository("https://[invalid/acme/widgets.git"))

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

    def test_enterprise_checkout_matches_only_its_known_host(self) -> None:
        git(self.root, "remote", "set-url", "origin", f"git@{ENTERPRISE}:acme/widgets.git")

        enterprise = self.resolve(host=ENTERPRISE, hosts=frozenset({ENTERPRISE}))
        default_host = self.resolve(hosts=frozenset({ENTERPRISE}))

        self.assertEqual("verified", enterprise["status"])
        self.assertEqual(ENTERPRISE, enterprise["target"]["host"])
        self.assertEqual("repository-not-found", default_host["checkout"]["reason"])
        with self.assertRaisesRegex(ValueError, "not a known GitHub host"):
            self.resolve(host=ENTERPRISE, hosts=frozenset())

    def test_known_gh_host_becomes_the_default_host(self) -> None:
        git(self.root, "remote", "set-url", "origin", f"git@{ENTERPRISE}:acme/widgets.git")
        hosts = frozenset({ENTERPRISE})

        os.environ["GH_HOST"] = ENTERPRISE
        known = self.resolve(hosts=hosts)
        os.environ["GH_HOST"] = "unknown.example.com"
        unknown = self.resolve(hosts=hosts)

        self.assertEqual((ENTERPRISE, "verified"), (known["target"]["host"], known["status"]))
        self.assertEqual("github.com", unknown["target"]["host"])
        self.assertEqual("repository-not-found", unknown["checkout"]["reason"])

    def test_repository_scope_lists_only_the_requested_host(self) -> None:
        git(self.root, "remote", "set-url", "origin", f"https://{ENTERPRISE}/acme/widgets.git")
        hosts = frozenset({ENTERPRISE})

        enterprise = CHECKOUT.resolve_repository_scope(
            candidate_paths=[str(self.root)], timeout=10.0, host=ENTERPRISE, hosts=hosts
        )
        default_host = CHECKOUT.resolve_repository_scope(
            candidate_paths=[str(self.root)], timeout=10.0, hosts=hosts
        )

        self.assertEqual((ENTERPRISE, ["acme/widgets"]), (enterprise["host"], enterprise["repositories"]))
        self.assertEqual(("github.com", []), (default_host["host"], default_host["repositories"]))

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

    def test_cli_host_uses_the_gh_hosts_file(self) -> None:
        git(self.root, "remote", "set-url", "origin", f"git@{ENTERPRISE}:acme/widgets.git")
        config = Path(self.temporary.name) / "gh"
        config.mkdir()
        (config / "hosts.yml").write_text(f"{ENTERPRISE}:\n    git_protocol: ssh\n")

        def run(env_dir: Path) -> dict[str, Any]:
            completed = subprocess.run(
                [str(SCRIPT), "acme/widgets", self.head, "--host", ENTERPRISE],
                cwd=self.root,
                capture_output=True,
                text=True,
                env={**os.environ, "GH_CONFIG_DIR": str(env_dir)},
            )
            return json.loads(completed.stdout)

        self.assertEqual("verified", run(config)["status"])
        unknown = run(Path(self.temporary.name) / "absent")
        self.assertEqual("failed", unknown["status"])
        self.assertIn("not a known GitHub host", unknown["errors"][0]["message"])

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
