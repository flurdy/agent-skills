#!/usr/bin/env python3
"""tidy_settings.py — Sort/dedupe and audit Claude settings JSON files.

Reads one or more settings.{,local.}json files. Always emits a JSON report on
stdout. With --apply, writes back sort+dedupe transforms (a .bak is left next
to each file unless --no-backup is given).

Auto-applied transforms (with --apply):
  - Sort allow/deny/ask arrays by tool-prefix group, then alphabetical.
  - Remove exact duplicate entries.
  - Each written file is re-read and confirmed (applied.verified); write failures
    through a `.claude` symlink or onto a mode-600 file surface as write_error.

Report-only (the calling skill decides whether to remove):
  - subsumed_candidates: narrow entries covered by a broader `:*` entry.
  - broken_refs: file paths or Skill(name) references that don't exist.
  - risk_flags: entries matching known-risky patterns.
  - syntax_errors: entries that don't parse as a known permission shape.
  - cross_file.duplicates: identical entries appearing across multiple files.
  - worktree_promotions: entries in a --worktree file but missing from the
    --canonical file of the same basename (lost when the worktree is pruned).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

PREFIX_ORDER = [
    "Bash",
    "Read",
    "Edit",
    "Write",
    "WebFetch",
    "WebSearch",
    "Skill",
    "Task",
    "mcp__",
]

PERMISSION_RE = re.compile(r"^([A-Za-z][\w]*)\((.+)\)$")
BARE_TOOL_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
MCP_RE = re.compile(r"^mcp__[\w]+(?:__[\w]+)+$")

RISK_RULES_RAW = [
    (r"^Bash\(\*\)$", "high", "Unrestricted shell execution"),
    (r"^Bash\(sudo[: ]", "high", "Sudo execution"),
    (r"^Bash\(rm[ :]", "high", "Unrestricted rm"),
    (r"^Bash\(chmod[ :]", "medium", "Permission changes on files"),
    (r"^Bash\(curl[ :]", "medium", "Outbound HTTP — exfiltration risk"),
    (r"^Bash\(wget[ :]", "medium", "Outbound HTTP — exfiltration risk"),
    (r"^Bash\(ssh[ :]", "medium", "Remote shell access"),
    (r"^WebFetch\(\*\)$", "high", "Unrestricted web fetch"),
    (r"^WebFetch\(domain:\*\)$", "high", "Unrestricted domain fetch"),
    (r"^Read\(//?\)$", "high", "Root filesystem read"),
    (r"^Read\(/?\*\*\)$", "high", "Root filesystem read"),
    (r"^Edit\(\*\)$", "high", "Unrestricted file edit"),
    (r"^Edit\(/?\*\*\)$", "high", "Unrestricted file edit"),
    (r"^Write\(\*\)$", "high", "Unrestricted file write"),
    (r"^Write\(/?\*\*\)$", "high", "Unrestricted file write"),
]
RISK_RULES = [(re.compile(p), s, r) for (p, s, r) in RISK_RULES_RAW]


def parse_entry(entry: str) -> tuple[str, str]:
    if MCP_RE.match(entry):
        return ("mcp__", entry)
    m = PERMISSION_RE.match(entry)
    if m:
        return (m.group(1), m.group(2))
    if BARE_TOOL_RE.match(entry):
        return (entry, "")
    return ("", "")


def sort_key(entry: str) -> tuple[int, str]:
    prefix, _ = parse_entry(entry)
    try:
        idx = PREFIX_ORDER.index(prefix)
    except ValueError:
        idx = len(PREFIX_ORDER)
    return (idx, entry)


def find_subsumed(entries: list[str]) -> list[dict]:
    """Pairs where a narrow entry is covered by a broader `:*` entry."""
    broads: list[tuple[str, str, str]] = []
    for e in entries:
        m = re.match(r"^([A-Za-z][\w]*)\((.+):\*\)$", e)
        if m:
            broads.append((e, m.group(1), m.group(2)))

    out: list[dict] = []
    for narrow in entries:
        for full, prefix, cmd in broads:
            if narrow == full:
                continue
            inner = f"{prefix}("
            if not narrow.startswith(inner) or not narrow.endswith(")"):
                continue
            body = narrow[len(inner):-1]
            if body == cmd or body.startswith(cmd + " "):
                out.append({"narrow": narrow, "broad": full})
                break
    return out


def check_ref(entry: str) -> dict | None:
    m = re.match(r"^Bash\(([~/][^\s:)]*)", entry)
    if m:
        path = os.path.expanduser(m.group(1))
        if not os.path.exists(path):
            return {"kind": "missing_file", "resolved": path}
        return None

    m = re.match(r"^Skill\(([\w-]+)\)$", entry)
    if m:
        name = m.group(1)
        candidates = [
            os.path.expanduser(f"~/.agents/skills/{name}/SKILL.md"),
            str(Path.cwd() / "skills" / name / "SKILL.md"),
            str(Path.cwd() / ".claude" / "skills" / name / "SKILL.md"),
        ]
        if any(os.path.exists(p) for p in candidates):
            return None
        return {"kind": "missing_skill", "resolved": name}

    return None


def check_syntax(entry: str) -> str | None:
    if MCP_RE.match(entry):
        return None
    if PERMISSION_RE.match(entry):
        return None
    if BARE_TOOL_RE.match(entry):
        return None
    return "unrecognized permission shape"


def check_risk(entry: str) -> dict | None:
    for pattern, severity, reason in RISK_RULES:
        if pattern.match(entry):
            return {"severity": severity, "reason": reason}
    return None


def audit_array(entries: list[str]) -> dict:
    broken, risk, syntax = [], [], []
    for e in entries:
        ref = check_ref(e)
        if ref:
            broken.append({"entry": e, **ref})
        risk_info = check_risk(e)
        if risk_info:
            risk.append({"entry": e, **risk_info})
        syntax_err = check_syntax(e)
        if syntax_err:
            syntax.append({"entry": e, "reason": syntax_err})
    return {
        "subsumed_candidates": find_subsumed(entries),
        "broken_refs": broken,
        "risk_flags": risk,
        "syntax_errors": syntax,
    }


def transform_array(entries: list[str]) -> tuple[list[str], list[str]]:
    seen: set[str] = set()
    deduped: list[str] = []
    removed: list[str] = []
    for e in entries:
        if e in seen:
            removed.append(e)
        else:
            seen.add(e)
            deduped.append(e)
    deduped.sort(key=sort_key)
    return deduped, removed


def process_file(path: str, apply: bool, make_backup: bool) -> dict:
    file_path = Path(path)
    result: dict = {"path": str(file_path), "exists": file_path.exists()}
    if not file_path.exists():
        return result

    try:
        with open(file_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result["error"] = f"JSON parse error: {e}"
        return result
    except OSError as e:
        # Unreadable file (mode-600 the agent can't read, dangling symlink) —
        # report it rather than crashing the whole run.
        result["error"] = f"read error: {e}"
        return result

    perms = data.get("permissions") or {}
    allow_in = list(perms.get("allow", []))
    deny_in = list(perms.get("deny", []))
    ask_in = list(perms.get("ask", []))

    allow, allow_dupes = transform_array(allow_in)
    deny, deny_dupes = transform_array(deny_in)
    ask, ask_dupes = transform_array(ask_in)

    changed = allow != allow_in or deny != deny_in or ask != ask_in

    result["applied"] = {
        "changed": changed,
        "deduped": {"allow": allow_dupes, "deny": deny_dupes, "ask": ask_dupes},
        "backup": None,
    }
    result["report"] = {
        "current": {"allow": allow, "deny": deny, "ask": ask},
        "allow_audit": audit_array(allow),
        "deny_audit": audit_array(deny),
        "ask_audit": audit_array(ask),
        "allow_shadowed_by_deny": cross_section_conflicts(allow, deny),
    }

    if apply and changed:
        data.setdefault("permissions", {})
        data["permissions"]["allow"] = allow
        data["permissions"]["deny"] = deny
        data["permissions"]["ask"] = ask
        # Resolve through any `.claude` symlink and record where the bytes
        # actually go — this is the path that a write/read must agree on.
        result["applied"]["realpath"] = os.path.realpath(file_path)
        try:
            if make_backup:
                backup = file_path.with_suffix(file_path.suffix + ".bak")
                shutil.copy2(file_path, backup)
                result["applied"]["backup"] = str(backup)
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
        except OSError as e:
            # Dangling symlink, mode-600 file the agent can't write, read-only
            # mount, etc. Surface it loudly instead of pretending the write took.
            result["applied"]["write_error"] = str(e)
            result["applied"]["verified"] = False
            return result
        # Re-read from disk and confirm the permission arrays round-tripped.
        # Catches partial writes and writes that silently landed elsewhere.
        result["applied"]["verified"] = verify_persisted(file_path, allow, deny, ask)

    return result


def verify_persisted(
    file_path: Path, allow: list[str], deny: list[str], ask: list[str]
) -> bool:
    """Re-read file_path and confirm its permission arrays match what we wrote."""
    try:
        with open(file_path) as f:
            on_disk = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    perms = on_disk.get("permissions") or {}
    return (
        perms.get("allow", []) == allow
        and perms.get("deny", []) == deny
        and perms.get("ask", []) == ask
    )


def cross_section_conflicts(allow: list[str], deny: list[str]) -> list[dict]:
    """Find allow entries hard-blocked by a broader deny pattern."""
    deny_broads: list[tuple[str, str, str]] = []
    for d in deny:
        m = re.match(r"^([A-Za-z][\w]*)\((.+):\*\)$", d)
        if m:
            deny_broads.append((d, m.group(1), m.group(2)))

    conflicts: list[dict] = []
    for a in allow:
        for full, prefix, cmd in deny_broads:
            inner = f"{prefix}("
            if not a.startswith(inner) or not a.endswith(")"):
                continue
            body = a[len(inner):-1]
            if body == cmd or body.startswith(cmd + " "):
                conflicts.append({"allow_entry": a, "shadowed_by_deny": full})
                break
    return conflicts


def cross_file_duplicates(file_results: list[dict]) -> list[dict]:
    seen: dict[str, list[str]] = {}
    for fr in file_results:
        if not fr.get("exists") or "report" not in fr:
            continue
        for entry in fr["report"]["current"]["allow"]:
            seen.setdefault(entry, []).append(fr["path"])
    return [
        {"entry": e, "in": paths}
        for e, paths in seen.items()
        if len(paths) > 1
    ]


def compute_promotions(
    file_results: list[dict], canonical: list[str], worktree: list[str]
) -> list[dict]:
    """Entries present in a worktree settings file but absent from the canonical
    file of the same basename — these are lost when the worktree is pruned.

    Matched by basename so `settings.local.json` pairs with `settings.local.json`
    and `settings.json` with `settings.json`.
    """
    by_path = {fr["path"]: fr for fr in file_results}
    canon_by_base: dict[str, dict] = {}
    for path in canonical:
        fr = by_path.get(path)
        if fr and fr.get("exists") and "report" in fr:
            canon_by_base[os.path.basename(path)] = fr

    out: list[dict] = []
    for wt_path in worktree:
        wt_fr = by_path.get(wt_path)
        if not wt_fr or not wt_fr.get("exists") or "report" not in wt_fr:
            continue
        canon_fr = canon_by_base.get(os.path.basename(wt_path))
        if not canon_fr:
            continue
        wt_cur = wt_fr["report"]["current"]
        canon_cur = canon_fr["report"]["current"]
        for section in ("allow", "deny", "ask"):
            canon_set = set(canon_cur.get(section, []))
            only = [e for e in wt_cur.get(section, []) if e not in canon_set]
            if only:
                out.append(
                    {
                        "from": wt_path,
                        "into": canon_fr["path"],
                        "section": section,
                        "entries": only,
                    }
                )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Write sort/dedupe transforms back to disk.",
    )
    ap.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating .bak files when applying.",
    )
    ap.add_argument(
        "--canonical",
        action="append",
        default=[],
        metavar="PATH",
        help="Tag a (positional) path as a canonical main-worktree settings file "
        "— the promotion target. Repeatable.",
    )
    ap.add_argument(
        "--worktree",
        action="append",
        default=[],
        metavar="PATH",
        help="Tag a (positional) path as a per-worktree settings file whose "
        "extra entries are promotion candidates. Repeatable.",
    )
    ap.add_argument("files", nargs="+", help="Paths to settings JSON files.")
    args = ap.parse_args()

    results = [
        process_file(p, apply=args.apply, make_backup=not args.no_backup)
        for p in args.files
    ]

    output = {
        "files": results,
        "cross_file": {"duplicates": cross_file_duplicates(results)},
        "worktree_promotions": compute_promotions(
            results, args.canonical, args.worktree
        ),
    }
    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
