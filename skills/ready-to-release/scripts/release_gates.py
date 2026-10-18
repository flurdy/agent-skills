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
OPTIONAL_SOURCES = ("uptake",)
BUDGETS = {"release-digest": 90, "release-order": 20, "contract-check": 20, "release-config-uptake": 20}
UPTAKE_HEADER = "resource|context|namespace|workload|desired|applied|consumed|rolloutState|template"
UPTAKE_IDENTITY = ("resource", "context", "namespace", "workload")
UPTAKE_REVISIONS = ("desired", "applied", "consumed", "template")
RELOADS = {"startup", "dynamic", "unknown"}
ROLLOUT_STATES = {"settled", "rolling", "unknown"}
POLICY = {"ignore": [], "non_deploying": [], "toggles": {}, "parked": {}}
MAX_BUDGET = 120
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


def budget_seconds(name):
    try:
        return min(MAX_BUDGET, max(1, int(os.environ["RELEASE_GATES_TIMEOUT"])))
    except (KeyError, ValueError):
        return BUDGETS[name]


def collect_command(root, name, args):
    command = root / "scripts" / name
    if not command.is_file():
        return unavailable(f"{name} adapter missing", "absent")
    timeout = budget_seconds(name)
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
                return unavailable(f"{name} timeout after {timeout}s budget")
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
    return {
        "schemaVersion": 1,
        "digest": collect_command(root, "release-digest", []),
        "order": collect_command(root, "release-order", []),
        "contracts": collect_command(root, "contract-check", ["all"]),
        "manifest": read_evidence(root / "docs" / "release-manifest.yaml"),
        "state": read_evidence(root / ".release-state.json"),
        "uptake": collect_command(root, "release-config-uptake", []),
    }


def source_text(source):
    if source["status"] != "ok":
        raise ValueError(source.get("reason", "evidence unavailable"))
    return source["text"]


def sections(text):
    result = {}
    current = None
    for line in text.splitlines():
        if re.fullmatch(r"---[A-Z0-9]+---", line):
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


def parse_blocks(text, template):
    """Parse only the documented manifest subset, never pretend to parse general YAML."""
    policy = {key: list(value) if isinstance(value, list) else {} for key, value in template.items()}
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
    return policy


def parse_policy(text):
    policy = parse_blocks(text, POLICY)
    for entry in policy["toggles"].values():
        if not NAME.fullmatch(entry.get("service", "")) or entry.get("status", "active") not in {"active", "parked", "dark-release"}:
            raise ValueError("toggle service/status policy is invalid")
    return policy


def parse_uptake_declarations(text):
    """Project-owned config-to-workload mappings; problems are advisory diagnostics, never holds."""
    declarations, diagnostics = {}, []
    try:
        entries = parse_blocks(text, {"config_uptake": {}})["config_uptake"]
    except ValueError as error:
        return declarations, [f"config_uptake declarations unreadable: {error}"]
    fields = ("service", *UPTAKE_IDENTITY)
    for name, entry in entries.items():
        reload = entry.get("reload", "unknown")
        if any(not NAME.fullmatch(entry.get(field, "")) for field in fields) or reload not in RELOADS:
            diagnostics.append(f"config_uptake {name}: requires service, resource, context, namespace, workload names and reload in startup|dynamic|unknown")
            continue
        declarations[name] = {**{field: entry[field] for field in fields}, "reload": reload}
    return declarations, diagnostics


def parse_uptake(text):
    parts = sections(text)
    if not NAME.fullmatch(metadata(parts.get("---META---", [])).get("provider", "")):
        raise ValueError("missing config-uptake provider")
    rows = parts.get("---UPTAKE---", [])
    if not rows or rows[0] != UPTAKE_HEADER:
        raise ValueError("missing or malformed uptake header")
    observations = {}
    for line in rows[1:]:
        fields = line.split("|")
        if len(fields) != len(UPTAKE_HEADER.split("|")):
            raise ValueError("malformed uptake row")
        row = dict(zip(UPTAKE_HEADER.split("|"), fields, strict=True))
        if (any(not NAME.fullmatch(row[field]) for field in UPTAKE_IDENTITY)
                or any(row[field] != "-" and not NAME.fullmatch(row[field]) for field in UPTAKE_REVISIONS)
                or row["rolloutState"] not in ROLLOUT_STATES):
            raise ValueError("malformed uptake row")
        key = identity(row)
        observations[key] = None if key in observations else row
    return observations


