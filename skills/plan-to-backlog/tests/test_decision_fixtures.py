#!/usr/bin/env python3
"""Evidence-derived invariants for frozen plan-to-backlog decision fixtures.

These checks exercise a deterministic policy oracle over captured scenarios. Live model
behavior remains nondeterministic and is recorded separately as dogfood evidence.
"""

from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
FIXTURE_NAMES = {"decision-boundary-scenarios.json", "decision-scenarios.json"}
OUTCOME_CHECKS = (
    "observable",
    "ownAcceptance",
    "independentValue",
    "independentLifecycle",
    "outcomeLanguage",
)
MECHANICAL_TITLE_PATTERN = re.compile(r"\b(test|review|commit|retry|handoff)\b", re.IGNORECASE)
SEQUENCE_RATIONALE_TERMS = ("planning order", "do first", "then implement", "work sequence")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
ALLOWED_WRITE_ACTIONS = {"create", "update-type", "set-parent", "add-blocker"}
REQUIRED_MATRIX = {
    "no-item-existing-owner": ("ready", "no-item"),
    "mechanical-single-outcome": ("ready", "single-item"),
    "bounded-epic-conversion": ("ready", "epic"),
    "tightly-coupled-two-outcomes": ("ready", "single-item"),
    "cross-repository-two-outcomes": ("ready", "epic"),
    "existing-duplicate-tree": ("ready", "no-item"),
    "partially-materialized-tree": ("ready", "epic"),
    "unresolved-plan": ("needs-clarification", None),
    "unapproved-plan": ("needs-clarification", None),
    "declined-apply": ("ready", "single-item"),
    "partial-failure-recovery": ("ready", "epic"),
    "mechanical-dependency-sequence": ("ready", "epic"),
    "more-than-six-candidates": ("needs-clarification", None),
    "duplicate-reuse": ("ready", "no-item"),
}


def load_scenarios() -> list[dict[str, Any]]:
    paths = sorted(FIXTURE_ROOT.glob("decision-*.json"))
    if {path.name for path in paths} != FIXTURE_NAMES:
        raise ValueError("fixture directory contains missing or unreferenced decision files")
    scenarios: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("scenarioVersion") != 1:
            raise ValueError(f"unsupported scenarioVersion in {path.name}")
        if not isinstance(payload.get("scenarios"), list):
            raise ValueError(f"scenarios must be a list in {path.name}")
        scenarios.extend(payload["scenarios"])
    identifiers = [scenario.get("id") for scenario in scenarios]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("scenario IDs must be unique")
    return scenarios


def qualifying_outcomes(scenario_input: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        outcome
        for outcome in scenario_input.get("candidateOutcomes", [])
        if all(outcome.get(check) is True for check in OUTCOME_CHECKS)
    ]


def has_two_outcome_epic_boundary(
    scenario_input: dict[str, Any], outcomes: list[dict[str, Any]]
) -> bool:
    repositories = {outcome.get("repository") for outcome in outcomes}
    return (
        len(outcomes) == 2
        and None not in repositories
        and len(repositories) == 2
        and all(outcome.get("independentlyShippable") is True for outcome in outcomes)
        and bool(scenario_input.get("aggregateOwnershipEvidence", "").strip())
    )


def derive_decision(scenario_input: dict[str, Any]) -> tuple[str, str | None]:
    source = scenario_input["source"]
    if not source.get("approved") or scenario_input.get("unresolvedQuestions"):
        return "needs-clarification", None

    owners = [
        item
        for item in scenario_input.get("existingItems", [])
        if item.get("classification") == "owner"
    ]
    if len(owners) > 1:
        return "needs-clarification", None
    if owners and owners[0].get("exactCompleteOutcome"):
        return "ready", "no-item"

    candidates = scenario_input.get("candidateOutcomes", [])
    if not candidates:
        return "needs-clarification", None
    outcomes = qualifying_outcomes(scenario_input)
    if len(outcomes) > 6:
        return "needs-clarification", None
    if len(outcomes) <= 1:
        return "ready", "single-item"
    if len(outcomes) == 2:
        disposition = "epic" if has_two_outcome_epic_boundary(scenario_input, outcomes) else "single-item"
        return "ready", disposition
    return "ready", "epic"


