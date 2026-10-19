"""Runtime workflow stays read-only and requires disclosure before text exposure."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


class ContractTests(unittest.TestCase):
    def test_skill_separates_summary_disclosure_emission_and_external_consent(self):
        skill = (ROOT / "SKILL.md").read_text()
        self.assertLess(skill.index("## 1. Collect metadata only"), skill.index("Before requesting any text"))
        self.assertLess(skill.index("Before requesting any text"), skill.index("## 2. Expose only"))
        for required in ("current session model", "fresh, explicit consent", "untrusted historical data",
                         "--expected-digest", "stale-summary", "never reread raw history", "$ARGUMENTS",
                         "never create", "Persist nothing by default", "ignored `.artifacts/`",
                         "separately approved follow-up", "real-history usefulness trial",
                         "directory-proxy count", "union", "already covered", "Codex is"):
            self.assertIn(required, skill)

    def test_helper_has_no_network_subprocess_or_file_output_interface(self):
        source = (ROOT / "scripts/prompt_patterns.py").read_text()
        tree = ast.parse(source)
        imports = {node.names[0].name.split(".")[0] if isinstance(node, ast.Import) else (node.module or "").split(".")[0]
                   for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))}
        self.assertFalse(imports & {"socket", "http", "urllib", "requests", "subprocess"})
        for sink in ("write_text", "write_bytes", "O_WRONLY", "O_RDWR", "O_CREAT", "--output", "--provider", "--model"):
            self.assertNotIn(sink, source)

    def test_catalogue_and_full_gate_include_the_new_skill(self):
        catalogue = (REPO / "skills/README.md").read_text()
        self.assertEqual(catalogue.count("| prompt-patterns |"), 1)
        makefile = (REPO / "Makefile").read_text()
        self.assertIn("test-prompt-patterns", makefile.split("test: $(TEST_TARGETS)")[0])
        self.assertIn("test-prompt-patterns:", makefile)


if __name__ == "__main__":
    unittest.main()
