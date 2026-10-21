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
ARCHIVE_SCRIPT = SKILL_DIR / "scripts" / "archive.sh"
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
        self.handoffs = self.home / ".agents" / "handoffs"
        self.legacy = self.home / ".claude" / "handoffs"
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
        directory: Path | None = None,
    ) -> str:
        date = self.today - dt.timedelta(days=age_days)
        handoff_repo = repo or self.repo
        filename = f"{date.isoformat()}-{slug}.md"
        resume_header = f"# Resume: {slug} — {date.isoformat()} {time}" if header_time else f"# Resume: {slug}"
        target = directory or self.handoffs
        target.mkdir(parents=True, exist_ok=True)
        (target / filename).write_text(
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

    def environment(self) -> dict[str, str]:
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["HANDOFFS_TODAY"] = self.today.isoformat()
        return env

    def run_script(self, script: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(script), *args],
            cwd=cwd or self.repo,
            env=self.environment(),
            text=True,
            capture_output=True,
            check=False,
        )

    def run(self, *args: str, cwd: Path | None = None) -> str:
        result = self.run_script(SCRIPT, "--check-branches", *args, cwd=cwd)
        result.check_returncode()
        return result.stdout


def section(output: str, name: str) -> list[str]:
    marker = f"---{name}---"
    lines = output.splitlines()
    start = lines.index(marker) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("---")), len(lines))
    return lines[start:end]


