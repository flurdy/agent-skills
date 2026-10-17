#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

COMMAND_TIMEOUT_SECONDS = 5
BEADS_READ_TIMEOUT_ENV = "NEXT_BEADS_READ_TIMEOUT_SECONDS"
MISSING_STORE_ERROR = "missing .beads store"
DOLT_UNREACHABLE = re.compile(r"Dolt server (?:unreachable|may not be running)", re.IGNORECASE)
REGISTRATION_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MANAGED_DIRECTORIES = (
    "docs",
    "docs/prds",
    "docs/adrs",
    "docs/architecture",
    "docs/runbooks",
    "repos",
    "infrastructure",
)


@dataclass(frozen=True)
class Source:
    name: str
    relative_path: str
    directory: Path
    store: str = "local"
    declaration_error: str | None = None
    store_declared: bool = False


def beads_read_timeout() -> int:
    value = os.environ.get(BEADS_READ_TIMEOUT_ENV, "60")
    if not re.fullmatch(r"[0-9]{1,3}", value) or not 1 <= int(value) <= 120:
        raise ValueError(f"{BEADS_READ_TIMEOUT_ENV} must be an integer from 1 to 120 seconds")
    return int(value)


def is_nested(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def is_git_root(directory: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=False,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and Path(result.stdout.strip()).resolve() == directory.resolve()


def text_file(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def entry_summary(entries: list[dict[str, Any]], empty: str) -> str:
    if not entries:
        return empty
    lines = []
    for entry in entries:
        suffix = f" ({entry['role']})" if entry.get("role") else ""
        lines.append(
            f"- `{entry['name']}` — [`{entry['path']}`]({entry['path']}){suffix}"
        )
    return "\n".join(lines)


def legacy_readme(manifest: dict[str, Any]) -> str | None:
    if manifest["infrastructure"]:
        return None
    name = manifest["name"]
    repositories = entry_summary(
        manifest["repositories"], "_No repositories are registered yet._"
    )
    return f"""# {name} Workspace

This workspace holds cross-project context and tracking for **{name}**.
Implementation remains in the repositories linked below.

## Start here

- [`workspace.json`](workspace.json) is the machine-readable topology index.
- [`AGENTS.md`](AGENTS.md) defines workspace-level agent guidance.
- [`docs/prds/`](docs/prds/) contains cross-project product requirements.
- [`docs/adrs/`](docs/adrs/) contains cross-project architecture decisions.
- [`docs/architecture/`](docs/architecture/) contains architecture context.
- [`docs/runbooks/`](docs/runbooks/) contains cross-project operational guidance.

## Repositories

{repositories}

For a greenfield workspace, link the first repository under `repos/` and add its
relative path to `workspace.json` when it exists. Repository-specific instructions and """ \
        """documentation remain authoritative inside each
repository. Infrastructure repositories or configuration may be linked under
[`infrastructure/`](infrastructure/) and indexed in `workspace.json`.

## Commands

```bash
make help
make status
make doctor
```

Use `bd` from this root for durable cross-project work. Configure multi-repository Git
operations separately with `/setup-multirepo-git` when needed.
"""


def readme_matches_manifest(readme: str, manifest: dict[str, Any]) -> bool:
    sections = {
        "repositories": entry_summary(
            manifest["repositories"], "_No repositories are registered yet._"
        ),
        "infrastructure": entry_summary(
            manifest["infrastructure"],
            "_No infrastructure references are registered yet._",
        ),
    }
    markers = [
        f"<!-- project-workspace:{collection}:{boundary} -->"
        for collection in sections
        for boundary in ("start", "end")
    ]
    if all(readme.count(marker) == 1 for marker in markers):
        return all(
            (
                f"<!-- project-workspace:{collection}:start -->\n"
                f"{content}\n"
                f"<!-- project-workspace:{collection}:end -->"
            )
            in readme
            for collection, content in sections.items()
        )
    if any(marker in readme for marker in markers):
        return False
    return readme == legacy_readme(manifest)


def valid_workspace_root(root: Path) -> bool:
    git_path = root / ".git"
    beads_path = root / ".beads"
    if root.is_symlink() or git_path.is_symlink() or beads_path.is_symlink():
        return False
    if not is_git_root(root) or not beads_path.is_dir():
        return False
    for relative_path in MANAGED_DIRECTORIES:
        directory = root / relative_path
        if not directory.is_dir() or directory.is_symlink():
            return False
    return all(
        text_file(root / filename) is not None
        for filename in ("README.md", "AGENTS.md", "Makefile")
    )


def registered_sources(root: Path, manifest: dict[str, Any]) -> list[Source] | None:
    if manifest.get("version") != 1 or not isinstance(manifest.get("name"), str):
        return None
    if not manifest["name"].strip() or "\n" in manifest["name"] or "\r" in manifest["name"]:
        return None
    if not valid_workspace_root(root):
        return None

    names: set[str] = set()
    targets: set[Path] = set()
    expected_links: set[Path] = set()
    repositories: list[Source] = []
    physical_root = root.resolve()

    for collection, directory_name in (
        ("repositories", "repos"),
        ("infrastructure", "infrastructure"),
    ):
        directory = root / directory_name
        entries = manifest.get(collection)
        if not directory.is_dir() or directory.is_symlink() or not isinstance(entries, list):
            return None
        for entry in entries:
            if not isinstance(entry, dict):
                return None
            name = entry.get("name")
            relative_path = entry.get("path")
            if not isinstance(name, str) or not isinstance(relative_path, str):
                return None
            if not REGISTRATION_NAME.fullmatch(name) or name in names:
                return None
            if relative_path != f"{directory_name}/{name}":
                return None
            if collection == "repositories" and entry.get("role") not in {"primary", "service"}:
                return None

            names.add(name)
            link = root / relative_path
            expected_links.add(link)
            if not link.is_symlink() or os.path.isabs(os.readlink(link)) or not link.is_dir():
                return None
            target = link.resolve()
            if is_nested(target, physical_root) or is_nested(physical_root, target):
                return None
            if target in targets:
                return None
            targets.add(target)
            if collection == "repositories":
                if not is_git_root(target):
                    return None
                store = entry.get("beadsStore", "local")
                error = None
                if store not in ("local", "workspace"):
                    error = "invalid beadsStore declaration: expected local or workspace"
                    store = "local"
                repositories.append(Source(
                    name, relative_path, link, store, error,
                    store_declared="beadsStore" in entry,
                ))

        if any(
            child.name != ".gitkeep" and child not in expected_links
            for child in directory.iterdir()
        ):
            return None

    readme = text_file(root / "README.md")
    if readme is None or not readme_matches_manifest(readme, manifest):
        return None
    return [Source("workspace", ".", root), *repositories]


def discover_sources(root: Path) -> tuple[bool, list[Source]]:
    manifest_path = root / "workspace.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return False, [Source("local", ".", root)]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False, [Source("local", ".", root)]
    if not isinstance(manifest, dict):
        return False, [Source("local", ".", root)]
    sources = registered_sources(root, manifest)
    if sources is None:
        return False, [Source("local", ".", root)]
    return True, sources


def concise_text(text: str) -> str:
    return text.strip().replace("\n", " ")[:240]


def diagnostic_text(result: subprocess.CompletedProcess[str]) -> str:
    return concise_text(result.stderr or result.stdout) or f"bd exited {result.returncode}"


def store_error(source: Source) -> str | None:
    if source.declaration_error is not None:
        return source.declaration_error
    beads = source.directory / ".beads"
    if source.store == "workspace":
        if os.path.lexists(beads):
            return "unexpected .beads store for workspace-owned repository"
        return None
    if beads.is_symlink():
        return "unusable .beads store: symlink"
    if not beads.exists():
        return MISSING_STORE_ERROR
    if not beads.is_dir():
        return "unusable .beads store: not a directory"
    return None


def unavailable_store(source: Source, reason: str) -> dict[str, Any]:
    hint = None
    if DOLT_UNREACHABLE.search(reason):
        command = f"bd -C {shlex.quote(str(source.directory))} dolt start"
        hint = f"Dolt server not running. Start it manually: `{command}`, then rerun /next."
    return {"repository": source.name, "reason": reason, "hint": hint}


def load_issues(source: Source, arguments: list[str]) -> tuple[list[dict[str, Any]], str | None]:
    timeout = beads_read_timeout()
    started = monotonic()
    try:
        result = subprocess.run(
            ["bd", "-C", str(source.directory), *arguments, "--json", "--readonly"],
            cwd=source.directory,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return [], (f"Beads read timed out (elapsed {monotonic() - started:.2f}s, "
                    f"deadline {timeout}s; {BEADS_READ_TIMEOUT_ENV})")
    except OSError as error:
        return [], concise_text(str(error))
    if result.returncode != 0:
        return [], diagnostic_text(result)
    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        return [], f"invalid bd JSON: {error}"
    if not isinstance(issues, list) or not all(
        isinstance(issue, dict) and isinstance(issue.get("id"), str) and issue["id"].strip()
        for issue in issues
    ):
        return [], "invalid bd JSON: expected an issue list with non-empty IDs"
    return issues, None


def owned_issues(
    source: Source, issues: list[dict[str, Any]], workspace: bool
) -> list[dict[str, Any]]:
    if not workspace:
        return issues
    return [
        {
            **issue,
            "repository": source.name,
            "repository_path": source.relative_path,
            "selector": f"{source.name}:{issue.get('id', '')}",
        }
        for issue in issues
    ]


def declared_source_scope(issue: dict[str, Any], source: Source) -> dict[str, Any]:
    def result(state: str, reason: str, roots: list[str] | None = None) -> dict[str, Any]:
        return {"state": state, "reason": reason, "roots": roots or []}

    metadata = issue.get("metadata")
    if metadata is None or isinstance(metadata, dict) and "source_scope" not in metadata:
        return result("unknown", "source scope is undeclared")
    scope = metadata.get("source_scope") if isinstance(metadata, dict) else None
    if not isinstance(scope, dict) or set(scope) != {"version", "complete", "roots"}:
        return result("invalid", "expected source_scope version, complete and roots")
    roots = scope["roots"]
    if (
        type(scope["version"]) is not int or scope["version"] != 1
        or type(scope["complete"]) is not bool
        or not isinstance(roots, list) or not 1 <= len(roots) <= 32
        or any(not isinstance(root, str) or not root or len(root) > 4096
               or Path(root).is_absolute() or root.startswith("~")
               or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in root)
               for root in roots)
    ):
        return result("invalid", "invalid or oversized source_scope v1 declaration")
    if store_error(source) is not None or os.path.lexists(source.directory / ".beads" / "redirect"):
        return result("unavailable", "source-scope base is not a usable non-redirected store root")
    canonical = []
    try:
        for root in roots:
            path = (source.directory.resolve() / root).resolve(strict=True)
            if not path.is_dir():
                return result("invalid", "source roots must be directories")
            if str(path) not in canonical:
                canonical.append(str(path))
    except (OSError, RuntimeError):
        return result("unavailable", "a declared source path cannot be resolved")
    return result(
        "declared" if scope["complete"] else "partial",
        "explicit complete declaration; Git roots not yet observed" if scope["complete"]
        else "source scope is explicitly incomplete",
        canonical,
    )


def service_names(source: Source, workspace: bool) -> dict[str, str]:
    directories = [source.directory]
    if workspace and source.relative_path == ".":
        directories += [source.directory / "repos", source.directory / "infrastructure"]
    names: dict[str, str] = {}
    for directory in directories:
        try:
            for child in directory.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    names.setdefault(child.name, str(child.resolve()))
        except OSError:
            continue
    return names


def service_labels(issue: dict[str, Any], services: dict[str, str]) -> list[str]:
    labels = issue.get("labels")
    if not isinstance(labels, list):
        return []
    return [label for label in labels if isinstance(label, str) and label in services]


def collect(root: Path, source_scope: bool = False) -> dict[str, Any]:
    beads_read_timeout()
    workspace, sources = discover_sources(root)
    payload: dict[str, Any] = {
        "workspace": workspace,
        "ready": [],
        "blocked": [],
        "in_progress": [],
        "deferred": [],
        "diagnostics": [],
        "unavailable_stores": [],
    }
    commands = {
        "ready": ["list", "--ready", "--flat", "--limit=0"],
        "blocked": ["blocked"],
        "in_progress": ["list", "--status=in_progress", "--flat", "--limit=0"],
        "deferred": ["list", "--status=deferred", "--flat", "--limit=0"],
    }
    for source in sources:
        error = store_error(source)
        if workspace and error is not None:
            payload["diagnostics"].append(f"{source.name}: {error}")
            payload["unavailable_stores"].append(unavailable_store(source, error))
            continue
        if source.store == "workspace":
            continue
        collected: dict[str, list[dict[str, Any]]] = {}
        services = service_names(source, workspace) if source_scope else {}
        for key, arguments in commands.items():
            issues, error = load_issues(source, arguments)
            if error is not None:
                payload["diagnostics"].append(f"{source.name}: {key}: {error}")
                payload["unavailable_stores"].append(unavailable_store(source, f"{key}: {error}"))
                break
            collected[key] = owned_issues(source, issues, workspace)
            if source_scope:
                collected[key] = [
                    {**issue, "repository": source.name, "selector": f"{source.name}:{issue['id']}",
                     "source_scope": declared_source_scope(issue, source),
                     "services": service_labels(issue, services),
                     "service_roots": [services[label] for label in service_labels(issue, services)]}
                    for issue in collected[key]
                ]
        else:
            for key, issues in collected.items():
                payload[key].extend(issues)
    return payload


def main() -> int:
    try:
        payload = collect(Path.cwd(), source_scope="--source-scope" in sys.argv[1:])
    except ValueError as error:
        print(f"next-bd: {error}", file=sys.stderr)
        return 2
    json.dump(payload, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
