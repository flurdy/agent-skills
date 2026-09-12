import json
import os
import pathlib
import subprocess
import tempfile
import unittest

HELPER = pathlib.Path(__file__).resolve().parents[1] / "scripts/subscription-route-check.py"


class SubscriptionCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        (self.root / "bin").mkdir()
        (self.root / ".agents/second-opinion").mkdir(parents=True)
        (self.root / ".agents/second-opinion/config.json").write_text(json.dumps({
            "version": 1,
            "profiles": {},
            "subscriptionRoutes": {
                "claude": ["opus", "fable"],
                "codex": ["gpt-5.6-sol", "gpt-6-astra"],
            },
        }))
        claude = self.root / "bin/claude"
        claude.write_text("#!/bin/sh\nprintf '%s\\n' '{\"loggedIn\":true,\"authMethod\":\"claude.ai\",\"apiProvider\":\"firstParty\",\"subscriptionType\":\"max\",\"email\":\"private\"}'\n")
        claude.chmod(0o700)
        codex = self.root / "bin/codex"
        codex.write_text('#!/bin/sh\necho "Logged in using ChatGPT" >&2\n')
        codex.chmod(0o700)
        self.env = {**os.environ, "HOME": str(self.root), "PATH": str(self.root / "bin") + os.pathsep + os.environ["PATH"]}
        for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY", "OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"):
            self.env.pop(key, None)

    def tearDown(self):
        self.temp.cleanup()

    def check(self, route, model, env=None):
        result = subprocess.run(["python3", str(HELPER), route, model], env=env or self.env, text=True, capture_output=True, check=True, timeout=10)
        return json.loads(result.stdout)

    def test_authorizes_stable_subscription_models_without_account_or_version(self):
        for route, model, auth in (("claude", "opus", "claude.ai"), ("claude", "fable", "claude.ai"), ("codex", "gpt-5.6-sol", "ChatGPT"), ("codex", "gpt-6-astra", "ChatGPT")):
            with self.subTest(route=route, model=model):
                value = self.check(route, model)
                self.assertTrue(value["authorized"])
                self.assertEqual(value["auth"], auth)
                self.assertEqual(value["policyBasis"], "configured")
                self.assertNotIn("email", json.dumps(value))
                self.assertNotIn("version", value)

    def test_unlisted_model_or_invalid_policy_requires_confirmation(self):
        self.assertFalse(self.check("claude", "sonnet")["authorized"])
        config = self.root / ".agents/second-opinion/config.json"
        config.write_text(json.dumps({"version": 2, "subscriptionRoutes": {"claude": ["opus"]}}))
        self.assertEqual(self.check("claude", "opus")["policyBasis"], "invalid")
        config.write_text(json.dumps({"version": 1, "subscriptionRoutes": {"claude": ["*"]}}))
        self.assertEqual(self.check("claude", "opus")["policyBasis"], "invalid")

    def test_reports_override_names_without_values(self):
        value = self.check("claude", "opus", {**self.env, "ANTHROPIC_API_KEY": "secret"})
        self.assertFalse(value["authorized"])
        self.assertEqual(value["apiOverridesPresent"], ["ANTHROPIC_API_KEY"])
        self.assertNotIn("secret", json.dumps(value))

    def test_rejects_unknown_route_and_nonliteral_model(self):
        for args in (("gemini", "model"), ("claude", "*"), ("claude", "bad model")):
            result = subprocess.run(["python3", str(HELPER), *args], env=self.env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
