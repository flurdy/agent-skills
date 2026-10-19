"""Metadata-only Claude fallback; synthetic docs and subprocesses, never inference."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("claude_discovery", SCRIPTS / "claude_discovery.py")
CLAUDE = importlib.util.module_from_spec(SPEC)
# Load in setUpModule so the missing implementation is an explicit red-phase error.

DOCS = """# Model configuration
### Model aliases
| Model alias | Behavior |
| - | - |
| **`sonnet`** | Latest Sonnet for the provider |
| **`opus`** | Latest Opus |
| **`fable`** | Provider-dependent Fable |
### Versions
Sonnet 9.1 requires Claude Code v2.1.500 or later, and Opus 9.2 requires v2.1.400 or later.
Use v2.1.450 or later with Haiku 9.1.
"""


def setUpModule():
    SPEC.loader.exec_module(CLAUDE)


class ClaudeDiscoveryTests(unittest.TestCase):
    def collect(self, status="ok", version="2.1.499 (Claude Code)\n", docs=DOCS, docs_status="ok"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "docs.md"
            path.write_text(docs)
            before = path.read_bytes()
            with patch.object(CLAUDE, "run_native", return_value=(status, version)) as native:
                result = CLAUDE.collect(path, docs_status)
            self.assertEqual(native.call_count, 1)
            self.assertEqual(native.call_args.args[0], ["claude", "--version"])
            self.assertLessEqual(native.call_args.kwargs["max_bytes"], 4096)
            self.assertEqual(before, path.read_bytes())
            return result

    def test_documented_fallback_is_not_native_inventory_or_access(self):
        result = self.collect()
        self.assertEqual(result["client"]["installedVersion"], "2.1.499")
        self.assertEqual(result["inventory"]["status"], "not-assessed")
        self.assertIn("supportedModels", result["inventory"]["supportedInterface"])
        self.assertEqual(result["accountAccess"], "unverified")
        self.assertEqual(result["billing"], "unverified")
        self.assertEqual(result["extensionCompatibility"], "unverified")
        docs = result["documentation"]
        self.assertEqual(docs["status"], "ok")
        self.assertEqual(docs["url"], CLAUDE.DOC_URL)
        self.assertEqual(len(docs["sha256"]), 64)
        self.assertTrue(docs["checkedAt"])
        self.assertEqual(docs["aliases"], ["sonnet", "opus", "fable"])
        self.assertNotIn("models", result["inventory"])

    def test_minimum_version_is_separate_from_model_availability(self):
        result = self.collect()
        self.assertEqual(CLAUDE.client_support("claude-sonnet-9-1", result)["status"], "minimum-version-mismatch")
        self.assertEqual(CLAUDE.client_support("claude-opus-9-2", result)["status"], "minimum-version-met")
        self.assertEqual(CLAUDE.client_support("claude-haiku-9-1", result)["status"], "minimum-version-met")
        self.assertEqual(CLAUDE.client_support("sonnet", result)["status"], "native-resolution")
        self.assertEqual(CLAUDE.client_support("claude-fable-9-1", result)["status"], "unverified")
        self.assertEqual(CLAUDE.client_support("claude-sonnet-9-1", self.collect(version="2.1.500 (Claude Code)"))["status"], "minimum-version-met")
        self.assertEqual(CLAUDE.client_support("claude-sonnet-9-1", self.collect(status="unavailable", version=""))["status"], "unverified")

    def test_missing_timeout_malformed_and_oversized_version_never_leak_output(self):
        for status in ("unavailable", "timeout", "failed", "output-limit"):
            with self.subTest(status=status):
                result = self.collect(status=status, version="credential-shaped-diagnostic")
                self.assertEqual(result["client"]["status"], status)
                self.assertIsNone(result["client"]["installedVersion"])
                self.assertNotIn("credential-shaped", json.dumps(result))
        for raw in ("bad-version secret-value", "2.1.499 (Claude Code)\nextra-output", "x" * 4097):
            result = self.collect(version=raw)
            self.assertEqual(result["client"]["status"], "invalid-version")
            self.assertIsNone(result["client"]["installedVersion"])
            self.assertNotIn(raw, json.dumps(result))

    def test_offline_failed_malformed_and_oversized_docs_are_not_empty_success(self):
        for status in ("skipped", "error", "missing-curl"):
            with self.subTest(status=status):
                result = self.collect(docs_status=status)
                self.assertEqual(result["documentation"]["status"], status)
                self.assertIsNone(result["documentation"]["sha256"])
                self.assertEqual(CLAUDE.client_support("claude-sonnet-9-1", result)["status"], "unverified")
        for raw in ("<html>unexpected page</html>", "x" * (CLAUDE.MAX_DOC_BYTES + 1)):
            self.assertNotEqual(self.collect(docs=raw)["documentation"]["status"], "ok")

    def test_partly_recognized_docs_do_not_validate_an_alias(self):
        for raw in (DOCS.split("### Versions")[0], "Sonnet 9.1 requires Claude Code v2.1.500 or later."):
            with self.subTest(raw=raw):
                result = self.collect(docs=raw)
                self.assertEqual(result["documentation"]["status"], "unrecognized-output")
                self.assertEqual(CLAUDE.client_support("sonnet", result)["status"], "unverified")

    def test_conflicting_minimum_versions_remain_unverified(self):
        result = self.collect(docs=DOCS + "\nSonnet 9.1 requires Claude Code v2.1.600 or later.\n")
        self.assertEqual(CLAUDE.client_support("claude-sonnet-9-1", result)["status"], "unverified")

    def test_native_stdout_is_bounded_while_reading(self):
        status, output = CLAUDE.run_native([sys.executable, "-c", "print('x' * 1000000)"], 2, max_bytes=1024)
        self.assertEqual((status, output), ("output-limit", ""))


if __name__ == "__main__":
    unittest.main()
