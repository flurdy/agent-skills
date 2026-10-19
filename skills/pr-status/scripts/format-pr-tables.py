#!/usr/bin/env python3
"""Render the pr-status dashboard tables deterministically from collected JSON on stdin.

Input: {"now": ISO-8601 UTC, "closed": [row...], "open": [row...]}. Each row carries the
gh-pr-details fields plus owner, repo, title, closedAt (closed rows) and an optional jira
summary {"total": N, "author": name, "created": ISO} or {"error": true}. Output is markdown:
tables with plain `#N` PR cells, bounded cells, and link / full-name lines below each table.
"""

import json
import re
import sys
import unicodedata
from datetime import datetime, timezone

OPEN_COLUMNS = ["PR", "Ticket", "Jira 💬", "Title", "Branch", "Target", "Ready", "Push", "Sync", "CI",
                "Approved", "Threads", "LGTM"]
CLOSED_COLUMNS = ["PR", "Repo", "Ticket", "Jira 💬", "Title", "Status", "CI", "Ready", "Wait", "Closed"]
DEFAULT_BASES = {"main", "master"}
OPEN_TITLE_WIDTH, CLOSED_TITLE_WIDTH, BRANCH_WIDTH, TARGET_WIDTH = 25, 50, 30, 30
TOKEN_WIDTH = 30  # terminal renderers wrap unbroken words beyond this mid-word
POST_MERGE_CI_WINDOW_SECONDS = 2 * 24 * 3600
TICKET = re.compile(r"[A-Z]+-\d+")
BRANCH_PREFIX = re.compile(r"^[a-z]+(?:\([^)]*\))?!?/")
TICKET_PREFIX = re.compile(r"^[A-Z]+-\d+-")
ESCAPES = str.maketrans({char: "\\" + char for char in "\\|`*_[]<~"})
CI = {"SUCCESS": "✅", "FAILURE": "❌", "ERROR": "❌", "PENDING": "⏳", "EXPECTED": "⏳"}
ZERO_WIDTH = {"\u200d", "\ufe0f", "\ufe0e"}


def visible_width(text):
    total = 0
    for char in text:
        if char in ZERO_WIDTH or unicodedata.combining(char) or unicodedata.category(char) == "Cf":
            continue
        total += 2 if unicodedata.east_asian_width(char) in "WF" else 1
    return total


def parse_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def relative(now, value):
    moment = parse_time(value)
    if moment is None:
        return "—"
    return span(max(0, int((now - moment).total_seconds())))


def span(seconds):
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def take(text, limit):
    kept, used = [], 0
    for char in text:
        width = visible_width(char)
        if used + width > limit:
            break
        kept.append(char)
        used += width
    return "".join(kept)


def truncate(text, limit):
    text = " ".join(str(text or "").split())
    if visible_width(text) <= limit:
        return text, False
    return take(text, limit - 1).rstrip() + "…", True


def break_long_tokens(text):
    tokens = []
    for token in text.split(" "):
        while visible_width(token) > TOKEN_WIDTH:
            head = take(token, TOKEN_WIDTH)
            tokens.append(head)
            token = token[len(head):]
        tokens.append(token)
    return " ".join(tokens)


def cell(text):
    return break_long_tokens(str(text)).translate(ESCAPES) or "—"


def ticket(*sources):
    for source in sources:
        match = TICKET.search(source or "")
        if match:
            return match.group(0)
    return "—"


def jira_cell(now, row):
    jira = row.get("jira")
    if not isinstance(jira, dict):
        return "—"
    if jira.get("error"):
        return "?"
    total = jira.get("total")
    if not isinstance(total, int) or total <= 0:
        return "—"
    author = str(jira.get("author") or "").split()
    who = author[0] if author else "@" + str(jira.get("accountId") or "?")
    return f"💬 {total} · {who} · {relative(now, jira.get('created'))}"


def short_branch(branch):
    branch = BRANCH_PREFIX.sub("", branch or "")
    return TICKET_PREFIX.sub("", branch)


def sync(row):
    if row.get("mergeable") == "CONFLICTING" or row.get("mergeState") == "DIRTY":
        return "💥 conflict"
    behind = row.get("behindBy")
    if isinstance(behind, int) and behind > 0:
        return "⏪"
    if behind is None and row.get("mergeState") == "BEHIND":
        return "⏪"
    if row.get("mergeable") == "MERGEABLE" and behind == 0:
        return "✅"
    return "?"


