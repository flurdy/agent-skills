"""Static workflow regression scenarios, not model-executed semantic assurance.

Each synthetic case names evidence and the instruction that must survive editing.
Runtime collector behavior is tested separately; the live trial tests agent interpretation.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

SCENARIOS = [
    ("partial_pr", "PR merged; AC2 not in that PR", "NOT READY", "A PR slice never satisfies an unmapped ticket requirement."),
    ("other_store", "Jira Done; another proven store has a deferred required bead", "NOT READY", "Include required open, in-progress, blocked and deferred work across proven stores."),
    ("closed_at_creation", "Bead closed; PR still open", "NOT READY", "A closed bead is not evidence of merge, rollout or Jira completion."),
    ("approved_deviation", "Exact product approval; replacement implemented, verified and delivered", "READY", "An approved change still needs replacement acceptance evidence."),
    ("unapproved_deviation", "Implementation comment calls changed copy deliberate; no approval", "INCOMPLETE", "An implementation comment is not scope approval."),
    ("lost_baseline", "Only current Jira description available", "INCOMPLETE", "Do not invent the original request or reconstruct approval from timestamps."),
    ("unread_design", "Figma unavailable and Confluence page cap reached", "INCOMPLETE", "A required unread source or material traversal omission blocks READY."),
    ("conflict", "Jira requires all brands; authoritative design contradicts it", "NOT READY", "Unresolved requirement conflicts are NOT READY."),
    ("stale_checks", "CI green on old PR head, new changes untested", "INCOMPLETE", "Evidence from different revisions cannot be combined into one passing snapshot."),
    ("store_failure", "One store unavailable; no matches in another", "INCOMPLETE", "A partial inventory never proves absence of outstanding work."),
    ("optional_followup", "Required work complete; separately agreed optional improvement open", "READY", "An explicitly separate optional follow-up is not automatically a ticket blocker."),
    ("complete", "All required sources read; acceptance, checks and applicable delivery proven", "READY", "READY requires all required obligations satisfied with cited current evidence."),
]


class CloseoutContractTests(unittest.TestCase):
    def test_synthetic_scenarios_retain_their_guardrails(self):
        path = ROOT / "skills/outstanding-work/references/ticket-closeout.md"
        self.assertTrue(path.is_file(), "ticket-wide workflow missing")
        contract = " ".join(path.read_text().split())
        for name, evidence, expected, rule in SCENARIOS:
            with self.subTest(scenario=name, evidence=evidence, expected=expected):
                self.assertIn(rule, contract)

    def test_prompt_is_thin_read_only_composition(self):
        path = ROOT / "prompts/ticket-closeout.md"
        self.assertTrue(path.is_file(), "thin prompt missing")
        text = path.read_text()
        for phrase in ("$ARGUMENTS", "outstanding-work", "ticket-wide", "report-only", "verify-task", "Do not"):
            self.assertIn(phrase, text)
        self.assertLess(len(text.splitlines()), 30)
        for phrase in ("run /complete-task", "run /total-review", "bd close", "jira transition"):
            self.assertNotIn(phrase, text)

    def test_mode_catalog_and_bounds_are_documented(self):
        skill = (ROOT / "skills/outstanding-work/SKILL.md").read_text()
        self.assertIn("ticket-wide", skill)
        self.assertIn("TRACKING-INVENTORY", skill)
        self.assertNotIn("bd search --external-contains", skill)
        self.assertIn("ticket-closeout.md", (ROOT / "prompts/README.md").read_text())
        ref = ROOT / "skills/outstanding-work/references/ticket-closeout.md"
        self.assertTrue(ref.is_file())
        contract = ref.read_text()
        for term in ("5 Confluence", "2 Figma", "20 PR", "source ledger", "deviation ledger", "NOT ASSESSED", "definition of Done"):
            self.assertIn(term, contract)


if __name__ == "__main__":
    unittest.main()