def operation_key(write: dict[str, Any]) -> tuple[Any, ...]:
    action = write.get("action")
    if action == "create":
        return action, write.get("ref"), write.get("parent")
    if action == "update-type":
        return action, write.get("ref")
    if action == "set-parent":
        return action, write.get("ref"), write.get("parent")
    if action == "add-blocker":
        return action, write.get("dependent"), write.get("prerequisite")
    return action,


def existing_proposal_ref(item: dict[str, Any]) -> str | None:
    if item.get("proposalRef"):
        return item["proposalRef"]
    if item.get("classification") == "owner":
        return "owner"
    return None


def validate_traceability(scenario: dict[str, Any], errors: list[str]) -> None:
    source = scenario["input"]["source"]
    if not SHA256_PATTERN.fullmatch(source.get("fingerprint", "")):
        errors.append("source fingerprint is not lowercase SHA-256")
    for item in scenario["expected"]["items"]:
        if item["action"] != "create":
            continue
        expected_metadata = {
            "plan_source": source["locator"],
            "plan_source_sha256": source["fingerprint"],
            "plan_proposal_ref": item["ref"],
        }
        if item.get("metadata") != expected_metadata:
            errors.append(f"{item['ref']} create metadata is not source-traceable")
        if item.get("sourceCitation") != f"Source plan: {source['locator']}":
            errors.append(f"{item['ref']} create lacks the exact source citation")


def validate_write_set(scenario: dict[str, Any], errors: list[str]) -> None:
    expected = scenario["expected"]
    items = expected["items"]
    item_refs = [item["ref"] for item in items]
    if len(item_refs) != len(set(item_refs)):
        errors.append("proposal item refs are not unique")
    declared_refs = set(item_refs)

    relationships = expected["relationships"]
    for relationship in relationships:
        if relationship.get("from") not in declared_refs or relationship.get("to") not in declared_refs:
            errors.append("relationship references an undeclared proposal ref")

    writes = expected["logicalWrites"]
    write_keys = [operation_key(write) for write in writes]
    if len(write_keys) != len(set(write_keys)):
        errors.append("logical write set contains duplicate operations")
    for write in writes:
        if write.get("action") not in ALLOWED_WRITE_ACTIONS:
            errors.append(f"logical write set contains unsupported action {write.get('action')}")

    required_item_writes = []
    for item in items:
        if item["action"] == "create":
            parent = "owner" if item["ref"].startswith("child-") else None
            required_item_writes.append(operation_key({"action": "create", "ref": item["ref"], "parent": parent}))
        elif item["action"] == "update-type":
            required_item_writes.append(("update-type", item["ref"]))
        elif item["action"] not in {"reuse"}:
            errors.append(f"unsupported item action {item['action']}")
    actual_item_writes = [
        key for key in write_keys if key[0] in {"create", "update-type", "set-parent"}
    ]
    if actual_item_writes != required_item_writes:
        errors.append("logical item writes do not exactly match proposed item actions")

    blocker_keys = [
        ("add-blocker", relationship["from"], relationship["to"])
        for relationship in relationships
        if relationship["kind"] == "blocking"
    ]
    actual_blocker_keys = [key for key in write_keys if key[0] == "add-blocker"]
    if actual_blocker_keys != blocker_keys:
        errors.append("logical blocker writes do not exactly match proposed blocking relationships")

    parent_refs = {
        relationship["from"]
        for relationship in relationships
        if relationship["kind"] == "parent" and relationship["to"] == "owner"
    }
    created_children = {item["ref"] for item in items if item["action"] == "create" and item["ref"].startswith("child-")}
    if not created_children.issubset(parent_refs):
        errors.append("created child lacks a proposed parent relationship")


