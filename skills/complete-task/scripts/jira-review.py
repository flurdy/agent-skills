#!/usr/bin/env python3
"""Decide whether a just-completed bead may offer one approved Jira review transition.

``plan`` gathers local evidence only: the opt-in policy, delivery milestone, the completing
bead's explicit ``jira-<KEY>`` association and every bead with that reference in the proven
tracking scope. ``decide`` repeats ``plan`` and applies the policy to raw Jira issue and
transition responses read from stdin. Both print one JSON object and exit 0 for every
evaluated outcome (2 for usage errors). Neither contacts Jira, writes tracking, fetches Git
refs nor synchronizes stores. Requires Python 3.11+.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

POLICY_PATH = Path(".agents") / "jira-review.toml"
POLICY_KEYS = {"milestones", "source_statuses", "target_status"}
MILESTONES = ("trunk-commit", "pr-created")
JIRA_KEY = re.compile(r"[A-Z][A-Z0-9]*-[1-9][0-9]*")
NEXT_SELECT = Path(__file__).resolve().parents[2] / "next" / "scripts" / "next-select"
TIMEOUT_SECONDS = 60


class Outcome(Exception):
    """Stops evaluation with a reportable result other than ``ready``."""

    def __init__(self, status: str, reason: str, detail: str = "") -> None:
        super().__init__(detail)
        self.status, self.reason, self.detail = status, reason, detail


def skip(reason: str, detail: str) -> Outcome:
    return Outcome("skip", reason, detail)


def fold(value: str) -> str:
    return " ".join(value.split()).casefold()


def run(args: list[str], reason: str, cwd: Path | None = None) -> str:
    name = Path(args[0]).name
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise skip(reason, f"{name}: {error}") from error
    if result.returncode:
        lines = (result.stderr or result.stdout).strip().splitlines()
        raise skip(reason, f"{name} exited {result.returncode}: {lines[-1][:300] if lines else 'no output'}")
    return result.stdout


def run_json(args: list[str], reason: str, cwd: Path | None = None) -> Any:
    output = run(args, reason, cwd)
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise skip(reason, f"{Path(args[0]).name} returned malformed JSON") from error


def logical_path(repo: str) -> Path:
    working = Path.cwd()
    shell = os.environ.get("PWD")
    if shell and Path(shell).is_absolute():
        try:
            if Path(shell).resolve() == working.resolve():
                working = Path(shell)
        except OSError:
            pass
    return Path(os.path.normpath(working / repo))


def upward(start: Path):
    """Yield start and its ancestors, stopping below $HOME so ~/.agents never applies."""
    home = Path(os.environ.get("HOME") or "/")
    boundaries = {home, home.resolve()}
    directory = start
    while directory != directory.parent:
        if any(directory == boundary or boundary.is_relative_to(directory) for boundary in boundaries):
            return
        yield directory
        directory = directory.parent


def find_policy(logical: Path, physical: Path | None) -> Path | None:
    for start in (logical, physical):
        for directory in upward(start) if start else ():
            if (directory / POLICY_PATH).is_file():
                return directory / POLICY_PATH
    return None


def load_policy(path: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()
        raw = tomllib.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise skip("policy-invalid", f"{path}: {error}") from error
    problems = []
    if unknown := sorted(set(raw) - POLICY_KEYS):
        problems.append(f"unknown keys {', '.join(unknown)}")
    milestones = raw.get("milestones")
    if not (isinstance(milestones, list) and milestones and all(m in MILESTONES for m in milestones)
            and len(set(milestones)) == len(milestones)):
        problems.append(f"milestones must be a non-empty list of distinct {' / '.join(MILESTONES)}")
    sources = raw.get("source_statuses")
    if not (isinstance(sources, list) and sources and all(isinstance(s, str) and s.strip() for s in sources)
            and len({fold(s) for s in sources}) == len(sources)):
        problems.append("source_statuses must be a non-empty list of distinct status names")
        sources = []
    target = raw.get("target_status")
    if not (isinstance(target, str) and target.strip()):
        problems.append("target_status must be a status name")
    elif fold(target) in {fold(s) for s in sources}:
        problems.append("target_status must not also be a source status")
    if problems:
        raise skip("policy-invalid", f"{path}: {'; '.join(problems)}")
    return {
        "path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "milestones": milestones,
        "source_statuses": [s.strip() for s in sources], "target_status": target.strip(),
    }


def git_root(path: Path) -> Path:
    output = run(["git", "-C", str(path), "rev-parse", "--show-toplevel"], "repository-unavailable")
    return Path(output.strip()).resolve()


def store_listing(directory: Path) -> dict[str, Any]:
    listing = run_json([str(NEXT_SELECT), "stores"], "scope-unavailable", cwd=directory)
    if not (isinstance(listing, dict) and isinstance(listing.get("workspace"), bool)
            and isinstance(listing.get("stores"), list) and listing["stores"]):
        raise skip("scope-unavailable", f"unexpected store listing from {directory}")
    return listing


def find_scope(logical: Path, physical: Path) -> tuple[str, Path, list[Any]]:
    """Use the enclosing validated workspace when this repository is registered in it."""
    for directory in upward(logical):
        if not (directory / "workspace.json").is_file():
            continue
        listing = store_listing(directory)
        if not listing["workspace"]:
            raise skip("scope-unavailable", f"{directory / 'workspace.json'} is not a validated workspace")
        members = {directory.resolve()}
        for entry in listing["stores"]:
            for field in ("directory", "repository_directory"):
                if isinstance(entry, dict) and isinstance(entry.get(field), str):
                    members.add(Path(entry[field]).resolve())
        if physical in members:
            return "workspace", directory, listing["stores"]
        break
    listing = store_listing(physical)
    return ("workspace" if listing["workspace"] else "repository"), physical, listing["stores"]


def unique_stores(entries: list[Any]) -> dict[Path, str]:
    stores: dict[Path, str] = {}
    for entry in entries:
        if not (isinstance(entry, dict) and isinstance(entry.get("directory"), str)
                and isinstance(entry.get("repository"), str)):
            raise skip("coverage-unavailable", "malformed store entry")
        if entry.get("usable") is not True:
            raise skip("coverage-unavailable",
                       f"store {entry['repository']} is unusable: {entry.get('error') or 'unknown error'}")
        stores.setdefault(Path(entry["directory"]).resolve(), entry["repository"])
    return stores


def completing_bead(bead: str, directory: Path) -> dict[str, Any]:
    rows = run_json(["bd", "-C", str(directory), "show", bead, "--readonly", "--json"], "bead-unavailable")
    matches = [row for row in rows if isinstance(row, dict) and row.get("id") == bead] if isinstance(rows, list) else []
    if len(matches) != 1:
        raise skip("bead-unavailable", f"could not read {bead} in {directory}")
    return matches[0]


def inventory(stores: dict[Path, str], reference: str) -> list[dict[str, str]]:
    associated = []
    for directory, repository in stores.items():
        rows = run_json(["bd", "-C", str(directory), "list", "--readonly", "--all", "--external-ref", reference,
                         "--limit=0", "--flat", "--json"], "coverage-unavailable")
        if not isinstance(rows, list):
            raise skip("coverage-unavailable", f"{repository} returned no issue list")
        for row in rows:
            if not (isinstance(row, dict) and isinstance(row.get("id"), str) and isinstance(row.get("status"), str)
                    and row.get("external_ref") == reference):
                raise skip("coverage-unavailable", f"{repository} returned a row without external_ref {reference}")
            associated.append({"selector": f"{repository}:{row['id']}", "id": row["id"],
                               "status": row["status"], "directory": str(directory)})
    return associated


def git_code(physical: Path, *args: str) -> int:
    try:
        return subprocess.run(["git", "-C", str(physical), *args], capture_output=True,
                              timeout=TIMEOUT_SECONDS).returncode
    except (OSError, subprocess.TimeoutExpired):
        return -1


def delivery(physical: Path, milestone: str) -> dict[str, Any]:
    if milestone != "trunk-commit":
        return {"milestone": milestone}
    try:
        head = run(["git", "-C", str(physical), "rev-parse", "--verify", "HEAD"], "head-unavailable").strip()
    except Outcome:
        return {"milestone": milestone, "head": None, "published": "unknown"}
    if git_code(physical, "rev-parse", "--verify", "--quiet", "@{upstream}"):
        published = "no-upstream"
    else:
        published = {0: "yes", 1: "no"}.get(git_code(physical, "merge-base", "--is-ancestor", "HEAD", "@{upstream}"),
                                           "unknown")
    return {"milestone": milestone, "head": head, "published": published}


def evaluate(args: argparse.Namespace, context: dict[str, Any]) -> dict[str, Any]:
    logical = logical_path(args.repo)
    try:
        physical: Path | None = git_root(logical)
    except Outcome:
        physical = None
    path = find_policy(logical, physical)
    if path is None:
        raise Outcome("disabled", "no-policy")
    policy = load_policy(path)
    context["policyPath"] = policy["path"]
    if args.milestone not in policy["milestones"]:
        raise Outcome("disabled", "milestone-not-enabled", f"{args.milestone} is not enabled by {path}")
    if args.draft:
        raise skip("draft-pr", "a draft pull request is not ready for review")
    if args.stacked:
        raise skip("stacked-pr", "the pull request does not target the default branch")
    physical = physical or git_root(logical)
    kind, root, entries = find_scope(logical, physical)
    stores = unique_stores(entries)
    context["scope"] = {"kind": kind, "root": str(root), "stores": [str(directory) for directory in stores]}
    store = Path(args.store).resolve()
    if store not in stores:
        raise skip("store-out-of-scope", f"{args.store} is not a store in the {kind} scope at {root}")
    completing = f"{stores[store]}:{args.bead}"
    context["completing"] = completing
    bead = completing_bead(args.bead, store)
    if bead.get("status") != "closed":
        raise skip("not-completed", f"{completing} is {bead.get('status')}, not closed")
    reference = bead.get("external_ref")
    key = reference[5:] if isinstance(reference, str) and reference.startswith("jira-") else ""
    if not JIRA_KEY.fullmatch(key):
        raise skip("no-association", f"{completing} has no exact jira-<KEY> external_ref")
    context["key"] = key
    if args.expected_key and args.expected_key != key:
        raise skip("association-mismatch", f"{completing} is associated with {key}, not {args.expected_key}")
    associated = inventory(stores, reference)
    if not any(row["id"] == args.bead and Path(row["directory"]) == store for row in associated):
        raise skip("coverage-unavailable", f"{completing} is missing from its own {reference} inventory")
    remaining = [row["selector"] for row in associated if row["status"] != "closed"]
    if remaining:
        context["remaining"] = remaining
        raise skip("remaining-work", f"{len(remaining)} associated bead(s) unfinished: {', '.join(remaining[:10])}")
    summary = sorted(({"selector": row["selector"], "status": row["status"]} for row in associated),
                     key=lambda row: row["selector"])
    evidence = {"key": key, "milestone": args.milestone, "policy": policy["sha256"], "policyPath": policy["path"],
                "scope": context["scope"]["stores"], "completing": completing, "associated": summary}
    return {
        "status": "ready", "key": key, "completing": completing, "associated": summary,
        "policy": {name: policy[name] for name in ("path", "source_statuses", "target_status")},
        "scope": context["scope"], "delivery": delivery(physical, args.milestone),
        "fingerprint": hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest(),
    }


def report(outcome: Outcome, context: dict[str, Any]) -> dict[str, Any]:
    return {"status": outcome.status, "reason": outcome.reason, "detail": outcome.detail, **context}


def plan(args: argparse.Namespace) -> dict[str, Any]:
    context: dict[str, Any] = {}
    try:
        return evaluate(args, context)
    except Outcome as outcome:
        return report(outcome, context)


def current_status(evidence: dict[str, Any]) -> str:
    try:
        name = evidence["issue"]["fields"]["status"]["name"]
    except (KeyError, TypeError):
        name = None
    if not isinstance(name, str) or not name.strip():
        raise skip("jira-unavailable", "issue response has no fields.status.name")
    return name.strip()


def transitions(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    raw = evidence.get("transitions")
    if isinstance(raw, dict):
        raw = raw.get("transitions")
    if not isinstance(raw, list):
        raise skip("jira-unavailable", "transitions response has no transitions list")
    for item in raw:
        try:
            identifier, target = item["id"], item["to"]["name"]
        except (KeyError, TypeError) as error:
            raise skip("jira-unavailable", "malformed transition entry") from error
        if isinstance(identifier, bool) or not isinstance(identifier, (str, int)) or not isinstance(target, str):
            raise skip("jira-unavailable", "malformed transition entry")
    return raw


def choose(ready: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    key, policy = ready["key"], ready["policy"]
    status, target = current_status(evidence), policy["target_status"]
    if fold(status) == fold(target):
        raise Outcome("noop", "already-in-target", f"{key} is already {status}")
    if fold(status) not in {fold(source) for source in policy["source_statuses"]}:
        raise skip("ineligible-status", f"{key} is {status}; policy allows {', '.join(policy['source_statuses'])}")
    candidates: dict[str, dict[str, Any]] = {}
    for item in transitions(evidence):
        if item.get("isAvailable", True) is not False and fold(item["to"]["name"]) == fold(target):
            candidates.setdefault(str(item["id"]), item)
    if not candidates:
        raise skip("no-transition", f"no available transition from {status} to {target}")
    if len(candidates) > 1:
        raise skip("ambiguous-transition", f"several transitions reach {target}: {', '.join(sorted(candidates))}")
    ((identifier, item),) = candidates.items()
    fields = item.get("fields")
    if isinstance(fields, dict):
        required = sorted(str(field.get("name") or name) for name, field in fields.items()
                          if isinstance(field, dict) and field.get("required") is True
                          and field.get("hasDefaultValue") is not True)
        if required:
            raise skip("required-fields", f"transition {identifier} requires {', '.join(required)}")
    elif fields is not None:
        raise skip("jira-unavailable", "malformed transition fields")
    elif item.get("hasScreen") is not False:
        raise skip("screen-fields-unknown", f"transition {identifier} has a screen whose fields were not read")
    name = item.get("name")
    return {
        "status": "propose", "delivery": ready["delivery"], "associated": len(ready["associated"]),
        "proposal": {"key": key, "transitionId": identifier, "transitionName": name if isinstance(name, str) else identifier,
                     "from": status, "to": item["to"]["name"], "fingerprint": ready["fingerprint"]},
    }


def decide(args: argparse.Namespace, raw_input: str) -> dict[str, Any]:
    ready = plan(args)
    if ready["status"] != "ready":
        return ready
    context = {"key": ready["key"], "completing": ready["completing"]}
    try:
        evidence = json.loads(raw_input)
        if not isinstance(evidence, dict):
            raise ValueError
    except ValueError:
        return report(skip("jira-unavailable", "stdin is not a JSON object"), context)
    try:
        result = choose(ready, evidence)
    except Outcome as outcome:
        return report(outcome, context)
    previous = evidence.get("previous")
    if isinstance(previous, dict) and isinstance(previous.get("proposal"), dict):
        previous = previous["proposal"]
    if previous is not None and previous != result["proposal"]:
        return {"status": "changed", "reason": "evidence-changed",
                "detail": "the fresh proposal differs from the approved one; do not transition",
                "previous": previous, "proposal": result["proposal"], **context}
    return result


def jira_key(value: str) -> str:
    if not JIRA_KEY.fullmatch(value):
        raise argparse.ArgumentTypeError(f"invalid Jira key: {value}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("command", choices=("plan", "decide"))
    parser.add_argument("--bead", required=True, help="completing bead ID")
    parser.add_argument("--store", required=True, help="resolver-proven store directory of the bead")
    parser.add_argument("--milestone", required=True, choices=MILESTONES)
    parser.add_argument("--repo", default=".", help="delivering repository path (logical, default cwd)")
    parser.add_argument("--expected-key", type=jira_key, help="ticket key the caller expects")
    parser.add_argument("--draft", action="store_true", help="the pull request is a draft")
    parser.add_argument("--stacked", action="store_true", help="the pull request base is not the default branch")
    args = parser.parse_args(argv)
    result = plan(args) if args.command == "plan" else decide(args, sys.stdin.read())
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
