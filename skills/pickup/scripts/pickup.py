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
FUTURE_SCOPE = "sprint in futureSprints() AND sprint not in openSprints()"
FOLLOW_ON_SCOPE = "(sprint in openSprints() OR sprint in futureSprints() OR sprint is EMPTY)"
DEFAULT_LIMITS = {"active_limit": 50, "next_limit": 10, "backlog_limit": 10}
MINE_LIMIT = 50
FOLLOW_ON_LIMIT = 50
MAX_FOLLOW_ON_KEYS = 100
FIELD_ID = re.compile(r"^customfield_\d+$")
ISSUE_KEY = re.compile(r"^[A-Z][A-Z0-9_]*-[1-9]\d*$")
PROJECTION = (
    "issues[*].{{key: key, url: self, summary: fields.summary, type: fields.issuetype.name, "
    "priority: fields.priority.name, labels: fields.labels, has_description: fields.description != null, "
    "parent_key: fields.parent.key, parent: fields.parent.fields.summary, parent_type: fields.parent.fields.issuetype.name, "
    "points: fields.{story_points}, flags: fields.{flagged}[*].value, "
    "sprints: fields.{sprint}[*].{{id: id, name: name, state: state, start: startDate}}, "
    "blocked_by: fields.issuelinks[?type.inward=='is blocked by' && inwardIssue]"
    ".{{key: inwardIssue.key, category: inwardIssue.fields.status.statusCategory.key}}}}"
)

MINE_PROJECTION = (
    "issues[*].{{key: key, url: self, summary: fields.summary, status: fields.status.name, "
    "status_category: fields.status.statusCategory.key, "
    "type: fields.issuetype.name, priority: fields.priority.name, parent_key: fields.parent.key, "
    "points: fields.{story_points}, sprints: fields.{sprint}[*].{{id: id, name: name, state: state, start: startDate}}}}"
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


def search(jql: str, fields: str, max_results: int, issues_projection: str) -> dict[str, Any]:
    """One enhanced-search request whose projection keeps the paging state."""
    return {
        "path": "/rest/api/3/search/jql",
        "queryParams": {
            "jql": jql + " ORDER BY Rank ASC",
            "fields": fields,
            "maxResults": str(max_results),
        },
        "jq": f"{{isLast: isLast, nextPageToken: nextPageToken, issues: {issues_projection}}}",
    }


def ready_clauses(config: dict[str, Any], labels: list[str] | None) -> list[str]:
    effective_labels = config["labels"] if labels is None else labels
    clauses = [
        f"project in ({quoted(config['projects'])})",
        f"status in ({quoted(config['ready_statuses'])})",
        "assignee is EMPTY",
        f"issuetype not in ({quoted(config['exclude_types'])})",
    ]
    if effective_labels:
        clauses.append(f"labels in ({quoted(effective_labels)})")
    return clauses


def ready_search(config: dict[str, Any], labels: list[str] | None, scope: str, limit: int) -> dict[str, Any]:
    return search(
        " AND ".join((*ready_clauses(config, labels), scope)),
        ",".join((*BASE_FIELDS, *config["fields"].values())),
        limit,
        PROJECTION.format(**config["fields"]),
    )


def build_requests(config: dict[str, Any], labels: list[str] | None) -> list[dict[str, Any]]:
    holding = config["holding_sprints"]
    next_scope = FUTURE_SCOPE + (f" AND sprint not in ({quoted(holding)})" if holding else "")
    buckets = [
        {"bucket": "active", **ready_search(config, labels, "sprint in openSprints()", config["active_limit"])},
        {"bucket": "next", **ready_search(config, labels, next_scope, config["next_limit"])},
    ]
    buckets += [
        {
            "bucket": "holding",
            "sprint": sprint,
            **ready_search(
                config, labels, f"sprint in ({quoted([sprint])}) AND sprint not in openSprints()", config["next_limit"]
            ),
        }
        for sprint in holding
    ]
    buckets.append({"bucket": "backlog", **ready_search(config, labels, "sprint is EMPTY", config["backlog_limit"])})
    return buckets


def build_mine_request(config: dict[str, Any]) -> dict[str, Any]:
    fields = config["fields"]
    return search(
        f"project in ({quoted(config['projects'])}) AND assignee = currentUser() AND statusCategory != Done",
        ",".join(
            ("summary", "status", "priority", "issuetype", "parent", fields["sprint"], fields["story_points"])
        ),
        MINE_LIMIT,
        MINE_PROJECTION.format(**fields),
    )


def issue_keys(option: str, value: str | None) -> list[str]:
    keys = list(dict.fromkeys(part.strip() for part in (value or "").split(",") if part.strip()))
    invalid = [key for key in keys if not ISSUE_KEY.match(key)]
    if invalid:
        raise ConfigError(f"{option}: invalid issue key {invalid[0]!r}")
    if len(keys) > MAX_FOLLOW_ON_KEYS:
        raise ConfigError(f"{option}: at most {MAX_FOLLOW_ON_KEYS} keys")
    return keys


def build_follow_on_request(
    config: dict[str, Any], labels: list[str] | None, parents: list[str], linked: list[str]
) -> dict[str, Any] | None:
    """Ready tickets in the epics or parents of your work, or linked to your tickets."""
    matches = [f"parent in ({quoted(parents)})"] if parents else []
    matches += [f"issue in linkedIssues({quoted([key])})" for key in linked]
    if not matches:
        return None
    return ready_search(config, labels, f"{FOLLOW_ON_SCOPE} AND ({' OR '.join(matches)})", FOLLOW_ON_LIMIT)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace", type=Path, help=f"directory to search upward for {CONFIG_NAME}"
    )
    parser.add_argument(
        "--labels", help="comma-separated labels overriding jira.labels; empty for all"
    )
    parser.add_argument("--size", choices=SIZES, default="any")
    parser.add_argument(
        "--parents", help="comma-separated parent/epic keys of your open work, for follow-ons"
    )
    parser.add_argument(
        "--linked", help="comma-separated keys of your open tickets, for linked follow-ons"
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        config = load_config(find_config((args.workspace or Path.cwd()).resolve()))
        parents = issue_keys("--parents", args.parents)
        linked = issue_keys("--linked", args.linked)
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
        "follow_on": build_follow_on_request(config, labels, parents, linked),
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
