#!/usr/bin/env python3
"""Evaluate the user-owned ~/.agents/disabled-models.json deny policy for the current directory.

The policy path is fixed and the working directory is the process cwd; no caller-supplied
path or environment override is accepted. The policy only removes routes: it never grants
consent or changes billing classification.

  disabled-models.py evaluate              JSON evaluation; exit 0, or 2 when invalid
  disabled-models.py check-direct AGENT    JSON decision; exit 0 allowed, 3 denied, 2 invalid
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

LOCAL_AGENTS = ("claude", "codex", "gemini")
MAX_BYTES = 1024 * 1024
MAX_RULES = 256
RULE_KEYS = {"id", "roots", "models", "agents", "reason"}
RULE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
MODEL_ID = re.compile(r"[^/\s]+/\S+")


class PolicyError(ValueError):
    pass


def string_list(value, label, valid):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and valid(item) for item in value):
        raise PolicyError(f"{label} must be an array of valid strings")
    return value


def parse_rules(raw):
    try:
        document = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as error:
        raise PolicyError("malformed JSON") from error
    if not isinstance(document, dict):
        raise PolicyError("policy must be an object")
    extra = sorted(set(document) - {"version", "rules"})
    if extra:
        raise PolicyError(f"unknown top-level fields: {', '.join(extra)}")
    if type(document.get("version")) is not int or document["version"] != 1:
        raise PolicyError("version must be 1")
    rules = document.get("rules")
    if not isinstance(rules, list) or len(rules) > MAX_RULES:
        raise PolicyError(f"rules must be an array of at most {MAX_RULES}")
    ids, parsed = set(), []
    for index, item in enumerate(rules, 1):
        label = f"rule {index}"
        if not isinstance(item, dict):
            raise PolicyError(f"{label} must be an object")
        extra = [key for key in item if key not in RULE_KEYS]
        if extra:
            raise PolicyError(f"{label} has unknown fields: {', '.join(extra)}")
        rule_id = item.get("id")
        if not isinstance(rule_id, str) or not RULE_ID.fullmatch(rule_id):
            raise PolicyError(f"{label} id is invalid")
        if rule_id in ids:
            raise PolicyError(f"{label} duplicates id {rule_id}")
        ids.add(rule_id)
        roots = string_list(item.get("roots"), f"{label} roots", os.path.isabs)
        if not roots:
            raise PolicyError(f"{label} roots must name at least one absolute path")
        models = string_list(item.get("models"), f"{label} models", MODEL_ID.fullmatch)
        agents = string_list(item.get("agents"), f"{label} agents", lambda agent: agent in LOCAL_AGENTS)
        if not models and not agents:
            raise PolicyError(f"{label} must deny at least one model or agent")
        reason = item.get("reason")
        if reason is not None and (not isinstance(reason, str) or not reason.strip() or len(reason) > 500):
            raise PolicyError(f"{label} reason must be a non-empty string of at most 500 characters")
        parsed.append({"id": rule_id, "roots": roots, "models": models, "agents": agents, "reason": reason})
    return parsed


def spellings(path):
    lexical = os.path.abspath(path)
    try:
        real = os.path.realpath(lexical, strict=True)
    except OSError:
        return [lexical]
    return [lexical] if real == lexical else [lexical, real]


def contains(root, path):
    return root == os.sep or path == root or path.startswith(root + os.sep)


def evaluate(home, cwd):
    path = Path(home) / ".agents" / "disabled-models.json"
    result = {"status": "missing", "path": str(path), "revision": None, "error": None,
              "matchedRules": [], "deniedModels": {}, "deniedAgents": {}}
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return result
    except OSError as error:
        return {**result, "status": "invalid", "error": f"could not read policy ({type(error).__name__})"}
    result["revision"] = hashlib.sha256(raw).hexdigest()
    if len(raw) > MAX_BYTES:
        return {**result, "status": "invalid", "error": "policy exceeds 1 MiB"}
    try:
        rules = parse_rules(raw)
    except PolicyError as error:
        return {**result, "status": "invalid", "error": str(error)}
    result["status"] = "loaded"
    locations = spellings(cwd)
    for rule in rules:
        roots = [spelling for root in rule["roots"] for spelling in spellings(root)]
        if not any(contains(root, location) for root in roots for location in locations):
            continue
        result["matchedRules"].append(rule["id"])
        detail = f"{rule['id']}: {rule['reason']}" if rule["reason"] else rule["id"]
        for model in rule["models"]:
            result["deniedModels"].setdefault(model, []).append(detail)
        for agent in rule["agents"]:
            result["deniedAgents"].setdefault(agent, []).append(detail)
    return result


def current_directory():
    try:
        return os.getcwd()
    except OSError:
        return os.environ.get("PWD", os.sep)


def main(argv):
    usage = "usage: disabled-models.py evaluate | check-direct claude|codex|gemini"
    if argv == ["evaluate"]:
        result = evaluate(Path.home(), current_directory())
        print(json.dumps(result, separators=(",", ":")))
        return 2 if result["status"] == "invalid" else 0
    if len(argv) == 2 and argv[0] == "check-direct" and argv[1] in LOCAL_AGENTS:
        policy = evaluate(Path.home(), current_directory())
        reasons = policy["deniedAgents"].get(argv[1], [])
        decision = {"route": argv[1], "allowed": policy["status"] != "invalid" and not reasons,
                    "reasons": reasons, "policy": {key: policy[key] for key in
                                                   ("status", "path", "revision", "error", "matchedRules")}}
        print(json.dumps(decision, separators=(",", ":")))
        if policy["status"] == "invalid":
            return 2
        return 3 if reasons else 0
    print(usage, file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
