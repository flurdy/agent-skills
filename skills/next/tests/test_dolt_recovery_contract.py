"""Attended skill contract, not runtime enforcement or an automatic startup test."""
from pathlib import Path
import unittest

NEXT = Path(__file__).resolve().parents[1]


class DoltRecoveryContractTest(unittest.TestCase):
    def setUp(self):
        self.skill = (NEXT / "SKILL.md").read_text()
        self.recovery = (NEXT / "references/dolt-recovery.md").read_text()

    def test_recovery_is_explicit_and_separate_from_listing_and_claiming(self):
        self.assertIn("/next recover <repo>", self.skill)
        self.assertIn("references/dolt-recovery.md", self.skill)
        self.assertIn("do not pass `recover` to `next-bd`", self.skill)
        self.assertIn("Listing never starts servers", self.skill)
        for phrase in (
            "scheduled/unattended tick", "never drop `--readonly`",
            "Shared, proxied,", "auto-start-disabled and ambiguous",
        ):
            self.assertIn(phrase, self.skill)
        for phrase in (
            "not an executable collector flag", "not permission to",
            "never batch-start", "unknown means ineligible",
            "Do not restart `next-select start`", "next_safe",
            "Reproduce list Markdown verbatim",
        ):
            self.assertIn(phrase, self.recovery)

    def test_effective_policy_checks_cannot_be_replaced_by_a_connection_error(self):
        for phrase in (
            "both** `Dolt server unreachable`", "`connection refused`",
            "numeric loopback", "metadata.json", "dolt_mode: server",
            "repo-local `.beads/dolt`", "`.beads/redirect`",
            "No shared-server, proxied-server, team-server",
            "explicitly pinned host, port, socket", "BEADS_DOLT_AUTO_START",
            "BEADS_DIR", "BEADS_DB", "BD_DB", "BEADS_PROXIED_SERVER_*",
            "`.beads/.env`", "config.local.yaml", "global/user configuration",
            "never print credentials", "partial YAML parser",
            "Never override a disable setting",
        ):
            self.assertIn(phrase, self.recovery)

    def test_confirmation_discloses_lifecycle_effects_and_preserves_guards(self):
        for phrase in (
            "may clean up", "initialise missing storage or identity",
            "reclaim a port", "no no-kill/no-init switch",
            "bd -C <directory> --sandbox dolt start",
            "Obtain fresh explicit approval", "invalidates confirmation",
            "Session guards remain", "standalone visible tool call",
            "60-second timeout", "No remote sync",
        ):
            self.assertIn(phrase, self.recovery)
        self.assertLess(self.recovery.index("Obtain fresh explicit approval"),
                        self.recovery.index("Execute the exact approved command"))

    def test_failed_start_and_failed_retry_do_not_loop_or_claim_success(self):
        for phrase in (
            "no start and no retry", "never retry a failed start",
            "a background child may already exist", "Only after exit zero",
            "read still unverified", "read-only invocation once",
            "same cwd/options/qualified", "never inject prose into JSON stdout",
            "A failed read remains unavailable", "No other store is started",
            "Successful recovery returns to the picker",
        ):
            self.assertIn(phrase, self.recovery)


if __name__ == "__main__":
    unittest.main()
