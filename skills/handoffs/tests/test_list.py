from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "list.sh"
HANDOFFS_SKILL = SKILL_DIR / "SKILL.md"
TIDY_SKILL = SKILL_DIR.parent / "handoffs-tidy" / "SKILL.md"
REFERENCE = SKILL_DIR / "REFERENCE.md"


class HandoffListFixture:
    def __init__(
        self,
        root: Path,
        pr_line: str | None = "",
        today: dt.date | None = None,
    ) -> None:
        self.root = root
        self.today = today or dt.date.today()
        self.home = root / "home"
        self.repo = root / "repo"
        self.handoffs = self.home / ".claude" / "handoffs"
        self.bin = root / "bin"
        self.handoffs.mkdir(parents=True)
        self.bin.mkdir()
        self.repo.mkdir()
        subprocess.run(["git", "init", "-b", "main", str(self.repo)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "--allow-empty", "-m", "init"], check=True, capture_output=True)
        gh = self.bin / "gh"
        if pr_line is None:
            gh.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        else:
            gh.write_text(f"#!/bin/sh\nprintf '%s\\n' '{pr_line}'\n", encoding="utf-8")
        gh.chmod(0o755)

    def add_workspace_member(self) -> Path:
        member = self.repo / "member"
        member.mkdir()
        subprocess.run(["git", "init", "-b", "main", str(member)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(member), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(member), "config", "user.name", "Test"], check=True)
        subprocess.run(
            ["git", "-C", str(member), "commit", "--allow-empty", "-m", "init"],
            check=True,
            capture_output=True,
        )
        (self.repo / ".mgit.conf").write_text("services=member\n", encoding="utf-8")
        return member

    def force_bsd_date_fallback(self) -> None:
        date = self.bin / "date"
        date.write_text(
            f"""#!{sys.executable}
import datetime as dt
import re
import sys

args = sys.argv[1:]
if "-d" in args:
    raise SystemExit(1)
if args[:3] != ["-j", "-f", "%Y-%m-%d"]:
    raise SystemExit(2)
rest = args[3:]
adjustment = next((arg for arg in rest if re.fullmatch(r"-v-[0-9]+d", arg)), None)
base = next((arg for arg in rest if re.fullmatch(r"[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}", arg)), None)
if base is None or (adjustment is not None and rest.index(adjustment) > rest.index(base)):
    raise SystemExit(2)
value = dt.date.fromisoformat(base)
if adjustment is not None:
    value -= dt.timedelta(days=int(adjustment[3:-1]))
print(value.isoweekday() if rest[-1] == "+%u" else value.isoformat())
""",
            encoding="utf-8",
        )
        date.chmod(0o755)

    def add_beads_store(self, *statuses: str) -> None:
        (self.repo / ".beads").mkdir()
        payload = "[" + ",".join(
            f'{{"status":"{status}"}}' for status in statuses or ("open",)
        ) + "]"
        bd = self.bin / "bd"
        bd.write_text(
            f"#!/bin/sh\nprintf '%s\\n' '{payload}'\n",
            encoding="utf-8",
        )
        bd.chmod(0o755)

    def add_handoff(
        self,
        age_days: int,
        slug: str,
        branch: str = "main",
        beads: str = "—",
        jira: str = "—",
        prs: str = "—",
        time: str = "12:00",
        header_time: bool = True,
        repo: Path | None = None,
    ) -> str:
        date = self.today - dt.timedelta(days=age_days)
        handoff_repo = repo or self.repo
        filename = f"{date.isoformat()}-{slug}.md"
        resume_header = f"# Resume: {slug} — {date.isoformat()} {time}" if header_time else f"# Resume: {slug}"
        (self.handoffs / filename).write_text(
            f"{resume_header}\n\n"
            f"**Where to pick up:** `{handoff_repo}` on branch `{branch}`\n"
            f"**Repo root:** `{handoff_repo}`\n"
            f"**Beads:** {beads}\n"
            f"**Jira:** {jira}\n"
            f"**PRs:** {prs}\n",
            encoding="utf-8",
        )
        return filename

    def set_mtime(self, filename: str, time: str) -> None:
        timestamp = dt.datetime.combine(dt.date.today(), dt.time.fromisoformat(time)).timestamp()
        os.utime(self.handoffs / filename, (timestamp, timestamp))

    def run(self, *args: str) -> str:
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["HANDOFFS_TODAY"] = self.today.isoformat()
        result = subprocess.run(
            [str(SCRIPT), "--check-branches", *args],
            cwd=self.repo,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout


def section(output: str, name: str) -> list[str]:
    marker = f"---{name}---"
    lines = output.splitlines()
    start = lines.index(marker) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("---")), len(lines))
    return lines[start:end]