class StorageLocationTests(unittest.TestCase):
    def test_canonical_storage_is_reported_and_listed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            filename = fixture.add_handoff(0, "ready")
            output = fixture.run()
            self.assertEqual(section(output, "HANDOFFS-DIR"), [str(fixture.handoffs)])
            self.assertEqual(section(output, "STORAGE"), ["canonical"])
            self.assertTrue(any(row.startswith(f"{filename}|") for row in section(output, "HANDOFFS")))

    def test_canonical_rows_carry_their_source_and_exact_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            filename = fixture.add_handoff(0, "ready")
            output = fixture.run()
            fields = section(output, "HANDOFFS")[0].split("|")
            self.assertEqual(fields[22:], ["canonical", str(fixture.handoffs / filename)])
            self.assertEqual(
                section(output, "SOURCES"),
                [f"canonical|{fixture.handoffs}|ok|1", f"legacy|{fixture.legacy}|absent|0"],
            )
            self.assertEqual(section(output, "SOURCE-COLLISIONS"), [])

    def test_legacy_only_storage_is_listed_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.handoffs.rmdir()
            filename = fixture.add_handoff(0, "old-thread", beads="repo-1", directory=fixture.legacy)
            result = fixture.run_script(SCRIPT, "--check-branches", "--bead", "repo-1")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("read-only", result.stderr)
            self.assertEqual(section(result.stdout, "STORAGE"), ["legacy"])
            fields = section(result.stdout, "HANDOFFS")[0].split("|")
            self.assertEqual(fields[0], filename)
            self.assertEqual(fields[22:], ["legacy", str(fixture.legacy / filename)])
            matched = section(result.stdout, "MATCHED-HANDOFFS")
            self.assertEqual(len(matched), 1)
            self.assertEqual(matched[0].split("|")[9:], ["legacy", str(fixture.legacy / filename)])
            summary = section(result.stdout, "SUMMARY")
            self.assertIn("total=1", summary)
            self.assertIn("legacy_total=1", summary)

    def test_mixed_storage_keeps_same_named_rows_apart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            different = fixture.add_handoff(1, "shared", branch="feature/x", time="09:00")
            fixture.add_handoff(1, "shared", branch="feature/x", time="08:00", directory=fixture.legacy)
            identical = fixture.add_handoff(2, "copied")
            (fixture.legacy / identical).write_bytes((fixture.handoffs / identical).read_bytes())
            result = fixture.run_script(SCRIPT, "--check-branches")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(section(result.stdout, "STORAGE"), ["mixed"])
            rows = [line.split("|") for line in section(result.stdout, "HANDOFFS")]
            shared = [fields for fields in rows if fields[0] == different]
            self.assertEqual([fields[22] for fields in shared], ["canonical", "legacy"])
            self.assertEqual(
                [fields[23] for fields in shared],
                [str(fixture.handoffs / different), str(fixture.legacy / different)],
            )
            self.assertEqual([fields[7] for fields in shared], ["", ""])
            self.assertEqual(
                sorted(section(result.stdout, "SOURCE-COLLISIONS")),
                sorted([f"{different}|different", f"{identical}|identical"]),
            )
            summary = section(result.stdout, "SUMMARY")
            self.assertIn("source_collisions=2", summary)
            self.assertIn("legacy_total=2", summary)

    def test_newer_canonical_thread_still_supersedes_an_older_legacy_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            older = fixture.add_handoff(5, "topic", directory=fixture.legacy)
            newer = fixture.add_handoff(0, "topic")
            rows = {
                fields[0]: fields
                for fields in (line.split("|") for line in section(fixture.run(), "HANDOFFS"))
            }
            self.assertEqual(rows[older][7], newer)
            self.assertEqual(rows[older][22], "legacy")

    def test_neither_location_is_an_empty_canonical_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.handoffs.rmdir()
            result = fixture.run_script(SCRIPT, "--check-branches")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(section(result.stdout, "STORAGE"), ["canonical"])
            self.assertEqual(section(result.stdout, "HANDOFFS"), [])
            self.assertIn("total=0", section(result.stdout, "SUMMARY"))

    def test_symlinked_location_is_not_followed_and_reports_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            kept = fixture.add_handoff(0, "kept")
            elsewhere = Path(tmp) / "elsewhere"
            linked = fixture.add_handoff(0, "linked", directory=elsewhere)
            fixture.legacy.parent.mkdir(parents=True)
            fixture.legacy.symlink_to(elsewhere, target_is_directory=True)
            result = fixture.run_script(SCRIPT, "--check-branches")
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertIn("partial", result.stderr)
            self.assertEqual(section(result.stdout, "STORAGE"), ["partial"])
            self.assertIn(f"legacy|{fixture.legacy}|unsafe|0", section(result.stdout, "SOURCES"))
            files = [line.split("|")[0] for line in section(result.stdout, "HANDOFFS")]
            self.assertEqual(files, [kept])
            self.assertNotIn(linked, result.stdout)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores directory permissions")
    def test_unreadable_location_reports_partial_not_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.add_handoff(0, "hidden")
            fixture.handoffs.chmod(0)
            try:
                result = fixture.run_script(SCRIPT, "--check-branches")
            finally:
                fixture.handoffs.chmod(0o700)
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertEqual(section(result.stdout, "STORAGE"), ["partial"])
            self.assertIn(f"canonical|{fixture.handoffs}|unreadable|0", section(result.stdout, "SOURCES"))

    def test_workspace_member_rows_keep_the_member_path_last(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            member = fixture.add_workspace_member()
            filename = fixture.add_handoff(0, "member-row", repo=member, directory=fixture.legacy)
            fields = section(fixture.run(), "WORKSPACE-MEMBER-HANDOFFS")[0].split("|")
            self.assertEqual(len(fields), 26)
            self.assertEqual(fields[22:24], ["legacy", str(fixture.legacy / filename)])
            self.assertEqual(fields[-1], str(member))

    def test_archive_moves_within_canonical_storage_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            filename = fixture.add_handoff(1, "done")
            result = fixture.run_script(ARCHIVE_SCRIPT, filename, "missing.md")
            self.assertEqual(result.returncode, 0, result.stderr)
            archive = fixture.handoffs / "archive"
            self.assertEqual(section(result.stdout, "ARCHIVE-DIR"), [str(archive)])
            self.assertEqual(section(result.stdout, "ARCHIVED"), [f"{filename}|{archive / filename}"])
            self.assertEqual(section(result.stdout, "SKIPPED"), ["missing.md|not found"])
            self.assertTrue((archive / filename).is_file())

    def test_archive_refuses_while_legacy_storage_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            filename = fixture.add_handoff(1, "done")
            (fixture.home / ".claude" / "handoffs").mkdir(parents=True)
            result = fixture.run_script(ARCHIVE_SCRIPT, filename)
            self.assertEqual(result.returncode, 3)
            self.assertEqual(section(result.stdout, "ARCHIVED"), [])
            self.assertEqual(section(result.stdout, "SKIPPED"), [f"{filename}|legacy handoff storage present; migrate first"])
            self.assertTrue((fixture.handoffs / filename).is_file())
            self.assertFalse((fixture.handoffs / "archive").exists())


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
            self.assertEqual(rows[recent][21], "")
            self.assertEqual(rows[old][13], "safe")
            self.assertEqual(rows[old][21], "")
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

            self.assertEqual(len(fields), 24)
            self.assertEqual(fields[13], "")
            self.assertEqual(fields[20], "")
            self.assertEqual(fields[21], "Y")
            self.assertIn("current_repo_age_review=1", section(output, "SUMMARY"))
            self.assertIn("current_repo_stale=0", section(output, "SUMMARY"))

    def test_old_workspace_member_handoff_needs_assisted_age_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            member = fixture.add_workspace_member()
            filename = fixture.add_handoff(40, "old-member-unclassified", repo=member)

            output = fixture.run("--stale-days", "30")
            rows = {
                fields[0]: fields
                for fields in (
                    line.split("|")
                    for line in section(output, "WORKSPACE-MEMBER-HANDOFFS")
                )
            }

            self.assertEqual(rows[filename][13], "")
            self.assertEqual(rows[filename][21], "Y")
            self.assertIn("current_repo_age_review=0", section(output, "SUMMARY"))
            self.assertIn("workspace_member_age_review=1", section(output, "SUMMARY"))

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

    def test_successful_empty_pr_lookup_leaves_a_recorded_pr_reviewable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.add_handoff(40, "recorded-pr", prs="#123")

            fields = section(fixture.run("--stale-days", "30"), "HANDOFFS")[0].split("|")

            self.assertEqual(fields[10], "none")
            self.assertEqual(fields[21], "Y")

    def test_ticketed_old_handoff_remains_available_for_jira_done_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.add_handoff(40, "ticketed", jira="`ABC-123`")

            fields = section(fixture.run("--stale-days", "30"), "HANDOFFS")[0].split("|")

            self.assertEqual(fields[16], "`ABC-123`")
            self.assertEqual(fields[21], "Y")

    def test_workspace_member_selection_names_the_supported_workspace_flow(self) -> None:
        handoffs = HANDOFFS_SKILL.read_text(encoding="utf-8")

        self.assertIn("This is a workspace-member handoff for `{member-display}`.", handoffs)
        self.assertIn("**Switch first:** `cd {member-path}`", handoffs)
        self.assertIn("cannot pick handoffs from unrelated repos", handoffs)
        self.assertNotIn(
            "This handoff belongs to `{member-display}`, not the repo you're in.",
            handoffs,
        )

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
        self.assertIn("## §Age-review-members", reference)
        self.assertIn("REFERENCE §Age-review-members", handoffs)
        self.assertIn("REFERENCE §Age-review-members", tidy)
        self.assertIn("offer only `safe` rows", handoffs)
        self.assertIn("per-member confirmation", handoffs)
        self.assertIn("one question per member repo", reference)
        self.assertIn("Only `safe` rows are offered here.", reference)
        self.assertIn("A recent row is also", reference)
        self.assertIn("Supersede remains immediately `safe`", reference)
        self.assertIn("inside the recent grace window", tidy)


class DirectoryIdentityTests(unittest.TestCase):
    """Outside any git repo the directory itself is the identity, so handoffs
    written from a non-git workspace root are pickable from that directory."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fixture = HandoffListFixture(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_non_repo_directory_matches_its_own_handoffs(self) -> None:
        plain = self.root / "workspace"
        plain.mkdir()
        mine = self.fixture.add_handoff(0, "workspace-thread", repo=plain)
        theirs = self.fixture.add_handoff(1, "repo-thread")
        output = self.fixture.run(cwd=plain)

        self.assertEqual(section(output, "CURRENT-REPO"), [f"dir:{plain.resolve()}"])
        self.assertEqual(section(output, "CURRENT-REPO-DISPLAY"), ["workspace"])
        self.assertEqual(section(output, "CURRENT-REPO-KIND"), ["dir"])
        rows = {line.split("|")[0]: line.split("|") for line in section(output, "HANDOFFS")}
        self.assertEqual(rows[mine][5], f"dir:{plain.resolve()}")
        self.assertEqual(rows[mine][9], "unknown")
        self.assertNotEqual(rows[theirs][5], f"dir:{plain.resolve()}")
        summary = dict(line.split("=", 1) for line in section(output, "SUMMARY"))
        self.assertEqual(summary["current_repo_total"], "1")
        self.assertEqual(summary["unresolved"], "0")
        self.assertIn("repo", [line.split("|")[2] for line in section(output, "OTHER-REPOS")])

    def test_non_repo_handoff_is_another_directory_from_inside_a_repo(self) -> None:
        plain = self.root / "workspace"
        plain.mkdir()
        self.fixture.add_handoff(0, "workspace-thread", repo=plain)
        output = self.fixture.run()

        self.assertEqual(section(output, "CURRENT-REPO-KIND"), ["repo"])
        self.assertIn("workspace", [line.split("|")[2] for line in section(output, "OTHER-REPOS")])

    def test_pruned_non_repo_path_stays_unresolved(self) -> None:
        gone = self.root / "gone"
        self.fixture.add_handoff(0, "gone-thread", repo=gone)
        output = self.fixture.run()

        rows = section(output, "HANDOFFS")
        self.assertEqual(rows[0].split("|")[5], "UNRESOLVED")


class RecordEncodingTests(unittest.TestCase):
    """Records are pipe-delimited and REFERENCE.md parses them by field position,
    so free text carrying a delimiter must not shift what a later field means."""

    HANDOFF_FIELDS = 24

    def test_pipe_in_branch_cannot_shift_record_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.add_handoff(0, "evil", branch="main|N|Y|safe")

            rows = section(fixture.run(), "HANDOFFS")

            self.assertEqual(len(rows), 1)
            self.assertEqual(len(rows[0].split("|")), self.HANDOFF_FIELDS)

    def test_pipe_does_not_forge_the_archive_class_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            # 'safe' is what /handoffs-tidy will archive without further checks.
            fixture.add_handoff(0, "evil", branch="main|x|x|x|x|x|x|x|x|x|safe")

            fields = section(fixture.run(), "HANDOFFS")[0].split("|")

            self.assertEqual(len(fields), self.HANDOFF_FIELDS)
            self.assertNotEqual(fields[13], "safe")

    def test_clean_records_keep_their_field_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = HandoffListFixture(Path(tmp))
            fixture.add_handoff(0, "ordinary", branch="feature/work")

            fields = section(fixture.run(), "HANDOFFS")[0].split("|")

            self.assertEqual(len(fields), self.HANDOFF_FIELDS)
            self.assertEqual(fields[4], "feature/work")


if __name__ == "__main__":
    unittest.main()
