"""Exercise commit coverage against real, offline Git repositories."""

import os
from pathlib import Path
import subprocess
import tempfile
import shutil
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "activity-commits.py"


class CommitCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.env = dict(os.environ, TZ="UTC", GIT_CONFIG_NOSYSTEM="1", HOME=str(self.root))
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Tester")
        self.git("config", "user.email", "work@example.com")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text("""#!/usr/bin/env python3
import json, os, sys
if os.environ.get('GH_UNAVAILABLE'):
    sys.exit(1)
if sys.argv[1:3] == ['api', 'user']:
    print(json.dumps({'login': 'tester', 'id': 42, 'email': None}))
elif sys.argv[1:3] == ['api', 'user/emails']:
    addresses = ['personal@example.com']
    if 'select(.verified)' not in sys.argv[-1]:
        addresses.append('unverified@example.com')
    print(json.dumps(addresses))
else:
    sys.exit(1)
""")
        gh.chmod(0o755)
        self.env["PATH"] = f"{self.bin}:{os.environ['PATH']}"
        self.commit("base", "2026-10-25T12:00:00Z")

    def git(self, *args, env=None):
        return subprocess.check_output(
            ["git", "-C", str(self.repo), *args], env=env or self.env, text=True
        ).strip()

    def commit(self, subject, when, author="work@example.com", authored=None):
        env = dict(
            self.env,
            GIT_AUTHOR_EMAIL=author,
            GIT_AUTHOR_DATE=authored or when,
            GIT_COMMITTER_DATE=when,
        )
        self.git("commit", "-q", "--allow-empty", "-m", subject, env=env)
        return self.git("rev-parse", "HEAD")

    def collect(self, *extra, env=None):
        result = subprocess.run(
            [
                "python3", str(SCRIPT), "--since", "2026-10-26T00:00:00+00:00",
                "--until", "2026-10-27T00:00:00+00:00", "--repo", "repo", str(self.repo),
                *extra,
            ],
            env=env or self.env, text=True, capture_output=True, check=True,
        )
        return result.stdout

    def test_squash_on_cached_default_branch_and_exact_account_identity(self):
        self.git("checkout", "-qb", "merged")
        self.commit("squash PR (#123)", "2026-10-26T12:00:00Z", "personal@example.com",
                    authored="2026-10-24T12:00:00Z")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.git("checkout", "-q", "main")
        self.git("branch", "-D", "merged")
        output = self.collect()
        self.assertIn("squash PR (#123)", output)
        self.assertIn("origin/main", output)
        self.assertIn("Mon 2026-10-26 12:00:00 +0000", output)
        self.assertIn("behind cached origin/main", output)
        self.assertIn("no fetch", output)

    def test_unchecked_branches_detached_worktrees_and_sha_deduplication(self):
        self.git("checkout", "-qb", "feature")
        sha = self.commit("feature change", "2026-10-26T09:00:00Z")
        self.git("branch", "copy")
        self.git("checkout", "-q", "main")
        wt = self.root / "detached worktree"
        self.git("worktree", "add", "-q", "--detach", str(wt), sha)
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "detached change"],
            env=dict(self.env, GIT_AUTHOR_DATE="2026-10-26T10:00:00Z",
                     GIT_COMMITTER_DATE="2026-10-26T10:00:00Z"), check=True,
        )
        output = self.collect()
        self.assertEqual(output.count("feature change"), 1)
        self.assertEqual(output.count("detached change"), 1)
        self.assertIn("detached worktree|HEAD", output)

    def test_aliases_noreply_and_literal_email_matching(self):
        self.git("config", "--add", "activity.authorEmail", "alias+dev@example.com")
        self.commit("alias change", "2026-10-26T08:00:00Z", "alias+dev@example.com")
        self.commit("noreply change", "2026-10-26T09:00:00Z", "42+tester@users.noreply.github.com")
        self.commit("lookalike excluded", "2026-10-26T10:00:00Z", "work@exampleXcom")
        self.commit("unrelated excluded", "2026-10-26T11:00:00Z", "someone@example.com")
        self.commit("unverified excluded", "2026-10-26T11:30:00Z", "unverified@example.com")
        output = self.collect()
        self.assertIn("alias change", output)
        self.assertIn("noreply change", output)
        self.assertNotIn("lookalike excluded", output)
        self.assertNotIn("unrelated excluded", output)
        self.assertNotIn("unverified excluded", output)

    def test_inclusive_start_exclusive_end_and_nonmonotonic_history(self):
        self.commit("start included", "2026-10-26T00:00:00Z")
        self.commit("end excluded", "2026-10-27T00:00:00Z")
        self.commit("old tip excluded", "2026-10-25T23:00:00Z")
        output = self.collect()
        self.assertIn("start included", output)
        self.assertNotIn("end excluded", output)
        self.assertNotIn("old tip excluded", output)

    def test_failed_identity_lookup_retains_local_commits_and_reports_gap(self):
        self.commit("local change", "2026-10-26T12:00:00Z")
        output = self.collect(env=dict(self.env, GH_UNAVAILABLE="1"))
        self.assertIn("repo|OK", output)
        self.assertIn("local change", output)
        self.assertIn("GitHub author identities unavailable", output)

    def test_missing_author_and_failed_repository_are_isolated(self):
        self.git("config", "user.email", "")
        output = self.collect("--repo", "missing", str(self.root / "missing"),
                              env=dict(self.env, GH_UNAVAILABLE="1"))
        self.assertIn("repo|NO_AUTHOR", output)
        self.assertIn("missing|ERROR", output)

    def test_unicode_subject_does_not_drop_other_commits(self):
        self.commit("earlier change", "2026-10-26T08:00:00Z")
        self.commit("subject with\u2028unicode separator", "2026-10-26T09:00:00Z")
        output = self.collect()
        self.assertIn("repo|OK", output)
        self.assertIn("earlier change", output)
        self.assertIn("unicode separator", output)

    def test_missing_default_pointer_and_failed_lag_probe_keep_commits(self):
        self.commit("cached change", "2026-10-26T12:00:00Z")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("reset", "--hard", "HEAD~1")
        real_git = shutil.which("git")
        wrapper = self.bin / "git"
        wrapper.write_text(
            "#!/usr/bin/env python3\nimport os, sys\n"
            "if 'rev-list' in sys.argv: sys.exit(1)\n"
            f"os.execv({real_git!r}, [{real_git!r}, *sys.argv[1:]])\n"
        )
        wrapper.chmod(0o755)
        output = self.collect()
        self.assertIn("repo|OK", output)
        self.assertIn("cached change", output)
        self.assertIn("default branch unknown", output)
        self.assertIn("lag unavailable", output)

    def test_failed_ref_preserves_successful_ref_rows(self):
        self.commit("good change", "2026-10-26T12:00:00Z")
        self.git("branch", "bad")
        real_git = shutil.which("git")
        wrapper = self.bin / "git"
        wrapper.write_text(
            "#!/usr/bin/env python3\nimport os, sys\n"
            "if 'log' in sys.argv and 'refs/heads/bad' in sys.argv: sys.exit(1)\n"
            f"os.execv({real_git!r}, [{real_git!r}, *sys.argv[1:]])\n"
        )
        wrapper.chmod(0o755)
        output = self.collect()
        self.assertIn("repo|ERROR", output)
        self.assertIn("good change", output)
        self.assertIn("history for bad", output)

    def test_unborn_repository_is_empty_not_failed(self):
        empty = self.root / "empty"
        subprocess.run(["git", "init", "-q", str(empty)], env=self.env, check=True)
        output = self.collect("--repo", "empty", str(empty))
        self.assertIn("empty|OK", output)


if __name__ == "__main__":
    unittest.main()