def validate_epic(scenario: dict[str, Any], errors: list[str]) -> None:
    expected = scenario["expected"]
    if expected["disposition"] != "epic":
        return
    children = [item for item in expected["items"] if item["ref"].startswith("child-")]
    if not 2 <= len(children) <= 6:
        errors.append("epic child count is outside the bounded threshold")

    candidate_by_ref = {
        candidate["ref"]: candidate
        for candidate in scenario["input"].get("candidateOutcomes", [])
    }
    for child in children:
        candidate = candidate_by_ref.get(child["ref"], {})
        missing = [check for check in OUTCOME_CHECKS if candidate.get(check) is not True]
        if missing:
            errors.append(f"{child['ref']} lacks independent-outcome checks: {missing}")
        if MECHANICAL_TITLE_PATTERN.search(child["title"]):
            errors.append(f"{child['ref']} uses a mechanical child title")

    if len(children) == 2 and not has_two_outcome_epic_boundary(
        scenario["input"], list(candidate_by_ref.values())
    ):
        errors.append("two-child epic lacks evidenced cross-repository boundaries")

    parent_refs = {
        relationship["from"]
        for relationship in expected["relationships"]
        if relationship["kind"] == "parent" and relationship["to"] == "owner"
    }
    if parent_refs != {child["ref"] for child in children}:
        errors.append("epic parent relationships do not match all children")

    declared_refs = {item["ref"] for item in expected["items"]}
    for relationship in expected["relationships"]:
        if relationship["kind"] != "blocking":
            continue
        if relationship["from"] not in declared_refs or relationship["to"] not in declared_refs:
            errors.append("blocking relationship references an undeclared proposal ref")
        if not relationship.get("acceptanceCondition"):
            errors.append("blocking relationship lacks an acceptance condition")
        rationale = relationship.get("rationale", "").casefold()
        if not any(term in rationale for term in ("cannot", "until", "requires")):
            errors.append("blocking relationship does not state an acceptance dependency")
        if any(term in rationale for term in SEQUENCE_RATIONALE_TERMS):
            errors.append("blocking relationship represents plan-step sequencing")

    evidenced_blockers = [
        (candidate["ref"], prerequisite)
        for candidate in scenario["input"].get("candidateOutcomes", [])
        for prerequisite in candidate.get("acceptanceRequires", [])
    ]
    proposed_blockers = [
        (relationship["from"], relationship["to"])
        for relationship in expected["relationships"]
        if relationship["kind"] == "blocking"
    ]
    if proposed_blockers != evidenced_blockers:
        errors.append("blocking relationships do not match source acceptance dependencies")


def validate_no_mutation_paths(scenario: dict[str, Any], errors: list[str]) -> None:
    expected = scenario["expected"]
    decision = scenario["confirmation"]["decision"]
    observed = scenario["observed"]
    if expected["disposition"] == "no-item" or expected["readiness"] == "needs-clarification":
        if expected["logicalWrites"]:
            errors.append("read-only decision contains logical writes")
        if observed["writeCalls"]:
            errors.append("read-only decision observed writes")
    if expected["readiness"] == "needs-clarification":
        if decision != "unavailable":
            errors.append("needs-clarification decision exposed apply confirmation")
        if observed["ledger"]:
            errors.append("needs-clarification decision recorded a result ledger")
    if decision == "proposal-only":
        expected_ledger = {
            item["ref"]: ("reused", item.get("existingId"))
            for item in expected["items"]
            if item["action"] == "reuse"
        }
        actual_ledger = {
            row["ref"]: (row["status"], row.get("actualId"))
            for row in observed["ledger"]
        }
        if len(actual_ledger) != len(observed["ledger"]) or actual_ledger != expected_ledger:
            errors.append("proposal-only ledger does not exactly match reused nodes")
    if expected["disposition"] == "no-item":
        if decision != "not-required":
            errors.append("no-item decision exposed apply confirmation")
        expected_ledger = {}
        for item in scenario["input"].get("existingItems", []):
            ref = existing_proposal_ref(item) or item.get("proposalRef")
            if not ref or item.get("classification") not in {
                "owner",
                "owner-node",
                "duplicate",
                "duplicate-node",
            }:
                continue
            status = "reused" if item["classification"] in {"owner", "owner-node"} else "skipped"
            expected_ledger[ref] = (status, item["id"])
        actual_ledger = {
            row["ref"]: (row["status"], row.get("actualId"))
            for row in observed["ledger"]
        }
        if len(actual_ledger) != len(observed["ledger"]) or actual_ledger != expected_ledger:
            errors.append("no-item ledger does not exactly match classified existing nodes")
    if decision == "decline":
        if observed["writeCalls"]:
            errors.append("declined proposal observed writes")
        item_refs = {item["ref"] for item in expected["items"]}
        ledger_refs = {row["ref"] for row in observed["ledger"]}
        if len(ledger_refs) != len(observed["ledger"]) or ledger_refs != item_refs or any(
            row["status"] != "declined" or row.get("actualId") is not None
            for row in observed["ledger"]
        ):
            errors.append("declined proposal ledger is not exact")