def identity(entry):
    return tuple(entry[field] for field in UPTAKE_IDENTITY)


def describe(key):
    resource, context, namespace, workload = key
    return f"{resource} {context}/{namespace} {workload}"


def uptake_entry(name, declaration, observations, status, reason):
    """Advisory state for one declared mapping; unknown stays unknown and never becomes a restart."""
    entry = {"id": name, **declaration, "desired": None, "applied": None, "effective": None, "rolloutState": None,
             "template": None, "state": "unknown", "maintenance": None, "evidence": ""}
    if status != "ok":
        entry["evidence"] = f"config-uptake evidence {status}" + (f": {reason}" if reason else "")
        return entry
    key = identity(declaration)
    if key not in observations:
        same = [describe(other) for other in observations if other[0] == declaration["resource"]]
        entry["evidence"] = "workload identity mismatch: observed " + ", ".join(same) if same else "no observation for this resource and workload"
        return entry
    row = observations[key]
    if row is None:
        entry["evidence"] = "conflicting observations for this resource and workload"
        return entry
    revisions = {field: None if row[field] == "-" else row[field] for field in UPTAKE_REVISIONS}
    entry.update(desired=revisions["desired"], applied=revisions["applied"], effective=revisions["consumed"],
                 rolloutState=row["rolloutState"], template=revisions["template"])
    desired, applied, consumed, template = (revisions[field] for field in UPTAKE_REVISIONS)
    if desired is None or applied is None:
        entry["evidence"] = "desired or applied revision not reported"
        return entry
    if applied != desired:
        entry.update(state="pending", evidence=f"controller applied {applied}; desired {desired}")
        return entry
    if consumed == desired:
        entry.update(state="effective", evidence=f"workload consumes {desired}")
        return entry
    if row["rolloutState"] == "rolling" and template == desired:
        entry.update(state="rolling", evidence=f"rollout in progress delivers {desired}")
        return entry
    entry["state"] = "applied"
    workload = f"{declaration['workload']} in {declaration['context']}/{declaration['namespace']}"
    if consumed is None:
        reason = f"{desired} applied; consumed revision unknown"
    elif row["rolloutState"] == "rolling":
        reason = f"unrelated rollout in progress does not deliver {desired}; workload consumes {consumed}"
    elif row["rolloutState"] != "settled":
        reason = f"rollout state unknown; workload consumes {consumed}, not {desired}"
    elif template != desired:
        reason = f"pod template delivers {template or 'an unknown revision'}, not {desired}; a restart would not apply it"
    elif declaration["reload"] == "startup":
        reason = f"startup-only reload; workload consumes {consumed} while {desired} is applied and delivered by the pod template"
        entry.update(evidence=reason, maintenance={"action": "restart", "workload": workload, "reason": reason,
                                                     "command": f"/release-maintenance restart {declaration['service']}"})
        return entry
    elif declaration["reload"] == "dynamic":
        reason = f"dynamic reload declared but workload still consumes {consumed}, not {desired}"
    else:
        reason = f"reload semantics unknown; workload consumes {consumed}, not {desired}"
    entry.update(evidence=reason, maintenance={"action": "investigate", "workload": workload, "reason": reason})
    return entry


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
    required = {"schemaVersion", *SOURCES}
    if (not isinstance(data, dict) or not required <= set(data) or set(data) - required - set(OPTIONAL_SOURCES)
            or type(data["schemaVersion"]) is not int or data["schemaVersion"] != 1):
        raise ValueError("unsupported snapshot schema")
    for name in (*SOURCES, *(name for name in OPTIONAL_SOURCES if name in data)):
        item = data[name]
        if not isinstance(item, dict) or set(item) - {"status", "text", "reason"} or item.get("status") not in {"ok", "absent", "unavailable"}:
            raise ValueError("invalid evidence envelope")
        if item["status"] == "ok" and (not isinstance(item.get("text"), str) or len(item["text"].encode()) > LIMIT):
            raise ValueError("invalid or oversized evidence text")
        if "reason" in item and not isinstance(item["reason"], str):
            raise ValueError("invalid evidence reason")