class SupersedeOrderingTests(unittest.TestCase):
    def test_same_day_time_beats_numeric_topic_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            older = fixture.add_handoff(0, "ticket-123", branch="feature/work", time="09:00")
            newer = fixture.add_handoff(0, "follow-up", branch="feature/work", time="12:00")

            rows = {
                fields[0]: fields
                for fields in (line.split("|") for line in section(fixture.run(), "HANDOFFS"))
            }

            self.assertEqual(rows[older][7], newer)
            self.assertEqual(rows[older][13], "safe")
            self.assertEqual(rows[newer][7], "")
            self.assertEqual(rows[newer][13], "")

    def test_headerless_handoff_does_not_use_mtime_for_recency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            headerless = fixture.add_handoff(0, "ticket-123", branch="feature/work", header_time=False)
            fixture.set_mtime(headerless, "23:59")
            newer = fixture.add_handoff(0, "follow-up", branch="feature/work", time="12:00")

            rows = {
                fields[0]: fields
                for fields in (line.split("|") for line in section(fixture.run(), "HANDOFFS"))
            }

            self.assertEqual(rows[headerless][7], "")
            self.assertEqual(rows[newer][7], "")

    def test_collision_family_orders_same_minute_rewraps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            original = fixture.add_handoff(0, "resume", branch="feature/work")
            second = fixture.add_handoff(0, "resume-2", branch="feature/work")
            third = fixture.add_handoff(0, "resume-3", branch="feature/work")

            rows = {
                fields[0]: fields
                for fields in (line.split("|") for line in section(fixture.run(), "HANDOFFS"))
            }

            self.assertEqual(rows[original][7], third)
            self.assertEqual(rows[original][8], "branch")
            self.assertEqual(rows[second][7], third)
            self.assertEqual(rows[second][13], "safe")
            self.assertEqual(rows[third][7], "")


