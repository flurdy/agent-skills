import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/contract-check/scripts/contract-check.sh"
spec = importlib.util.spec_from_file_location("release_gates", ROOT / "skills/ready-to-release/scripts/release_gates.py")
gates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gates)
fixture_spec = importlib.util.spec_from_file_location("release_fixtures", ROOT / "skills/ready-to-release/tests/test_release_gates.py")
release_fixtures = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(release_fixtures)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.put(".mgit.conf", "services=web,api\n")
        self.put("scripts/mgit", '#!/bin/bash\n[[ "$1" == status ]] || exit 9\n', executable=True)
        self.put("scripts/pact-pairs", '#!/bin/bash\ncase "$1" in intended|built|synced) printf "web\\tapi\\n";; *) exit 9;; esac\n', executable=True)
        self.consumer = self.put("web/target/pacts/web-consumer-api-provider.json", "{}\n")
        self.provider = self.put("api/test/resources/pacts/web-consumer-api-provider.json", "{}\n")
        self.ci = self.put("api/.circleci/config.yml", 'jobs:\n  verify:\n    steps:\n      - run: sbt "testOnly -- -n tags.ContractVerifyTest"\n')
        os.utime(self.consumer, (1000000000, 1000000000))
        os.utime(self.provider, (1000000000, 1000000000))

    def put(self, name, content, executable=False):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        if executable:
            path.chmod(0o755)
        return path

    def run_audit(self, command="all", *, cwd=None, root=None):
        env = os.environ.copy()
        env.pop("RELEASE_PROJECT_ROOT", None)
        if root is not None:
            env["RELEASE_PROJECT_ROOT"] = str(root)
        result = subprocess.run(["bash", str(SCRIPT), command], cwd=cwd or self.root, env=env,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def footprint(self):
        return {str(path.relative_to(self.root)): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode), path.stat().st_mtime_ns)
                for path in self.root.rglob("*") if path.is_file()}

    def test_complete_report_is_read_only_and_consumable_by_release_authority(self):
        before = self.footprint()
        output = self.run_audit()
        known, findings, complete = gates.parse_contracts(output)
        self.assertEqual(known, {"web", "api"})
        self.assertEqual(findings, {})
        self.assertTrue(complete, output)
        self.assertEqual(before, self.footprint())
        self.assertIn("static configuration", output)
        self.assertNotIn("normalize-pacts", output)

    def test_identical_newer_output_is_not_stale(self):
        os.utime(self.consumer, (1000000100, 1000000100))
        output = self.run_audit("stale")
        self.assertIn("OK  web -> api", output)
        self.assertNotIn("STALE ", output)

    def test_changed_output_and_missing_provider_remain_findings(self):
        self.consumer.write_text('{"changed":true}\n')
        self.assertIn("STALE  web -> api", self.run_audit("stale"))
        os.utime(self.consumer, (999999900, 999999900))
        self.assertIn("DIFFERS  web -> api", self.run_audit("stale"))
        self.provider.unlink()
        self.assertIn("MISSING_PROVIDER  web -> api", self.run_audit("stale"))

    def test_failed_git_status_is_incomplete_not_clean(self):
        self.put("scripts/mgit", "#!/bin/bash\nexit 7\n", executable=True)
        output = self.run_audit()
        self.assertIn("status=error", output)
        self.assertNotIn("CLEAN ", output)
        self.assertFalse(gates.parse_contracts(output)[2])

    def test_untracked_pacts_use_read_only_porcelain_status(self):
        subprocess.run(["git", "init", "-q", str(self.root / "api")], check=True)
        self.put("scripts/mgit", '#!/bin/bash\n[[ "$1" == status && "$3" == --porcelain=v1 && "$GIT_OPTIONAL_LOCKS" == 0 ]] || exit 9\nservice="$2"; shift 2\nexec git -C "$service" status "$@"\n', executable=True)
        before = self.footprint()
        output = self.run_audit("uncommitted")
        self.assertIn("UNCOMMITTED  api", output)
        self.assertNotIn("CLEAN ", output)
        self.assertEqual(before, self.footprint())

    def test_collector_failure_does_not_become_zero_gaps(self):
        for mode in ("missing", "built", "synced", "intended"):
            with self.subTest(mode=mode):
                helper = self.root / "scripts/pact-pairs"
                if mode == "missing":
                    helper.unlink()
                else:
                    self.put("scripts/pact-pairs", f'#!/bin/bash\n[[ "$1" != {mode} ]] || exit 8\nprintf "web\\tapi\\n"\n', executable=True)
                output = self.run_audit()
                self.assertIn("status=error", output)
                self.assertFalse(gates.parse_contracts(output)[2])

    def test_release_root_is_honored_instead_of_ancestor_guess(self):
        outside = self.root / "unrelated"
        outside.mkdir()
        self.put("unrelated/.mgit.conf", "services=none\n")
        output = self.run_audit("matrix", cwd=outside, root=self.root)
        self.assertIn("| web | api | consumer provider |", output)

    def test_quoted_enum_values_and_comments_are_literal_evidence(self):
        self.ci.write_text('environment:\n  PACTCONSUMER: "web-consumer" # current\n')
        output = self.run_audit("coverage")
        self.assertIn("OK   api  style=enum", output)
        self.assertNotIn("GAP ", output)

    def test_commented_verify_and_consumer_entries_do_not_count(self):
        self.ci.write_text('# - run: sbt "testOnly -- -n tags.ContractVerifyTest"\nenvironment:\n  PACTCONSUMER1: other-consumer\n  # PACTCONSUMER2: web-consumer\n')
        output = self.run_audit("coverage")
        self.assertIn("GAP  api  style=enum", output)
        self.assertIn("not-verified=web", output)
        self.ci.write_text('# - run: sbt "testOnly -- -n tags.ContractVerifyTest"\n')
        output = self.run_audit("coverage")
        self.assertNotIn("style=tag", output)
        self.assertIn("style=unsupported", output)

    def test_tag_mentions_outside_a_command_are_not_verification_evidence(self):
        for text in ('description: ContractVerifyTest\n', '- run: echo "ContractVerifyTest"\n', '- run: sbt "testOnly *OtherTest" && echo "-- -n tags.ContractVerifyTest"\n'):
            with self.subTest(text=text):
                self.ci.write_text(text)
                output = self.run_audit("coverage")
                self.assertNotIn("style=tag", output)
                self.assertIn("style=unsupported", output)

    def test_supported_tag_command_forms_are_static_matches(self):
        for line in ('sbt testOnly -- -n tags.ContractVerifyTest', "command: sbt 'testOnly -- -n tags.ContractVerifyTest'", '- run: sbt "testOnly -- -n tags.ContractVerifyTest" # selector'):
            with self.subTest(line=line):
                self.ci.write_text("    " + line + "\n")
                output = self.run_audit("coverage")
                self.assertIn("OK   api  style=tag", output)
                self.assertIn("static configuration", output)

    def test_src_provider_layout_and_single_quoted_enum(self):
        self.provider.unlink()
        self.put("api/src/test/resources/pacts/web-consumer-api-provider.json", "{}\n")
        self.ci.write_text("environment:\n  PACTCONSUMER1: 'web-consumer' # current\n")
        known, findings, complete = gates.parse_contracts(self.run_audit())
        self.assertEqual(known, {"web", "api"})
        self.assertEqual(findings, {})
        self.assertTrue(complete)

    def test_malformed_quoted_enum_is_unknown(self):
        self.ci.write_text("environment:\n  PACTCONSUMER: 'web-consumer\"\n")
        self.assertIn("style=unsupported", self.run_audit("coverage"))

    def test_invalid_pinned_root_fails_without_guessing(self):
        for root in ("relative", str(self.root / "absent")):
            with self.subTest(root=root):
                env = {**os.environ, "RELEASE_PROJECT_ROOT": root}
                result = subprocess.run(["bash", str(SCRIPT), "all"], cwd=self.root, env=env,
                                        text=True, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("RELEASE_PROJECT_ROOT", result.stderr)
                self.assertNotIn("SUMMARY", result.stdout)

    def test_real_audit_output_drives_release_verdicts(self):
        data = release_fixtures.add_api(release_fixtures.snapshot())
        ci_text = self.ci.read_text()
        mgit_text = (self.root / "scripts/mgit").read_text()
        for scenario, expected in (("healthy", "READY"), ("unsupported-ci", "HOLD"), ("git-failed", "HOLD"), ("different", "NOT READY")):
            with self.subTest(scenario=scenario):
                self.ci.write_text(ci_text)
                self.put("scripts/mgit", mgit_text, executable=True)
                if scenario == "unsupported-ci":
                    self.ci.write_text("jobs: {}\n")
                elif scenario == "git-failed":
                    self.put("scripts/mgit", "#!/bin/bash\nexit 7\n", executable=True)
                elif scenario == "different":
                    self.consumer.write_text('{"changed":true}\n')
                data["contracts"] = release_fixtures.evidence(self.run_audit())
                row = gates.evaluate(data, "web")["services"][0]
                self.assertEqual(row["verdict"], expected, row)

    def test_dynamic_ci_and_other_engines_are_unknown_not_verified(self):
        for text in ('environment:\n  PACTCONSUMER: << parameters.consumer >>\n', 'environment:\n  PACTCONSUMER: $CONSUMER\n'):
            with self.subTest(text=text):
                self.ci.write_text(text)
                self.assertIn("style=unsupported", self.run_audit("coverage"))
        self.ci.unlink()
        self.put("api/.github/workflows/check.yml", "jobs: {}\n")
        output = self.run_audit()
        self.assertIn("style=unsupported", output)
        self.assertIn("unavailable", output)
        known, findings, complete = gates.parse_contracts(output)
        self.assertTrue(complete, output)
        self.assertEqual(known, {"web", "api"})
        self.assertIn("GAP", findings["api"])
        self.assertIn("GAP", findings["web"])


if __name__ == "__main__":
    unittest.main()
