from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).parents[1]

FAKE_BD = """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

arguments = sys.argv[1:]
directory = Path.cwd()
while arguments and arguments[0] == '-C':
    directory = Path(arguments[1])
    arguments = arguments[2:]

log = os.environ.get('BD_CALL_LOG')
if log:
    with open(log, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps({
            'directory': str(directory.resolve()),
            'arguments': arguments,
        }) + '\\n')

payload = json.loads((directory / '.beads' / 'fixture.json').read_text())
command = arguments[0]

if command == 'show':
    key = 'show'
elif command == 'update':
    key = 'update'
elif command == 'blocked':
    key = 'blocked'
elif '--id' in arguments:
    key = 'probe'
elif '--ready' in arguments:
    key = 'ready'
elif '--status=in_progress' in arguments:
    key = 'in_progress'
else:
    raise SystemExit(2)

fault = payload.get('faults', {}).get(key)
if fault == 'error':
    print(f'simulated {key} failure', file=sys.stderr)
    raise SystemExit(9)
if fault == 'invalid-json':
    print('{')
    raise SystemExit(0)

issues = [i for k in ('ready', 'blocked', 'in_progress', 'other') for i in payload.get(k, [])]
if key == 'show':
    selector = arguments[1]
    matches = [
        issue for issue in issues
        if issue['id'] == selector or issue['id'].endswith('-' + selector)
    ]
    if not matches:
        print(f"issue not found: {arguments[1]}", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(matches[:1]))
    raise SystemExit(0)
if key == 'update':
    raise SystemExit(0)
if key == 'probe':
    issue_id = arguments[arguments.index('--id') + 1]
    print(json.dumps([issue for issue in issues if issue['id'] == issue_id]))
    raise SystemExit(0)
print(json.dumps(payload[key]))
"""


def issue(
    issue_id: str,
    priority: int,
    issue_type: str,
    created_at: str,
    *,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": issue_id,
        "title": f"Title for {issue_id}",
        "priority": priority,
        "issue_type": issue_type,
        "labels": labels or [],
        "created_at": created_at,
    }


class WorkspaceFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.call_log = self.base / "bd-calls.jsonl"

        fake_bin = self.base / "bin"
        fake_bin.mkdir()
        fake_bd = fake_bin / "bd"
        fake_bd.write_text(FAKE_BD, encoding="utf-8")
        fake_bd.chmod(0o755)

        self.environment = os.environ.copy()
        self.environment["PATH"] = f"{fake_bin}:{self.environment['PATH']}"
        self.environment["BD_CALL_LOG"] = str(self.call_log)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def recorded_calls(self) -> list[dict[str, Any]]:
        if not self.call_log.exists():
            return []
        return [
            json.loads(line)
            for line in self.call_log.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def create_store(
        self,
        directory: Path,
        *,
        ready: list[dict[str, Any]] | None = None,
        blocked: list[dict[str, Any]] | None = None,
        in_progress: list[dict[str, Any]] | None = None,
        other: list[dict[str, Any]] | None = None,
        faults: dict[str, str] | None = None,
    ) -> None:
        directory.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "-q", "--initial-branch=main"],
            cwd=directory,
            check=True,
        )
        beads = directory / ".beads"
        beads.mkdir()
        (beads / "fixture.json").write_text(
            json.dumps(
                {
                    "ready": ready or [],
                    "blocked": blocked or [],
                    "in_progress": in_progress or [],
                    "other": other or [],
                    "faults": faults or {},
                }
            ),
            encoding="utf-8",
        )

    def create_workspace(
        self,
        *,
        root_data: dict[str, Any] | None = None,
        repositories: dict[str, dict[str, Any]] | None = None,
    ) -> Path:
        root = self.base / "workspace"
        self.create_store(root, **(root_data or {}))
        (root / "repos").mkdir()
        (root / "infrastructure").mkdir()
        for relative_path in (
            "docs/prds",
            "docs/adrs",
            "docs/architecture",
            "docs/runbooks",
        ):
            (root / relative_path).mkdir(parents=True)
        (root / "AGENTS.md").write_text("# Fixture agents\n", encoding="utf-8")
        (root / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")

        entries = []
        for index, (name, data) in enumerate((repositories or {}).items()):
            target = self.base / "sources" / name
            self.create_store(target, **data)
            link = root / "repos" / name
            link.symlink_to(os.path.relpath(target, link.parent), target_is_directory=True)
            entries.append(
                {
                    "name": name,
                    "path": f"repos/{name}",
                    "role": "primary" if index == 0 else "service",
                }
            )

        manifest = {
            "version": 1,
            "name": "Fixture Workspace",
            "repositories": entries,
            "infrastructure": [],
        }
        (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
        repository_lines = "\n".join(
            f"- `{entry['name']}` — [`{entry['path']}`]({entry['path']}) ({entry['role']})"
            for entry in entries
        ) or "_No repositories are registered yet._"
        (root / "README.md").write_text(
            "# Fixture Workspace\n\n"
            "<!-- project-workspace:repositories:start -->\n"
            f"{repository_lines}\n"
            "<!-- project-workspace:repositories:end -->\n\n"
            "<!-- project-workspace:infrastructure:start -->\n"
            "_No infrastructure references are registered yet._\n"
            "<!-- project-workspace:infrastructure:end -->\n",
            encoding="utf-8",
        )
        return root

    def run_script(
        self, script: Path, directory: Path, *arguments: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(script), *arguments],
            cwd=directory,
            env=self.environment,
            capture_output=True,
            check=check,
            text=True,
        )
