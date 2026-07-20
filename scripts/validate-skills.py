#!/usr/bin/env python3
"""Validate shared skill metadata, catalog parity, and local references."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

REQUIRED_FIELDS = (
    "name",
    "description",
    "model-tier",
    "effort",
    "version",
    "author",
)
ALLOWED_MODEL_TIERS = ("economy", "standard", "premium")
ALLOWED_EFFORTS = ("low", "medium", "high", "xhigh")
ALLOWED_CLAUDE_MODELS = ("haiku", "sonnet", "opus")
ARCHIVED_STATUSES = {"archived", "deprecated", "disabled"}
PLACEHOLDER_LINK_PARTS = ("{", "}", "…", "<", ">", "${")
LOCAL_SKILL_PATH = re.compile(
    r"(?:~/(?:\.agents/skills|\.claude/skills|\.codex/skills|\.pi/agent/skills)|\*)/"
    r"(?P<skill>[a-z0-9][a-z0-9-]*)/(?P<path>[^,:)\s]+)"
)
MARKDOWN_LINK_START = re.compile(r"!?\[[^\]]*\]\(")
REFERENCE_LINK = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]+>|\S+)")
TOP_LEVEL_FIELD = re.compile(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$")


def scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        if value[0] == '"':
            value = value[1:-1].replace(r'\"', '"').replace(r"\\", "\\")
        else:
            value = value[1:-1].replace("''", "'")
    return value.strip()


def parse_frontmatter(path: Path) -> tuple[dict[str, str], list[str], int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    errors: list[str] = []
    if not lines or lines[0] != "---":
        return {}, [f"{path}: frontmatter must start on line 1"], 0

    try:
        closing = lines.index("---", 1)
    except ValueError:
        return {}, [f"{path}: frontmatter has no closing delimiter"], 0

    fields: dict[str, str] = {}
    index = 1
    while index < closing:
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        match = TOP_LEVEL_FIELD.match(line)
        if not match:
            errors.append(f"{path}:{index + 1}: unsupported frontmatter line")
            index += 1
            continue

        key, raw_value = match.group(1), (match.group(2) or "").strip()
        if key in fields:
            errors.append(f"{path}:{index + 1}: duplicate frontmatter field '{key}'")
        if raw_value in {">", "|", ">-", "|-", ">+", "|+"}:
            block: list[str] = []
            index += 1
            while index < closing and (lines[index].startswith((" ", "\t")) or not lines[index]):
                if lines[index].strip():
                    block.append(lines[index].strip())
                index += 1
            fields[key] = " ".join(block)
            continue

        fields[key] = scalar(raw_value)
        index += 1

    return fields, errors, closing + 1


def split_table_row(line: str) -> list[str]:
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line.strip().strip("|"):
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            current.append(char)
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip())
    return cells


def normalized_header(cells: list[str]) -> list[str]:
    return [re.sub(r"\s*[¹²³⁴⁵⁶⁷⁸⁹⁰]+$", "", cell) for cell in cells]


def catalog_rows(readme: Path) -> list[list[str]]:
    if not readme.is_file():
        return []
    description_rows: list[list[str]] = []
    in_description_table = False
    for line in readme.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            in_description_table = False
            continue
        cells = split_table_row(line)
        if normalized_header(cells) == ["Skill", "Description"]:
            in_description_table = True
            continue
        if not cells or set(cells[0]) <= {"-", ":"}:
            continue
        if in_description_table and len(cells) >= 2:
            description_rows.append(cells)
    return description_rows


def catalog_name(cell: str) -> str:
    return cell.replace("`", "").split()[0].strip()


def validate_link_target(target: str, markdown: Path, root: Path, line_number: int) -> str:
    target = target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    if (
        not target
        or target.startswith(("#", "/"))
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target)
        or any(part in target for part in PLACEHOLDER_LINK_PARTS)
        or target.lower() in {"url", "path", "link"}
    ):
        return ""
    relative = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not relative:
        return ""
    resolved = (markdown.parent / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return f"{markdown}:{line_number}: relative link escapes repository: {target}"
    if not resolved.exists():
        return f"{markdown}:{line_number}: broken relative link: {target}"
    return ""


def inline_link_targets(line: str) -> list[str]:
    targets: list[str] = []
    for match in MARKDOWN_LINK_START.finditer(line):
        start = match.end()
        depth = 1
        escaped = False
        for index in range(start, len(line)):
            character = line[index]
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    targets.append(line[start:index])
                    break
    return targets


def validate_markdown_links(markdown: Path, root: Path) -> list[str]:
    errors: list[str] = []
    fenced = False
    for line_number, line in enumerate(markdown.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        targets = inline_link_targets(line)
        reference = REFERENCE_LINK.match(line)
        if reference:
            targets.append(reference.group(1))
        for target in targets:
            error = validate_link_target(target, markdown, root, line_number)
            if error:
                errors.append(error)
    return errors


def validate_allowed_tools(fields: dict[str, str], skill_file: Path, root: Path) -> list[str]:
    errors: list[str] = []
    allowed_tools = fields.get("allowed-tools", "")
    for match in LOCAL_SKILL_PATH.finditer(allowed_tools):
        referenced_skill = match.group("skill")
        relative = match.group("path")
        skills_root = (root / "skills").resolve()
        base = (skills_root / referenced_skill).resolve()
        try:
            base.relative_to(skills_root)
        except ValueError:
            errors.append(
                f"{skill_file}: allowed-tools skill directory resolves outside repository "
                f"skills/{referenced_skill}"
            )
            continue
        candidate = (base / relative).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            errors.append(
                f"{skill_file}: allowed-tools path escapes skill directory "
                f"skills/{referenced_skill}/{relative}"
            )
            continue

        if any(character in relative for character in "*?["):
            matches: list[Path] = []
            for path in base.glob(relative):
                try:
                    path.resolve().relative_to(base)
                except ValueError:
                    errors.append(
                        f"{skill_file}: allowed-tools glob resolves outside skill directory "
                        f"skills/{referenced_skill}/{relative}"
                    )
                    continue
                if path.is_file():
                    matches.append(path)
            exists = bool(matches)
        else:
            exists = candidate.is_file()
        if not exists:
            errors.append(
                f"{skill_file}: allowed-tools references missing local file "
                f"skills/{referenced_skill}/{relative}"
            )
    return errors


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    skills_root = root / "skills"
    readme = skills_root / "README.md"
    if not skills_root.is_dir():
        return [f"{skills_root}: skills directory not found"]

    skill_dirs = sorted(path for path in skills_root.iterdir() if path.is_dir())
    skill_files: list[Path] = []
    resolved_skills_root = skills_root.resolve()
    for directory in skill_dirs:
        try:
            directory.resolve().relative_to(resolved_skills_root)
        except ValueError:
            errors.append(f"{directory}: skill directory resolves outside repository")
            continue
        skill_file = directory / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"{directory}: skill directory has no SKILL.md")
            continue
        skill_files.append(skill_file)
    metadata: dict[str, dict[str, str]] = {}
    names: list[str] = []

    for skill_file in skill_files:
        fields, parse_errors, body_start = parse_frontmatter(skill_file)
        errors.extend(parse_errors)
        if parse_errors and not fields:
            continue

        directory_name = skill_file.parent.name
        for required in REQUIRED_FIELDS:
            if not fields.get(required, "").strip():
                errors.append(f"{skill_file}: missing required frontmatter field '{required}'")

        name = fields.get("name", "")
        if name and name != directory_name:
            errors.append(
                f"{skill_file}: frontmatter name '{name}' does not match directory '{directory_name}'"
            )
        if name and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            errors.append(f"{skill_file}: skill name '{name}' is not lowercase kebab-case")

        model_tier = fields.get("model-tier", "")
        if model_tier and model_tier not in ALLOWED_MODEL_TIERS:
            errors.append(
                f"{skill_file}: model-tier '{model_tier}' is invalid; expected one of "
                f"{', '.join(ALLOWED_MODEL_TIERS)}"
            )

        effort = fields.get("effort", "")
        if effort and effort not in ALLOWED_EFFORTS:
            errors.append(
                f"{skill_file}: effort '{effort}' is invalid; expected one of "
                f"{', '.join(ALLOWED_EFFORTS)}"
            )

        if "model" in fields and fields["model"] not in ALLOWED_CLAUDE_MODELS:
            errors.append(
                f"{skill_file}: model alias '{fields['model']}' is invalid; expected one of "
                f"{', '.join(ALLOWED_CLAUDE_MODELS)}"
            )

        status = fields.get("status", "").lower()
        body_lines = skill_file.read_text(encoding="utf-8").splitlines()[body_start:]
        first_body_line = next((line.strip() for line in body_lines if line.strip()), "")
        if status in ARCHIVED_STATUSES or first_body_line.upper().startswith(("ARCHIVED", "DEPRECATED")):
            errors.append(f"{skill_file}: archived/deprecated skill is present in the active skills directory")

        if name:
            names.append(name)
            metadata[name] = fields
        errors.extend(validate_allowed_tools(fields, skill_file, root))

    for name, count in Counter(names).items():
        if count > 1:
            errors.append(f"duplicate frontmatter skill name '{name}' appears {count} times")

    description_rows = catalog_rows(readme)
    if not readme.is_file():
        errors.append(f"{readme}: catalog not found")
        return errors

    description_names = [catalog_name(row[0]) for row in description_rows]
    skill_names = sorted(metadata)
    counts = Counter(description_names)
    for name in skill_names:
        if counts[name] != 1:
            errors.append(
                f"{readme}: skill '{name}' has {counts[name]} description rows; expected exactly 1"
            )
    for name in sorted(set(description_names) - set(skill_names)):
        errors.append(f"{readme}: description row references unknown skill '{name}'")
    for name, count in counts.items():
        if count > 1:
            errors.append(f"{readme}: duplicate description rows for skill '{name}'")

    if description_names != sorted(description_names):
        errors.append(f"{readme}: description table is not alphabetical by skill name")

    markdown_files = sorted(skills_root.glob("**/*.md"))
    for markdown in markdown_files:
        errors.extend(validate_markdown_links(markdown, root))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the validator parent repository)",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    errors = validate(root)
    if errors:
        print(f"Skill catalog validation failed with {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    skill_count = len(list((root / "skills").glob("*/SKILL.md")))
    print(f"Skill catalog validation: PASS ({skill_count} skills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
