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
    def test_status_skills_use_narrow_api_wrappers(self):
        wrappers = {
            "circleci-status": ("status.sh", "logs.sh"),
            "pr-status": (
                "gh-pr-list-open.sh", "gh-pr-list-closed.sh", "gh-pr-details.sh",
                "gh-pr-feedback.py", "gh-pr-checks.sh", "gh-pr-reviews.sh",
                "gh-pr-threads.sh", "gh-pr-merge-state.sh",
            ),
        }
        for name, scripts in wrappers.items():
            with self.subTest(skill=name):
                text = skill(name)
                frontmatter = text.split("---", 2)[1]
                grants = re.search(r'^allowed-tools: "(.*)"$', frontmatter, re.M)
                self.assertIsNotNone(grants)
                permissions = {entry.strip() for entry in grants[1].split(",")}
                self.assertNotIn("Bash(gh api:*)", permissions)
                self.assertNotIn("Bash(gh:*)", permissions)
                for script in scripts:
                    self.assertIn(
                        f"Bash(~/.agents/skills/{name}/scripts/{script}:*)", permissions
                    )
                    self.assertTrue((ROOT / "skills" / name / "scripts" / script).is_file())

    def test_no_skill_executes_or_grants_raw_github_api(self):
        for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
            with self.subTest(skill=path.parent.name):
                text = path.read_text()
                frontmatter = text.split("---", 2)[1]
                self.assertNotIn("Bash(gh api:", frontmatter)
                self.assertNotIn("Bash(gh:*)", frontmatter)
                for block in re.findall(r"```(?:bash|sh)\n(.*?)```", text, re.S):
                    self.assertIsNone(re.search(r"^\s*gh\s+api\b", block, re.M))

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
        for name in ("start-ticket", "create-pr", "stack-branch", "breakdown"):
            with self.subTest(name=name):
                text = skill(name)
                self.assertIn("../jira-ticket/SKILL.md", text)
                self.assertNotIn("mcp__jira__", text)
                self.assertNotIn("Jira MCP tools directly", text)

    def test_audit_planning_and_capture_routing(self):
        economy = {"pickup", "thoughtbox", "today"}
        names = (
            "contract-check", "eas-build-error", "model-update-check", "pickup",
            "plan-day", "second-opinion", "skills-review", "thoughtbox",
            "today", "trello-beads",
        )
        for name in names:
            with self.subTest(name=name):
                front = skill(name).split("---", 2)[1]
                tier = "economy" if name in economy else "standard"
                effort = "medium" if name == "eas-build-error" else "high"
                self.assertRegex(front, rf"(?m)^model-tier: {tier}$")
                self.assertRegex(front, r"(?m)^model: sonnet$")
                self.assertRegex(front, rf"(?m)^effort: {effort}$")

    def test_finalisation_and_git_routing(self):
        economy = {"artifact-hygiene", "stack-branch"}
        names = (
            "artifact-hygiene", "clean-code", "complete-task", "create-pr",
            "ready-to-merge", "reply-comments", "setup-multirepo-git",
            "stack-branch", "workspace-sync", "wrap-up",
        )
        for name in names:
            with self.subTest(name=name):
                front = skill(name).split("---", 2)[1]
                tier = "economy" if name in economy else "standard"
                self.assertRegex(front, rf"(?m)^model-tier: {tier}$")
                self.assertRegex(front, r"(?m)^model: sonnet$")
                self.assertRegex(front, r"(?m)^effort: high$")

    def test_watch_and_release_routing(self):
        expected = {
            "watch-prs": ("standard", "medium"),
            "watch-release": ("standard", "medium"),
            "watch-actions-rollout": ("standard", "high"),
            "watch-flux-rollout": ("standard", "high"),
            "pr-status": ("standard", "high"),
            "release-manager": ("standard", "high"),
            "release-status": ("standard", "medium"),
            "ready-to-release": ("economy", "high"),
            "outstanding-work": ("standard", "high"),
            "tracking-sweep": ("standard", "high"),
        }
        for name, (tier, effort) in expected.items():
            with self.subTest(name=name):
                front = skill(name).split("---", 2)[1]
                self.assertRegex(front, rf"(?m)^model-tier: {tier}$")
                self.assertRegex(front, r"(?m)^model: sonnet$")
                self.assertRegex(front, rf"(?m)^effort: {effort}$")

    def test_dashboard_and_handoff_routing(self):
        expected = {
            "jira-comment": ("economy", "sonnet", "medium"),
            "pr-review-requests": ("standard", "sonnet", "high"),
            "pr-reviewers": ("economy", "haiku", "medium"),
            "watch-review-requests": ("standard", "sonnet", "medium"),
            "watch-rollout": ("economy", "haiku", "medium"),
            "watch-telemetry": ("economy", "haiku", "medium"),
            "handoffs-tidy": ("standard", "sonnet", "medium"),
            "name-session": ("economy", "haiku", "low"),
            "handoffs": ("standard", "sonnet", "high"),
            "landscape": ("standard", "sonnet", "high"),
        }
        for name, settings in expected.items():
            with self.subTest(name=name):
                front = skill(name).split("---", 2)[1]
                for field, value in zip(("model-tier", "model", "effort"), settings, strict=True):
                    self.assertRegex(front, rf"(?m)^{field}: {value}$")

    def test_economy_effort_matches_workflow_decisions(self):
        high_effort = {"beads", "beads-check-dolt-migration", "next", "start-ticket"}
        names = (
            "beads", "beads-check-dolt-migration", "browser-screenshot",
            "circleci-status", "confluence", "jira-ticket", "next",
            "pi-spend", "start-ticket", "token-dashboard",
        )
        for name in names:
            with self.subTest(name=name):
                front = skill(name).split("---", 2)[1]
                effort = "high" if name in high_effort else "medium"
                self.assertRegex(front, r"(?m)^model-tier: economy$")
                if name == "next":
                    self.assertNotRegex(front, r"(?m)^model:")
                else:
                    self.assertRegex(front, r"(?m)^model: haiku$")
                self.assertRegex(front, rf"(?m)^effort: {effort}$")

    def test_claude_model_hints_preserve_coding_layers(self):
        expected = {
            "breakdown": ("sonnet", "medium"),
            "dependabot-remediation": ("sonnet", "high"),
            "develop": (None, "high"),
            "do-i-need-this": ("sonnet", "high"),
            "image-studio": ("sonnet", "high"),
            "pair-programming": (None, "high"),
            "peer-session": ("sonnet", "high"),
            "reassess": ("sonnet", "high"),
            "refine": ("opus", "high"),
            "sanity-check": ("sonnet", "high"),
        }
        for name, (model, effort) in expected.items():
            with self.subTest(name=name):
                front = skill(name).split("---", 2)[1]
                self.assertRegex(front, r"(?m)^model-tier: standard$")
                self.assertRegex(front, rf"(?m)^effort: {effort}$")
                if model is None:
                    self.assertNotRegex(front, r"(?m)^model:")
                else:
                    self.assertRegex(front, rf"(?m)^model: {model}$")
        self.assertNotIn("no `model:` pin on purpose", skill("image-studio"))

    def test_breakdown_keeps_a_read_only_overview_contract(self):
        text = skill("breakdown")
        metadata = text.split("---", 2)[1]
        self.assertIn("model-tier: standard", metadata)
        self.assertIn("effort: medium", metadata)
        for tool in ("Write", "Edit", "Bash(make", "Bash(bd", "Skill(architect)", "Skill(triage)", "Skill(plan-to-backlog)"):
            self.assertNotIn(tool, metadata)
        headings = ("### Problem", "### Solution", "### Steps", "### Open questions")
        positions = [text.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        for term in (
            "**description**", "user-provided, not fetched verification",
            "untrusted data", "do not edit files", "Do not run tests",
            "do not execute them or claim their results", "Implementation requires a separate request",
            "../architect/SKILL.md#when-to-use", "../triage/SKILL.md", "../plan-to-backlog/SKILL.md",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_start_ticket_suggests_breakdown_only_after_success(self):
        text = skill("start-ticket")
        confirm = text.split("### 6. Confirm to User", 1)[1]
        self.assertIn("../breakdown/SKILL.md", confirm)
        self.assertIn("/skill:breakdown {TICKET-NUMBER}", confirm)
        self.assertIn("Do not invoke it automatically", confirm)
        self.assertIn("Skip this suggestion on a handoff-resume path, an abort, or any stop/error path", confirm)

    def test_browser_screenshot_needs_no_project_link(self):
        text = skill("browser-screenshot")
        front = text.split("---", 2)[1]
        grants = {entry.strip() for entry in re.search(r'^allowed-tools: "(.*)"$', front, re.M)[1].split(",")}
        self.assertIn("Bash(~/.agents/skills/browser-screenshot/scripts/screenshot.sh:*)", grants)
        for stale in ("Bash(ln:*)", "Bash(npm:*)", "Bash(npx:*)", "Bash(scripts/screenshot:*)"):
            self.assertNotIn(stale, grants)
        for block in re.findall(r"```bash\n(.*?)```", text, re.S):
            self.assertNotIn("ln -s", block)
            self.assertIsNone(re.search(r"^\s*scripts/screenshot\b", block, re.M))
        for term in ("-C", "not verified", "Pi", "Codex", "Never install"):
            self.assertIn(term, text)
        self.assertFalse((ROOT / "skills/browser-screenshot/scripts/screenshot.mjs").exists())


FAKE_PLAYWRIGHT = """
import { writeFileSync } from 'fs';
export const chromium = {
  async launch() {
    return {
      async newContext({ viewport }) {
        return { async newPage() {
          let target;
          return {
            async goto(url) { target = url; },
            async screenshot({ path }) { writeFileSync(path, JSON.stringify({ url: target, viewport })); },
          };
        } };
      },
      async close() {},
    };
  },
};
"""


class ScreenshotHelperTests(unittest.TestCase):
    SCRIPT = ROOT / "skills/browser-screenshot/scripts/screenshot.sh"

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="screenshot project ")
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name)
        self.app = self.project / "web app"
        package = self.app / "node_modules/playwright"
        package.mkdir(parents=True)
        (package / "package.json").write_text('{"name":"playwright","type":"module","exports":"./index.js"}')
        (package / "index.js").write_text(FAKE_PLAYWRIGHT)
        self.tmp = self.project / "tmp"
        self.tmp.mkdir()

    def run_helper(self, *args, cwd=None):
        env = {"PATH": os.environ["PATH"], "HOME": str(self.project), "TMPDIR": str(self.tmp)}
        return subprocess.run([str(self.SCRIPT), *args], cwd=cwd or self.project, env=env,
                              text=True, capture_output=True, timeout=30)

    def project_files(self):
        return sorted(str(p.relative_to(self.project)) for p in self.project.rglob("*") if self.tmp not in p.parents)

    def test_dependency_directory_option_resolves_nested_install_without_project_writes(self):
        before = self.project_files()
        result = self.run_helper("-C", str(self.app), "http://localhost:5173/a b", "mobile")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = Path(result.stdout.strip())
        self.assertEqual(output.parent.parent, self.tmp)
        self.assertEqual(stat_mode(output.parent), 0o700)
        self.assertEqual(output.name, "screenshot-mobile.png")
        self.assertIn('"width":375', output.read_text())
        self.assertIn("localhost:5173/a b", output.read_text())
        self.assertEqual(before, self.project_files())

    def test_parent_install_resolves_from_nested_cwd(self):
        nested = self.app / "src"
        nested.mkdir()
        result = self.run_helper("http://localhost:3000", "800x600", cwd=nested)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"width":800', Path(result.stdout.strip()).read_text())

    def test_relative_output_stays_relative_to_invocation_cwd(self):
        result = self.run_helper("-C", "web app", "http://localhost:3000", "desktop", "shot one.png")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), self.project / "shot one.png")
        self.assertTrue((self.project / "shot one.png").is_file())

    def test_missing_playwright_is_diagnosed_without_install(self):
        before = self.project_files()
        result = self.run_helper("http://localhost:3000")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Playwright is not resolvable from", result.stderr)
        self.assertIn(str(self.project), result.stderr)
        self.assertIn("-C", result.stderr)
        self.assertEqual(before, self.project_files())
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_invalid_dependency_directory_fails_before_capture(self):
        for args in (("-C",), ("-C", str(self.project / "absent"))):
            with self.subTest(args=args):
                result = self.run_helper(*args, "http://localhost:3000")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("-C", result.stderr)
                self.assertEqual(list(self.tmp.iterdir()), [])


def stat_mode(path):
    return path.stat().st_mode & 0o777


class AuthoringGuidance(unittest.TestCase):
    def test_native_gate_and_authoring_guidance(self):
        self.assertIn("test-portability", (ROOT / "Makefile").read_text())
        text = (ROOT / "CONTRIBUTING.md").read_text()
        self.assertIn("explicit override", text)
        self.assertIn("ToolSearch", text)


if __name__ == "__main__":
    unittest.main()
