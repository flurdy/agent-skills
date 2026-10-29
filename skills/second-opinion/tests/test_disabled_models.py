import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "disabled-models.py"
spec = importlib.util.spec_from_file_location("disabled_models", SCRIPT)
disabled_models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(disabled_models)


class DisabledModelsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name).resolve()
        self.home = root / "home"
        self.workspace = root / "workspace"
        self.member = root / "elsewhere" / "member"
        self.sibling = root / "workspace-sibling"
        for directory in (self.home / ".agents", self.workspace / "repos", self.workspace / "nested" / "deep",
                          self.member, self.sibling):
            directory.mkdir(parents=True)
        (self.workspace / "repos" / "member").symlink_to(self.member)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, policy):
        text = policy if isinstance(policy, str) else json.dumps(policy)
        (self.home / ".agents" / "disabled-models.json").write_text(text)

    def evaluate(self, cwd):
        return disabled_models.evaluate(self.home, cwd)

    def run_cli(self, cwd, *arguments):
        environment = {key: value for key, value in os.environ.items() if key != "PWD"}
        environment["HOME"] = str(self.home)
        return subprocess.run([str(SCRIPT), *arguments], cwd=cwd, env=environment,
                              capture_output=True, text=True, check=False)

    def test_missing_file_is_no_policy(self):
        result = self.evaluate(self.workspace)
        self.assertEqual((result["status"], result["revision"], result["deniedAgents"]), ("missing", None, {}))

    def test_descendants_boundaries_and_accumulated_rules(self):
        self.write({"version": 1, "rules": [
            {"id": "outer", "roots": [str(self.workspace)], "models": ["vendor/a"], "reason": "licence"},
            {"id": "inner", "roots": [str(self.workspace / "nested")], "models": ["vendor/a", "vendor/b"],
             "agents": ["gemini"]},
        ]})
        deep = self.evaluate(self.workspace / "nested" / "deep")
        self.assertEqual(deep["matchedRules"], ["outer", "inner"])
        self.assertEqual(deep["deniedModels"], {"vendor/a": ["outer: licence", "inner"], "vendor/b": ["inner"]})
        self.assertEqual(deep["deniedAgents"], {"gemini": ["inner"]})
        self.assertRegex(deep["revision"], r"^[a-f0-9]{64}$")
        self.assertEqual(self.evaluate(self.workspace)["matchedRules"], ["outer"])
        self.assertEqual(self.evaluate(self.sibling)["matchedRules"], [])

    def test_symlinks_match_in_either_direction(self):
        self.write({"version": 1, "rules": [
            {"id": "member", "roots": [str(self.workspace / "repos" / "member")], "agents": ["codex"]}]})
        self.assertEqual(self.evaluate(self.member)["matchedRules"], ["member"])
        self.write({"version": 1, "rules": [{"id": "real", "roots": [str(self.member)], "agents": ["codex"]}]})
        self.assertEqual(self.evaluate(self.workspace / "repos" / "member")["matchedRules"], ["real"])

    def test_roots_absent_on_this_machine_are_valid_but_unmatched(self):
        self.write({"version": 1, "rules": [{"id": "other", "roots": ["/nonexistent/other"], "models": ["vendor/a"]}]})
        result = self.evaluate(self.workspace)
        self.assertEqual((result["status"], result["matchedRules"]), ("loaded", []))

    def test_malformed_or_ambiguous_policy_is_invalid(self):
        rule = {"id": "r", "roots": [str(self.workspace)], "models": ["vendor/a"]}
        cases = [
            ("{", "malformed JSON"),
            ([], "must be an object"),
            ({"version": 2, "rules": []}, "version must be 1"),
            ({"version": True, "rules": []}, "version must be 1"),
            ({"version": 1, "rules": [], "extra": True}, "unknown top-level"),
            ({"version": 1, "rules": [{**rule, "model": ["vendor/b"]}]}, "unknown fields: model"),
            ({"version": 1, "rules": [{**rule, "roots": ["relative/path"]}]}, "roots"),
            ({"version": 1, "rules": [{**rule, "roots": []}]}, "at least one absolute path"),
            ({"version": 1, "rules": [{"id": "r", "roots": [str(self.workspace)]}]}, "at least one model or agent"),
            ({"version": 1, "rules": [{**rule, "models": ["bare-model"]}]}, "models"),
            ({"version": 1, "rules": [{**rule, "agents": ["copilot"]}]}, "agents"),
            ({"version": 1, "rules": [rule, rule]}, "duplicates id r"),
            ({"version": 1, "rules": [{**rule, "reason": ""}]}, "reason"),
        ]
        for policy, error in cases:
            with self.subTest(policy=policy):
                self.write(policy)
                result = self.evaluate(self.workspace)
                self.assertEqual(result["status"], "invalid")
                self.assertIn(error, result["error"])
                self.assertEqual(result["deniedModels"], {})

    def test_cli_uses_fixed_home_path_and_cwd_with_exit_codes(self):
        self.write({"version": 1, "rules": [
            {"id": "work", "roots": [str(self.workspace)], "agents": ["gemini"], "reason": "no Gemini here"}]})
        denied = self.run_cli(self.workspace, "check-direct", "gemini")
        self.assertEqual(denied.returncode, 3)
        self.assertEqual(json.loads(denied.stdout)["reasons"], ["work: no Gemini here"])
        self.assertEqual(self.run_cli(self.workspace, "check-direct", "claude").returncode, 0)
        self.assertEqual(self.run_cli(self.sibling, "check-direct", "gemini").returncode, 0)
        self.write("{")
        invalid = self.run_cli(self.workspace, "check-direct", "claude")
        self.assertEqual(invalid.returncode, 2)
        self.assertFalse(json.loads(invalid.stdout)["allowed"])
        self.assertEqual(self.run_cli(self.workspace, "evaluate").returncode, 2)
        for arguments in (("evaluate", str(self.home)), ("check-direct", "copilot"), ("--policy", "/tmp/x")):
            with self.subTest(arguments=arguments):
                self.assertEqual(self.run_cli(self.workspace, *arguments).returncode, 64)


if __name__ == "__main__":
    unittest.main()
