"""Offline instruction contracts, not runtime approval enforcement or live sync tests."""

import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parents[1]


class WorkspaceSyncContractTests(unittest.TestCase):
    def text(self):
        path = SKILL / "SKILL.md"
        self.assertTrue(path.is_file(), "missing workspace-sync skill")
        return path.read_text()

    def section(self, heading, next_heading):
        text = self.text()
        self.assertIn(heading, text)
        self.assertIn(next_heading, text)
        return text.split(heading, 1)[1].split(next_heading, 1)[0]

    def assert_phrases(self, content, *phrases):
        flat = " ".join(content.split())
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertTrue(phrase in flat, f"missing: {phrase}")

    def test_explicit_entry_and_no_automatic_mutation_grants(self):
        text = self.text()
        front = text.split("---", 2)[1]
        self.assertIn("name: workspace-sync", front)
        self.assertIn("disable-model-invocation: true", front)
        self.assertIn("model-tier: standard", front)
        self.assertIn("effort: high", front)
        grants = re.search(r'^allowed-tools: "(.*)"$', front, re.M).group(1).split(",")
        self.assertIn("AskUserQuestion", grants)
        self.assertIn("Skill(beads)", grants)
        for grant in grants:
            self.assertNotRegex(grant, r"^(Write|Edit|Bash\((make|git|bd|project-workspace))")
        self.assert_phrases(
            text, "explicit invocation only", "default: preview", "preview | git | beads | all",
            "Loading this file", "never activates", "no synchronization now",
        )

    def test_root_validation_and_recipe_inspection_precede_execution(self):
        text = self.text()
        self.assert_phrases(
            text, "current working directory", "physical parent", "not a workspace root",
            "workspace.json", "installed `project-workspace`", "Makefile", "workspace.mk",
            "Before running even a preview", "`make -n` is not a sandbox",
            "project-workspace doctor --workspace .", "no installation or repair",
            "stricter member", "guard", "actual push destination", "alternate worktrees",
            "infrastructure",
        )
        self.assertLess(text.index("## 1. Establish"), text.index("## 2. Preview"))

    def test_previews_disclose_different_effects(self):
        body = self.section("## 2. Preview", "## 3. Confirm Git")
        self.assert_phrases(
            body, "make sync-check", "fetches", "remote-tracking refs", "not offline",
            "fresh confirmation", "make beads-sync-check", "does not contact remotes",
            "does not prove remote freshness", "root and registered checkout paths",
            "unique stores", "workspace-owned",
            "No synchronization in preview mode",
        )

    def test_git_approval_is_separate_exact_and_noninteractive(self):
        body = self.section("## 3. Confirm Git", "## 4. Confirm Beads")
        self.assert_phrases(
            body, "explicit grouped Git exception", "per-action policy", "AskUserQuestion",
            "Run make sync", "Skip Git", "Stop", "next tool call", "make sync",
            "fetches again", "not an atomic", "non-interactively", "diverged branches",
            "never add `--yes`", "no Beads approval",
        )
        self.assertLess(body.index("AskUserQuestion"), body.index("```bash\nmake sync\n```"))

    def test_beads_approval_reuses_owner_without_authorizing_git(self):
        body = self.section("## 4. Confirm Beads", "## 5. Outcomes")
        self.assert_phrases(
            body, "../beads/SKILL.md#remote-and-destructive-safety", "AskUserQuestion",
            "Run make beads-sync", "Skip Beads", "Stop", "next tool call",
            "make beads-sync", "pull then non-force push", "origin", "unique store",
            "no Git approval", "changed preview",
        )
        self.assertLess(body.index("AskUserQuestion"), body.index("```bash\nmake beads-sync\n```"))

    def test_deny_and_changed_state_never_dispatch(self):
        self.assert_phrases(
            self.text(), "Denied, skipped, abandoned or ambiguous approval means no dispatch",
            "not permission for the other action", "changed preview invalidates approval",
            "no blanket approval for both", "recheck", "before asking",
            "No automatic retries or raw-command fallback",
        )

    def test_partial_outcomes_do_not_claim_atomicity_or_success(self):
        body = self.section("## 5. Outcomes", "## Maintainer evidence")
        self.assert_phrases(
            body, "continue other targets after a failure", "non-zero", "skipped",
            "not synchronized", "possible merge/rebase state", "abort succeeded",
            "stop before the other sync path", "Do not resume", "No automatic retries",
            "production", "remote configuration", "migration", "backup publication",
        )

    def test_code_blocks_never_hide_mutations_or_raw_fallback(self):
        blocks = re.findall(r"```bash\n(.*?)```", self.text(), re.S)
        commands = [line for block in blocks for line in block.splitlines() if line.strip()]
        self.assertEqual(commands, [
            "project-workspace doctor --workspace .",
            "make sync-check",
            "make beads-sync-check",
            "make sync",
            "make beads-sync",
        ])
        for command in commands:
            self.assertNotRegex(command, r"&&|;|\||--yes|--force|git (push|pull|rebase)|bd dolt")

    def test_test_guide_covers_manual_decision_scenarios(self):
        guide = (SKILL / "tests/README.md").read_text()
        self.assertIn("authored expectations, not observed model behavior", guide)
        cases = set(re.findall(r"^\| `([^`]+)` \|", guide, re.M))
        self.assertEqual(cases, {
            "preview-only", "deny-fetch", "deny-git", "deny-beads", "abandoned",
            "changed-preview", "unsafe-recipe", "wrong-root", "strict-member",
            "unclear-push", "diverged", "partial-git", "partial-beads", "separate-approvals",
        })

    def test_catalog_and_full_gate_include_skill(self):
        catalog = (ROOT / "skills/README.md").read_text()
        self.assertEqual(len(re.findall(r"^\| workspace-sync \|", catalog, re.M)), 1)
        makefile = (ROOT / "Makefile").read_text()
        self.assertIn("test-workspace-sync", makefile.split("TEST_TARGETS :=", 1)[1].split("test:", 1)[0])
        self.assertIn("-s skills/workspace-sync/tests", makefile)
        self.assert_phrases(self.text(), "not runtime enforcement", "not live remote evidence")


if __name__ == "__main__":
    unittest.main()
