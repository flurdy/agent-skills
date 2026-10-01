#!/usr/bin/env python3
"""Enrich one collector snapshot. Advisory previews only; never apply configuration."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

SKILLS = Path(__file__).resolve().parents[2]
MAX_CONFIG_BYTES = 2 * 1024 * 1024
MAX_EVIDENCE_BYTES = 65536
COMPATIBILITY = {"role", "stability", "reasoning", "modalities", "limits", "pricing", "billingRoute"}
ALIASES = {"claude": {"opus", "sonnet", "haiku", "fable", "default", "smart", "fast"},
           "codex": {"default", "smart", "fast"}, "gemini": {"default", "smart", "fast", "auto"}}
CLI_CATALOG = {"codex": "openai", "claude": "anthropic", "gemini": "google"}
PI_CATALOG = {"openai-codex": "openai", "google-gemini-cli": "google"}


def load_spend():
    path = SKILLS / "pi-spend/scripts/pi_spend.py"
    spec = importlib.util.spec_from_file_location("model_audit_spend", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SPEND = load_spend()


def snapshot(path, ceiling=MAX_CONFIG_BYTES):
    path = Path(path).expanduser()
    metadata = {"path": str(path), "sha256": None, "status": "missing"}
    try:
        with path.open("rb") as handle:
            data = handle.read(ceiling + 1)
        if len(data) > ceiling:
            raise ValueError("oversize")
        metadata["sha256"] = hashlib.sha256(data).hexdigest()
        value = json.loads(data, object_pairs_hook=SPEND.strict_json_object,
                           parse_constant=SPEND.reject_json_constant)
        if not isinstance(value, dict):
            raise ValueError("object required")
        metadata["status"] = "ok"
        return value, metadata
    except FileNotFoundError:
        return {}, metadata
    except (OSError, ValueError):
        metadata["status"] = "invalid"
        return {}, metadata


def pointer(*parts):
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def text(value, limit=2000):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and not any(ord(c) < 32 for c in value)


def identity_parts(identity):
    if not text(identity, 512) or any(c.isspace() for c in identity):
        return None
    parts = identity.split("/")
    if len(parts) < 2 or not all(parts):
        return None
    if parts[0] == "local":
        return ("/".join(parts[:2]), "/".join(parts[2:])) if len(parts) >= 3 and parts[1] in CLI_CATALOG else None
    return parts[0], "/".join(parts[1:])


def router_policy(router, identity):
    """Read-only projection of global policy, not runtime or launch authorization."""
    explicit = router.get("modelPolicies", {})
    if not isinstance(explicit, dict):
        return None, "invalid", None
    if identity in explicit:
        policy = explicit[identity]
        if not isinstance(policy, dict) or type(policy.get("metered")) is not bool or not isinstance(policy.get("consent", "ask"), str) or policy.get("consent", "ask") not in {"ask", "allow"}:
            return None, "invalid", None
        return policy["metered"], "modelPolicies", policy.get("consent", "ask")
    values = []
    for tier in router.get("tiers", {}).values():
        for item in tier.get("candidates", []):
            if item.get("model") == identity and "metered" in item:
                if type(item["metered"]) is not bool:
                    return None, "invalid", None
                values.append(item["metered"])
    if not values:
        return None, "unknown", None
    return any(values), "inline-conflict" if len(set(values)) > 1 else "inline", "ask"


def inventory(router, panel, sources):
    rows = []
    if sources["routerConfig"]["status"] == "ok":
        for tier_name, tier in router.get("tiers", {}).items():
            for index, item in enumerate(tier.get("candidates", [])):
                identity = item["model"]
                metered, basis, consent = router_policy(router, identity)
                rows.append({"source": "routerConfig", "identity": identity, "model": identity,
                             "path": pointer("tiers", tier_name, "candidates", index, "model"),
                             "usage": tier_name, "resolution": "exact", "enabled": item.get("enabled", True),
                             "routerEnabled": router.get("enabled", True), "weight": item.get("weight"),
                             "selection": tier.get("selection", "first-available"), "thinking": tier.get("thinking"),
                             "metered": metered, "policyBasis": basis, "consent": consent,
                             "policyPath": pointer("modelPolicies", identity)})
    if sources["consensusConfig"]["status"] != "ok":
        return rows
    for name, profile in panel.get("profiles", {}).items():
        collection = "routes" if "routes" in profile else "models"
        for index, item in enumerate(profile[collection]):
            local = item.get("kind") == "local"
            model = item.get("model", "native-default")
            identity = f"local/{item['agent']}/{model}" if local else model
            resolution = "exact"
            if model == "native-default":
                resolution = "native-default"
            elif local and (model in ALIASES.get(item["agent"], set()) or model.endswith("-latest")):
                resolution = "native-alias"
            rows.append({"source": "consensusConfig", "identity": identity, "model": model,
                         "path": pointer("profiles", name, collection, index, "model"), "usage": name,
                         "role": item["role"], "resolution": resolution,
                         "enabled": profile.get("enabled", True) and item.get("enabled", True),
                         "effort": item.get("effort"), "quorum": profile.get("quorum"),
                         "consensusQuorum": profile.get("consensusQuorum"),
                         "runtimeAvailability": None if local else "catalog-check"})
    subscriptions = panel.get("subscriptionRoutes", {})
    if isinstance(subscriptions, dict):
        for agent, models in subscriptions.items():
            if agent not in CLI_CATALOG or not isinstance(models, list):
                continue
            for index, model in enumerate(models):
                if not text(model, 512):
                    continue
                rows.append({"source": "consensusConfig", "identity": f"local/{agent}/{model}", "model": model,
                             "path": pointer("subscriptionRoutes", agent, index), "usage": "subscriptionRoutes",
                             "resolution": "native-alias" if model in ALIASES[agent] or model.endswith("-latest") else "exact",
                             "consentSensitive": True, "runtimeAvailability": None})
    return rows


def catalog_scope(identity):
    route, model = identity_parts(identity)
    if route.startswith("local/"):
        return route, CLI_CATALOG[route.split("/")[1]], model
    return route, PI_CATALOG.get(route, route), model


def model_facts(identity, catalogs, sources):
    route, provider, model = catalog_scope(identity)
    dev, opened, pi = catalogs
    record = (dev.get(provider, {}).get("models") or {}).get(model)
    # OpenRouter facts stay on the OpenRouter route. Local CLI/Pi availability never follows them.
    direct = opened.get(model) if route == "openrouter" else None
    return {
        "piAvailable": None if route.startswith("local/") or sources["piCatalog"]["status"] != "ok" else identity in pi,
        "runtimeAvailability": "unknown" if route.startswith("local/") else "pi-catalog",
        "liveFound": None if sources["modelsDev"]["status"] != "ok" or provider not in dev else record is not None,
        "openRouterFound": None if route != "openrouter" or sources["openRouter"]["status"] != "ok" else direct is not None,
        "modelsDev": record, "openRouter": direct,
    }


def discover(rows, catalogs, sources):
    dev, opened, pi = catalogs
    scopes = {}
    for row in rows:
        if row["resolution"] != "exact" or not identity_parts(row["identity"]):
            continue
        route, provider, model = catalog_scope(row["identity"])
        namespace = model.split("/")[0].lstrip("~") if route == "openrouter" else None
        scopes[(route, provider, namespace)] = True
    result = []
    for route, provider, namespace in sorted(scopes):
        candidates = set(dev.get(provider, {}).get("models") or {})
        if route == "openrouter":
            candidates.update(opened)
        else:
            # Discovery leads only, never identity equivalence or runtime availability.
            candidates.update(key.split("/", 1)[1] for key in opened if key.startswith(provider + "/"))
        candidates.update(key[len(route) + 1:] for key in pi if key.startswith(route + "/"))
        for model in sorted(candidates):
            if namespace is not None and model.split("/")[0].lstrip("~") != namespace:
                continue
            identity = f"{route}/{model}"
            if not identity_parts(identity):
                continue
            facts = model_facts(identity, catalogs, sources)
            cross_route = opened.get(f"{provider}/{model}") if route != "openrouter" else None
            result.append({"identity": identity, "status": "discovered-not-successor",
                           "crossRouteDiscoveryOnly": cross_route, **facts})
    return result


def release_date(facts):
    date = (facts.get("modelsDev") or {}).get("release_date")
    if isinstance(date, str) and re.fullmatch(r"\d{4}(?:-\d{2}){0,2}", date):
        return date
    created = (facts.get("openRouter") or facts.get("crossRouteDiscoveryOnly") or {}).get("created")
    if isinstance(created, (int, float)) and 0 < created < 253402300799:
        return datetime.fromtimestamp(created, timezone.utc).date().isoformat()
    return None


def discovery_leads(rows, candidates):
    """Name/date similarity is a research trigger only, never upgrade evidence."""
    result = []
    seen = set()
    for row in rows:
        if row["resolution"] != "exact" or row.get("enabled") is False:
            continue
        identity = row["identity"]
        if identity in seen:
            continue
        seen.add(identity)
        family = re.sub(r"\d+(?:[.-]\d+)*", "<version>", identity)
        if "<version>" not in family:
            continue
        current_date = release_date(row["facts"])
        for candidate in candidates:
            target = candidate["identity"]
            if target == identity or re.sub(r"\d+(?:[.-]\d+)*", "<version>", target) != family:
                continue
            candidate_date = release_date(candidate)
            if current_date and candidate_date and candidate_date <= current_date:
                continue
            result.append({"from": identity, "to": target, "status": "compatibility-unverified",
                           "reason": "Same-family discovery lead; release metadata is newer or incomplete. Not successor proof.",
                           "currentRelease": current_date, "candidateRelease": candidate_date})
    return result


def checked_time(value, now):
    parsed = SPEND.parse_utc_timestamp(value)
    return parsed is not None and now - timedelta(days=7) <= parsed <= now


def valid_citation(citation):
    if not isinstance(citation, dict) or set(citation) != {"url", "quote"} or not text(citation["quote"]):
        return False
    try:
        url = urlsplit(citation["url"])
        return url.scheme == "https" and bool(url.hostname) and not url.username and not url.password and url.port in {None, 443}
    except (ValueError, TypeError):
        return False


def validate_evidence(payload, now):
    if set(payload) != {"schemaVersion", "recommendations"} or type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1:
        return False
    items = payload["recommendations"]
    if not isinstance(items, list) or len(items) > 32:
        return False
    seen = set()
    for item in items:
        required = {"from", "to", "checkedAt", "citations", "compatibility"}
        if not isinstance(item, dict) or not required <= set(item) or set(item) - required - {"nativeAvailability", "billing", "routerPolicy"}:
            return False
        pair = (item["from"], item["to"])
        if not all(identity_parts(value) for value in pair) or pair[0] == pair[1]:
            return False
        if pair in seen or identity_parts(pair[0])[0] != identity_parts(pair[1])[0]:
            return False
        seen.add(pair)
        if not checked_time(item["checkedAt"], now):
            return False
        citations = item["citations"]
        if not isinstance(citations, list) or not 1 <= len(citations) <= 4 or not all(valid_citation(c) for c in citations):
            return False
        compatibility = item["compatibility"]
        if not isinstance(compatibility, dict) or set(compatibility) != COMPATIBILITY or not all(text(v) for v in compatibility.values()):
            return False
        native = item.get("nativeAvailability")
        if "nativeAvailability" in item and not text(native):
            return False
        billing = item.get("billing")
        if "billing" in item:
            if not isinstance(billing, dict) or set(billing) != {"billing", "effectiveFrom", "evidence"}:
                return False
            if not isinstance(billing["billing"], str) or billing["billing"] not in {"metered", "subscription"} or SPEND.parse_utc_timestamp(billing["effectiveFrom"]) is None or not text(billing["evidence"]):
                return False
        policy = item.get("routerPolicy")
        if "routerPolicy" in item and (not isinstance(policy, dict) or set(policy) != {"metered", "consent", "evidence"}
                                   or type(policy["metered"]) is not bool or not isinstance(policy["consent"], str) or policy["consent"] not in {"ask", "allow"} or not text(policy["evidence"])):
            return False
    return True


def change(source, path, before, after, consent=False, operation="replace"):
    return {"source": source, "path": path, "operation": operation, "before": before, "after": after,
            "consentSensitive": consent, "authorization": "separate-current-run-required"}


def spend_coverage(identity, policy, now, payload, policy_status):
    if identity.startswith("local/"):
        return {"billing": "not-applicable", "reason": "cli-not-pi",
                "explanation": "This CLI route is not classified by Pi spend reports."}
    provider, model = identity.split("/", 1)
    billing, source = policy.classify(provider, model, now)
    intervals = policy.models.get(identity, ())
    if billing != "unknown":
        reason = "covered"
        explanation = f"Spend reports classify current usage as {billing}."
    else:
        if policy_status == "missing":
            reason, explanation = "missing-policy", "The spend-reporting policy file is missing."
        elif policy_status == "invalid":
            reason, explanation = "invalid-policy", "The spend-reporting policy cannot be read or validated."
        elif identity not in payload.get("models", {}):
            reason, explanation = "missing-model-rule", "This model has no spend-reporting rule."
        elif not intervals:
            reason, explanation = "invalid-model-rule", "This model's spend-reporting rule is invalid."
        elif all(interval.effective_from > now for interval in intervals):
            reason, explanation = "not-started", "This model's spend-reporting rule starts in the future."
        elif all(interval.effective_until is not None and interval.effective_until <= now for interval in intervals):
            reason, explanation = "ended", "This model's spend-reporting rules have ended."
        else:
            reason, explanation = "gap", "There is a date gap in this model's spend-reporting rules."
        explanation += " If used now, /pi-spend labels its usage unknown. This is a reporting gap, not a charge or proof of free usage."
    return {"billing": billing, "source": source, "at": now.isoformat(),
            "historicalIntervals": len(intervals), "reason": reason, "explanation": explanation}


def interaction_plan(sources, leads, recommendations, assessments, candidates, findings):
    """Suggest the next conversation step; never authorize a side effect."""
    blocking = [name for name in ("routerConfig", "consensusConfig") if sources[name]["status"] != "ok"]
    unavailable = [name for name in ("piCatalog", "modelsDev", "openRouter") if sources[name]["status"] != "ok"]
    candidate_facts = {item["identity"]: item for item in candidates}
    locations = {item["identity"]: item["locations"] for item in assessments}
    opportunities = []
    for lead in leads:
        facts = candidate_facts.get(lead["to"], {})
        opportunities.append({"from": lead["from"], "to": lead["to"],
                              "locations": locations.get(lead["from"], []),
                              "piAvailable": facts.get("piAvailable"), "liveFound": facts.get("liveFound"),
                              "cliAvailability": "unverified" if lead["to"].startswith("local/") else "not-applicable"})
    if blocking:
        kind, question = "inspect-config", "A configuration could not be audited. Review the problem before planning upgrades?"
        label, option = "Review configuration issue", "inspect"
    elif recommendations:
        kind, question = "review-preview", "Review the proposed changes and any unresolved decisions?"
        label, option = "Review preview", "review-preview"
    elif leads:
        kind, question = "review-upgrade", "Review the model candidate and preview the affected configuration changes?"
        label, option = "Review and preview", "review-preview"
    elif unavailable:
        kind, question = "inspect-availability", "Some model sources are unavailable. Review what could not be checked?"
        label, option = "Review missing evidence", "inspect"
    else:
        kind, question, label, option = "none", None, None, None
    action = {"kind": kind, "question": question, "scope": "read-only", "requiresReply": kind != "none",
              "doesNotAuthorize": ["apply", "refresh", "billing-classification", "allowlist-expansion", "inference"],
              "options": ([{"id": option, "label": label, "description": "Read-only review; no configuration changes."},
                           {"id": "leave-unchanged", "label": "Leave unchanged", "description": "Stop without changing settings."}]
                          if kind != "none" else [])}
    return {"schemaVersion": 1, "primaryAction": action, "opportunities": opportunities,
            "blockingSources": blocking, "unavailableSources": unavailable,
            "housekeeping": [f for f in findings if f["kind"] in {"spend-policy", "spend-uncovered", "pi-npm-ahead-of-homebrew"}]}


def spend_change(evidence, spend, policy, now):
    identity = evidence["to"]
    if identity.startswith("local/"):
        return [], []
    if "billing" not in evidence:
        return [], ["Explicit exact-model billing and effective-start evidence required; no interval inferred."]
    if policy.status != "complete":
        return [], ["Repair or establish the spend policy separately before proposing interval additions."]
    entry = evidence["billing"]
    interval = {"effectiveFrom": entry["effectiveFrom"], "effectiveUntil": None, "billing": entry["billing"]}
    previous = spend["models"].get(identity, [])
    if interval in previous:
        return [], []
    if SPEND.parse_utc_timestamp(interval["effectiveFrom"]) < now:
        return [], ["Proposed effectiveFrom is in the past; this preview never backfills historical billing."]
    # Addition only; the owner validator rejects overlaps, including existing open intervals.
    after = previous + [interval]
    candidate = {**spend, "models": {**spend["models"], identity: after}}
    if SPEND.parse_billing_policy(candidate).status != "complete":
        return [], ["Proposed billing interval overlaps or is invalid; historical intervals are never rewritten."]
    return [change("billingPolicy", pointer("models", identity), previous if identity in spend["models"] else None,
                   after, operation="replace" if identity in spend["models"] else "add")], []


def router_policy_preview(item, router):
    policies = router.get("modelPolicies", {})
    if not isinstance(policies, dict):
        return [], ["Router modelPolicies map is invalid; repair separately."]
    previous = policies.get(item["to"])
    if item["to"] in policies and router_policy(router, item["to"])[1] == "invalid":
        return [], ["Candidate router policy is invalid; repair separately."]
    requested = item.get("routerPolicy")
    if requested is None:
        return ([], ["New exact router policy needs an explicit billing/consent decision; not copied from the old model."]) if previous is None else ([], [])
    after = {k: requested[k] for k in ("metered", "consent")}
    if previous is not None:
        return ([], ["Candidate already has a different router policy; resolve separately, never overwrite consent."]) if any(previous.get(k) != v for k, v in after.items()) else ([], [])
    path = pointer("modelPolicies", item["to"]) if "modelPolicies" in router else pointer("modelPolicies")
    value = after if "modelPolicies" in router else {item["to"]: after}
    return [change("routerConfig", path, None, value, consent=True, operation="add")], []


def previews(evidence, rows, router, panel, spend, policy, catalogs, sources, now):
    result = []
    for item in evidence.get("recommendations", []):
        locations = [r for r in rows if r["identity"] == item["from"]]
        unresolved = []
        changes = []
        facts = model_facts(item["to"], catalogs, sources)
        local = item["from"].startswith("local/")
        available = bool(item.get("nativeAvailability")) if local else facts["piAvailable"] is True
        if item["to"].startswith("openrouter/"):
            available = available and facts["openRouterFound"] is True
        if not locations:
            unresolved.append("Source identity is not configured.")
        if not available:
            unresolved.append("Candidate availability is missing or unverified on this exact runtime route.")
        if any(r["resolution"] != "exact" for r in locations):
            unresolved.append("Native aliases/defaults are preserved; resolve explicit pins separately.")
        if locations and available and all(r["resolution"] == "exact" for r in locations):
            target = identity_parts(item["to"])[1] if local else item["to"]
            for row in locations:
                if row["usage"] == "subscriptionRoutes":
                    agent = identity_parts(item["from"])[0].split("/")[1]
                    previous = panel["subscriptionRoutes"][agent]
                    if target not in previous:
                        proposed = change("consensusConfig", pointer("subscriptionRoutes", agent), previous,
                                          previous + [target], consent=True)
                        if proposed not in changes:
                            changes.append(proposed)
                else:
                    changes.append(change(row["source"], row["path"], row["model"], target))
            if any(r["source"] == "routerConfig" for r in locations):
                policy_changes, policy_unresolved = router_policy_preview(item, router)
                changes.extend(policy_changes)
                unresolved.extend(policy_unresolved)
            if item["to"].startswith("openrouter/") and any(r["source"] == "consensusConfig" for r in locations):
                policies = panel.get("modelPolicies", {})
                if item["to"] not in policies:
                    unresolved.append("Review new panel exact-model consent separately; existing consent is not inherited.")
            spend_changes, spend_unresolved = spend_change(item, spend, policy, now)
            changes.extend(spend_changes)
            unresolved.extend(spend_unresolved)
        result.append({"from": item["from"], "to": item["to"], "evidence": item,
                       "evidenceTrust": "reviewed-input-not-independently-verified",
                       "status": "incomplete" if unresolved else "optional-upgrade",
                       "availability": facts, "changes": changes, "unresolved": unresolved})
    return result


def enrich(report, router_path, panel_path, spend_path, evidence_path, catalogs, refresh, now, billing_policy_path=None):
    router, router_meta = snapshot(router_path)
    panel, panel_meta = snapshot(panel_path)
    spend, spend_meta = snapshot(spend_path)
    sources = report["sources"]
    for name, meta in (("routerConfig", router_meta), ("consensusConfig", panel_meta)):
        if meta["status"] != "ok":
            sources[name]["status"] = meta["status"]
        sources[name]["sha256"] = meta["sha256"]
    policy = SPEND.parse_billing_policy(spend) if spend_meta["status"] == "ok" else SPEND.missing_policy(SPEND.EFFECTIVE_POLICY, "billing-policy-" + spend_meta["status"])
    spend_meta.update(status=policy.status if spend_meta["status"] == "ok" else spend_meta["status"], diagnostics=list(policy.diagnostics))
    spend_meta["path"] = billing_policy_path or str(spend_path)
    sources["billingPolicy"] = spend_meta
    rows = inventory(router, panel, sources)
    invalid_sources = {r["source"] for r in rows if not identity_parts(r["identity"])}
    for source in invalid_sources:
        sources[source]["status"] = "invalid"
        report["findings"].append({"severity": "error", "kind": "config", "source": source,
                                   "message": "Malformed configured model identity; source excluded."})
    rows = [r for r in rows if r["source"] not in invalid_sources]
    for row in rows:
        row["config"] = sources[row["source"]]["path"]
        row["sourceSha256"] = sources[row["source"]].get("sha256")
        row["facts"] = model_facts(row["identity"], catalogs, sources) if row["resolution"] == "exact" else None
        row["spendCoverage"] = spend_coverage(row["identity"], policy, now, spend, spend_meta["status"])
    for configured in report["configuredModels"]:
        if configured["source"] == "model-tier-router":
            configured["metered"], configured["policyBasis"], configured["consent"] = router_policy(router, configured["model"])
    evidence = {}
    evidence_meta = {"status": "not-supplied"}
    if evidence_path:
        evidence, evidence_meta = snapshot(evidence_path, MAX_EVIDENCE_BYTES)
        if evidence_meta["status"] == "ok" and not validate_evidence(evidence, now):
            evidence_meta["status"] = "invalid-or-stale"
        if evidence_meta["status"] != "ok":
            evidence = {}
    sources["releaseEvidence"] = evidence_meta
    subscriptions = panel.get("subscriptionRoutes", {})
    valid_subscriptions = isinstance(subscriptions, dict) and all(
        agent in CLI_CATALOG and isinstance(models, list) and all(text(model, 512) for model in models)
        for agent, models in subscriptions.items())
    if not valid_subscriptions:
        report["findings"].append({"severity": "error", "kind": "config", "source": "second-opinion",
                                   "message": "subscriptionRoutes must contain named CLI model lists."})
        sources["consensusConfig"]["status"] = "invalid"
        evidence = {}
    recommendations = previews(evidence, rows, router, panel, spend, policy, catalogs, sources, now)
    for recommendation in recommendations:
        for proposed in recommendation["changes"]:
            proposed["config"] = sources[proposed["source"]]["path"]
            proposed["sourceSha256"] = sources[proposed["source"]].get("sha256")
    assessments = []
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["identity"]].append(row)
    for identity, locations in sorted(grouped.items()):
        assessments.append({"identity": identity, "locations": [{k: r[k] for k in ("config", "path", "usage")} for r in locations],
                            "assessment": "native-resolution" if locations[0]["resolution"] != "exact" else "configured; successor compatibility requires reviewed evidence"})
    candidates = discover(rows, catalogs, sources)
    leads = discovery_leads(rows, candidates)
    reviewed = {(item["from"], item["to"]) for item in recommendations}
    unreviewed_leads = [item for item in leads if (item["from"], item["to"]) not in reviewed]
    findings = report["findings"]
    if policy.status != "complete":
        findings.append({"severity": "review", "kind": "spend-policy", "message": "Some spend-reporting rules could not be read or validated. This concerns reporting, not an amount owed."})
    for identity, locations in sorted(grouped.items()):
        if any(r.get("policyBasis") in {"unknown", "invalid"} for r in locations):
            findings.append({"severity": "review", "kind": "router-policy-unknown", "model": identity,
                             "message": "Exact global billing/consent policy is missing or invalid; runtime decision required."})
        if locations[0]["spendCoverage"]["billing"] == "unknown":
            coverage = locations[0]["spendCoverage"]
            findings.append({"severity": "review", "kind": "spend-uncovered", "model": identity,
                             "reason": coverage["reason"], "message": coverage["explanation"]})
    if evidence_meta["status"] not in {"ok", "not-supplied"}:
        findings.append({"severity": "error", "kind": "release-evidence", "message": "Evidence file is missing, invalid, oversized or older than seven days."})
    failed_sources = [name for name in ("piCatalog", "modelsDev", "openRouter") if sources[name]["status"] != "ok"]
    refresh_failed = refresh["status"] not in {"ok", "not-requested"}
    if refresh_failed:
        findings.append({"severity": "error", "kind": "refresh", "message": "Refresh did not complete; catalog freshness is unproven.", "status": refresh["status"]})
    repair = any(sources[name]["status"] != "ok" for name in ("routerConfig", "consensusConfig"))
    unknown_models = sorted({r["identity"] for r in rows if r["resolution"] == "exact" and r.get("enabled") is not False
                             and (r["facts"]["liveFound"] is None or (not r["identity"].startswith("local/") and r["facts"]["piAvailable"] is None))})
    incomplete_reasons = (["Unreviewed discovery leads require authoritative compatibility evidence."] if unreviewed_leads else [])
    if unknown_models:
        incomplete_reasons.append("Model evidence is unknown for: " + ", ".join(unknown_models))
    review = repair or policy.status != "complete" or any(f["kind"] in {"router-policy-unknown", "spend-uncovered", "pi-unavailable", "live-missing", "openrouter-missing", "openrouter-expiration"} for f in findings) or bool(recommendations)
    verdict = "REVIEW CONFIG" if review else "CURRENT"
    if failed_sources or refresh_failed or incomplete_reasons or evidence_meta["status"] not in {"ok", "not-supplied"}:
        verdict = "REVIEW CONFIG" if repair else "INCOMPLETE EVIDENCE"
    if report["piUpdateAvailable"] and any(f["kind"] == "pi-unavailable" for f in findings):
        verdict = "UPDATE PI FIRST"
    refresh["nativeCompleted"] = refresh["status"] == "ok"
    refresh["fresh"] = refresh["fresh"] and sources["piCatalog"]["status"] == "ok"
    report.update(schemaVersion=2, generatedAt=now.isoformat().replace("+00:00", "Z"),
                  readOnly=not refresh["attempted"], refresh=refresh, configurationInventory=rows,
                  catalogCandidates=candidates, discoveryLeads=leads, migrationAssessments=assessments,
                  recommendations=recommendations, verdict=verdict, incompleteSources=failed_sources,
                  incompleteReasons=incomplete_reasons,
                  interaction=interaction_plan(sources, leads, recommendations, assessments, candidates, findings),
                  handoff={"companionAvailable": True, "companion": "scripts/apply_migration.py",
                           "implementationOwner": "attended companion applier",
                           "authorization": "Preview is not approval; exact changes, each file and consent-sensitive allowlists require separate current-run confirmation.",
                           "preserve": "All unrelated fields, old model keys, consent and historical billing intervals.",
                           "previewOnly": True})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--router", required=True)
    parser.add_argument("--panel", required=True)
    parser.add_argument("--billing-policy", required=True)
    parser.add_argument("--billing-policy-path")
    parser.add_argument("--evidence")
    parser.add_argument("--evidence-origin", choices=["stdin"])
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--openrouter", required=True)
    parser.add_argument("--pi-catalog", required=True)
    parser.add_argument("--refresh-result", required=True)
    args = parser.parse_args()
    report = json.load(sys.stdin)
    dev = json.loads(Path(args.catalog).read_text())
    opened = {m["id"]: m for m in json.loads(Path(args.openrouter).read_text())["data"] if isinstance(m, dict) and isinstance(m.get("id"), str)}
    pi = {f"{m['provider']}/{m['model']}" for m in json.loads(Path(args.pi_catalog).read_text())}
    refresh_result = json.loads(Path(args.refresh_result).read_text())
    result = enrich(report, args.router, args.panel, args.billing_policy, args.evidence,
                    (dev, opened, pi), refresh_result, datetime.now(timezone.utc), args.billing_policy_path)
    if args.evidence_origin:
        result["sources"]["releaseEvidence"]["path"] = args.evidence_origin
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
