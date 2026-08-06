#!/usr/bin/env python3
import argparse
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


CONTRACT_VERSION = "workspace-admin-watch/v2"
SOURCE_ORDER = ("git", "beads", "jira")
SCOPES = {"git": "workspace", "beads": "workspace", "jira": "assigned-jira-portfolio"}
RECORD_CAPS = {"git": 1000, "beads": 200, "jira": 100}
ENVELOPE_BYTES = 64 * 1024
STATE_BYTES = 128 * 1024
STRING_BYTES = 256
DIAGNOSTIC_BYTES = 240
EVENT_CAP = 50
SEEN_EVENT_CAP = 128
DEGRADED_PROBE_SECONDS = 3600

ENVELOPE_FIELDS = {"source", "scope", "status", "observedAt", "coverage", "records", "error"}
COVERAGE_FIELDS = {"total", "included", "omitted", "selectionBasis"}
RECORD_FIELDS = {
    "git": {
        "id",
        "entityType",
        "head",
        "commit",
        "branch",
        "worktree",
        "present",
        "dirty",
        "upstream",
        "ahead",
        "behind",
        "detached",
    },
    "beads": {"id", "status", "priority", "blockers", "dependencies", "owningStore"},
    "jira": {"id", "status", "priority", "assignee", "sprint", "due"},
}
LIST_FIELDS = {"blockers", "dependencies"}
GIT_ENTITY_TYPES = {"repository", "branch", "worktree"}
STATE_FIELDS = {
    "contractVersion",
    "tickCount",
    "maxTicks",
    "stopAt",
    "stopped",
    "stopReason",
    "sources",
    "seenEventIds",
    "warmUntil",
}
SOURCE_STATE_FIELDS = {
    "scope",
    "revision",
    "records",
    "coverage",
    "hasData",
    "failureStreak",
    "partialStreak",
    "degraded",
    "nextProbeAt",
    "lastStatus",
    "lastObservedAt",
}
CHANGE_KINDS = {
    "git": ("git_observed", "no_longer_observed", "git_changed"),
    "beads": ("bead_created", "no_longer_observed", "bead_changed"),
    "jira": ("entered_assigned_non_done_set", "left_assigned_non_done_set", "jira_changed"),
}


def serialized_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty string")
    _validate_string(value, "timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("timestamp must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_string(value: str, field: str, limit: int = STRING_BYTES) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{field} contains control characters")
    if len(value.encode("utf-8")) > limit:
        raise ValueError(f"{field} exceeds {limit} UTF-8 bytes")
    return value


def _bounded_diagnostic(value: str) -> str:
    clean = " ".join(value.split())
    encoded = clean.encode("utf-8")
    if len(encoded) <= DIAGNOSTIC_BYTES:
        return clean
    return encoded[:DIAGNOSTIC_BYTES].decode("utf-8", errors="ignore")


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def initial_state(max_ticks: int | None = None, stop_at: str | None = None) -> dict[str, Any]:
    if max_ticks is not None and (isinstance(max_ticks, bool) or not 1 <= max_ticks <= 96):
        raise ValueError("max_ticks must be between 1 and 96")
    if stop_at is not None:
        parse_timestamp(stop_at)
    return {
        "contractVersion": CONTRACT_VERSION,
        "tickCount": 0,
        "maxTicks": max_ticks,
        "stopAt": stop_at,
        "stopped": False,
        "stopReason": None,
        "sources": {},
        "seenEventIds": [],
        "warmUntil": None,
    }


def stop(state: dict[str, Any], reason: str = "user_stop") -> dict[str, Any]:
    stopped = copy.deepcopy(state)
    stopped["stopped"] = True
    stopped["stopReason"] = _bounded_diagnostic(str(reason))
    return stopped


def _normalize_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    normalized = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field} entries must be non-empty strings")
        normalized.append(_validate_string(item, field))
    return sorted(set(normalized))


def _normalize_scalar(value: Any, field: str) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _validate_string(value, field)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ValueError(f"{field} has unsupported value type")


