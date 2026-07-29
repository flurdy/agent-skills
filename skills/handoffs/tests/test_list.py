from __future__ import annotations

import datetime as dt
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "list.sh"
HANDOFFS_SKILL = SKILL_DIR / "SKILL.md"
TIDY_SKILL = SKILL_DIR.parent / "handoffs-tidy" / "SKILL.md"
REFERENCE = SKILL_DIR / "REFERENCE.md"


class HandoffListFixture:
    def __init__(self, root: Path, pr_line: str | None = "") -> None:
        self.root = root
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

    def add_beads_store(self, status: str = "open") -> None:
        (self.repo / ".beads").mkdir()
        bd = self.bin / "bd"
        bd.write_text(
            f"#!/bin/sh\nprintf '%s\\n' '[{{\"status\":\"{status}\"}}]'\n",
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
    ) -> str:
        date = dt.date.today() - dt.timedelta(days=age_days)
        filename = f"{date.isoformat()}-{slug}.md"
        (self.handoffs / filename).write_text(
            f"# Resume: {slug} — {date.isoformat()} 12:00\n\n"
            f"**Where to pick up:** `{self.repo}` on branch `{branch}`\n"
            f"**Repo root:** `{self.repo}`\n"
            f"**Beads:** {beads}\n"
            f"**Jira:** {jira}\n"
            f"**PRs:** {prs}\n",
            encoding="utf-8",
        )
        return filename

    def run(self, *args: str) -> str:
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["PATH"] = f"{self.bin}:{env['PATH']}"
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

    def test_default_age_floor_is_30_days(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.add_handoff(40, "default-threshold")

            fields = section(fixture.run(), "HANDOFFS")[0].split("|")

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

    def test_non_trunk_handoff_is_not_offered_for_age_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.add_handoff(40, "feature-branch", branch="feature/work")

            fields = section(fixture.run("--stale-days", "30"), "HANDOFFS")[0].split("|")

            self.assertEqual(fields[21], "")

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
        self.assertIn("§1a produced no Jira-Done", handoffs)
        self.assertIn("promotion is itself an effective Done candidate", reference)
        self.assertIn("never auto-selected", reference)
        self.assertIn("never auto-archived", reference)


if __name__ == "__main__":
    unittest.main()
