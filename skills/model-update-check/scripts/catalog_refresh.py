#!/usr/bin/env python3
"""Explicit, models-only Pi refresh. Never print native stdout/stderr or credentials."""
from __future__ import annotations

import argparse
import json
import os
import re
import selectors
import signal
import subprocess
import time
from pathlib import Path

DISCLOSURE = (
    "Runs only pi update --models. Pi natively accesses auth.json and models.json; "
    "it performs network activity and persists catalog data (models-store.json in Pi 0.87.1). "
    "Native provider authentication effects are version-dependent; this is not a public-only "
    "unauthenticated fetch. The agent does not read credentials or run inference. "
    "Failure/timeout may leave partial cache/auth effects; there is no automatic rollback."
)


def run_native(argv, timeout, max_bytes=16 * 1024 * 1024):
    try:
        with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              stdin=subprocess.DEVNULL, start_new_session=True) as child:
            deadline = time.monotonic() + timeout
            output = bytearray()
            status = "ok"
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        status = "timeout"
                        break
                    if not selector.select(remaining):
                        continue
                    chunk = os.read(child.stdout.fileno(), min(65536, max_bytes + 1 - len(output)))
                    if not chunk:
                        selector.unregister(child.stdout)
                        break
                    output.extend(chunk)
                    if len(output) > max_bytes:
                        status = "output-limit"
                        break
            if status == "ok":
                try:
                    child.wait(timeout=max(0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    status = "timeout"
            if status != "ok":
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
                return status, ""
            return ("failed", "") if child.returncode else ("ok", output.decode("utf-8", errors="replace"))
    except OSError:
        return "unavailable", ""


def refresh(requested, confirmed, offline, timeout=60):
    result = {"status": "not-requested", "attempted": False, "fresh": False,
              "command": ["pi", "update", "--models"], "disclosure": DISCLOSURE}
    if offline and requested:
        result["status"] = "offline-conflict"
    elif confirmed and not requested:
        result["status"] = "invalid-confirmation"
    elif requested and not confirmed:
        result["status"] = "authorization-required"
    elif requested:
        status, help_text = run_native(["pi", "update", "--help"], min(timeout, 15))
        if status != "ok":
            result["status"] = f"capability-{status}"
        elif not re.search(r"^\s*--models\s+.*[Rr]efresh.*[Mm]odel", help_text, re.M):
            result["status"] = "unsupported"
        else:
            result["attempted"] = True
            status, _ = run_native(result["command"], timeout)
            result["status"] = status
            result["fresh"] = status == "ok"
    return result


def collect_catalog():
    status, version = run_native(["pi", "--version"], 15)
    if status != "ok":
        return {"status": status, "installedVersion": None, "models": []}
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version.strip()):
        return {"status": "invalid-version", "installedVersion": None, "models": []}
    # Native AuthStorage creates a missing auth.json even during enumeration.
    # Check existence only: never open or copy the credential store in this helper.
    agent_dir = Path(os.environ.get("PI_CODING_AGENT_DIR", str(Path.home() / ".pi/agent")))
    if not (agent_dir / "auth.json").is_file():
        return {"status": "auth-store-absent", "installedVersion": version.strip(), "models": []}
    command = ["pi", "--offline", "--no-extensions", "--no-skills", "--no-prompt-templates",
               "--no-themes", "--no-context-files", "--no-approve", "--list-models"]
    status, output = run_native(command, 30)
    lines = output.splitlines()
    rows = []
    if status == "ok":
        if not lines or lines[0].split()[:2] != ["provider", "model"]:
            status = "invalid-output"
        else:
            for line in lines[1:]:
                fields = line.split()
                if len(fields) != 6:
                    status = "invalid-output"
                    break
                rows.append({"provider": fields[0], "model": fields[1]})
    return {"status": status, "installedVersion": version.strip(),
            "scope": "offline native catalog/auth scope; extensions disabled", "extensionsEnabled": False,
            "models": rows if status == "ok" else []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enumerate", action="store_true")
    parser.add_argument("--requested", action="store_true")
    parser.add_argument("--confirmed", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--timeout", type=int, default=60, choices=range(1, 301), metavar="1..300")
    args = parser.parse_args()
    result = collect_catalog() if args.enumerate else refresh(args.requested, args.confirmed, args.offline, args.timeout)
    print(json.dumps(result))
    return 0 if result["status"] in {"not-requested", "ok"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