def normalize_record(source: str, record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    unknown = set(record) - RECORD_FIELDS[source]
    if unknown:
        raise ValueError(f"unknown record fields: {', '.join(sorted(unknown))}")
    identity = record.get("id")
    if not isinstance(identity, str) or not identity:
        raise ValueError("record id must be a non-empty string")
    normalized = {"id": _validate_string(identity, "id")}
    for field in sorted(set(record) - {"id"}):
        value = record[field]
        if field in LIST_FIELDS:
            normalized[field] = _normalize_list(value, field)
        else:
            normalized[field] = _normalize_scalar(value, field)
    if source == "git":
        entity_type = normalized.get("entityType", "repository")
        if entity_type not in GIT_ENTITY_TYPES:
            raise ValueError("git entityType must be repository, branch, or worktree")
        normalized["entityType"] = entity_type
        for field in ("ahead", "behind"):
            if field in normalized:
                _non_negative_int(normalized[field], field)
    if source == "beads" and "priority" in normalized:
        priority = normalized["priority"]
        if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 4:
            raise ValueError("bead priority must be an integer from 0 through 4")
    return normalized


def normalize_records(source: str, records: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list):
        raise ValueError("records must be an array")
    if len(records) > RECORD_CAPS[source]:
        raise ValueError(f"record cap exceeded: {len(records)} > {RECORD_CAPS[source]}")
    normalized: dict[str, dict[str, Any]] = {}
    for record in records:
        item = normalize_record(source, record)
        identity = item["id"]
        if identity in normalized:
            raise ValueError(f"duplicate record id: {identity}")
        normalized[identity] = item
    return dict(sorted(normalized.items()))


def normalize_coverage(status: str, coverage: Any, record_count: int) -> dict[str, Any]:
    if not isinstance(coverage, dict):
        raise ValueError("coverage must be an object")
    unknown = set(coverage) - COVERAGE_FIELDS
    missing = COVERAGE_FIELDS - set(coverage)
    if unknown:
        raise ValueError(f"unknown coverage fields: {', '.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"missing coverage fields: {', '.join(sorted(missing))}")
    total = _non_negative_int(coverage["total"], "coverage.total")
    included = _non_negative_int(coverage["included"], "coverage.included")
    omitted = _non_negative_int(coverage["omitted"], "coverage.omitted")
    basis = coverage["selectionBasis"]
    if not isinstance(basis, str) or not basis:
        raise ValueError("coverage.selectionBasis must be a non-empty string")
    basis = _validate_string(basis, "coverage.selectionBasis")
    if included != record_count or total != included + omitted:
        raise ValueError("coverage counts do not match records")
    if status == "complete" and omitted != 0:
        raise ValueError("complete coverage cannot omit records")
    if status == "partial" and omitted == 0:
        raise ValueError("partial coverage must omit at least one record")
    return {"total": total, "included": included, "omitted": omitted, "selectionBasis": basis}


def normalize_envelope(source: str, envelope: Any) -> dict[str, Any]:
    if serialized_bytes(envelope) > ENVELOPE_BYTES:
        raise ValueError(f"source envelope exceeds {ENVELOPE_BYTES} bytes")
    if not isinstance(envelope, dict):
        raise ValueError("source envelope must be an object")
    unknown = set(envelope) - ENVELOPE_FIELDS
    if unknown:
        raise ValueError(f"unknown envelope fields: {', '.join(sorted(unknown))}")
    for field in ("source", "scope", "status", "observedAt"):
        if field not in envelope:
            raise ValueError(f"missing envelope field: {field}")
    if envelope["source"] != source:
        raise ValueError("envelope source does not match source key")
    if envelope["scope"] != SCOPES[source]:
        raise ValueError(f"invalid scope for {source}")
    status = envelope["status"]
    if status not in {"complete", "partial", "error"}:
        raise ValueError("status must be complete, partial, or error")
    observed_at = format_timestamp(parse_timestamp(envelope["observedAt"]))
    if status == "error":
        return {
            "source": source,
            "scope": SCOPES[source],
            "status": status,
            "observedAt": observed_at,
            "records": {},
            "coverage": None,
        }
    records = normalize_records(source, envelope.get("records"))
    coverage = normalize_coverage(status, envelope.get("coverage"), len(records))
    return {
        "source": source,
        "scope": SCOPES[source],
        "status": status,
        "observedAt": observed_at,
        "records": records,
        "coverage": coverage,
    }


def validate_state(state: Any) -> None:
    if not isinstance(state, dict):
        raise ValueError("state must be an object")
    unknown = set(state) - STATE_FIELDS
    missing = STATE_FIELDS - set(state)
    if unknown:
        raise ValueError(f"unknown state fields: {', '.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"missing state fields: {', '.join(sorted(missing))}")
    if state["contractVersion"] != CONTRACT_VERSION:
        raise ValueError("state contract version mismatch")
    _non_negative_int(state["tickCount"], "tickCount")
    max_ticks = state["maxTicks"]
    if max_ticks is not None and (isinstance(max_ticks, bool) or not isinstance(max_ticks, int) or not 1 <= max_ticks <= 96):
        raise ValueError("maxTicks must be between 1 and 96")
    for field in ("stopAt", "warmUntil"):
        if state[field] is not None:
            parse_timestamp(state[field])
    if not isinstance(state["stopped"], bool):
        raise ValueError("stopped must be boolean")
    if state["stopReason"] is not None:
        if not isinstance(state["stopReason"], str):
            raise ValueError("stopReason must be a string")
        _validate_string(state["stopReason"], "stopReason", DIAGNOSTIC_BYTES)
    seen = state["seenEventIds"]
    if not isinstance(seen, list) or len(seen) > SEEN_EVENT_CAP:
        raise ValueError("seenEventIds must be a bounded array")
    for identity in seen:
        if not isinstance(identity, str) or len(identity) != 64 or any(character not in "0123456789abcdef" for character in identity):
            raise ValueError("seen event id must be a SHA-256 hex string")
    sources = state["sources"]
    if not isinstance(sources, dict) or set(sources) - set(SOURCE_ORDER):
        raise ValueError("state sources are invalid")
    for source, source_state in sources.items():
        if not isinstance(source_state, dict) or set(source_state) != SOURCE_STATE_FIELDS:
            raise ValueError(f"{source} state fields are invalid")
        if source_state["scope"] not in {None, SCOPES[source]}:
            raise ValueError(f"{source} state scope is invalid")
        for field in ("revision", "failureStreak", "partialStreak"):
            _non_negative_int(source_state[field], f"{source}.{field}")
        if not isinstance(source_state["records"], dict):
            raise ValueError(f"{source} records must be an object")
        for identity, record in source_state["records"].items():
            normalized = normalize_record(source, record)
            if normalized["id"] != identity:
                raise ValueError(f"{source} record identity mismatch")
            if normalized != record:
                raise ValueError(f"{source} record state is not canonical")
        coverage = source_state["coverage"]
        if coverage is not None:
            if not isinstance(coverage, dict) or set(coverage) != COVERAGE_FIELDS:
                raise ValueError(f"{source} coverage fields are invalid")
            total = _non_negative_int(coverage["total"], f"{source}.coverage.total")
            included = _non_negative_int(coverage["included"], f"{source}.coverage.included")
            omitted = _non_negative_int(coverage["omitted"], f"{source}.coverage.omitted")
            if total != included + omitted or included > len(source_state["records"]):
                raise ValueError(f"{source} coverage counts are invalid")
            basis = coverage["selectionBasis"]
            if not isinstance(basis, str) or not basis:
                raise ValueError(f"{source} coverage selectionBasis is invalid")
            _validate_string(basis, f"{source}.coverage.selectionBasis")
            if omitted == 0 and included != len(source_state["records"]):
                raise ValueError(f"{source} complete coverage count is invalid")
        for field in ("hasData", "degraded"):
            if not isinstance(source_state[field], bool):
                raise ValueError(f"{source}.{field} must be boolean")
        if source_state["lastStatus"] not in {None, "complete", "partial", "error"}:
            raise ValueError(f"{source} lastStatus is invalid")
        for field in ("nextProbeAt", "lastObservedAt"):
            if source_state[field] is not None:
                parse_timestamp(source_state[field])


def due_sources(state: dict[str, Any], now: str) -> list[str]:
    validate_state(state)
    current = parse_timestamp(now)
    due = []
    for source in SOURCE_ORDER:
        source_state = state["sources"].get(source)
        if source_state is None:
            due.append(source)
        elif source_state["degraded"]:
            probe = source_state["nextProbeAt"]
            if probe is not None and current >= parse_timestamp(probe):
                due.append(source)
        elif source == "jira":
            observed = source_state["lastObservedAt"]
            if observed is None or current >= parse_timestamp(observed) + timedelta(seconds=1800):
                due.append(source)
        else:
            due.append(source)
    return due


def _event_id(
    source: str,
    scope: str,
    entity_id: str,
    kind: str,
    from_revision: int,
    to_revision: int,
    before: Any,
    after: Any,
) -> str:
    payload = {
        "source": source,
        "scope": scope,
        "entity": entity_id,
        "kind": kind,
        "fromRevision": from_revision,
        "toRevision": to_revision,
        "before": before,
        "after": after,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def make_event(
    source: str,
    entity_type: str,
    entity_id: str,
    kind: str,
    severity: str,
    from_revision: int,
    to_revision: int,
    before: Any,
    after: Any,
    observed_at: str,
) -> dict[str, Any]:
    scope = SCOPES[source]
    qualified_id = f"{source}:{entity_id}"
    return {
        "contractVersion": CONTRACT_VERSION,
        "eventId": _event_id(
            source,
            scope,
            qualified_id,
            kind,
            from_revision,
            to_revision,
            before,
            after,
        ),
        "source": source,
        "scope": scope,
        "entityType": entity_type,
        "entityId": qualified_id,
        "kind": kind,
        "severity": severity,
        "fromRevision": from_revision,
        "toRevision": to_revision,
        "before": before,
        "after": after,
        "observedAt": observed_at,
    }


def _entity_type(source: str, record: dict[str, Any]) -> str:
    if source == "git":
        return record.get("entityType", "repository")
    return "bead" if source == "beads" else "jira-issue"


def diff_records(
    source: str,
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    from_revision: int,
    to_revision: int,
    observed_at: str,
) -> list[dict[str, Any]]:
    added_kind, removed_kind, changed_kind = CHANGE_KINDS[source]
    events = []
    for identity in sorted(before.keys() - after.keys()):
        record = before[identity]
        events.append(
            make_event(
                source,
                _entity_type(source, record),
                identity,
                removed_kind,
                "info",
                from_revision,
                to_revision,
                record,
                None,
                observed_at,
            )
        )
    for identity in sorted(after.keys() - before.keys()):
        record = after[identity]
        events.append(
            make_event(
                source,
                _entity_type(source, record),
                identity,
                added_kind,
                "info",
                from_revision,
                to_revision,
                None,
                record,
                observed_at,
            )
        )
    for identity in sorted(before.keys() & after.keys()):
        if before[identity] != after[identity]:
            record = after[identity]
            events.append(
                make_event(
                    source,
                    _entity_type(source, record),
                    identity,
                    changed_kind,
                    "info",
                    from_revision,
                    to_revision,
                    before[identity],
                    record,
                    observed_at,
                )
            )
    return events


def _empty_source_state() -> dict[str, Any]:
    return {
        "scope": None,
        "revision": 0,
        "records": {},
        "coverage": None,
        "hasData": False,
        "failureStreak": 0,
        "partialStreak": 0,
        "degraded": False,
        "nextProbeAt": None,
        "lastStatus": None,
        "lastObservedAt": None,
    }


def _failure_update(
    source: str,
    previous: dict[str, Any],
    observed_at: str,
    diagnostic: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    updated = copy.deepcopy(previous)
    from_revision = previous["revision"]
    to_revision = from_revision + 1
    streak = previous["failureStreak"] + 1
    updated.update(
        {
            "scope": SCOPES[source],
            "revision": to_revision,
            "failureStreak": streak,
            "partialStreak": 0,
            "lastStatus": "error",
            "lastObservedAt": observed_at,
        }
    )
    if streak >= 3:
        updated["degraded"] = True
        updated["nextProbeAt"] = format_timestamp(parse_timestamp(observed_at) + timedelta(seconds=DEGRADED_PROBE_SECONDS))
    kind = "source_failed" if streak == 1 else "source_degraded" if streak == 3 else None
    if kind is None:
        return updated, []
    severity = "warning" if streak == 1 else "attention"
    return updated, [
        make_event(
            source,
            "source",
            "source",
            kind,
            severity,
            from_revision,
            to_revision,
            {"failureStreak": streak - 1},
            {"failureStreak": streak, "diagnostic": _bounded_diagnostic(diagnostic)},
            observed_at,
        )
    ]


def _accepted_update(
    source: str,
    previous: dict[str, Any],
    envelope: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from_revision = previous["revision"]
    to_revision = from_revision + 1
    status = envelope["status"]
    incoming = envelope["records"]
    records = incoming if status == "complete" else {**previous["records"], **incoming}
    events = []
    if previous["hasData"]:
        events.extend(diff_records(source, previous["records"], records, from_revision, to_revision, envelope["observedAt"]))

    updated = copy.deepcopy(previous)
    partial_streak = previous["partialStreak"] + 1 if status == "partial" else 0
    updated.update(
        {
            "scope": envelope["scope"],
            "revision": to_revision,
            "records": records,
            "coverage": envelope["coverage"],
            "hasData": True,
            "partialStreak": partial_streak,
            "lastStatus": status,
            "lastObservedAt": envelope["observedAt"],
        }
    )
    if status == "complete":
        if previous["failureStreak"]:
            events.append(
                make_event(
                    source,
                    "source",
                    "source",
                    "source_recovered",
                    "info",
                    from_revision,
                    to_revision,
                    {"failureStreak": previous["failureStreak"], "degraded": previous["degraded"]},
                    {"failureStreak": 0, "degraded": False},
                    envelope["observedAt"],
                )
            )
        updated.update({"failureStreak": 0, "degraded": False, "nextProbeAt": None})
    if status == "partial" and partial_streak in {1, 3}:
        kind = "source_partial" if partial_streak == 1 else "source_partial_persistent"
        events.append(
            make_event(
                source,
                "source",
                "source",
                kind,
                "warning" if partial_streak == 1 else "attention",
                from_revision,
                to_revision,
                {"partialStreak": partial_streak - 1},
                {"partialStreak": partial_streak, "coverage": envelope["coverage"]},
                envelope["observedAt"],
            )
        )
    return updated, events


def _remember_events(state: dict[str, Any], events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    seen = state["seenEventIds"]
    emitted = []
    pruned = 0
    for event in events:
        identity = event["eventId"]
        if identity in seen:
            continue
        seen.append(identity)
        emitted.append(event)
        if len(seen) > SEEN_EVENT_CAP:
            excess = len(seen) - SEEN_EVENT_CAP
            del seen[:excess]
            pruned += excess
    notice = None
    if pruned:
        notice = {"kind": "identity_ledger_pruned", "pruned": pruned, "retained": len(seen)}
    return emitted, notice


def _terminal_result(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return state, {
        "contractVersion": CONTRACT_VERSION,
        "outcome": "terminal",
        "reason": state["stopReason"],
        "events": [],
        "failedSources": [],
        "partialSources": [],
        "omittedEventCount": 0,
        "omittedEventSources": [],
        "identityLedgerNotice": None,
        "delaySeconds": None,
        "tickCount": state["tickCount"],
        "stopped": True,
    }


def tick(state: dict[str, Any], snapshot: Any, now: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if serialized_bytes(state) > STATE_BYTES:
        raise ValueError(f"state byte cap exceeded: {serialized_bytes(state)} > {STATE_BYTES}")
    validate_state(state)
    current = copy.deepcopy(state)
    if current.get("stopped"):
        return _terminal_result(current)
    now_value = parse_timestamp(now)
    if current.get("stopAt") is not None and now_value >= parse_timestamp(current["stopAt"]):
        return _terminal_result(stop(current, "deadline_reached"))
    if current.get("maxTicks") is not None and current["tickCount"] >= current["maxTicks"]:
        return _terminal_result(stop(current, "tick_budget_exhausted"))
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be an object")
    unknown_sources = set(snapshot) - set(SOURCE_ORDER)
    if unknown_sources:
        raise ValueError(f"unsupported sources: {', '.join(sorted(unknown_sources))}")

    had_sources = bool(current["sources"])
    current["tickCount"] += 1
    events = []
    failed_sources = []
    partial_sources = []

    for source in SOURCE_ORDER:
        if source not in snapshot:
            continue
        previous = copy.deepcopy(current["sources"].get(source, _empty_source_state()))
        observed_at = format_timestamp(now_value)
        try:
            envelope = normalize_envelope(source, snapshot[source])
            observed_at = envelope["observedAt"]
            if envelope["status"] == "error":
                updated, source_events = _failure_update(source, previous, observed_at, "collector reported error")
                failed_sources.append(source)
            else:
                updated, source_events = _accepted_update(source, previous, envelope)
                if envelope["status"] == "partial":
                    partial_sources.append(source)
                candidate = copy.deepcopy(current)
                candidate["sources"][source] = updated
                if serialized_bytes(candidate) > STATE_BYTES:
                    raise ValueError(f"state byte cap would exceed {STATE_BYTES} bytes")
        except (TypeError, ValueError) as error:
            updated, source_events = _failure_update(source, previous, observed_at, str(error))
            if source not in failed_sources:
                failed_sources.append(source)
            partial_sources = [name for name in partial_sources if name != source]
        current["sources"][source] = updated
        events.extend(source_events)

    event_priority = {
        "source_failed": 1,
        "source_degraded": 1,
        "source_recovered": 1,
        "source_partial": 1,
        "source_partial_persistent": 1,
    }
    events.sort(key=lambda event: (event_priority.get(event["kind"], 0), SOURCE_ORDER.index(event["source"]), event["entityId"], event["kind"]))
    unique_events, ledger_notice = _remember_events(current, events)
    omitted_count = max(0, len(unique_events) - EVENT_CAP)
    omitted_sources = sorted({event["source"] for event in unique_events[EVENT_CAP:]})
    visible_events = unique_events[:EVENT_CAP]
    if unique_events:
        current["warmUntil"] = format_timestamp(now_value + timedelta(hours=1))
    warm_until = current.get("warmUntil")
    delay_seconds = 300 if warm_until and now_value < parse_timestamp(warm_until) else 900

    extra_pruned = 0
    while serialized_bytes(current) > STATE_BYTES and current["seenEventIds"]:
        del current["seenEventIds"][0]
        extra_pruned += 1
    if extra_pruned:
        if ledger_notice is None:
            ledger_notice = {"kind": "identity_ledger_pruned", "pruned": 0, "retained": 0}
        ledger_notice["pruned"] += extra_pruned
        ledger_notice["retained"] = len(current["seenEventIds"])
    if serialized_bytes(current) > STATE_BYTES:
        raise ValueError(f"state byte cap exceeded after reduction: {serialized_bytes(current)} > {STATE_BYTES}")
    if failed_sources:
        outcome = "partial_failure"
    elif partial_sources:
        outcome = "partial"
    elif visible_events:
        outcome = "material"
    elif not had_sources:
        outcome = "baseline"
    else:
        outcome = "quiet"
    return current, {
        "contractVersion": CONTRACT_VERSION,
        "outcome": outcome,
        "reason": None,
        "events": visible_events,
        "failedSources": failed_sources,
        "partialSources": partial_sources,
        "omittedEventCount": omitted_count,
        "omittedEventSources": omitted_sources,
        "identityLedgerNotice": ledger_notice,
        "delaySeconds": delay_seconds,
        "tickCount": current["tickCount"],
        "stopped": False,
    }


def load_json(path: str) -> Any:
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one workspace-admin watcher reducer tick")
    parser.add_argument("snapshot", nargs="?", help="bounded snapshot JSON path, or - for stdin")
    parser.add_argument("--snapshot-json", help="bounded snapshot as inline JSON")
    parser.add_argument("--state", help="prior state JSON path")
    parser.add_argument("--state-json", help="prior state as inline JSON")
    parser.add_argument("--now", required=True, help="current timezone-qualified ISO-8601 timestamp")
    parser.add_argument("--max-ticks", type=int)
    parser.add_argument("--stop-at")
    parser.add_argument("--due-sources", action="store_true")
    args = parser.parse_args()

    if not args.due_sources and bool(args.snapshot) == bool(args.snapshot_json):
        parser.error("provide exactly one of snapshot or --snapshot-json")
    if args.due_sources and (args.snapshot or args.snapshot_json):
        parser.error("--due-sources does not accept a snapshot")
    if args.state and args.state_json:
        parser.error("provide only one of --state or --state-json")
    state = (
        load_json(args.state)
        if args.state
        else json.loads(args.state_json)
        if args.state_json
        else initial_state(args.max_ticks, args.stop_at)
    )
    if args.due_sources:
        json.dump(
            {"contractVersion": CONTRACT_VERSION, "dueSources": due_sources(state, args.now)},
            sys.stdout,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        sys.stdout.write("\n")
        return 0
    snapshot = load_json(args.snapshot) if args.snapshot else json.loads(args.snapshot_json)
    next_state, result = tick(state, snapshot, args.now)
    json.dump({"state": next_state, "result": result}, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
