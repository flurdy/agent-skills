"""Instruction contracts; runtime gates are characterized separately, not inferred from prose."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills/beads-setup/SKILL.md"


class SetupContractTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SKILL.is_file(), "missing beads-setup skill")
        self.text = SKILL.read_text()

    def test_create_is_host_pinned_and_never_publishes_source(self):
        blocks = re.findall(r"```bash\n(.*?)```", self.text, re.S)
        create = [b.strip() for b in blocks if "gh repo create" in b]
        self.assertEqual(create, ["GH_HOST=github.com gh repo create OWNER/NAME --private --add-readme"])
        for block in blocks:
            self.assertNotIn("gh repo edit", block)
            self.assertNotIn("--public", block)
            if "gh repo create" in block:
                for forbidden in ("--source", "--push", "--remote"):
                    self.assertNotIn(forbidden, block)
        self.assertIn("runtime command permission", self.text)

    def test_scope_and_capability_gates(self):
        for phrase in ("Preview is read-only and the default", "bd 1.2.2", "Python 3.10+", "GitHub CLI",
                       'beadsStore: "workspace"', "ancestor", "symlink", "dirty", "index", "shared Git",
                       "ambient", "no-push", "backup", "Never print credentials"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

    def test_individual_mutations_are_gated_and_no_executor_is_added(self):
        self.assertIn("fresh confirmation immediately before each mutation", self.text)
        self.assertIn("not-visible", self.text)
        self.assertIn("not proof of absence", self.text)
        self.assertIn("name collision", self.text)
        self.assertIn("--private --add-readme", self.text)
        blocks = re.findall(r"```bash\n(.*?)```", self.text, re.S)
        init = [b for b in blocks if "init --prefix" in b]
        self.assertEqual(len(init), 1)
        self.assertIn('--chdir="$ROOT"', init[0])
        self.assertNotIn(' -C ', init[0])
        for flag in ("--remote", "--sandbox", "--non-interactive", "--skip-hooks", "--skip-agents"):
            self.assertIn(flag, init[0])
        for block in blocks:
            self.assertNotIn("&&", block)
            for forbidden in ("--force", "--reinit", "--discard-remote", "--destroy-token", "gh repo delete", "git push"):
                self.assertNotIn(forbidden, block)
        self.assertIn('"$BD" -C "$ROOT"', self.text)
        self.assertIn("dolt push --remote origin", self.text)

    def test_side_effects_and_failure_boundaries(self):
        for phrase in ("auto-stage", "--no-verify", "active hooks", "source Git remotes", "Dolt data branch",
                       "repository ID", "partial failure", "no automatic retry", "no automatic rollback",
                       "no live GitHub", "refs/dolt/data", "warnings", "unchanged"):
            self.assertIn(phrase, self.text)
        self.assertNotIn("`vc log`", self.text)
        self.assertIn("DOLT_HASHOF('HEAD')", self.text)
        self.assertIn("separately confirmed readback fetch", self.text)
        self.assertIn('fetch origin "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"', self.text)
        self.assertIn("../beads/SKILL.md", self.text)
        self.assertIn("../beads-migrate-to-dolt/SKILL.md", self.text)
        self.assertIn("../beads/references/integration-cleanup.md", self.text)

    def test_catalog_dispatch_and_test_gate(self):
        self.assertIn("| beads-setup |", (ROOT / "skills/README.md").read_text())
        self.assertIn("../beads-setup/SKILL.md", (ROOT / "skills/beads/SKILL.md").read_text())
        self.assertIn("test-beads-setup", (ROOT / "Makefile").read_text())


if __name__ == "__main__":
    unittest.main()
