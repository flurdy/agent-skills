#!/usr/bin/env python3
"""Report Pi model cost estimates by period, grouped by provider and model.

Reads Pi session transcripts only. Cost values are Pi's own catalog estimates
recorded per assistant response, not provider invoices.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import TZPATH, ZoneInfo, ZoneInfoNotFoundError

SCHEMA_VERSION = 2
BILLING_POLICY_SCHEMA_VERSION = 1
DEFAULT_SESSIONS_DIR = "~/.pi/agent/sessions"
DEFAULT_BILLING_POLICY = "~/.pi/agent/pi-spend-billing-policy.json"
PERIODS = ("today", "week", "month", "all")

METERED = "metered"
SUBSCRIPTION = "subscription"
UNKNOWN = "unknown"
EFFECTIVE_POLICY = "effective-dated-policy"
LEGACY_POLICY = "legacy-current-router-policy"
UNKNOWN_POLICY = "unknown"
MAX_POLICY_DIAGNOSTICS = 20


@dataclass(frozen=True)
class BillingInterval:
    effective_from: datetime
    effective_until: datetime | None
    billing: str


@dataclass(frozen=True)
class BillingPolicy:
    source: str
    status: str
    diagnostics: tuple[str, ...]
    models: dict[str, tuple[BillingInterval, ...]]

    def classify(self, provider, model, when):
        for interval in self.models.get(f"{provider}/{model}", ()):
            if when >= interval.effective_from and (
                interval.effective_until is None or when < interval.effective_until
            ):
                return interval.billing, self.source
        return UNKNOWN, UNKNOWN_POLICY


def policy_diagnostic(diagnostics, code):
    if code not in diagnostics and len(diagnostics) < MAX_POLICY_DIAGNOSTICS:
        diagnostics.append(code)


def parse_utc_timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed.astimezone(timezone.utc)


def exact_model_key(value):
    return (
        isinstance(value, str)
        and "/" in value
        and all(part and not any(character.isspace() for character in part)
                for part in value.split("/", 1))
    )


def missing_policy(source, code):
    return BillingPolicy(source, "missing", (code,), {})


def reject_json_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def strict_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json_file(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(
            handle,
            object_pairs_hook=strict_json_object,
            parse_constant=reject_json_constant,
        )


def load_billing_policy(path):
    expanded = os.path.expanduser(path)
    try:
        payload = read_json_file(expanded)
    except FileNotFoundError:
        return missing_policy(EFFECTIVE_POLICY, "billing-policy-missing")
    except (OSError, ValueError):
        return BillingPolicy(EFFECTIVE_POLICY, "invalid", ("billing-policy-invalid",), {})
    if (
        not isinstance(payload, dict)
        or type(payload.get("schemaVersion")) is not int
        or payload["schemaVersion"] != BILLING_POLICY_SCHEMA_VERSION
    ):
        return BillingPolicy(EFFECTIVE_POLICY, "invalid", ("billing-policy-invalid",), {})
    configured_models = payload.get("models")
    if not isinstance(configured_models, dict):
        return BillingPolicy(EFFECTIVE_POLICY, "invalid", ("billing-policy-invalid",), {})

    diagnostics = []
    models = {}
    for key, entries in configured_models.items():
        if not exact_model_key(key) or not isinstance(entries, list) or not entries:
            policy_diagnostic(diagnostics, "invalid-model-policy")
            continue
        intervals = []
        invalid = False
        for entry in entries:
            if (
                not isinstance(entry, dict)
                or not {"effectiveFrom", "effectiveUntil", "billing"}.issubset(entry)
                or not isinstance(entry.get("billing"), str)
                or entry["billing"] not in {METERED, SUBSCRIPTION}
            ):
                invalid = True
                break
            effective_from = parse_utc_timestamp(entry.get("effectiveFrom"))
            effective_until = (
                None if entry.get("effectiveUntil") is None
                else parse_utc_timestamp(entry.get("effectiveUntil"))
            )
            if effective_from is None or (
                entry.get("effectiveUntil") is not None and effective_until is None
            ) or (effective_until is not None and effective_until <= effective_from):
                invalid = True
                break
            intervals.append(BillingInterval(
                effective_from, effective_until, entry["billing"]
            ))
        if invalid:
            policy_diagnostic(diagnostics, "invalid-interval")
            continue
        intervals.sort(key=lambda interval: interval.effective_from)
        overlaps = any(
            previous.effective_until is None
            or current.effective_from < previous.effective_until
            for previous, current in zip(intervals, intervals[1:], strict=False)
        )
        if overlaps:
            policy_diagnostic(diagnostics, "overlapping-intervals")
            continue
        models[key] = tuple(intervals)
    return BillingPolicy(
        EFFECTIVE_POLICY,
        "partial" if diagnostics else "complete",
        tuple(diagnostics),
        models,
    )


def load_legacy_router_policy(path):
    expanded = os.path.expanduser(path)
    try:
        payload = read_json_file(expanded)
    except FileNotFoundError:
        return missing_policy(LEGACY_POLICY, "legacy-router-policy-missing")
    except (OSError, ValueError):
        return BillingPolicy(LEGACY_POLICY, "invalid", ("legacy-router-policy-invalid",), {})
    configured = payload.get("modelPolicies") if isinstance(payload, dict) else None
    if not isinstance(configured, dict):
        return BillingPolicy(LEGACY_POLICY, "invalid", ("legacy-router-policy-invalid",), {})
    diagnostics = []
    models = {}
    beginning = datetime.min.replace(tzinfo=timezone.utc)
    for key, policy in configured.items():
        if not exact_model_key(key) or not isinstance(policy, dict) or not isinstance(policy.get("metered"), bool):
            policy_diagnostic(diagnostics, "invalid-legacy-model-policy")
            continue
        billing = METERED if policy["metered"] else SUBSCRIPTION
        models[key] = (BillingInterval(beginning, None, billing),)
    return BillingPolicy(
        LEGACY_POLICY,
        "partial" if diagnostics else "complete",
        tuple(diagnostics),
        models,
    )


class Row:
    __slots__ = ("provider", "model", "billing", "billing_source", "requests",
                 "input", "cache_read", "cache_write", "output", "reasoning",
                 "cost", "cost_missing")

    def __init__(self, provider, model, billing, billing_source):
        self.provider = provider
        self.model = model
        self.billing = billing
        self.billing_source = billing_source
        self.requests = 0
        self.input = 0
        self.cache_read = 0
        self.cache_write = 0
        self.output = 0
        self.reasoning = 0
        self.cost = 0.0
        self.cost_missing = 0

    @property
    def key(self):
        return f"{self.provider}/{self.model}"

    def add(self, usage, cost):
        self.requests += 1
        self.input += usage.get("input") or 0
        self.cache_read += usage.get("cacheRead") or 0
        self.cache_write += usage.get("cacheWrite") or 0
        self.output += usage.get("output") or 0
        self.reasoning += usage.get("reasoning") or 0
        if cost is None:
            self.cost_missing += 1
        else:
            self.cost += cost

    def as_dict(self):
        return {
            "provider": self.provider,
            "model": self.model,
            "billing": self.billing,
            "billingSource": self.billing_source,
            "requests": self.requests,
            "input": self.input,
            "cacheRead": self.cache_read,
            "cacheWrite": self.cache_write,
            "output": self.output,
            "reasoning": self.reasoning,
            "estimatedCost": round(self.cost, 6),
            "responsesMissingCost": self.cost_missing,
        }


def local_timezone(
    environment=None,
    localtime_path="/etc/localtime",
    timezone_path="/etc/timezone",
    zoneinfo_paths=TZPATH,
):
    environment = os.environ if environment is None else environment
    candidates = []
    configured = environment.get("TZ")
    if configured:
        candidates.append(configured.removeprefix(":"))
    try:
        configured_file = Path(timezone_path).read_text(encoding="utf-8").strip()
        if configured_file:
            candidates.append(configured_file)
    except OSError:
        pass

    resolved_localtime = None
    try:
        resolved_localtime = Path(localtime_path).resolve(strict=True)
    except OSError:
        pass
    if resolved_localtime is not None:
        for root_value in zoneinfo_paths:
            try:
                relative = resolved_localtime.relative_to(Path(root_value).resolve())
                candidates.append(relative.as_posix())
                break
            except (OSError, ValueError):
                continue
    for candidate in candidates:
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            continue

    try:
        localtime = Path(localtime_path).read_bytes()
    except OSError:
        localtime = None
    if localtime is not None:
        for root_value in zoneinfo_paths:
            root = Path(root_value)
            try:
                files = sorted(path for path in root.rglob("*") if path.is_file())
            except OSError:
                continue
            for path in files[:5000]:
                try:
                    if path.stat().st_size != len(localtime) or path.read_bytes() != localtime:
                        continue
                    return ZoneInfo(path.relative_to(root).as_posix())
                except (OSError, ValueError, ZoneInfoNotFoundError):
                    continue
    return datetime.now().astimezone().tzinfo or timezone.utc


def period_starts(now):
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "today": midnight,
        "week": midnight - timedelta(days=midnight.weekday()),
        "month": midnight.replace(day=1),
        "all": datetime.fromtimestamp(0, tz=timezone.utc),
    }


def parse_timestamp(record, message, tzinfo):
    raw = record.get("timestamp") or message.get("timestamp")
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw / 1000, tz=timezone.utc).astimezone(tzinfo)
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(tzinfo)
    return None


def iter_session_files(root):
    for dirpath, _, filenames in os.walk(root):
        for name in sorted(filenames):
            if name.endswith(".jsonl"):
                yield os.path.join(dirpath, name)


def collect(sessions_dir, policy, now, tzinfo):
    starts = period_starts(now)
    totals = {period: {} for period in PERIODS}
    stats = {
        "files": 0,
        "responses": 0,
        "duplicates": 0,
        "unparsable": 0,
        "undated": 0,
        "future": 0,
        "billingUnknownResponses": 0,
        "legacyProjectedResponses": 0,
    }
    seen = set()

    for path in iter_session_files(sessions_dir):
        stats["files"] += 1
        try:
            handle = open(path, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with handle:
            for line in handle:
                if '"assistant"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    stats["unparsable"] += 1
                    continue
                if not isinstance(record, dict):
                    stats["unparsable"] += 1
                    continue
                message = record.get("message")
                if not isinstance(message, dict) or message.get("role") != "assistant":
                    continue
                usage = message.get("usage")
                if not isinstance(usage, dict):
                    continue
                response_id = message.get("responseId")
                if response_id:
                    if response_id in seen:
                        stats["duplicates"] += 1
                        continue
                    seen.add(response_id)
                when = parse_timestamp(record, message, tzinfo)
                if when is None:
                    stats["undated"] += 1
                    continue
                if when > now:
                    stats["future"] += 1
                    continue

                provider_value = message.get("provider")
                model_value = message.get("model")
                valid_identity = (
                    isinstance(provider_value, str)
                    and bool(provider_value)
                    and isinstance(model_value, str)
                    and bool(model_value)
                )
                provider = provider_value if isinstance(provider_value, str) and provider_value else "unknown"
                model = model_value if isinstance(model_value, str) and model_value else "unknown"
                billing, billing_source = (
                    policy.classify(provider, model, when)
                    if valid_identity
                    else (UNKNOWN, UNKNOWN_POLICY)
                )
                cost_block = usage.get("cost")
                cost = cost_block.get("total") if isinstance(cost_block, dict) else None
                if not isinstance(cost, (int, float)):
                    cost = None
                stats["responses"] += 1
                if billing == UNKNOWN:
                    stats["billingUnknownResponses"] += 1
                if billing_source == LEGACY_POLICY:
                    stats["legacyProjectedResponses"] += 1

                key = (provider, model, billing, billing_source)
                for period, start in starts.items():
                    if when < start:
                        continue
                    bucket = totals[period]
                    if key not in bucket:
                        bucket[key] = Row(provider, model, billing, billing_source)
                    bucket[key].add(usage, cost)

    return totals, starts, stats


def summarise(rows):
    by_class = defaultdict(float)
    for row in rows:
        by_class[row.billing] += row.cost
    return by_class


def billing_policy_payload(policy):
    return {
        "source": policy.source,
        "status": policy.status,
        "diagnostics": list(policy.diagnostics),
    }


def render_text(totals, starts, stats, periods, metered_only, now, policy):
    out = []
    out.append(f"Pi model spend estimate  ·  generated {now:%Y-%m-%d %H:%M %Z}")
    out.append(
        f"Sources: {stats['files']} session files, {stats['responses']} responses"
        f" ({stats['duplicates']} duplicate, {stats['unparsable']} unparsable,"
        f" {stats['undated']} undated, {stats['future']} future)"
    )
    diagnostic = ",".join(policy.diagnostics) if policy.diagnostics else "none"
    out.append(
        f"Billing policy: {policy.source} ({policy.status}; diagnostics: {diagnostic})"
    )
    out.append(
        f"Classification: {stats['billingUnknownResponses']} unknown, "
        f"{stats['legacyProjectedResponses']} legacy current-policy projection"
    )

    for period in periods:
        rows = [row for row in totals[period].values()]
        if metered_only:
            rows = [row for row in rows if row.billing == METERED]
        label = "all recorded history" if period == "all" else f"since {starts[period]:%Y-%m-%d %H:%M %Z}"
        out.append("")
        out.append(f"== {period.upper()} ==  ({label})")
        if not rows:
            out.append("  no recorded responses")
            continue

        rows.sort(key=lambda r: (-r.cost, r.key, r.billing, r.billing_source))
        header = (
            f"{'provider/model':<38} {'bill':<12} {'policy':<28} {'reqs':>6}"
            f" {'input':>12} {'cacheRead':>13} {'output':>10} {'est USD':>9}"
        )
        out.append(header)
        out.append("-" * len(header))
        for row in rows:
            out.append(
                f"{row.key:<38} {row.billing:<12} {row.billing_source:<28}"
                f" {row.requests:>6} {row.input:>12,} {row.cache_read:>13,}"
                f" {row.output:>10,} {row.cost:>9.2f}"
            )
        by_class = summarise(rows)
        out.append("-" * len(header))
        out.append(
            f"{'TOTAL':<38} {'':<12} {'':<28} {'':>6} {'':>12} {'':>13}"
            f" {'':>10} {sum(by_class.values()):>9.2f}"
        )
        for billing in (METERED, SUBSCRIPTION, UNKNOWN):
            if billing in by_class:
                out.append(
                    f"{'  ' + billing:<38} {'':<12} {'':<28} {'':>6} {'':>12}"
                    f" {'':>13} {'':>10} {by_class[billing]:>9.2f}"
                )
        missing = sum(row.cost_missing for row in rows)
        if missing:
            out.append(f"  {missing} response(s) recorded no cost and are excluded from the estimate")

    out.append("")
    out.append("Estimates are Pi's own catalog pricing per response, not a provider invoice.")
    if policy.source == LEGACY_POLICY:
        out.append("LEGACY: classifications are current router-policy projections and may relabel history.")
    else:
        out.append("Billing class comes from the effective-dated local policy; uncovered responses remain unknown.")
    return "\n".join(out)


def render_json(totals, starts, stats, periods, metered_only, now, policy):
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": now.isoformat(),
        "timezone": str(now.tzname()),
        "source": "pi-sessions",
        "costAuthority": "pi-catalog-estimate",
        "billingPolicy": billing_policy_payload(policy),
        "stats": stats,
        "periods": {},
    }
    for period in periods:
        rows = list(totals[period].values())
        if metered_only:
            rows = [row for row in rows if row.billing == METERED]
        rows.sort(key=lambda r: (-r.cost, r.key, r.billing, r.billing_source))
        by_class = summarise(rows)
        payload["periods"][period] = {
            "start": None if period == "all" else starts[period].isoformat(),
            "end": now.isoformat(),
            "totalEstimatedCost": round(sum(by_class.values()), 6),
            "estimatedCostByBilling": {k: round(v, 6) for k, v in sorted(by_class.items())},
            "rows": [row.as_dict() for row in rows],
        }
    return json.dumps(payload, indent=2)


def build_parser():
    parser = argparse.ArgumentParser(description="Report Pi model spend estimates by period.")
    parser.add_argument("--period", choices=PERIODS, action="append",
                        help="Limit output to a period; repeatable. Defaults to all four.")
    parser.add_argument("--json", action="store_true", help="Emit normalized JSON instead of a table.")
    parser.add_argument("--metered-only", action="store_true",
                        help="Show only responses classified as metered.")
    parser.add_argument("--sessions-dir", default=DEFAULT_SESSIONS_DIR,
                        help=f"Pi sessions root (default: {DEFAULT_SESSIONS_DIR}).")
    billing_source = parser.add_mutually_exclusive_group()
    billing_source.add_argument(
        "--billing-policy",
        help=f"Effective-dated billing policy (default: {DEFAULT_BILLING_POLICY}).",
    )
    billing_source.add_argument(
        "--router-config",
        help="LEGACY: explicitly project current router modelPolicies across history.",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    sessions_dir = os.path.expanduser(args.sessions_dir)
    if not os.path.isdir(sessions_dir):
        print(f"ERROR: Pi sessions directory not found: {sessions_dir}", file=sys.stderr)
        return 2

    timezone_info = local_timezone()
    now = datetime.now(timezone_info)
    policy = (
        load_legacy_router_policy(args.router_config)
        if args.router_config
        else load_billing_policy(args.billing_policy or DEFAULT_BILLING_POLICY)
    )
    totals, starts, stats = collect(sessions_dir, policy, now, timezone_info)
    periods = tuple(dict.fromkeys(args.period)) if args.period else PERIODS

    renderer = render_json if args.json else render_text
    print(renderer(totals, starts, stats, periods, args.metered_only, now, policy))
    return 0


if __name__ == "__main__":
    sys.exit(main())
