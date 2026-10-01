#!/usr/bin/env python3
"""Preview selected audit changes; apply only in an attended, file-authorized terminal."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
MAX_REPORT = 8 * 1024 * 1024
MAX_CONFIG = 2 * 1024 * 1024
SOURCES = {"routerConfig", "consensusConfig", "billingPolicy"}


class Refused(Exception):
    """An input, authority or concurrent-change boundary was not satisfied."""


def spend_owner():
    path = SKILL.parent / "pi-spend/scripts/pi_spend.py"
    spec = importlib.util.spec_from_file_location("apply_migration_spend", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SPEND = spend_owner()


def audit_owner():
    path = SKILL / "scripts/migration_audit.py"
    spec = importlib.util.spec_from_file_location("apply_migration_audit", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


AUDIT = audit_owner()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def strict_load(data):
    try:
        return json.loads(data, object_pairs_hook=SPEND.strict_json_object,
                          parse_constant=SPEND.reject_json_constant)
    except (ValueError, UnicodeError) as error:
        raise Refused("invalid or duplicate-key JSON") from error


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def read_file(path, ceiling=MAX_CONFIG):
    try:
        with path.open("rb") as handle:
            data = handle.read(ceiling + 1)
    except OSError as error:
        raise Refused("target is missing or unreadable") from error
    if len(data) > ceiling:
        raise Refused("target exceeds size limit")
    return data


def pointer_parts(pointer):
    if not isinstance(pointer, str) or not pointer.startswith("/") or pointer == "/":
        raise Refused("invalid JSON pointer")
    parts = []
    for token in pointer[1:].split("/"):
        if not token or "~" in token.replace("~0", "").replace("~1", ""):
            raise Refused("invalid JSON pointer escape")
        value = token.replace("~1", "/").replace("~0", "~")
        if value == "-":
            raise Refused("array append is not a bounded change")
        parts.append(value)
    return parts


def parent_at(document, parts):
    node = document
    for token in parts[:-1]:
        try:
            node = node[int(token)] if isinstance(node, list) and token.isdecimal() else node[token]
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise Refused("JSON pointer parent does not exist") from error
        if not isinstance(node, (dict, list)):
            raise Refused("JSON pointer parent is not a container")
    last = parts[-1]
    if isinstance(node, list):
        if not last.isdecimal() or str(int(last)) != last:
            raise Refused("array index must be canonical")
        return node, int(last)
    if not isinstance(node, dict):
        raise Refused("JSON pointer parent is not an object")
    return node, last


def at(document, parts):
    node, key = parent_at(document, parts)
    try:
        return node[key]
    except (KeyError, IndexError, TypeError) as error:
        raise Refused("JSON pointer target does not exist") from error


def permitted_change(change):
    source, path, operation = (change.get(key) for key in ("source", "path", "operation"))
    parts = pointer_parts(path)
    if source == "routerConfig":
        allowed = (len(parts) == 5 and parts[:1] == ["tiers"] and parts[2] == "candidates" and
                   parts[3].isdecimal() and parts[4] == "model" and operation == "replace" and
                   isinstance(change.get("after"), str) and "/" in change["after"])
        allowed = allowed or (len(parts) in {1, 2} and parts[0] == "modelPolicies" and operation == "add" and
                              isinstance(change.get("after"), dict))
    elif source == "consensusConfig":
        allowed = (len(parts) == 5 and parts[0] == "profiles" and parts[2] in {"routes", "models"} and
                   parts[3].isdecimal() and parts[4] == "model" and operation == "replace" and
                   isinstance(change.get("after"), str))
        allowed = allowed or (len(parts) == 2 and parts[0] == "subscriptionRoutes" and
                              operation == "replace" and isinstance(change.get("after"), list) and
                              all(isinstance(model, str) and model for model in change["after"]))
    elif source == "billingPolicy":
        allowed = (len(parts) == 2 and parts[0] == "models" and "/" in parts[1] and
                   operation in {"add", "replace"} and isinstance(change.get("after"), list))
    else:
        allowed = False
    if not allowed or change.get("authorization") != "separate-current-run-required" or type(change.get("consentSensitive")) is not bool:
        raise Refused("unsupported or unauthorized change")
    return parts


def validate_change_evidence(recommendation, change, parts):
    old, new = recommendation["from"], recommendation["to"]
    evidence = recommendation["evidence"]
    source = change["source"]
    if old.startswith("local/"):
        allowed = {"consensusConfig"}
        old_value, new_value = old.split("/", 2)[2], new.split("/", 2)[2]
    elif old.startswith("openrouter/"):
        allowed = {"consensusConfig", "billingPolicy"}
        old_value, new_value = old, new
    else:
        allowed = {"routerConfig", "billingPolicy"}
        old_value, new_value = old, new
    if source not in allowed:
        raise Refused("change crosses the reviewed model route")
    if source == "billingPolicy":
        billing = evidence.get("billing")
        if not isinstance(billing, dict) or parts[1] != new:
            raise Refused("billing interval lacks matching reviewed start/classification evidence")
        expected = {"effectiveFrom": billing["effectiveFrom"], "effectiveUntil": None,
                    "billing": billing["billing"]}
        old = [] if change["operation"] == "add" else change.get("before")
        if not isinstance(old, list) or change["after"] != old + [expected]:
            raise Refused("billing change must append only the one reviewed interval")
    elif source == "routerConfig" and parts[0] == "modelPolicies":
        policy = evidence.get("routerPolicy")
        expected = {key: policy[key] for key in ("metered", "consent")} if isinstance(policy, dict) else None
        after = change["after"] if len(parts) == 2 else change["after"].get(new)
        if (expected is None or after != expected or (len(parts) == 2 and parts[1] != new) or
                (len(parts) == 1 and change["after"] != {new: expected}) or not change["consentSensitive"]):
            raise Refused("router billing/consent policy lacks matching reviewed evidence")
    elif source == "consensusConfig" and parts[0] == "subscriptionRoutes":
        if (not evidence.get("nativeAvailability") or not change["consentSensitive"] or
                not isinstance(change["before"], list) or change["after"] != change["before"] + [new_value]):
            raise Refused("subscription allowlist must retain old entries and have separate consent")
    elif change["before"] != old_value or change["after"] != new_value:
        raise Refused("model change does not match reviewed exact identities")
    if source == "consensusConfig" and old.startswith("local/") and parts[0] == "subscriptionRoutes" and parts[1] != old.split("/")[1]:
        raise Refused("subscription allowlist agent differs from reviewed route")


def apply_change(document, change, parts):
    node, key = parent_at(document, parts)
    before = change.get("before")
    if change["operation"] == "add":
        if not isinstance(node, dict) or key in node or before is not None:
            raise Refused("add would replace an existing value")
        node[key] = copy.deepcopy(change["after"])
    elif change["operation"] == "replace":
        try:
            current = node[key]
        except (KeyError, IndexError, TypeError) as error:
            raise Refused("replace target is missing") from error
        if current != before:
            raise Refused("replace precondition differs from audit preview")
        node[key] = copy.deepcopy(change["after"])
    else:
        raise Refused("unsupported operation")


def validate_billing(previous, proposed, now):
    if SPEND.parse_billing_policy(proposed).status != "complete":
        raise Refused("pi-spend owner rejected proposed billing intervals")
    for model, original in previous.get("models", {}).items():
        after = proposed.get("models", {}).get(model)
        if not isinstance(after, list) or after[:len(original)] != original:
            raise Refused("historical billing intervals may not change")
    for model, intervals in proposed.get("models", {}).items():
        originals = previous.get("models", {}).get(model, [])
        for interval in intervals[len(originals):]:
            start = SPEND.parse_utc_timestamp(interval.get("effectiveFrom"))
            if start is None or start < now:
                raise Refused("new billing interval starts in the past or is invalid")


def owner_validate(files):
    """Reuse the audit's router/panel validation and pi-spend's policy owner."""
    with tempfile.TemporaryDirectory(prefix="model-migration-validate-") as temp:
        root = Path(temp)
        paths = {}
        for item in files:
            target = root / (item["source"] + ".json")
            target.write_bytes(item["_afterBytes"])
            paths[item["source"]] = target
        cmd = [str(SKILL / "scripts/model-update-check.sh"), "--offline",
               "--router-config", str(paths["routerConfig"]),
               "--consensus-config", str(paths["consensusConfig"]),
               "--billing-policy", str(paths["billingPolicy"])]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=90, check=False)
            if result.returncode or len(result.stdout) > MAX_REPORT:
                raise Refused("owner validation failed")
            audited = strict_load(result.stdout)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Refused("owner validation unavailable") from error
        if any(audited["sources"][source]["status"] != expected for source, expected in
               (("routerConfig", "ok"), ("consensusConfig", "ok"), ("billingPolicy", "complete"))):
            raise Refused("owner validation rejected proposed configuration")


def prepare(raw, selection, *, now=None, validate=owner_validate):
    now = now or datetime.now(timezone.utc)
    if len(raw) > MAX_REPORT:
        raise Refused("audit report exceeds size limit")
    report = strict_load(raw)
    if not isinstance(report, dict) or type(report.get("schemaVersion")) is not int or report["schemaVersion"] != 2:
        raise Refused("unsupported audit schema")
    recommendations = report.get("recommendations")
    sources = report.get("sources", {})
    if not isinstance(recommendations, list) or not isinstance(sources, dict) or not selection:
        raise Refused("no selected recommendations")
    release = sources.get("releaseEvidence")
    refresh = report.get("refresh")
    if (not isinstance(release, dict) or release.get("status") != "ok" or
            not isinstance(refresh, dict) or refresh.get("status") not in {"ok", "not-requested"}):
        raise Refused("review evidence or catalog refresh is incomplete")
    if len(selection) != len(set(selection)) or any(type(i) is not int or not 1 <= i <= len(recommendations) for i in selection):
        raise Refused("invalid selection")
    grouped = {source: [] for source in SOURCES}
    selected = []
    for index in selection:
        recommendation = recommendations[index - 1]
        if (not isinstance(recommendation, dict) or recommendation.get("status") != "optional-upgrade" or
                recommendation.get("unresolved") != [] or
                recommendation.get("evidenceTrust") != "reviewed-input-not-independently-verified" or
                not isinstance(recommendation.get("changes"), list) or not recommendation["changes"]):
            raise Refused("selected recommendation is incomplete")
        evidence = recommendation.get("evidence")
        if (not isinstance(evidence, dict) or evidence.get("from") != recommendation.get("from") or
                evidence.get("to") != recommendation.get("to") or
                not AUDIT.validate_evidence({"schemaVersion": 1, "recommendations": [evidence]}, now)):
            raise Refused("selected proposal lacks valid reviewed identity, billing or availability evidence")
        if recommendation["from"].startswith("local/") and not evidence.get("nativeAvailability"):
            raise Refused("local CLI availability has not been reviewed")
        if not all(isinstance(recommendation[key], str) for key in ("from", "to")):
            raise Refused("selected model identities are invalid")
        selected.append({"index": index, "from": recommendation["from"], "to": recommendation["to"]})
        for change in recommendation["changes"]:
            if not isinstance(change, dict):
                raise Refused("malformed change")
            parts = permitted_change(change)
            validate_change_evidence(recommendation, change, parts)
            source = change["source"]
            meta = sources.get(source)
            expected = "complete" if source == "billingPolicy" else "ok"
            if not isinstance(meta, dict) or meta.get("status") != expected or change.get("config") != meta.get("path") or change.get("sourceSha256") != meta.get("sha256"):
                raise Refused("change does not match audited target")
            grouped[source].append((change, parts))
    files = []
    for source in sorted(SOURCES):
        meta = sources.get(source)
        if not isinstance(meta, dict) or meta.get("status") != ("complete" if source == "billingPolicy" else "ok"):
            raise Refused("one required target is missing or invalid")
        name = Path(meta.get("path", ""))
        if not name.is_absolute() or not name.is_file():
            raise Refused("audited target path is not a regular file")
        resolved = name.resolve(strict=True)
        original_bytes = read_file(resolved)
        original = strict_load(original_bytes)
        if not isinstance(original, dict):
            raise Refused("target config must be a JSON object")
        changes = grouped[source]
        parts_list = [parts for _, parts in changes]
        for n, left in enumerate(parts_list):
            if any(left == right[:len(left)] or right == left[:len(right)] for right in parts_list[n + 1:]):
                raise Refused("overlapping selected pointers")
        if changes:
            proposed = copy.deepcopy(original)
            current_sha = digest(original_bytes)
            if current_sha == meta["sha256"]:
                for change, parts in changes:
                    apply_change(proposed, change, parts)
                status = "pending"
            elif all(at(original, parts) == change["after"] for change, parts in changes):
                status = "already-applied"
            else:
                raise Refused("source digest changed since audit preview")
            if source == "billingPolicy":
                validate_billing(original if status == "pending" else proposed, proposed, now)
        else:
            proposed = original
            status = "unchanged"
        # Structural identity is guaranteed by applying only the selected pointers to a deep copy.
        after_bytes = (json.dumps(proposed, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
        if status in {"already-applied", "unchanged"}:
            after_bytes = original_bytes
        mode = stat.S_IMODE(resolved.stat().st_mode)
        files.append({"source": source, "config": str(name), "realPath": str(resolved),
                      "sourceSha256": meta["sha256"], "currentSha256": digest(original_bytes),
                      "afterSha256": digest(after_bytes), "status": status,
                      "unrelatedUnchanged": None if status == "already-applied" else True, "mode": mode,
                      "changes": [change for change, _ in changes], "_afterBytes": after_bytes})
    validate(files)
    record = {"reportSha256": digest(raw), "selected": selected,
              "files": [{key: row[key] for key in ("source", "config", "realPath", "sourceSha256", "currentSha256", "afterSha256", "status", "changes")}
                        for row in files]}
    return {"digest": digest(canonical(record)), "reportSha256": digest(raw), "selected": selected,
            "consentSensitive": any(change["consentSensitive"] for row in files for change in row["changes"]),
            "files": files}


def atomic_write(path, data, mode):
    descriptor, name = tempfile.mkstemp(prefix=".model-migration-", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def backup_root_ready(root, paths):
    if root.is_symlink():
        raise Refused("backup root is a symlink")
    resolved = root.resolve()
    if any(resolved == path.parent or resolved.is_relative_to(path.parent) for path in paths):
        raise Refused("backups must live outside target directories")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    if root.is_symlink() or stat.S_IMODE(root.stat().st_mode) & 0o077:
        raise Refused("backup root is not private")
    return root


def backup_all(root, files):
    run = Path(tempfile.mkdtemp(prefix="run-", dir=root))
    records = []
    for row in files:
        file = run / (row["source"] + "-" + row["currentSha256"] + ".json")
        data = read_file(Path(row["realPath"]))
        if digest(data) != row["currentSha256"]:
            raise Refused("target changed before backups completed")
        descriptor = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        records.append({"source": row["source"], "target": row["realPath"], "sha256": row["currentSha256"], "backup": str(file)})
    manifest = run / "manifest.json"
    descriptor = os.open(manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical(records))
        handle.flush()
        os.fsync(handle.fileno())
    directory_fd = os.open(run, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return {row["source"]: row["backup"] for row in records}


def apply_plan(plan, backup_root, *, allowed, confirm, writer=atomic_write, validate=owner_validate):
    files = plan["files"]
    required = {Path(row["realPath"]) for row in files if row["status"] == "pending"}
    if not required <= {Path(path) for path in allowed}:
        raise Refused("explicit file authority is missing")
    if not confirm(plan):
        raise Refused("exact preview approval declined")
    for row in files:
        path = Path(row["config"])
        if not path.is_file() or path.resolve(strict=True) != Path(row["realPath"]) or digest(read_file(path)) != row["currentSha256"]:
            raise Refused("target changed after approval; no writes performed")
    for row in files:
        if row["source"] == "billingPolicy" and row["status"] == "pending":
            for change in row["changes"]:
                for interval in change["after"][len(change.get("before") or []):]:
                    if SPEND.parse_utc_timestamp(interval["effectiveFrom"]) < datetime.now(timezone.utc):
                        raise Refused("billing start is now in the past; regenerate the preview")
    validate(files)
    if not required:
        return {"status": "already-applied", "files": [{"source": row["source"], "status": row["status"], "backup": None} for row in files]}
    root = backup_root_ready(Path(backup_root), required)
    try:
        backups = backup_all(root, [row for row in files if row["status"] == "pending"])
    except (OSError, Refused) as error:
        raise Refused("backups could not be completed; no targets were written") from error
    outcomes = [{"source": row["source"], "status": "not-attempted" if row["status"] == "pending" else row["status"],
                 "backup": backups.get(row["source"])} for row in files]
    for row, outcome in zip(files, outcomes, strict=True):
        if row["status"] != "pending":
            continue
        try:
            path = Path(row["config"])
            if path.resolve(strict=True) != Path(row["realPath"]) or digest(read_file(path)) != row["currentSha256"]:
                raise Refused("target changed during application")
            writer(Path(row["realPath"]), row["_afterBytes"], row["mode"])
            if digest(read_file(path)) != row["afterSha256"]:
                raise Refused("post-write content differs from approved preview")
            outcome["status"] = "applied"
        except (OSError, Refused) as error:
            outcome["status"] = "failed"
            try:
                observed = digest(read_file(Path(row["realPath"])))
                outcome["changed"] = observed != row["currentSha256"]
                outcome["observedSha256"] = observed
            except Refused:
                outcome["changed"] = "unavailable"
            return {"status": "partial", "files": outcomes, "error": str(error),
                    "recovery": "Review the private backups; recovery requires separate authorization. No rollback was attempted."}
    return {"status": "applied", "files": outcomes,
            "recovery": "Private backups retained; no automatic rollback."}


def visible(plan):
    return {key: ([{k: v for k, v in row.items() if not k.startswith("_")} for row in value]
                  if key == "files" else value)
            for key, value in plan.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="bounded audit JSON file, or - for preview stdin")
    parser.add_argument("--select", type=int, action="append", required=True, help="1-based recommendation index")
    parser.add_argument("--apply", action="store_true", help="attended application; never implied by a preview")
    parser.add_argument("--allow-target", action="append", default=[], help="exact canonical path with separate file authority")
    parser.add_argument("--backup-root", default=str(Path.home() / ".local/state/model-update-check/backups"))
    args = parser.parse_args()
    try:
        if args.report == "-" and args.apply:
            raise Refused("attended apply requires a report file; stdin is reserved for approval")
        raw = sys.stdin.buffer.read(MAX_REPORT + 1) if args.report == "-" else read_file(Path(args.report), MAX_REPORT)
        plan = prepare(raw, args.select)
        print(json.dumps(visible(plan), indent=2))
        if not args.apply:
            return 0
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise Refused("apply requires an interactive terminal; no --yes or noninteractive bypass")
        def confirm(bound):
            if input("Type the complete preview digest to approve these exact files and changes: ").strip() != bound["digest"]:
                return False
            if bound["consentSensitive"] and input("Type CONSENT followed by the same digest for allowlist/policy changes: ").strip() != "CONSENT " + bound["digest"]:
                return False
            return True
        outcome = apply_plan(plan, Path(args.backup_root), allowed={Path(path) for path in args.allow_target}, confirm=confirm)
        if outcome["status"] == "applied":
            commands = [str(SKILL / "scripts/model-update-check.sh"), "--offline"]
            for key, source in (("--router-config", "routerConfig"), ("--consensus-config", "consensusConfig"), ("--billing-policy", "billingPolicy")):
                commands.extend([key, next(row["config"] for row in plan["files"] if row["source"] == source)])
            try:
                audit = subprocess.run(commands, capture_output=True, timeout=90, check=False)
                statuses = strict_load(audit.stdout).get("sources", {}) if audit.returncode == 0 and len(audit.stdout) <= MAX_REPORT else {}
                outcome["audit"] = {source: statuses.get(source, {}).get("status", "unavailable") for source in SOURCES}
            except (OSError, subprocess.TimeoutExpired, Refused):
                outcome["audit"] = {source: "unavailable" for source in SOURCES}
            if (outcome["audit"].get("routerConfig") != "ok" or
                    outcome["audit"].get("consensusConfig") != "ok" or
                    outcome["audit"].get("billingPolicy") != "complete"):
                outcome["status"] = "applied-unverified"
        print(json.dumps(outcome, indent=2))
        return 0 if outcome["status"] in {"applied", "already-applied"} and all(value == "ok" if key != "billingPolicy" else value == "complete" for key, value in outcome.get("audit", {}).items()) else 2
    except Refused as error:
        print(json.dumps({"status": "refused", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
