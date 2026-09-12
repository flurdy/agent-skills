"""Prototype contract checks; optional cross-repo checks use only synthetic policy."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1]
CONTRACT = SKILL / "references" / "billing-evidence.md"
FIXTURES = SKILL / "tests" / "fixtures" / "billing-evidence.json"
PACKAGE = os.environ.get("MODEL_POLICY_PACKAGE")


class BillingEvidenceContractTests(unittest.TestCase):
    def test_contract_keeps_policy_and_launch_authority_separate(self):
        self.assertTrue(CONTRACT.is_file(), "shared billing evidence contract is missing")
        text = CONTRACT.read_text()
        for boundary in (
            "not launch authorization",
            "No direct-review prompt bypass",
            "effective identity",
            "fallback",
            "fast",
            "Claude",
            "revision",
            "fanout",
            "unknown",
        ):
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, text)

    def test_consumers_link_to_one_contract_without_replacing_current_gates(self):
        root = SKILL.parents[1]
        for relative in (
            "MODEL_ROUTING.md",
            "skills/second-opinion/SKILL.md",
            "skills/delegate-work/references/child-routing-policy.md",
        ):
            with self.subTest(file=relative):
                self.assertTrue("billing-evidence.md" in (root / relative).read_text(), relative)

    def test_native_adapter_is_bounded_to_fully_resolved_policy(self):
        root = SKILL.parents[1]
        delegate = (root / "skills/delegate-work/references/runtime-adapters.md").read_text()
        child_policy = (root / "skills/delegate-work/references/child-routing-policy.md").read_text()
        for required in (
            'subagent({ action: "models", agent: "<agent>" })',
            "model_policy_evidence",
            "native Pi agents only",
            "every fallback model",
            '`fast: false`',
            "immediately before each launch",
            "pass the exact primary model",
            "current-run confirmation",
        ):
            with self.subTest(required=required):
                self.assertIn(required, delegate)
        self.assertIn('`consent: "allow"`', child_policy)
        self.assertIn("does not authorize fanout", child_policy)

    @unittest.skipUnless(PACKAGE, "MODEL_POLICY_PACKAGE required for cross-repository producer checks")
    def test_router_public_export_matches_shared_fixtures(self):
        self.assertTrue(FIXTURES.is_file(), "shared producer fixtures are missing")
        cases = json.loads(FIXTURES.read_text())
        self.assertGreaterEqual(len(cases), 6)
        script = """
            import { queryModelPolicies } from '@flurdy/pi-skill-model-router/policy';
            console.log(JSON.stringify(queryModelPolicies(process.argv[1], JSON.parse(process.argv[2]))));
        """
        for case in cases:
            with self.subTest(case=case["name"]), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "model-tier-router.json"
                content = json.dumps(case["configuration"])
                path.write_text(content)
                result = subprocess.run(
                    ["node", "--experimental-strip-types", "--input-type=module", "-e", script, directory, json.dumps(case["models"])],
                    cwd=PACKAGE,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=True,
                )
                evidence = json.loads(result.stdout)
                self.assertEqual(set(evidence), {"version", "runtime", "scope", "source", "policies"})
                self.assertEqual((evidence["version"], evidence["runtime"], evidence["scope"]), (1, "pi", "user"))
                self.assertEqual(evidence["policies"], case["policies"])
                self.assertEqual(evidence["source"], {
                    "owner": "@flurdy/pi-skill-model-router",
                    "path": str(path),
                    "status": case.get("status", "loaded"),
                    "revision": hashlib.sha256(content.encode()).hexdigest(),
                })
                self.assertEqual(path.read_text(), content)
                self.assertNotIn("fixture-private-value", result.stdout)
                self.assertEqual(sorted(item.name for item in Path(directory).iterdir()), [path.name])


if __name__ == "__main__":
    unittest.main()
