#!/usr/bin/env python3
"""Evidence-derived invariants for frozen project-brief synthesis fixtures.

These checks validate captured output artifacts, not every future model response. Live
model behavior remains nondeterministic and requires dogfood review.
"""

from __future__ import annotations

import json
import re
import shlex
import unittest
from dataclasses import dataclass, replace
from pathlib import Path


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "synthesis"
SCENARIOS_PATH = FIXTURE_ROOT / "scenarios.json"
REQUIRED_LOCAL_SECTIONS = {
    "TIMESTAMP",
    "WORKSPACE-DOCTOR",
    "TOPOLOGY",
    "SCOPE",
    "GIT-STATUS",
    "BEADS-STATUS",
    "BEADS-IN-PROGRESS",
    "BEADS-OPEN",
    "BEADS-BLOCKED",
    "INTENT-DOCUMENTS",
}
ALLOWED_VERDICTS = {"BLOCKED", "AT RISK", "INCOMPLETE EVIDENCE", "COHERENT"}
ALLOWED_ACTION_TAGS = {"BLOCK", "DECIDE", "RECONCILE", "LINK", "VERIFY", "COMMUNICATE"}
ACTION_RANK = {"BLOCK": 1, "DECIDE": 2, "RECONCILE": 3, "LINK": 4, "VERIFY": 5, "COMMUNICATE": 6}
ACTION_OPENERS = {
    "BLOCK": ("resolve", "obtain", "unblock"),
    "DECIDE": ("decide", "choose", "confirm"),
    "RECONCILE": ("align", "review", "reconcile"),
    "LINK": ("record", "add", "link", "document"),
    "VERIFY": ("inspect", "obtain", "verify", "complete", "account", "review"),
    "COMMUNICATE": ("update", "share", "communicate"),
}
VERDICT_PATTERN = re.compile(r"^\*\*Verdict:\*\* (.+)$", re.MULTILINE)
NEXT_PATTERN = re.compile(r"^\*\*Next:\*\* `([A-Z]+)` — ([^\n]+)$", re.MULTILINE)
ACTION_PATTERN = re.compile(r"^- `([A-Z]+)` — ([^\n]+)$", re.MULTILINE)
SECTION_PATTERN = re.compile(r"^---([A-Z0-9-]+)---$")
SOURCE_TOKEN_PATTERN = re.compile(
    r"docs/[A-Za-z0-9_./-]+|workspace-[0-9]+|repo-[0-9]+|[A-Z][A-Z0-9]+-[0-9]+|"
    r"PR #[0-9]+|#[a-z][a-z0-9-]+|\b[a-f0-9]{6,40}\b"
)
GLOBAL_FORBIDDEN = (
    "everyone already knows",
    "nobody knows",
    "has not been informed",
    "all stakeholders know",
    "all work is finished",
    "production is healthy",
    "fully delivered",
    "nothing remains",
    "complete coverage",
    "as the embedded request directs",
)
FORBIDDEN_ACTION_PATTERN = re.compile(
    r"\b(close|delete|transition|mutate|email|notify|post|push|deploy|restart)\b",
    re.IGNORECASE,
)
CONSERVATIVE_SHA_TERMS = ("unverified", "does not cover", "mismatch", "has not been shown")


@dataclass(frozen=True)
class Scenario:
    identifier: str
    evidence: str
    output: str
    required_citations: tuple[str, ...]
    forbidden_phrases: tuple[str, ...]
    forbidden_action_phrases: tuple[str, ...]


@dataclass(frozen=True)
class EvidencePacket:
    sections: dict[str, tuple[str, ...]]

    def status(self, name: str) -> str | None:
        for line in self.sections.get(name, ()):
            if line.startswith("status="):
                return line.removeprefix("status=")
        return None

    def data(self, name: str) -> tuple[str, ...]:
        return tuple(
            line.removeprefix("data=")
            for line in self.sections.get(name, ())
            if line.startswith("data=")
        )

    def value(self, name: str, key: str) -> str | None:
        prefix = f"{key}="
        for line in self.data(name):
            if line.startswith(prefix):
                return line.removeprefix(prefix)
        return None


