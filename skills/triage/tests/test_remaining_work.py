"""Offline instruction contracts; no model runs or real tracker mutations."""

import re
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]


def text(name, relative="SKILL.md"):
    return (SKILLS / name / relative).read_text()


class RemainingWorkContractTests(unittest.TestCase):
    def setUp(self):
        self.triage = text("triage")
        self.reference = text("triage", "references/remaining-work.md")
        self.flat = " ".join(self.reference.split())

    def require(self, *phrases):
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_discovery_and_explicit_dispatch(self):
        self.assertIn("partially completed", self.triage.split("---", 2)[1])
        self.assertIn("/triage --remaining <selector>", self.triage)
        self.assertIn("references/remaining-work.md", self.triage)
        self.assertLess(
            self.triage.index("- **Explicit `--remaining`**"),
            self.triage.index("- **Existing bead**"),
        )
        for skill in ("beads", "backlog-groom", "complete-task", "verify-task"):
            with self.subTest(skill=skill):
                self.assertIn("/triage --remaining", text(skill))
        self.assertIn("partially completed", (SKILLS / "README.md").read_text())

    def test_scenario_matrix_preserves_existing_policy(self):
        rows = {
            "Independent remaining outcome": ("EXTRACT", "five-part child test"),
            "Future rollout/job verification only": ("HAND OFF", "complete-task"),
            "Cache expiry": ("DEFER ORIGINAL", "not event detection"),
            "Pending manual action": ("KEEP OPEN", "independent outcome"),
            "Failed checks": ("KEEP OPEN", "failure"),
            "Unavailable tooling": ("VERIFY FIRST", "not a future event"),
            "Missing or stale verification": ("VERIFY FIRST", "verify-task"),
            "Unclear acceptance or delivery policy": ("DECISION", "no writes"),
        }
        for case, expected in rows.items():
            with self.subTest(case=case):
                row = next(line for line in self.reference.splitlines() if line.startswith(f"| {case} |"))
                for term in expected:
                    self.assertIn(term, row)
        self.require(
            "No sizing or delivery-boundary policy changes",
            "local-main reachability alone is not the explicit delivery declaration",
            "Do not broaden the evidence-only exception to cache waits or manual actions",
            "Never auto-run the receiving workflow",
        )

    def test_ownership_and_input_boundaries(self):
        self.require(
            "next-select resolve <selector>", "`ambiguous`", "`unavailable`", "`not-found`",
            "never fall through to free-text creation", "fresh full resolution before every independent mutation",
            "claim owner's agreement", "session activity is unverified",
            "epic or aggregate", "keep it open", "external-text",
            "same proven store", "Cross-store extraction needs a separate proposal",
        )
        code = "\n".join(re.findall(r"```(?:bash|text)\n(.*?)```", self.reference, re.S))
        self.assertNotRegex(code, r"(?m)^bd (?:create|update|close|defer|dep|show)\b")
        self.assertNotIn("--force", code)

    def test_evidence_packet_and_acceptance_conservation(self):
        self.require(
            "every original acceptance item", "before/after acceptance union",
            "current `verify-task` report", "exact revision", "applicable project delivery boundary",
            "observable pass criteria", "event or manual action", "environment",
            "evidence destination", "failure disposition", "Exact `external_ref`",
            "labels", "imported-text fences", "no acceptance may disappear",
        )

    def test_independent_extraction_order_and_separate_close_approval(self):
        ordered = [
            "### A. Find an existing owner",
            "### B. Preview and approve",
            "### C. Create or reuse, then verify",
            "bd -C <directory> create",
            "next-select resolve <follow-up-selector>",
            "bd -C <directory> show <follow-up-id>",
            "### D. Update the original, then separately confirm closure",
            "bd -C <directory> update <id>",
            "fresh per-bead confirmation",
            "bd -C <directory> close <id>",
        ]
        position = 0
        for phrase in ordered:
            with self.subTest(phrase=phrase):
                position = self.reference.index(phrase, position) + len(phrase)
        self.require(
            "discovered-from:<id>", "not parent membership or a blocking edge",
            "original stays open", "not permission to close",
            "Jira is untouched", "No automatic scope release",
        )

    def test_failure_and_rerun_reconciliation(self):
        self.require(
            "all statuses, including closed and deferred", "actual provenance links",
            "closed match", "multiple matches", "unreadable inventory",
            "failed or uncertain creation", "do not create another",
            "overlapping ownership", "scope update fails",
            "close fails", "no automatic retry", "changed proposal needs fresh approval",
            "already closed", "read-only reconciliation",
        )

    def test_defer_requires_agreed_date_and_readback(self):
        body = self.reference.split("## 4. Defer the original", 1)[1].split("## 5.", 1)[0]
        for phrase in (
            "future wake date", "timezone", "Missing date", "no writes",
            "review date", "not event detection", "bd defer --help",
            "next-select resolve <selector>", "bd -C <directory> defer <id>",
            "--until", "--reason", "read back", "defer_until", "no automatic retry",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)
        self.assertNotRegex(body, r"bd -C <directory> (?:create|close)\b")
        self.assertIn("Bash(bd -C * defer:*)", self.triage.split("---", 2)[1])

    def test_evidence_only_followups_have_no_second_writer(self):
        body = self.reference.split("## 2. Classify", 1)[1].split("## 3.", 1)[0]
        self.assertIn("triage makes no lifecycle writes for that row", body)
        self.require(
            "future event is still absent", "wrong revision", "verification failed",
            "do not close as verified", "No new implementation commit",
            "separate explicit tracking approval", "no automatic reopen or bug creation",
        )
        self.assertIn("explicit project declaration", text("beads"))
        self.assertIn("future rollout/job check", text("beads", "references/sizing.md"))

    def test_decline_and_operational_side_effects(self):
        self.require(
            "declined or abandoned", "no writes", "does not authorize",
            "cache purge", "rollout", "installation", "remote synchronization",
            "publication", "source edits", "Do not start the remainder",
        )


if __name__ == "__main__":
    unittest.main()
