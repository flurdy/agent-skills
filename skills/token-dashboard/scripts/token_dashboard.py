#!/usr/bin/env python3
"""Read-only token telemetry collector for supported coding harnesses."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA_VERSION = "1"
OPENROUTER_BASE_URL = "https://openrouter.ai"
USER_AGENT = "flurdy-token-dashboard/1.0"
MAX_REMOTE_BYTES = 2 * 1024 * 1024
MAX_LOCAL_LINE_BYTES = 1024 * 1024
REMOTE_ROW_LIMIT = 1000
TOKEN_FIELDS = ("input", "output", "cacheRead", "cacheWrite", "reasoning", "total")
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+@ -]{0,119}\Z")
REMOTE_METRICS = (
    "request_count",
    "tokens_total",
    "tokens_prompt",
    "tokens_completion",
    "reasoning_tokens",
    "cached_tokens",
)


@dataclass
class Event:
    source: str
    harness: str
    timestamp: Optional[dt.datetime]
    session: str
    aliases: set[str]
    parent_session: Optional[str]
    provider: Optional[str]
    model: Optional[str]
    agent: str
    usage: dict[str, Optional[int]]
    exactness: str = "exact"
    semantics: dict[str, bool] = field(default_factory=dict)


@dataclass
class ScanResult:
    source: str
    harness: str
    events: list[Event] = field(default_factory=list)
    status: str = "ok"
    detail: str = "Local telemetry collected."
    exactness: str = "exact"
    malformed: int = 0
    conflicts: int = 0
    invalid_timestamps: int = 0
    file_errors: int = 0


def safe_text(value: Any, limit: int = 160) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    sanitized = "".join("?" if unicodedata.category(char) in ("Cc", "Cf") else char for char in value)
    return sanitized.strip()[:limit] or None


def safe_identifier(value: Any, limit: int = 120) -> Optional[str]:
    text = safe_text(value, limit)
    return text if text and IDENTIFIER_RE.fullmatch(text) else None


def safe_agent(value: Any) -> Optional[str]:
    return safe_identifier(value, 80)


def internal_hash(*parts: Any) -> str:
    encoded = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8", "replace")).hexdigest()


def parse_time(value: Any) -> Optional[dt.datetime]:
    if isinstance(value, (int, float)):
        try:
            result = dt.datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value, dt.timezone.utc)
            return result
        except (ValueError, OSError, OverflowError):
            return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def as_token(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    return None


def as_remote_count(value: Any) -> Optional[int]:
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        try:
            return int(value)
        except ValueError:
            return None
    return as_token(value)


def first(mapping: Any, *names: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def load_json_lines(path: Path, result: ScanResult) -> Iterable[tuple[int, dict[str, Any]]]:
    try:
        with path.open("rb") as stream:
            number = 0
            while True:
                raw = stream.readline(MAX_LOCAL_LINE_BYTES + 1)
                if not raw:
                    break
                number += 1
                if len(raw) > MAX_LOCAL_LINE_BYTES:
                    while raw and not raw.endswith(b"\n"):
                        raw = stream.readline(MAX_LOCAL_LINE_BYTES + 1)
                    yield number, {}
                    continue
                try:
                    value = json.loads(raw.decode("utf-8", "replace"))
                except (json.JSONDecodeError, UnicodeError, ValueError):
                    yield number, {}
                    continue
                yield number, value if isinstance(value, dict) else {}
    except OSError:
        result.file_errors += 1


def jsonl_files(root: Path, result: ScanResult) -> list[Path]:
    if root.is_symlink():
        result.file_errors += 1
        return []
    if not root.is_dir():
        return []
    try:
        resolved_root = root.resolve(strict=True)
        candidates = sorted(root.rglob("*.jsonl"))
    except OSError:
        result.file_errors += 1
        return []
    files = []
    for path in candidates:
        try:
            if path.is_symlink():
                result.file_errors += 1
                continue
            resolved = path.resolve(strict=True)
            resolved.relative_to(resolved_root)
            if not resolved.is_file():
                result.file_errors += 1
                continue
        except (OSError, ValueError):
            result.file_errors += 1
            continue
        files.append(path)
    return files


def path_session(root: Path, path: Path, source: str) -> tuple[str, str]:
    """Return opaque internal file and parent-run grouping keys."""
    try:
        relative = path.relative_to(root)
        parts = relative.parts
    except ValueError:
        parts = (path.name,)
    lowered = [part.lower() for part in parts]
    marker = next((i for i, part in enumerate(lowered) if part in ("subagents", "extra-agents", "agents")), None)
    if marker is not None and marker > 0:
        group_parts = parts[:marker]
    else:
        group_parts = parts[:-1] + (Path(parts[-1]).stem,)
    return internal_hash(source, parts), internal_hash(source, group_parts)


def merge_duplicate(existing: Event, candidate: Event) -> bool:
    comparisons = [
        (candidate.usage[name] > existing.usage[name]) - (candidate.usage[name] < existing.usage[name])
        for name in TOKEN_FIELDS
        if existing.usage.get(name) is not None and candidate.usage.get(name) is not None
    ]
    conflict = any(value > 0 for value in comparisons) and any(value < 0 for value in comparisons)
    for name in TOKEN_FIELDS:
        old = existing.usage.get(name)
        new = candidate.usage.get(name)
        if new is not None and (old is None or new > old):
            existing.usage[name] = new
    if candidate.timestamp and (existing.timestamp is None or candidate.timestamp > existing.timestamp):
        existing.timestamp = candidate.timestamp
    existing.aliases.update(candidate.aliases)
    if existing.provider is None:
        existing.provider = candidate.provider
    if existing.model is None:
        existing.model = candidate.model
    if conflict:
        existing.exactness = "partial"
    return conflict


def claude_group(root: Path, path: Path) -> str:
    return path_session(root, path, "claude")[1]


def pi_group(root: Path, path: Path) -> str:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = (path.name,)
    if path.name == "session.jsonl" and len(parts) >= 3:
        alias_parts = parts[:2]
    else:
        alias_parts = parts[:-1] + (Path(parts[-1]).stem,)
    return internal_hash("pi-parent", alias_parts)


def collect_claude(root: Path) -> ScanResult:
    result = ScanResult("claude-local", "Claude Code")
    files = jsonl_files(root, result)
    if not root.exists():
        result.status, result.detail, result.exactness = "unavailable", "Claude telemetry root is missing; allowance and billing quota are unavailable.", "unavailable"
        return result
    if not files:
        if result.file_errors:
            result.status, result.exactness = "partial", "partial"
            result.detail = f"Claude telemetry had {result.file_errors} rejected/unreadable files; local telemetry is not billing or quota."
        else:
            result.status, result.detail = "empty", "No Claude JSONL telemetry found; local telemetry is not billing or quota."
        return result

    seen: dict[str, Event] = {}
    for path in files:
        group_key = claude_group(root, path)
        is_child = any(part.lower() in ("subagents", "extra-agents", "agents") for part in path.parts)
        for _, row in load_json_lines(path, result):
            if not row:
                result.malformed += 1
                continue
            message = row.get("message")
            if row.get("type") != "assistant" or not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
                continue
            usage_raw = message["usage"]
            usage = {
                "input": as_token(first(usage_raw, "input_tokens")),
                "output": as_token(first(usage_raw, "output_tokens")),
                "cacheRead": as_token(first(usage_raw, "cache_read_input_tokens")),
                "cacheWrite": as_token(first(usage_raw, "cache_creation_input_tokens")),
                "reasoning": None,
                "total": None,
            }
            aliases = {group_key}
            for candidate_id in (row.get("sessionId"), message.get("sessionId")):
                if isinstance(candidate_id, str) and candidate_id:
                    aliases.add(candidate_id)
            message_id = safe_text(message.get("id"), 300)
            request_id = safe_text(first(row, "requestId", "request_id") or first(message, "requestId", "request_id"), 300)
            if message_id:
                dedup_key = "message:" + message_id
            elif request_id:
                dedup_key = "request:" + request_id
            else:
                dedup_key = "fallback:" + internal_hash(
                    row.get("timestamp"), row.get("sessionId"), message.get("model"),
                    first(row, "agentName", "agent_name"),
                )
            recorded_agent = safe_agent(first(row, "agentName", "agent_name") or first(message, "agentName", "agent_name"))
            timestamp = parse_time(first(row, "timestamp", "created_at") or first(message, "timestamp", "created_at"))
            if timestamp is None:
                result.invalid_timestamps += 1
            event = Event(
                source=result.source,
                harness=result.harness,
                timestamp=timestamp,
                session=group_key,
                aliases=aliases,
                parent_session=None,
                provider="anthropic",
                model=safe_identifier(message.get("model")),
                agent=recorded_agent or ("subagent" if is_child else "parent"),
                usage=usage,
                semantics={"cacheTokensExclusiveOfInput": True},
            )
            if dedup_key in seen:
                if merge_duplicate(seen[dedup_key], event):
                    result.conflicts += 1
            else:
                seen[dedup_key] = event
    result.events = list(seen.values())
    if result.malformed or result.conflicts or result.invalid_timestamps or result.file_errors:
        result.status, result.exactness = "partial", "partial"
        result.detail = f"Claude telemetry collected with {result.malformed} malformed rows, {result.conflicts} incompatible duplicate snapshots, {result.invalid_timestamps} usage rows without valid timestamps, and {result.file_errors} rejected/unreadable files; local telemetry is not billing or quota."
    else:
        result.detail = "Claude JSONL assistant usage collected; local telemetry is not billing or subscription quota."
    return result


def pi_usage(raw: dict[str, Any]) -> dict[str, Optional[int]]:
    return {
        "input": as_token(first(raw, "input", "input_tokens")),
        "output": as_token(first(raw, "output", "output_tokens")),
        "cacheRead": as_token(first(raw, "cacheRead", "cache_read", "cache_read_input_tokens")),
        "cacheWrite": as_token(first(raw, "cacheWrite", "cache_write", "cache_creation_input_tokens")),
        "reasoning": as_token(first(raw, "reasoning", "reasoningTokens", "reasoning_tokens")),
        "total": as_token(first(raw, "totalTokens", "total_tokens", "total")),
    }


def collect_pi(root: Path) -> ScanResult:
    result = ScanResult("pi-local", "Pi")
    files = jsonl_files(root, result)
    if not root.exists():
        result.status, result.detail, result.exactness = "unavailable", "Pi telemetry root is missing; allowance and billing quota are unavailable.", "unavailable"
        return result
    if not files:
        if result.file_errors:
            result.status, result.exactness = "partial", "partial"
            result.detail = f"Pi telemetry had {result.file_errors} rejected/unreadable files; local telemetry is not billing or quota."
        else:
            result.status, result.detail = "empty", "No Pi session JSONL telemetry found; local telemetry is not billing or quota."
        return result

    seen: dict[str, Event] = {}
    for path in files:
        group_key = pi_group(root, path)
        session_id: Optional[str] = None
        parent_id: Optional[str] = None
        for _, row in load_json_lines(path, result):
            if not row:
                result.malformed += 1
                continue
            if row.get("type") in ("session", "session_meta"):
                payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
                raw_session = first(payload, "id", "sessionId", "session_id")
                raw_parent = first(payload, "parentSession", "parentSessionId", "parent_session_id", "parentId")
                session_id = raw_session if isinstance(raw_session, str) and raw_session else session_id
                parent_id = raw_parent if isinstance(raw_parent, str) and raw_parent else parent_id
                continue
            message = row.get("message") if isinstance(row.get("message"), dict) else row
            if message.get("role") != "assistant" or not isinstance(message.get("usage"), dict):
                continue
            usage = pi_usage(message["usage"])
            aliases = {group_key}
            row_session = first(row, "sessionId", "session_id")
            for value in (session_id, row_session):
                if isinstance(value, str) and value:
                    aliases.add(value)
            raw_id = first(row, "id", "messageId", "message_id") or first(message, "id", "messageId", "message_id")
            if isinstance(raw_id, str) and raw_id:
                dedup_key = "id:" + raw_id
            else:
                dedup_key = "fallback:" + internal_hash(
                    first(row, "timestamp", "created_at") or first(message, "timestamp", "created_at"),
                    session_id, message.get("provider"), message.get("model"),
                )
            is_child = path.name == "session.jsonl" or len(path.relative_to(root).parts) > 2
            agent_name = safe_agent(first(row, "agentName", "agent_name") or first(message, "agentName", "agent_name"))
            timestamp = parse_time(first(row, "timestamp", "created_at") or first(message, "timestamp", "created_at"))
            if timestamp is None:
                result.invalid_timestamps += 1
            event = Event(
                source=result.source,
                harness=result.harness,
                timestamp=timestamp,
                session=session_id or group_key,
                aliases=aliases,
                parent_session=parent_id,
                provider=safe_identifier(message.get("provider")),
                model=safe_identifier(message.get("model")),
                agent=agent_name or ("child" if is_child else "parent"),
                usage=usage,
                semantics={"reasoningSubsetOfOutput": True},
            )
            if dedup_key in seen:
                if merge_duplicate(seen[dedup_key], event):
                    result.conflicts += 1
            else:
                seen[dedup_key] = event
    result.events = list(seen.values())
    if result.malformed or result.conflicts or result.invalid_timestamps or result.file_errors:
        result.status, result.exactness = "partial", "partial"
        result.detail = f"Pi telemetry collected with {result.malformed} malformed rows, {result.conflicts} incompatible duplicate snapshots, {result.invalid_timestamps} usage rows without valid timestamps, and {result.file_errors} rejected/unreadable files; local telemetry is not billing or quota."
    else:
        result.detail = "Pi assistant usage collected; reasoning is a subset of output and local telemetry is not billing or subscription quota."
    return result


def codex_counter(raw: Any) -> dict[str, Optional[int]]:
    if not isinstance(raw, dict):
        raw = {}
    return {
        "input": as_token(first(raw, "input_tokens", "input")),
        "output": as_token(first(raw, "output_tokens", "output")),
        "cacheRead": as_token(first(raw, "cached_input_tokens", "cache_read", "cacheRead")),
        "cacheWrite": None,
        "reasoning": as_token(first(raw, "reasoning_output_tokens", "reasoning_tokens", "reasoning")),
        "total": as_token(first(raw, "total_tokens", "total")),
    }


def subtract_counters(current: dict[str, Optional[int]], previous: Optional[dict[str, Optional[int]]], fallback: dict[str, Optional[int]]) -> dict[str, Optional[int]]:
    if previous is None:
        return {name: (fallback.get(name) if fallback.get(name) is not None else current.get(name)) for name in TOKEN_FIELDS}
    output: dict[str, Optional[int]] = {}
    for name in TOKEN_FIELDS:
        now, before = current.get(name), previous.get(name)
        if now is not None and before is not None and now >= before:
            output[name] = now - before
        else:
            output[name] = fallback.get(name)
    return output


def collect_codex(root: Path) -> ScanResult:
    result = ScanResult("codex-local", "OpenAI Codex")
    files = jsonl_files(root, result)
    if not root.exists():
        result.status, result.detail, result.exactness = "unavailable", "Codex telemetry root is missing; allowance and billing quota are unavailable.", "unavailable"
        return result
    if not files:
        if result.file_errors:
            result.status, result.exactness = "partial", "partial"
            result.detail = f"Codex telemetry had {result.file_errors} rejected/unreadable files; local telemetry is not billing or quota."
        else:
            result.status, result.detail = "empty", "No Codex rollout JSONL telemetry found; local telemetry is not billing or quota."
        return result

    raw_events: list[tuple[Optional[dt.datetime], str, set[str], Optional[str], Optional[str], Optional[str], dict[str, Optional[int]], dict[str, Optional[int]], str]] = []
    global_fingerprints: set[str] = set()
    for path in files:
        _, group_key = path_session(root, path, "codex")
        session_id: Optional[str] = None
        parent_id: Optional[str] = None
        current_model: Optional[str] = None
        provider: Optional[str] = "openai"
        for _, row in load_json_lines(path, result):
            if not row:
                result.malformed += 1
                continue
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            row_type = row.get("type")
            payload_type = payload.get("type")
            if row_type in ("session_meta", "session"):
                session_id = first(payload, "id", "session_id", "sessionId") or session_id
                parent_id = first(payload, "parent_session_id", "parentSessionId") or parent_id
                current_model = safe_identifier(first(payload, "model", "model_name")) or current_model
                continue
            if row_type == "turn_context" or payload_type == "turn_context":
                context = payload if payload else row
                current_model = safe_identifier(first(context, "model", "model_name")) or current_model
                provider = safe_identifier(first(context, "provider", "model_provider")) or provider
                continue
            if row_type != "event_msg" or payload_type != "token_count":
                continue
            info = payload.get("info") if isinstance(payload.get("info"), dict) else payload
            total = codex_counter(first(info, "total_token_usage", "totalTokenUsage"))
            last = codex_counter(first(info, "last_token_usage", "lastTokenUsage"))
            timestamp = parse_time(first(row, "timestamp", "created_at") or first(payload, "timestamp", "created_at"))
            if timestamp is None:
                result.invalid_timestamps += 1
            aliases = {group_key}
            if isinstance(session_id, str) and session_id:
                aliases.add(session_id)
            fingerprint = internal_hash(timestamp.isoformat() if timestamp else None, session_id, total, last)
            if fingerprint in global_fingerprints:
                continue
            global_fingerprints.add(fingerprint)
            raw_events.append((timestamp, session_id or group_key, aliases, parent_id, provider, current_model, total, last, fingerprint))

    previous_by_session: dict[str, dict[str, Optional[int]]] = {}
    seen_cumulative: set[str] = set()
    raw_events.sort(key=lambda item: (item[0] or dt.datetime.min.replace(tzinfo=dt.timezone.utc), item[8]))
    for timestamp, session, aliases, parent_id, provider, model, total, last, _ in raw_events:
        cumulative_key = internal_hash(session, total)
        if cumulative_key in seen_cumulative:
            continue
        seen_cumulative.add(cumulative_key)
        usage = subtract_counters(total, previous_by_session.get(session), last)
        previous_by_session[session] = total
        if all(value in (None, 0) for value in usage.values()):
            continue
        result.events.append(Event(
            source=result.source,
            harness=result.harness,
            timestamp=timestamp,
            session=session,
            aliases=aliases,
            parent_session=parent_id if isinstance(parent_id, str) else None,
            provider=provider,
            model=model,
            agent="parent",
            usage=usage,
            semantics={"cacheReadSubsetOfInput": True, "reasoningSubsetOfOutput": True},
        ))
    if result.malformed or result.invalid_timestamps or result.file_errors:
        result.status, result.exactness = "partial", "partial"
        result.detail = f"Codex cumulative usage collected with {result.malformed} malformed rows, {result.invalid_timestamps} usage rows without valid timestamps, and {result.file_errors} rejected/unreadable files; cached input and reasoning are subsets, and local telemetry is not billing or quota."
    else:
        result.detail = "Codex cumulative snapshots converted to non-duplicated deltas; cached input and reasoning are subsets, and local telemetry is not billing or subscription quota."
    return result


def week_bounds(now: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    now = now.astimezone(dt.timezone.utc)
    start = (now - dt.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + dt.timedelta(days=7)


def available_meta_values(meta: Any, name: str) -> set[str]:
    data = meta.get("data", meta) if isinstance(meta, dict) else {}
    value = data.get(name) if isinstance(data, dict) else None
    if isinstance(value, dict):
        return {str(key) for key in value}
    if isinstance(value, list):
        output = set()
        for item in value:
            if isinstance(item, str):
                output.add(item)
            elif isinstance(item, dict) and isinstance(item.get("id") or item.get("name"), str):
                output.add(item.get("id") or item.get("name"))
        return output
    return set()


def remote_error_detail(error: Exception) -> tuple[str, str]:
    if isinstance(error, urllib.error.HTTPError):
        if error.code == 401:
            return "unauthorized", "OpenRouter management authentication was rejected (401)."
        if error.code == 403:
            return "insufficient_scope", "OpenRouter management analytics permission is insufficient (403)."
        if error.code == 429:
            return "rate_limited", "OpenRouter analytics is rate limited (429); local telemetry remains available."
        return "remote_error", f"OpenRouter analytics returned HTTP {error.code}; response body was discarded."
    if isinstance(error, (urllib.error.URLError, TimeoutError, OSError)):
        return "network_error", "OpenRouter analytics network request failed; local telemetry remains available."
    return "malformed", "OpenRouter analytics returned malformed data; response body was discarded."


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def request_json(url: str, method: str, key: str, body: Optional[dict[str, Any]], timeout: float) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", "Bearer " + key)
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", USER_AGENT)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    opener = urllib.request.build_opener(NoRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_REMOTE_BYTES:
            raise ValueError("response too large")
        raw = response.read(MAX_REMOTE_BYTES + 1)
        if len(raw) > MAX_REMOTE_BYTES:
            raise ValueError("response too large")
        return json.loads(raw.decode("utf-8"))


def collect_openrouter(start: dt.datetime, end: dt.datetime, offline: bool, base_url: str, timeout: float, environ: dict[str, str]) -> tuple[ScanResult, list[dict[str, Any]]]:
    result = ScanResult("openrouter-analytics", "OpenRouter", exactness="exact")
    result.events = []
    if offline:
        result.status, result.exactness = "offline", "unavailable"
        result.detail = "Offline mode: no OpenRouter request was sent."
        return result, []
    key = environ.get("OPENROUTER_MANAGEMENT_API_KEY")
    if not key:
        if environ.get("OPENROUTER_API_KEY"):
            result.status, result.exactness = "insufficient_scope", "unavailable"
            result.detail = "OPENROUTER_API_KEY is inference-only; set OPENROUTER_MANAGEMENT_API_KEY for analytics. No request was sent."
        else:
            result.status, result.exactness = "not_configured", "unavailable"
            result.detail = "Set OPENROUTER_MANAGEMENT_API_KEY to enable optional weekly analytics."
        return result, []
    base = base_url.rstrip("/")
    try:
        meta = request_json(base + "/api/v1/analytics/meta", "GET", key, None, timeout)
        supported_metrics = available_meta_values(meta, "metrics") or available_meta_values(meta, "available_metrics")
        metrics = [metric for metric in REMOTE_METRICS if metric in supported_metrics]
        supported_dimensions = (
            available_meta_values(meta, "dimensions")
            or available_meta_values(meta, "available_dimensions")
            or available_meta_values(meta, "group_by")
        )
        dimensions = [dimension for dimension in ("model", "provider") if dimension in supported_dimensions]
        if not metrics or not dimensions:
            raise ValueError("analytics metadata lacks supported fields")
        query = {
            "time_range": {
                "start": start.isoformat().replace("+00:00", "Z"),
                "end": end.isoformat().replace("+00:00", "Z"),
            },
            "metrics": metrics,
            "dimensions": dimensions,
            "limit": REMOTE_ROW_LIMIT,
        }
        payload = request_json(base + "/api/v1/analytics/query", "POST", key, query, timeout)
        envelope = payload.get("data") if isinstance(payload, dict) else None
        rows = envelope.get("data") if isinstance(envelope, dict) else None
        metadata = envelope.get("metadata") if isinstance(envelope, dict) else None
        if not isinstance(rows, list) or not isinstance(metadata, dict):
            raise ValueError("official analytics envelope missing")
        normalized = []
        skipped = 0
        for raw in rows:
            if not isinstance(raw, dict):
                skipped += 1
                continue
            dimensions_raw = raw.get("dimensions") if isinstance(raw.get("dimensions"), dict) else raw
            metrics_raw = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else raw
            metric_values = {metric: as_remote_count(metrics_raw.get(metric)) for metric in metrics}
            if any(value is None for value in metric_values.values()):
                skipped += 1
                continue
            provider = safe_identifier(first(dimensions_raw, "provider"))
            model = safe_identifier(first(dimensions_raw, "model"))
            if ("provider" in dimensions and provider is None) or ("model" in dimensions and model is None):
                skipped += 1
                continue
            normalized.append({
                "provider": provider,
                "model": model,
                "requests": as_remote_count(first(metrics_raw, "request_count")),
                "input": as_remote_count(first(metrics_raw, "tokens_prompt")),
                "output": as_remote_count(first(metrics_raw, "tokens_completion")),
                "cacheRead": as_remote_count(first(metrics_raw, "cached_tokens")),
                "cacheWrite": None,
                "reasoning": as_remote_count(first(metrics_raw, "reasoning_tokens")),
                "total": as_remote_count(first(metrics_raw, "tokens_total")),
            })
        truncated = metadata.get("truncated") is True
        if truncated or skipped:
            result.status, result.exactness = "partial", "partial"
            result.malformed = skipped
            reason = "truncated response" if truncated else ""
            if skipped:
                reason = (reason + " and " if reason else "") + f"{skipped} malformed/skipped rows"
            result.detail = f"Partial OpenRouter API analytics ({reason}); this is telemetry, not a subscription allowance or quota."
        else:
            result.detail = "Exact OpenRouter API analytics for the UTC week-to-date; this is telemetry, not a subscription allowance or quota."
        for row in normalized:
            row["exactness"] = result.exactness
        return result, normalized
    except Exception as error:  # Sanitized at this trust boundary.
        result.status, result.detail = remote_error_detail(error)
        result.exactness = "unavailable"
        return result, []


def active_harness(environ: dict[str, str]) -> Optional[str]:
    evidence = {
        "pi-local": any(environ.get(name) for name in (
            "PI_CODING_AGENT", "PI_SESSION_ID", "PI_SUBAGENT_PARENT_SESSION",
            "PI_SUBAGENT_ORCHESTRATOR_SESSION_ID", "PI_SUBAGENT_RUN_ID",
        )),
        "claude-local": any(environ.get(name) for name in (
            "CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDECODE",
        )),
        "codex-local": any(environ.get(name) for name in (
            "CODEX_SESSION_ID", "CODEX_THREAD_ID", "CODEX_CLI",
        )),
    }
    active = [source for source, present in evidence.items() if present]
    return active[0] if len(active) == 1 else None


def runtime_session_ids(source: str, environ: dict[str, str]) -> list[str]:
    names = {
        "pi-local": ("PI_SUBAGENT_PARENT_SESSION", "PI_SUBAGENT_ORCHESTRATOR_SESSION_ID", "PI_SESSION_ID"),
        "claude-local": ("CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID"),
        "codex-local": ("CODEX_SESSION_ID", "CODEX_THREAD_ID"),
    }.get(source, ())
    return [environ[name] for name in names if environ.get(name)]


def linked_sessions(events: list[Event], roots: set[str]) -> set[str]:
    changed = True
    while changed:
        changed = False
        selected = [event for event in events if event.session in roots]
        aliases = set(roots)
        for event in selected:
            aliases.update(event.aliases)
            if event.parent_session:
                aliases.add(event.parent_session)
        for event in events:
            linked = bool(event.aliases & aliases) or event.session in aliases
            linked = linked or bool(event.parent_session and event.parent_session in aliases)
            if linked and event.session not in roots:
                roots.add(event.session)
                changed = True
    return roots


def select_sessions(results: list[ScanResult], explicit: Optional[str], environ: dict[str, str]) -> tuple[dict[str, set[str]], dict[str, dict[str, str]]]:
    selections = {result.source: set() for result in results}
    details: dict[str, dict[str, str]] = {}
    active = active_harness(environ)

    if explicit:
        for result in results:
            matching = [event for event in result.events if explicit == event.session or explicit in event.aliases or explicit == event.parent_session]
            selections[result.source] = linked_sessions(result.events, {event.session for event in matching})
            details[result.source] = {
                "precision": "explicit" if matching else "unavailable",
                "detail": "Selected by explicit session identifier." if matching else "Requested session was not present in this source.",
            }
        return selections, details

    if active:
        for result in results:
            if result.source != active:
                details[result.source] = {"precision": "unavailable", "detail": "Excluded because another supported harness is active."}
                continue
            wanted = runtime_session_ids(active, environ)
            matching = [
                event for event in result.events
                if any(value == event.session or value in event.aliases or value == event.parent_session for value in wanted)
            ]
            if matching:
                selections[active] = linked_sessions(result.events, {event.session for event in matching})
                details[active] = {"precision": "runtime-match", "detail": "Matched the active harness runtime session."}
            elif wanted:
                details[active] = {"precision": "unavailable", "detail": "The active runtime session was not present in local telemetry."}
            elif result.events:
                newest = max(result.events, key=lambda event: event.timestamp or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
                selections[active] = linked_sessions(result.events, {newest.session})
                details[active] = {"precision": "estimated", "detail": "Active harness detected; its most recent local session was estimated."}
            else:
                details[active] = {"precision": "unavailable", "detail": "No active-harness session usage was available."}
        return selections, details

    candidates = [(event.timestamp, result, event) for result in results for event in result.events if event.timestamp]
    newest_result: Optional[ScanResult] = None
    newest_event: Optional[Event] = None
    if candidates:
        _, newest_result, newest_event = max(candidates, key=lambda item: item[0])
        selections[newest_result.source] = linked_sessions(newest_result.events, {newest_event.session})
    for result in results:
        if result is newest_result:
            details[result.source] = {"precision": "estimated", "detail": "Estimated as the single globally newest local session."}
        else:
            details[result.source] = {"precision": "unavailable", "detail": "Excluded by the single globally newest-session estimate." if newest_event else "No session usage was available."}
    return selections, details


def add_usage(total: dict[str, Optional[int]], usage: dict[str, Optional[int]]) -> None:
    for name in TOKEN_FIELDS:
        value = usage.get(name)
        if value is not None:
            total[name] = (total[name] or 0) + value


def normalized_row(scope: str, period: dict[str, Any], source: str, harness: str, provider: Optional[str], model: Optional[str], agent: str, exactness: str, requests: Optional[int], usage: dict[str, Optional[int]], semantics: dict[str, bool]) -> dict[str, Any]:
    unavailable = {name: "not_recorded_by_source" for name in TOKEN_FIELDS if usage.get(name) is None}
    if requests is None:
        unavailable["requests"] = "not_recorded_by_source"
    if provider is None:
        unavailable["provider"] = "not_recorded_by_source"
    if model is None:
        unavailable["model"] = "not_recorded_by_source"
    return {
        "scope": scope,
        "source": source,
        "harness": harness,
        "provider": provider,
        "model": model,
        "agent": agent,
        "period": period,
        "timezone": period["timezone"],
        "exactness": exactness,
        "requests": requests,
        **{name: usage.get(name) for name in TOKEN_FIELDS},
        "unavailableReasons": unavailable,
        "semantics": semantics,
    }


def aggregate_events(events: list[Event], scope: str, exactness_override: Optional[str] = None, period: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    if period is None:
        timestamps = [event.timestamp for event in events if event.timestamp]
        period = {
            "start": min(timestamps).isoformat().replace("+00:00", "Z") if timestamps else None,
            "end": max(timestamps).isoformat().replace("+00:00", "Z") if timestamps else None,
            "timezone": "UTC",
        }
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for event in events:
        key = (event.source, event.harness, event.provider, event.model, event.agent)
        group = groups.setdefault(key, {
            "usage": {name: None for name in TOKEN_FIELDS},
            "present": {name: 0 for name in TOKEN_FIELDS},
            "requests": 0,
            "exactness": exactness_override or event.exactness,
            "semantics": {},
        })
        add_usage(group["usage"], event.usage)
        for name in TOKEN_FIELDS:
            if event.usage.get(name) is not None:
                group["present"][name] += 1
        group["requests"] += 1
        group["semantics"].update(event.semantics)
        if event.exactness == "partial":
            group["exactness"] = "partial"
    rows = []
    for key in sorted(groups, key=lambda value: tuple("" if part is None else str(part) for part in value)):
        source, harness, provider, model, agent = key
        group = groups[key]
        for name in TOKEN_FIELDS:
            if group["present"][name] != group["requests"]:
                if group["present"][name] > 0:
                    group["exactness"] = "partial"
                group["usage"][name] = None
        rows.append(normalized_row(scope, period, source, harness, provider, model, agent, group["exactness"], group["requests"], group["usage"], group["semantics"]))
    return rows


def build_dashboard(now: dt.datetime, roots: dict[str, Path], offline: bool, base_url: str, timeout: float, explicit_session: Optional[str], environ: dict[str, str]) -> dict[str, Any]:
    now = now.astimezone(dt.timezone.utc)
    week_start, week_boundary_end = week_bounds(now)
    local = [collect_claude(roots["claude"]), collect_pi(roots["pi"]), collect_codex(roots["codex"])]
    selections, selection_detail = select_sessions(local, explicit_session, environ)
    current_by_source: list[tuple[ScanResult, list[Event]]] = []
    week_by_source: list[tuple[ScanResult, list[Event]]] = []
    for result in local:
        current_by_source.append((result, [event for event in result.events if event.session in selections[result.source]]))
        week_by_source.append((result, [event for event in result.events if event.timestamp and week_start <= event.timestamp <= now]))
    current_events = [event for _, events in current_by_source for event in events]
    current_times = [event.timestamp for event in current_events if event.timestamp]
    current_period = {
        "start": min(current_times).isoformat().replace("+00:00", "Z") if current_times else None,
        "end": now.isoformat().replace("+00:00", "Z"),
        "timezone": "UTC",
    }
    week_period = {
        "start": week_start.isoformat().replace("+00:00", "Z"),
        "end": now.isoformat().replace("+00:00", "Z"),
        "boundaryEnd": week_boundary_end.isoformat().replace("+00:00", "Z"),
        "timezone": "UTC",
    }
    usage = []
    for result, events in current_by_source:
        usage.extend(aggregate_events(events, "current-session", "partial" if result.exactness == "partial" else None, current_period))
    for result, events in week_by_source:
        usage.extend(aggregate_events(events, "week", "partial" if result.exactness == "partial" else None, week_period))

    remote_result, remote_rows = collect_openrouter(week_start, now, offline, base_url, timeout, environ)
    for raw in remote_rows:
        values = {name: raw.get(name) for name in TOKEN_FIELDS}
        usage.append(normalized_row(
            "week", week_period, remote_result.source, remote_result.harness, raw.get("provider"), raw.get("model"),
            "account", raw.get("exactness", remote_result.exactness), raw.get("requests"), values,
            {"cacheReadMayBeSubsetOfInput": True, "reasoningMayBeSubsetOfOutput": True},
        ))

    selected_precisions = {item["precision"] for item in selection_detail.values() if item["precision"] != "unavailable"}
    current_precision = next(iter(selected_precisions)) if len(selected_precisions) == 1 else ("unavailable" if not selected_precisions else "mixed")
    selected_results = [result for result, events in current_by_source if events]
    if not selected_results:
        current_completeness = "unavailable"
    elif any(result.status not in ("ok", "empty") for result in selected_results):
        current_completeness = "partial"
    else:
        current_completeness = "complete"
    week_completeness = "partial" if any(result.status not in ("ok", "empty") for result in local) else "complete"
    sources = []
    authority = {
        "claude-local": "Claude Code JSONL assistant message.usage",
        "pi-local": "Pi session JSONL assistant usage",
        "codex-local": "Codex rollout token_count cumulative telemetry",
        "openrouter-analytics": "OpenRouter Management Analytics API",
    }
    for result in local + [remote_result]:
        sources.append({
            "id": result.source,
            "harness": result.harness,
            "kind": "remote-analytics" if result.source == "openrouter-analytics" else "local-telemetry",
            "status": result.status,
            "exactness": result.exactness,
            "detail": result.detail,
            "authority": authority[result.source],
        })
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "periods": {
            "current-session": {
                **current_period,
                "completeness": current_completeness,
                "selection": {"precision": current_precision, "sources": selection_detail},
                "unavailableReasons": {} if current_times else {"start": "no_selected_session_timestamp"},
            },
            "week": {
                **week_period,
                "completeness": week_completeness if remote_result.status in ("ok", "offline", "not_configured", "insufficient_scope") else "partial",
                "selection": {"precision": "calendar", "detail": "UTC calendar week beginning Monday 00:00."},
            },
        },
        "sources": sources,
        "usage": usage,
    }


def token_display(value: Optional[int]) -> str:
    return "unavailable" if value is None else f"{value:,}"


def render_terminal(dashboard: dict[str, Any]) -> str:
    lines = ["Token dashboard", f"Generated {dashboard['generatedAt']}"]
    for scope, title in (("current-session", "Current session"), ("week", "Week")):
        period = dashboard["periods"][scope]
        selection = period["selection"]["precision"]
        lines.extend(["", title, f"Period: {period['start'] or 'unavailable'} to {period['end']} | timezone UTC | selection {selection}"])
        rows = [row for row in dashboard["usage"] if row["scope"] == scope]
        if not rows:
            lines.append("  No usage rows available.")
        for row in rows:
            identity = "/".join(safe_identifier(value) or "unknown" for value in (row["provider"], row["model"], row["agent"]))
            lines.append(
                f"  harness {row['harness']} | scope {row['scope']} | period {period['start'] or 'unavailable'} to {period['end']} {period['timezone']} | "
                f"source {row['source']} | identity {identity} | exactness {row['exactness']} | requests {token_display(row['requests'])} | "
                f"input {token_display(row['input'])} output {token_display(row['output'])} "
                f"cache-read {token_display(row['cacheRead'])} cache-write {token_display(row['cacheWrite'])} "
                f"reasoning {token_display(row['reasoning'])} total {token_display(row['total'])}"
            )
    lines.extend(["", "Sources"])
    for source in dashboard["sources"]:
        lines.append(f"  {source['id']} | {source['status']} | {source['exactness']} | {safe_text(source['detail'], 300) or 'unavailable'}")
    return "\n".join(lines) + "\n"


def parse_now(value: Optional[str]) -> dt.datetime:
    if not value:
        return dt.datetime.now(dt.timezone.utc)
    parsed = parse_time(value)
    if parsed is None:
        raise argparse.ArgumentTypeError("--now must be an ISO-8601 timestamp")
    return parsed


def main(argv: Optional[list[str]] = None, environ: Optional[dict[str, str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only token telemetry dashboard")
    parser.add_argument("--json", action="store_true", help="emit normalized schema v1 JSON")
    parser.add_argument("--offline", action="store_true", help="guarantee no network requests")
    parser.add_argument("--session-id", help="explicit current session identifier (never emitted)")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--now", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    env = dict(os.environ if environ is None else environ)
    home = Path(env.get("HOME", str(Path.home())))
    roots = {
        "claude": home / ".claude" / "projects",
        "pi": home / ".pi" / "agent" / "sessions",
        "codex": home / ".codex" / "sessions",
    }
    try:
        now = parse_now(args.now)
        dashboard = build_dashboard(now, roots, args.offline, OPENROUTER_BASE_URL, max(0.1, min(args.timeout, 30.0)), args.session_id, env)
    except argparse.ArgumentTypeError as error:
        parser.error(str(error))
    if args.json:
        json.dump(dashboard, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_terminal(dashboard))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
