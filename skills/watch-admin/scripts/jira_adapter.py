#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import json
import sys
from typing import Any


RECORD_CAP = 100
ENVELOPE_BYTES = 64 * 1024
STRING_BYTES = 256
DIAGNOSTIC_BYTES = 240
PAYLOAD_FIELDS = {"issues", "nextPageToken", "total", "isLast", "startAt", "maxResults"}
ISSUE_FIELDS = {"id", "key", "self", "expand", "fields"}
PROJECTED_FIELDS = {"status", "priority", "assignee", "customfield_10020", "duedate"}


class AdapterError(ValueError):
    pass


def _timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise AdapterError("observed-at must be timezone-qualified ISO-8601") from error
    if parsed.tzinfo is None:
        raise AdapterError("observed-at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _string(value: Any, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value:
        raise AdapterError(f"{field} must be a non-empty string")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise AdapterError(f"{field} contains control characters")
    if len(value.encode("utf-8")) > STRING_BYTES:
        raise AdapterError(f"{field} exceeds {STRING_BYTES} UTF-8 bytes")
    return value


def _named(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _string(value, field)
    if not isinstance(value, dict):
        raise AdapterError(f"{field} must be an object")
    name = value.get("name")
    return _string(name, field, optional=True)


def _assignee(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AdapterError("assignee must be an object")
    identity = value.get("accountId") or value.get("displayName")
    return _string(identity, "assignee", optional=True)


def _sprint(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise AdapterError("sprint must be an array")
    candidates = []
    for sprint in value:
        if not isinstance(sprint, dict) or set(sprint) - {"id", "name", "state", "startDate", "endDate", "completeDate", "goal", "boardId"}:
            raise AdapterError("sprint contains unknown fields")
        name = _string(sprint.get("name"), "sprint name")
        state = sprint.get("state")
        if state not in {"active", "future", "closed"}:
            raise AdapterError("sprint state is invalid")
        start = sprint.get("startDate") or ""
        if start:
            _string(start, "sprint startDate")
        rank = 0 if state == "active" else 1 if state == "future" else 2
        candidates.append((rank, start, name))
    if not candidates:
        return None
    return sorted(candidates)[0][2]


def _project(issue: Any) -> dict[str, Any]:
    if not isinstance(issue, dict) or set(issue) - ISSUE_FIELDS:
        raise AdapterError("issue contains unknown fields")
    key = _string(issue.get("key"), "issue key")
    fields = issue.get("fields")
    if not isinstance(fields, dict) or set(fields) - PROJECTED_FIELDS:
        raise AdapterError("issue fields exceed the Jira projection")
    return {
        "id": key,
        "status": _named(fields.get("status"), "status"),
        "priority": _named(fields.get("priority"), "priority"),
        "assignee": _assignee(fields.get("assignee")),
        "sprint": _sprint(fields.get("customfield_10020")),
        "due": _string(fields.get("duedate"), "due", optional=True),
    }


def _error(observed_at: str, diagnostic: str = "Jira adapter rejected the response") -> dict[str, Any]:
    encoded = " ".join(diagnostic.split()).encode("utf-8")
    bounded = encoded[:DIAGNOSTIC_BYTES].decode("utf-8", errors="ignore")
    return {
        "source": "jira",
        "scope": "assigned-jira-portfolio",
        "status": "error",
        "observedAt": observed_at,
        "coverage": {"total": 0, "included": 0, "omitted": 0, "selectionBasis": "unavailable"},
        "records": [],
        "error": bounded,
    }


def adapt(payload: Any, observed_at: str) -> dict[str, Any]:
    observed_at = _timestamp(observed_at)
    try:
        if not isinstance(payload, dict):
            raise AdapterError("Jira response must be an object")
        if "error" in payload:
            return _error(observed_at)
        if set(payload) - PAYLOAD_FIELDS:
            raise AdapterError("Jira response contains unknown fields")
        issues = payload.get("issues")
        if not isinstance(issues, list):
            raise AdapterError("Jira issues must be an array")
        records_by_id = {}
        for issue in issues:
            record = _project(issue)
            if record["id"] in records_by_id:
                raise AdapterError(f"duplicate Jira issue: {record['id']}")
            records_by_id[record["id"]] = record
        records = [records_by_id[key] for key in sorted(records_by_id)]
        total_value = payload.get("total", len(records))
        if isinstance(total_value, bool) or not isinstance(total_value, int) or total_value < len(records):
            raise AdapterError("Jira total is invalid")
        total = max(total_value, len(records) + (1 if payload.get("nextPageToken") else 0))
        selected = records[:RECORD_CAP]
        while True:
            omitted = total - len(selected)
            envelope = {
                "source": "jira",
                "scope": "assigned-jira-portfolio",
                "status": "partial" if omitted else "complete",
                "observedAt": observed_at,
                "coverage": {
                    "total": total,
                    "included": len(selected),
                    "omitted": omitted,
                    "selectionBasis": "issue key",
                },
                "records": selected,
            }
            if len(json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")) <= ENVELOPE_BYTES:
                return envelope
            if not selected:
                raise AdapterError("Jira metadata exceeds envelope byte cap")
            selected.pop()
    except (AdapterError, TypeError) as error:
        return _error(observed_at, str(error))


def main() -> int:
    parser = argparse.ArgumentParser(description="Project assigned Jira search results into a bounded watcher envelope")
    parser.add_argument("--json", required=True, help="exact Jira search response JSON")
    parser.add_argument("--observed-at", required=True)
    args = parser.parse_args()
    try:
        payload = json.loads(args.json)
    except json.JSONDecodeError:
        payload = {"error": "malformed JSON"}
    json.dump(adapt(payload, args.observed_at), sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
