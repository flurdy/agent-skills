"""Ties second-opinion's Claude-style allowed-tools grants to its documented invocations."""
import re
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL = SKILL_DIR / "SKILL.md"
PERMISSIONS = SKILL_DIR / "references/permissions.md"
HELPERS = "~/.agents/skills/second-opinion/scripts"

EXPECTED = {
    "Read",
    "Grep",
    "Glob",
    "AskUserQuestion",
    "Edit(//tmp/**/second-opinion.*/**)",
    "Bash(claude -p * --tools Read,Grep,Glob)",
    "Bash(codex exec --sandbox read-only *)",
    "Bash(gemini --sandbox -o text *)",
    "Bash(git ls-files:*)",
    f"Bash({HELPERS}/subscription-route-check.py:*)",
    f"Bash({HELPERS}/disabled-models.py:*)",
    f"Bash({HELPERS}/review-panel.sh:*)",
    "Bash(~/.agents/skills/review-pr/scripts/gh-pr-snapshot.py:*)",
}


def split_grants(value):
    """Split on commas outside parentheses, as rules such as --tools Read,Grep,Glob contain commas."""
    entries, current, depth = [], "", 0
    for character in value:
        if character == "," and depth == 0:
            entries.append(current)
            current = ""
            continue
        depth += {"(": 1, ")": -1}.get(character, 0)
        current += character
    return [*entries, current]


def grants():
    front = SKILL.read_text().split("---", 2)[1]
    return split_grants(re.search(r'^allowed-tools: "(.*)"$', front, re.M).group(1))


def bash_rule_pattern(rule):
    """Claude Code Bash rule text: `*` spans any text, a trailing `:*` also matches the bare command."""
    if rule.endswith(":*"):
        return re.compile(re.escape(rule[:-2]) + r"(?: .*)?")
    return re.compile(".*".join(re.escape(part) for part in rule.split("*")))


def documented_commands():
    """Commands in fenced shell blocks and inline code of the operational docs, split at pipes."""
    sources = [SKILL, *sorted(path for path in (SKILL_DIR / "references").glob("*.md") if path != PERMISSIONS)]
    commands = set()
    for path in sources:
        body = path.read_text()
        if path == SKILL:
            body = body.split("---", 2)[2]
        lines = [line for block in re.findall(r"```(?:bash|sh)\n(.*?)```", body, re.S) for line in block.splitlines()]
        lines += re.findall(r"`([^`\n]+)`", body)
        for line in lines:
            commands.update(part.strip() for part in line.rstrip(" \\").split(" | "))
    return commands


def gitignore_pattern(rule):
    path = rule[len("Edit(//"):-1]
    expression = re.escape("/" + path).replace(r"/\*\*/", "/(?:.*/)?").replace(r"/\*\*", "/.*")
    return re.compile(expression.replace(r"\*", "[^/]*"))


class PermissionContractTests(unittest.TestCase):
    def test_grants_are_the_reviewed_minimal_set(self):
        actual = grants()
        self.assertEqual(len(actual), len(set(actual)), "duplicate grant")
        self.assertEqual(set(actual), EXPECTED)

    def test_no_broad_write_destructive_or_agent_preapproval(self):
        for grant in grants():
            with self.subTest(grant=grant):
                self.assertNotIn(grant, {"Write", "Edit", "Bash"})
                self.assertNotRegex(grant, r"^Bash\((?:rm|chmod|mktemp|pwd|printf|sh|bash|python3?)[ :]")
                self.assertNotRegex(grant, r"^Bash\(git(?::| \*| (?:status|diff|log|rev-parse|show)\b)")
                self.assertNotRegex(grant, r"^Bash\((?:claude|codex|gemini)(?::\*| \*)\)$")
                self.assertNotIn("|", grant)
                if grant.startswith("Edit("):
                    self.assertTrue(grant.startswith("Edit(//tmp/") and "/second-opinion.*/" in grant)
        cli = {grant for grant in grants() if re.match(r"Bash\((?:claude|codex|gemini) ", grant)}
        self.assertEqual(cli, {
            "Bash(claude -p * --tools Read,Grep,Glob)",
            "Bash(codex exec --sandbox read-only *)",
            "Bash(gemini --sandbox -o text *)",
        })

    def test_each_bash_grant_matches_a_documented_invocation(self):
        commands = documented_commands()
        for grant in grants():
            if not grant.startswith("Bash("):
                continue
            with self.subTest(grant=grant):
                pattern = bash_rule_pattern(grant[len("Bash("):-1])
                self.assertTrue(any(pattern.fullmatch(command) for command in commands),
                                f"no documented command matches {grant}")

    def test_scratch_lifecycle_is_documented_and_covered_by_the_edit_grant(self):
        commands = documented_commands()
        self.assertIn(f"{HELPERS}/review-panel.sh scratch", commands)
        self.assertIn(f"{HELPERS}/review-panel.sh cleanup {{scratch_dir}}", commands)
        self.assertIn('mktemp -d "$root/second-opinion.XXXXXXXXXX"', (SKILL_DIR / "scripts/review-panel.sh").read_text())
        [edit] = [grant for grant in grants() if grant.startswith("Edit(")]
        pattern = gitignore_pattern(edit)
        for allowed in ("/tmp/second-opinion.AbCdEf1234/prompt.md", "/tmp/claude-1000/second-opinion.AbCdEf1234/local.json"):
            self.assertIsNotNone(pattern.fullmatch(allowed), allowed)
        for refused in ("/tmp/prompt.md", "/tmp/other.AbCdEf1234/prompt.md", "/home/user/second-opinion.AbCdEf1234/x",
                        "/tmp/second-opinion.AbCdEf1234"):
            self.assertIsNone(pattern.fullmatch(refused), refused)

    def test_portability_and_retained_exceptions_are_documented(self):
        text = PERMISSIONS.read_text()
        for invariant in ("turn that invokes", "not a security boundary", "Pi 1.4.0", "Codex", "no automatic",
                          "128 KiB", "splits pipelines", "Write(path)", "--output", "macOS", "not verified"):
            self.assertIn(invariant, text)
        for grant in grants():
            self.assertIn(f"`{grant}`", text)


if __name__ == "__main__":
    unittest.main()
