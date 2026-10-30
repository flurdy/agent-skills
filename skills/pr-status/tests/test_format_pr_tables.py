"""Deterministic dashboard formatting: layout, truncation, escaping and Sync presentation."""

import json
import subprocess
import sys
import unicodedata
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
FORMAT = SKILL / "scripts" / "format-pr-tables.py"
NOW = "2026-10-19T16:00:00Z"
URL = "https://github.com/acme/widgets/pull/{}"
OPEN_COLUMNS = ["PR", "Ticket", "Jira 💬", "Title", "Branch", "Target", "Ready", "Push", "Sync", "CI",
                "Approved", "Threads", "LGTM"]
CLOSED_COLUMNS = ["PR", "Repo", "Ticket", "Jira 💬", "Title", "Status", "CI", "Ready", "Wait", "Closed"]


def visible_width(text):
    total = 0
    for char in text:
        if unicodedata.combining(char) or char in "\u200d\ufe0f\ufe0e":
            continue
        total += 2 if unicodedata.east_asian_width(char) in "WF" else 1
    return total


def open_pr(number, **overrides):
    row = {
        "number": number, "owner": "acme", "repo": "widgets",
        "title": f"feat(web): AB-{number} change the thing",
        "branch": f"feat/AB-{number}-change-the-thing", "base": "main", "isDraft": False,
        "mergeable": "MERGEABLE", "mergeState": "CLEAN", "behindBy": 0,
        "reviewDecision": "REVIEW_REQUIRED", "approvers": [], "reviewRequestCount": 0,
        "unresolvedThreads": 0, "checksState": "SUCCESS",
        "lastPush": "2026-10-19T14:00:00Z", "readyAt": "2026-10-17T16:00:00Z",
        "jira": {"total": 7, "author": "Ivar Abrahamsen", "created": "2026-10-17T15:00:00Z"},
    }
    row.update(overrides)
    return row


def closed_pr(number, **overrides):
    row = {
        "number": number, "owner": "acme", "repo": "widgets",
        "title": f"feat(web): AB-{number} ship it", "closedAt": "2026-10-18T16:00:00Z",
        "readyAt": "2026-10-16T04:00:00Z", "mergeCommitSha": "abc123",
        "mergeCommitAt": "2026-10-18T16:00:00Z", "mainChecksState": "SUCCESS", "jira": None,
    }
    row.update(overrides)
    return row


def render(open_rows=(), closed_rows=()):
    payload = {"now": NOW, "open": list(open_rows), "closed": list(closed_rows)}
    result = subprocess.run([sys.executable, "-I", str(FORMAT)], input=json.dumps(payload),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return result.stdout


def table_rows(markdown, columns):
    header = "| " + " | ".join(columns) + " |"
    lines = markdown.splitlines()
    start = lines.index(header)
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip().strip("|").split(" | ")])
    return rows


def cells(markdown, columns, number):
    for row in table_rows(markdown, columns):
        if row[0] == f"#{number}":
            return dict(zip(columns, row, strict=True))
    raise AssertionError(f"#{number} missing from table")


class SyncPresentationTests(unittest.TestCase):
    def test_behind_is_icon_only_regardless_of_merge_state(self):
        rows = [open_pr(1, mergeState="BLOCKED", behindBy=6), open_pr(2, mergeState="BEHIND", behindBy=None),
                open_pr(3, mergeState="BLOCKED", behindBy=1, reviewDecision="APPROVED", approvers=["alice"])]
        out = render(rows)
        for number in (1, 2, 3):
            with self.subTest(number=number):
                self.assertEqual(cells(out, OPEN_COLUMNS, number)["Sync"], "⏪")
        self.assertNotIn("behind", out.lower())
        self.assertNotIn("⚠️ 6", out)

    def test_conflict_outranks_behind_and_other_states_are_unchanged(self):
        rows = [open_pr(1, mergeable="CONFLICTING", behindBy=4), open_pr(2, mergeState="DIRTY", mergeable=None),
                open_pr(3), open_pr(4, mergeState="BLOCKED", mergeable="UNKNOWN", behindBy=None),
                open_pr(5, mergeState="BLOCKED", behindBy=None)]
        out = render(rows)
        expected = {1: "💥 conflict", 2: "💥 conflict", 3: "✅", 4: "?", 5: "?"}
        for number, cell in expected.items():
            with self.subTest(number=number):
                self.assertEqual(cells(out, OPEN_COLUMNS, number)["Sync"], cell)
        self.assertNotIn("| — |", "".join(f"| {cells(out, OPEN_COLUMNS, n)['Sync']} |" for n in expected))


