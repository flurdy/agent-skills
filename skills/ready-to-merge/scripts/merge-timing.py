#!/usr/bin/env python3
"""Evaluate the trusted merge-timing policy for one repository at one instant.

The policy is the nearest merge-timing.toml above the repository's top level, so the
pull request being merged cannot edit it. Prints one JSON object. Exit 0 when the
policy is absent or evaluated, 3 when it is malformed or unavailable, 2 for usage errors.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

POLICY_NAME = "merge-timing.toml"
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
ENFORCEMENTS = ("advisory", "required")
RULE_KEYS = {"name", "enforcement", "days", "start", "end", "end_by_day"}
TIME = re.compile(r"^([01]\d|2[0-4]):([0-5]\d)$")
DAY_MINUTES = 24 * 60
SEARCH_DAYS = 8


class PolicyError(Exception):
    pass


def git(directory: Path, *args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(directory), *args], text=True, capture_output=True)
    return result.stdout.strip() if result.returncode == 0 else None


def repository_identity(repo: Path) -> tuple[Path, str]:
    top = git(repo, "rev-parse", "--show-toplevel")
    common = git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not top or not common:
        raise PolicyError(f"{repo} is not inside a Git working tree")
    return Path(top).resolve(), str(Path(common).resolve())


def exists(path: Path) -> bool:
    try:
        path.stat()
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError as error:
        raise PolicyError(f"cannot inspect {path}: {error.strerror}") from error
    return True


def find_policy(top: Path, common_dir: str) -> Path | None:
    for directory in top.parents:
        candidate = directory / POLICY_NAME
        if not exists(candidate):
            continue
        resolved = candidate.resolve()
        owner = git(resolved.parent, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if owner and str(Path(owner).resolve()) == common_dir:
            raise PolicyError(f"{candidate} lies in another checkout of the same repository")
        return candidate
    return None


def minutes(value: Any, field: str, latest: int) -> int:
    match = TIME.match(value) if isinstance(value, str) else None
    if not match:
        raise PolicyError(f"{field} must be an HH:MM string")
    total = int(match[1]) * 60 + int(match[2])
    if total > latest:
        raise PolicyError(f"{field} must not be later than {latest // 60:02d}:{latest % 60:02d}")
    return total


def parse_rule(raw: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise PolicyError(f"rule {index} must be a table")
    name = raw.get("name", f"rule-{index}")
    label = f"rule {name!r}"
    if not isinstance(name, str) or not name:
        raise PolicyError(f"rule {index} name must be a non-empty string")
    if unknown := sorted(set(raw) - RULE_KEYS):
        raise PolicyError(f"{label} has unknown keys: {', '.join(unknown)}")
    if raw.get("enforcement") not in ENFORCEMENTS:
        raise PolicyError(f"{label} enforcement must be one of: {', '.join(ENFORCEMENTS)}")
    if not (RULE_KEYS - {"name", "enforcement"}) & set(raw):
        raise PolicyError(f"{label} restricts nothing; set days, start, end or end_by_day")
    days = raw.get("days", list(WEEKDAYS))
    if (not isinstance(days, list) or not days or len(set(days)) != len(days)
            or any(day not in WEEKDAYS for day in days)):
        raise PolicyError(f"{label} days must be a non-empty list of distinct {'/'.join(WEEKDAYS)}")
    start = minutes(raw.get("start", "00:00"), f"{label} start", DAY_MINUTES - 1)
    end = minutes(raw.get("end", "24:00"), f"{label} end", DAY_MINUTES)
    cutoffs = raw.get("end_by_day", {})
    if not isinstance(cutoffs, dict):
        raise PolicyError(f"{label} end_by_day must be a table of weekday = HH:MM")
    ends = {}
    for day in WEEKDAYS:
        ends[day] = end
        if day in cutoffs:
            ends[day] = minutes(cutoffs[day], f"{label} end_by_day.{day}", DAY_MINUTES)
    for day in cutoffs:
        if day not in days:
            raise PolicyError(f"{label} end_by_day.{day} is not one of its allowed days")
    if any(ends[day] <= start for day in days):
        raise PolicyError(f"{label} start must be earlier than every end")
    return {"name": name, "enforcement": raw["enforcement"], "days": set(days),
            "start": start, "ends": ends, "cutoff_days": set(cutoffs)}


def load_policy(path: Path) -> tuple[ZoneInfo, list[dict[str, Any]]]:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise PolicyError(f"cannot read {path}: {error.strerror}") from error
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise PolicyError(f"{path}: {error}") from error
    if unknown := sorted(set(raw) - {"timezone", "rule"}):
        raise PolicyError(f"unknown top-level keys: {', '.join(unknown)}")
    name = raw.get("timezone")
    if not isinstance(name, str) or not name:
        raise PolicyError("timezone must be an IANA name such as Europe/London")
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise PolicyError(f"unknown timezone {name!r}") from error
    rules = raw.get("rule")
    if not isinstance(rules, list) or not rules:
        raise PolicyError("at least one [[rule]] is required")
    parsed = [parse_rule(rule, index) for index, rule in enumerate(rules, 1)]
    if len({rule["name"] for rule in parsed}) != len(parsed):
        raise PolicyError("rule names must be unique")
    return zone, parsed


def clock(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def violation(rule: dict[str, Any], day: str, now: int) -> str | None:
    if day not in rule["days"]:
        return f"{day.title()} is not an allowed merge day"
    if now < rule["start"]:
        return f"before {clock(rule['start'])}"
    end = rule["ends"][day]
    if now >= end:
        suffix = f" for {day.title()}" if day in rule["cutoff_days"] else ""
        return f"at or after the {clock(end)} cutoff{suffix}"
    return None


def wall(day: date, offset: int, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time(), zone) + timedelta(minutes=offset)


def next_allowed(local: datetime, zone: ZoneInfo, rules: list[dict[str, Any]]) -> str | None:
    now = local.astimezone(timezone.utc)
    for offset in range(SEARCH_DAYS):
        day = local.date() + timedelta(days=offset)
        weekday = WEEKDAYS[day.weekday()]
        if any(weekday not in rule["days"] for rule in rules):
            continue
        opens = wall(day, max(rule["start"] for rule in rules), zone).astimezone(timezone.utc)
        closes = wall(day, min(rule["ends"][weekday] for rule in rules), zone).astimezone(timezone.utc)
        opens = max(opens, now)
        if opens < closes:
            return opens.astimezone(zone).isoformat(timespec="minutes")
    return None


def evaluate(path: Path, instant: datetime) -> dict[str, Any]:
    zone, rules = load_policy(path)
    local = instant.astimezone(zone)
    weekday = WEEKDAYS[local.weekday()]
    elapsed = local.hour * 60 + local.minute
    violations = [{"rule": rule["name"], "enforcement": rule["enforcement"], "reason": reason}
                  for rule in rules if (reason := violation(rule, weekday, elapsed))]
    levels = {item["enforcement"] for item in violations}
    status = "required" if "required" in levels else "advisory" if levels else "clear"
    return {
        "status": status,
        "policy": str(path),
        "timezone": zone.key,
        "local_time": local.isoformat(timespec="minutes"),
        "weekday": weekday,
        "violations": violations,
        "next_allowed": next_allowed(local, zone, rules) if violations else None,
    }


def instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--now needs an explicit UTC offset")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repository checkout (default: cwd)")
    parser.add_argument("--now", type=instant, help="fixed instant for tests; omit in real use")
    args = parser.parse_args()
    result: dict[str, Any]
    try:
        top, common_dir = repository_identity(args.repo)
        ignored = [str(top / POLICY_NAME)] if exists(top / POLICY_NAME) else []
        path = find_policy(top, common_dir)
        result = evaluate(path, args.now or datetime.now(timezone.utc)) if path else {"status": "none"}
        if ignored:
            result["ignored"] = ignored
        code = 0
    except PolicyError as error:
        result, code = {"status": "unknown", "error": str(error)}, 3
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
