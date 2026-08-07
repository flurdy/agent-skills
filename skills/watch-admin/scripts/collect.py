#!/usr/bin/env python3
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Callable, Iterable


SOURCE_SCOPES = {"git": "workspace", "beads": "workspace"}
RECORD_CAPS = {"git": 1000, "beads": 200}
ENVELOPE_BYTES = 64 * 1024
COMMAND_OUTPUT_BYTES = 1024 * 1024
STRING_BYTES = 256
DIAGNOSTIC_BYTES = 240
COMMAND_TIMEOUT_SECONDS = 20
MAX_REPOSITORIES = 10
SESSION_BYTES = 4 * 1024 * 1024
REQUIRED_REASONING = "medium"
APPROVED_UAT_PATH = Path("/home/ivar/Code/blc/workspace")
APPROVED_UAT_WORKSPACE = "blc-2"
APPROVED_UAT_REPOSITORIES = {
    "auth0": ("repos/auth0", "service"),
    "blc-2": ("repos/blc-2", "primary"),
    "blc-au": ("repos/blc-au", "service"),
    "blc-old": ("repos/blc-old", "service"),
    "dds-old": ("repos/dds-old", "service"),
    "docs": ("repos/docs", "service"),
    "members-service": ("repos/members-service", "service"),
    "reverse-proxy": ("repos/reverse-proxy", "service"),
}
THINKING_LEVELS = {"off", "minimal", "low", "medium", "high", "xhigh", "max"}


class CollectorError(RuntimeError):
    pass


@dataclass(frozen=True)
class Repository:
    name: str
    path: Path


@dataclass(frozen=True)
class CollectedRecords:
    records: list[dict[str, Any]]
    total: int


Runner = Callable[..., str]


def _bounded(value: str, limit: int = DIAGNOSTIC_BYTES) -> str:
    clean = " ".join(value.split())
    encoded = clean.encode("utf-8")
    return encoded[:limit].decode("utf-8", errors="ignore")


def _validate_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise CollectorError(f"{field} must be a non-empty string")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise CollectorError(f"{field} contains control characters")
    if len(value.encode("utf-8")) > STRING_BYTES:
        raise CollectorError(f"{field} exceeds {STRING_BYTES} UTF-8 bytes")
    return value


def _validate_record_strings(value: Any, field: str = "record") -> None:
    if isinstance(value, str):
        _validate_string(value, field)
    elif isinstance(value, list):
        for item in value:
            _validate_record_strings(item, field)
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_string(key, "record field")
            _validate_record_strings(item, key)
    elif value is not None and not isinstance(value, (bool, int)):
        raise CollectorError(f"{field} has unsupported value type")