class LayoutTests(unittest.TestCase):
    def test_pr_cell_is_plain_and_links_live_below_the_table(self):
        out = render([open_pr(7433)])
        row = cells(out, OPEN_COLUMNS, 7433)
        self.assertEqual(row["PR"], "#7433")
        for line in out.splitlines():
            if line.startswith("|"):
                self.assertNotIn("http", line)
        self.assertIn(f"[#7433]({URL.format(7433)})", out)

    def test_stacked_target_is_capped_with_marker_and_full_name_available(self):
        parent = "feat/ABC-101-restructure-the-document-upload-flow"
        out = render([open_pr(7437, base=parent, branch="feat/ABC-102-add-email-verification-error-states")])
        row = cells(out, OPEN_COLUMNS, 7437)
        self.assertTrue(row["Target"].startswith("📌 "))
        self.assertTrue(row["Target"].endswith("…"))
        self.assertLessEqual(visible_width(row["Target"][2:]), 30)
        self.assertTrue(row["Branch"].endswith("…"))
        self.assertLessEqual(visible_width(row["Branch"]), 30)
        self.assertEqual(row["LGTM"], "🚧")
        self.assertIn(f"#7437 target {parent}", out)
        self.assertIn("#7437 branch feat/ABC-102-add-email-verification-error-states", out)

    def test_default_base_target_is_plain_and_not_listed_as_truncated(self):
        out = render([open_pr(1)])
        self.assertEqual(cells(out, OPEN_COLUMNS, 1)["Target"], "main")
        self.assertNotIn("Full names", out)

    def test_titles_are_truncated_factually_and_markdown_escaped(self):
        title = "fix(api): AB-9 *a|b* `c` [x] <y> handled correctly for everyone"
        out = render([open_pr(9, title=title)])
        row = cells(out, OPEN_COLUMNS, 9)
        self.assertEqual(len(row), len(OPEN_COLUMNS), row)
        self.assertTrue(row["Title"].endswith("…"))
        self.assertLessEqual(visible_width(row["Title"].replace("\\", "")), 25)
        self.assertTrue(title.startswith(row["Title"].replace("\\", "").rstrip("…")))
        self.assertIn("\\|", row["Title"])
        self.assertIn("\\`", row["Title"])
        self.assertIn("\\*", row["Title"])

    def test_every_cell_token_fits_a_narrow_column(self):
        rows = [open_pr(1, base="x" * 80, branch="feat/AB-1-" + "y" * 80, title="z" * 80,
                        reviewDecision="APPROVED", approvers=["a", "b", "c", "d"], unresolvedThreads=12),
                open_pr(2, title="w" * 60)]
        out = render(rows, [closed_pr(3, title="q" * 90)])
        for line in out.splitlines():
            if line.startswith("|") and not line.startswith("|---"):
                for token in line.split():
                    self.assertLessEqual(visible_width(token), 31, token)
        self.assertEqual(len(table_rows(out, OPEN_COLUMNS)), 2)
        self.assertEqual(len(table_rows(out, CLOSED_COLUMNS)), 1)

    def test_open_prs_group_by_repo_with_heading(self):
        out = render([open_pr(1), open_pr(2, repo="gadgets"), open_pr(3)])
        self.assertIn("#### Open — widgets", out)
        self.assertIn("#### Open — gadgets", out)
        self.assertLess(out.index("#### Open — widgets"), out.index("#### Open — gadgets"))

    def test_empty_inputs(self):
        self.assertNotIn("Recently closed", render([open_pr(1)]))
        self.assertIn("_No open PRs._", render([], [closed_pr(1)]))


