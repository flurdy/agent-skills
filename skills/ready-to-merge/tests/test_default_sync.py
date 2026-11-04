"""Offline Git fixtures: the planner reads; only this fixture executes previews."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "default-sync.py"
MGIT = Path(__file__).resolve().parents[2] / "setup-multirepo-git" / "scripts" / "mgit"
spec = importlib.util.spec_from_file_location("default_sync", SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class DefaultSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
                    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com"}
        self.env_patch = patch.dict(os.environ, self.env)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.remote, self.dev, self.other = [self.root / x for x in ("remote.git", "dev", "other")]
        self.git(self.root, "init", "--bare", "-q", "--initial-branch=main", str(self.remote))
        self.git(self.root, "clone", "-q", str(self.remote), str(self.dev))
        self.base = self.commit(self.dev, "base")
        self.git(self.dev, "push", "-qu", "origin", "main")
        self.git(self.root, "clone", "-q", str(self.remote), str(self.other))
        self.merged = self.commit(self.other, "merged")
        self.git(self.other, "push", "-q", "origin", "main")
        self.args = sync.parser().parse_args([
            "inspect", "--repo", str(self.dev), "--github", "example/project",
            "--default", "main", "--merge-commit", self.merged,
        ])
        # No production local-remote escape hatch: identity alone is stubbed for offline fixtures.
        self.identity = patch.object(sync, "github_identity", return_value="example/project")
        self.identity.start()
        self.addCleanup(self.identity.stop)

    def git(self, cwd, *args, check=True):
        return subprocess.run(["git", "-C", str(cwd), *args], env=self.env,
                              capture_output=True, text=True, check=check)

    def commit(self, repo, name):
        (repo / name).write_text(name)
        self.git(repo, "add", name)
        self.git(repo, "commit", "-qm", name)
        return self.git(repo, "rev-parse", "HEAD").stdout.strip()

    def inspect(self):
        return sync.inspect(sync.Git(self.args), self.args)

    def plan(self):
        before = self.inspect()
        self.execute(before["fetch_command"])
        return sync.plan(sync.Git(self.args), self.args, before)

    def execute(self, argv, check=True):
        return subprocess.run(argv, cwd=self.root, env=self.env, capture_output=True,
                              text=True, check=check)

    def test_checked_out_main_and_autostash_settings(self):
        self.git(self.dev, "config", "pull.rebase", "true")
        self.git(self.dev, "config", "merge.autoStash", "true")
        plan = self.plan()
        self.assertEqual("ff-worktree", plan["status"])
        self.assertIn("--no-autostash", plan["command"])
        self.assertIn("--ff-only", plan["command"])
        self.assertEqual(self.merged, plan["command"][-1])
        sync.check(sync.Git(self.args), self.args, plan)
        self.execute(plan["command"])
        self.assertEqual(self.merged, self.git(self.dev, "rev-parse", "HEAD").stdout.strip())
        self.assertEqual("main", self.git(self.dev, "branch", "--show-current").stdout.strip())
        self.assertEqual("noop", self.plan()["status"])

    def test_other_worktree_and_mgit(self):
        wt = self.root / "default worktree"
        self.git(self.dev, "switch", "-qc", "feature")
        self.git(self.dev, "worktree", "add", "-q", str(wt), "main")
        self.args.mgit, self.args.service = str(MGIT), str(self.dev)
        plan = self.plan()
        self.assertEqual([str(MGIT), "merge", str(wt)], plan["command"][:3])
        self.execute(plan["command"])
        self.assertEqual(self.merged, self.git(wt, "rev-parse", "HEAD").stdout.strip())
        self.assertEqual(self.base, self.git(self.dev, "rev-parse", "HEAD").stdout.strip())
        self.assertEqual("feature", self.git(self.dev, "branch", "--show-current").stdout.strip())

    def test_unchecked_ref_pins_oid_and_git_rejects_late_checkout(self):
        self.git(self.dev, "switch", "-qc", "feature")
        plan = self.plan()
        self.assertEqual("ff-ref", plan["status"])
        self.assertEqual(f"{self.merged}:refs/heads/main", plan["command"][-1])
        wt = self.root / "late"
        self.git(self.dev, "worktree", "add", "-q", str(wt), "main")
        with self.assertRaises(sync.Skip):
            sync.check(sync.Git(self.args), self.args, plan)
        result = self.execute(plan["command"], check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(self.base, self.git(wt, "rev-parse", "HEAD").stdout.strip())

    def test_unchecked_ref_fast_forward_and_divergence_race(self):
        self.git(self.dev, "switch", "-qc", "feature")
        plan = self.plan()
        self.execute(plan["command"])
        self.assertEqual(self.merged, self.git(self.dev, "rev-parse", "main").stdout.strip())
        self.assertEqual(self.base, self.git(self.dev, "rev-parse", "HEAD").stdout.strip())
        local = self.commit(self.dev, "local")
        self.git(self.dev, "update-ref", "refs/heads/main", local)
        self.assertNotEqual(0, self.execute(plan["command"], check=False).returncode)
        self.assertEqual(local, self.git(self.dev, "rev-parse", "main").stdout.strip())

    def test_dirty_index_untracked_operation_lock_and_shallow_skip(self):
        for mode in ("untracked", "index", "operation", "lock", "shallow"):
            with self.subTest(mode=mode):
                if mode in ("untracked", "index"):
                    p = self.dev / "dirty"
                    p.write_text("x")
                    if mode == "index":
                        self.git(self.dev, "add", "dirty")
                else:
                    p = self.dev / ".git" / {"operation": "MERGE_HEAD", "lock": "index.lock", "shallow": "shallow"}[mode]
                    p.write_text(self.base + "\n")
                with self.assertRaises(sync.Skip):
                    self.inspect()
                if mode == "index":
                    self.git(self.dev, "rm", "--cached", "dirty")
                p.unlink()

    def test_ahead_diverged_and_merge_not_contained(self):
        self.commit(self.dev, "local")
        with self.assertRaisesRegex(sync.Skip, "diverged"):
            self.plan()
        self.args.merge_commit = self.base
        self.git(self.dev, "update-ref", "refs/remotes/origin/main", self.base)
        before = self.inspect()
        with self.assertRaisesRegex(sync.Skip, "ahead"):
            sync.plan(sync.Git(self.args), self.args, before)
        self.args.merge_commit = self.merged
        before = self.inspect()
        with self.assertRaisesRegex(sync.Skip, "merge commit"):
            sync.plan(sync.Git(self.args), self.args, before)

    def test_newer_tip_and_changed_plan(self):
        tip = self.commit(self.other, "later")
        self.git(self.other, "push", "-q", "origin", "main")
        plan = self.plan()
        self.assertEqual(tip, plan["target"])
        self.assertEqual(1, plan["extra_commits"])
        (self.dev / "changed").write_text("x")
        with self.assertRaises(sync.Skip):
            sync.check(sync.Git(self.args), self.args, plan)

    def test_missing_ambiguous_upstream_and_multiple_worktrees(self):
        self.git(self.dev, "config", "--add", "branch.main.merge", "refs/heads/other")
        with self.assertRaises(sync.Skip):
            self.inspect()
        self.git(self.dev, "config", "--replace-all", "branch.main.merge", "refs/heads/main")
        self.git(self.dev, "worktree", "add", "--force", "-q", str(self.root / "duplicate"), "main")
        with self.assertRaisesRegex(sync.Skip, "multiple"):
            self.inspect()

    def test_remote_identity_and_unique_remote(self):
        self.identity.stop()
        self.assertEqual("example/project", sync.github_identity("git@github.com:example/project.git"))
        self.assertEqual("example/project", sync.github_identity("https://github.com/example/project.git"))
        for url in ("https://user:secret@github.com/example/project", "https://elsewhere/example/project", str(self.remote)):
            self.assertIsNone(sync.github_identity(url))
        with self.assertRaises(sync.Skip):
            self.inspect()
        self.identity.start()
        self.git(self.dev, "remote", "add", "duplicate", str(self.remote))
        with self.assertRaises(sync.Skip):
            self.inspect()

    def test_inspect_and_plan_do_not_write(self):
        def metadata():
            return {str(p): p.read_bytes() for p in (self.dev / ".git").rglob("*") if p.is_file()}
        before = metadata()
        snapshot = self.inspect()
        self.assertEqual(before, metadata())
        with self.assertRaises(sync.Skip):
            sync.plan(sync.Git(self.args), self.args, snapshot)
        self.assertEqual(before, metadata())
        self.assertNotIn("+", snapshot["fetch_command"][-1])
        self.assertIn("--refmap=", snapshot["fetch_command"])

    def test_locked_missing_branch_replacements_and_config_changes(self):
        self.git(self.dev, "switch", "-qc", "feature")
        wt = self.root / "locked"
        self.git(self.dev, "worktree", "add", "-q", str(wt), "main")
        self.git(self.dev, "worktree", "lock", str(wt))
        with self.assertRaisesRegex(sync.Skip, "locked"):
            self.inspect()
        self.git(self.dev, "worktree", "unlock", str(wt))
        plan = self.plan()
        self.git(self.dev, "config", "remote.origin.pushurl", "https://example.invalid/elsewhere")
        # Push URLs cannot affect this fetch-only plan.
        sync.check(sync.Git(self.args), self.args, plan)
        self.git(self.dev, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/changed/*")
        with self.assertRaises(sync.Skip):
            sync.check(sync.Git(self.args), self.args, plan)
        self.git(self.dev, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
        self.git(self.dev, "update-ref", f"refs/replace/{self.base}", self.merged)
        with self.assertRaisesRegex(sync.Skip, "replacement"):
            self.inspect()
        self.git(self.dev, "update-ref", "-d", f"refs/replace/{self.base}")
        self.git(wt, "switch", "--detach", "-q")
        self.git(self.dev, "branch", "-D", "main")
        with self.assertRaises(sync.Skip):
            self.inspect()

    def test_other_branch_in_target_worktree_invalidates_plan(self):
        plan = self.plan()
        self.git(self.dev, "switch", "-qc", "feature")
        with self.assertRaises(sync.Skip):
            sync.check(sync.Git(self.args), self.args, plan)

    def test_cli_skip_is_redaction_safe(self):
        result = self.execute(["python3", str(SCRIPT), "inspect", "--repo", str(self.dev),
                               "--github", "example/project", "--default", "main", "--merge-commit", self.merged], check=False)
        self.assertEqual(1, result.returncode)
        record = json.loads(result.stdout)
        self.assertEqual("skip", record["status"])
        self.assertNotIn(str(self.remote), result.stdout)


if __name__ == "__main__":
    unittest.main()