def approved(row):
    decision = row.get("reviewDecision")
    approvers = row.get("approvers") or []
    if decision == "APPROVED":
        return "✅" * max(1, len(approvers))
    if approvers and decision != "CHANGES_REQUESTED":
        return "☑️" * len(approvers)
    if decision == "CHANGES_REQUESTED":
        return "👎"
    if row.get("isDraft"):
        return "—"
    count = row.get("reviewRequestCount")
    if count == 0:
        return "⚠️ 0"
    if isinstance(count, int) and count > 0:
        return f"🔔 {count}"
    return "🔔"


def lgtm(row):
    ready = (not row.get("isDraft") and row.get("base") in DEFAULT_BASES
             and row.get("reviewDecision") == "APPROVED" and row.get("checksState") == "SUCCESS"
             and row.get("unresolvedThreads") == 0 and row.get("mergeState") == "CLEAN")
    return "🚀" if ready else "🚧"


def url(row):
    return f"https://github.com/{row.get('owner')}/{row.get('repo')}/pull/{row.get('number')}"


def open_row(now, row):
    title, _ = truncate(row.get("title"), OPEN_TITLE_WIDTH)
    branch, branch_cut = truncate(short_branch(row.get("branch")), BRANCH_WIDTH)
    base = row.get("base") or ""
    full_names = []
    if base in DEFAULT_BASES:
        target = base
    else:
        target, target_cut = truncate(base, TARGET_WIDTH)
        target = "📌 " + cell(target)
        if target_cut:
            full_names.append(f"#{row.get('number')} target {base}")
    if branch_cut:
        full_names.append(f"#{row.get('number')} branch {row.get('branch')}")
    threads = row.get("unresolvedThreads")
    cells = [
        f"#{row.get('number')}",
        ticket(row.get("branch"), row.get("title")),
        jira_cell(now, row),
        cell(title),
        cell(branch),
        target,
        "🚧" if row.get("isDraft") else relative(now, row.get("readyAt")),
        relative(now, row.get("lastPush")),
        sync(row),
        CI.get(row.get("checksState"), "—"),
        approved(row),
        f"💬 {threads}" if isinstance(threads, int) and threads > 0 else "—",
        lgtm(row),
    ]
    return cells, full_names


def closed_row(now, row):
    title, _ = truncate(row.get("title"), CLOSED_TITLE_WIDTH)
    merged = bool(row.get("mergeCommitSha"))
    merged_at = parse_time(row.get("mergeCommitAt"))
    ci = "—"
    if merged and merged_at and (now - merged_at).total_seconds() <= POST_MERGE_CI_WINDOW_SECONDS:
        ci = CI.get(row.get("mainChecksState"), "—")
    ready_at, closed_at = parse_time(row.get("readyAt")), parse_time(row.get("closedAt"))
    wait = span(max(0, int((closed_at - ready_at).total_seconds()))) if ready_at and closed_at else "—"
    return [
        f"#{row.get('number')}",
        cell(row.get("repo") or "—"),
        ticket(row.get("title")),
        jira_cell(now, row),
        cell(title),
        "🔀" if merged else "🗑️",
        ci,
        relative(now, row.get("readyAt")),
        wait,
        relative(now, row.get("closedAt")),
    ]


def table(columns, rows):
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def links(rows):
    return "Links: " + " · ".join(f"[#{row.get('number')}]({url(row)})" for row in rows)


def render(payload):
    now = parse_time(payload.get("now"))
    if now is None:
        raise ValueError("'now' must be an ISO-8601 timestamp")
    closed, open_rows = payload.get("closed") or [], payload.get("open") or []
    out = []
    if closed:
        out += ["#### Recently closed", ""]
        out += table(CLOSED_COLUMNS, [closed_row(now, row) for row in closed])
        out += ["", links(closed), ""]
    if not open_rows:
        out.append("_No open PRs._")
        return "\n".join(out) + "\n"
    groups = {}
    for row in open_rows:
        groups.setdefault(str(row.get("repo")), []).append(row)
    for repo, rows in groups.items():
        rendered = [open_row(now, row) for row in rows]
        out += [f"#### Open — {repo}", ""]
        out += table(OPEN_COLUMNS, [cells for cells, _ in rendered])
        out += ["", links(rows)]
        full_names = [name for _, names in rendered for name in names]
        if full_names:
            out.append("Full names: " + " · ".join(full_names))
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level value must be an object")
        sys.stdout.write(render(payload))
    except (ValueError, TypeError, AttributeError) as error:
        sys.stderr.write(f"format-pr-tables: invalid JSON input: {error}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
