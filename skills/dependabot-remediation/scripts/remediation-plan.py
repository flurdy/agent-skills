#!/usr/bin/env python3
"""Deterministic Dependabot remediation planning and post-publication recheck.

``plan`` groups collected alerts into independently coherent outcomes and classifies
each as eligible (compatible patch/minor with local version evidence and, for transitive
dependencies, every parent range proven to allow the patch), hold (major, pre-1.0, no
patched version, unsupported ecosystem, parent range excluding or not proving the patch,
or missing local evidence) or verify-publication (locally already patched). Severity
informs priority only; it never widens eligibility. Eligible outcomes already owned by
existing tracking are excluded; the rest are partitioned into one dedicated item per
urgent (critical) fix and a capped number of small manifest-coherent batches. Anything
left over is deferred to one dated follow-up, never silently dropped.

``recheck`` compares a saved plan with a fresh collector read and reports fixed,
pending, dismissed, changed or unknown per outcome. Dismissed is not fixed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from itertools import groupby
from pathlib import Path

PLAN_SCHEMA = "dependabot-remediation-plan/v1"
RECHECK_SCHEMA = "dependabot-remediation-recheck/v1"
ALERTS_SCHEMA = "dependabot-alerts/v1"
SEMVER_ECOSYSTEMS = {"npm", "pip", "rubygems", "maven", "nuget", "composer", "go", "rust", "pub", "swift"}
SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
SEVERITY_PRIORITY = {"critical": "P1", "high": "P2", "medium": "P3", "low": "P3"}
URGENT_SEVERITIES = {"critical"}
BATCH_SIZE = 5
MAX_BATCHES = 3
EXCEPTION_BUDGET = 2
FOLLOW_UP_DAYS = 7
NUMERIC = re.compile(r"\d+")
NPM_COMPARATOR = re.compile(r"(\^|~|>=|<=|>|<|=)?v?(\d+|[xX*])(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?")
EXIT_OK, EXIT_UNAVAILABLE, EXIT_USAGE = 0, 3, 64


def parse_version(text) -> tuple[int, ...] | None:
    if not isinstance(text, str) or not text.strip():
        return None
    core = re.split(r"[-+ ]", text.strip().lstrip("vV=^~"), maxsplit=1)[0]
    parts = []
    for segment in core.split("."):
        match = NUMERIC.match(segment)
        if not match:
            break
        parts.append(int(match.group()))
    return tuple(parts) if parts else None


def padded(version: tuple[int, ...]) -> tuple[int, int, int]:
    return tuple((list(version) + [0, 0, 0])[:3])


def npm_comparator_allows(token: str, version: tuple[int, int, int]) -> bool | None:
    """Evaluate one npm comparator; None for syntax outside this deliberately small subset."""
    match = NPM_COMPARATOR.fullmatch(token)
    if not match:
        return None
    operator = match[1] or "="
    parts: list[int] = []
    for raw in match.group(2, 3, 4):
        if raw is None or raw in "xX*":
            break
        parts.append(int(raw))
    if operator in {">=", "<=", ">", "<"}:
        if len(parts) != 3:
            return None
        bound = tuple(parts)
        return {">=": version >= bound, "<=": version <= bound, ">": version > bound, "<": version < bound}[operator]
    if not parts:
        return True
    lower = padded(tuple(parts))
    if operator == "=":
        if len(parts) == 3:
            return version == lower
        index = len(parts) - 1
    elif operator == "~":
        index = min(len(parts) - 1, 1)
    else:
        index = next((i for i, part in enumerate(parts) if part), len(parts) - 1)
    upper = padded((*parts[:index], parts[index] + 1))
    return lower <= version < upper


def npm_range_allows(text, version: tuple[int, int, int]) -> bool | None:
    """True/False when an npm range provably includes/excludes version; None when unknown."""
    if not isinstance(text, str):
        return None
    results = []
    for alternative in text.split("||"):
        tokens = alternative.split()
        checks = [npm_comparator_allows(token, version) for token in tokens] if tokens else [None]
        # An unsupported token (e.g. a hyphen range) changes its neighbours' meaning.
        results.append(None if None in checks else False if False in checks else True)
    return True if True in results else None if None in results else False


def parent_reasons(ecosystem: str, dependency: dict, target: tuple[int, int, int]) -> list[str]:
    if dependency.get("parentRequiresMajorBump"):
        return ["transitive-parent-major"]
    if ecosystem == "npm":
        ranges = dependency.get("parentRanges")
        if not isinstance(ranges, list) or not ranges:
            return ["parent-range-unknown"]
        results = [npm_range_allows(text, target) for text in ranges]
    else:
        allowed = dependency.get("parentAllowsTarget")
        results = [allowed if isinstance(allowed, bool) else None]
    if False in results:
        return ["parent-range-excludes-target"]
    if None in results:
        return ["parent-range-unknown"]
    return []


def load_json(path: str | None):
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return json.load(sys.stdin)


def alerts_document(path: str | None) -> dict:
    document = load_json(path)
    if not isinstance(document, dict) or document.get("schemaVersion") != ALERTS_SCHEMA:
        raise SystemExit(f"remediation-plan: expected a {ALERTS_SCHEMA} document")
    return document


def dependency_index(local: dict) -> dict[tuple, dict]:
    index = {}
    for dependency in local.get("dependencies") or []:
        if isinstance(dependency, dict):
            index[group_key(dependency)] = dependency
    return index


def group_key(item: dict) -> tuple:
    return (
        str(item.get("ecosystem") or "").lower(),
        str(item.get("package") or "").lower(),
        str(item.get("manifestPath") or ""),
    )


def top_severity(alerts: list[dict]) -> str | None:
    ranked = sorted((a.get("severity") or "" for a in alerts), key=lambda s: SEVERITY_RANK.get(s, 0))
    return ranked[-1] if ranked and ranked[-1] in SEVERITY_RANK else None


def classify(alerts: list[dict], dependency: dict | None) -> tuple[str, list[str], dict]:
    sample = alerts[0]
    ecosystem = str(sample.get("ecosystem") or "").lower()
    reasons: list[str] = []
    upgrade = {"from": None, "to": None, "kind": None}
    if ecosystem not in SEMVER_ECOSYSTEMS:
        return "hold", ["unsupported-ecosystem"], upgrade
    targets = [parse_version(a.get("firstPatchedVersion")) for a in alerts]
    if any(target is None for target in targets):
        return "hold", ["uncertain-version"], upgrade
    target = max(padded(version) for version in targets if version)
    upgrade["to"] = ".".join(str(part) for part in target)
    if target[0] == 0:
        reasons.append("pre-1.0-uncertain")
    installed = parse_version(dependency.get("installedVersion")) if dependency else None
    if installed is None:
        reasons.append("local-version-unknown")
        return "hold", reasons, upgrade
    current = padded(installed)
    upgrade["from"] = dependency.get("installedVersion")
    if current >= target:
        upgrade["kind"] = "none"
        return "verify-publication", reasons or ["locally-at-or-above-patched"], upgrade
    if current[0] != target[0]:
        reasons.append("major-upgrade")
    upgrade["kind"] = "major" if current[0] != target[0] else "minor" if current[1] != target[1] else "patch"
    relationship = str(sample.get("relationship") or dependency.get("relationship") or "").lower()
    if relationship == "transitive":
        reasons.extend(parent_reasons(ecosystem, dependency, target))
    if relationship not in {"direct", "transitive"}:
        reasons.append("relationship-unknown")
    return ("hold" if reasons else "eligible"), reasons, upgrade


def tracked_owner(outcome: dict, tracked: list) -> str | None:
    for entry in tracked:
        if not isinstance(entry, dict):
            continue
        keys, alerts = entry.get("keys") or [], entry.get("alerts") or []
        if outcome["key"] in keys or any(identity in alerts for identity in outcome["alerts"]):
            return str(entry.get("owner") or "unknown")
    return None


def build_plan(alerts_doc: dict, local: dict, tracked: list | None = None,
               batch_size: int = BATCH_SIZE, max_batches: int = MAX_BATCHES) -> dict:
    repository = alerts_doc.get("repository")
    evidence = {
        "status": alerts_doc.get("status"),
        "reason": alerts_doc.get("reason"),
        "defaultBranchHeadSha": (alerts_doc.get("defaultBranch") or {}).get("headSha"),
    }
    plan = {
        "schemaVersion": PLAN_SCHEMA,
        "repository": repository,
        "alertEvidence": evidence,
        "local": {"revision": local.get("revision"), "dirty": bool(local.get("dirty"))},
        "blockers": ["dirty-worktree"] if local.get("dirty") else [],
        "outcomes": [],
        "work": None,
        "summary": {"alerts": 0, "eligible": 0, "hold": 0, "verify-publication": 0},
    }
    if evidence["status"] not in {"complete", "partial"}:
        plan["blockers"].append("alert-evidence-unavailable")
        return with_work(plan, batch_size, max_batches)
    if evidence["status"] == "partial":
        plan["blockers"].append("alert-evidence-partial")
    open_alerts = [a for a in alerts_doc.get("alerts") or [] if a.get("state") == "open"]
    plan["summary"]["alerts"] = len(open_alerts)
    groups: dict[tuple, list[dict]] = {}
    for alert in open_alerts:
        bucket = "patched" if alert.get("firstPatchedVersion") else "unpatched"
        groups.setdefault((*group_key(alert), bucket), []).append(alert)
    dependencies = dependency_index(local)
    for (ecosystem, package, manifest, bucket), alerts in sorted(groups.items()):
        dependency = dependencies.get((ecosystem, package, manifest))
        if bucket == "unpatched":
            decision, reasons, upgrade = "hold", ["no-patched-version"], {"from": None, "to": None, "kind": None}
        else:
            decision, reasons, upgrade = classify(alerts, dependency)
        severity = top_severity(alerts)
        target = f" to >= {upgrade['to']}" if upgrade["to"] else ""
        plan["outcomes"].append({
            "key": f"{repository}:{ecosystem}:{package}:{manifest}:{bucket}",
            "ecosystem": alerts[0].get("ecosystem"),
            "package": alerts[0].get("package"),
            "manifestPath": manifest,
            "relationship": alerts[0].get("relationship"),
            "scope": alerts[0].get("scope"),
            "alerts": [a["identity"] for a in alerts],
            "severity": severity,
            "priority": SEVERITY_PRIORITY.get(severity or "", "P3"),
            "decision": decision,
            "reasons": reasons,
            "upgrade": upgrade,
            "tracked": None,
            "work": None,
            "titleHint": f"Upgrade {alerts[0].get('package')}{target} ({manifest})",
        })
        plan["summary"][decision] += 1
    for outcome in plan["outcomes"]:
        outcome["tracked"] = tracked_owner(outcome, tracked or [])
    return with_work(plan, batch_size, max_batches)


def with_work(plan: dict, batch_size: int, max_batches: int) -> dict:
    work = build_work(plan["outcomes"], plan["repository"], batch_size, max_batches)
    plan["work"] = work
    plan["summary"].update({
        "urgent": len(work["urgent"]),
        "batched": sum(len(batch["outcomes"]) for batch in work["batches"]),
        "deferred": len(work["deferred"]),
        "tracked": len(work["tracked"]),
    })
    return plan


def priority_order(outcome: dict) -> tuple:
    return (-SEVERITY_RANK.get(outcome["severity"] or "", 0), outcome["scope"] != "runtime", outcome["key"])


def work_item(kind: str, index: int, outcomes: list[dict]) -> dict:
    packages = [o["package"] for o in outcomes]
    shown = ", ".join(packages[:3]) + (f" (+{len(packages) - 3} more)" if len(packages) > 3 else "")
    manifest = outcomes[0]["manifestPath"]
    if kind == "urgent":
        title = f"Urgent: {outcomes[0]['titleHint']}"
    else:
        title = f"Dependabot security batch {index}: {len(outcomes)} fix{'' if len(outcomes) == 1 else 'es'} in {manifest} ({shown})"
    for outcome in outcomes:
        outcome["work"] = f"{kind}-{index}"
    return {
        "id": f"{kind}-{index}",
        "manifestPath": manifest,
        "priority": min(o["priority"] for o in outcomes),
        "outcomes": [o["key"] for o in outcomes],
        "alerts": [identity for o in outcomes for identity in o["alerts"]],
        "titleHint": title,
    }


def build_work(outcomes: list[dict], repository, batch_size: int, max_batches: int) -> dict:
    """Partition eligible, untracked outcomes into dedicated urgent items and bounded batches."""
    urgent, normal = [], []
    for outcome in outcomes:
        if outcome["tracked"] is not None:
            outcome["work"] = "tracked"
        elif outcome["decision"] == "eligible":
            (urgent if outcome["severity"] in URGENT_SEVERITIES else normal).append(outcome)
    urgent.sort(key=priority_order)
    normal.sort(key=lambda o: (o["manifestPath"], *priority_order(o)))
    chunks = []
    for _manifest, group in groupby(normal, key=lambda o: o["manifestPath"]):
        members = list(group)
        chunks.extend(members[i:i + batch_size] for i in range(0, len(members), batch_size))
    chunks.sort(key=lambda chunk: (*priority_order(chunk[0])[:2], chunk[0]["manifestPath"]))
    deferred = [o for chunk in chunks[max_batches:] for o in chunk]
    for outcome in deferred:
        outcome["work"] = "deferred"
    return {
        "limits": {"batchSize": batch_size, "maxBatches": max_batches,
                   "exceptions": EXCEPTION_BUDGET, "followUpDays": FOLLOW_UP_DAYS},
        "urgent": [work_item("urgent", i, [o]) for i, o in enumerate(urgent, 1)],
        "batches": [work_item("batch", i, chunk) for i, chunk in enumerate(chunks[:max_batches], 1)],
        "deferred": [o["key"] for o in deferred],
        "tracked": [{"key": o["key"], "owner": o["tracked"]} for o in outcomes if o["tracked"] is not None],
        "held": [o["key"] for o in outcomes if o["decision"] == "hold"],
        "verifyPublication": [o["key"] for o in outcomes if o["decision"] == "verify-publication"],
        "followUp": {
            "needed": bool(deferred),
            "reason": "deferred-outcomes" if deferred else None,
            "days": FOLLOW_UP_DAYS,
            "titleHint": f"Recheck Dependabot alerts for {repository}" if deferred else None,
        },
    }


def alert_resolution(identity: str, fresh: dict) -> str:
    number = int(identity.rsplit("#", 1)[-1]) if "#" in identity else None
    if fresh.get("status") not in {"complete", "partial"} or number in (fresh.get("unavailable") or []):
        return "unknown"
    if number in (fresh.get("missing") or []):
        return "missing"
    for alert in fresh.get("alerts") or []:
        if alert.get("identity") == identity:
            state = alert.get("state")
            if state == "fixed":
                return "fixed"
            if state in {"dismissed", "auto_dismissed"}:
                return "dismissed"
            return "open" if state == "open" else "unknown"
    return "missing" if fresh.get("requested") else "unknown"


def outcome_resolution(states: list[str]) -> str:
    if not states or "unknown" in states:
        return "unknown"
    if all(state == "fixed" for state in states):
        return "fixed"
    if "missing" in states:
        return "changed"
    if "open" in states:
        return "pending"
    return "dismissed"


def build_recheck(plan: dict, fresh: dict, published_sha: str | None) -> dict:
    head = fresh.get("defaultBranch") or {}
    head_sha = head.get("headSha")
    publication = None if published_sha is None or head_sha is None else head_sha == published_sha
    outcomes = []
    for outcome in plan.get("outcomes") or []:
        states = {identity: alert_resolution(identity, fresh) for identity in outcome.get("alerts") or []}
        outcomes.append({
            "key": outcome.get("key"),
            "decision": outcome.get("decision"),
            "alerts": states,
            "resolution": outcome_resolution(list(states.values())),
        })
    return {
        "schemaVersion": RECHECK_SCHEMA,
        "repository": plan.get("repository"),
        "alertEvidence": {"status": fresh.get("status"), "reason": fresh.get("reason")},
        "defaultBranchHeadSha": head_sha,
        "publishedSha": published_sha,
        "publicationObserved": publication,
        "outcomes": outcomes,
        "allFixed": bool(outcomes) and all(o["resolution"] == "fixed" for o in outcomes),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="group alerts into remediation outcomes")
    plan.add_argument("--alerts", help="collector JSON file; defaults to stdin")
    plan.add_argument("--local", help="JSON file with local revision, dirty flag and dependency versions")
    plan.add_argument("--tracked", help="JSON array of existing owners: [{\"owner\", \"alerts\": [...], \"keys\": [...]}]")
    plan.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                      help=f"maximum fixes in one batch (default {BATCH_SIZE})")
    plan.add_argument("--max-batches", type=int, default=MAX_BATCHES,
                      help=f"maximum batches per plan run (default {MAX_BATCHES})")
    recheck = commands.add_parser("recheck", help="compare a saved plan with a fresh collector read")
    recheck.add_argument("--plan", required=True, help="saved plan JSON file")
    recheck.add_argument("--alerts", help="fresh collector JSON file; defaults to stdin")
    recheck.add_argument("--published-sha", help="commit expected on the default branch")
    args = parser.parse_args(argv)

    if args.command == "plan":
        local = load_json(args.local) if args.local else {}
        if not isinstance(local, dict):
            raise SystemExit("remediation-plan: --local must be a JSON object")
        tracked = load_json(args.tracked) if args.tracked else []
        if not isinstance(tracked, list):
            raise SystemExit("remediation-plan: --tracked must be a JSON array")
        if args.batch_size < 1 or args.max_batches < 1:
            raise SystemExit("remediation-plan: --batch-size and --max-batches must be at least 1")
        result = build_plan(alerts_document(args.alerts), local, tracked, args.batch_size, args.max_batches)
        exit_code = EXIT_UNAVAILABLE if "alert-evidence-unavailable" in result["blockers"] else EXIT_OK
    else:
        saved = load_json(args.plan)
        if not isinstance(saved, dict) or saved.get("schemaVersion") != PLAN_SCHEMA:
            raise SystemExit(f"remediation-plan: --plan must be a {PLAN_SCHEMA} document")
        result = build_recheck(saved, alerts_document(args.alerts), args.published_sha)
        exit_code = EXIT_OK
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, json.JSONDecodeError) as error:
        print(f"remediation-plan: {error}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
