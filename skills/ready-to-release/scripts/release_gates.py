"""One read-only release authority. Python 3.10+, standard library only."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
from datetime import datetime, timezone


LIMIT = 1024 * 1024
NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*")
HEADER = "service|unpushed|uncommitted|ci|ciBranch|gitBranch|head|deploy|tag|age|ciRevision|ciExpectedRevision"
SOURCES = ("digest", "order", "contracts", "manifest", "state")
HARD_CONTRACTS = {"STALE", "DIFFERS", "MISSING_PROVIDER", "UNCOMMITTED", "NOT_BUILT", "NOT_SYNCED"}
SENTINELS = {"", "-", "unknown", "notfound", "not-applicable"}


def unavailable(reason, status="unavailable"):
    return {"status": status, "reason": reason}


def read_evidence(path):
    try:
        with path.open("rb") as handle:
            data = handle.read(LIMIT + 1)
        if len(data) > LIMIT:
            return unavailable("evidence exceeds size limit")
        return {"status": "ok", "text": data.decode("utf-8")}
    except FileNotFoundError:
        return unavailable("not present", "absent")
    except (OSError, UnicodeError):
        return unavailable("evidence unreadable")


def collect_command(root, name, args, timeout):
    command = root / "scripts" / name
    if not command.is_file():
        return unavailable(f"{name} adapter missing", "absent")
    try:
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen([str(command), *args], cwd=root, stdout=output,
                                       stderr=subprocess.DEVNULL, start_new_session=True,
                                       env={**os.environ, "RELEASE_PROJECT_ROOT": str(root)})
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                return unavailable(f"{name} timeout")
            if code:
                return unavailable(f"{name} exited {code}")
            output.seek(0)
            data = output.read(LIMIT + 1)
            if len(data) > LIMIT:
                return unavailable(f"{name} output exceeds size limit")
            return {"status": "ok", "text": data.decode("utf-8")}
    except (OSError, UnicodeError):
        return unavailable(f"{name} cannot provide evidence")


def collect(root):
    try:
        timeout = min(120, max(1, int(os.environ.get("RELEASE_GATES_TIMEOUT", "20"))))
    except ValueError:
        timeout = 20
    return {
        "schemaVersion": 1,
        "digest": collect_command(root, "release-digest", [], timeout),
        "order": collect_command(root, "release-order", [], timeout),
        "contracts": collect_command(root, "contract-check", ["all"], timeout),
        "manifest": read_evidence(root / "docs" / "release-manifest.yaml"),
        "state": read_evidence(root / ".release-state.json"),
    }


def source_text(source):
    if source["status"] != "ok":
        raise ValueError(source.get("reason", "evidence unavailable"))
    return source["text"]


def sections(text):
    result = {}
    current = None
    for line in text.splitlines():
        if re.fullmatch(r"---[A-Z]+---", line):
            if line in result:
                raise ValueError("duplicate evidence section")
            current = line
            result[current] = []
        elif line.strip() and not line.lstrip().startswith("#"):
            if current is None:
                raise ValueError("evidence outside a section")
            result[current].append(line)
    return result


def metadata(lines):
    result = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if not separator or key in result:
            raise ValueError("invalid metadata")
        result[key] = value
    return result


def parse_digest(text):
    parts = sections(text)
    meta = metadata(parts.get("---META---", []))
    if not NAME.fullmatch(meta.get("ciProvider", "")) or meta.get("ci") not in {"available", "partial", "unavailable"}:
        raise ValueError("missing or malformed CI metadata")
    rows = parts.get("---SERVICES---", [])
    if not rows or rows[0] != HEADER:
        raise ValueError("missing or malformed services header")
    services = {}
    for line in rows[1:]:
        fields = line.split("|")
        if len(fields) != len(HEADER.split("|")):
            raise ValueError("malformed service row")
        row = dict(zip(HEADER.split("|"), fields, strict=True))
        name = row["service"]
        if not NAME.fullmatch(name) or name in services:
            raise ValueError("invalid or duplicate service")
        if not re.fullmatch(r"\d+", row["unpushed"]) or row["uncommitted"] not in {"true", "false"}:
            raise ValueError("invalid Git evidence")
        row["unpushed"] = int(row["unpushed"])
        row["uncommitted"] = row["uncommitted"] == "true"
        services[name] = row
    toggles = {}
    for line in parts.get("---TOGGLES---", []):
        key, separator, value = line.partition("=")
        if not separator or not NAME.fullmatch(key):
            raise ValueError("malformed toggle observation")
        toggles[key] = value if key not in toggles and value in {"true", "false"} else "unknown"
    return meta, services, toggles


def parse_order(text):
    parts = sections(text)
    source = metadata(parts.get("---SOURCE---", []))
    provider = source.get("provider")
    sources = {"none": {"none"}, "manifest": {"manual"}, "pact": {"generated", "live", "manual"}}
    if provider not in sources or source.get("graph") not in sources[provider] or "---GRAPH---" not in parts or not parts.get("---DRIFT---"):
        raise ValueError("missing or malformed order evidence")
    graph = {}
    for line in parts["---GRAPH---"]:
        match = re.fullmatch(r"([^:]+):\s*\[([^]]*)\]\s*", line)
        if not match or not NAME.fullmatch(match[1]) or match[1] in graph:
            raise ValueError("malformed dependency graph")
        names = [name.strip() for name in match[2].split(",") if name.strip()]
        if any(not NAME.fullmatch(name) for name in names):
            raise ValueError("malformed prerequisite name")
        graph[match[1]] = names
    if provider == "none" and graph:
        raise ValueError("none provider with nonempty graph")
    return provider, graph, parts["---DRIFT---"]


def strip_comment(line):
    quote = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
        elif char == "\\" and quote == '"':
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index].rstrip()
    if quote:
        raise ValueError("unterminated policy scalar")
    return line.rstrip()


def scalar(value):
    value = value.strip()
    if value.startswith('"'):
        result = json.loads(value)
        if not isinstance(result, str):
            raise ValueError("policy scalar must be text")
        return result
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if not value or value[0] in "&*!|>{[" or value in {"null", "~"}:
        raise ValueError("unsupported policy scalar; use plain or quoted text")
    return value


def name_list(value):
    if not value.startswith("[") or not value.endswith("]"):
        raise ValueError("policy list must use [name, ...] or block-list syntax")
    result = [scalar(item) for item in value[1:-1].split(",") if item.strip()]
    if any(not NAME.fullmatch(name) for name in result):
        raise ValueError("invalid name in policy list")
    return result


def parse_policy(text):
    """Parse only the documented policy subset, never pretend to parse general YAML."""
    policy = {"ignore": [], "non_deploying": [], "toggles": {}, "parked": {}}
    seen = set()
    section = None
    entry = None
    inline = False
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw[:len(raw) - len(raw.lstrip())] or raw.lstrip().startswith("<<:"):
            raise ValueError("unsupported policy indentation or merge key")
        if not raw.startswith(" "):
            section = None
            key, separator, value = strip_comment(raw).partition(":")
            key = key.strip()
            if key.strip("\"'") in policy and key not in policy:
                raise ValueError("readiness policy keys must be unquoted")
            if key not in policy:
                continue
            if not separator or key in seen:
                raise ValueError("invalid or duplicate policy section")
            seen.add(key)
            section, entry, inline = key, None, bool(value.strip())
            if inline:
                if isinstance(policy[key], list):
                    policy[key] = name_list(value.strip())
                elif value.strip() != "{}":
                    raise ValueError("toggle policy requires a block map")
            continue
        if section is None:
            if raw.lstrip().partition(":")[0] in policy:
                raise ValueError("readiness policy sections must be top-level")
            continue
        line = strip_comment(raw)
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        if not body:
            continue
        if inline or "\t" in raw:
            raise ValueError("unsupported policy indentation")
        if isinstance(policy[section], list):
            if indent != 2 or not body.startswith("- "):
                raise ValueError("policy list requires two-space block entries")
            name = scalar(body[2:])
            if not NAME.fullmatch(name):
                raise ValueError("invalid policy name")
            policy[section].append(name)
        elif indent == 2:
            key, separator, value = body.partition(":")
            if not separator or not NAME.fullmatch(key) or key in policy[section] or value.strip() not in {"", "{}"}:
                raise ValueError("invalid toggle policy entry")
            entry = key
            policy[section][entry] = {}
        elif indent == 4 and entry is not None:
            key, separator, value = body.partition(":")
            if not separator or not NAME.fullmatch(key) or key in policy[section][entry]:
                raise ValueError("invalid toggle policy field")
            policy[section][entry][key] = scalar(value)
        else:
            raise ValueError("unsupported policy shape")
    for entry in policy["toggles"].values():
        if not NAME.fullmatch(entry.get("service", "")) or entry.get("status", "active") not in {"active", "parked", "dark-release"}:
            raise ValueError("toggle service/status policy is invalid")
    return policy


def parse_contracts(text):
    reports = {
        "## Staleness Report": {"stale": {"STALE", "DIFFERS"}, "ok": {"OK"}, "missing_provider": {"MISSING_PROVIDER"}},
        "## Uncommitted Pact Files": {"uncommitted": {"UNCOMMITTED"}},
        "## Sync Coverage (consumer test → built pact → provider)": {"ok": {"OK"}, "not_built": {"NOT_BUILT"}, "not_synced": {"NOT_SYNCED"}},
        "## CI Verification Coverage": {"ok": {"OK"}, "gaps": {"GAP"}},
    }
    matrix = "## Contract Relationship Matrix"
    headings, summaries, counts = set(), {}, {}
    known, findings = set(), {}
    section, matrix_rows, matrix_total = None, 0, None
    relationships, unnamed_gaps = set(), set()
    complete = "status=error" not in text
    for line in text.splitlines():
        if line.startswith("## "):
            if line in headings:
                complete = False
            headings.add(line)
            section = line
            counts.setdefault(section, {})
            continue
        if line.startswith("SUMMARY"):
            if section in summaries:
                complete = False
            summaries[section] = dict(re.findall(r"(\w+)=(\d+)(?:\s|$)", line))
        total = re.fullmatch(r"TOTAL\s+(\d+) relationships", line)
        if total:
            if matrix_total is not None or section != matrix:
                complete = False
            matrix_total = int(total[1])
        match = re.match(r"^(OK|STALE|DIFFERS|MISSING_PROVIDER|UNCOMMITTED|NOT_BUILT|NOT_SYNCED|GAP)\s+(\S+)(?:\s+->\s+(\S+))?", line)
        if match:
            kind, first, second = match.groups()
            names = [first] + ([second] if second else [])
            if any(not NAME.fullmatch(name) for name in names) or section not in reports:
                complete = False
                continue
            counts[section][kind] = counts[section].get(kind, 0) + 1
            if second:
                relationships.add((first, second))
            if kind == "GAP":
                unverified = re.search(r"\bnot-verified=(\S+)", line)
                if unverified:
                    consumers = unverified[1].split(",")
                    if any(not NAME.fullmatch(name) for name in consumers):
                        complete = False
                    else:
                        names.extend(consumers)
                else:
                    unnamed_gaps.add(first)
            known.update(names)
            for name in names:
                if kind != "OK":
                    findings.setdefault(name, []).append(kind)
        elif line.startswith("|"):
            fields = [field.strip() for field in line.split("|")[1:-1]]
            if len(fields) == 3 and fields[2] in {"consumer", "provider", "consumer provider"}:
                if section != matrix or any(not NAME.fullmatch(name) for name in fields[:2]):
                    complete = False
                    continue
                matrix_rows += 1
                relationships.add(tuple(fields[:2]))
                known.update(fields[:2])
    for consumer, provider in relationships:
        if provider in unnamed_gaps:
            findings.setdefault(consumer, []).append("GAP")
    complete = complete and headings == {*reports, matrix} and matrix_total == matrix_rows
    for heading, mapping in reports.items():
        summary = summaries.get(heading, {})
        for field, kinds in mapping.items():
            observed = sum(counts.get(heading, {}).get(kind, 0) for kind in kinds)
            if field not in summary or int(summary[field]) != observed:
                complete = False
    return known, findings, complete


def deployment(value):
    if value == "cron":
        return "settled"
    if value == "cron:rollout":
        return "rolling"
    match = re.fullmatch(r"(\d+)/(\d+)", value)
    if match and int(match[2]) > 0 and int(match[1]) <= int(match[2]):
        return "settled" if match[1] == match[2] else "rolling"
    return "unknown"


def rollout(row, watches):
    live = deployment(row["deploy"])
    watch = watches.get(row["service"])
    if not isinstance(watch, dict):
        return "rolling" if live == "rolling" else "none"
    baseline = watch.get("fromTag")
    if live == "unknown" or not baseline or baseline == "-" or row["tag"] in {"-", "unknown", "notfound", ""}:
        return "unknown"
    if live == "settled" and row["tag"] != baseline:
        return "confirmed"
    return "rolling"


def gate(result, *evidence):
    return {"result": result, "evidence": list(evidence)}


def verdict(gates):
    results = {item["result"] for item in gates.values()}
    return "NOT READY" if "block" in results else "HOLD" if "hold" in results else "READY"


def validate_snapshot(data):
    if not isinstance(data, dict) or set(data) != {"schemaVersion", *SOURCES} or type(data["schemaVersion"]) is not int or data["schemaVersion"] != 1:
        raise ValueError("unsupported snapshot schema")
    for name in SOURCES:
        item = data[name]
        if not isinstance(item, dict) or set(item) - {"status", "text", "reason"} or item.get("status") not in {"ok", "absent", "unavailable"}:
            raise ValueError("invalid evidence envelope")
        if item["status"] == "ok" and (not isinstance(item.get("text"), str) or len(item["text"].encode()) > LIMIT):
            raise ValueError("invalid or oversized evidence text")
        if "reason" in item and not isinstance(item["reason"], str):
            raise ValueError("invalid evidence reason")


def evaluate(data, selected=None):
    result = {"schemaVersion": 1, "observedAt": datetime.now(timezone.utc).isoformat(), "context": "unknown", "drift": [], "services": [], "errors": [], "verdict": "HOLD"}
    try:
        validate_snapshot(data)
        meta, services, toggles = parse_digest(source_text(data["digest"]))
    except (ValueError, KeyError) as error:
        result["errors"].append(str(error))
        return result
    result["context"] = meta.get("context", "unknown")
    errors = {}
    try:
        policy = parse_policy("") if data["manifest"]["status"] == "absent" else parse_policy(source_text(data["manifest"]))
        if any(entry["service"] not in services and entry.get("status", "active") == "active" and flag not in policy["parked"] for flag, entry in policy["toggles"].items()):
            raise ValueError("active flag policy names a missing service")
    except ValueError as error:
        policy = parse_policy("")
        errors["policy"] = str(error)
    try:
        provider, graph, drift = parse_order(source_text(data["order"]))
    except ValueError as error:
        provider, graph, drift = "unknown", {}, []
        errors["order"] = str(error)
    result["drift"] = [line for line in drift if line.startswith(("new:", "removed:", "status: unmanaged"))]
    try:
        known, findings, complete = parse_contracts(source_text(data["contracts"]))
        if not complete:
            errors["contracts"] = "contract-check all is incomplete or inconsistent"
    except ValueError as error:
        known, findings = set(), {}
        errors["contracts"] = str(error)
    if provider == "pact":
        known.update(graph)
        known.update(name for names in graph.values() for name in names)
    watches = {}
    if data["state"]["status"] == "ok":
        try:
            state = json.loads(data["state"]["text"])
            if not isinstance(state, dict) or not isinstance(state.get("rolloutWatch", {}), dict):
                raise ValueError("invalid state")
            watches = state.get("rolloutWatch", {})
            if any(not isinstance(entry, dict) or not isinstance(entry.get("sha"), str)
                   or entry["sha"] in SENTINELS or "fromTag" not in entry
                   or (entry["fromTag"] is not None and not isinstance(entry["fromTag"], str))
                   for entry in watches.values()):
                raise ValueError("invalid rollout entry")
        except ValueError:
            watches = {}
            errors["state"] = "saved rollout state malformed; evidence required"
    elif data["state"]["status"] == "unavailable":
        errors["state"] = "saved rollout state unreadable; evidence required"
    result["errors"].extend(f"{source}: {reason}" for source, reason in errors.items())
    if selected and selected not in services:
        result["errors"].append("requested service absent from full digest")
        return result
    for name, row in services.items():
        if name in policy["ignore"] or (selected and selected != name):
            continue
        gates = {}
        notes = []
        non_deploying = name in policy["non_deploying"]
        gates["work"] = gate("block", "nothing to release") if row["unpushed"] == 0 else gate("hold", "uncommitted work") if row["uncommitted"] else gate("pass", f"{row['unpushed']} unpushed at {row['head']}")
        if row["head"] in SENTINELS and row["unpushed"] > 0:
            gates["work"] = gate("hold", "local head unavailable")
        exact = (row["ciBranch"] == row["gitBranch"] and row["ciBranch"] not in SENTINELS
                 and row["ciRevision"] not in SENTINELS and row["ciRevision"] == row["ciExpectedRevision"]
                 and meta["ci"] != "unavailable" and meta["ciProvider"] in {"circleci", "github-actions", "cloud-build"})
        ci = row["ci"] if exact else "unknown"
        gates["ci"] = gate("na", "non-deploying repository") if non_deploying else gate("pass" if ci == "success" else "block" if ci in {"failed", "error"} else "hold", f"exact upstream CI: {ci}")
        if ci == "success" and not non_deploying:
            notes.append("upstream green does not verify unpushed candidate commits")
        issues = findings.get(name, [])
        if any(issue in HARD_CONTRACTS for issue in issues):
            gates["contracts"] = gate("block", *issues)
        elif "GAP" in issues:
            gates["contracts"] = gate("hold", "contract coverage GAP")
        elif "contracts" in errors and (name in known or data["contracts"]["status"] != "absent"):
            gates["contracts"] = gate("hold", errors["contracts"])
        else:
            gates["contracts"] = gate("pass", "applicable contracts clean") if name in known else gate("na", "no known contract relationship")
        if non_deploying:
            gates["order"] = gate("na", "non-deploying repository")
        elif "order" in errors:
            gates["order"] = gate("hold", errors["order"])
        else:
            waiting, unknown = [], []
            for prerequisite in graph.get(name, []):
                other = services.get(prerequisite)
                if not other:
                    unknown.append(prerequisite)
                elif other["unpushed"] > 0 or rollout(other, watches) == "rolling":
                    waiting.append(prerequisite)
                elif other["uncommitted"] or deployment(other["deploy"]) != "settled" or rollout(other, watches) == "unknown":
                    unknown.append(prerequisite)
            gates["order"] = gate("block", "waiting on " + ", ".join(waiting)) if waiting else gate("hold", "prerequisite evidence unsettled: " + ", ".join(unknown)) if unknown else gate("na" if provider == "none" else "pass", "no ordering configured" if provider == "none" else "prerequisites settled")
        active, missing = [], []
        for flag, entry in policy["toggles"].items():
            if entry["service"] != name:
                continue
            status = "parked" if flag in policy["parked"] else entry.get("status", "active")
            if status in {"parked", "dark-release"}:
                notes.append(f"{flag}: {status}; activation is a manual decision")
            else:
                active.append(flag)
                if toggles.get(flag) not in {"true", "false"}:
                    missing.append(flag)
                elif toggles[flag] == "false":
                    notes.append(f"{flag}: false; activation follow-up — {entry.get('flip_when', 'validate before enabling')}")
        gates["toggle"] = gate("hold", "declared flag evidence missing: " + ", ".join(missing)) if missing else gate("pass" if active else "na", "flag state observed; activation is separate" if active else "no active toggle gate")
        progress = rollout(row, watches)
        live = deployment(row["deploy"])
        gates["deployment"] = gate("na", "non-deploying repository") if non_deploying else gate("hold", "rollout in progress") if progress == "rolling" else gate("hold", "saved rollout needs deployment evidence or explicit acknowledgement") if progress == "unknown" else gate("pass", row["deploy"], row["tag"], row["age"]) if live == "settled" else gate("na", "deployment evidence unavailable")
        if "policy" in errors:
            gates["policy"] = gate("hold", errors["policy"])
        if "state" in errors and not non_deploying:
            gates["state"] = gate("hold", errors["state"])
        result["services"].append({**row, "ci": ci, "nonDeploying": non_deploying, "prerequisites": graph.get(name, []), "rollout": progress, "gates": gates, "notes": notes, "verdict": verdict(gates)})
    rows = result["services"]
    if selected and not rows:
        result["errors"].append("requested service is excluded by readiness policy")
    result["verdict"] = "NOT READY" if any(row["verdict"] == "NOT READY" for row in rows) else "HOLD" if not rows or any(row["verdict"] == "HOLD" for row in rows) else "READY"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", nargs="?")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--snapshot", type=Path, help="evaluate captured raw evidence; run no collectors")
    args = parser.parse_args()
    if args.snapshot:
        evidence = read_evidence(args.snapshot)
        try:
            data = json.loads(source_text(evidence))
        except ValueError:
            data = None
    else:
        data = collect(args.project_root.resolve())
    print(json.dumps(evaluate(data, args.service), ensure_ascii=True))
