#!/usr/bin/env python3
"""Reduce feedback to bounded dashboard state; optionally collect internally without files."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

MAX_REQUESTS = 200
MAX_RECORDS = 500
MAX_INPUT_BYTES = 16_000_000


def reduce_feedback(payload: dict) -> dict:
    keys = payload.get("keys", [])
    if not isinstance(keys, list) or len(keys) > MAX_REQUESTS or not all(isinstance(key, str) for key in keys):
        raise ValueError("invalid or oversized request scope")
    previous = payload.get("previous", {})
    if not isinstance(previous, dict):
        raise ValueError("invalid feedback state")
    state = {key: previous.get(key, {}) for key in keys}
    for records in state.values():
        if not isinstance(records, dict) or len(records) > MAX_RECORDS:
            raise ValueError("invalid or oversized feedback state")
        for identity, observation in records.items():
            if (not isinstance(identity, str) or not isinstance(observation, dict)
                    or set(observation) != {"updatedAt", "stateKey"}
                    or not all(value is None or isinstance(value, str) for value in observation.values())):
                raise ValueError("invalid feedback observation")
    summaries = {key: {"complete": False, "threads": None, "conversationCount": None,
                       "latestConversation": None, "candidateCount": None} for key in keys}
    deltas = []
    errors = []
    seen = set()
    for inventory in payload.get("inventories", []):
        repository = inventory.get("repository")
        inventory_keys = {f"{repository}#{number}" for number in inventory.get("pullRequests", [])}
        if not inventory_keys.issubset(set(keys)) or seen & inventory_keys:
            raise ValueError("feedback inventory is outside scope or duplicated")
        seen.update(inventory_keys)
        errors.extend(inventory.get("errors", []))
        for key in inventory_keys:
            records = [record for record in inventory.get("records", [])
                       if f'{record.get("repository")}#{record.get("pr")}' == key]
            complete = not inventory.get("partial", True) and len(records) <= MAX_RECORDS
            if len(records) > MAX_RECORDS:
                errors.append({"source": "state", "key": key, "kind": "capacity"})
            old = state[key]
            current = {} if complete else dict(old)
            threads = set()
            conversations = []
            candidates = 0
            for record in records:
                identity = record.get("identity")
                if not isinstance(identity, str):
                    raise ValueError("feedback identity is missing")
                if identity not in current and len(current) >= MAX_RECORDS:
                    complete = False
                    errors.append({"source": "state", "key": key, "kind": "capacity"})
                    continue
                observation = {field: record.get(field) for field in ("updatedAt", "stateKey")}
                if not all(value is None or isinstance(value, str) for value in observation.values()):
                    raise ValueError("invalid feedback record observation")
                prior = old.get(identity)
                change = None
                if prior is None:
                    change = "new"
                elif str(observation["updatedAt"] or "") > str(prior.get("updatedAt") or ""):
                    change = "edited"
                elif observation["stateKey"] != prior.get("stateKey"):
                    change = "state"
                candidate = record.get("actionability") == "candidate"
                if change:
                    deltas.append({"key": key, "identity": identity, "change": change,
                                   "candidate": candidate, "author": record.get("author"),
                                   "source": record.get("source"),
                                   "gist": str(record.get("gist") or "")[:160]})
                current[identity] = observation
                if record.get("source") == "inline_review" and record.get("lifecycle") == "unresolved":
                    if record.get("threadId"):
                        threads.add(record["threadId"])
                if record.get("source") == "conversation":
                    conversations.append(record)
                candidates += int(candidate)
            state[key] = current
            latest = max(conversations, key=lambda record: str(record.get("updatedAt") or ""), default=None)
            summaries[key] = {"complete": complete, "threads": len(threads),
                              "conversationCount": len(conversations), "candidateCount": candidates,
                              "latestConversation": ({field: latest.get(field) for field in
                                                       ("author", "updatedAt")} if latest else None)}
        if any(f'{record.get("repository")}#{record.get("pr")}' not in inventory_keys
               for record in inventory.get("records", [])):
            raise ValueError("feedback record is outside inventory scope")
    return {"summaries": summaries, "deltas": deltas, "errors": errors, "state": state}


def run_collector(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess:
    with subprocess.Popen(
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def collect_feedback(payload: dict, deadline: datetime | None = None) -> dict:
    if os.name != "posix":
        raise ValueError("collect mode requires POSIX process groups")
    if set(payload) - {"keys", "previous"}:
        raise ValueError("collect mode accepts only keys and previous state")
    reduce_feedback(payload)  # Validate state and caps before any network access.
    keys = payload.get("keys", [])
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate request scope")
    if deadline is not None and deadline.utcoffset() is None:
        raise ValueError("deadline must include a timezone")
    groups: dict[str, list[int]] = {}
    for key in keys:
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+)#([1-9][0-9]{0,9})", key)
        if not match or match[1].split("/")[1] in {".", ".."} or int(match[2]) > 2_147_483_647:
            raise ValueError("invalid qualified request key")
        groups.setdefault(match[1], []).append(int(match[2]))
    collector = Path(__file__).resolve().parents[2] / "pr-status/scripts/gh-pr-feedback.py"
    inventories = []
    for repository, numbers in groups.items():
        timeout = min(120, (deadline - datetime.now(timezone.utc)).total_seconds()) if deadline else 120
        failure = None
        if timeout <= 0:
            failure = "deadline"
        else:
            owner, repo = repository.split("/")
            try:
                completed = run_collector(
                    [sys.executable, str(collector), owner, repo, *map(str, numbers),
                     "--body-limit", "200", "--max-source-items", "100", "--max-records-per-pr", "500"],
                    timeout=timeout,
                )
                if completed.returncode:
                    raise ValueError("collector failed")
                if len(completed.stdout.encode()) > MAX_INPUT_BYTES:
                    raise ValueError("collector output exceeded byte limit")
                inventory = json.loads(completed.stdout)
                if (not isinstance(inventory, dict) or inventory.get("schemaVersion") != 1
                        or inventory.get("repository") != repository
                        or inventory.get("pullRequests") != numbers
                        or not isinstance(inventory.get("partial"), bool)
                        or not isinstance(inventory.get("errors"), list)
                        or not isinstance(inventory.get("records"), list)
                        or "recordFormat" in inventory):
                    raise ValueError("invalid full feedback inventory")
                reduce_feedback({"keys": [f"{repository}#{n}" for n in numbers], "inventories": [inventory]})
                inventories.append(inventory)
            except subprocess.TimeoutExpired:
                failure = "timeout"
            except (OSError, ValueError, TypeError, AttributeError):
                failure = "collector"
        if failure:
            inventories.append({
                "repository": repository, "pullRequests": numbers, "records": [], "partial": True,
                "errors": [{"repository": repository, "source": "feedback", "kind": failure,
                            "message": "Feedback collection incomplete; prior state retained"}],
            })
    result = reduce_feedback({**payload, "inventories": inventories})
    result["deadlineReached"] = deadline is not None and datetime.now(timezone.utc) >= deadline
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", action="store_true", help="fetch scoped inventories and reduce internally")
    parser.add_argument("--deadline", help="immutable watch deadline (ISO-8601 with timezone)")
    args = parser.parse_args()
    if args.deadline is not None:
        if not args.collect:
            parser.error("--deadline requires --collect")
        try:
            args.deadline = datetime.fromisoformat(args.deadline.replace("Z", "+00:00"))
            if args.deadline.utcoffset() is None:
                raise ValueError("timezone missing")
        except ValueError:
            parser.error("--deadline must be ISO-8601 with a timezone")
    return args


def main() -> int:
    args = parse_args()
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("feedback input exceeded byte limit")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("feedback input must be an object")
        result = collect_feedback(payload, args.deadline) if args.collect else reduce_feedback(payload)
    except (ValueError, TypeError, AttributeError) as error:
        json.dump({"status": "failed", "error": str(error)}, sys.stdout)
        sys.stdout.write("\n")
        return 1
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
