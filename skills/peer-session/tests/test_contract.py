"""Offline instruction contracts; these do not message sessions or execute an agent."""

import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parents[1]


class PeerSessionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (SKILL / "SKILL.md").read_text()
        cls.front = cls.text.split("---", 2)[1]
        cls.flat = " ".join(cls.text.split())

    def assert_phrases(self, *phrases):
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertTrue(phrase in self.flat, f"missing: {phrase}")

    def test_metadata_grants_only_messaging_and_orca(self):
        self.assertIn("name: peer-session", self.front)
        self.assertIn("model-tier: standard", self.front)
        self.assertIn("effort: high", self.front)
        grants = re.search(r'^allowed-tools: "(.*)"$', self.front, re.M).group(1)
        self.assertEqual(
            grants.split(","),
            ["Read", "AskUserQuestion", "ToolSearch", "ListAgents", "SendMessage", "Skill(orca-cli)"],
        )
        description = re.search(r"^description: (.*)$", self.front, re.M).group(1)
        for term in ("native Claude Code", "Orca", "transport switching"):
            self.assertIn(term, description)

    def test_one_transport_chosen_up_front_without_automatic_switching(self):
        self.assert_phrases(
            "## Choose one transport",
            "another live Claude Code session on this machine",
            "Pi callers or recipients, other machines",
            "`ToolSearch` **if exposed**",
            "Use only `to`, `message`, `summary` and `notify_when_idle`",
            "native is unavailable for this run",
            "Pi exposes neither tool",
            "Never switch transport automatically",
            "a new, separately approved request",
        )
        self.assertFalse("not a second transport" in self.flat, "stale single-transport rule")
        for section in ("## 1.", "## 2.", "## 3.", "## 4."):
            body = self.text.split(section, 1)[1].split("\n## ", 1)[0]
            with self.subTest(section=section):
                self.assertLess(body.index("### Native"), body.index("### Orca"))

    def test_native_binding_excludes_self_and_never_guesses(self):
        self.assert_phrases(
            "Call `ListAgents` once",
            "subagents, agent-team teammates, cloud and Remote Control",
            "can't receive cross-session messages",
            "not proof of identity, ownership or liveness",
            "Exclude self only when this session is positively identified",
            "the candidate stays ambiguous",
            "short identifier",
            "never guess between same-project peers",
        )

    def test_identification_pings_need_separate_consent(self):
        self.assert_phrases(
            "#### Optional identification pings",
            "identification only, no action needed",
            "may start a turn and use that session's quota",
            "untrusted self-reports",
            "never bind identity",
            "Ping approval never authorizes the request itself",
            "no second batch",
        )

    def test_ping_choices_cannot_expand_to_unrelated_sessions(self):
        pings = self.text.split("#### Optional identification pings", 1)[1].split("### Orca", 1)[0]
        flat = " ".join(pings.split())
        for phrase in (
            "Only offer candidates within the user's requested project/session scope",
            "Never offer a `ping all sessions` option",
            "confirm the candidate subset with the user",
            "revalidate each bound address before its ping",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(phrase in flat, f"missing: {phrase}")

    def test_native_message_is_bounded_and_cannot_launder_permissions(self):
        self.assert_phrases(
            "**4 KiB UTF-8**",
            "first line self-contained",
            "status, facts, decisions or one question",
            "denied, blocked or unauthorized in the caller's session",
            "cannot approve prompts in the recipient",
            "single correlated native reply",
            "only from the main conversation",
        )

    def test_native_receipts_and_replies_stay_unverified_until_correlated(self):
        self.assert_phrases(
            "call `ListAgents` again",
            "`SendMessage` exactly once",
            "`Not sent`",
            "Readiness only",
            "**outcome unknown**",
            "Do not sleep, poll or start a watcher",
            "whose first line carries the request ID",
            "label it late",
            "**response unverified**",
        )
        evidence = self.text.split("## 3.", 1)[1].split("### Orca", 1)[0]
        self.assertFalse("turn_started" in evidence, "native evidence borrows Orca terms")

    def test_orca_path_is_preserved(self):
        self.assert_phrases(
            "at most 20 lines",
            "`satisfied: true`",
            "**16 KiB**",
            "`0600`",
            "`turn_started`",
            "**120 seconds after send**",
            "same-request recovery",
            "Never send to an implicit active/current terminal",
        )

    def test_catalog_docs_and_test_gate(self):
        catalog = (ROOT / "skills/README.md").read_text()
        rows = re.findall(r"^\| peer-session \|(.*)\|$", catalog, re.M)
        self.assertEqual(len(rows), 1)
        self.assertIn("native", rows[0])
        makefile = (ROOT / "Makefile").read_text()
        targets = makefile.split("TEST_TARGETS :=", 1)[1].split("test:", 1)[0]
        self.assertIn("test-peer-session", targets)
        self.assertIn("-s skills/peer-session/tests", makefile)
        self.assertTrue((SKILL / "tests/README.md").is_file())
        self.assert_phrases("human-operated native pilot", "not live-delivery evidence")


if __name__ == "__main__":
    unittest.main()
