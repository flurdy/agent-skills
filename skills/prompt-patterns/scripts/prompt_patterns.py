#!/usr/bin/env python3
"""Bounded local prompt candidates. Summary by default; no model calls or file writes."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import unicodedata

VERSION = "prompt-patterns/v1"
PLACEHOLDER = re.compile(r"\$\{[^}\n]{1,512}\}|\$ARGUMENTS|\$@|\$[1-9][0-9]{0,3}")
WRAPPED = re.compile(r"^\s*<[A-Za-z][A-Za-z0-9_-]*(?:\s[^>\n]*)?>")
INJECTED = re.compile(r"<\s*(?:skill(?:\s|>)|skill_content|system-reminder|command-name|command-message|local-command-stdout|local-command-caveat|bash-input|bash-stdout|bash-stderr|user-memory-input|ide_opened_file|ide_selection|task-notification|user-prompt-submit-hook)|base directory for this skill:|watch-loop protocol\s+\d+\s+tick\b|\[request interrupted by user", re.I)
CREDENTIAL_VALUE = r"""(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\n]+)"""
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.I),
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/-]+=*", re.I),
    re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]{0,31}://[^\s<>\"']+"),
    re.compile(r"--(?:[a-z0-9_-]{0,64}(?:password|passwd|pass|secret|token|cookie|key)[a-z0-9_-]{0,64})(?:=|\s+)" + CREDENTIAL_VALUE, re.I),
    re.compile(r"[\"']?\b[A-Za-z0-9_-]{0,64}(?:key|secret|token|password|passwd|pass|pwd|cookie|authorization|credential)[A-Za-z0-9_-]{0,64}\\?[\"']?\s*[:=]\s*" + CREDENTIAL_VALUE, re.I),
    re.compile(r"(?<![\w-])-[pu](?:=|\s*)" + CREDENTIAL_VALUE),
    re.compile(r"^[ \t]*(?:password|passwd)[ \t]+" + CREDENTIAL_VALUE, re.I | re.M),
    re.compile(r"^[ \t]*machine[ \t]+[^\n]*?\bpassword[ \t]+[^\n]+", re.I | re.M),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,}|(?:AKIA|ASIA)[A-Z0-9]{16})\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_+/=-]{32,}(?![A-Za-z0-9])"),
    re.compile(r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})+\b"),
]
ORIGIN_FLAGS = ("isMeta", "isSidechain", "isCompactSummary", "isSynthetic", "isInjected")
CHILD_FIELDS = ("agentId", "parentSession", "parentSessionId", "parent_session_id")


@dataclass(frozen=True)
class Limits:
    max_files: int = 2000
    max_walk_entries: int = 20000
    max_file_bytes: int = 8 * 1024 * 1024
    max_line_bytes: int = 1024 * 1024
    max_total_bytes: int = 128 * 1024 * 1024
    max_records: int = 100000
    max_file_records: int = 20000
    max_unique_candidates: int = 2000
    max_prompt_input_chars: int = 65536
    max_templates: int = 256
    max_template_bytes: int = 65536
    quiet_seconds: int = 60
    max_scan_seconds: int = 30


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def opaque(prefix, value):
    return prefix + "-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def timestamp(value):
    try:
        if not isinstance(value, str):
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize(value):
    return " ".join(value.split())


def canonical_text(value):
    value = unicodedata.normalize("NFKC", value)
    return "".join(c for c in value if c in "\n\t" or not unicodedata.category(c).startswith("C"))


def redact(value):
    value = canonical_text(value)
    operations = 0
    for pattern in SECRET_PATTERNS:
        value, count = pattern.subn("[REDACTED:SECRET]", value)
        operations += count
    value = re.sub(r"/(?:home|Users)/[^/\s]+", "~", value)
    return normalize(value), operations


def templates(roots, limits):
    patterns, manifest = [], []
    rejected = 0
    visited = 0
    for root in roots:
        try:
            paths = []
            if root.is_dir():
                for path in root.glob("*.md"):
                    if len(paths) >= limits.max_walk_entries:
                        rejected += 1
                        break
                    paths.append(path)
        except OSError:
            rejected += 1
            continue
        remaining = max(0, limits.max_templates - visited)
        rejected += max(0, len(paths) - remaining)
        for path in sorted(paths)[:remaining]:
            visited += 1
            try:
                # Installed templates are commonly symlinks. Read their resolved data,
                # never execute them; history files use the stricter no-follow reader.
                target = path.resolve(strict=True)
                if target.suffix.lower() != ".md":
                    raise ValueError("template target must be Markdown")
                fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as handle:
                    if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                        raise ValueError("nonregular")
                    raw = handle.read(limits.max_template_bytes + 1)
                if len(raw) > limits.max_template_bytes:
                    raise ValueError("oversized")
                body = raw.decode("utf-8")
                manifest.append(hashlib.sha256(raw).hexdigest())
                body = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", body, count=1, flags=re.S)
                body = normalize(unicodedata.normalize("NFKC", body))
                parts = PLACEHOLDER.split(body)
                if not any(len(part) >= 32 for part in parts):
                    rejected += 1
                    continue
                patterns.append((parts, bool(PLACEHOLDER.search(body))))
            except (OSError, ValueError):
                rejected += 1
    return patterns, {"templatesLoaded": len(patterns), "rejectedTemplates": rejected,
                      "limitation": "Only known current templates are matched; old, deleted or project-only unmarked expansions may remain."}, manifest


def matches_template(text, patterns):
    text = normalize(unicodedata.normalize("NFKC", text))
    for parts, parameterized in patterns:
        if not parameterized:
            if text == parts[0]:
                return True
            continue
        offset = 0
        for part in parts:
            if not part:
                continue
            found = text.find(part, offset)
            if found < 0:
                break
            offset = found + len(part)
        else:
            if (not parts[0] or text.startswith(parts[0])) and (not parts[-1] or text.endswith(parts[-1])):
                return True
    return False


def history_files(root, counters, limits, deadline, cutoff):
    files, directories = [], [root]
    visited = 0

    def selected():
        files.sort(key=lambda item: (-item[0], str(item[1])))
        counters["limitedFiles"] += max(0, len(files) - limits.max_files)
        return [path for _mtime, path in files[:limits.max_files]]

    while directories:
        if time.monotonic() > deadline:
            counters["limitedFiles"] += 1
            break
        directory = directories.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    visited += 1
                    if visited > limits.max_walk_entries or time.monotonic() > deadline:
                        counters["limitedFiles"] += 1
                        return selected()
                    if entry.is_symlink():
                        counters["rejectedFiles"] += 1
                    elif entry.is_dir(follow_symlinks=False):
                        if directory == root:
                            directories.append(Path(entry.path))
                        else:
                            counters["childDirectoriesExcluded"] += 1
                    elif entry.name.endswith(".jsonl"):
                        counters["filesDiscovered"] += 1
                        mtime = entry.stat(follow_symlinks=False).st_mtime
                        if mtime > cutoff:
                            counters["activeFilesExcluded"] += 1
                        else:
                            files.append((mtime, Path(entry.path)))
        except OSError:
            counters["rejectedFiles"] += 1
    return selected()


def read_history(root, path, limits, remaining, cutoff):
    """Open every directory component without following transcript symlinks."""
    relative = path.relative_to(root)
    with ExitStack() as stack:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, fd)
        for component in relative.parts[:-1]:
            fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            stack.callback(os.close, fd)
        final = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        handle = stack.enter_context(os.fdopen(final, "rb"))
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            return "rejected", b""
        if before.st_mtime > cutoff:
            return "active", b""
        maximum = min(limits.max_file_bytes, remaining)
        if before.st_size > maximum:
            return "limited", b""
        raw = handle.read(maximum + 1)
        after = os.fstat(handle.fileno())
        if len(raw) > maximum:
            return "limited", b""
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            return "changed", b""
        return "ok", raw


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(_value):
    raise ValueError("non-JSON constant")


def file_candidates(source, raw, source_stats, patterns, start, as_of, limits, deadline):
    rows, header = [], None
    stream = io.BytesIO(raw)
    file_rows = 0
    child = False
    while True:
        line = stream.readline(limits.max_line_bytes + 1)
        if not line:
            break
        file_rows += 1
        source_stats["recordsScanned"] += 1
        if file_rows > limits.max_file_records or source_stats["recordsScanned"] > limits.max_records or time.monotonic() > deadline:
            source_stats["limitedFiles"] += 1
            return []
        if len(line) > limits.max_line_bytes:
            source_stats["malformedRecords"] += 1
            return []
        try:
            row = json.loads(line, object_pairs_hook=strict_pairs, parse_constant=reject_constant)
            if not isinstance(row, dict):
                raise ValueError("object required")
        except (ValueError, UnicodeError, RecursionError):
            source_stats["malformedRecords"] += 1
            return []
        if row.get("isSidechain") or any(row.get(k) for k in CHILD_FIELDS):
            child = True
        if source == "pi" and row.get("type") == "session":
            if header is not None or not isinstance(row.get("id"), str) or row.get("version") not in (1, 2, 3):
                source_stats["unknownShapes"] += 1
                return []
            header = row
            continue
        message = row.get("message")
        wanted_type = "message" if source == "pi" else "user"
        if row.get("type") != wanted_type or not isinstance(message, dict) or message.get("role") != "user":
            continue
        source_stats["seenUserMessages"] += 1
        if source == "pi" and header is None:
            source_stats["unknownShapes"] += 1
            return []
        if any(key.startswith("is") and key not in ORIGIN_FLAGS and value is not False
               for item in (row, message) for key, value in item.items()):
            source_stats["unknownShapes"] += 1
            source_stats["excludedMessages"]["unknown-origin-flag"] += 1
            continue
        if any(item.get(flag, False) is not False for item in (row, message) for flag in ORIGIN_FLAGS) or "toolUseResult" in row:
            source_stats["excludedMessages"]["metadata"] += 1
            continue
        if any(item.get("source", "interactive") not in ("interactive", "human", "user") for item in (row, message)):
            source_stats["excludedMessages"]["unknown-origin"] += 1
            continue
        content = message.get("content")
        if isinstance(content, list):
            if not content or any(not isinstance(b, dict) or b.get("type") != "text" or not isinstance(b.get("text"), str) for b in content):
                source_stats["excludedMessages"]["nontext-content"] += 1
                continue
            if any(WRAPPED.search(canonical_text(b["text"])) for b in content):
                source_stats["excludedMessages"]["wrapped-content"] += 1
                continue
            content = "\n".join(b["text"] for b in content)
        if not isinstance(content, str):
            source_stats["unknownShapes"] += 1
            continue
        if len(content) > limits.max_prompt_input_chars:
            source_stats["oversizedInputMessages"] += 1
            continue
        when = timestamp(row.get("timestamp"))
        if when is None and source == "pi":
            millis = message.get("timestamp")
            try:
                when = datetime.fromtimestamp(millis / 1000, timezone.utc) if type(millis) in (int, float) else None
            except (ValueError, OverflowError, OSError):
                when = None
        if when is None:
            source_stats["invalidTimestamps"] += 1
            continue
        if not start <= when < as_of:
            source_stats["excludedMessages"]["outside-window"] += 1
            continue
        content = canonical_text(content)
        if content.lstrip().startswith("/") or INJECTED.search(content) or WRAPPED.search(content):
            source_stats["excludedMessages"]["command-or-injected"] += 1
            continue
        if matches_template(content, patterns):
            source_stats["excludedMessages"]["known-template"] += 1
            continue
        cleaned, operations = redact(content)
        source_stats["redactionOperations"] += operations
        if len(cleaned) < source_stats["minChars"] or len(cleaned.split()) < source_stats["minWords"]:
            source_stats["excludedMessages"]["short"] += 1
            continue
        event_id = row.get("id") if source == "pi" else row.get("uuid")
        session = header.get("id") if header else row.get("sessionId")
        cwd = header.get("cwd") if header else row.get("cwd")
        if not isinstance(event_id, str) or not event_id or len(event_id) > 512 or not isinstance(session, str) or not session or len(session) > 512:
            source_stats["unknownShapes"] += 1
            continue
        repository = opaque("r", cwd) if isinstance(cwd, str) and cwd and len(cwd) <= 4096 else None
        rows.append({"text": cleaned, "when": iso(when), "session": opaque("s", source + ":" + session),
                     "repository": repository, "event": opaque("e", source + ":" + (session + ":" if source == "pi" else "") + event_id), "source": source})
    if child:
        source_stats["childFilesExcluded"] += 1
        return []
    if source == "pi" and header is None:
        source_stats["unknownShapes"] += 1
        return []
    return rows


def collect(roots, template_roots, *, as_of, days=30, min_chars=80, min_words=12, max_candidates=50,
            max_bytes=65536, max_prompt_chars=8000, limits=None):
    limits = limits or Limits()
    deadline = time.monotonic() + limits.max_scan_seconds
    start = as_of - timedelta(days=days)
    patterns, template_coverage, template_manifest = templates(template_roots, limits)
    sources, manifest, groups, seen = {}, [], {}, set()
    truncation = Counter()
    source_budget = limits.max_total_bytes // max(1, len(roots))
    pool_share = max(1, limits.max_unique_candidates // max(1, len(roots)))
    for source, root in sorted(roots.items()):
        source_bytes, introduced = 0, 0
        source_deadline = min(deadline, time.monotonic() + limits.max_scan_seconds / max(1, len(roots)))
        counters = {name: 0 for name in ("filesDiscovered", "filesScanned", "childDirectoriesExcluded", "childFilesExcluded", "activeFilesExcluded", "rejectedFiles", "limitedFiles", "recordsScanned", "malformedRecords", "unknownShapes", "invalidTimestamps", "seenUserMessages", "redactionOperations", "duplicateEvents", "oversizedInputMessages")}
        counters.update(status="ok", excludedMessages=Counter(), minChars=min_chars, minWords=min_words)
        sources[source] = counters
        if root.is_symlink() or not root.is_dir():
            counters["status"] = "unavailable"
            continue
        try:
            for path in history_files(root, counters, limits, source_deadline, as_of.timestamp() - limits.quiet_seconds):
                parts = path.relative_to(root).parts
                if len(parts) != 2 or any(p.lower() in ("subagents", "extra-agents", "agents") for p in parts):
                    if path.is_symlink():
                        counters["rejectedFiles"] += 1
                    else:
                        counters["childFilesExcluded"] += 1
                    continue
                if time.monotonic() > source_deadline or source_bytes >= source_budget:
                    counters["limitedFiles"] += 1
                    break
                try:
                    status, raw = read_history(root, path, limits, source_budget - source_bytes, as_of.timestamp() - limits.quiet_seconds)
                except (OSError, ValueError):
                    counters["rejectedFiles"] += 1
                    continue
                if status != "ok":
                    counters[{"active": "activeFilesExcluded", "limited": "limitedFiles"}.get(status, "rejectedFiles")] += 1
                    continue
                source_bytes += len(raw)
                counters["filesScanned"] += 1
                manifest.append([source, opaque("f", str(path.relative_to(root))), hashlib.sha256(raw).hexdigest()])
                for row in file_candidates(source, raw, counters, patterns, start, as_of, limits, source_deadline):
                    if row["event"] in seen:
                        counters["duplicateEvents"] += 1
                        continue
                    seen.add(row["event"])
                    if len(row["text"]) > max_prompt_chars:
                        truncation["oversizedPrompts"] += 1
                        continue
                    key = row["text"]
                    if key not in groups:
                        if len(groups) >= limits.max_unique_candidates or introduced >= pool_share:
                            truncation["candidatePoolOccurrencesOmitted"] += 1
                            continue
                        introduced += 1
                        groups[key] = {"id": opaque("p", key), "text": key, "occurrences": 0,
                                       "sessions": set(), "repositories": set(), "sources": set(),
                                       "unknownRepositoryOccurrences": 0, "firstSeen": row["when"], "lastSeen": row["when"]}
                    group = groups[key]
                    group["occurrences"] += 1
                    group["sessions"].add(row["session"])
                    if row["repository"]:
                        group["repositories"].add(row["repository"])
                    else:
                        group["unknownRepositoryOccurrences"] += 1
                    group["sources"].add(source)
                    group["firstSeen"] = min((group["firstSeen"], row["when"]), key=timestamp)
                    group["lastSeen"] = max((group["lastSeen"], row["when"]), key=timestamp)
        except (OSError, ValueError, RecursionError):
            counters["rejectedFiles"] += 1
        if any(counters[k] for k in ("rejectedFiles", "limitedFiles", "malformedRecords", "unknownShapes", "invalidTimestamps", "activeFilesExcluded")):
            counters["status"] = "partial"
    salt = hashlib.sha256(encoded(manifest)).hexdigest()
    for group in groups.values():
        group["sessions"] = {opaque("s", salt + value) for value in group["sessions"]}
        group["repositories"] = {opaque("r", salt + value) for value in group["repositories"]}
    candidates = [{k: sorted(v) if isinstance(v, set) else v for k, v in group.items()} for group in groups.values()]
    candidates.sort(key=lambda c: (-c["occurrences"], -len(c["sessions"]), -len(c["repositories"]), c["id"]))
    packet = {"schemaVersion": 1, "asOf": iso(as_of), "digest": "0" * 64, "candidates": []}
    for candidate in candidates:
        if len(packet["candidates"]) >= max_candidates:
            truncation["candidateLimitOmitted"] += 1
        elif len(encoded({**packet, "candidates": packet["candidates"] + [candidate]})) + 1 > max_bytes:
            truncation["byteBudgetOmitted"] += 1
        else:
            packet["candidates"].append(candidate)
    summary = {"schemaVersion": 1, "asOf": iso(as_of), "window": {"start": iso(start), "end": iso(as_of)},
               "sources": sources, "templateCoverage": template_coverage,
               "candidateCount": len(packet["candidates"]), "occurrenceCount": sum(c["occurrences"] for c in packet["candidates"]),
               "candidateTextBytes": sum(len(c["text"].encode("utf-8")) for c in packet["candidates"]), "payloadBytes": len(encoded(packet)) + 1,
               "truncation": {**{name: truncation[name] for name in ("candidateLimitOmitted", "byteBudgetOmitted", "oversizedPrompts", "candidatePoolOccurrencesOmitted")},
                              "oversizedInputMessages": sum(s["oversizedInputMessages"] for s in sources.values()),
                              "scanLimited": any(s["limitedFiles"] for s in sources.values())},
               "provenance": "heuristic user-message candidates, not certified human authorship or guaranteed secret-free data",
               "repositoryBasis": "distinct recorded working directories, not verified Git repository identities"}
    config = {"version": VERSION, "days": days, "minChars": min_chars, "minWords": min_words,
              "maxCandidates": max_candidates, "maxBytes": max_bytes, "maxPromptChars": max_prompt_chars, "limits": asdict(limits),
              "roots": {source: opaque("root", str(path.absolute())) for source, path in sorted(roots.items())},
              "templateRoots": [opaque("root", str(path.absolute())) for path in template_roots]}
    digest = hashlib.sha256(encoded({"summary": summary, "packet": packet, "manifest": manifest,
                                    "templates": template_manifest, "config": config})).hexdigest()
    packet["digest"] = summary["digest"] = digest
    return {"summary": summary, "packet": packet}


def cluster_metrics(packet, groups):
    candidates = {c["id"]: c for c in packet["candidates"]}
    if not isinstance(groups, list) or len(groups) > 200:
        raise ValueError("invalid cluster map")
    seen, clusters = set(), []
    for index, group in enumerate(groups, 1):
        if not isinstance(group, list) or not group or not all(isinstance(k, str) for k in group):
            raise ValueError("invalid cluster members")
        if len(set(group)) != len(group) or any(k not in candidates or k in seen for k in group):
            raise ValueError("unknown or repeated candidate")
        seen.update(group)
        members = [candidates[k] for k in group]
        clusters.append({"cluster": index, "candidateIds": group,
                         "occurrences": sum(c["occurrences"] for c in members),
                         "sessionCount": len({s for c in members for s in c["sessions"]}),
                         "repositoryCount": len({r for c in members for r in c["repositories"]}),
                         "unknownRepositoryOccurrences": sum(c["unknownRepositoryOccurrences"] for c in members),
                         "firstSeen": min((c["firstSeen"] for c in members), key=timestamp),
                         "lastSeen": max((c["lastSeen"] for c in members), key=timestamp)})
    clusters.sort(key=lambda c: (-c["occurrences"], -c["sessionCount"], -c["repositoryCount"], c["cluster"]))
    return {"digest": packet["digest"], "clusters": clusters, "ungroupedCandidateCount": len(candidates) - len(seen)}


def bounded_int(low, high):
    def parse(value):
        number = int(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"must be {low}..{high}")
        return number
    return parse


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-root", type=Path, default=Path.home() / ".pi/agent/sessions")
    parser.add_argument("--claude-root", type=Path, default=Path.home() / ".claude/projects")
    parser.add_argument("--template-root", type=Path, action="append")
    parser.add_argument("--as-of")
    parser.add_argument("--days", type=bounded_int(1, 365), default=30)
    parser.add_argument("--min-chars", type=bounded_int(40, 10000), default=80)
    parser.add_argument("--min-words", type=bounded_int(3, 1000), default=12)
    parser.add_argument("--max-candidates", type=bounded_int(1, 200), default=50)
    parser.add_argument("--max-bytes", type=bounded_int(1024, 131072), default=65536)
    parser.add_argument("--max-prompt-chars", type=bounded_int(80, 32000), default=8000)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--emit", action="store_true")
    mode.add_argument("--clusters", action="store_true", help="Read a bounded JSON array of candidate-ID groups from stdin; emit statistics only")
    parser.add_argument("--expected-digest")
    args = parser.parse_args(argv)
    if (args.emit or args.clusters) and (not args.as_of or not args.expected_digest or not re.fullmatch(r"[a-f0-9]{64}", args.expected_digest)):
        parser.error("--emit/--clusters requires the summary --as-of and --expected-digest")
    as_of = timestamp(args.as_of) if args.as_of else datetime.now(timezone.utc)
    if as_of is None:
        parser.error("--as-of requires an ISO timestamp with a timezone")
    default_templates = [Path(__file__).resolve().parents[3] / "prompts", Path.home() / ".agents/prompts", Path.home() / ".pi/agent/prompts", Path.home() / ".claude/commands"]
    try:
        result = collect({"pi": args.pi_root, "claude": args.claude_root}, args.template_root or default_templates,
                         as_of=as_of, days=args.days, min_chars=args.min_chars, min_words=args.min_words,
                         max_candidates=args.max_candidates, max_bytes=args.max_bytes, max_prompt_chars=args.max_prompt_chars)
        if (args.emit or args.clusters) and args.expected_digest != result["summary"]["digest"]:
            print(json.dumps({"error": "stale-summary", "message": "Inputs or settings changed. Obtain a new metadata-only summary; no prompt text emitted."}))
            return 2
        if args.clusters:
            raw = sys.stdin.buffer.read(8193)
            if len(raw) > 8192:
                raise ValueError("oversized cluster map")
            groups = json.loads(raw, object_pairs_hook=strict_pairs, parse_constant=reject_constant)
            output = cluster_metrics(result["packet"], groups)
        else:
            output = result["packet"] if args.emit else result["summary"]
        print(encoded(output).decode("utf-8"))
        return 0
    except Exception:
        print(json.dumps({"error": "collection-failed", "message": "Collection failed; no raw diagnostics or prompt text emitted."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
