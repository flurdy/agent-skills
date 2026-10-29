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
    def test_backlog_groom_binds_workspace_stores_and_unfinished_statuses(self):
        text = " ".join(skill("backlog-groom").split())
        for boundary in (
            "/backlog-groom workspace",
            "open,in_progress,blocked,deferred",
            "next-select stores",
            "deduplicate by the returned canonical `directory`",
            "`workspace: true` selects workspace mode by default",
            "`workspace: false` selects the local open-only default",
            "/backlog-groom local",
            "An explicit `local` override narrows the scope",
            "No recursive filesystem discovery",
            "unavailable stores",
            "Missing evidence is not a clean backlog",
            "never synchronize",
        ):
            with self.subTest(boundary=boundary):
                self.assertTrue(boundary in text, f"missing grooming scope boundary: {boundary}")
        catalog = (ROOT / "skills/README.md").read_text()
        row = next(line for line in catalog.splitlines() if line.startswith("| backlog-groom |"))
        self.assertIn("workspace", row)
        self.assertIn("unfinished", row)

    def test_backlog_groom_qualifies_commands_and_preserves_apply_gates(self):
        text = skill("backlog-groom")
        normalized = " ".join(text.split())
        for boundary in (
            "not approval for label edits",
            "fresh `next-select resolve`",
            "If status, ownership, or relevant content changed",
            "per-store duplicate coverage",
            "Do not pass the list's comma-separated status filter",
            "Do not use `--skip-labels` or `--brief`",
        ):
            with self.subTest(boundary=boundary):
                self.assertTrue(boundary in normalized, f"missing grooming safety boundary: {boundary}")
        commands = re.findall(r"(?m)^bd .*", text)
        self.assertTrue(commands)
        for command in commands:
            self.assertTrue(command.startswith("bd -C <directory> "), command)
            self.assertIn("--readonly", command)
            if "find-duplicates" in command:
                self.assertNotIn("--status", command)
            if " stale " in command:
                self.assertIn("--status=<one-status>", command)
                self.assertNotIn("open,in_progress", command)
        self.assertIn("next-select stores", grants("backlog-groom"))
        self.assertNotIn("Bash(bd:*)", grants("backlog-groom"))

    def test_response_endings_separate_user_actions_from_next_summaries(self):
        triage = " ".join(skill("triage").split())
        for boundary in (
            "Creating or refining a bead never implies starting work in this session",
            "Put the actual question or required user action in a separate",
            "before the final line",
            "Awaiting ownership clarification.",
            "It promises no automatic continuation",
            "Do not propose claiming, starting, or implementing the bead",
        ):
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, triage)
        refine = skill("refine")
        self.assertIn("The handoff is never executed from here", refine)
        self.assertIn("before the final `Next` summary", refine)
        self.assertNotIn("The `Next` line is the only handoff", refine)
        groom = skill("backlog-groom")
        self.assertIn("To request changes:", groom)
        self.assertIn("**Next:** Grooming proposals await selection.", groom)
        self.assertIn("**Next:** Nothing required.", groom)
        for name in ("triage", "refine", "backlog-groom", "wrap-up"):
            for line in skill(name).splitlines():
                if line.startswith("**Next:**"):
                    with self.subTest(skill=name, line=line):
                        self.assertNotIn("/", line)

    def test_response_formatting_preserves_strict_output_and_read_only_boundaries(self):
        guide = " ".join((ROOT / "CONTRIBUTING.md").read_text().split())
        self.assertIn("Exact/verbatim output and final protocol-line contracts take precedence", guide)
        self.assertIn("required question and confirmation tools", guide)
        closeout = " ".join((ROOT / "skills/outstanding-work/references/ticket-closeout.md").read_text().split())
        self.assertIn("separate short list or command block", closeout)
        self.assertIn("Never update Jira, post comments, close tracking, merge, push", closeout)

    def test_coding_skill_reads_continue_without_a_user_prompt(self):
        for name in ("develop", "implement-solution"):
            with self.subTest(skill=name):
                text = " ".join(skill(name).split())
                for boundary in ("not a new user message", "Never mutate in the same response that loads the skill"):
                    self.assertTrue(boundary in text, f"missing routing boundary: {boundary}")

    def test_verification_distinguishes_standalone_and_composed_handoffs(self):
        text = " ".join(skill("verify-task").split())
        for boundary in (
            "Standalone (default)",
            "already-authorized broader task",
            "owning workflow, not this verification pass",
            "without requiring another user message solely to continue",
            "existing scope and approval gates",
            "Partial or stale proof still blocks finalization",
            "deferred-verification tracking handoff",
            "only when every other requirement is met",
            "Any failed, stale, not-run check",
            "Never create, defer or close a bead in verification",
            "not completion approval",
            "No automatic fixes",
        ):
            with self.subTest(boundary=boundary):
                self.assertTrue(boundary in text, f"missing verification boundary: {boundary}")
        for forbidden in ("Write", "Edit", "Skill(", "Bash(git:*)", "Bash(bd update"):
            self.assertNotIn(forbidden, grants("verify-task"))

    def test_next_continues_selected_bead_without_widening_authority(self):
        text = " ".join(skill("next").split())
        for obsolete in ("Continue fixing bugs", "Minor Bug Criteria", "Context Continuity", "and fix it", "Show top 5 candidates", "Selection ends after one claim", "implementation needs a separate user request"):
            self.assertNotIn(obsolete, text)
        for boundary in (
            "Claim once",
            "Continue into that bead's work in the same turn",
            "Do not ask for confirmation merely to start work after the selection",
            "Never select a second bead automatically",
            "The tracker claim grants no additional authority",
            "native Edit/Write acquire the canonical worktree lease automatically",
            "do not request a redundant `/implement` command",
            "Never bypass a denied operation through shell scripts or another worktree",
        ):
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, text)
        for forbidden in ("Write", "Edit", "Skill(", "Bash(git", "Bash(gh", "Bash(bd update"):
            self.assertNotIn(forbidden, grants("next"))
        self.assertIn("next-select start", text)
        self.assertIn("session activity unverified", text)

    def test_next_shows_details_before_work_and_loads_its_workflow(self):
        text = " ".join(skill("next").split())
        details = text.index("Repeat the full bead details and first step in a visible commentary message")
        continuation = text.index("Continue into that bead's work in the same turn")
        self.assertLess(details, continuation)
        for boundary in (
            "Do not rely on the collapsed tool output; do not end the turn here",
            "including implementation when that is the selected outcome",
            "a read-only investigation or decision bead stays read-only",
            "[develop](../develop/SKILL.md) in a separate tool call before any edit",
            "Do not implement directly under the listing skill's economy route",
            "never force a route or waive billing consent",
            "The user's selection (or explicit auto-pick mode) requests work on that one bead",
        ):
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, text)

    def test_next_preserves_listing_and_selection_checks(self):
        text = " ".join(skill("next").split())
        for boundary in (
            "Never auto-pick in this mode",
            "Listing mode never marks anything `in_progress`",
            "require explicit confirmation before starting",
            "When a live handoff remains, ask with `AskUserQuestion` before starting",
            "Show the selected bug and continue into `/diagnose-bug` in the same turn",
            "Follow its investigation boundary",
        ):
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, text)

    def test_next_safe_pick_rechecks_then_claims_unchecked_work_as_ordinary(self):
        text = " ".join(skill("next").split())
        self.assertNotIn("Do not infer either approval from choosing a review row", text)
        recheck = text.index('`{"action":"recheck","selector":"<owner>:<id>"}` immediately before the tracking claim')
        claim = text.index("Claim with `next-select start <owner>:<id> --expect-id <id>`")
        self.assertLess(recheck, claim)
        for boundary in (
            "Every pick from the safe view runs the normal handoff check",
            "| Error (no longer ready, owning source unreadable) | Stop and show the error; do not claim |",
            "| `occupied` (`held` or `held (label)`) | Stop and show the holder; do not claim |",
            "| Non-empty `tracker_overlap` in any queue | Held back: show the shared service and ask before claiming |",
            "| `eligible` | Safe claim |",
            "| `unknown` or `unavailable` without overlap | Ordinary claim; disclose the gap in one line |",
            "For a stopped row, do not claim via a fallback such as an ordinary `next-select start`",
            "do not ask again to approve the same disclosed fact",
            "lease safety was not checked",
            "Never call it safe or free",
            "no automatic metadata backfill",
            "a held-back row still needs its advisory conflict reviewed first",
        ):
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, text)
        reference = " ".join((ROOT / "skills/next/references/source-scope.md").read_text().split())
        self.assertIn("never as safe. Metadata backfill is never inferred from a pick", reference)
        self.assertNotIn("separately confirmed ordinary selection", reference)

    def test_wrap_up_writes_handoffs_not_tracker_or_settings(self):
        text = skill("wrap-up")
        self.assertIn("Bash(~/.agents/skills/wrap-up/scripts/save-handoff.py:*)", grants("wrap-up"))
        self.assertIn("save_handoff", grants("wrap-up"))
        self.assertIn("Do not fall back to Bash, native file tools", text)
        for forbidden in ("Write", "handoff-path.sh", "Bash(bd update", "Skill(", "archive.sh"):
            self.assertNotIn(forbidden, grants("wrap-up"))
        for obsolete in ("bd update {id}", "--status=ready", "invoke the `tidy-settings` skill", "Run /tidy-settings** →", "After any demotions"):
            self.assertNotIn(obsolete, text)
        for required in ("session activity is unverified", "does not change tracker status", "report-only", "auto-save", "collision", "wrap-up-save/v1"):
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

    def test_landscape_review_requests_are_full_mode_only_and_degrade(self):
        text = skill("landscape")
        section = text.split("### 2b. 👀 Review requests", 1)[1].split("### 3. 🎯 Beads", 1)[0]
        for required in ("Full mode only", "quick", "make no request", "gh-pr-review-requests.py --timeout 60", "No open PRs requesting your review", "Review requests unavailable", "Incomplete", "ciHeadSha == headSha"):
            self.assertIn(required, section)
        self.assertNotIn("--state-stdin", section.split("```bash", 1)[1].split("```", 1)[0])
        self.assertNotIn("gh-pr-review-requests", text.split("## Resume mode", 1)[1].split("## What It Shows", 1)[0])
        self.assertIn("Bash(~/.agents/skills/pr-status/scripts/gh-pr-review-requests.py:*)", grants("landscape"))

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
