import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "reducer.py"
SPEC = importlib.util.spec_from_file_location("watch_admin_reducer", SCRIPT)
reducer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reducer
assert SPEC.loader
SPEC.loader.exec_module(reducer)

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "scenarios.json").read_text())
NOW = "2026-08-05T09:00:00Z"
LATER = "2026-08-05T09:05:00Z"


def snapshot(*sources):
    return {source["source"]: source for source in sources}


def observed(source, *, status=None, records=None, observed_at=LATER, error=None, coverage=None):
    value = copy.deepcopy(FIXTURES[source])
    value["observedAt"] = observed_at
    if status is not None:
        value["status"] = status
    if records is not None:
        value["records"] = records
    if coverage is not None:
        value["coverage"] = coverage
    if error is not None:
        value["error"] = error
    return value


class ReducerTest(unittest.TestCase):
    def baseline(self, **options):
        state, result = reducer.tick(
            reducer.initial_state(**options),
            snapshot(FIXTURES["git"], FIXTURES["beads"], FIXTURES["jira"]),
            NOW,
        )
        self.assertEqual("baseline", result["outcome"])
        self.assertEqual([], result["events"])
        return state

    def test_baseline_quiet_and_absent_not_due_source_preserve_state(self):
        state = self.baseline()
        jira_before = copy.deepcopy(state["sources"]["jira"])
        reordered_git = observed("git", records=list(reversed(FIXTURES["git"]["records"])))

        state, result = reducer.tick(state, snapshot(reordered_git), LATER)

        self.assertEqual("quiet", result["outcome"])
        self.assertEqual([], result["events"])
        self.assertEqual(jira_before, state["sources"]["jira"])
        self.assertEqual(2, state["sources"]["git"]["revision"])

    def test_material_changes_are_scope_labelled_and_revision_aware(self):
        state = self.baseline()
        git = observed("git")
        git["records"][0]["head"] = "bbb"
        beads = observed("beads")
        beads["records"][0]["status"] = "closed"
        jira = observed("jira")
        jira["records"][0]["sprint"] = "38"

        _, result = reducer.tick(state, snapshot(git, beads, jira), LATER)

        self.assertEqual("material", result["outcome"])
        self.assertEqual(
            {
                ("git", "workspace", "git_changed"),
                ("beads", "workspace", "bead_changed"),
                ("jira", "assigned-jira-portfolio", "jira_changed"),
            },
            {(event["source"], event["scope"], event["kind"]) for event in result["events"]},
        )
        for event in result["events"]:
            self.assertEqual(1, event["fromRevision"])
            self.assertEqual(2, event["toRevision"])
            self.assertEqual(reducer.CONTRACT_VERSION, event["contractVersion"])

    def test_complete_can_remove_but_partial_cannot(self):
        state = self.baseline()
        partial = observed(
            "beads",
            status="partial",
            records=[],
            coverage={"total": 1, "included": 0, "omitted": 1, "selectionBasis": "first 200 ids"},
        )

        state, partial_result = reducer.tick(state, snapshot(partial), LATER)
        self.assertIn("agents-l1i", state["sources"]["beads"]["records"])
        complete = observed(
            "beads",
            records=[],
            observed_at="2026-08-05T09:10:00Z",
            coverage={"total": 0, "included": 0, "omitted": 0, "selectionBasis": "owning store and bead id"},
        )
        state, complete_result = reducer.tick(state, snapshot(complete), "2026-08-05T09:10:00Z")

        self.assertNotIn("no_longer_observed", [event["kind"] for event in partial_result["events"]])
        self.assertEqual(["no_longer_observed"], [event["kind"] for event in complete_result["events"]])
        self.assertEqual({}, state["sources"]["beads"]["records"])

    def test_jira_complete_disappearance_is_set_exit_not_inferred_done(self):
        state = self.baseline()
        jira = observed(
            "jira",
            records=[],
            coverage={"total": 0, "included": 0, "omitted": 0, "selectionBasis": "issue key"},
        )

        _, result = reducer.tick(state, snapshot(jira), LATER)

        event = result["events"][0]
        self.assertEqual("left_assigned_non_done_set", event["kind"])
        self.assertIsNone(event["after"])

    def test_error_isolated_first_and_third_alert_degradation_and_recovery(self):
        state = self.baseline()
        failed = observed("git", status="error", records=[], error="timeout\nPRIVATE")
        changed_beads = observed("beads")
        changed_beads["records"][0]["status"] = "closed"

        state, first = reducer.tick(state, snapshot(failed, changed_beads), LATER)
        failed["observedAt"] = "2026-08-05T09:10:00Z"
        state, second = reducer.tick(state, snapshot(failed), "2026-08-05T09:10:00Z")
        failed["observedAt"] = "2026-08-05T09:15:00Z"
        state, third = reducer.tick(state, snapshot(failed), "2026-08-05T09:15:00Z")

        self.assertEqual(["bead_changed", "source_failed"], [event["kind"] for event in first["events"]])
        self.assertEqual([], second["events"])
        self.assertEqual(["source_degraded"], [event["kind"] for event in third["events"]])
        self.assertTrue(state["sources"]["git"]["degraded"])
        self.assertEqual("2026-08-05T10:15:00Z", state["sources"]["git"]["nextProbeAt"])
        self.assertEqual("aaa", state["sources"]["git"]["records"]["agent-skills"]["head"])
        self.assertNotIn("PRIVATE", json.dumps(first))

        recovered = observed("git", observed_at="2026-08-05T10:15:00Z")
        recovered["records"][0]["head"] = "ccc"
        state, result = reducer.tick(state, snapshot(recovered), "2026-08-05T10:15:00Z")

        self.assertEqual(["git_changed", "source_recovered"], [event["kind"] for event in result["events"]])
        self.assertFalse(state["sources"]["git"]["degraded"])
        self.assertIsNone(state["sources"]["git"]["nextProbeAt"])

    def test_partial_coverage_reports_first_and_third_without_erasing(self):
        state = self.baseline()
        partial = observed(
            "beads",
            status="partial",
            records=[],
            coverage={"total": 1, "included": 0, "omitted": 1, "selectionBasis": "first 200 ids"},
        )

        state, first = reducer.tick(state, snapshot(partial), LATER)
        state, second = reducer.tick(state, snapshot(partial), "2026-08-05T09:10:00Z")
        state, third = reducer.tick(state, snapshot(partial), "2026-08-05T09:15:00Z")

        self.assertEqual(["source_partial"], [event["kind"] for event in first["events"]])
        self.assertEqual([], second["events"])
        self.assertEqual(["source_partial_persistent"], [event["kind"] for event in third["events"]])
        self.assertIn("agents-l1i", state["sources"]["beads"]["records"])

    def test_retry_identity_is_stable_but_repeated_transition_is_new(self):
        baseline = self.baseline()
        changed = observed("git")
        changed["records"][0]["head"] = "bbb"

        state, first = reducer.tick(copy.deepcopy(baseline), snapshot(changed), LATER)
        _, retry = reducer.tick(copy.deepcopy(baseline), snapshot(changed), LATER)
        back = observed("git", observed_at="2026-08-05T09:10:00Z")
        state, second = reducer.tick(state, snapshot(back), "2026-08-05T09:10:00Z")
        changed["observedAt"] = "2026-08-05T09:15:00Z"
        state, third = reducer.tick(state, snapshot(changed), "2026-08-05T09:15:00Z")

        self.assertEqual(first["events"][0]["eventId"], retry["events"][0]["eventId"])
        self.assertNotEqual(first["events"][0]["eventId"], third["events"][0]["eventId"])
        self.assertEqual((1, 2), (first["events"][0]["fromRevision"], first["events"][0]["toRevision"]))
        self.assertEqual((3, 4), (third["events"][0]["fromRevision"], third["events"][0]["toRevision"]))
        self.assertEqual("aaa", second["events"][0]["after"]["head"])

    def test_invalid_source_isolated_and_hostile_records_rejected(self):
        state = self.baseline()
        hostile = observed("git")
        hostile["records"][0]["head"] = "bad\u0000value"
        valid = observed("beads")
        valid["records"][0]["priority"] = 1

        state, result = reducer.tick(state, snapshot(hostile, valid), LATER)

        self.assertEqual(["bead_changed", "source_failed"], [event["kind"] for event in result["events"]])
        self.assertEqual("aaa", state["sources"]["git"]["records"]["agent-skills"]["head"])
        self.assertLessEqual(len(result["events"][-1]["after"]["diagnostic"].encode()), reducer.DIAGNOSTIC_BYTES)

    def test_unknown_fields_duplicates_invalid_enum_and_long_strings_fail_source_only(self):
        cases = []
        unknown = observed("git")
        unknown["records"][0]["updated"] = "volatile"
        cases.append(unknown)
        duplicate = observed("git", records=FIXTURES["git"]["records"] * 2)
        duplicate["coverage"]["total"] = duplicate["coverage"]["included"] = 2
        cases.append(duplicate)
        invalid_status = observed("git", status="ok")
        cases.append(invalid_status)
        long_string = observed("git")
        long_string["records"][0]["head"] = "x" * 257
        cases.append(long_string)

        for index, value in enumerate(cases):
            with self.subTest(index=index):
                state = self.baseline()
                state, result = reducer.tick(state, snapshot(value), LATER)
                self.assertEqual(["source_failed"], [event["kind"] for event in result["events"]])
                self.assertEqual("aaa", state["sources"]["git"]["records"]["agent-skills"]["head"])

    def test_envelope_event_ledger_and_state_bounds(self):
        state = self.baseline()
        huge = observed("git")
        huge["records"][0]["head"] = "x" * reducer.ENVELOPE_BYTES
        state, result = reducer.tick(state, snapshot(huge), LATER)
        self.assertEqual(["source_failed"], [event["kind"] for event in result["events"]])

        many = observed(
            "git",
            records=[
                {"id": f"repo-{index:03}", "entityType": "repository", "head": str(index), "present": True}
                for index in range(200)
            ],
            observed_at="2026-08-05T09:10:00Z",
        )
        many["coverage"] = {"total": 200, "included": 200, "omitted": 0, "selectionBasis": "identity"}
        state, result = reducer.tick(state, snapshot(many), "2026-08-05T09:10:00Z")

        self.assertLessEqual(len(result["events"]), reducer.EVENT_CAP)
        self.assertGreater(result["omittedEventCount"], 0)
        self.assertLessEqual(len(state["seenEventIds"]), reducer.SEEN_EVENT_CAP)
        self.assertIsNotNone(result["identityLedgerNotice"])
        self.assertLessEqual(reducer.serialized_bytes(state), reducer.STATE_BYTES)

        unknown_state = reducer.initial_state()
        unknown_state["padding"] = "small"
        with self.assertRaisesRegex(ValueError, "unknown state fields"):
            reducer.tick(unknown_state, {}, LATER)

        malformed_ledger = reducer.initial_state()
        malformed_ledger["seenEventIds"] = ["not-a-sha"]
        with self.assertRaisesRegex(ValueError, "seen event id"):
            reducer.tick(malformed_ledger, {}, LATER)

        oversized_state = reducer.initial_state()
        oversized_state["padding"] = "x" * reducer.STATE_BYTES
        with self.assertRaisesRegex(ValueError, "state byte cap exceeded"):
            reducer.tick(oversized_state, {}, LATER)

    def test_record_caps_are_source_specific(self):
        state = self.baseline()
        records = [{"id": f"issue-{index}", "status": "open"} for index in range(reducer.RECORD_CAPS["jira"] + 1)]
        jira = observed("jira", records=records)
        jira["coverage"] = {
            "total": len(records),
            "included": len(records),
            "omitted": 0,
            "selectionBasis": "issue key",
        }

        state, result = reducer.tick(state, snapshot(jira), LATER)

        self.assertEqual(["source_failed"], [event["kind"] for event in result["events"]])
        self.assertIn("record cap exceeded", result["events"][0]["after"]["diagnostic"])

    def test_due_sources_keep_jira_at_thirty_minutes_and_degraded_probes_hourly(self):
        state = self.baseline()
        self.assertEqual(["git", "beads"], reducer.due_sources(state, "2026-08-05T09:15:00Z"))
        self.assertEqual(["git", "beads", "jira"], reducer.due_sources(state, "2026-08-05T09:30:00Z"))

        failed = observed("git", status="error", records=[], error="timeout")
        for minute in (5, 10, 15):
            at = f"2026-08-05T09:{minute:02}:00Z"
            failed["observedAt"] = at
            state, _ = reducer.tick(state, snapshot(failed), at)
        self.assertEqual(["beads"], reducer.due_sources(state, "2026-08-05T09:20:00Z"))
        self.assertEqual(["git", "beads", "jira"], reducer.due_sources(state, "2026-08-05T10:15:00Z"))

    def test_material_event_warms_cadence_for_one_hour(self):
        state = self.baseline()
        changed = observed("git")
        changed["records"][0]["head"] = "bbb"

        state, material = reducer.tick(state, snapshot(changed), LATER)
        quiet_git = observed("git", records=changed["records"], observed_at="2026-08-05T09:30:00Z")
        state, warm_quiet = reducer.tick(state, snapshot(quiet_git), "2026-08-05T09:30:00Z")
        quiet_git["observedAt"] = "2026-08-05T10:10:00Z"
        state, cold_quiet = reducer.tick(state, snapshot(quiet_git), "2026-08-05T10:10:00Z")

        self.assertEqual(300, material["delaySeconds"])
        self.assertEqual("2026-08-05T10:05:00Z", state["warmUntil"])
        self.assertEqual(300, warm_quiet["delaySeconds"])
        self.assertEqual(900, cold_quiet["delaySeconds"])

    def test_tick_budget_deadline_and_explicit_stop_are_terminal_before_collection(self):
        state = self.baseline(max_ticks=1)
        state, budget = reducer.tick(state, snapshot(observed("git")), LATER)
        self.assertEqual("tick_budget_exhausted", budget["reason"])
        self.assertEqual(1, state["tickCount"])

        state = reducer.initial_state(stop_at=NOW)
        state, deadline = reducer.tick(state, snapshot(FIXTURES["git"]), NOW)
        self.assertEqual("deadline_reached", deadline["reason"])
        self.assertEqual({}, state["sources"])

        state = reducer.stop(self.baseline(), "user_stop")
        count = state["tickCount"]
        state, stopped = reducer.tick(state, snapshot(observed("git")), LATER)
        self.assertEqual("user_stop", stopped["reason"])
        self.assertEqual(count, state["tickCount"])


if __name__ == "__main__":
    unittest.main()