class ArchiveRetentionTests(unittest.TestCase):
    MONDAY = dt.date(2026, 8, 3)

    def test_recent_completed_handoff_is_retained_without_looking_live(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(
                Path(tmp),
                "feature/work\tmerged\t123\thttps://example.test/pr/123",
                today=self.MONDAY,
            )
            fixture.add_handoff(
                1,
                "recent-complete",
                branch="feature/work",
                jira="`ABC-123`",
            )

            output = fixture.run("--ticket", "ABC-123")
            fields = section(output, "HANDOFFS")[0].split("|")

            self.assertEqual(fields[10], "merged")
            self.assertEqual(fields[13], "")
            self.assertIn("current_repo_recent_live=0", section(output, "SUMMARY"))
            self.assertIn("current_repo_stale=0", section(output, "SUMMARY"))
            self.assertEqual(section(output, "CURRENT-REPO-LIVE"), [])
            self.assertEqual(section(output, "MATCHED-HANDOFFS"), [])

    def test_active_handoff_remains_live_and_matchable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp), today=self.MONDAY)
            filename = fixture.add_handoff(1, "active", jira="`ABC-123`")

            output = fixture.run("--ticket", "ABC-123")
            live = section(output, "CURRENT-REPO-LIVE")
            matched = section(output, "MATCHED-HANDOFFS")

            self.assertEqual(live, ["active|main|2026-08-02|12:00"])
            self.assertEqual(matched[0].split("|")[0], filename)
            self.assertIn("current_repo_recent_live=1", section(output, "SUMMARY"))

    def test_recent_stale_handoff_is_retained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(
                Path(tmp),
                "feature/work\tclosed\t123\thttps://example.test/pr/123",
                today=self.MONDAY,
            )
            fixture.add_handoff(1, "recent-stale", branch="feature/work")

            output = fixture.run()
            fields = section(output, "HANDOFFS")[0].split("|")

            self.assertEqual(fields[10], "closed")
            self.assertEqual(fields[13], "")
            self.assertIn("current_repo_recent_live=0", section(output, "SUMMARY"))
            self.assertIn("current_repo_stale=0", section(output, "SUMMARY"))

    def test_workspace_member_retention_uses_the_same_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(
                Path(tmp),
                "feature/complete\tmerged\t123\thttps://example.test/pr/123\n"
                "feature/old\tmerged\t124\thttps://example.test/pr/124",
                today=self.MONDAY,
            )
            member = fixture.add_workspace_member()
            recent = fixture.add_handoff(
                1,
                "member-recent",
                branch="feature/complete",
                repo=member,
            )
            old = fixture.add_handoff(
                4,
                "member-old",
                branch="feature/old",
                repo=member,
            )
            superseded = fixture.add_handoff(
                1,
                "member-first",
                branch="feature/superseded",
                repo=member,
            )
            newer = fixture.add_handoff(
                0,
                "member-second",
                branch="feature/superseded",
                repo=member,
            )

            rows = {
                fields[0]: fields
                for fields in (
                    line.split("|")
                    for line in section(fixture.run(), "WORKSPACE-MEMBER-HANDOFFS")
                )
            }

            self.assertEqual(rows[recent][13], "")
            self.assertEqual(rows[old][13], "safe")
            self.assertEqual(rows[superseded][7], newer)
            self.assertEqual(rows[superseded][13], "safe")

    def test_recent_superseded_handoff_remains_archivable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp), today=self.MONDAY)
            older = fixture.add_handoff(1, "first", branch="feature/work")
            newer = fixture.add_handoff(0, "second", branch="feature/work")

            rows = {
                fields[0]: fields
                for fields in (line.split("|") for line in section(fixture.run(), "HANDOFFS"))
            }

            self.assertEqual(rows[older][7], newer)
            self.assertEqual(rows[older][13], "safe")

    def test_friday_completed_handoff_is_retained_on_monday(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(
                Path(tmp),
                "feature/work\tmerged\t123\thttps://example.test/pr/123",
                today=self.MONDAY,
            )
            fixture.add_handoff(3, "friday-complete", branch="feature/work")

            output = fixture.run()
            fields = section(output, "HANDOFFS")[0].split("|")

            self.assertIn("3", section(output, "RECENT-WINDOW-DAYS"))
            self.assertEqual(fields[13], "")
            self.assertIn("current_repo_stale=0", section(output, "SUMMARY"))


class TrunkReviewClassificationTests(unittest.TestCase):
    def test_recent_partial_bead_closure_is_retained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(
                Path(tmp),
                today=ArchiveRetentionTests.MONDAY,
            )
            fixture.add_beads_store("closed", "open")
            fixture.add_handoff(1, "partial-closure", beads="`repo-closed`, `repo-open`")

            fields = section(fixture.run(), "HANDOFFS")[0].split("|")

            self.assertEqual(fields[19], "1/2")
            self.assertEqual(fields[20], "")

    def test_partial_bead_closure_still_needs_assisted_trunk_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.add_beads_store("closed", "open")
            fixture.add_handoff(40, "partial-closure", beads="`repo-closed`, `repo-open`")

            fields = section(fixture.run("--stale-days", "30"), "HANDOFFS")[0].split("|")

            self.assertEqual(fields[13], "")
            self.assertEqual(fields[19], "1/2")
            self.assertEqual(fields[20], "Y")
            self.assertEqual(fields[21], "")


class AgeReviewClassificationTests(unittest.TestCase):
    def test_old_unclassified_trunk_handoff_needs_assisted_age_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.add_handoff(40, "old-unclassified")

            output = fixture.run("--stale-days", "30")
            fields = section(output, "HANDOFFS")[0].split("|")

            self.assertEqual(len(fields), 22)
            self.assertEqual(fields[13], "")
            self.assertEqual(fields[20], "")
            self.assertEqual(fields[21], "Y")
            self.assertIn("current_repo_age_review=1", section(output, "SUMMARY"))
            self.assertIn("current_repo_stale=0", section(output, "SUMMARY"))

    def test_short_age_floor_cannot_expose_a_recent_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp), today=ArchiveRetentionTests.MONDAY)
            fixture.add_handoff(2, "still-recent")

            output = fixture.run("--stale-days", "1")
            fields = section(output, "HANDOFFS")[0].split("|")

            self.assertIn("3", section(output, "STALE-DAYS"))
            self.assertEqual(fields[21], "")

    def test_bsd_date_fallback_computes_cutoffs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp), today=ArchiveRetentionTests.MONDAY)
            fixture.force_bsd_date_fallback()
            fixture.add_handoff(4, "bsd-cutoff")

            output = fixture.run()
            fields = section(output, "HANDOFFS")[0].split("|")

            self.assertIn("2026-07-31", section(output, "CUTOFF"))
            self.assertEqual(fields[21], "Y")

    def test_default_age_floor_starts_after_the_recent_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp), today=ArchiveRetentionTests.MONDAY)
            fixture.add_handoff(4, "default-threshold")

            output = fixture.run()
            fields = section(output, "HANDOFFS")[0].split("|")

            self.assertIn("3", section(output, "STALE-DAYS"))
            self.assertEqual(fields[21], "Y")

    def test_recent_equivalent_is_not_offered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.add_handoff(10, "recent-unclassified")

            fields = section(fixture.run("--stale-days", "30"), "HANDOFFS")[0].split("|")

            self.assertEqual(fields[21], "")

    def test_handoff_at_the_age_floor_is_not_older_than_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.add_handoff(30, "at-threshold")

            fields = section(fixture.run("--stale-days", "30"), "HANDOFFS")[0].split("|")

            self.assertEqual(fields[21], "")

    def test_stale_days_changes_the_age_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.add_handoff(40, "threshold-controlled")

            fields = section(fixture.run("--stale-days", "45"), "HANDOFFS")[0].split("|")

            self.assertEqual(fields[21], "")

    def test_unknown_non_trunk_handoff_is_offered_for_age_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp), None)
            fixture.add_handoff(40, "feature-branch", branch="feature/work")

            fields = section(fixture.run("--stale-days", "30"), "HANDOFFS")[0].split("|")

            self.assertEqual(fields[9], "unknown")
            self.assertEqual(fields[21], "Y")

    def test_resolvable_bead_keeps_the_handoff_out_of_age_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.add_beads_store("open")
            fixture.add_handoff(40, "open-bead", beads="`repo-123`")

            fields = section(fixture.run("--stale-days", "30"), "HANDOFFS")[0].split("|")

            self.assertEqual(fields[19], "0/1")
            self.assertEqual(fields[21], "")

    def test_open_pr_is_not_offered_for_age_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp), "main\topen\t123\thttps://example.test/pr/123")
            fixture.add_handoff(40, "open-pr")

            fields = section(fixture.run("--stale-days", "30"), "HANDOFFS")[0].split("|")

            self.assertEqual(fields[10], "open")
            self.assertEqual(fields[21], "")

    def test_unknown_pr_state_without_a_recorded_pr_still_gets_assisted_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp), None)
            fixture.add_handoff(40, "offline-pr-state")

            fields = section(fixture.run("--stale-days", "30"), "HANDOFFS")[0].split("|")

            self.assertEqual(fields[10], "unknown")
            self.assertEqual(fields[21], "Y")

    def test_unknown_pr_state_with_a_recorded_pr_is_not_offered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp), None)
            fixture.add_handoff(40, "recorded-pr", prs="#123")

            fields = section(fixture.run("--stale-days", "30"), "HANDOFFS")[0].split("|")

            self.assertEqual(fields[10], "unknown")
            self.assertEqual(fields[21], "")

    def test_successful_empty_pr_lookup_does_not_override_a_recorded_pr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.add_handoff(40, "recorded-pr", prs="#123")

            fields = section(fixture.run("--stale-days", "30"), "HANDOFFS")[0].split("|")

            self.assertEqual(fields[10], "none")
            self.assertEqual(fields[21], "")

    def test_ticketed_old_handoff_remains_available_for_jira_done_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.add_handoff(40, "ticketed", jira="`ABC-123`")

            fields = section(fixture.run("--stale-days", "30"), "HANDOFFS")[0].split("|")

            self.assertEqual(fields[16], "`ABC-123`")
            self.assertEqual(fields[21], "Y")

    def test_both_skills_delegate_age_review_to_the_shared_reference(self) -> None:
        reference = REFERENCE.read_text(encoding="utf-8")
        handoffs = HANDOFFS_SKILL.read_text(encoding="utf-8")
        tidy = TIDY_SKILL.read_text(encoding="utf-8")

        self.assertIn("## §Age-review", reference)
        self.assertIn("REFERENCE §Age-review", handoffs)
        self.assertIn("REFERENCE §Age-review", tidy)
        self.assertIn("mcp__jira__jira_get", handoffs)
        self.assertIn("§1a produced no older Jira-Done", handoffs)
        self.assertIn("A recent Jira-Done row stays retained", reference)
        self.assertIn("never auto-selected", reference)
        self.assertIn("never auto-archived", reference)
        self.assertIn("Used by `/handoffs` and `/handoffs-tidy`", reference)
        self.assertIn("§Archive-flow-members", handoffs)
        self.assertIn("offer only `safe` rows", handoffs)
        self.assertIn("per-member confirmation", handoffs)
        self.assertIn("one question per member repo", reference)
        self.assertIn("Only `safe` rows are offered here.", reference)
        self.assertIn("A recent row is also", reference)
        self.assertIn("Supersede remains immediately `safe`", reference)
        self.assertIn("inside the recent grace window", tidy)


if __name__ == "__main__":
    unittest.main()
