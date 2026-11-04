"""Prescribed status cells must not rely on emoji/text variation selectors.

This checks instructions and fixed glyphs, not arbitrary PR titles or model compliance.
Actual Pi/xterm renderer comparison is a separate installed-runtime check.
"""

from pathlib import Path
import re
import unicodedata
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
EXPECTED = {
    "handoffs/SKILL.md": ("`pruned`", "`📦 safe`", "`🔶 keep?`"),
    "handoffs/REFERENCE.md": ("`pruned`", "`📦 safe`", "`🔶 keep?`"),
    "pr-review-requests/SKILL.md": ("🔶 Behind", "🔄 Stale approval", "🚫 Closed", "📝 Await author"),
    "landscape/SKILL.md": ("🔶 diverged",),
    "wrap-up/SKILL.md": ("🔶 diverged", "🚫 closed-unmerged"),
    "ready-to-merge/SKILL.md": ("✅ / 🔶 / —", "🔶 none"),
    "ready-to-release/SKILL.md": ("`⏳ hold`",),
}


class TableGlyphTests(unittest.TestCase):
    def test_literal_markdown_table_cells_have_no_variation_selectors(self):
        for path in SKILLS.rglob("*.md"):
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if line.lstrip().startswith("|"):
                    with self.subTest(path=str(path.relative_to(ROOT)), line=number):
                        self.assertNotRegex(line, "[\ufe0e\ufe0f]")

    def test_prescribed_cell_values_and_legends(self):
        for name, tokens in EXPECTED.items():
            text = (SKILLS / name).read_text()
            for token in tokens:
                with self.subTest(path=name, token=token):
                    self.assertIn(token, text)
            # Field instructions and inline table tokens are outside literal table rows.
            if name.startswith(("handoffs/", "pr-review-requests/")):
                for old in ("✂\ufe0f", "✂\ufe0e", "🗄\ufe0f", "☑\ufe0f", "✍\ufe0f", "🗑\ufe0f"):
                    self.assertNotIn(old, text)
            self.assertNotIn("⚠\ufe0f diverged", text)
        for name in ("handoffs/SKILL.md", "handoffs/REFERENCE.md"):
            self.assertIn("no U+FE0F/U+FE0E", (SKILLS / name).read_text())

    def test_generated_emoji_are_natively_wide(self):
        # Narrow ordinary text is valid; every symbol in these replacement tokens is W/F.
        for tokens in EXPECTED.values():
            for token in tokens:
                for char in token:
                    if unicodedata.category(char) == "So":
                        self.assertIn(unicodedata.east_asian_width(char), "WF", char)
                    self.assertNotIn(char, "\ufe0e\ufe0f")

    def test_headings_and_prose_can_keep_variation_selectors(self):
        text = (SKILLS / "handoffs/SKILL.md").read_text()
        self.assertRegex(text, r"(?m)^### .*🗂\ufe0f")
        # The old field prescription must not survive as an instruction to add VS16.
        for name in ("handoffs/SKILL.md", "handoffs/REFERENCE.md"):
            self.assertNotIn("including the variation selector", (SKILLS / name).read_text())

    def test_representative_cells_are_in_source_contracts(self):
        fixture = (ROOT / "tests/fixtures/table-glyphs.md").read_text()
        cells = [cell.strip() for line in fixture.splitlines()[2:] for cell in line.strip("|").split("|")]
        sources = "\n".join((SKILLS / name).read_text() for name in EXPECTED)
        for cell in cells:
            if cell != "—":
                self.assertIn(cell, sources)
        self.assertNotRegex(fixture, "[\ufe0e\ufe0f]")
        self.assertGreater(len(re.findall(r"^\|", fixture, re.M)), 5)


if __name__ == "__main__":
    unittest.main()
