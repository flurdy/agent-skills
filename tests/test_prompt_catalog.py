"""Every top-level prompt template has frontmatter and one catalog row, and vice versa."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"


class PromptCatalogTests(unittest.TestCase):
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
