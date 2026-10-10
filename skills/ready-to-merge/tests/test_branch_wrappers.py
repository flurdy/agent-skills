"""Exercise fixed-method branch helpers with a fake gh, never GitHub."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
PROJECTION = "{name, sha: .commit.sha}"


class BranchWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="branch wrappers ")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.log = self.work / "gh-args.jsonl"
        (self.bin / "git").symlink_to(shutil.which("git"))
        fake_gh = self.bin / "gh"
        fake_gh.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "with open(os.environ['GH_TEST_LOG'], 'a') as log:\n"
            "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "sys.stdout.write(os.environ['GH_TEST_STDOUT'])\n"
            "sys.stderr.write(os.environ['GH_TEST_STDERR'])\n"
            "sys.exit(int(os.environ['GH_TEST_EXIT']))\n"
        )
        fake_gh.chmod(0o755)
        self.env = {
            "PATH": str(self.bin),
            "HOME": str(self.work),
            "GH_TEST_LOG": str(self.log),
            "GH_TEST_STDOUT": '{"name":"feature/topic","sha":"fixture"}\n',
            "GH_TEST_STDERR": "",
            "GH_TEST_EXIT": "0",
        }

    def invoke(self, script, args=("acme", "widgets", "feature/topic"), **overrides):
        self.log.unlink(missing_ok=True)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            cwd=self.work, env=self.env | overrides,
            capture_output=True, text=True, timeout=5,
        )
        commands = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, commands

    def test_read_method_endpoint_projection_and_output_are_fixed(self):
        result, commands = self.invoke("gh-branch-view.py")
        self.assertEqual(commands, [[
            "api", "--hostname", "github.com", "--method", "GET",
            "repos/acme/widgets/branches/feature/topic", "--jq", PROJECTION,
        ]])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, self.env["GH_TEST_STDOUT"])
        self.assertEqual(result.stderr, "")

    def test_delete_method_and_heads_namespace_are_fixed(self):
        result, commands = self.invoke("gh-branch-delete.py", GH_TEST_STDOUT="")
        self.assertEqual(commands, [[
            "api", "--hostname", "github.com", "--method", "DELETE",
            "repos/acme/widgets/git/refs/heads/feature/topic",
        ]])
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_valid_ref_characters_cannot_become_url_or_gh_placeholders(self):
        for script in ("gh-branch-view.py", "gh-branch-delete.py"):
            with self.subTest(script=script):
                result, commands = self.invoke(script, ("acme-team", "widgets.repo", "feature/café#50%{branch}"))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(commands), 1)
                endpoint = commands[0][5]
                self.assertTrue(endpoint.endswith("feature/caf%C3%A9%2350%25%7Bbranch%7D"), endpoint)
                self.assertNotIn("{branch}", endpoint)
                self.assertNotIn("#", endpoint)

    def test_invalid_arguments_never_reach_gh(self):
        invalid = [
            (), ("acme",), ("acme", "widgets"),
            ("acme", "widgets", "feature/topic", "--method=POST"),
            (".", "widgets", "feature/topic"), ("..", "widgets", "feature/topic"),
            ("acme/other", "widgets", "feature/topic"), ("{owner}", "widgets", "feature/topic"),
            ("acme", "../other", "feature/topic"), ("acme", "--hostname", "feature/topic"),
        ]
        invalid.extend(("acme", "widgets", branch) for branch in (
            "", "--method=POST", "../main", "feature/../main", "feature?x=1",
            "feature/.hidden", "feature~1", "feature:tags", "feature topic", "HEAD", "@{-1}",
        ))
        for script in ("gh-branch-view.py", "gh-branch-delete.py"):
            for args in invalid:
                with self.subTest(script=script, args=args):
                    result, commands = self.invoke(script, args)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(commands, [])
                    self.assertTrue(result.stderr)

    def test_delete_rejects_common_trunk_names_but_read_can_inspect_them(self):
        for branch in ("main", "master"):
            result, commands = self.invoke("gh-branch-delete.py", ("acme", "widgets", branch))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(commands, [])
            result, commands = self.invoke("gh-branch-view.py", ("acme", "widgets", branch))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(commands), 1)

    def test_errors_and_404_propagate_without_retry_or_success_reclassification(self):
        for script in ("gh-branch-view.py", "gh-branch-delete.py"):
            for message in ("gh: Not Found (HTTP 404)\n", "gh: Forbidden (HTTP 403)\n", "fixture timeout\n"):
                with self.subTest(script=script, message=message):
                    result, commands = self.invoke(
                        script, GH_TEST_EXIT="17", GH_TEST_STDOUT="partial\n", GH_TEST_STDERR=message,
                    )
                    self.assertEqual(result.returncode, 17)
                    self.assertEqual(result.stdout, "partial\n")
                    self.assertEqual(result.stderr, message)
                    self.assertEqual(len(commands), 1)

    def test_missing_runtime_tools_fail_without_remote_requests(self):
        for script in ("gh-branch-view.py", "gh-branch-delete.py"):
            for tool in ("git", "gh"):
                with self.subTest(script=script, tool=tool):
                    path = self.bin / tool
                    backup = self.bin / f"disabled-{tool}"
                    path.rename(backup)
                    try:
                        result, commands = self.invoke(script)
                    finally:
                        backup.rename(path)
                    self.assertEqual(result.returncode, 127, result.stderr)
                    self.assertEqual(commands, [])
                    self.assertIn(tool, result.stderr)

    def test_entry_points_are_executable(self):
        for script in ("gh-branch-view.py", "gh-branch-delete.py"):
            self.assertTrue(os.access(SCRIPTS / script, os.X_OK))


if __name__ == "__main__":
    unittest.main()
