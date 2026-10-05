"""Local-only Git fixtures for the read-only trunk integration analyser."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "upstream.py"


class UpstreamTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
                    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
                    "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
        self.serial = 0
        self.route = []
        self.fixture()

    def git(self, repo, *args, check=True):
        return subprocess.run(["git", "-C", str(repo), *args], env=self.env,
                              capture_output=True, text=True, check=check)

    def fixture(self, branch="main", remote="origin"):
        self.serial += 1
        folder = self.root / str(self.serial)
        folder.mkdir()
        self.dev, self.other, self.remote = (folder / name for name in ("dev", "other", "remote.git"))
        self.branch, self.remote_name = branch, remote
        self.dev.mkdir()
        self.remote.mkdir()
        self.git(self.remote, "init", "--bare", "-q", f"--initial-branch={branch}")
        self.git(self.dev, "init", "-q", f"--initial-branch={branch}")
        self.base = self.commit(self.dev, "base", "base\n")
        self.git(self.dev, "remote", "add", remote, str(self.remote))
        self.git(self.dev, "push", "-qu", remote, branch)
        self.git(folder, "clone", "-q", str(self.remote), str(self.other))

    def commit(self, repo, name, content):
        (repo / name).write_text(content)
        self.git(repo, "add", name)
        self.git(repo, "commit", "-qm", name)
        return self.git(repo, "rev-parse", "HEAD").stdout.strip()

    def saved(self, payload, name):
        path = self.root / name
        path.write_text(json.dumps(payload))
        return str(path)

    def call(self, action, *, before=None, plan=None, ok=True):
        args = [sys.executable, str(HELPER), action, "--repo", str(self.dev), *self.route]
        if before is not None:
            args += ["--before", self.saved(before, "before.json")]
        if plan is not None:
            args += ["--plan", self.saved(plan, "plan.json")]
        result = subprocess.run(args, cwd=self.root, env=self.env, capture_output=True,
                                text=True, timeout=30)
        if ok:
            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        else:
            self.assertNotEqual(0, result.returncode, result.stdout)
        return json.loads(result.stdout)

    def advance_remote(self, name="remote", content="remote\n"):
        oid = self.commit(self.other, name, content)
        self.git(self.other, "push", "-q", "origin", self.branch)
        self.git(self.dev, "fetch", "-q", self.remote_name)
        return oid

    def divergent(self):
        self.commit(self.dev, "local", "local\n")
        before = self.call("inspect")
        self.advance_remote()
        return self.call("plan", before=before)

    def apply_fixture(self, plan):
        checked = self.call("check", plan=plan)
        self.assertEqual("current", checked["status"])
        # Fixtures alone execute previews. Production helper never executes them.
        return subprocess.run(plan["command"], cwd=self.root, env=self.env,
                              capture_output=True, text=True)

    def test_noop_and_local_ahead_are_read_only(self):
        for ahead in (False, True):
            if ahead:
                self.commit(self.dev, "local", "local\n")
            before = self.call("inspect")
            def metadata():
                return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (self.dev / ".git").rglob("*") if p.is_file()}
            original = metadata()
            plan = self.call("plan", before=before)
            self.assertEqual("local-ahead" if ahead else "unchanged", plan["classification"])
            self.assertEqual([], plan["command"])
            self.call("check", plan=plan)
            self.call("verify", plan=plan)
            self.assertEqual(original, metadata())

    def test_fast_forward_main_and_master_non_origin(self):
        for branch in ("main", "master"):
            self.fixture(branch, "team")
            before = self.call("inspect")
            target = self.advance_remote()
            plan = self.call("plan", before=before)
            self.assertEqual("fast-forward", plan["classification"])
            self.assertIn("--ff-only", plan["command"])
            self.assertEqual(0, self.apply_fixture(plan).returncode)
            self.assertEqual(target, self.git(self.dev, "rev-parse", "HEAD").stdout.strip())
            self.assertEqual("verified", self.call("verify", plan=plan)["status"])

    def test_divergence_preserves_remote_and_local_patches(self):
        plan = self.divergent()
        self.assertEqual("replay", plan["classification"])
        self.assertEqual(1, len(plan["replay"]))
        for flag in ("--no-autostash", "--no-autosquash", "--no-update-refs", "--empty=stop"):
            self.assertIn(flag, plan["command"])
        self.assertEqual(0, self.apply_fixture(plan).returncode)
        self.assertEqual("verified", self.call("verify", plan=plan)["status"])
        self.git(self.dev, "merge-base", "--is-ancestor", plan["current"]["target"], "HEAD")
        self.assertEqual("local\n", (self.dev / "local").read_text())
        self.assertTrue((self.dev / "remote").exists())

    def test_missing_wrong_and_multiple_upstreams(self):
        key = f"branch.{self.branch}.merge"
        self.git(self.dev, "config", "--unset", key)
        self.assertIn("upstream", self.call("inspect", ok=False)["reason"])
        self.git(self.dev, "config", key, "refs/heads/feature")
        self.call("inspect", ok=False)
        self.git(self.dev, "config", key, "refs/heads/main")
        self.git(self.dev, "config", "--add", key, "refs/heads/master")
        self.call("inspect", ok=False)

    def test_detached_feature_dirty_and_operation_states(self):
        self.git(self.dev, "switch", "--detach", "-q")
        self.call("inspect", ok=False)
        self.git(self.dev, "switch", "-q", "-c", "feature")
        self.call("inspect", ok=False)
        self.git(self.dev, "switch", "-q", "main")
        (self.dev / "untracked").touch()
        self.call("inspect", ok=False)
        (self.dev / "untracked").unlink()
        for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG", "index.lock"):
            with self.subTest(name=name):
                path = self.dev / ".git" / name
                path.write_text(self.base + "\n")
                self.call("inspect", ok=False)
                path.unlink()
        for name in ("rebase-merge", "rebase-apply", "sequencer"):
            path = self.dev / ".git" / name
            path.mkdir()
            self.call("inspect", ok=False)
            path.rmdir()

    def test_stale_head_target_config_and_shared_refs(self):
        for changed in ("head", "target", "config", "url-rewrite", "shared"):
            with self.subTest(changed=changed):
                self.fixture()
                plan = self.divergent()
                if changed == "head":
                    self.commit(self.dev, "later", "later\n")
                elif changed == "target":
                    self.advance_remote("later", "later\n")
                elif changed == "config":
                    self.git(self.dev, "config", "remote.origin.pushurl", str(self.root / "elsewhere"))
                elif changed == "url-rewrite":
                    self.git(self.dev, "config", "url.https://invalid.example/.insteadOf", str(self.remote))
                else:
                    self.git(self.dev, "tag", "shared")
                self.call("check", plan=plan, ok=False)

    def test_rewound_or_unrelated_upstream_is_refused(self):
        before = self.call("inspect")
        self.advance_remote()
        moved = self.call("inspect")
        self.git(self.dev, "update-ref", "refs/remotes/origin/main", self.base)
        self.call("plan", before=moved, ok=False)
        self.git(self.other, "switch", "--orphan", "unrelated")
        unrelated = self.commit(self.other, "different", "different\n")
        self.git(self.dev, "fetch", "-q", "origin")
        self.git(self.other, "push", "-q", "origin", "unrelated")
        self.git(self.dev, "fetch", "-q", "origin")
        self.git(self.dev, "update-ref", "refs/remotes/origin/main", unrelated)
        self.call("plan", before=before, ok=False)

    def test_shared_merge_empty_and_equivalent_ranges_are_refused(self):
        for kind in ("branch", "tag", "remote", "merge", "empty", "equivalent"):
            with self.subTest(kind=kind):
                self.fixture()
                local = self.commit(self.dev, "local", "local\n")
                if kind == "branch":
                    self.git(self.dev, "branch", "shared")
                elif kind == "tag":
                    self.git(self.dev, "tag", "shared")
                elif kind == "remote":
                    self.git(self.dev, "update-ref", "refs/remotes/another/shared", local)
                elif kind == "merge":
                    self.git(self.dev, "switch", "-qc", "side", self.base)
                    self.commit(self.dev, "side", "side\n")
                    self.git(self.dev, "switch", "-q", "main")
                    self.git(self.dev, "merge", "--no-ff", "side", "-qm", "merge")
                    self.git(self.dev, "branch", "-D", "side")
                elif kind == "empty":
                    self.git(self.dev, "commit", "--allow-empty", "-qm", "empty")
                before = self.call("inspect")
                if kind == "equivalent":
                    self.commit(self.other, "local", "local\n")
                    self.git(self.other, "commit", "--amend", "-qm", "equivalent remote patch")
                    self.git(self.other, "push", "-q", "origin", self.branch)
                    self.git(self.dev, "fetch", "-q", self.remote_name)
                else:
                    self.advance_remote()
                self.call("plan", before=before, ok=False)

    def test_conflicts_stop_and_fixture_abort_restores_source(self):
        old = self.commit(self.dev, "base", "local conflict\n")
        before = self.call("inspect")
        self.advance_remote("base", "remote conflict\n")
        plan = self.call("plan", before=before)
        self.assertNotEqual(0, self.apply_fixture(plan).returncode)
        self.call("verify", plan=plan, ok=False)
        self.git(self.dev, "rebase", "--abort")
        self.assertEqual(old, self.git(self.dev, "rev-parse", "HEAD").stdout.strip())
        self.call("check", plan=plan)

    def test_verification_rejects_changed_recovery_identity(self):
        plan = self.divergent()
        self.assertEqual(0, self.apply_fixture(plan).returncode)
        self.git(self.dev, "update-ref", "ORIG_HEAD", self.base)
        refused = self.call("verify", plan=plan, ok=False)
        self.assertIn("recovery identity", refused["reason"])

    def test_patch_verification_rejects_same_count_with_valid_ancestry_and_reflog(self):
        plan = self.divergent()
        bad = self.commit(self.other, "local", "wrong replayed change\n")
        self.git(self.dev, "fetch", "-q", str(self.other), bad)
        self.git(self.dev, "reset", "--hard", bad)
        self.assertEqual(plan["current"]["head"], self.git(self.dev, "rev-parse", "ORIG_HEAD").stdout.strip())
        self.assertEqual("1", self.git(self.dev, "rev-list", "--count", f"{plan['current']['target']}..HEAD").stdout.strip())
        refused = self.call("verify", plan=plan, ok=False)
        self.assertIn("replayed patches changed", refused["reason"])

    def test_tampered_plan_is_not_a_command_source(self):
        plan = self.divergent()
        plan["command"] = ["git", "push", "--force"]
        self.call("check", plan=plan, ok=False)

    def test_shallow_replacement_and_graft_graphs_are_refused(self):
        (self.dev / ".git" / "shallow").write_text(self.base + "\n")
        self.call("inspect", ok=False)
        (self.dev / ".git" / "shallow").unlink()
        oid = self.commit(self.dev, "new", "new\n")
        self.git(self.dev, "replace", self.base, oid)
        self.call("inspect", ok=False)
        self.git(self.dev, "replace", "-d", self.base)
        (self.dev / ".git" / "info" / "grafts").write_text(oid + "\n")
        self.call("inspect", ok=False)

    def test_stdin_evidence_and_remote_url_redaction(self):
        self.git(self.dev, "config", "remote.origin.url", "https://user:example-only@invalid.example/repo")
        before = self.call("inspect")
        self.assertNotIn("example-only", json.dumps(before))
        result = subprocess.run(
            [sys.executable, str(HELPER), "plan", "--repo", str(self.dev), "--before", "-"],
            cwd=self.root, env=self.env, input=json.dumps(before), text=True, capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual("unchanged", json.loads(result.stdout)["classification"])

    def test_missing_safe_git_capability_stops_replay(self):
        wrapper = self.root / "old-git-wrapper"
        wrapper.write_text(f'''#!{sys.executable}
import os, sys
if sys.argv[1] == "rebase":
    print("old help without required options")
    sys.exit(129)
os.execvp("git", ["git", "-C", {str(self.dev)!r}, sys.argv[1], *sys.argv[3:]])
''')
        wrapper.chmod(0o755)
        self.route = ["--mgit", str(wrapper), "--service", "member"]
        self.commit(self.dev, "local", "local\n")
        before = self.call("inspect")
        self.advance_remote()
        self.assertIn("options", self.call("plan", before=before, ok=False)["reason"])

    def test_rejected_nonforce_fixture_push_leaves_remote_intact(self):
        plan = self.divergent()
        self.assertEqual(0, self.apply_fixture(plan).returncode)
        result = self.call("verify", plan=plan)
        remote_tip = self.advance_remote("later", "later\n")
        rejected = self.git(self.dev, "push", "--no-force", "--no-follow-tags", "origin",
                            f"{result['head']}:refs/heads/main", check=False)
        self.assertNotEqual(0, rejected.returncode)
        self.assertEqual(remote_tip, self.git(self.remote, "rev-parse", "main").stdout.strip())
        self.call("verify", plan=plan, ok=False)

    def test_mgit_routes_all_reads_without_mutations(self):
        wrapper = self.root / "mgit"
        log = self.root / "git-calls"
        wrapper.write_text(f'''#!{sys.executable}
import json, os, sys
args = sys.argv[1:]
assert args[1] == "member"
with open({str(log)!r}, "a") as out: out.write(json.dumps(args) + "\\n")
os.execvp("git", ["git", "-C", {str(self.dev)!r}, args[0], *args[2:]])
''')
        wrapper.chmod(0o755)
        self.route = ["--mgit", str(wrapper), "--service", "member"]
        plan = self.divergent()
        self.call("check", plan=plan)
        self.assertEqual([str(wrapper), "rebase", "member"], plan["command"][:3])
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertGreater(len(calls), 5)
        for call in calls:
            self.assertNotIn(call[0], {"fetch", "push", "merge", "update-ref", "reset", "checkout"})
            if call[0] == "rebase":
                self.assertEqual(["rebase", "member", "-h"], call)


if __name__ == "__main__":
    unittest.main()
