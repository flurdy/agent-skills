#!/usr/bin/env python3
"""Helper for the plan-day skill: config loading, collector contract, merge, plan files.

Subcommands print JSON to stdout and fail closed with a non-zero exit and a message on
stderr. The judgement step in SKILL.md consumes the output; nothing here ranks or plans.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

CONTRACT_FIELDS = {
    "source": str,
    "id": str,
    "title": str,
    "priority": int,
    "due": (str, type(None)),
    "status": str,
    "url": str,
    "repository": str,
    "delegable": bool,
}
SOURCES = ("jira", "trello", "beads", "thoughtbox", "calendar", "dependabot", "grafana")
BLOCK_HOURS = ("work", "project-session", "evening")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
PLAN_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
ARTIFACT_DIR = Path(".artifacts") / "plan-day"


class PlanDayError(Exception):
    """A fail-closed error reported on stderr."""


@dataclass(frozen=True)
class Workspace:
    root: Path
    config: dict[str, Any]

    @property
    def plans_dir(self) -> Path:
        return self.root / self.config["plans"]["directory"]

    @property
    def artifacts_dir(self) -> Path:
        return self.root / ARTIFACT_DIR


def find_root(start: Path | None) -> Path:
    candidate = (start or Path.cwd()).resolve()
    for directory in (candidate, *candidate.parents):
        if (directory / "workspace.json").is_file() and (directory / "pa.toml").is_file():
            return directory
    raise PlanDayError(f"no workspace with workspace.json and pa.toml at or above {candidate}")


def _require(mapping: dict[str, Any], key: str, kind: type, where: str) -> Any:
    value = mapping.get(key)
    if not isinstance(value, kind) or isinstance(value, bool) and kind is int:
        raise PlanDayError(f"pa.toml: {where}.{key} must be {kind.__name__}")
    return value


def _validate_hours(value: str, where: str) -> None:
    if not re.fullmatch(r"\d{2}:\d{2}-\d{2}:\d{2}", value):
        raise PlanDayError(f"pa.toml: {where} must look like HH:MM-HH:MM")


def _validate_members(root: Path, entries: Any, where: str) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        raise PlanDayError(f"pa.toml: {where} must be an array of tables")
    for entry in entries:
        name = _require(entry, "name", str, where)
        workspace = _require(entry, "workspace", str, f"{where}.{name}")
        if not (root / workspace).is_dir():
            raise PlanDayError(f"pa.toml: {where}.{name}.workspace {workspace} is not a directory")
        hours = _require(entry, "hours", str, f"{where}.{name}")
        if hours not in BLOCK_HOURS:
            raise PlanDayError(f"pa.toml: {where}.{name}.hours must be one of {BLOCK_HOURS}")
    return entries


def load_config(root: Path) -> dict[str, Any]:
    try:
        config = tomllib.loads((root / "pa.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise PlanDayError(f"pa.toml: {error}") from error

    schedule = _require(config, "schedule", dict, "root")
    _require(schedule, "timezone", str, "schedule")
    _validate_hours(_require(schedule, "work_hours", str, "schedule"), "schedule.work_hours")
    for day in _require(schedule, "work_days", list, "schedule"):
        if day not in WEEKDAYS:
            raise PlanDayError(f"pa.toml: schedule.work_days has unknown day {day!r}")
    blocks = _require(schedule, "blocks", list, "schedule")
    for hours in BLOCK_HOURS:
        if hours not in blocks:
            raise PlanDayError(f"pa.toml: schedule.blocks must include {hours!r}")

    plans = _require(config, "plans", dict, "root")
    _require(plans, "directory", str, "plans")
    if _require(plans, "retention_days", int, "plans") < 1:
        raise PlanDayError("pa.toml: plans.retention_days must be at least 1")

    priority = _require(config, "priority", dict, "root")
    for table in ("jira", "trello_labels"):
        for label, level in _require(priority, table, dict, "priority").items():
            if not isinstance(level, int) or not 0 <= level <= 4:
                raise PlanDayError(f"pa.toml: priority.{table}.{label} must be 0-4")

    sources = _require(config, "sources", dict, "root")
    for name, enabled in sources.items():
        if name not in SOURCES or not isinstance(enabled, bool):
            raise PlanDayError(f"pa.toml: sources.{name} must be a known source set true or false")

    config["clients"] = _validate_members(root, config.get("clients", []), "clients")
    config["projects"] = _validate_members(root, config.get("projects", []), "projects")
    return config


def load_workspace(start: Path | None) -> Workspace:
    root = find_root(start)
    return Workspace(root, load_config(root))


def validate_item(item: Any, where: str) -> list[str]:
    if not isinstance(item, dict):
        return [f"{where}: item must be an object"]
    errors = [f"{where}: missing field {field!r}" for field in CONTRACT_FIELDS if field not in item]
    errors.extend(f"{where}: unknown field {field!r}" for field in item if field not in CONTRACT_FIELDS)
    for field, kind in CONTRACT_FIELDS.items():
        if field not in item:
            continue
        value = item[field]
        if isinstance(value, bool) and kind is int or not isinstance(value, kind):
            errors.append(f"{where}: field {field!r} has wrong type")
    if not errors:
        if item["source"] not in SOURCES:
            errors.append(f"{where}: unknown source {item['source']!r}")
        if not 0 <= item["priority"] <= 4:
            errors.append(f"{where}: priority must be 0-4")
        if item["due"] is not None:
            try:
                date.fromisoformat(item["due"])
            except ValueError:
                errors.append(f"{where}: due must be YYYY-MM-DD or null")
        for field in ("id", "title"):
            if not item[field].strip():
                errors.append(f"{where}: field {field!r} must not be blank")
    return errors


def load_items(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PlanDayError(f"{path}: {error}") from error
    if not isinstance(payload, list):
        raise PlanDayError(f"{path}: collector output must be a JSON array")
    errors = [
        error
        for index, item in enumerate(payload)
        for error in validate_item(item, f"{path}[{index}]")
    ]
    if errors:
        raise PlanDayError("\n".join(errors))
    return payload


def hours_for(workspace: Workspace, repository: str) -> str | None:
    for kind in ("clients", "projects"):
        for member in workspace.config[kind]:
            if repository == Path(member["workspace"]).name or repository.startswith(
                member["workspace"] + "/"
            ):
                return member["hours"]
    return None


def merge(workspace: Workspace) -> dict[str, Any]:
    enabled = [name for name, on in workspace.config["sources"].items() if on]
    items: list[dict[str, Any]] = []
    present: set[str] = set()
    for path in sorted(workspace.artifacts_dir.glob("*.json")):
        for item in load_items(path):
            present.add(item["source"])
            item = dict(item)
            item["hours"] = hours_for(workspace, item["repository"])
            items.append(item)
    items.sort(key=lambda item: (item["priority"], item["due"] or "9999-99-99", item["source"]))
    return {
        "items": items,
        "missing_sources": sorted(set(enabled) - present),
        "disabled_sources": sorted(set(SOURCES) - set(enabled)),
    }


def plan_files(workspace: Workspace, today: date) -> dict[str, Any]:
    retention = timedelta(days=workspace.config["plans"]["retention_days"])
    plans: list[tuple[date, Path]] = []
    if workspace.plans_dir.is_dir():
        for path in workspace.plans_dir.iterdir():
            match = PLAN_FILE.match(path.name)
            if match and path.is_file():
                plans.append((date.fromisoformat(match.group(1)), path))
    plans.sort()
    previous = [path for day, path in plans if day < today]
    stale = [path for day, path in plans if today - day > retention]
    return {
        "today": str(workspace.plans_dir / f"{today.isoformat()}.md"),
        "previous": str(previous[-1]) if previous else None,
        "stale": [str(path) for path in stale],
    }


def prune(stale: list[str]) -> None:
    for path in stale:
        Path(path).unlink()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="plan_day.py", description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", type=Path, help="workspace root (default: search upward)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("config", help="print the validated pa.toml as JSON")
    validate = commands.add_parser("validate", help="check collector JSON against the contract")
    validate.add_argument("files", nargs="+", type=Path)
    commands.add_parser("merge", help="merge validated collector output from .artifacts/plan-day")
    plans = commands.add_parser("plans", help="locate today's, the previous, and stale plan files")
    plans.add_argument("--today", type=date.fromisoformat, default=None)
    plans.add_argument("--prune", action="store_true", help="delete stale plan files")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        if args.command == "validate":
            for path in args.files:
                load_items(path)
            print(json.dumps({"valid": [str(path) for path in args.files]}))
            return 0
        workspace = load_workspace(args.workspace)
        if args.command == "config":
            output: dict[str, Any] = {"root": str(workspace.root), **workspace.config}
        elif args.command == "merge":
            output = merge(workspace)
        else:
            today = args.today or datetime.now().astimezone().date()
            output = plan_files(workspace, today)
            if args.prune:
                prune(output["stale"])
                output["pruned"] = output.pop("stale")
    except PlanDayError as error:
        print(f"plan-day: {error}", file=sys.stderr)
        return 1
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
