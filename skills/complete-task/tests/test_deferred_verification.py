"""Offline cross-skill instruction contracts, not live Beads/model execution tests."""

import re
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]


def text(skill, file="SKILL.md"):
    return (SKILLS / skill / file).read_text()


class DeferredVerificationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.complete = text("complete-task")
        cls.beads = text("beads")
        cls.verify = text("verify-task")

    def assert_phrases(self, content, *phrases):
        flat = " ".join(content.split())
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertTrue(phrase in flat, f"missing: {phrase}")

    def section(self, start, end):
        self.assertIn(start, self.complete, f"missing section: {start}")
        self.assertIn(end, self.complete, f"missing section: {end}")
        return self.complete.split(start, 1)[1].split(end, 1)[0]

    def test_pending_handoff_is_reachable_but_not_a_pass(self):
        self.assert_phrases(
            self.section("## Prerequisites", "## Usage"),
            "deferred-verification tracking handoff", "Incomplete evidence",
            "failed, stale, not-run", "ordinary unavailable evidence",
        )
        self.assert_phrases(
            self.section("### 3.", "#### Stage"),
            "existing pending-event commit", "single §6 choice", "not fully verified",
        )
        self.assert_phrases(
            self.section("### 5.", "### 6."),
            "explicit project guidance takes precedence", "not a delivery-boundary declaration",
        )

    def test_choice_requires_exact_preview_and_reached_project_boundary(self):
        body = self.section("#### Future-event-only verification", "#### A. Close implementation")
        self.assert_phrases(
            body, "AskUserQuestion", "only when", "explicit project declaration",
            "boundary has been reached", "Snooze the original (Recommended)",
            "Close implementation + deferred follow-up", "Stop",
            "exact proposed follow-up", "close reason", "wake date", "explicit confirmation",
            "failed", "stale", "No tracking writes",
        )
        self.assertLess(
            self.complete.index("**Detached mode** — never close"),
            self.complete.index("#### Future-event-only verification"),
        )
        self.assertNotIn("--force", body)

    def test_follow_up_before_close_and_readback_before_second_mutation(self):
        body = self.section("#### A. Close implementation", "#### B. Snooze")
        ordered = [
            "Check for an existing",
            "next-select resolve <bead-id>",
            "bd -C <directory> create",
            "next-select resolve <follow-up-selector>",
            "bd -C <directory> show <follow-up-id>",
            "next-select resolve <bead-id>",
            "bd -C <directory> close <bead-id>",
        ]
        position = 0
        for term in ordered:
            with self.subTest(term=term):
                position = body.index(term, position) + len(term)
        self.assert_phrases(
            body, "--status=deferred", "--defer", "--deps", "discovered-from:<bead-id>",
            "--external-ref", "original stays open", "ambiguous create result",
            "do not create another", "close fails", "skip §6a",
            "implemented at <sha>; <check> unverified, tracked in <follow-up-id>",
        )
        self.assertNotRegex(body, r"--parent|--deps\s+[\"']?(?:blocks|blocked-by|parent-child):")

    def test_snooze_records_complete_packet_without_creating_or_closing(self):
        body = self.section("#### B. Snooze", "#### Normal finalization")
        self.assert_phrases(
            body, "next-select resolve <bead-id>", "bd -C <directory> defer <bead-id>",
            "--until", "--reason", "<verification-note>", "read back", "skip §6a",
            "failure", "do not claim it was deferred",
        )
        self.assertNotRegex(body, r"bd -C <directory> (?:create|close) ")

    def test_shared_packet_wake_failure_and_evidence_only_closure(self):
        self.assertIn("### Deferred verification", self.beads)
        body = self.beads.split("### Deferred verification", 1)[1].split("## Use current", 1)[0]
        self.assert_phrases(
            body, "exact command, URL or job", "environment", "revision", "pass criteria",
            "wake date", "event", "evidence destination", "failure disposition",
            "same owning store", "discovered-from", "not parent membership",
            "does not detect the event", "event has not happened", "no automatic polling",
            "completion claim", "linked bug", "No new implementation commit",
            "explicitly authorized verification", "never close it as verified",
        )

    def test_only_scoped_new_mutation_grants(self):
        front = self.complete.split("---", 2)[1]
        grants = re.search(r'^allowed-tools: "(.*)"$', front, re.M).group(1)
        for command in ("create", "defer"):
            self.assertIn(f"Bash(bd -C * {command}:*)", grants.split(","))
        verify_front = self.verify.split("---", 2)[1]
        self.assertNotRegex(verify_front, r"Bash\(bd[^)]* (create|defer|close|update)")
        self.assertNotIn("Skill(complete-task)", verify_front)


if __name__ == "__main__":
    unittest.main()


class ScopeReleaseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.complete = text("complete-task")
        cls.flat = " ".join(cls.complete.split())

    def test_release_follows_a_verified_trunk_close_and_precedes_jira_review(self):
        trunk = self.complete.index("**Trunk mode** — close the bead now")
        release = self.complete.index("#### Release task scopes (Pi only)")
        pr_mode = self.complete.index("**PR mode** — do **not** close")
        jira = self.complete.index("### 6a. Offer Jira review")
        self.assertLess(trunk, release)
        self.assertLess(release, pr_mode)
        self.assertLess(release, jira)
        for phrase in (
            "Only after this run's fully verified trunk-mode close succeeds, and before §6a",
            "`release_scopes` tool once with no arguments",
            "Never pass `allowDirty`",
            "do not retry, work around it, or reopen the bead",
            "release nothing and report that leases remain held until the user runs `/lazy` or `/plan`",
            "The tracker close itself never releases source authority",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_non_trunk_and_pending_outcomes_skip_release(self):
        section = self.complete.split("#### Release task scopes (Pi only)", 1)[1].split("**PR mode**", 1)[0]
        flat = " ".join(section.split())
        for outcome in ("Detached mode", "PR mode", "**Close the bead anyway**", "deferred-verification closures", "snoozes", "failed or uncertain closes"):
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, flat)
        self.assertIn("skip this release", flat)

    def test_report_and_tool_permission_cover_release(self):
        self.assertIn("release_scopes", self.complete.split("---", 2)[1])
        self.assertIn("The Pi scope-release outcome", self.complete.split("### 8. Report", 1)[1])
