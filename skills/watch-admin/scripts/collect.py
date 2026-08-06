#!/usr/bin/env python3
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
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
    args = parser.parse_args()
    sources = tuple(part for part in args.sources.split(",") if part)
    root = Path(args.workspace).absolute()
    try:
        local_now = datetime.now().astimezone()
        observed_at = local_now.isoformat(timespec="seconds")
        if args.clock:
            payload = {"status": "ok", "observedAt": observed_at}
        else:
            repositories = load_workspace(root)
            check_dependencies(sources)
            if args.check:
                run_command(["project-workspace", "doctor", "--workspace", str(root)], cwd=root)
                payload = {
                    "status": "ok",
                    "workspace": str(root),
                    "repositories": len(repositories) - 1,
                    "sources": list(sources),
                    "observedAt": observed_at,
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
