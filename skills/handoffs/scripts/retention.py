"""Read-only completion clocks shared by the lister and Jira skill-layer promotion."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys


TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?"
    r"(?:Z|[+-](?:[01][0-9]|2[0-3]):?[0-5][0-9])"
)


def timestamp(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        return None
    value = value.replace("Z", "+00:00")
    if re.search(r"[+-][0-9]{4}$", value):
        value = value[:-2] + ":" + value[-2:]
    try:
        return dt.datetime.fromisoformat(value).astimezone(dt.timezone.utc)
    except (ValueError, OverflowError):
        return None


def latest(values: list[object]) -> str:
    parsed = [timestamp(value) for value in values]
    if not parsed or any(value is None for value in parsed):
        return ""
    return max(value for value in parsed if value is not None).isoformat()


def expired(handoff_date: str, completed_at: str, today: str, days: int) -> bool:
    completed = timestamp(completed_at)
    if completed is None:
        return False
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", handoff_date):
            return False
        cutoff = dt.date.fromisoformat(today) - dt.timedelta(days=days)
        return max(dt.date.fromisoformat(handoff_date), completed.date()) < cutoff
    except (ValueError, OverflowError):
        return False


def beads(payload: object, ids: str) -> tuple[int, int, str]:
    expected = set(ids.split(",")) - {""}
    if not isinstance(payload, list):
        raise ValueError("invalid Beads response")
    rows = [row for row in payload if isinstance(row, dict)
            and isinstance(row.get("id"), str) and row["id"] in expected]
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("duplicate Beads identity")
    if not rows:
        return 0, 0, ""
    closed = [row for row in rows if row.get("status") == "closed"]
    return len(closed), len(expected), latest([row.get("closed_at") for row in closed])


def jira(payload: object, keys: str, handoff_date: str, today: str, days: int) -> dict:
    expected = set(keys.split(",")) - {""}
    issues = payload.get("issues", []) if isinstance(payload, dict) else []
    rows = [row for row in issues if isinstance(row, dict)
            and isinstance(row.get("key"), str) and row["key"] in expected] if isinstance(issues, list) else []
    unique = len({row["key"] for row in rows}) == len(rows)
    fields = [row.get("fields") for row in rows]
    done = bool(expected) and unique and len(rows) == len(expected) and all(jira_done(field) for field in fields)
    completed = latest([field.get("resolutiondate") for field in fields]) if done else ""
    return {"done": done, "archive_class": "safe" if done and expired(handoff_date, completed, today, days) else ""}


def jira_done(fields: object) -> bool:
    if not isinstance(fields, dict):
        return False
    status = fields.get("status")
    category = status.get("statusCategory") if isinstance(status, dict) else None
    return isinstance(category, dict) and category.get("key") == "done"


def read_json() -> object:
    try:
        return json.load(sys.stdin)
    except (ValueError, OSError):
        return None


def positive_days(value: str) -> int:
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise argparse.ArgumentTypeError("days must be a positive integer")
    return int(value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    clocks = commands.add_parser("latest")
    clocks.add_argument("timestamps", nargs="*")
    counts = commands.add_parser("beads")
    counts.add_argument("--ids", required=True)
    check = commands.add_parser("expired")
    check.add_argument("--completed-at", required=True)
    tickets = commands.add_parser("jira")
    tickets.add_argument("--keys", required=True)
    for command in (check, tickets):
        command.add_argument("--handoff-date", required=True)
        command.add_argument("--today", required=True)
        command.add_argument("--days", type=positive_days, required=True)
    args = parser.parse_args()
    if args.command == "latest":
        print(latest(args.timestamps))
    elif args.command == "beads":
        try:
            print(*beads(read_json(), args.ids))
        except ValueError:
            parser.exit(2, "unusable Beads response; retain context\n")
    elif args.command == "jira":
        print(json.dumps(jira(read_json(), args.keys, args.handoff_date, args.today, args.days)))
    else:
        raise SystemExit(0 if expired(args.handoff_date, args.completed_at, args.today, args.days) else 1)


if __name__ == "__main__":
    main()