def validate_observed_apply(scenario: dict[str, Any], errors: list[str]) -> None:
    observed = scenario["observed"]
    calls = observed["writeCalls"]
    decision = scenario["confirmation"]["decision"]
    if not calls:
        if decision == "apply" and scenario["expected"]["logicalWrites"]:
            errors.append("confirmed apply lacks observed operations")
        return
    if decision != "apply":
        errors.append("writes were observed without apply confirmation")
        return

    expected_keys = [operation_key(write) for write in scenario["expected"]["logicalWrites"]]
    observed_keys = [operation_key(call) for call in calls]
    if observed_keys != expected_keys:
        errors.append("observed operations do not match the full confirmed apply sequence")

    ledger_by_ref = {row["ref"]: row for row in observed["ledger"]}
    if len(ledger_by_ref) != len(observed["ledger"]):
        errors.append("result ledger contains duplicate refs")
    call_refs = {call.get("ref") for call in calls}
    if set(ledger_by_ref) != call_refs:
        errors.append("result ledger refs do not exactly match observed operations")
    for call in calls:
        row = ledger_by_ref.get(call.get("ref"))
        if not row:
            errors.append(f"observed {call.get('ref')} call lacks a ledger row")
            continue
        if row.get("status") != call.get("status") or row.get("actualId") != call.get("actualId"):
            errors.append(f"observed {call.get('ref')} call disagrees with its ledger row")
        if call.get("status") == "created" and not call.get("actualId"):
            errors.append(f"created {call.get('ref')} call lacks an actual ID")
        if call.get("status") in {"failed", "skipped"} and call.get("actualId") is not None:
            errors.append(f"{call.get('status')} {call.get('ref')} call unexpectedly has an actual ID")


def validate_existing_reuse(scenario: dict[str, Any], errors: list[str]) -> None:
    authoritative = [
        item
        for item in scenario["input"].get("existingItems", [])
        if item.get("classification") in {"owner", "owner-node"}
        and existing_proposal_ref(item)
    ]
    if not authoritative:
        return
    evidenced_ids = {existing_proposal_ref(item): item["id"] for item in authoritative}
    proposed_ids = {
        item["ref"]: item.get("existingId")
        for item in scenario["expected"]["items"]
        if item["action"] in {"reuse", "update-type"}
    }
    if proposed_ids != evidenced_ids:
        errors.append("proposed existing IDs do not exactly match authoritative source nodes")

    expected_reuse = {
        item["ref"]: item.get("existingId")
        for item in scenario["expected"]["items"]
        if item["action"] == "reuse"
    }
    ledger_reuse = {
        row["ref"]: row.get("actualId")
        for row in scenario["observed"]["ledger"]
        if row["status"] == "reused"
    }
    if ledger_reuse != expected_reuse:
        errors.append("reuse ledger does not exactly match proposed existing nodes")

    evidenced_parents = {
        (existing_proposal_ref(item), item["parentProposalRef"])
        for item in authoritative
        if item.get("parentProposalRef")
    }
    proposed_parents = {
        (relationship["from"], relationship["to"])
        for relationship in scenario["expected"]["relationships"]
        if relationship["kind"] == "parent" and relationship["from"] in evidenced_ids
    }
    if proposed_parents != evidenced_parents:
        errors.append("proposed reuse topology does not match authoritative source nodes")


