#!/usr/bin/env python3
"""Contract tests for repository-qualified review-pr snapshots."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from time import monotonic
from typing import Any

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gh-pr-snapshot.py"
SPEC = importlib.util.spec_from_file_location("gh_pr_snapshot", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
SNAPSHOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SNAPSHOT)

HEAD_A = "a" * 40
HEAD_B = "b" * 40
BASE = "c" * 40
BASE_B = "d" * 40


def metadata(
    head: str = HEAD_A,
    *,
    changed_files: int = 1,
    checks_state: str = "SUCCESS",
    head_repository: str = "contributor/widgets",
) -> dict[str, Any]:
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "id": "PR_node",
                    "number": 42,
                    "url": "https://github.com/acme/widgets/pull/42",
                    "title": "ABC-123 improve widgets",
                    "body": "Implements the widget change.",
                    "state": "OPEN",
                    "isDraft": False,
                    "updatedAt": "2026-07-31T00:00:00Z",
                    "reviewDecision": "REVIEW_REQUIRED",
                    "author": {"login": "author"},
                    "additions": 12,
                    "deletions": 3,
                    "changedFiles": changed_files,
                    "baseRefName": "main",
                    "baseRefOid": BASE,
                    "headRefName": "feature/widgets",
                    "headRefOid": head,
                    "headRepository": {"nameWithOwner": head_repository},
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": head,
                                    "statusCheckRollup": {"state": checks_state},
                                }
                            }
                        ]
                    },
                }
            }
        }
    }


def final_metadata(
    head: str = HEAD_A,
    *,
    base: str = BASE,
    state: str = "OPEN",
    draft: bool = False,
    updated_at: str = "2026-07-31T00:00:00Z",
    review_decision: str = "REVIEW_REQUIRED",
    checks_state: str = "SUCCESS",
) -> dict[str, Any]:
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "id": "PR_node",
                    "state": state,
                    "isDraft": draft,
                    "updatedAt": updated_at,
                    "reviewDecision": review_decision,
                    "baseRefOid": base,
                    "headRefOid": head,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": head,
                                    "statusCheckRollup": {"state": checks_state},
                                }
                            }
                        ]
                    },
                }
            }
        }
    }


class FakeRunner:
    def __init__(
        self,
        *,
        initial: dict[str, Any] | Exception | None = None,
        final: dict[str, Any] | Exception | None = None,
        feedback: dict[str, Any] | Exception | None = None,
        files: list[dict[str, Any]] | Exception | None = None,
        repository: str = "acme/widgets",
        current_number: int = 42,
        git_repository: str | None = None,
        git_head: str = HEAD_A,
        git_dirty: bool = False,
    ) -> None:
        self.initial = initial if initial is not None else metadata()
        self.final = final if final is not None else final_metadata()
        self.feedback = feedback if feedback is not None else {
            "schemaVersion": 1,
            "repository": "acme/widgets",
            "pullRequests": [42],
            "partial": False,
            "errors": [],
            "records": [],
        }
        self.files = files if files is not None else [
            {
                "filename": "src/widget.ts",
                "status": "modified",
                "additions": 12,
                "deletions": 3,
                "changes": 15,
                "patch": "@@ -1 +1 @@\n-old\n+new",
            }
        ]
        self.repository = repository
        self.current_number = current_number
        self.git_repository = git_repository
        self.git_head = git_head
        self.git_dirty = git_dirty
        self.calls: list[tuple[list[str], Path | None]] = []
        self.graphql_calls = 0

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None,
        deadline: float,
        max_output_bytes: int,
        check: bool = True,
    ) -> str:
        del deadline, max_output_bytes
        self.calls.append((args, cwd))
        if args[:3] == ["gh", "repo", "view"]:
            return json.dumps({"nameWithOwner": self.repository})
        if args[:3] == ["gh", "pr", "view"]:
            return json.dumps(
                {
                    "number": self.current_number,
                    "url": f"https://github.com/{self.repository}/pull/{self.current_number}",
                }
            )
        if args[:3] == ["gh", "api", "graphql"]:
            self.graphql_calls += 1
            response = self.initial if self.graphql_calls == 1 else self.final
            if isinstance(response, Exception):
                raise response
            return json.dumps(response)
        if args[:2] == ["gh", "api"] and "/files?" in args[2]:
            if isinstance(self.files, Exception):
                raise self.files
            return json.dumps(self.files)
        if args and args[0].endswith("gh-pr-feedback.py"):
            if isinstance(self.feedback, Exception):
                raise self.feedback
            return json.dumps(self.feedback)
        if args[:2] == ["git", "-C"]:
            command = args[3:]
            if self.git_repository is None:
                if check:
                    raise SNAPSHOT.CommandError("not a Git checkout")
                return ""
            if command == ["rev-parse", "--show-toplevel"]:
                return f"{args[2]}\n"
            if command == ["remote", "get-url", "origin"]:
                return f"git@github.com:{self.git_repository}.git\n"
            if command == ["rev-parse", "HEAD"]:
                return f"{self.git_head}\n"
            if command == ["status", "--porcelain", "--untracked-files=all"]:
                return " M src/widget.ts\n" if self.git_dirty else ""
        raise AssertionError(f"unexpected command: {args}")

    def command_args(self) -> list[list[str]]:
        return [args for args, _ in self.calls]


class SnapshotContractTest(unittest.TestCase):
    def test_subprocess_runner_enforces_output_and_time_bounds(self) -> None:
        runner = SNAPSHOT.SubprocessRunner()
        with self.assertRaisesRegex(SNAPSHOT.CommandError, "output exceeded"):
            runner.run(
                [sys.executable, "-c", "print('x' * 2000)"],
                cwd=None,
                deadline=monotonic() + 2,
                max_output_bytes=1_000,
            )
        with self.assertRaisesRegex(SNAPSHOT.CommandError, "deadline exceeded"):
            runner.run(
                [sys.executable, "-c", "import time; time.sleep(1)"],
                cwd=None,
                deadline=monotonic() + 0.05,
                max_output_bytes=1_000,
            )

    def test_subprocess_runner_kills_descendants_after_parent_exit(self) -> None:
        runner = SNAPSHOT.SubprocessRunner()
        with tempfile.TemporaryDirectory() as temporary:
            pid_file = Path(temporary) / "child.pid"
            program = (
                "import subprocess,sys; "
                "child=subprocess.Popen([sys.executable,'-c',"
                "'import time; time.sleep(5)']); "
                f"open({str(pid_file)!r},'w').write(str(child.pid))"
            )
            with self.assertRaisesRegex(SNAPSHOT.CommandError, "deadline exceeded"):
                runner.run(
                    [sys.executable, "-c", program],
                    cwd=None,
                    deadline=monotonic() + 0.1,
                    max_output_bytes=1_000,
                )
            child_pid = int(pid_file.read_text(encoding="utf-8"))
            for _ in range(20):
                try:
                    os.kill(child_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.01)
            else:
                self.fail("descendant process survived the shared deadline")

    def test_qualified_target_ignores_wrong_cwd_and_qualifies_every_remote_call(self) -> None:
        runner = FakeRunner(repository="wrong/repository", git_repository="wrong/repository")

        result = SNAPSHOT.collect_snapshot(
            "acme/widgets#42",
            runner=runner,
            cwd=Path("/workspace/wrong"),
        )

        self.assertEqual("complete", result["status"])
        self.assertEqual("acme/widgets", result["target"]["repository"])
        self.assertEqual(HEAD_A, result["target"]["headSha"])
        self.assertFalse(result["checkout"]["available"])
        self.assertIn("repository mismatch", result["checkout"]["reason"])
        commands = runner.command_args()
        self.assertFalse(any(command[:3] == ["gh", "repo", "view"] for command in commands))
        self.assertFalse(any(command[:3] == ["gh", "pr", "view"] for command in commands))
        graphql = [command for command in commands if command[:3] == ["gh", "api", "graphql"]]
        self.assertEqual(2, len(graphql))
        for command in graphql:
            self.assertIn("owner=acme", command)
            self.assertIn("repo=widgets", command)
        self.assertTrue(
            any(
                command[0].endswith("gh-pr-feedback.py")
                and command[1:4] == ["acme", "widgets", "42"]
                for command in commands
            )
        )
        self.assertTrue(
            any(
                command[:2] == ["gh", "api"]
                and command[2].startswith("repos/acme/widgets/pulls/42/files?")
                for command in commands
            )
        )

    def test_numeric_and_current_branch_shorthand_resolve_from_cwd_once(self) -> None:
        for selector, expected_pr_lookup, expected_repo_lookup in (
            ("42", False, 1),
            (None, True, 0),
        ):
            with self.subTest(selector=selector):
                runner = FakeRunner(git_repository="acme/widgets")

                result = SNAPSHOT.collect_snapshot(
                    selector,
                    runner=runner,
                    cwd=Path("/checkout"),
                    checkout=Path("/checkout"),
                )

                self.assertEqual("complete", result["status"])
                self.assertTrue(result["checkout"]["available"])
                commands = runner.command_args()
                self.assertEqual(
                    expected_pr_lookup,
                    any(command[:3] == ["gh", "pr", "view"] for command in commands),
                )
                self.assertEqual(
                    expected_repo_lookup,
                    sum(command[:3] == ["gh", "repo", "view"] for command in commands),
                )

    def test_missing_or_dirty_checkout_never_blocks_remote_evidence(self) -> None:
        for runner, reason in (
            (FakeRunner(git_repository=None), "not a Git checkout"),
            (
                FakeRunner(git_repository="acme/widgets", git_dirty=True),
                "working tree is not clean",
            ),
            (FakeRunner(git_repository="acme/widgets", git_head=HEAD_B), "HEAD does not match"),
        ):
            with self.subTest(reason=reason):
                result = SNAPSHOT.collect_snapshot(
                    "acme/widgets#42",
                    runner=runner,
                    cwd=Path("/workspace"),
                    checkout=Path("/candidate"),
                )

                self.assertEqual("complete", result["status"])
                self.assertFalse(result["checkout"]["available"])
                self.assertIn(reason, result["checkout"]["reason"])
                self.assertEqual(1, len(result["evidence"]["files"]))

    @unittest.skipUnless(shutil.which("git"), "Git is required for checkout tests")
    def test_checkout_verification_forces_untracked_file_reporting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            subprocess.run(
                ["git", "init", "-b", "main"],
                cwd=repository,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repository,
                check=True,
            )
            (repository / "tracked.txt").write_text("tracked\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "commit", "-m", "initial"],
                cwd=repository,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "remote", "add", "origin", "git@github.com:acme/widgets.git"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "status.showUntrackedFiles", "no"],
                cwd=repository,
                check=True,
            )
            (repository / "untracked.txt").write_text("untracked\n", encoding="utf-8")
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            result = SNAPSHOT.verify_checkout(
                repository,
                {
                    "repository": "acme/widgets",
                    "owner": "acme",
                    "repo": "widgets",
                    "headRepository": "contributor/widgets",
                },
                head,
                runner=SNAPSHOT.SubprocessRunner(),
                cwd=repository,
                deadline=monotonic() + 5,
                max_output_bytes=10_000,
            )

        self.assertFalse(result["available"])
        self.assertIn("working tree is not clean", result["reason"])

    def test_exact_head_checkout_from_a_fork_is_accepted(self) -> None:
        result = SNAPSHOT.collect_snapshot(
            "acme/widgets#42",
            runner=FakeRunner(git_repository="contributor/widgets"),
            cwd=Path("/fork-checkout"),
            checkout=Path("/fork-checkout"),
        )

        self.assertEqual("complete", result["status"])
        self.assertTrue(result["checkout"]["available"])

    def test_head_change_returns_stale_and_suppresses_review_readiness(self) -> None:
        runner = FakeRunner(final=final_metadata(HEAD_B))

        result = SNAPSHOT.collect_snapshot(
            "https://github.com/acme/widgets/pull/42",
            runner=runner,
            cwd=Path("/workspace"),
            expected_head=HEAD_A,
        )

        self.assertEqual("stale", result["status"])
        self.assertFalse(result["reviewReady"])
        self.assertEqual(HEAD_A, result["snapshot"]["initialHeadSha"])
        self.assertEqual(HEAD_B, result["snapshot"]["finalHeadSha"])

    def test_mutable_pr_and_ci_races_return_stale(self) -> None:
        races = {
            "base": final_metadata(base=BASE_B),
            "state": final_metadata(state="CLOSED"),
            "draft": final_metadata(draft=True),
            "updated": final_metadata(updated_at="2026-07-31T00:01:00Z"),
            "review": final_metadata(review_decision="CHANGES_REQUESTED"),
            "checks": final_metadata(checks_state="FAILURE"),
        }
        for name, final in races.items():
            with self.subTest(name=name):
                result = SNAPSHOT.collect_snapshot(
                    "acme/widgets#42",
                    runner=FakeRunner(final=final),
                    cwd=Path("/workspace"),
                )
                self.assertEqual("stale", result["status"])
                self.assertFalse(result["reviewReady"])

    def test_expected_head_mismatch_stops_before_collecting_evidence(self) -> None:
        runner = FakeRunner()

        result = SNAPSHOT.collect_snapshot(
            "acme/widgets#42",
            runner=runner,
            cwd=Path("/workspace"),
            expected_head=HEAD_B,
        )

        self.assertEqual("stale", result["status"])
        self.assertFalse(result["reviewReady"])
        self.assertEqual(1, runner.graphql_calls)
        self.assertEqual([], result["evidence"]["files"])

    def test_verify_only_rechecks_revisions_and_mutable_review_state(self) -> None:
        initial = SNAPSHOT.collect_snapshot(
            "acme/widgets#42",
            runner=FakeRunner(),
            cwd=Path("/workspace"),
        )
        state_key = initial["snapshot"]["stateKey"]
        runner = FakeRunner()

        result = SNAPSHOT.collect_snapshot(
            "acme/widgets#42",
            runner=runner,
            cwd=Path("/workspace"),
            expected_head=HEAD_A,
            expected_base=BASE,
            expected_state_key=state_key,
            verify_only=True,
        )

        self.assertEqual("complete", result["status"])
        self.assertFalse(result["reviewReady"])
        self.assertEqual(2, runner.graphql_calls)
        self.assertEqual([], result["evidence"]["files"])
        self.assertIsNotNone(result["evidence"]["feedback"])

    def test_verify_only_detects_same_sha_feedback_and_ci_changes(self) -> None:
        initial = SNAPSHOT.collect_snapshot(
            "acme/widgets#42",
            runner=FakeRunner(),
            cwd=Path("/workspace"),
        )
        state_key = initial["snapshot"]["stateKey"]
        changed_feedback = {
            "schemaVersion": 1,
            "repository": "acme/widgets",
            "pullRequests": [42],
            "partial": False,
            "errors": [],
            "records": [
                {
                    "identity": "conversation:C1",
                    "updateKey": "new",
                    "stateKey": "active",
                    "source": "conversation",
                    "lifecycle": "active",
                }
            ],
        }
        scenarios = {
            "feedback": FakeRunner(feedback=changed_feedback),
            "checks": FakeRunner(
                initial=metadata(checks_state="FAILURE"),
                final=final_metadata(checks_state="FAILURE"),
            ),
        }
        for name, runner in scenarios.items():
            with self.subTest(name=name):
                result = SNAPSHOT.collect_snapshot(
                    "acme/widgets#42",
                    runner=runner,
                    cwd=Path("/workspace"),
                    expected_head=HEAD_A,
                    expected_base=BASE,
                    expected_state_key=state_key,
                    verify_only=True,
                )
                self.assertEqual("stale", result["status"])
                self.assertFalse(result["reviewReady"])

    def test_final_api_failure_suppresses_the_verdict(self) -> None:
        result = SNAPSHOT.collect_snapshot(
            "acme/widgets#42",
            runner=FakeRunner(final=SNAPSHOT.CommandError("final check unavailable")),
            cwd=Path("/workspace"),
        )

        self.assertEqual("failed", result["status"])
        self.assertFalse(result["reviewReady"])
        self.assertEqual("final-head", result["errors"][-1]["source"])

    def test_api_failure_is_machine_readable(self) -> None:
        runner = FakeRunner(initial=SNAPSHOT.CommandError("GitHub unavailable"))

        result = SNAPSHOT.collect_snapshot(
            "acme/widgets#42",
            runner=runner,
            cwd=Path("/workspace"),
        )

        self.assertEqual("failed", result["status"])
        self.assertFalse(result["reviewReady"])
        self.assertEqual("metadata", result["errors"][0]["source"])
        self.assertIn("GitHub unavailable", result["errors"][0]["message"])

    def test_missing_patches_and_truncated_feedback_are_partial(self) -> None:
        feedback = {
            "schemaVersion": 1,
            "repository": "acme/widgets",
            "pullRequests": [42],
            "partial": False,
            "errors": [],
            "records": [
                {
                    "identity": "inline:C1",
                    "updateKey": "update",
                    "stateKey": "state",
                    "source": "inline_review",
                    "lifecycle": "active",
                    "bodyTruncated": True,
                }
            ],
        }
        files = [
            {
                "filename": "assets/widget.png",
                "status": "modified",
                "additions": 0,
                "deletions": 0,
                "changes": 1,
            }
        ]

        result = SNAPSHOT.collect_snapshot(
            "acme/widgets#42",
            runner=FakeRunner(feedback=feedback, files=files),
            cwd=Path("/workspace"),
        )

        self.assertEqual("partial", result["status"])
        self.assertFalse(result["reviewReady"])
        self.assertTrue(result["evidence"]["files"][0]["patchUnavailable"])
        kinds = {(error["source"], error["kind"]) for error in result["errors"]}
        self.assertIn(("files", "unavailable"), kinds)
        self.assertIn(("feedback", "truncated"), kinds)

    def test_partial_feedback_and_file_caps_are_explicit(self) -> None:
        feedback = {
            "schemaVersion": 1,
            "repository": "acme/widgets",
            "pullRequests": [42],
            "partial": True,
            "errors": [{"source": "reviewThreads", "message": "truncated"}],
            "records": [],
        }
        runner = FakeRunner(initial=metadata(changed_files=101), feedback=feedback)

        result = SNAPSHOT.collect_snapshot(
            "acme/widgets#42",
            runner=runner,
            cwd=Path("/workspace"),
            max_files=100,
        )

        self.assertEqual("partial", result["status"])
        self.assertFalse(result["reviewReady"])
        self.assertTrue(any(error["source"] == "files" for error in result["errors"]))
        self.assertTrue(any(error["source"] == "feedback" for error in result["errors"]))
        self.assertEqual(100, result["limits"]["files"])


if __name__ == "__main__":
    unittest.main()
