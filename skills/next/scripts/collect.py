#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

COMMAND_TIMEOUT_SECONDS = 5
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
                repositories.append(Source(name, relative_path, link))

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


def diagnostic_text(result: subprocess.CompletedProcess[str]) -> str:
    text = (result.stderr or result.stdout).strip().replace("\n", " ")
    return text[:240] or f"bd exited {result.returncode}"


def load_issues(source: Source, arguments: list[str]) -> tuple[list[dict[str, Any]], str | None]:
    try:
        result = subprocess.run(
            ["bd", *arguments, "--json", "--readonly"],
            cwd=source.directory,
            capture_output=True,
            check=False,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return [], f"timed out after {COMMAND_TIMEOUT_SECONDS} seconds"
    except OSError as error:
        return [], str(error)
    if result.returncode != 0:
        return [], diagnostic_text(result)
    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        return [], f"invalid bd JSON: {error}"
    if not isinstance(issues, list) or not all(isinstance(issue, dict) for issue in issues):
        return [], "invalid bd JSON: expected an issue list"
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


def collect(root: Path) -> dict[str, Any]:
    workspace, sources = discover_sources(root)
    payload: dict[str, Any] = {
        "workspace": workspace,
        "ready": [],
        "blocked": [],
        "in_progress": [],
        "diagnostics": [],
    }
    commands = {
        "ready": ["list", "--ready", "--priority-max=3", "--flat"],
        "blocked": ["blocked"],
        "in_progress": ["list", "--status=in_progress", "--flat"],
    }
    for source in sources:
        beads = source.directory / ".beads"
        if workspace and (not beads.is_dir() or beads.is_symlink()):
            continue
        for key, arguments in commands.items():
            issues, error = load_issues(source, arguments)
            if error is not None:
                if workspace:
                    payload["diagnostics"].append(f"{source.name}: {key}: {error}")
                continue
            payload[key].extend(owned_issues(source, issues, workspace))
    return payload


def main() -> int:
    json.dump(collect(Path.cwd()), sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
