"""Offline contract for the shared inline-comment reader and its legacy entry points."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
CANONICAL = "pr-status/scripts/gh-pr-inline-comments.sh"
COMPATIBILITY = (
    "review-comments/scripts/gh-pr-comments.sh",
    "reply-comments/scripts/gh-pr-comments.sh",
)
PROJECTION = ".[] | {id, path, line, body, user: .user.login, in_reply_to_id, created_at}"


class InlineCommentsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="inline comments ")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.log = self.work / "gh-args"
        bin_dir = self.work / "bin"
        bin_dir.mkdir()
        fake_gh = bin_dir / "gh"
        fake_gh.write_text(
            '#!/bin/bash\n'
            'printf "%s\\0" "$@" >>"$GH_TEST_LOG"\n'
            'printf "%s" "$GH_TEST_STDOUT"\n'
            'printf "%s" "$GH_TEST_STDERR" >&2\n'
            'exit "$GH_TEST_EXIT"\n'
        )
        fake_gh.chmod(0o755)
        self.env = {
            "PATH": f"{bin_dir}:{os.defpath}",
            "HOME": str(self.work),
            "GH_TEST_LOG": str(self.log),
            "GH_TEST_STDOUT": '{"id":1,"body":"fixture"}\n',
            "GH_TEST_STDERR": "",
            "GH_TEST_EXIT": "0",
        }

    def invoke(self, path, args=("acme", "widgets", "42"), **overrides):
        self.log.unlink(missing_ok=True)
        result = subprocess.run(
            [str(path), *args], cwd=self.work, env=self.env | overrides,
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(
            self.log.read_bytes().split(b"\0")[:-1],
            [value.encode() for value in (
                "api", f"repos/{args[0]}/{args[1]}/pulls/{args[2]}/comments",
                "--jq", PROJECTION,
            )],
        )
        return result

    def test_all_entry_points_preserve_arguments_and_output(self):
        for entry in (CANONICAL, *COMPATIBILITY):
            for args in (("acme", "widgets", "42"), ("acme-team", "widget repo", "43")):
                with self.subTest(entry=entry, args=args):
                    result = self.invoke(ROOT / "skills" / entry, args)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, self.env["GH_TEST_STDOUT"])
                    self.assertEqual(result.stderr, "")

    def test_empty_response_is_not_replaced(self):
        for entry in (CANONICAL, *COMPATIBILITY):
            with self.subTest(entry=entry):
                result = self.invoke(ROOT / "skills" / entry, GH_TEST_STDOUT="")
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_failures_propagate_without_retry(self):
        for entry in (CANONICAL, *COMPATIBILITY):
            with self.subTest(entry=entry):
                result = self.invoke(
                    ROOT / "skills" / entry,
                    GH_TEST_EXIT="23", GH_TEST_STDOUT="partial\n", GH_TEST_STDERR="fixture failure\n",
                )
                self.assertEqual(result.returncode, 23)
                self.assertEqual(result.stdout, "partial\n")
                self.assertEqual(result.stderr, "fixture failure\n")

    def test_installed_skill_directory_links_work_from_an_unrelated_cwd(self):
        installed = self.work / "installed skills"
        installed.mkdir()
        for skill in ("pr-status", "reply-comments", "review-comments"):
            (installed / skill).symlink_to(ROOT / "skills" / skill, target_is_directory=True)
        for entry in (CANONICAL, *COMPATIBILITY):
            with self.subTest(entry=entry):
                result = self.invoke(installed / entry)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, self.env["GH_TEST_STDOUT"])

    def test_compatibility_paths_delegate_without_duplicating_api_logic(self):
        for entry in COMPATIBILITY:
            with self.subTest(entry=entry):
                text = (ROOT / "skills" / entry).read_text()
                self.assertIn("exec ", text)
                self.assertIn(CANONICAL, text)
                self.assertNotIn("gh api", text)
                self.assertNotIn(PROJECTION, text)

    def test_consumers_grant_the_canonical_helper(self):
        for skill in ("review-comments", "reply-comments"):
            with self.subTest(skill=skill):
                text = (ROOT / "skills" / skill / "SKILL.md").read_text()
                frontmatter = text.split("---", 2)[1]
                grants = re.search(r'^allowed-tools: "(.*)"$', frontmatter, re.M)
                self.assertIsNotNone(grants)
                permissions = {entry.strip() for entry in grants[1].split(",")}
                self.assertIn(f"Bash(~/.agents/skills/{CANONICAL}:*)", permissions)
                self.assertNotIn(f"Bash(~/.agents/skills/{skill}/scripts/gh-pr-comments.sh:*)", permissions)
                self.assertNotIn("Bash(gh api:*)", permissions)


if __name__ == "__main__":
    unittest.main()
