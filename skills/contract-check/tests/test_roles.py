from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
AUDIT = ROOT / "skills/contract-check/SKILL.md"
RUNNER = ROOT / "skills/contract-test/SKILL.md"
SETUP = ROOT / "skills/contract-check/references/project-setup.md"


class RoleContracts(unittest.TestCase):
    def test_audit_has_only_read_permissions_and_never_bootstraps(self):
        text = AUDIT.read_text()
        frontmatter = text.split("---", 2)[1]
        self.assertIn("Bash(~/.agents/skills/contract-check/scripts/contract-check.sh:*)", frontmatter)
        for forbidden in ("AskUserQuestion", "Skill", "Bash(./scripts/mgit:*)", "chmod", "ln -s", "Ensure Setup", "Offer Remediation"):
            self.assertNotIn(forbidden, text)
        self.assertIn("Do not normalize", text)
        self.assertIn("references/project-setup.md", text)
        self.assertIn("UNKNOWN", text)

    def test_runner_status_delegates_instead_of_collecting(self):
        text = RUNNER.read_text()
        self.assertIn("Skill(contract-check)", text.split("---", 2)[1])
        section = text.split("## Status compatibility alias", 1)[1].split("\n## ", 1)[0]
        self.assertIn("/contract-check status", section)
        self.assertIn("missing", section)
        self.assertIn("stop", section)
        self.assertNotIn("last-modified", section)
        self.assertNotIn("find ", section)

    def test_runner_executes_only_requested_phases_and_preserves_scope(self):
        text = RUNNER.read_text()
        for required in ("consumer stops after generation", "sync stops after copying", "ALL selected consumers", "before sync", "/contract-check uncommitted", "Do not broaden", "inspect", "normalization"):
            self.assertIn(required, text)
        for obsolete in ("ALWAYS sync", "ALWAYS normalize", "Adapting to a New Project", "npm test -- --grep contract", "cp target/pacts/*", "-mmin -5"):
            self.assertNotIn(obsolete, text)
        self.assertIn("references/project-setup.md", text)

    def test_setup_is_separately_authorized_and_documents_supported_evidence(self):
        text = SETUP.read_text()
        for required in ("separate setup request", "confirm", "never overwrite", "scripts/pact-pairs", "intended", "built", "synced", "TSV", "scripts/contract-check", "release", ".circleci/config.yml", "static", "GitHub Actions", "unsupported", "status=error"):
            self.assertIn(required, text)
        self.assertNotIn("ln -sfn", text)
        self.assertNotIn("chmod +x", text)

    def test_helper_diagnostics_do_not_invent_execution_commands(self):
        text = (ROOT / "skills/contract-check/scripts/contract-check.sh").read_text()
        self.assertNotIn("make test-contract", text)
        self.assertNotIn("run scripts/sync-pacts.sh", text)
        self.assertIn("/contract-test", text)

    def test_native_gate_includes_both_contract_suites(self):
        text = (ROOT / "Makefile").read_text()
        self.assertIn("test-contract-check:", text)
        targets = text.split("TEST_TARGETS :=", 1)[1].split("\ntest:", 1)[0]
        self.assertIn("test-contract-check", targets)
        self.assertIn("skills/contract-check/tests", text)


if __name__ == "__main__":
    unittest.main()