def validate_duplicate_reuse(scenario: dict[str, Any], errors: list[str]) -> None:
    if "duplicate" not in scenario["covers"]:
        return
    existing = scenario["input"]["existingItems"]
    authoritative = [
        item for item in existing if item["classification"] in {"owner", "owner-node"}
    ]
    duplicates = [
        item for item in existing if item["classification"] in {"duplicate", "duplicate-node"}
    ]
    if len([item for item in authoritative if item["classification"] == "owner"]) != 1 or not duplicates:
        errors.append("duplicate fixture lacks one authoritative owner/tree and a duplicate")
        return
    expected_reuse = {
        (item.get("proposalRef") or "owner"): item["id"]
        for item in authoritative
        if item.get("proposalRef") or item["classification"] == "owner"
    }
    actual_reuse = {
        item["ref"]: item.get("existingId")
        for item in scenario["expected"]["items"]
        if item["action"] == "reuse"
    }
    if actual_reuse != expected_reuse:
        errors.append("duplicate fixture did not reuse the complete authoritative owner tree")
    duplicate_ids = {item["id"] for item in duplicates}
    if duplicate_ids & set(actual_reuse.values()):
        errors.append("duplicate fixture reused a non-authoritative tree node")
    if scenario["expected"]["logicalWrites"]:
        errors.append("duplicate reuse fixture proposes mutation")


def validate_partial_materialization(scenario: dict[str, Any], errors: list[str]) -> None:
    if "partial-materialization" not in scenario["covers"]:
        return
    existing_refs = {
        item["proposalRef"]
        for item in scenario["input"]["existingItems"]
        if item["classification"] in {"owner", "owner-node"}
    }
    candidate_refs = {
        candidate["ref"] for candidate in scenario["input"]["candidateOutcomes"]
    }
    expected_reuse_refs = {
        item["ref"] for item in scenario["expected"]["items"] if item["action"] == "reuse"
    }
    create_refs = {
        item["ref"] for item in scenario["expected"]["items"] if item["action"] == "create"
    }
    if expected_reuse_refs != existing_refs:
        errors.append("partial rerun does not reuse every existing proposal ref")
    if create_refs != candidate_refs - existing_refs:
        errors.append("partial rerun does not create exactly the missing outcome refs")
    if create_refs & existing_refs:
        errors.append("partial rerun would duplicate an existing proposal ref")


def validate_partial_recovery(scenario: dict[str, Any], errors: list[str]) -> None:
    if "partial-failure" not in scenario["covers"]:
        return
    calls = scenario["observed"]["writeCalls"]
    ledger = scenario["observed"]["ledger"]
    statuses = {row["status"] for row in ledger}
    if not {"created", "failed", "skipped"}.issubset(statuses):
        errors.append("partial-failure ledger lacks created, failed, and skipped states")

    successful = {
        row["ref"]: row["actualId"]
        for row in ledger
        if row["status"] in {"created", "reused", "updated"} and row.get("actualId")
    }
    recovery = scenario.get("recovery", {})
    if recovery.get("reuseMappings") != successful:
        errors.append("recovery does not preserve every successful actual ID")

    recovery_keys = [operation_key(write) for write in recovery.get("logicalWrites", [])]
    retry_keys = [
        operation_key(call) for call in calls if call.get("status") in {"failed", "skipped"}
    ]
    if recovery_keys != retry_keys:
        errors.append("recovery write set does not match failed/skipped operations")

    successful_refs = set(successful)
    recovery_create_refs = {
        write.get("ref")
        for write in recovery.get("logicalWrites", [])
        if write.get("action") == "create"
    }
    if recovery_create_refs & successful_refs:
        errors.append("recovery would duplicate a successful item")


