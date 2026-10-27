from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import datetime, timezone

from workspace_fixture import SKILL_DIR, WorkspaceFixture, issue

SCRIPT = SKILL_DIR / "scripts" / "next-bd"
NOW = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
ELAPSED = "2000-01-01T00:00:00Z"
FUTURE = "2999-12-31T23:59:59Z"
NOTE = ("⏰ 2 elapsed wake dates: still stored deferred, not ready. "
        "Read-only listing never wakes work; review the awaited event before undeferring.")


def load_collector():
    spec = importlib.util.spec_from_file_location("next_collect_defer", SKILL_DIR / "scripts" / "collect.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DeferElapsedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.elapsed = load_collector().defer_elapsed

    def test_instants_at_or_before_now_are_elapsed(self) -> None:
        for value in ("2026-10-27T11:59:59Z", "2026-10-27T12:00:00Z", "2026-10-27T14:00:00+02:00",
                      "2026-10-27T07:00:00-05:00", "2026-10-27T11:59:59.999Z",
                      "2026-10-27T11:59:59.999999999Z", ELAPSED):
            with self.subTest(value=value):
                self.assertIs(self.elapsed(value, NOW), True)

    def test_later_instants_are_pending(self) -> None:
        for value in ("2026-10-27T12:00:01Z", "2026-10-27T12:00:00.000001Z", "2026-10-27T14:00:01+02:00",
                      "2026-10-27T07:00:01-05:00", "2026-10-27T12:00:00-00:01", FUTURE):
            with self.subTest(value=value):
                self.assertIs(self.elapsed(value, NOW), False)

    def test_missing_or_unparseable_dates_are_never_elapsed(self) -> None:
        for value in (None, "", 5, True, [], {}, "soon", "2000-01-01", "2000-01-01T00:00:00",
                      "2000-01-01 00:00:00Z", "2000-01-01T00:00:00+0000", " 2000-01-01T00:00:00Z",
                      "2000-01-01T00:00:00Z\n", "2026-13-45T00:00:00Z", "2026-10-27T25:00:00Z",
                      "2000-01-01T00:00:00+25:00"):
            with self.subTest(value=value):
                self.assertIsNone(self.elapsed(value, NOW))


class ElapsedDeferListingTest(WorkspaceFixture):
    def run_next(self, directory, *arguments: str):
        return self.run_script(SCRIPT, directory, *arguments)

    @staticmethod
    def fixture_data() -> dict:
        dates = {"wake-elapsed": ELAPSED, "wake-future": FUTURE, "wake-icebox": None,
                 "wake-text": "soon", "wake-naive": "2000-01-01T00:00:00"}
        deferred = []
        for issue_id, defer_until in dates.items():
            row = issue(issue_id, 3, "task", "2026-01-01T00:00:00Z")
            if defer_until is not None:
                row["defer_until"] = defer_until
            deferred.append(row)
        overlap = issue("wake-overlap", 2, "task", "2026-01-02T00:00:00Z")
        deferred.append({**overlap, "defer_until": ELAPSED})
        return {"ready": [issue("ready-task", 2, "task", "2026-01-01T00:00:00Z"), overlap],
                "deferred": deferred}

    def test_elapsed_wake_dates_are_marked_without_implying_readiness(self) -> None:
        data = self.fixture_data()
        workspace = self.create_workspace(repositories={"repo-a": data})
        local = self.base / "local"
        self.create_store(local, **data)
        for directory, owner in ((workspace, "repo-a | "), (local, "")):
            with self.subTest(workspace=bool(owner)):
                listing = self.run_next(directory, "--list").stdout
                safe = self.run_next(directory, "--safe").stdout
                marked = {
                    f"| {owner}wake-elapsed | P3 | task | - | Title for wake-elapsed | {ELAPSED} ⏰ elapsed |",
                    f"| {owner}wake-overlap | P2 | task | - | Title for wake-overlap | {ELAPSED} ⏰ elapsed |",
                }
                plain = {
                    f"| {owner}wake-future | P3 | task | - | Title for wake-future | {FUTURE} |",
                    f"| {owner}wake-icebox | P3 | task | - | Title for wake-icebox | — |",
                    f"| {owner}wake-text | P3 | task | - | Title for wake-text | soon |",
                    f"| {owner}wake-naive | P3 | task | - | Title for wake-naive | 2000-01-01T00:00:00 |",
                }
                for output, heading in ((listing, "## Deferred (6 beads; not selectable)"),
                                        (safe, "## Later — deferred (6 beads; not selectable)")):
                    before, after = output.split(heading, 1)
                    self.assertNotIn("elapsed", before)
                    self.assertNotIn("⏰", before)
                    self.assertTrue(after.startswith(f"\n\n{NOTE}\n\n|"), after[:240])
                    self.assertEqual(after.count("⏰ elapsed"), 2)
                    for row in marked | plain:
                        self.assertIn(row, after)
                self.assertIn(f"| 1 | {owner}ready-task |", listing)
                self.assertIn(f"| 2 | {owner}wake-overlap |", listing)
                self.assertEqual(listing.count("| # |"), 1)
                candidates = json.loads(self.run_next(directory, "--json").stdout)
                self.assertEqual([row["id"] for row in candidates], ["ready-task", "wake-overlap"])
                self.assertFalse(any("defer_elapsed" in row for row in candidates))
                packet = json.loads(self.run_next(directory, "--safe-json").stdout)
                self.assertEqual(
                    {row["id"]: row["defer_elapsed"] for row in packet["deferred"]},
                    {"wake-elapsed": True, "wake-future": False, "wake-icebox": None,
                     "wake-text": None, "wake-naive": None, "wake-overlap": True},
                )
                self.assertFalse(any("defer_elapsed" in row for row in packet["candidates"]))
        calls = self.recorded_calls()
        self.assertTrue(all("--readonly" in call["arguments"] for call in calls))
        self.assertTrue(all(call["arguments"][0] in {"list", "blocked"} for call in calls))

    def test_pending_and_dateless_deferrals_carry_no_attention_line(self) -> None:
        local = self.base / "local"
        future = issue("later", 3, "task", "2026-01-01T00:00:00Z")
        future["defer_until"] = FUTURE
        self.create_store(local, deferred=[future, issue("icebox", 3, "task", "2026-01-01T00:00:00Z")])
        for arguments in (("--list",), ("--safe",)):
            output = self.run_next(local, *arguments).stdout
            self.assertNotIn("elapsed", output)
            self.assertNotIn("⏰", output)
            self.assertIn(f"| Title for later | {FUTURE} |", output)
            self.assertIn("| Title for icebox | — |", output)


if __name__ == "__main__":
    unittest.main()
