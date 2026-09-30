"""GitHub remote identity parsing shared by checkout discovery and review snapshots."""

from __future__ import annotations

import re
from urllib.parse import urlparse

REPOSITORY_PATTERN = re.compile(r"^[^/\s]+/[^/\s]+$")
SSH_GITHUB_HOST_PATTERN = re.compile(
    r"^(?:[A-Za-z0-9-]+\.)?github\.com$",
    flags=re.IGNORECASE,
)


def github_repository(remote_url: str) -> str | None:
    value = remote_url.strip()
    scp = re.fullmatch(
        r"(?:[^@/:]+@)?([^/:]+):([^/\s]+)/([^/\s]+?)(?:\.git)?/?",
        value,
        flags=re.IGNORECASE,
    )
    if scp and SSH_GITHUB_HOST_PATTERN.fullmatch(scp.group(1)):
        repository = f"{scp.group(2)}/{scp.group(3)}"
        return repository if REPOSITORY_PATTERN.fullmatch(repository) else None

    try:
        parsed = urlparse(value if "://" in value else f"https://{value}")
        hostname = parsed.hostname or ""
    except ValueError:
        return None
    if parsed.scheme.casefold() not in {"http", "https", "ssh"}:
        return None
    exact_github = hostname.casefold() == "github.com"
    ssh_alias = parsed.scheme.casefold() == "ssh" and SSH_GITHUB_HOST_PATTERN.fullmatch(
        hostname
    )
    if not exact_github and not ssh_alias:
        return None
    if parsed.query or parsed.fragment or parsed.params:
        return None
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2:
        return None
    owner, repository = parts
    if repository.endswith(".git"):
        repository = repository[:-4]
    result = f"{owner}/{repository}"
    return result if REPOSITORY_PATTERN.fullmatch(result) else None
