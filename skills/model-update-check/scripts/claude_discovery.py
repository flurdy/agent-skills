#!/usr/bin/env python3
"""Safe Claude metadata fallback. No SDK initialization, auth inspection or inference."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from catalog_refresh import run_native

DOC_URL = "https://code.claude.com/docs/en/model-config.md"
SDK_URL = "https://platform.claude.com/docs/en/agent-sdk/typescript#query"
MAX_DOC_BYTES = 1024 * 1024
VERSION = r"\d+\.\d+\.\d+"
MODEL_LABEL = r"(?:Sonnet|Opus|Haiku|Fable) \d+(?:\.\d+)*"


def documentation(path, status):
    result = {"status": status, "url": DOC_URL, "sha256": None,
              "checkedAt": datetime.now(timezone.utc).isoformat(),
              "scope": "Public documentation, not native inventory or account access.",
              "aliases": [], "versionRequirements": []}
    if status != "ok":
        return result
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(MAX_DOC_BYTES + 1)
        if len(raw) > MAX_DOC_BYTES:
            raise ValueError("oversized")
        content = raw.decode("utf-8")
    except (OSError, ValueError):
        result["status"] = "invalid-output"
        return result
    result["sha256"] = hashlib.sha256(raw).hexdigest()
    section = re.search(r"^### Model aliases\s*\n(.*?)(?=^### |\Z)", content, re.M | re.S)
    aliases = re.findall(r"^\| \*\*`([a-z][a-z0-9\[\]]*)`\*\* \|", section[1] if section else "", re.M)
    requirements = []
    for pattern, reverse in (
        (rf"({MODEL_LABEL}) requires (?:Claude Code )?v({VERSION}) or later", False),
        (rf"Use v({VERSION}) or later with ({MODEL_LABEL})", True),
    ):
        for match in re.finditer(pattern, content):
            label, version = reversed(match.groups()) if reverse else match.groups()
            requirements.append({"modelLabel": label, "minimumVersion": version, "quote": match[0]})
    result.update(aliases=list(dict.fromkeys(aliases)), versionRequirements=requirements)
    if not aliases or not requirements:
        result["status"] = "unrecognized-output"
    return result


def collect(path, docs_status):
    status, output = run_native(["claude", "--version"], 10, max_bytes=4096)
    version = None
    if status == "ok":
        match = re.fullmatch(rf"({VERSION}) \(Claude Code\)", output.strip())
        if match:
            version = match[1]
        else:
            status = "invalid-version"
    return {
        "client": {"status": status, "installedVersion": version, "command": ["claude", "--version"],
                   "scope": "CLI on PATH only; the extension executable/version is not verified."},
        "inventory": {"status": "not-assessed", "reason": "no-reviewed-metadata-only-cli",
                      "supportedInterface": "Agent SDK Query.supportedModels() / initializationResult()",
                      "documentation": SDK_URL,
                      "limitation": "The standalone CLI has no documented model-list command. SDK initialization is not run: it can consult authentication/organization metadata and native startup can migrate saved settings. Installation and initialization-effects review are separate work."},
        "documentation": documentation(path, docs_status),
        "accountAccess": "unverified", "billing": "unverified", "extensionCompatibility": "unverified",
    }


def client_support(model, evidence):
    result = {"status": "unverified", "scope": "Documented CLI minimum only, not exact-model acceptance, entitlement or extension compatibility."}
    docs = evidence.get("documentation", {})
    base = model.removesuffix("[1m]")
    if docs.get("status") != "ok":
        return result
    if base in docs.get("aliases", []):
        return {**result, "status": "native-resolution"}
    match = re.fullmatch(r"claude-([a-z]+)-(\d+(?:-\d+)*)", base)
    if not match:
        return result
    label = match[1].capitalize() + " " + match[2].replace("-", ".")
    requirements = [r for r in docs.get("versionRequirements", []) if r["modelLabel"] == label]
    minima = {r["minimumVersion"] for r in requirements}
    version = evidence.get("client", {}).get("installedVersion")
    if len(minima) != 1 or not version:
        return result
    minimum = minima.pop()
    sufficient = tuple(map(int, version.split("."))) >= tuple(map(int, minimum.split(".")))
    return {**result, "status": "minimum-version-met" if sufficient else "minimum-version-mismatch",
            "minimumVersion": minimum, "modelLabel": label, "citation": {"url": docs["url"], "quote": requirements[0]["quote"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documentation", required=True)
    parser.add_argument("--documentation-status", choices=("ok", "error", "skipped", "missing-curl"), required=True)
    args = parser.parse_args()
    print(json.dumps(collect(args.documentation, args.documentation_status)))


if __name__ == "__main__":
    main()