def _timestamp(value: str | None = None) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    else:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as error:
            raise CollectorError("observed-at must be timezone-qualified ISO-8601") from error
        if parsed.tzinfo is None:
            raise CollectorError("observed-at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _router_config(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CollectorError(f"{label} model-tier configuration is unavailable") from error
    if not isinstance(payload, dict):
        raise CollectorError(f"{label} model-tier configuration must be an object")
    return payload


def _configured_candidates(tier: Any) -> set[str]:
    if not isinstance(tier, dict):
        raise CollectorError("standard model-tier configuration is unavailable")
    rank = tier.get("rank")
    if isinstance(rank, bool) or not isinstance(rank, (int, float)):
        raise CollectorError("standard model tier has an invalid rank")
    if tier.get("thinking") not in THINKING_LEVELS:
        raise CollectorError("standard model tier has an invalid thinking level")
    selection = tier.get("selection", "first-available")
    if selection not in {"first-available", "weighted-random"}:
        raise CollectorError("standard model tier has an invalid selection policy")
    configured = tier.get("candidates")
    if not isinstance(configured, list):
        raise CollectorError("standard model-tier configuration is unavailable")
    candidates = set()
    for candidate in configured:
        if not isinstance(candidate, dict):
            raise CollectorError("standard model tier has an invalid candidate")
        model = candidate.get("model")
        if not isinstance(model, str) or model.startswith("/") or model.endswith("/") or "/" not in model:
            raise CollectorError("standard model tier has an invalid candidate model")
        if "enabled" in candidate and not isinstance(candidate["enabled"], bool):
            raise CollectorError("standard model tier has an invalid candidate state")
        if "metered" in candidate and not isinstance(candidate["metered"], bool):
            raise CollectorError("standard model tier has an invalid candidate metering policy")
        if selection == "weighted-random":
            weight = candidate.get("weight")
            if isinstance(weight, bool) or not isinstance(weight, int) or not 1 <= weight <= 100:
                raise CollectorError("standard model tier has an invalid candidate weight")
        if candidate.get("enabled") is not False:
            candidates.add(model)
    if not candidates:
        raise CollectorError("standard model tier has no enabled candidates")
    return candidates


def _standard_models(agent_dir: Path, workspace: Path) -> set[str]:
    global_config = _router_config(agent_dir / "model-tier-router.json", "global")
    enabled = global_config.get("enabled")
    tier = (global_config.get("tiers") or {}).get("standard")
    project_path = workspace / ".pi" / "model-tier-router.json"
    if project_path.is_file():
        raise CollectorError("project model-tier overrides are unsupported for the BLC UAT")
    if enabled is not True:
        raise CollectorError("model-tier routing must be enabled")
    return _configured_candidates(tier)


def _validate_uat_workspace(workspace: Path) -> None:
    try:
        payload = json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CollectorError("approved BLC UAT workspace identity is unavailable") from error
    if not isinstance(payload, dict):
        raise CollectorError("approved BLC UAT workspace identity is unavailable")
    repositories = payload.get("repositories")
    topology = {
        entry.get("name"): (entry.get("path"), entry.get("role"))
        for entry in repositories or []
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    if payload.get("name") != APPROVED_UAT_WORKSPACE or topology != APPROVED_UAT_REPOSITORIES:
        raise CollectorError("watch-admin is authorized only for the approved BLC UAT workspace")


def validate_route_stability(
    session_file: Path | None,
    session_id: str | None,
    provider: str | None,
    model: str | None,
    reasoning: str | None,
    agent_dir: Path | None,
    workspace: Path,
    uat_authorized: bool,
    uat_workspace: Path | None,
    approved_uat_path: Path = APPROVED_UAT_PATH,
    launch_path: Path | None = None,
) -> None:
    if not uat_authorized or uat_workspace is None or uat_workspace.absolute() != workspace.absolute():
        raise CollectorError("watch-admin UAT authorization is unavailable")
    if workspace.absolute() != approved_uat_path.absolute() or (launch_path or workspace).absolute() != approved_uat_path.absolute():
        raise CollectorError("watch-admin is authorized only at the approved BLC UAT path")
    _validate_uat_workspace(workspace)
    if session_file is None or not session_id or not provider or not model or not reasoning or agent_dir is None:
        raise CollectorError("Pi route telemetry is unavailable")
    try:
        if session_file.stat().st_size > SESSION_BYTES:
            raise CollectorError("Pi session exceeds the route preflight byte limit")
        lines = session_file.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise CollectorError("Pi route telemetry is unavailable") from error
    try:
        entries = [json.loads(line) for line in lines if line]
    except json.JSONDecodeError as error:
        raise CollectorError("Pi route telemetry is malformed") from error
    if not entries or entries[0].get("type") != "session" or entries[0].get("id") != session_id:
        raise CollectorError("Pi session identity does not match route telemetry")
    roles = [
        entry.get("message", {}).get("role")
        for entry in entries
        if isinstance(entry, dict) and entry.get("type") == "message" and isinstance(entry.get("message"), dict)
    ]
    if roles != ["user", "assistant"]:
        raise CollectorError("watch-admin requires a fresh dedicated Pi session")
    models = [
        (entry.get("provider"), entry.get("modelId"))
        for entry in entries
        if isinstance(entry, dict) and entry.get("type") == "model_change"
    ]
    thinking_levels = [
        entry.get("thinkingLevel")
        for entry in entries
        if isinstance(entry, dict) and entry.get("type") == "thinking_level_change"
    ]
    if not models or not thinking_levels:
        raise CollectorError("Pi route telemetry is incomplete")
    if any(candidate != (provider, model) for candidate in models) or any(
        candidate != reasoning for candidate in thinking_levels
    ):
        raise CollectorError("Pi route changed; start a fresh dedicated session on the standard route")
    if f"{provider}/{model}" not in _standard_models(agent_dir, workspace) or reasoning != REQUIRED_REASONING:
        raise CollectorError("Pi route is not the configured watch-admin standard route")


def resolve_deadline(value: str, now: datetime | None = None) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise CollectorError("until must use HH:MM")
    current = now or datetime.now().astimezone()
    hour, minute = (int(part) for part in value.split(":"))
    deadline = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if deadline <= current:
        raise CollectorError("until deadline must be in the future today")
    return deadline.isoformat(timespec="seconds")


def load_workspace(root: Path) -> list[Repository]:
    root = root.absolute()
    manifest = root / "workspace.json"
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CollectorError(f"workspace manifest not found: {manifest}") from error
    except json.JSONDecodeError as error:
        raise CollectorError("workspace manifest is malformed JSON") from error
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise CollectorError("workspace manifest must use version 1")
    configured = payload.get("repositories")
    if not isinstance(configured, list):
        raise CollectorError("workspace repositories must be an array")
    if len(configured) > MAX_REPOSITORIES:
        raise CollectorError(f"workspace supports at most {MAX_REPOSITORIES} registered repositories")
    repositories = [Repository("workspace", root)]
    names = {"workspace"}
    for entry in configured:
        if not isinstance(entry, dict) or set(entry) - {"name", "path", "role"}:
            raise CollectorError("workspace repository entry is malformed")
        name = _validate_string(entry.get("name"), "repository name")
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise CollectorError(f"repository {name} path must be a safe relative path")
        path = root / relative
        if name in names:
            raise CollectorError(f"duplicate repository name: {name}")
        if not path.is_dir():
            raise CollectorError(f"registered repository path is unavailable: {relative}")
        names.add(name)
        repositories.append(Repository(name, path))
    return repositories


def check_dependencies(sources: Iterable[str]) -> None:
    required = set()
    for source in sources:
        if source == "git":
            required.update(("git", "project-workspace"))
        elif source == "beads":
            required.add("bd")
        else:
            raise CollectorError(f"unsupported source: {source}")
    for command in sorted(required):
        if shutil.which(command) is None:
            raise CollectorError(f"missing required command: {command}")


def run_command(args: list[str], *, cwd: Path | None = None, timeout: int = COMMAND_TIMEOUT_SECONDS) -> str:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise CollectorError(f"{Path(args[0]).name} timed out") from error
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if len(stdout.encode("utf-8")) > COMMAND_OUTPUT_BYTES or len(stderr.encode("utf-8")) > COMMAND_OUTPUT_BYTES:
        raise CollectorError(f"{Path(args[0]).name} output exceeded {COMMAND_OUTPUT_BYTES} bytes")
    if completed.returncode != 0:
        raise CollectorError(f"{Path(args[0]).name} failed with exit {completed.returncode}")
    return stdout


def _parse_refs(output: str) -> dict[str, str]:
    refs = {}
    for line in output.splitlines():
        if not line:
            continue
        parts = line.split("\0")
        if len(parts) != 2 or not all(parts):
            raise CollectorError("malformed git ref output")
        refs[parts[0]] = parts[1]
    return refs


def _parse_worktree_heads(output: str) -> dict[str, str]:
    heads = {}
    path = None
    head = None
    for line in [*output.splitlines(), ""]:
        if not line:
            if path and head:
                heads[path] = head
            path = head = None
        elif line.startswith("worktree "):
            path = line.removeprefix("worktree ")
        elif line.startswith("HEAD "):
            head = line.removeprefix("HEAD ")
    return heads


def parse_git_inventory(
    text: str,
    refs: dict[str, dict[str, str]],
    worktree_heads: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    records = []
    for line in text.splitlines():
        if not line or line == "=== GIT INVENTORY ===":
            continue
        parts = line.split(" | ")
        if len(parts) < 8 or " (" not in parts[0] or not parts[0].endswith(")"):
            raise CollectorError("malformed git inventory row")
        name = parts[0].split(" (", 1)[0]
        values = {}
        for part in parts[1:]:
            if " " not in part:
                raise CollectorError("malformed git inventory field")
            key, value = part.split(" ", 1)
            values[key] = value
        required = {"branch", "worktree", "checkout", "upstream", "ahead", "behind", "dirty"}
        if not required <= set(values) or name not in refs:
            raise CollectorError("malformed git inventory row")
        branch = values["branch"]
        worktree = values["worktree"]
        present = worktree != "—" and values["checkout"] != "—"
        entity_type = "worktree" if present else "branch"
        identity = f"{name}:{entity_type}:{worktree if present else branch}"
        record: dict[str, Any] = {
            "id": identity,
            "entityType": entity_type,
            "branch": branch,
            "present": present,
            "upstream": values["upstream"] != "—",
            "detached": branch in {"HEAD", "(detached)"},
        }
        head = (worktree_heads or {}).get(name, {}).get(worktree) if present else None
        head = head or refs[name].get(branch)
        if head:
            record["head"] = head
        if present:
            record["worktree"] = worktree
        for field in ("ahead", "behind"):
            if values[field].isdigit():
                record[field] = int(values[field])
        if values["dirty"].isdigit():
            record["dirty"] = int(values["dirty"]) > 0
        records.append(record)
    if text.strip() and not records:
        raise CollectorError("malformed git inventory: no records")
    return sorted(records, key=lambda record: record["id"])


def collect_git(root: Path, repositories: list[Repository], runner: Runner = run_command) -> list[dict[str, Any]]:
    inventory = runner(["project-workspace", "git-inventory", "--workspace", str(root)], cwd=root)
    refs = {}
    worktree_heads = {}
    for repository in repositories:
        output = runner(
            [
                "git",
                "-C",
                str(repository.path),
                "for-each-ref",
                "--format=%(refname:short)%00%(objectname)",
                "refs/heads/",
            ],
            cwd=root,
        )
        refs[repository.name] = _parse_refs(output)
        worktree_output = runner(
            ["git", "-C", str(repository.path), "worktree", "list", "--porcelain"],
            cwd=root,
        )
        worktree_heads[repository.name] = _parse_worktree_heads(worktree_output)
    return parse_git_inventory(inventory, refs, worktree_heads)


def project_bead(issue: Any, store: str) -> dict[str, Any]:
    if not isinstance(issue, dict):
        raise CollectorError("bead record must be an object")
    identity = _validate_string(issue.get("id"), "bead id")
    status = _validate_string(issue.get("status"), "bead status")
    priority = issue.get("priority")
    if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 4:
        raise CollectorError("bead priority must be an integer from 0 through 4")
    dependencies = issue.get("dependencies") or []
    if not isinstance(dependencies, list):
        raise CollectorError("bead dependencies must be an array")
    dependency_ids = []
    blocker_ids = []
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            raise CollectorError("bead dependency must be an object")
        dependency_id = _validate_string(dependency.get("id"), "dependency id")
        dependency_ids.append(dependency_id)
        if dependency.get("dependency_type") == "blocks":
            blocker_ids.append(dependency_id)
    qualified_identity = f"{store}:{identity}"
    return {
        "id": qualified_identity,
        "status": status,
        "priority": priority,
        "blockers": sorted({f"{store}:{value}" for value in blocker_ids}),
        "dependencies": sorted({f"{store}:{value}" for value in dependency_ids}),
        "owningStore": _validate_string(store, "owning store"),
    }


def _json_array(output: str, source: str) -> list[Any]:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as error:
        raise CollectorError(f"{source} returned malformed JSON") from error
    if not isinstance(payload, list):
        raise CollectorError(f"{source} result must be an array")
    return payload


def collect_beads(root: Path, repositories: list[Repository], runner: Runner = run_command) -> CollectedRecords:
    stores = [repository for repository in repositories if (repository.path / ".beads").is_dir()]
    listed: list[tuple[Repository, dict[str, Any]]] = []
    for store in stores:
        output = runner(
            ["bd", "-C", str(store.path), "list", "--all", "--limit", "0", "--json", "--readonly"],
            cwd=root,
        )
        for issue in _json_array(output, "bd list"):
            if not isinstance(issue, dict) or not isinstance(issue.get("id"), str):
                raise CollectorError("bd list returned malformed issue data")
            listed.append((store, issue))
    listed.sort(key=lambda item: (item[0].name, item[1]["id"]))
    selected = listed[: RECORD_CAPS["beads"]]
    by_store: dict[str, tuple[Repository, list[str]]] = {}
    for store, issue in selected:
        by_store.setdefault(store.name, (store, []))[1].append(issue["id"])
    detailed: dict[tuple[str, str], dict[str, Any]] = {}
    for store_name, (store, ids) in by_store.items():
        output = runner(
            ["bd", "-C", str(store.path), "show", *ids, "--json", "--readonly"],
            cwd=root,
        )
        for issue in _json_array(output, "bd show"):
            if isinstance(issue, dict) and isinstance(issue.get("id"), str):
                detailed[(store_name, issue["id"])] = issue
    records = []
    for store, listed_issue in selected:
        issue = detailed.get((store.name, listed_issue["id"]), listed_issue)
        records.append(project_bead(issue, store.name))
    return CollectedRecords(records=records, total=len(listed))


def error_envelope(source: str, observed_at: str, diagnostic: str) -> dict[str, Any]:
    return {
        "source": source,
        "scope": SOURCE_SCOPES[source],
        "status": "error",
        "observedAt": observed_at,
        "coverage": {"total": 0, "included": 0, "omitted": 0, "selectionBasis": "unavailable"},
        "records": [],
        "error": _bounded(diagnostic),
    }


def make_envelope(source: str, records: list[dict[str, Any]], observed_at: str, *, total: int | None = None) -> dict[str, Any]:
    observed_at = _timestamp(observed_at)
    try:
        if source not in SOURCE_SCOPES:
            raise CollectorError(f"unsupported source: {source}")
        for record in records:
            _validate_record_strings(record)
        ordered = sorted(records, key=lambda record: record["id"])
        known_total = len(ordered) if total is None else total
        if known_total < len(ordered):
            raise CollectorError("source total cannot be smaller than included records")
        selected = ordered[: RECORD_CAPS[source]]
        basis = "stable repository-qualified identity" if source == "git" else "owning store and bead id"
        while True:
            omitted = known_total - len(selected)
            envelope = {
                "source": source,
                "scope": SOURCE_SCOPES[source],
                "status": "partial" if omitted else "complete",
                "observedAt": observed_at,
                "coverage": {
                    "total": known_total,
                    "included": len(selected),
                    "omitted": omitted,
                    "selectionBasis": basis,
                },
                "records": selected,
            }
            if len(json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")) <= ENVELOPE_BYTES:
                return envelope
            if not selected:
                raise CollectorError("source metadata exceeds envelope byte cap")
            selected.pop()
    except (KeyError, TypeError, CollectorError) as error:
        return error_envelope(source, observed_at, str(error))


def collect(root: Path, sources: tuple[str, ...], observed_at: str, runner: Runner = run_command) -> dict[str, Any]:
    observed_at = _timestamp(observed_at)
    repositories = load_workspace(root)
    result = {}
    for source in sources:
        try:
            check_dependencies((source,))
            if source == "git":
                collected: list[dict[str, Any]] | CollectedRecords = collect_git(root, repositories, runner)
            elif source == "beads":
                collected = collect_beads(root, repositories, runner)
            else:
                raise CollectorError(f"unsupported source: {source}")
            if isinstance(collected, CollectedRecords):
                result[source] = make_envelope(source, collected.records, observed_at, total=collected.total)
            else:
                result[source] = make_envelope(source, collected, observed_at)
        except (CollectorError, OSError) as error:
            result[source] = error_envelope(source, observed_at, str(error))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect bounded read-only workspace watcher evidence")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--sources", default="git,beads")
    parser.add_argument("--observed-at")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--clock", action="store_true")
    parser.add_argument("--until")
    parser.add_argument("--require-stable-route", action="store_true")
    args = parser.parse_args()
    sources = tuple(part for part in args.sources.split(",") if part)
    root = Path(args.workspace).absolute()
    launch_path = Path(os.environ.get("PWD", str(root))).absolute() if args.workspace == "." else root
    try:
        local_now = datetime.now().astimezone()
        observed_at = local_now.isoformat(timespec="seconds")
        if args.clock:
            payload = {"status": "ok", "observedAt": observed_at}
        else:
            repositories = load_workspace(root)
            check_dependencies(sources)
            if args.check:
                if args.require_stable_route:
                    session_value = os.environ.get("PI_SESSION_FILE")
                    agent_dir_value = os.environ.get("PI_CODING_AGENT_DIR")
                    validate_route_stability(
                        Path(session_value) if session_value else None,
                        os.environ.get("PI_SESSION_ID"),
                        os.environ.get("PI_PROVIDER"),
                        os.environ.get("PI_MODEL"),
                        os.environ.get("PI_REASONING_LEVEL"),
                        Path(agent_dir_value) if agent_dir_value else Path.home() / ".pi" / "agent",
                        root,
                        os.environ.get("WATCH_ADMIN_UAT") == "1",
                        Path(os.environ["WATCH_ADMIN_UAT_WORKSPACE"])
                        if os.environ.get("WATCH_ADMIN_UAT_WORKSPACE")
                        else None,
                        launch_path=launch_path,
                    )
                run_command(["project-workspace", "doctor", "--workspace", str(root)], cwd=root)
                payload = {
                    "status": "ok",
                    "workspace": str(root),
                    "repositories": len(repositories) - 1,
                    "sources": list(sources),
                    "observedAt": observed_at,
                    "routeStable": args.require_stable_route,
                }
                if args.until:
                    payload["stopAt"] = resolve_deadline(args.until, local_now)
            else:
                payload = collect(root, sources, args.observed_at or observed_at)
        json.dump(payload, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        sys.stdout.write("\n")
        return 0
    except CollectorError as error:
        print(f"ERROR: {_bounded(str(error))}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
