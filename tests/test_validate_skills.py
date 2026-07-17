#!/usr/bin/env python3
"""Fixture tests for scripts/validate-skills.py."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

VALID_SKILL = """---
name: alpha
description: A valid fixture skill.
allowed-tools: "Read,Bash(~/.claude/skills/alpha/scripts/check.sh:*)"
model-tier: standard-workflow
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
model: sonnet
effort: medium
version: "1.0.0"
author: tester
---

# Alpha

See [reference](REFERENCE.md).
"""

VALID_README = """# Shared Skills

| Skill | Description |
|-------|-------------|
| alpha | A valid fixture skill |

## Model routing

| Skill | Tier | Cost policy | Metered policy | `model:` pin | Effort | Tier guard |
|-------|------|-------------|----------------|--------------|--------|------------|
| alpha | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
"""


VALIDATOR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate-skills.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_skills", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator()


class ValidateSkillsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        skill = self.root / "skills" / "alpha"
        (skill / "scripts").mkdir(parents=True)
        (skill / "SKILL.md").write_text(VALID_SKILL, encoding="utf-8")
        (skill / "REFERENCE.md").write_text("# Reference\n", encoding="utf-8")
        (skill / "scripts" / "check.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (self.root / "skills" / "README.md").write_text(VALID_README, encoding="utf-8")

    def errors(self) -> list[str]:
        return VALIDATOR.validate(self.root)

    def assert_error_contains(self, expected: str) -> None:
        errors = self.errors()
        self.assertTrue(
            any(expected in error for error in errors),
            f"expected {expected!r} in errors:\n" + "\n".join(errors),
        )

    def test_valid_catalog_passes(self) -> None:
        self.assertEqual([], self.errors())

    def test_cli_returns_nonzero_for_invalid_catalog(self) -> None:
        path = self.root / "skills" / "alpha" / "SKILL.md"
        path.write_text(VALID_SKILL.replace("author: tester\n", ""), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH), "--root", str(self.root)],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("missing required frontmatter field 'author'", result.stderr)

    def test_missing_required_metadata_fails(self) -> None:
        path = self.root / "skills" / "alpha" / "SKILL.md"
        path.write_text(VALID_SKILL.replace("author: tester\n", ""), encoding="utf-8")
        self.assert_error_contains("missing required frontmatter field 'author'")

    def test_frontmatter_name_must_match_directory(self) -> None:
        path = self.root / "skills" / "alpha" / "SKILL.md"
        path.write_text(VALID_SKILL.replace("name: alpha", "name: beta"), encoding="utf-8")
        self.assert_error_contains("does not match directory 'alpha'")

    def test_missing_catalog_row_fails(self) -> None:
        readme = self.root / "skills" / "README.md"
        readme.write_text(VALID_README.replace(
            "| alpha | A valid fixture skill |\n", ""
        ), encoding="utf-8")
        self.assert_error_contains("has 0 description rows; expected exactly 1")

    def test_routing_catalog_must_match_frontmatter(self) -> None:
        readme = self.root / "skills" / "README.md"
        readme.write_text(
            VALID_README.replace("| alpha | standard-workflow", "| alpha | cheap-bulk"),
            encoding="utf-8",
        )
        self.assert_error_contains("alpha tier is 'cheap-bulk'")

    def test_broken_relative_markdown_reference_fails(self) -> None:
        path = self.root / "skills" / "alpha" / "SKILL.md"
        path.write_text(
            VALID_SKILL.replace("REFERENCE.md", "MISSING.md"), encoding="utf-8"
        )
        self.assert_error_contains("broken relative link: MISSING.md")

    def test_balanced_parentheses_in_link_destination_pass(self) -> None:
        path = self.root / "skills" / "alpha" / "SKILL.md"
        (path.parent / "REFERENCE_(v2).md").write_text("# Reference\n", encoding="utf-8")
        path.write_text(
            VALID_SKILL.replace("REFERENCE.md", "REFERENCE_(v2).md"), encoding="utf-8"
        )
        self.assertEqual([], self.errors())

    def test_angle_bracket_link_with_spaces_passes(self) -> None:
        path = self.root / "skills" / "alpha" / "SKILL.md"
        (path.parent / "REFERENCE FILE.md").write_text("# Reference\n", encoding="utf-8")
        path.write_text(
            VALID_SKILL.replace("REFERENCE.md", "<REFERENCE FILE.md>"),
            encoding="utf-8",
        )
        self.assertEqual([], self.errors())

    def test_broken_reference_style_markdown_link_fails(self) -> None:
        path = self.root / "skills" / "alpha" / "SKILL.md"
        path.write_text(
            VALID_SKILL.replace(
                "See [reference](REFERENCE.md).",
                "See [missing][ref].\n\n[ref]: MISSING.md",
            ),
            encoding="utf-8",
        )
        self.assert_error_contains("broken relative link: MISSING.md")

    def test_missing_allowed_tools_script_fails(self) -> None:
        (self.root / "skills" / "alpha" / "scripts" / "check.sh").unlink()
        self.assert_error_contains(
            "allowed-tools references missing local file skills/alpha/scripts/check.sh"
        )

    def test_allowed_tools_glob_must_match_a_file(self) -> None:
        path = self.root / "skills" / "alpha" / "SKILL.md"
        path.write_text(
            VALID_SKILL.replace("scripts/check.sh", "scripts/missing*.sh"),
            encoding="utf-8",
        )
        self.assert_error_contains(
            "allowed-tools references missing local file skills/alpha/scripts/missing*.sh"
        )

    def test_allowed_tools_glob_can_match_existing_files(self) -> None:
        path = self.root / "skills" / "alpha" / "SKILL.md"
        path.write_text(
            VALID_SKILL.replace("scripts/check.sh", "scripts/*.sh"), encoding="utf-8"
        )
        self.assertEqual([], self.errors())

    def test_allowed_tools_rejects_directories(self) -> None:
        path = self.root / "skills" / "alpha" / "SKILL.md"
        path.write_text(
            VALID_SKILL.replace("scripts/check.sh", "scripts"), encoding="utf-8"
        )
        self.assert_error_contains(
            "allowed-tools references missing local file skills/alpha/scripts"
        )

    def test_allowed_tools_cannot_escape_skill_directory(self) -> None:
        (self.root / "outside.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        path = self.root / "skills" / "alpha" / "SKILL.md"
        path.write_text(
            VALID_SKILL.replace("scripts/check.sh", "../../outside.sh"),
            encoding="utf-8",
        )
        self.assert_error_contains("allowed-tools path escapes skill directory")

    def test_allowed_tools_rejects_symlinked_external_skill_directory(self) -> None:
        external = self.root / "external"
        (external / "scripts").mkdir(parents=True)
        (external / "scripts" / "check.sh").write_text(
            "#!/usr/bin/env bash\n", encoding="utf-8"
        )
        (self.root / "skills" / "linked").symlink_to(external, target_is_directory=True)
        path = self.root / "skills" / "alpha" / "SKILL.md"
        path.write_text(
            VALID_SKILL.replace("skills/alpha", "skills/linked"), encoding="utf-8"
        )
        self.assert_error_contains(
            "allowed-tools skill directory resolves outside repository skills/linked"
        )

    def test_headingless_table_after_blank_is_not_catalog_data(self) -> None:
        readme = self.root / "skills" / "README.md"
        unrelated = """
