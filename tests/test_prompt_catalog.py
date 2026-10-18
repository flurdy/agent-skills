"""Every top-level prompt template has frontmatter and one catalog row, and vice versa."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"


class PromptCatalogTests(unittest.TestCase):
    def test_astra_delegates_exact_model_and_preserves_review_gates(self):
        text = (PROMPTS / "ask-astra.md").read_text()
        self.assertIn("argument-hint: \"<question>\"", text)
        self.assertIn("$ARGUMENTS", text)
        self.assertIn("`second-opinion` skill in `ask` mode", text)
        self.assertIn("--agent codex --model gpt-6-astra", text)
        for gate in ("context-sanitization", "read-only", "provider-independence",
                     "billing-consent", "failure-reporting"):
            self.assertIn(gate, text)
        self.assertNotIn("--agent claude", text)

    def test_quota_runs_both_read_only_helpers_and_isolates_failures(self):
        text = (PROMPTS / "quota.md").read_text()
        flat = " ".join(text.split())
        commands = re.findall(r"(?m)^    (\S.*)$", text)
        self.assertEqual(commands, ["codex-quota", "claude-quota"])
        for phrase in (
            "exactly these two read-only shell commands, as separate commands",
            "one provider's failure never hides or skips the other's report",
            "is not installed on PATH",
            "Null means unknown, never zero",
            "query any provider yourself, retry, sign in",
            "`windows`", "`usedPercent`", "`resetsAtText`", "`resetPassed`",
            "quota unavailable", "continue with the other provider",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat)

    def test_quota_keeps_standing_caveats_and_cost_note_in_documentation(self):
        text = (PROMPTS / "quota.md").read_text()
        flat = " ".join(text.split())
        self.assertIn("Do not print a caveats section or a model-turn reminder", flat)
        self.assertNotIn("every entry in `caveats`", text)
        self.assertNotIn("End with one line noting", text)
        self.assertIn("stale and its percentage is not current", flat)
        self.assertIn("one-row table with columns Window, Used, Remaining, Reset, and Time until reset", flat)
        self.assertIn("table with columns Window, Used, Reset, and Time until reset", flat)
        self.assertIn("One row per entry in `windows`", flat)
        docs = (PROMPTS / "README.md").read_text()
        for phrase in ("## Quota report notes", "model turn", "alignment", "undocumented",
                       "without a year", "not API dollars", "What's contributing"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, docs)

    def test_templates_and_catalog_rows_match(self):
        catalog = (PROMPTS / "README.md").read_text()
        listed = set(re.findall(r"\]\(([a-z0-9-]+\.md)\)", catalog))
        templates = sorted(path.name for path in PROMPTS.glob("*.md") if path.name != "README.md")
        self.assertEqual(sorted(listed), templates)
        for name in templates:
            with self.subTest(prompt=name):
                text = (PROMPTS / name).read_text()
                self.assertTrue(text.startswith("---\n"), "missing frontmatter")
                frontmatter = text.split("---", 2)[1]
                self.assertRegex(frontmatter, r"(?m)^description: \S", "missing description")
                self.assertIn(f"- [`/{name[:-3]}", catalog, "catalog row must name the command")


if __name__ == "__main__":
    unittest.main()
