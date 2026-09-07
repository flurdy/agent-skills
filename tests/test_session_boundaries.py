"""Scoped instruction contracts; helper fixtures own collection, not live session actions."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def skill(name):
    return (ROOT / "skills" / name / "SKILL.md").read_text()


def grants(name):
    return re.search(r'^allowed-tools: "(.*)"$', skill(name), re.M).group(1)


class SessionBoundaries(unittest.TestCase):
    def test_next_stops_after_one_claim(self):
        text = skill("next")
        for obsolete in ("Continue fixing bugs", "Minor Bug Criteria", "Context Continuity", "and fix it", "Show top 5 candidates"):
            self.assertNotIn(obsolete, text)
        self.assertIn("Selection ends after one claim", text)
        for forbidden in ("Write", "Edit", "Skill(", "Bash(git", "Bash(gh", "Bash(bd update"):
            self.assertNotIn(forbidden, grants("next"))
        self.assertIn("next-select start", text)
        self.assertIn("session activity unverified", text)

    def test_wrap_up_writes_handoffs_not_tracker_or_settings(self):
        text = skill("wrap-up")
        self.assertIn("Write", grants("wrap-up"))
        for forbidden in ("Bash(bd update", "Skill(", "archive.sh"):
            self.assertNotIn(forbidden, grants("wrap-up"))
        for obsolete in ("bd update {id}", "--status=ready", "invoke the `tidy-settings` skill", "Run /tidy-settings** →", "After any demotions"):
            self.assertNotIn(obsolete, text)
        for required in ("session activity is unverified", "does not change tracker status", "report-only", "auto-save", "collision"):
            self.assertIn(required, text)

    def test_wrap_up_does_not_prescribe_cleanup_or_drop_known_context(self):
        text = skill("wrap-up")
        for obsolete in ("commit, stash, or discard before leaving", "push before leaving this client", "omit Jira pointers", "After saving (§5), if this handoff continues an older thread you want to retire, run"):
            self.assertNotIn(obsolete, text)
        self.assertIn("separate preservation task", text)

    def test_missing_branch_examples_bind_an_explicit_base(self):
        text = skill("handoffs")
        examples = re.findall(r"git (?:checkout|worktree add) -b[^`\n]*", text)
        self.assertTrue(examples)
        for example in examples:
            self.assertIn("{base-sha}", example)

    def test_landscape_compact_mode_routes_before_full_fetches(self):
        text = skill("landscape")
        section = text.split("## Resume mode", 1)[1].split("## What It Shows", 1)[0]
        self.assertIn("/landscape resume", text)
        for required in ("15 lines", "--summary-only", "next-bd --in-progress --avoid-busy", "working-copy.sh", "return", "No Jira", "Do not load", "unavailable", "unclassified", "session activity"):
            self.assertIn(required, section)
        self.assertNotIn("beads.sh", section)
        self.assertNotIn("--check-branches", section)
        template, = re.findall(r"```markdown\n(.*?)```", section, re.S)
        self.assertLessEqual(len(template.splitlines()), 15)
        self.assertEqual(template.count("**Next:**"), 1)
        for forbidden in ("Bash(git:*)", "Bash(gh:*)", "Write", "Edit", "next-select"):
            self.assertNotIn(forbidden, grants("landscape"))
        self.assertIn("next-bd", grants("landscape"))

    def test_landscape_keeps_existing_full_and_quick_modes(self):
        text = skill("landscape")
        for required in ("/landscape quick", "### 1. 📋 Jira", "### 2. 🔀 PRs", "### 4. 📍 Working copy", "Only the full/quick modes", "display order, not a selectable"):
            self.assertIn(required, text)

    def test_handoff_picker_counts_remaining_current_and_member_rows(self):
        text = skill("handoffs")
        for obsolete in ("Only pickable rows (✅)", "If `current_repo_total == 0`, skip this step", "between 1 and 4", "skip the pickable table and step 4"):
            self.assertNotIn(obsolete, text)
        for required in ("remaining displayed", "2–4", "one row", "Pruned-worktree handoffs are pickable", "CURRENT-REPO-KIND == dir", "workspace-member"):
            self.assertIn(required, text)

    def test_handoff_recovery_does_not_infer_history_or_consent(self):
        text = skill("handoffs")
        self.assertNotIn("the pruned worktree's commits are still in the repo", text)
        self.assertNotIn("the user opened this worktree *for* this handoff", text)
        for required in ("not proof", "explicit base", "not authorization", "Unknown client"):
            self.assertIn(required, text)

    def test_archive_assisted_exceptions_and_prompt_bounds_are_shared(self):
        reference = (ROOT / "skills/handoffs/REFERENCE.md").read_text()
        tidy = skill("handoffs-tidy")
        for required in ("2–4", "single candidate", "§Trunk-review", "§Age-review", "not preselected"):
            self.assertIn(required, reference)
        self.assertNotIn("Pre-check", tidy)
        self.assertNotIn("Handoffs go stale three ways", tidy)
        self.assertIn("assisted", tidy)
        self.assertIn("REFERENCE §Archive-flow", tidy)

    def test_matched_handoffs_have_shared_field_contract(self):
        reference = (ROOT / "skills/handoffs/REFERENCE.md").read_text()
        self.assertIn("---MATCHED-HANDOFFS---", reference)
        self.assertIn("{filename}|{date}|{time}|{slug}|{branch}|{exists}|{pr-state}|{pr-number}|{pr-url}", reference)
        self.assertIn("handoffs/REFERENCE.md", skill("landscape"))

    def test_client_convention_and_descriptive_only_name(self):
        text = skill("name-session")
        for required in ("Harness selection comes from the current tool surface.", "Never use the shell, PATH, filesystem, process list, or installed binaries", "{session-name}", "no leading hyphen", "next-select resolve", "bd -C <directory>"):
            self.assertIn(required, text)
        self.assertNotIn("/name {scope}-{descriptive}", text)
        self.assertNotIn("bd list --status=in_progress", text)
        self.assertNotIn("Bash(git branch:*)", grants("name-session"))

    def test_routing_uses_current_authority_and_no_brand_taxonomy(self):
        text = skill("model-update-check")
        self.assertIn("../../MODEL_ROUTING.md", text)
        for tier in ("economy", "standard", "premium"):
            self.assertIn(tier, text)
        for obsolete in ("cheap bulk", "focused/advanced", "Luna/Terra/Sol", "Haiku/Sonnet/Fable/Opus"):
            self.assertNotIn(obsolete, text)
        self.assertIn("read-only", text)

    def test_wrap_up_does_not_infer_task_branch_from_retained_worktrees(self):
        text = skill("wrap-up")
        self.assertNotIn("that branch is almost never", text)
        self.assertNotIn("That branch almost never", text)
        self.assertIn("trunk-based", text)
        self.assertIn("do not prove", text)

    def test_catalog_describes_real_side_effects_and_new_mode(self):
        catalog = (ROOT / "skills/README.md").read_text()
        rows = {line.split(" | ")[0].removeprefix("| "): line for line in catalog.splitlines() if line.startswith("| ")}
        for name, word in (("next", "claim"), ("wrap-up", "save"), ("handoffs", "confirmed"), ("landscape", "resume")):
            self.assertIn(word, rows[name])
        makefile = (ROOT / "Makefile").read_text()
        self.assertIn("test-session-boundaries", makefile)


if __name__ == "__main__":
    unittest.main()