| Setting | Value |
|---------|-------|
| example | enabled |

"""
        readme.write_text(
            VALID_README.replace("## Model routing", unrelated + "## Model routing"),
            encoding="utf-8",
        )
        self.assertEqual([], self.errors())

    def test_lookalike_routing_header_is_not_catalog_data(self) -> None:
        readme = self.root / "skills" / "README.md"
        unrelated = """
| Skill | Tier | Cost policy | Metered policy | Extra | Notes |
|-------|------|-------------|----------------|-------|-------|
| bogus | cheap | none | none | value | note |

"""
        readme.write_text(
            VALID_README.replace("## Model routing", unrelated + "## Model routing"),
            encoding="utf-8",
        )
        self.assertEqual([], self.errors())

    def test_unrelated_markdown_table_is_not_catalog_data(self) -> None:
        readme = self.root / "skills" / "README.md"
        unrelated = """
## Settings

| Setting | Value |
|---------|-------|
| example | enabled |

"""
        readme.write_text(
            VALID_README.replace("## Model routing", unrelated + "## Model routing"),
            encoding="utf-8",
        )
        self.assertEqual([], self.errors())

    def test_archived_skill_cannot_remain_active(self) -> None:
        path = self.root / "skills" / "alpha" / "SKILL.md"
        path.write_text(
            VALID_SKILL.replace("author: tester", "author: tester\nstatus: archived"),
            encoding="utf-8",
        )
        self.assert_error_contains("archived/deprecated skill is present")


if __name__ == "__main__":
    unittest.main()
