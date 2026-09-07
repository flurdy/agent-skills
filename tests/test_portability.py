"""Execute documented resource selection; check scoped workflow contracts, not live MCP."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SETUPS = {
    "setup-multirepo-git": ["scripts/mgit", "templates/permissions.json", "templates/AGENTS-MGIT.md"],
    "trello-beads": ["scripts/trello-api.sh", "scripts/trello-pull.sh", "scripts/trello-sync.sh", "scripts/owning-store.sh"],
    "browser-screenshot": ["scripts/screenshot.sh"],
}


def skill(name):
    return (ROOT / "skills" / name / "SKILL.md").read_text()


class ResourceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="portable resources ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def install(self, root, name):
        for relative in ["SKILL.md", *SETUPS[name]]:
            path = root / name / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n")
            path.chmod(0o755 if relative.startswith("scripts/") else 0o644)
        return root

    def resolve(self, name, **overrides):
        blocks = [block for block in re.findall(r"```bash\n(.*?)```", skill(name), re.S) if "SKILLS_DIR=" in block]
        self.assertTrue(blocks)
        # Legacy examples bundled linking with discovery. Execute only selection,
        # never their mkdir/ln/cat commands; new examples isolate this read-only block.
        lines = blocks[0].splitlines()
        start = next(i for i, line in enumerate(lines) if "SKILLS_DIR=" in line or line.startswith("set -e"))
        end = next((i for i in range(start, len(lines)) if lines[i].startswith(("ln ", "cat "))), len(lines))
        script = "\n".join(lines[start:end]) + '\nprintf "RESOLVED=%s\\n" "$SKILLS_DIR"\n'
        env = {key: value for key, value in os.environ.items() if key not in {"SKILLS_DIR", "CLAUDE_HOME", "CLAUDE_SKILLS_DIR", "CODEX_HOME", "BASH_ENV"}}
        env.update(HOME=str(self.home), **overrides)
        return subprocess.run(["bash", "-c", script], cwd=self.home, env=env, text=True, capture_output=True, timeout=5)

    def test_canonical_wins_over_legacy_roots(self):
        for name in SETUPS:
            with self.subTest(name=name):
                canonical = self.install(self.home / ".agents/skills", name)
                self.install(self.home / ".codex/skills", name)
                self.install(self.home / ".claude/skills", name)
                result = self.resolve(name)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), f"RESOLVED={canonical}")

    def test_claude_fallback_checks_unit_not_root(self):
        (self.home / ".agents/skills").mkdir(parents=True)
        (self.home / ".codex/skills").mkdir(parents=True)
        for name in SETUPS:
            with self.subTest(name=name):
                fallback = self.install(self.home / "claude home/skills", name)
                result = self.resolve(name, CLAUDE_HOME=str(self.home / "claude home"))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), f"RESOLVED={fallback}")

    def test_explicit_root_with_spaces_is_authoritative(self):
        for name in SETUPS:
            with self.subTest(name=name):
                explicit = self.install(self.home / "chosen skills", name)
                self.install(self.home / ".agents/skills", name)
                result = self.resolve(name, SKILLS_DIR=str(explicit))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), f"RESOLVED={explicit}")

    def test_invalid_override_never_falls_back(self):
        for name in SETUPS:
            self.install(self.home / ".agents/skills", name)
            self.install(self.home / ".claude/skills", name)
            for override in (str(self.home / "absent"), "relative"):
                with self.subTest(name=name, override=override):
                    result = self.resolve(name, SKILLS_DIR=override)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("RESOLVED=", result.stdout)

    def test_missing_resources_stop_even_when_root_exists(self):
        for name in SETUPS:
            with self.subTest(name=name):
                root = self.install(self.home / "incomplete", name)
                (root / name / SETUPS[name][0]).unlink()
                result = self.resolve(name, SKILLS_DIR=str(root))
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("RESOLVED=", result.stdout)

    def test_partial_canonical_unit_does_not_mix_with_fallback(self):
        for name in SETUPS:
            with self.subTest(name=name):
                canonical = self.install(self.home / ".agents/skills", name)
                self.install(self.home / ".claude/skills", name)
                (canonical / name / SETUPS[name][-1]).unlink()
                result = self.resolve(name)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("RESOLVED=", result.stdout)

    def test_missing_executable_bit_stops_setup(self):
        for name in SETUPS:
            with self.subTest(name=name):
                root = self.install(self.home / ".agents/skills", name)
                (root / name / SETUPS[name][0]).chmod(0o644)
                result = self.resolve(name)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("RESOLVED=", result.stdout)

    def test_broken_claude_alias_stops_without_linking(self):
        fallback = self.home / ".claude/skills"
        fallback.mkdir(parents=True)
        for name in SETUPS:
            with self.subTest(name=name):
                (fallback / name).symlink_to(self.home / "missing source")
                result = self.resolve(name)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("RESOLVED=", result.stdout)
                self.assertFalse((self.home / "scripts").exists())

    def test_claude_skills_override_and_explicit_legacy_root(self):
        for name in SETUPS:
            with self.subTest(name=name):
                fallback = self.install(self.home / "custom aliases", name)
                result = self.resolve(name, CLAUDE_SKILLS_DIR=str(fallback))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), f"RESOLVED={fallback}")
                legacy = self.install(self.home / ".codex/skills", name)
                result = self.resolve(name, SKILLS_DIR=str(legacy))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), f"RESOLVED={legacy}")

    def test_existing_link_destinations_stop_before_any_project_write(self):
        destinations = {
            "setup-multirepo-git": ["mgit"],
            "trello-beads": ["trello-api", "trello-pull", "trello-sync"],
            "browser-screenshot": ["screenshot"],
        }
        for name, targets in destinations.items():
            root = self.install(self.home / ".agents/skills", name)
            block, = [block for block in re.findall(r"```bash\n(.*?)```", skill(name), re.S) if "ln -s " in block]
            for target in targets:
                for kind in ("file", "directory", "dangling-link"):
                    with self.subTest(name=name, target=target, kind=kind):
                        project = self.home / f"{name}-{target}-{kind}"
                        scripts = project / "scripts"
                        scripts.mkdir(parents=True)
                        existing = scripts / target
                        if kind == "directory":
                            existing.mkdir()
                        elif kind == "dangling-link":
                            existing.symlink_to("absent")
                        else:
                            existing.write_text("owned\n")
                        before = sorted(str(p.relative_to(project)) for p in project.rglob("*"))
                        result = subprocess.run(
                            ["bash", "-c", "set -eu\n" + block], cwd=project,
                            env={"PATH": os.environ["PATH"], "HOME": str(self.home), "SKILLS_DIR": str(root)},
                            text=True, capture_output=True, timeout=5,
                        )
                        self.assertNotEqual(result.returncode, 0)
                        self.assertEqual(before, sorted(str(p.relative_to(project)) for p in project.rglob("*")))
                        if kind == "file":
                            self.assertEqual(existing.read_text(), "owned\n")
                        elif kind == "dangling-link":
                            self.assertEqual(os.readlink(existing), "absent")

    def test_no_install_does_not_create_any_files(self):
        for name in SETUPS:
            with self.subTest(name=name):
                result = self.resolve(name)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("RESOLVED=", result.stdout)
                self.assertEqual(list(self.home.iterdir()), [])


class WorkflowContracts(unittest.TestCase):
    def test_canonical_contract_audit_remains_read_only(self):
        text = skill("contract-check")
        self.assertIn("~/.agents/skills/contract-check/scripts/contract-check.sh", text)
        self.assertNotIn("SKILLS_DIR=", text)
        self.assertNotIn("ln -s", text)

    def test_permission_template_is_explicitly_claude_only(self):
        text = skill("setup-multirepo-git")
        for term in ("Claude Code", "Codex", "Pi", "permissions.json", "add", "commit", "stash", "not read-only"):
            self.assertIn(term, text)
        self.assertNotIn("agent-specific local settings file", text)
        self.assertIn("Claude Code", (ROOT / "skills/setup-multirepo-git/templates/AGENTS-MGIT.md").read_text())

    def test_atlassian_owners_have_conditional_discovery_and_safe_handoff(self):
        for name in ("jira-ticket", "jira-comment", "confluence"):
            with self.subTest(name=name):
                text = skill(name)
                self.assertIn("ToolSearch", text.split("---", 2)[1])
                for term in ("schema", "unavailable for this run", "paste", "untrusted", "does not prove", "if exposed"):
                    self.assertIn(term, text)
                self.assertNotIn("mcp__jira__*", text.split("---", 2)[1])
                self.assertNotIn("mcp__confluence__*", text.split("---", 2)[1])
                self.assertNotIn("copy it across", text)
        self.assertNotIn("only the tool name changes", skill("confluence"))
        self.assertIn("do not retry", skill("jira-comment"))

    def test_confluence_does_not_assume_response_filter_language(self):
        self.assertNotIn("jq:", skill("confluence"))

    def test_ticket_consumers_delegate_instead_of_duplicating_discovery(self):
        for name in ("start-ticket", "create-pr", "stack-branch"):
            with self.subTest(name=name):
                text = skill(name)
                self.assertIn("../jira-ticket/SKILL.md", text)
                self.assertNotIn("mcp__jira__", text)
                self.assertNotIn("Jira MCP tools directly", text)

    def test_native_gate_and_authoring_guidance(self):
        self.assertIn("test-portability", (ROOT / "Makefile").read_text())
        text = (ROOT / "CONTRIBUTING.md").read_text()
        self.assertIn("explicit override", text)
        self.assertIn("ToolSearch", text)


if __name__ == "__main__":
    unittest.main()
