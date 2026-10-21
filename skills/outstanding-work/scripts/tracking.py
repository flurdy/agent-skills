#!/usr/bin/env python3
"""Bounded read-only tracking inventory; semantic completion remains the skill's job."""
from __future__ import annotations

import json
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

SELECTOR = Path(__file__).resolve().parents[2] / "next/scripts/next-select"
MAX_STORES = 8
MAX_ROWS = 200
MAX_RELATED = 20
MAX_BYTES = 2_000_000
MAX_TEXT = 6000
TIMEOUT_SECONDS = 15
FIELDS = (
    "id", "title", "status", "external_ref", "description", "acceptance_criteria",
    "notes", "close_reason", "parent", "dependencies", "children", "dependents",
    "dependency_count", "dependent_count", "comment_count", "updated_at", "revision",
)


def run_json(args):
    try:
        child = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 start_new_session=True)
    except OSError as error:
        raise ValueError("command unavailable") from error
    deadline, size, output = time.monotonic() + TIMEOUT_SECONDS, 0, bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            selector.register(child.stderr, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("command timed out")
                for key, _ in selector.select(min(remaining, 0.25)):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("combined stdout/stderr response exceeded byte limit")
                    if key.fileobj is child.stdout:
                        output.extend(chunk)
        code = child.wait(timeout=max(0.01, deadline - time.monotonic()))
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("command unavailable or timed out") from error
    finally:
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
        child.stdout.close()
        child.stderr.close()
    try:
        data = json.loads(output)
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError("malformed JSON") from error
    if code and not (args[0] == str(SELECTOR) and args[1:2] == ["resolve"]
                     and isinstance(data, dict) and data.get("status") in
                     ("ambiguous", "not-found", "unavailable", "stale")):
        raise ValueError("command failed")
    return data


def collect(target, runner=run_json):
    started = time.monotonic()
    result = {"target": target or "CURRENT", "complete": True, "stores": [], "issues": [], "gaps": []}
    issues = {}
    proven_refs = {}

    def gap(message):
        if message not in result["gaps"]:
            result["gaps"].append(message)
        result["complete"] = False

    def call(args):
        if time.monotonic() - started > 90:
            raise ValueError("collection time budget exhausted")
        return runner(args)

    def rows(value):
        if not isinstance(value, list) or any(
            not isinstance(row, dict) or not isinstance(row.get("id"), str)
            for row in value
        ):
            raise ValueError("malformed issue list")
        return value

    def add(directory, owner, row, association):
        identity = (directory, row["id"])
        if identity not in issues:
            if len(issues) >= MAX_ROWS:
                gap(f"distinct record limit {MAX_ROWS}; additional records omitted")
                return
            selected = {key: row[key] for key in FIELDS if key in row}
            for key, value in selected.items():
                if isinstance(value, str) and len(value) > MAX_TEXT:
                    selected[key] = value[:MAX_TEXT]
                    gap(f"{owner}:{row['id']} {key} truncated at {MAX_TEXT} characters")
            issues[identity] = {"directory": directory, "repository": owner,
                                "issue": selected, "association": []}
        if association not in issues[identity]["association"]:
            issues[identity]["association"].append(association)

    try:
        listing = call([str(SELECTOR), "stores"])
        if not isinstance(listing, dict) or not isinstance(listing.get("stores"), list):
            raise ValueError("malformed store listing")
        stores = {}
        for source in listing["stores"]:
            if not isinstance(source, dict):
                raise ValueError("malformed store entry")
            directory = source.get("directory")
            owner = source.get("owner") or source.get("repository")
            if not isinstance(directory, str) or not Path(directory).is_absolute() or not isinstance(owner, str):
                raise ValueError("invalid store identity")
            if source.get("usable") is not True:
                gap(f"{owner}: store unavailable")
                continue
            stores.setdefault(directory, owner)
        if len(stores) > MAX_STORES:
            gap(f"store limit {MAX_STORES}; additional stores not queried")
        stores = dict(list(stores.items())[:MAX_STORES])
        result["stores"] = [{"directory": d, "repository": o} for d, o in stores.items()]
        if not stores:
            gap("no proven usable stores")
    except (ValueError, TypeError) as error:
        gap(f"ownership unavailable: {error}")
        return result

    def resolve_read(selector, association):
        try:
            resolution = call([str(SELECTOR), "resolve", selector])
            if not isinstance(resolution, dict):
                raise ValueError("malformed ownership response")
            if resolution.get("status") != "resolved":
                details = {key: resolution[key] for key in ("status", "matches", "failures", "hint") if key in resolution}
                raise ValueError("ownership unresolved: " + json.dumps(details, ensure_ascii=True)[:MAX_TEXT])
            directory, issue_id = resolution.get("directory"), resolution.get("id")
            if issue_id != selector.split(":", 1)[-1]:
                raise ValueError("resolved ID does not match requested identity")
            if directory not in stores:
                raise ValueError("resolved owner outside inspected stores")
            found = rows(call(["bd", "-C", directory, "show", issue_id, "--json", "--readonly"]))
            if len(found) != 1 or found[0]["id"] != issue_id:
                raise ValueError("resolved issue not returned exactly")
            add(directory, stores[directory], found[0], association)
            proven_refs[selector] = (directory, issue_id)
        except (ValueError, TypeError) as error:
            gap(f"{selector}: {error}")

    jira = bool(re.fullmatch(r"[A-Z][A-Z0-9]+-[0-9]+", target))
    if target and not jira:
        if target.isdecimal():
            gap("numeric targets are not bead identities; ranked selection is not supported")
            return result
        resolve_read(target, "explicit")
    else:
        probes = [("--status=in_progress", None, "candidate")]
        if jira:
            probes = [("--external-contains", "external_ref", "external_ref"),
                      ("--title-contains", "title", "title"),
                      ("--desc-contains", "description", "description"),
                      ("--notes-contains", "notes", "notes")]
        token = re.compile(r"(?<![A-Z0-9_])" + re.escape(target) + r"(?![A-Z0-9_-])", re.I)
        for directory, owner in stores.items():
            for flag, field, association in probes:
                args = ["bd", "-C", directory, "list", flag]
                if jira:
                    args += [target, "--all"]
                args += ["--limit=201", "--json", "--readonly"]
                try:
                    found = rows(call(args))
                    if len(found) > MAX_ROWS:
                        gap(f"{owner} {association}: row limit {MAX_ROWS}; more records exist")
                    for row in found[:MAX_ROWS]:
                        if not jira or token.search(str(row.get(field) or "")):
                            add(directory, owner, row, association)
                except (ValueError, TypeError) as error:
                    gap(f"{owner} {association}: unavailable ({error})")

    def references(row):
        refs = []

        def reference(value, field):
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]+-[A-Za-z0-9_.-]+", value):
                gap(f"{row['id']}: malformed {field} identifier")
            else:
                refs.append(value)

        if row.get("parent") is not None:
            reference(row["parent"], "parent")
        for key in ("dependencies", "children", "dependents"):
            items = row.get(key)
            if items is None:
                continue
            if not isinstance(items, list):
                gap(f"{row['id']}: malformed {key} container")
                continue
            for item in items:
                ref = item if isinstance(item, str) else None
                if isinstance(item, dict):
                    ref = item.get("id") or item.get("depends_on_id")
                reference(ref, key)
        for count, key in (("dependent_count", "dependents"), ("dependency_count", "dependencies")):
            value = row.get(count, 0)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                gap(f"{row['id']}: malformed {count}")
            elif value and not row.get(key):
                gap(f"{row['id']}: {key} details missing (reverse links/children may be unexpanded)")
        return refs

    # One hop only. Resolve every linked identity: an ID prefix is not an owner.
    linked = sorted({ref for record in issues.values() for ref in references(record["issue"])})
    if len(linked) > MAX_RELATED:
        gap(f"related-record limit {MAX_RELATED}; additional links not queried")
    for ref in linked[:MAX_RELATED]:
        resolve_read(ref, "related")
    for record in issues.values():
        if "related" in record["association"]:
            for ref in references(record["issue"]):
                if ref not in proven_refs or proven_refs[ref] not in issues:
                    gap(f"{record['issue']['id']}: further link {ref} unresolved beyond one-hop limit")
    result["issues"] = list(issues.values())
    return result


def main():
    if len(sys.argv) > 2:
        print("usage: tracking.py [<owner:bead-id|JIRA-key>]", file=sys.stderr)
        return 2
    result = collect(sys.argv[1] if len(sys.argv) == 2 else "")
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
