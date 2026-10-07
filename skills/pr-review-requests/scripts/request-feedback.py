#!/usr/bin/env python3
"""Reduce fetched feedback to bounded session-local dashboard state; no I/O except JSON."""
from __future__ import annotations

import json
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


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("feedback input exceeded byte limit")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("feedback input must be an object")
        result = reduce_feedback(payload)
    except (ValueError, TypeError, AttributeError) as error:
        json.dump({"status": "failed", "error": str(error)}, sys.stdout)
        sys.stdout.write("\n")
        return 1
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
