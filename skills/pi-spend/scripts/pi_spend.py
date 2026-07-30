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
from datetime import datetime, timedelta, timezone

SCHEMA_VERSION = 1
DEFAULT_SESSIONS_DIR = "~/.pi/agent/sessions"
DEFAULT_ROUTER_CONFIG = "~/.pi/agent/model-tier-router.json"
PERIODS = ("today", "week", "month", "all")

METERED = "metered"
SUBSCRIPTION = "subscription"
UNKNOWN = "unknown"


class Row:
    __slots__ = ("provider", "model", "billing", "requests", "input", "cache_read",
                 "cache_write", "output", "reasoning", "cost", "cost_missing")

    def __init__(self, provider, model, billing):
        self.provider = provider
        self.model = model
        self.billing = billing
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
            "requests": self.requests,
            "input": self.input,
            "cacheRead": self.cache_read,
            "cacheWrite": self.cache_write,
            "output": self.output,
            "reasoning": self.reasoning,
            "estimatedCost": round(self.cost, 6),
            "responsesMissingCost": self.cost_missing,
        }


def load_billing_policies(path):
    """Map 'provider/model' to a billing class using the user's router config."""
    expanded = os.path.expanduser(path)
    try:
        with open(expanded, encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError):
        return {}
    policies = config.get("modelPolicies")
    if not isinstance(policies, dict):
        return {}
    classes = {}
    for key, policy in policies.items():
        if not isinstance(policy, dict) or "metered" not in policy:
            continue
        classes[key] = METERED if policy["metered"] else SUBSCRIPTION
    return classes


def classify(provider, model, policies):
    for candidate in (f"{provider}/{model}", model):
        if candidate in policies:
            return policies[candidate]
    return UNKNOWN


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
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(tzinfo)
        except ValueError:
            return None
    return None


def iter_session_files(root):
    for dirpath, _, filenames in os.walk(root):
        for name in sorted(filenames):
            if name.endswith(".jsonl"):
                yield os.path.join(dirpath, name)


def collect(sessions_dir, policies, now, tzinfo):
    starts = period_starts(now)
    totals = {period: {} for period in PERIODS}
    stats = {"files": 0, "responses": 0, "duplicates": 0, "unparsable": 0, "undated": 0}
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

                provider = str(message.get("provider") or "unknown")
                model = str(message.get("model") or "unknown")
                billing = classify(provider, model, policies)
                cost_block = usage.get("cost")
                cost = cost_block.get("total") if isinstance(cost_block, dict) else None
                if not isinstance(cost, (int, float)):
                    cost = None
                stats["responses"] += 1

                key = f"{provider}/{model}"
                for period, start in starts.items():
                    if when < start:
                        continue
                    bucket = totals[period]
                    if key not in bucket:
                        bucket[key] = Row(provider, model, billing)
                    bucket[key].add(usage, cost)

    return totals, starts, stats


def summarise(rows):
    by_class = defaultdict(float)
    for row in rows:
        by_class[row.billing] += row.cost
    return by_class


def render_text(totals, starts, stats, periods, metered_only, now):
    out = []
    out.append(f"Pi model spend estimate  ·  generated {now:%Y-%m-%d %H:%M %Z}")
    out.append(
        f"Sources: {stats['files']} session files, {stats['responses']} responses"
        f" ({stats['duplicates']} duplicate, {stats['unparsable']} unparsable,"
        f" {stats['undated']} undated)"
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

        rows.sort(key=lambda r: (-r.cost, r.key))
        header = f"{'provider/model':<38} {'bill':<12} {'reqs':>6} {'input':>12} {'cacheRead':>13} {'output':>10} {'est USD':>9}"
        out.append(header)
        out.append("-" * len(header))
        for row in rows:
            out.append(
                f"{row.key:<38} {row.billing:<12} {row.requests:>6} {row.input:>12,}"
                f" {row.cache_read:>13,} {row.output:>10,} {row.cost:>9.2f}"
            )
        by_class = summarise(rows)
        out.append("-" * len(header))
        out.append(f"{'TOTAL':<38} {'':<12} {'':>6} {'':>12} {'':>13} {'':>10} {sum(by_class.values()):>9.2f}")
        for billing in (METERED, SUBSCRIPTION, UNKNOWN):
            if billing in by_class:
                out.append(f"{'  ' + billing:<38} {'':<12} {'':>6} {'':>12} {'':>13} {'':>10} {by_class[billing]:>9.2f}")
        missing = sum(row.cost_missing for row in rows)
        if missing:
            out.append(f"  {missing} response(s) recorded no cost and are excluded from the estimate")

    out.append("")
    out.append("Estimates are Pi's own catalog pricing per response, not a provider invoice.")
    out.append("Billing class comes from the local model-tier-router policy; 'unknown' means unclassified there.")
    return "\n".join(out)


def render_json(totals, starts, stats, periods, metered_only, now):
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": now.isoformat(),
        "timezone": str(now.tzname()),
        "source": "pi-sessions",
        "costAuthority": "pi-catalog-estimate",
        "stats": stats,
        "periods": {},
    }
    for period in periods:
        rows = list(totals[period].values())
        if metered_only:
            rows = [row for row in rows if row.billing == METERED]
        rows.sort(key=lambda r: (-r.cost, r.key))
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
                        help="Show only models the router policy marks as metered.")
    parser.add_argument("--sessions-dir", default=DEFAULT_SESSIONS_DIR,
                        help=f"Pi sessions root (default: {DEFAULT_SESSIONS_DIR}).")
    parser.add_argument("--router-config", default=DEFAULT_ROUTER_CONFIG,
                        help=f"Router config used for billing classification (default: {DEFAULT_ROUTER_CONFIG}).")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    sessions_dir = os.path.expanduser(args.sessions_dir)
    if not os.path.isdir(sessions_dir):
        print(f"ERROR: Pi sessions directory not found: {sessions_dir}", file=sys.stderr)
        return 2

    now = datetime.now().astimezone()
    policies = load_billing_policies(args.router_config)
    totals, starts, stats = collect(sessions_dir, policies, now, now.tzinfo)
    periods = tuple(dict.fromkeys(args.period)) if args.period else PERIODS

    renderer = render_json if args.json else render_text
    print(renderer(totals, starts, stats, periods, args.metered_only, now))
    return 0


if __name__ == "__main__":
    sys.exit(main())