def validate_mechanical_sequence(scenario: dict[str, Any], errors: list[str]) -> None:
    if "mechanical-sequence" not in scenario["covers"]:
        return
    if not scenario["input"].get("planSequence"):
        errors.append("mechanical-sequence fixture lacks a source sequence")
    if any(
        relationship["kind"] == "blocking"
        for relationship in scenario["expected"]["relationships"]
    ):
        errors.append("mechanical plan sequence produced a blocking edge")


def validate_scenario(scenario: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = scenario["expected"]
    readiness, disposition = derive_decision(scenario["input"])
    if (expected["readiness"], expected["disposition"]) != (readiness, disposition):
        errors.append(
            "expected decision does not match policy oracle: "
            f"{expected['readiness']}/{expected['disposition']} != {readiness}/{disposition}"
        )

    validate_traceability(scenario, errors)
    validate_write_set(scenario, errors)
    validate_epic(scenario, errors)
    validate_no_mutation_paths(scenario, errors)
    validate_observed_apply(scenario, errors)
    validate_existing_reuse(scenario, errors)
    validate_duplicate_reuse(scenario, errors)
    validate_partial_materialization(scenario, errors)
    validate_partial_recovery(scenario, errors)
    validate_mechanical_sequence(scenario, errors)
    return errors


class PlanToBacklogDecisionFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenarios = load_scenarios()
        cls.by_id = {scenario["id"]: scenario for scenario in cls.scenarios}

    def test_frozen_scenarios_satisfy_policy_contract(self) -> None:
        self.assertEqual(set(REQUIRED_MATRIX), set(self.by_id))
        failures = {
            scenario["id"]: errors
            for scenario in self.scenarios
            if (errors := validate_scenario(scenario))
        }
        self.assertEqual({}, failures)

    def test_required_matrix_has_expected_decisions(self) -> None:
        actual = {
            identifier: derive_decision(self.by_id[identifier]["input"])
            for identifier in REQUIRED_MATRIX
        }
        self.assertEqual(REQUIRED_MATRIX, actual)

    def test_mechanical_steps_do_not_create_children(self) -> None:
        scenario = self.by_id["mechanical-single-outcome"]
        self.assertGreater(len(scenario["input"]["mechanicalSteps"]), 1)
        self.assertEqual(("ready", "single-item"), derive_decision(scenario["input"]))
        self.assertEqual(["owner"], [item["ref"] for item in scenario["expected"]["items"]])

    def test_tightly_coupled_two_outcomes_collapse(self) -> None:
        scenario = self.by_id["tightly-coupled-two-outcomes"]
        self.assertEqual(2, len(scenario["input"]["candidateOutcomes"]))
        self.assertEqual(("ready", "single-item"), derive_decision(scenario["input"]))
        self.assertFalse(has_two_outcome_epic_boundary(scenario["input"], qualifying_outcomes(scenario["input"])))

    def test_two_outcome_epic_requires_evidenced_cross_repository_boundaries(self) -> None:
        scenario_input = copy.deepcopy(self.by_id["cross-repository-two-outcomes"]["input"])
        self.assertEqual(("ready", "epic"), derive_decision(scenario_input))
        scenario_input["aggregateOwnershipEvidence"] = ""
        self.assertEqual(("ready", "single-item"), derive_decision(scenario_input))
        scenario_input = copy.deepcopy(self.by_id["cross-repository-two-outcomes"]["input"])
        scenario_input["candidateOutcomes"][1]["repository"] = "api"
        self.assertEqual(("ready", "single-item"), derive_decision(scenario_input))

    def test_duplicate_tree_reuses_every_authoritative_node(self) -> None:
        scenario = self.by_id["existing-duplicate-tree"]
        self.assertEqual([], validate_scenario(scenario))
        self.assertEqual([], scenario["expected"]["logicalWrites"])
        self.assertEqual(3, len(scenario["expected"]["items"]))

    def test_partial_tree_proposes_only_missing_actions(self) -> None:
        scenario = self.by_id["partially-materialized-tree"]
        self.assertEqual([], validate_scenario(scenario))
        self.assertEqual(
            [("create", "child-2", "owner"), ("add-blocker", "child-2", "child-1")],
            [operation_key(write) for write in scenario["expected"]["logicalWrites"]],
        )

    def test_more_than_six_outcomes_requires_clarification(self) -> None:
        scenario = self.by_id["more-than-six-candidates"]
        self.assertEqual(7, len(qualifying_outcomes(scenario["input"])))
        self.assertEqual(("needs-clarification", None), derive_decision(scenario["input"]))
        self.assertEqual([], scenario["expected"]["logicalWrites"])

    def test_ambiguous_owners_require_clarification(self) -> None:
        scenario_input = copy.deepcopy(self.by_id["no-item-existing-owner"]["input"])
        scenario_input["existingItems"].append(
            {
                "id": "fixture-102",
                "classification": "owner",
                "exactCompleteOutcome": True,
                "matchEvidence": "Competing complete owner",
            }
        )
        self.assertEqual(("needs-clarification", None), derive_decision(scenario_input))

    def test_recovery_requires_every_failed_and_skipped_operation(self) -> None:
        scenario = copy.deepcopy(self.by_id["partial-failure-recovery"])
        scenario["recovery"]["logicalWrites"].pop()
        self.assertIn(
            "recovery write set does not match failed/skipped operations",
            validate_scenario(scenario),
        )

    def test_recovery_preserves_confirmed_parent_and_dependency_refs(self) -> None:
        scenario = copy.deepcopy(self.by_id["partial-failure-recovery"])
        scenario["recovery"]["logicalWrites"][0]["parent"] = "bogus-owner"
        scenario["recovery"]["logicalWrites"][1]["prerequisite"] = "bogus-child"
        self.assertIn(
            "recovery write set does not match failed/skipped operations",
            validate_scenario(scenario),
        )

    def test_observed_apply_must_match_the_confirmed_write_set(self) -> None:
        scenario = copy.deepcopy(self.by_id["partial-failure-recovery"])
        scenario["observed"]["writeCalls"].pop(1)
        self.assertIn(
            "observed operations do not match the full confirmed apply sequence",
            validate_scenario(scenario),
        )
        scenario = copy.deepcopy(self.by_id["partial-failure-recovery"])
        scenario["observed"]["writeCalls"].append(
            {"action": "delete", "ref": "owner", "status": "failed", "actualId": None}
        )
        self.assertIn(
            "observed operations do not match the full confirmed apply sequence",
            validate_scenario(scenario),
        )

    def test_extra_ledger_rows_are_rejected(self) -> None:
        scenario = copy.deepcopy(self.by_id["partial-failure-recovery"])
        scenario["observed"]["ledger"].append(
            {"ref": "ghost", "status": "failed", "actualId": None}
        )
        self.assertIn(
            "result ledger refs do not exactly match observed operations",
            validate_scenario(scenario),
        )

    def test_read_only_ledgers_are_exact(self) -> None:
        scenario = copy.deepcopy(self.by_id["unapproved-plan"])
        scenario["confirmation"]["decision"] = "apply"
        scenario["observed"]["ledger"].append(
            {"ref": "owner", "status": "created", "actualId": "fixture-999"}
        )
        errors = validate_scenario(scenario)
        self.assertIn("needs-clarification decision exposed apply confirmation", errors)
        self.assertIn("needs-clarification decision recorded a result ledger", errors)

        scenario = copy.deepcopy(self.by_id["declined-apply"])
        scenario["observed"]["ledger"][0]["ref"] = "forged-ref"
        self.assertIn("declined proposal ledger is not exact", validate_scenario(scenario))

        scenario = copy.deepcopy(self.by_id["declined-apply"])
        scenario["observed"]["ledger"].append(copy.deepcopy(scenario["observed"]["ledger"][0]))
        self.assertIn("declined proposal ledger is not exact", validate_scenario(scenario))

        scenario = copy.deepcopy(self.by_id["no-item-existing-owner"])
        scenario["observed"]["ledger"].append(copy.deepcopy(scenario["observed"]["ledger"][0]))
        self.assertIn(
            "no-item ledger does not exactly match classified existing nodes",
            validate_scenario(scenario),
        )

        scenario = copy.deepcopy(self.by_id["partially-materialized-tree"])
        scenario["observed"]["ledger"].append(
            {"ref": "ghost", "status": "failed", "actualId": None}
        )
        self.assertIn(
            "proposal-only ledger does not exactly match reused nodes",
            validate_scenario(scenario),
        )

    def test_failed_or_skipped_calls_cannot_have_actual_ids(self) -> None:
        scenario = copy.deepcopy(self.by_id["partial-failure-recovery"])
        failed_call = next(
            call for call in scenario["observed"]["writeCalls"] if call["status"] == "failed"
        )
        failed_row = next(
            row for row in scenario["observed"]["ledger"] if row["status"] == "failed"
        )
        failed_call["actualId"] = "fixture-duplicate-risk"
        failed_row["actualId"] = "fixture-duplicate-risk"
        self.assertIn(
            "failed child-2 call unexpectedly has an actual ID",
            validate_scenario(scenario),
        )

    def test_existing_tree_identity_topology_and_reuse_ledger_are_exact(self) -> None:
        scenario = copy.deepcopy(self.by_id["existing-duplicate-tree"])
        scenario["expected"]["relationships"] = []
        self.assertIn(
            "proposed reuse topology does not match authoritative source nodes",
            validate_scenario(scenario),
        )

        scenario = copy.deepcopy(self.by_id["partially-materialized-tree"])
        scenario["expected"]["items"][0]["existingId"] = "unrelated-owner"
        scenario["observed"]["ledger"] = []
        errors = validate_scenario(scenario)
        self.assertIn("proposed existing IDs do not exactly match authoritative source nodes", errors)
        self.assertIn("reuse ledger does not exactly match proposed existing nodes", errors)

    def test_decline_cannot_record_a_write(self) -> None:
        scenario = copy.deepcopy(self.by_id["declined-apply"])
        scenario["observed"]["writeCalls"].append({"action": "create", "ref": "owner"})
        self.assertIn("declined proposal observed writes", validate_scenario(scenario))

    def test_mechanical_sequence_has_no_blocking_edges(self) -> None:
        scenario = self.by_id["mechanical-dependency-sequence"]
        self.assertEqual([], validate_scenario(scenario))
        self.assertFalse(
            any(
                relationship["kind"] == "blocking"
                for relationship in scenario["expected"]["relationships"]
            )
        )

    def test_blockers_need_declared_refs_and_acceptance_dependencies(self) -> None:
        scenario = copy.deepcopy(self.by_id["bounded-epic-conversion"])
        blocker = next(
            relationship
            for relationship in scenario["expected"]["relationships"]
            if relationship["kind"] == "blocking"
        )
        blocker["to"] = "bogus-child"
        blocker["rationale"] = "Do first because this is the planned work sequence."
        blocker["acceptanceCondition"] = ""
        errors = validate_scenario(scenario)
        self.assertIn("relationship references an undeclared proposal ref", errors)
        self.assertIn("blocking relationship lacks an acceptance condition", errors)
        self.assertIn("blocking relationship represents plan-step sequencing", errors)
        self.assertIn("logical blocker writes do not exactly match proposed blocking relationships", errors)

    def test_blocker_endpoints_must_match_source_acceptance_evidence(self) -> None:
        scenario = copy.deepcopy(self.by_id["bounded-epic-conversion"])
        blocker = next(
            relationship
            for relationship in scenario["expected"]["relationships"]
            if relationship["kind"] == "blocking"
        )
        blocker.update(
            {
                "from": "child-3",
                "to": "child-2",
                "rationale": "Child 3 cannot satisfy acceptance until child 2 exists.",
                "acceptanceCondition": "Child 2 is available.",
            }
        )
        blocker_write = next(
            write
            for write in scenario["expected"]["logicalWrites"]
            if write["action"] == "add-blocker"
        )
        blocker_write.update({"dependent": "child-3", "prerequisite": "child-2"})
        self.assertIn(
            "blocking relationships do not match source acceptance dependencies",
            validate_scenario(scenario),
        )


if __name__ == "__main__":
    unittest.main()