class StatusCellTests(unittest.TestCase):
    def test_open_row_cells(self):
        out = render([open_pr(1, isDraft=True), open_pr(2, reviewDecision="APPROVED", approvers=["b", "a"]),
                      open_pr(3, reviewRequestCount=4, unresolvedThreads=2, checksState="PENDING"),
                      open_pr(4, reviewDecision="CHANGES_REQUESTED", checksState="FAILURE", jira={"error": True}),
                      open_pr(5, reviewRequestCount=None, jira={"total": 0}),
                      open_pr(6, approvers=["c"], checksState=None, branch="chore/tidy", title="no ticket here"),
                      open_pr(7)])
        self.assertEqual(cells(out, OPEN_COLUMNS, 1)["Ready"], "🚧")
        self.assertEqual(cells(out, OPEN_COLUMNS, 1)["Approved"], "—")
        self.assertEqual(cells(out, OPEN_COLUMNS, 2)["Approved"], "✅✅")
        self.assertEqual(cells(out, OPEN_COLUMNS, 2)["LGTM"], "🚀")
        three = cells(out, OPEN_COLUMNS, 3)
        self.assertEqual((three["Approved"], three["Threads"], three["CI"]), ("🔔 4", "💬 2", "⏳"))
        four = cells(out, OPEN_COLUMNS, 4)
        self.assertEqual((four["Approved"], four["CI"], four["Jira 💬"]), ("👎", "❌", "?"))
        five = cells(out, OPEN_COLUMNS, 5)
        self.assertEqual((five["Approved"], five["Jira 💬"]), ("🔔", "—"))
        six = cells(out, OPEN_COLUMNS, 6)
        self.assertEqual((six["Approved"], six["CI"], six["Ticket"], six["Branch"]), ("🔄", "—", "—", "tidy"))
        self.assertEqual(cells(out, OPEN_COLUMNS, 7)["Approved"], "🔕 0")
        one = cells(out, OPEN_COLUMNS, 1)
        self.assertEqual((one["Ticket"], one["Jira 💬"], one["Push"], one["Approved"]),
                         ("AB-1", "💬 7 · Ivar · 2d", "2h", "—"))
        self.assertEqual(cells(out, OPEN_COLUMNS, 2)["Ready"], "2d")

    def test_closed_row_cells(self):
        out = render([], [closed_pr(1), closed_pr(2, mergeCommitSha=None, mergeCommitAt=None, mainChecksState=None),
                          closed_pr(3, mergeCommitAt="2026-10-10T00:00:00Z", mainChecksState="FAILURE")])
        one = cells(out, CLOSED_COLUMNS, 1)
        self.assertEqual((one["Repo"], one["Status"], one["CI"], one["Ready"], one["Wait"], one["Closed"]),
                         ("widgets", "🔀", "✅", "3d", "2d", "1d"))
        self.assertEqual(cells(out, CLOSED_COLUMNS, 2)["Status"], "🚫")
        self.assertEqual(cells(out, CLOSED_COLUMNS, 2)["CI"], "—")
        self.assertEqual(cells(out, CLOSED_COLUMNS, 3)["CI"], "—")

    def test_relative_times_use_single_short_units(self):
        out = render([open_pr(1, lastPush="2026-10-19T15:35:00Z", readyAt="2026-10-19T15:59:30Z"),
                      open_pr(2, lastPush="2026-10-18T15:00:00Z", readyAt="2026-10-01T00:00:00Z")])
        self.assertEqual((cells(out, OPEN_COLUMNS, 1)["Push"], cells(out, OPEN_COLUMNS, 1)["Ready"]), ("25m", "0m"))
        self.assertEqual((cells(out, OPEN_COLUMNS, 2)["Push"], cells(out, OPEN_COLUMNS, 2)["Ready"]), ("1d", "18d"))

    def test_generated_glyphs_have_one_unambiguous_width(self):
        """Pi pads an emoji presentation sequence (narrow base + U+FE0F) to two columns, but
        xterm.js Unicode 11 terminals such as Orca draw it in one, shifting every later border."""
        approvals = [{"reviewDecision": "APPROVED", "approvers": ["a", "b"]}, {"approvers": ["c"]},
                     {"reviewDecision": "CHANGES_REQUESTED"}, {"isDraft": True}, {"reviewRequestCount": 0},
                     {"reviewRequestCount": 3}, {"reviewRequestCount": None}]
        states = [{"mergeable": "CONFLICTING"}, {"behindBy": 2, "checksState": "FAILURE"},
                  {"checksState": "PENDING", "unresolvedThreads": 4}, {"mergeable": "UNKNOWN", "checksState": None},
                  {"base": "feat/AB-1-parent", "jira": {"error": True}},
                  {"reviewDecision": "APPROVED", "approvers": ["a"]}]
        rows = [open_pr(n, **overrides) for n, overrides in enumerate(approvals + states, start=1)]
        out = render(rows, [closed_pr(90), closed_pr(91, mergeCommitSha=None)])
        self.assertIn("🚀", out)
        self.assertNotIn("\ufe0f", out)
        self.assertNotIn("\ufe0e", out)
        narrow_text = {"—", "·", "…"}
        for char in sorted({char for char in out if ord(char) > 127}):
            with self.subTest(char=char, codepoint=f"U+{ord(char):04X}"):
                self.assertTrue(unicodedata.east_asian_width(char) in "WF" or char in narrow_text)

    def test_invalid_input_fails_clearly(self):
        result = subprocess.run([sys.executable, "-I", str(FORMAT)], input="not json",
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("JSON", result.stderr)


if __name__ == "__main__":
    unittest.main()
