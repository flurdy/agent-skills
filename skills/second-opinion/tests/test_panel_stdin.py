"""Offline end-to-end tests for the path-free panel transport."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HELPER = Path(__file__).resolve().parents[1] / "scripts/review-panel-stdin.py"


class PanelStdinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.config = self.home / ".agents/second-opinion/config.json"
        self.config.parent.mkdir(parents=True)
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.marker = self.home / "called"
        cli = self.bin / "claude"
        cli.write_text('''#!/usr/bin/env python3
import os
from pathlib import Path
import stat
import sys
(Path.home() / "called").write_text("called")
assert stat.S_IMODE(os.stat(os.environ["TMPDIR"]).st_mode) == 0o700
assert stat.S_IMODE(os.fstat(sys.stdin.fileno()).st_mode) == 0o600
sys.stdin.read()
print("fixture review", end="")
''')
        cli.chmod(0o700)
        self.config.write_text(json.dumps({"version": 1, "profiles": {"fixture": {
            "quorum": 1, "routes": [{"id": "claude", "kind": "local", "agent": "claude", "role": "review"}],
            "limits": {"maxParallel": 1, "maxPromptBytes": 65536,
                       "maxOutputTokensPerModel": 2000, "defaultTimeoutSeconds": 10},
        }}}))
        self.env = {**os.environ, "HOME": str(self.home), "TMPDIR": str(self.scratch),
                    "PATH": f"{self.bin}:{os.environ['PATH']}"}
        for key in ("OPENROUTER_API_KEY", "SECRET_API_KEY_PROJECT"):
            self.env.pop(key, None)
        self.base = {"version": 1, "panel": "fixture", "prompt": "Review without editing.\n"}

    def call(self, action, **fields):
        payload = {**self.base, "action": action, **fields}
        result = subprocess.run([sys.executable, str(HELPER)], input=json.dumps(payload),
                                capture_output=True, text=True, env=self.env, timeout=30)
        self.assertEqual(list(self.scratch.iterdir()), [], result.stderr)
        return result

    def checked(self):
        result = self.call("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    @staticmethod
    def digests(check):
        return {key: check[key] for key in ("panelSha256", "promptSha256", "openrouterSha256")}

    def test_check_run_evaluate_uses_real_coordinator_without_caller_files(self):
        check = self.checked()
        self.assertEqual(check["promptSha256"], hashlib.sha256(self.base["prompt"].encode()).hexdigest())
        self.assertFalse(self.marker.exists(), "check launched a provider")
        result = self.call("run-local", **self.digests(check))
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)
        self.assertEqual(rows[0]["status"], "ok", rows)
        self.assertEqual(rows[0]["response"], "fixture review")
        evaluated = self.call("evaluate", policy="quorum", check=check, results=[rows])
        self.assertEqual(evaluated.returncode, 0, evaluated.stderr)
        self.assertTrue(json.loads(evaluated.stdout)["quorumMet"])

    def test_rejects_prompt_and_panel_drift_before_launch(self):
        check = self.checked()
        changed_prompt = self.call("run-local", prompt="changed", **self.digests(check))
        self.assertNotEqual(changed_prompt.returncode, 0)
        self.assertIn("prompt changed", changed_prompt.stderr)
        config = json.loads(self.config.read_text())
        config["profiles"]["fixture"]["routes"][0]["model"] = "changed"
        self.config.write_text(json.dumps(config))
        changed_panel = self.call("run-local", **self.digests(check))
        self.assertNotEqual(changed_panel.returncode, 0)
        self.assertIn("panel changed", changed_panel.stderr)
        self.assertFalse(self.marker.exists())

    def test_rejects_paths_options_and_malformed_input(self):
        for fields in ({"config": "/tmp/config"}, {"promptFile": "/tmp/prompt"},
                       {"output": "/tmp/output"}, {"cwd": "/other"}, {"command": "touch x"},
                       {"prompt": ""}, {"prompt": "x" * 65537}, {"version": 2},
                       {"timeout": True}, {"routeModels": {"--config": "/tmp/config"}},
                       {"action": "run-local", "panelSha256": "bad"}):
            with self.subTest(fields=list(fields)):
                action = fields.pop("action", "check")
                result = self.call(action, **fields)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.marker.exists())
        for data in ('{', '[]', '{"version":1,"version":1}', 'null'):
            result = subprocess.run([sys.executable, str(HELPER)], input=data,
                                    capture_output=True, text=True, env=self.env, timeout=10)
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_openrouter_needs_explicit_consent_choice(self):
        check = self.checked()
        result = self.call("run-openrouter", **self.digests(check))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("consent", result.stderr)
        result = self.call("run-openrouter", consent="configured", **self.digests(check))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])
        declined = self.call("decline-openrouter", **self.digests(check))
        self.assertEqual(declined.returncode, 0, declined.stderr)
        self.assertFalse(self.marker.exists())

    def test_evaluate_preserves_partial_failure_and_checks_result_binding(self):
        check = self.checked()
        result = self.call("evaluate", policy="consensus", check=check, results=[])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["quorumMet"])
        result = self.call("evaluate", policy="quorum", check=check, results=[[
            {"id": "claude", "status": "ok", "panelSha256": "0" * 64, "promptSha256": "0" * 64}
        ]])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("digest mismatch", result.stderr)

    def test_transport_rejects_oversized_input_and_output(self):
        result = subprocess.run([sys.executable, str(HELPER)], input=b" " * (16 * 1024 * 1024 + 1),
                                capture_output=True, env=self.env, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"transport limit", result.stderr)
        spec = importlib.util.spec_from_file_location("panel_stdin", HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.MAX_BYTES = 64
        with self.assertRaisesRegex(ValueError, "output exceeded"):
            module.run([sys.executable, "-c", "print('x' * 65)"], self.scratch, 5)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_configured_consent_does_not_override_an_ask_policy(self):
        config = json.loads(self.config.read_text())
        config["profiles"]["fixture"]["routes"] = [{
            "id": "remote", "kind": "openrouter", "model": "openrouter/vendor/fixture",
            "vendor": "Fixture", "role": "offline validation only",
        }]
        self.config.write_text(json.dumps(config))
        check = self.checked()
        result = self.call("run-openrouter", consent="configured", **self.digests(check))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("configured consent does not authorize", result.stderr)
        self.assertFalse(self.marker.exists())

    def test_sigterm_cleans_private_files_and_stops_the_reviewer(self):
        cli = self.bin / "claude"
        cli.write_text('''#!/bin/sh
printf '%s' "$$" > "$HOME/called"
exec sleep 60
''')
        check = self.checked()
        proc = subprocess.Popen([sys.executable, str(HELPER)], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        proc.stdin.write(json.dumps({**self.base, "action": "run-local", **self.digests(check)}))
        proc.stdin.close()
        deadline = time.monotonic() + 15
        while not self.marker.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(self.marker.exists())
        pid = int(self.marker.read_text())
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=15)
        proc.stdout.close()
        proc.stderr.close()
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(list(self.scratch.iterdir()), [])
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)


if __name__ == "__main__":
    unittest.main()