def evaluate(data, selected=None, exclude_publication=None):
    result = {"schemaVersion": 1, "observedAt": datetime.now(timezone.utc).isoformat(), "context": "unknown", "drift": [], "services": [], "errors": [], "verdict": "HOLD"}
    try:
        validate_snapshot(data)
        meta, services, toggles = parse_digest(source_text(data["digest"]))
    except (ValueError, KeyError) as error:
        result["errors"].append(str(error))
        return result
    result["context"] = meta.get("context", "unknown")
    errors = {}
    declarations, uptake_diagnostics = parse_uptake_declarations(data["manifest"]["text"]) if data["manifest"]["status"] == "ok" else ({}, [])
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
    watches, publishing, publication_error = {}, {}, None
    if data["state"]["status"] == "ok":
        try:
            state = json.loads(data["state"]["text"])
        except ValueError:
            state = None
        # Publication records are parsed independently so a bad rollout entry cannot hide them.
        if not isinstance(state, dict) or not isinstance(state.get("publishing", {}), dict) or any(
                not isinstance(entry, dict) for entry in state.get("publishing", {}).values()):
            publication_error = "publication state unreadable; resolve before publishing"
        else:
            publishing = {service: entry for service, entry in state.get("publishing", {}).items()
                          if not exclude_publication or entry.get("id") != exclude_publication}
        try:
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
        publication_error = "publication state unreadable; resolve before publishing"
    result["errors"].extend(f"{source}: {reason}" for source, reason in errors.items())
    # Config uptake is advisory: its evidence and diagnostics never enter gates or collection errors.
    uptake_source = data.get("uptake", {"status": "not-captured"})
    uptake_status, uptake_reason, observations = uptake_source["status"], uptake_source.get("reason"), {}
    if uptake_status == "ok":
        try:
            observations = parse_uptake(uptake_source["text"])
        except ValueError as error:
            uptake_status, uptake_reason = "malformed", str(error)
    for name in [name for name, declaration in declarations.items() if declaration["service"] not in services]:
        uptake_diagnostics.append(f"config_uptake {name}: service {declarations.pop(name)['service']} is not in the digest")
    declared = {identity(declaration) for declaration in declarations.values()}
    result["uptake"] = {"status": uptake_status, "unmapped": [describe(key) for key in observations if key not in declared], "diagnostics": uptake_diagnostics}
    if uptake_reason:
        result["uptake"]["reason"] = uptake_reason
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
                if other and other["uncommitted"]:
                    notes.append(f"{prerequisite}: uncommitted local changes are not deployed")
                if not other:
                    unknown.append(prerequisite)
                elif other["unpushed"] > 0 or rollout(other, watches) == "rolling":
                    waiting.append(prerequisite)
                elif deployment(other["deploy"]) != "settled" or rollout(other, watches) == "unknown":
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
        if publication_error:
            gates["publication"] = gate("hold", publication_error)
        elif publishing:
            # A write-ahead publication record serializes every push until it settles or a human resolves it.
            gates["publication"] = gate("hold", *(
                f"{service}: {'uncertain outcome; resolve via /release-maintenance' if isinstance(entry, dict) and entry.get('uncertain') else 'publication in progress'}"
                for service, entry in sorted(publishing.items())))
        if "policy" in errors:
            gates["policy"] = gate("hold", errors["policy"])
        if "state" in errors and not non_deploying:
            gates["state"] = gate("hold", errors["state"])
        uptake = [uptake_entry(entry_name, declaration, observations, uptake_status, uptake_reason)
                  for entry_name, declaration in declarations.items() if declaration["service"] == name]
        for entry in uptake:
            if entry["maintenance"] and entry["maintenance"]["action"] == "restart":
                notes.append(f"config {entry['id']}: restart {entry['maintenance']['workload']} required — {entry['maintenance']['command']}")
            elif entry["state"] != "effective":
                notes.append(f"config {entry['id']}: {entry['state']} — {entry['evidence']}")
        result["services"].append({**row, "ci": ci, "nonDeploying": non_deploying, "prerequisites": graph.get(name, []), "rollout": progress, "gates": gates, "notes": notes, "configUptake": uptake, "verdict": verdict(gates)})
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
    parser.add_argument("--exclude-publication", metavar="ID", help="evaluate as if this one in-progress publication record were absent")
    args = parser.parse_args()
    if args.snapshot:
        evidence = read_evidence(args.snapshot)
        try:
            data = json.loads(source_text(evidence))
        except ValueError:
            data = None
    else:
        data = collect(args.project_root.resolve())
    if args.exclude_publication is not None and not re.fullmatch(r"[0-9a-f]{32}", args.exclude_publication):
        parser.error("--exclude-publication expects a 32-character publication attempt id")
    print(json.dumps(evaluate(data, args.service, args.exclude_publication), ensure_ascii=True))