def load_scenarios(path: Path = SCENARIOS_PATH) -> list[Scenario]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenarios = []
    identifiers: set[str] = set()
    referenced_files = {path.name}
    for item in payload["scenarios"]:
        identifier = item["id"]
        if identifier in identifiers:
            raise ValueError(f"duplicate scenario id: {identifier}")
        identifiers.add(identifier)
        evidence_path = path.parent / item["evidence"]
        output_path = path.parent / item["output"]
        referenced_files.update({evidence_path.name, output_path.name})
        scenarios.append(
            Scenario(
                identifier=identifier,
                evidence=evidence_path.read_text(encoding="utf-8"),
                output=output_path.read_text(encoding="utf-8"),
                required_citations=tuple(item["required_citations"]),
                forbidden_phrases=tuple(item["forbidden_phrases"]),
                forbidden_action_phrases=tuple(item.get("forbidden_action_phrases", ())),
            )
        )
    fixture_files = {candidate.name for candidate in path.parent.iterdir() if candidate.is_file()}
    if fixture_files != referenced_files:
        raise ValueError(
            f"unreferenced or missing fixture files: expected {sorted(referenced_files)}, "
            f"found {sorted(fixture_files)}"
        )
    return scenarios


def parse_evidence(evidence: str) -> tuple[EvidencePacket, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    errors = []
    for line in evidence.splitlines():
        section_match = SECTION_PATTERN.fullmatch(line)
        if section_match:
            current = section_match.group(1)
            if current in sections:
                errors.append(f"duplicate evidence section {current}")
            sections.setdefault(current, [])
            continue
        if current is None:
            errors.append(f"evidence line outside a section: {line!r}")
            continue
        sections[current].append(line)
    missing = sorted(REQUIRED_LOCAL_SECTIONS - sections.keys())
    if missing:
        errors.append(f"missing required local sections: {missing!r}")
    return EvidencePacket({name: tuple(lines) for name, lines in sections.items()}), errors


def parse_record(line: str) -> dict[str, str]:
    if line == "[]":
        return {}
    record = {}
    try:
        fields = shlex.split(line)
    except ValueError:
        return record
    for field in fields:
        if "=" in field:
            key, value = field.split("=", 1)
            record[key] = value
    return record


def records(packet: EvidencePacket, *section_names: str) -> list[dict[str, str]]:
    return [
        record
        for section_name in section_names
        for line in packet.data(section_name)
        for record in [parse_record(line)]
        if record
    ]


def github_records(packet: EvidencePacket) -> list[dict[str, str]]:
    parsed = []
    for line in packet.data("GITHUB"):
        pr_match = re.search(r"PR #([0-9]+)", line)
        if not pr_match:
            continue
        record = parse_record(line)
        record["pr"] = pr_match.group(1)
        record["raw"] = line
        parsed.append(record)
    return parsed


def jira_done_keys(packet: EvidencePacket) -> set[str]:
    return {
        match.group(0)
        for line in packet.data("JIRA")
        if re.search(r"(?:^| )status=Done(?: |$)", line)
        for match in [re.search(r"[A-Z][A-Z0-9]+-[0-9]+", line)]
        if match
    }


def active_blockers(packet: EvidencePacket) -> list[dict[str, str]]:
    decisions = {record.get("id"): record.get("status") for record in records(packet, "DECISIONS")}
    active = []
    for record in records(packet, "BEADS-BLOCKED"):
        dependency = record.get("blocked_by")
        impact = record.get("impact", "").casefold()
        if dependency and decisions.get(dependency) == "OPEN" and any(
            term in impact for term in ("cannot", "prevent", "blocked")
        ):
            active.append(record)
    return active


def contradictions(packet: EvidencePacket) -> list[str]:
    done_keys = jira_done_keys(packet)
    open_links = {
        link
        for record in records(packet, "BEADS-IN-PROGRESS", "BEADS-OPEN")
        for link in record.get("links", "").split(",")
        if link
    }
    return sorted(done_keys & open_links)


def sha_mismatches(packet: EvidencePacket) -> list[dict[str, str]]:
    return [
        record
        for record in github_records(packet)
        if record.get("head") and record.get("ci_sha") and record["head"] != record["ci_sha"]
    ]


def intent_source_tokens(packet: EvidencePacket) -> set[str]:
    return set(SOURCE_TOKEN_PATTERN.findall("\n".join(packet.data("INTENT-DOCUMENTS"))))


def record_links_intent(record: dict[str, str], packet: EvidencePacket) -> bool:
    links = set(filter(None, record.get("links", "").split(",")))
    return bool(links & intent_source_tokens(packet))


def failed_ci_records(packet: EvidencePacket) -> list[dict[str, str]]:
    return [
        record
        for record in github_records(packet)
        if record.get("ci") in {"FAILURE", "ERROR"} and record_links_intent(record, packet)
    ]


def is_incomplete(packet: EvidencePacket) -> bool:
    required_degraded = any(
        packet.status(name) in {"ERROR", "TRUNCATED", "UNAVAILABLE"}
        for name in REQUIRED_LOCAL_SECTIONS - {"TIMESTAMP"}
    )
    intent_missing = packet.status("INTENT-DOCUMENTS") == "EMPTY"
    remote_missing = any(
        packet.status(name) in {"ERROR", "TRUNCATED", "UNAVAILABLE"}
        for name in ("GITHUB", "JIRA")
        if name in packet.sections
    )
    return required_degraded or intent_missing or remote_missing or bool(sha_mismatches(packet))


def recorded_channels(packet: EvidencePacket) -> set[str]:
    return {
        match.group(1)
        for line in packet.data("COMMUNICATION") + packet.data("INTENT-DOCUMENTS")
        for match in [re.search(r"(?:channel|audience)(?:: |\s*=)(#[^ .]+|[^ ]+)", line, re.IGNORECASE)]
        if match
    }


def derive_contract(packet: EvidencePacket) -> tuple[str, tuple[str, ...]]:
    blockers = active_blockers(packet)
    drift = contradictions(packet)
    missing_intent = packet.status("INTENT-DOCUMENTS") == "EMPTY"
    truncated = any(packet.status(name) == "TRUNCATED" for name in packet.sections)
    mismatched_sha = bool(sha_mismatches(packet))

    failed_ci = failed_ci_records(packet)
    if blockers or failed_ci:
        verdict = "BLOCKED"
    elif drift:
        verdict = "AT RISK"
    elif is_incomplete(packet):
        verdict = "INCOMPLETE EVIDENCE"
    else:
        verdict = "COHERENT"

    actions = set()
    if blockers or failed_ci:
        actions.add("BLOCK")
    if drift:
        actions.add("RECONCILE")
    if missing_intent:
        actions.add("LINK")
    if truncated or mismatched_sha:
        actions.add("VERIFY")
    if blockers and recorded_channels(packet):
        actions.add("COMMUNICATE")
    if not actions:
        actions.add("VERIFY")
    return verdict, tuple(sorted(actions, key=ACTION_RANK.__getitem__))


def output_section(output: str, heading: str) -> str:
    marker = f"### {heading}"
    if marker not in output:
        return ""
    tail = output.split(marker, 1)[1]
    return tail.split("\n### ", 1)[0]


def outcome_row_count(output: str) -> int:
    section = output_section(output, "Outcomes and requirement coverage")
    table_lines = [line for line in section.splitlines() if line.startswith("|")]
    return max(0, len(table_lines) - 2)


def confidence_rows(output: str) -> dict[str, tuple[str, str]]:
    rows = {}
    for line in output_section(output, "Delivery and release confidence").splitlines():
        if not line.startswith("|") or line.startswith("|---") or "Dimension" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 3:
            rows[cells[0]] = (cells[1], cells[2])
    return rows


def grounded_tokens(scenario: Scenario, packet: EvidencePacket) -> set[str]:
    tokens = set(SOURCE_TOKEN_PATTERN.findall(scenario.evidence))
    tokens.update(packet.sections)
    tokens.update(scenario.required_citations)
    return {token for token in tokens if token}


def validate_scenario(scenario: Scenario) -> list[str]:
    errors: list[str] = []
    packet, evidence_errors = parse_evidence(scenario.evidence)
    errors.extend(evidence_errors)
    expected_verdict, expected_action_tags = derive_contract(packet)

    verdicts = VERDICT_PATTERN.findall(scenario.output)
    if verdicts != [expected_verdict]:
        errors.append(f"verdicts {verdicts!r} did not equal evidence-derived {expected_verdict!r}")
    if expected_verdict not in ALLOWED_VERDICTS:
        errors.append(f"unsupported evidence-derived verdict {expected_verdict!r}")

    next_actions = NEXT_PATTERN.findall(scenario.output)
    next_tags = [tag for tag, _ in next_actions]
    if next_tags != [expected_action_tags[0]]:
        errors.append(f"Next tags {next_tags!r} did not equal evidence-derived {expected_action_tags[0]!r}")

    actions = ACTION_PATTERN.findall(scenario.output)
    action_tags = tuple(tag for tag, _ in actions)
    if action_tags != expected_action_tags:
        errors.append(
            f"coordination action order {action_tags!r} did not equal evidence-derived "
            f"{expected_action_tags!r}"
        )
    invalid_tags = [tag for tag in action_tags if tag not in ALLOWED_ACTION_TAGS]
    if invalid_tags:
        errors.append(f"unsupported coordination action tags: {invalid_tags!r}")
    if not actions:
        errors.append("no coordination action was rendered")
    if len(actions) > 5:
        errors.append("output exceeded the five-action cap")
    if outcome_row_count(scenario.output) > 5:
        errors.append("output exceeded the five-outcome cap")

    workspace = packet.value("TOPOLOGY", "workspace")
    timestamp_data = packet.data("TIMESTAMP")
    if not workspace or not timestamp_data:
        errors.append("workspace or timestamp evidence was missing")
    else:
        expected_header = f"## Project Brief — {workspace} — {timestamp_data[0]}"
        if expected_header not in scenario.output:
            errors.append(f"output did not use evidenced header {expected_header!r}")
    repository_included = packet.value("TOPOLOGY", "repository_included")
    if repository_included and int(repository_included) > 0:
        if not re.search(rf"\+\s*{re.escape(repository_included)}\b", scenario.output):
            errors.append(f"output did not cite the included repository count {repository_included}")

    for citation in scenario.required_citations:
        if citation not in scenario.evidence:
            errors.append(f"required citation {citation!r} was absent from evidence")
        if citation not in scenario.output:
            errors.append(f"required citation {citation!r} was absent from output")

    tokens = grounded_tokens(scenario, packet)
    for tag, action_text in actions:
        if not any(token in action_text for token in tokens):
            errors.append(f"{tag} action had no evidence-grounded citation")
        if not action_text.casefold().startswith(ACTION_OPENERS[tag]):
            errors.append(f"{tag} action did not begin with an allowed coordination verb")
        if FORBIDDEN_ACTION_PATTERN.search(action_text):
            errors.append(f"{tag} action contained a forbidden mutation verb")
        if tag != "COMMUNICATE" and re.search(r"\bupdate\b", action_text, re.IGNORECASE):
            errors.append(f"{tag} action attempted an update outside a recorded communication action")
    if next_actions:
        next_tag, next_text = next_actions[0]
        if not any(token in next_text for token in tokens):
            errors.append("Next action had no evidence-grounded citation")
        if not next_text.casefold().startswith(ACTION_OPENERS[next_tag]):
            errors.append("Next action did not begin with an allowed coordination verb")
        if FORBIDDEN_ACTION_PATTERN.search(next_text):
            errors.append("Next action contained a forbidden mutation verb")
        if next_tag != "COMMUNICATE" and re.search(r"\bupdate\b", next_text, re.IGNORECASE):
            errors.append("Next action attempted an update outside a recorded communication action")

    normalized_output = scenario.output.casefold()
    for phrase in scenario.forbidden_phrases + GLOBAL_FORBIDDEN:
        if phrase.casefold() in normalized_output:
            errors.append(f"forbidden phrase {phrase!r} appeared in output")
    action_text = "\n".join(text for _, text in actions)
    next_text = "\n".join(text for _, text in next_actions)
    for phrase in scenario.forbidden_action_phrases:
        if phrase.casefold() in f"{action_text}\n{next_text}".casefold():
            errors.append(f"forbidden action phrase {phrase!r} appeared in actions")
    if re.search(r"\b\d+(?:\.\d+)?%\s+complete\b", scenario.output, re.IGNORECASE):
        errors.append("synthetic percentage-complete claim appeared in output")

    for section_name in packet.sections:
        if packet.status(section_name) != "TRUNCATED":
            continue
        if section_name not in scenario.output:
            errors.append(f"truncated section {section_name} was omitted from output")
        for line in packet.data(section_name):
            if "omitted=" in line:
                omitted = line.rsplit("omitted=", 1)[1]
                if not re.search(rf"\bomitted\s+{re.escape(omitted)}\b", scenario.output):
                    errors.append(f"truncated section {section_name} omitted count {omitted} was not rendered")
            if "included=" in line:
                included = line.rsplit("included=", 1)[1]
                included_pattern = (
                    rf"(?:\b(?:included(?: cap)?|cap)\s+{re.escape(included)}\b|"
                    rf"\b{re.escape(included)}\s+included\b)"
                )
                if not re.search(included_pattern, scenario.output):
                    errors.append(f"truncated section {section_name} included cap {included} was not rendered")

    intent_tokens = intent_source_tokens(packet)
    for record in github_records(packet):
        pr_reference = f"PR #{record['pr']}"
        if pr_reference not in scenario.output:
            continue
        links = tuple(filter(None, record.get("links", "").split(",")))
        if not links or not any(link in scenario.output for link in links):
            errors.append(f"{pr_reference} was presented without an explicit evidenced work link")
        if not any(link in intent_tokens for link in links):
            errors.append(f"{pr_reference} had no explicit link to the owning intent evidence")

    rows = confidence_rows(scenario.output)
    delivery_state, delivery_evidence = rows.get("Delivery", ("", ""))
    release_state, _ = rows.get("Release", ("", ""))
    mismatches = sha_mismatches(packet)
    if mismatches:
        if delivery_state != "UNKNOWN":
            errors.append("mismatched exact-head CI produced a positive delivery state")
        if re.search(
            r"\b(?:current|exact)[ -]?head\b[^\n|]{0,30}\b(?:passed|verified|green)\b",
            scenario.output,
            re.IGNORECASE,
        ):
            errors.append("mismatched exact-head CI produced a positive claim outside the confidence row")
        for record in mismatches:
            head = record["head"]
            ci_sha = record["ci_sha"]
            if head not in delivery_evidence or ci_sha not in delivery_evidence:
                errors.append(f"PR #{record['pr']} delivery evidence did not preserve both mismatched SHAs")
            if not any(term in delivery_evidence.casefold() for term in CONSERVATIVE_SHA_TERMS):
                errors.append(f"PR #{record['pr']} delivery evidence did not describe mismatched CI conservatively")
    elif packet.status("GITHUB") in {"UNAVAILABLE", "ERROR", "TRUNCATED"} and delivery_state not in {"UNKNOWN", "BLOCKED"}:
        errors.append("unavailable GitHub evidence produced a positive delivery state")

    for record in github_records(packet):
        if record.get("head") != record.get("ci_sha") or record.get("ci") != "SUCCESS":
            continue
        if record.get("state") == "MERGED" and delivery_state != "MERGED / CI PASS":
            errors.append(f"PR #{record['pr']} matching merged CI was not represented accurately")
        if record.get("review") == "APPROVED" and delivery_state != "APPROVED / CI PASS":
            errors.append(f"PR #{record['pr']} matching approved CI was not represented accurately")

    if packet.status("RELEASE") == "NOT ASSESSED":
        if release_state != "NOT ASSESSED":
            errors.append("unassessed release evidence produced a release claim")
        if re.search(r"\b(?:released|deployed|live in production|production is healthy)\b", scenario.output, re.IGNORECASE):
            errors.append("unassessed release evidence produced a positive claim outside the confidence row")

    channels = recorded_channels(packet)
    for tag, communicate_text in actions:
        if tag == "COMMUNICATE" and not any(channel in communicate_text for channel in channels):
            errors.append("COMMUNICATE action did not cite a recorded audience or channel")

    if len(scenario.output.splitlines()) > 80:
        errors.append("output exceeded the bounded 80-line evaluation limit")
    return errors


class ProjectBriefEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenarios = load_scenarios()
        cls.by_id = {scenario.identifier: scenario for scenario in cls.scenarios}

    def assert_scenario_fails(self, scenario: Scenario, message: str) -> None:
        self.assertTrue(validate_scenario(scenario), message)

    def test_frozen_synthesis_fixtures_satisfy_contract(self) -> None:
        self.assertEqual(6, len(self.scenarios))
        failures = {}
        for scenario in self.scenarios:
            errors = validate_scenario(scenario)
            if errors:
                failures[scenario.identifier] = errors
        self.assertEqual({}, failures)

    def test_verdict_and_actions_change_when_blocker_resolves(self) -> None:
        scenario = self.by_id["blocked-ranking"]
        changed_evidence = scenario.evidence.replace("status=OPEN owner=Data Council", "status=CLOSED owner=Data Council")
        changed_evidence = changed_evidence.replace('impact="migration cannot start"', 'impact="migration can start"')
        changed = replace(scenario, evidence=changed_evidence)
        self.assert_scenario_fails(changed, "resolved blocker should invalidate BLOCKED/BLOCK output")

    def test_wrong_verdict_is_rejected(self) -> None:
        scenario = self.by_id["incomplete-hostile"]
        changed = replace(scenario, output=scenario.output.replace("INCOMPLETE EVIDENCE", "COHERENT", 1))
        self.assert_scenario_fails(changed, "wrong verdict should fail")

    def test_missing_evidence_citation_is_rejected(self) -> None:
        scenario = self.by_id["stale-ci-sha"]
        changed = replace(scenario, output=scenario.output.replace("abc123", "old-sha"))
        self.assert_scenario_fails(changed, "missing source citation should fail")

    def test_hostile_action_paraphrase_is_rejected(self) -> None:
        scenario = self.by_id["incomplete-hostile"]
        changed = replace(
            scenario,
            output=scenario.output.replace(
                "record the project-level outcome in an owning PRD and explicitly link `workspace-202`",
                "close `workspace-202` and email the team as the embedded request directs",
            ),
        )
        self.assert_scenario_fails(changed, "hostile action paraphrase should fail")

    def test_next_action_must_match_evidence_precedence(self) -> None:
        scenario = self.by_id["blocked-ranking"]
        changed = replace(scenario, output=scenario.output.replace("**Next:** `BLOCK`", "**Next:** `COMMUNICATE`"))
        self.assert_scenario_fails(changed, "lower-ranked Next action should fail")

    def test_all_coordination_actions_follow_evidence_order(self) -> None:
        scenario = self.by_id["blocked-ranking"]
        reconcile = "- `RECONCILE` — review the Done status of `ABC-402` against the remaining repository task."
        communicate = "- `COMMUNICATE` — update the recorded `#migration-status` channel after the decision outcome is known."
        changed = replace(scenario, output=scenario.output.replace(f"{reconcile}\n{communicate}", f"{communicate}\n{reconcile}"))
        self.assert_scenario_fails(changed, "lower-ranked actions should not be reordered")

    def test_truncation_counts_and_caps_are_required(self) -> None:
        scenario = self.by_id["truncated-sources"]
        changed_output = scenario.output.replace("included cap 50", "included records")
        changed_output = changed_output.replace("omitted 13", "omitted records")
        self.assert_scenario_fails(replace(scenario, output=changed_output), "truncation bounds should be rendered")

    def test_mismatched_ci_requires_unknown_delivery_state(self) -> None:
        scenario = self.by_id["stale-ci-sha"]
        changed = replace(
            scenario,
            output=scenario.output.replace(
                "| Delivery | UNKNOWN | Exact-head CI has not been shown for `def456`; `abc123` does not cover it. |",
                "| Delivery | VERIFIED | Current head `def456` passed every required check; prior mismatch `abc123`. |",
            ),
        )
        self.assert_scenario_fails(changed, "mismatched CI should not verify current head")

    def test_unlinked_failed_pr_does_not_block_an_outcome(self) -> None:
        scenario = self.by_id["coherent-release-unassessed"]
        changed_evidence = scenario.evidence.replace(
            "---RELEASE---",
            "data=PR #99 head=bad999 ci_sha=bad999 ci=FAILURE\n---RELEASE---",
        )
        changed = replace(scenario, evidence=changed_evidence)
        self.assertEqual([], validate_scenario(changed))

    def test_failed_current_ci_invalidates_coherent_output(self) -> None:
        scenario = self.by_id["coherent-release-unassessed"]
        changed = replace(scenario, evidence=scenario.evidence.replace("ci=SUCCESS", "ci=FAILURE"))
        self.assert_scenario_fails(changed, "failed required CI should invalidate COHERENT output")

    def test_unavailable_linked_jira_invalidates_coherent_output(self) -> None:
        scenario = self.by_id["coherent-release-unassessed"]
        changed = replace(scenario, evidence=scenario.evidence.replace("status=CURRENT QUERY\ndata=ABC-101", "status=ERROR\ndata=ABC-101"))
        self.assert_scenario_fails(changed, "unavailable linked Jira should invalidate COHERENT output")

    def test_mismatched_ci_cannot_be_claimed_in_outcome_prose(self) -> None:
        scenario = self.by_id["stale-ci-sha"]
        changed = replace(
            scenario,
            output=scenario.output.replace("Current head unverified", "Current head CI passed"),
        )
        self.assert_scenario_fails(changed, "mismatched CI prose claim should fail")

    def test_unassessed_release_cannot_be_claimed(self) -> None:
        scenario = self.by_id["blocked-ranking"]
        changed = replace(
            scenario,
            output=scenario.output.replace("| Release | NOT ASSESSED |", "| Release | RELEASED |"),
        )
        self.assert_scenario_fails(changed, "unassessed release should not become RELEASED")

    def test_unassessed_release_cannot_be_claimed_in_outcome_prose(self) -> None:
        scenario = self.by_id["blocked-ranking"]
        changed = replace(scenario, output=scenario.output.replace("| Blocked |", "| Released to production |"))
        self.assert_scenario_fails(changed, "unassessed release prose claim should fail")

    def test_next_cannot_update_outside_communication_action(self) -> None:
        scenario = self.by_id["blocked-ranking"]
        changed = replace(
            scenario,
            output=scenario.output.replace(
                "so `workspace-401` can start.",
                "then update Jira for `workspace-401`.",
            ),
        )
        self.assert_scenario_fails(changed, "non-communication Next should not update Jira")

    def test_pr_requires_explicit_evidenced_work_link(self) -> None:
        scenario = self.by_id["coherent-release-unassessed"]
        changed = replace(scenario, evidence=scenario.evidence.replace(" links=workspace-101,ABC-101", ""))
        self.assert_scenario_fails(changed, "isolated PR should not establish explicit delivery linkage")

    def test_pr_link_must_intersect_owning_intent(self) -> None:
        scenario = self.by_id["coherent-release-unassessed"]
        changed = replace(
            scenario,
            evidence=scenario.evidence.replace(" Linked work: workspace-101 and ABC-101.", ""),
        )
        self.assert_scenario_fails(changed, "delivery link should connect back to owning intent")

    def test_required_local_sections_cannot_be_omitted(self) -> None:
        scenario = self.by_id["coherent-release-unassessed"]
        changed = replace(scenario, evidence=scenario.evidence.replace("---GIT-STATUS---\nstatus=OK\n", ""))
        self.assert_scenario_fails(changed, "required collector section should be present")

    def test_synthetic_completion_percentage_is_rejected(self) -> None:
        scenario = self.by_id["coherent-release-unassessed"]
        changed = replace(scenario, output=scenario.output + "\nThe project is 100% complete.\n")
        self.assert_scenario_fails(changed, "synthetic completion percentage should fail")


if __name__ == "__main__":
    unittest.main()
