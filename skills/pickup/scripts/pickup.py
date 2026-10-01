#!/usr/bin/env python3
"""Helper for the pickup skill: load pickup.toml and build the Jira search requests.

Prints JSON to stdout; fails closed with a non-zero exit and a message on stderr.
Ranking and rendering stay in SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

CONFIG_NAME = "pickup.toml"
SIZES = ("any", "small", "meaty")
DEFAULT_FIELDS = {
    "sprint": "customfield_10020",
    "flagged": "customfield_10021",
    "story_points": "customfield_10016",
}
BASE_FIELDS = (
    "summary",
    "status",
    "priority",
    "issuetype",
    "labels",
    "issuelinks",
    "description",
    "parent",
)
BUCKETS = (
    ("active", "sprint in openSprints()", "active_limit"),
    ("next", "sprint in futureSprints() AND sprint not in openSprints()", "next_limit"),
    ("backlog", "sprint is EMPTY", "backlog_limit"),
)
DEFAULT_LIMITS = {"active_limit": 50, "next_limit": 10, "backlog_limit": 10}
FIELD_ID = re.compile(r"^customfield_\d+$")
PROJECTION = (
    "issues[*].{{key: key, url: self, summary: fields.summary, type: fields.issuetype.name, "
    "priority: fields.priority.name, labels: fields.labels, has_description: fields.description != null, "
    "parent_key: fields.parent.key, parent: fields.parent.fields.summary, parent_type: fields.parent.fields.issuetype.name, "
    "points: fields.{story_points}, flags: fields.{flagged}[*].value, "
    "sprints: fields.{sprint}[*].{{id: id, name: name, state: state, start: startDate}}, "
    "blocked_by: fields.issuelinks[?type.inward=='is blocked by' && inwardIssue]"
    ".{{key: inwardIssue.key, category: inwardIssue.fields.status.statusCategory.key}}}}"
)


class ConfigError(Exception):
    pass


def find_config(start: Path) -> Path:
    for directory in (start, *start.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    raise ConfigError(f"no {CONFIG_NAME} found in {start} or any parent directory")


def string_list(table: dict[str, Any], key: str, required: bool = False) -> list[str]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ConfigError(f"jira.{key} must be a list of non-empty strings")
    if required and not value:
        raise ConfigError(f"jira.{key} is required")
    return value


def load_config(path: Path) -> dict[str, Any]:
    try:
        raw = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: {error}") from error
    jira = raw.get("jira")
    if not isinstance(jira, dict):
        raise ConfigError(f"{path}: missing [jira] table")
    fields = {**DEFAULT_FIELDS, **jira.get("fields", {})}
    for name, field_id in fields.items():
        if not isinstance(field_id, str) or not FIELD_ID.match(field_id):
            raise ConfigError(f"jira.fields.{name} must look like customfield_NNNNN")
    limits = {}
    for key, default in DEFAULT_LIMITS.items():
        value = jira.get(key, default)
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 100:
            raise ConfigError(f"jira.{key} must be an integer 1-100")
        limits[key] = value
    return {
        "path": str(path),
        "projects": string_list(jira, "projects", required=True),
        "ready_statuses": string_list(jira, "ready_statuses", required=True),
        "labels": string_list(jira, "labels"),
        "exclude_types": string_list(jira, "exclude_types") or ["Epic"],
        "holding_sprints": string_list(jira, "holding_sprints"),
        "fields": fields,
        **limits,
    }


def quoted(values: list[str]) -> str:
    return ", ".join(
        '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"' for value in values
    )


def build_requests(config: dict[str, Any], labels: list[str] | None) -> list[dict[str, Any]]:
    effective_labels = config["labels"] if labels is None else labels
    clauses = [
        f"project in ({quoted(config['projects'])})",
        f"status in ({quoted(config['ready_statuses'])})",
        "assignee is EMPTY",
        f"issuetype not in ({quoted(config['exclude_types'])})",
    ]
    if effective_labels:
        clauses.append(f"labels in ({quoted(effective_labels)})")
    fields = ",".join((*BASE_FIELDS, *config["fields"].values()))
    return [
        {
            "bucket": bucket,
            "path": "/rest/api/3/search/jql",
            "queryParams": {
                "jql": " AND ".join((*clauses, scope)) + " ORDER BY Rank ASC",
                "fields": fields,
                "maxResults": str(config[limit_key]),
            },
            "jq": PROJECTION.format(**config["fields"]),
        }
        for bucket, scope, limit_key in BUCKETS
    ]


def build_mine_request(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": "/rest/api/3/search/jql",
        "queryParams": {
            "jql": f"project in ({quoted(config['projects'])}) AND assignee = currentUser() "
            "AND statusCategory != Done",
            "fields": "parent",
            "maxResults": "50",
        },
        "jq": "issues[*].{key: key, parent_key: fields.parent.key}",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace", type=Path, help=f"directory to search upward for {CONFIG_NAME}"
    )
    parser.add_argument(
        "--labels", help="comma-separated labels overriding jira.labels; empty for all"
    )
    parser.add_argument("--size", choices=SIZES, default="any")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        config = load_config(find_config((args.workspace or Path.cwd()).resolve()))
    except (ConfigError, OSError) as error:
        print(f"pickup: {error}", file=sys.stderr)
        return 1
    labels = (
        None
        if args.labels is None
        else [part.strip() for part in args.labels.split(",") if part.strip()]
    )
    output = {
        "config": config,
        "size": args.size,
        "labels": config["labels"] if labels is None else labels,
        "requests": build_requests(config, labels),
        "mine": build_mine_request(config),
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
