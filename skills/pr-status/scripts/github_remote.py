"""GitHub remote identity parsing shared by checkout discovery and review snapshots.

github.com is always trusted. GitHub Enterprise hosts are trusted only when the
GitHub CLI already knows them: a top-level entry in its local ``hosts.yml``, or
``GH_HOST`` while an Enterprise token variable is set. No network call is made.

The default host for unqualified owner/repo targets is ``GH_HOST`` when gh knows
it, otherwise github.com. Hosts named by a remote or PR URL always win.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse

DEFAULT_HOST = "github.com"
REPOSITORY_PATTERN = re.compile(r"^[^/\s]+/[^/\s]+$")
SSH_GITHUB_HOST_PATTERN = re.compile(
    r"^(?:[A-Za-z0-9-]+\.)?github\.com$",
    flags=re.IGNORECASE,
)
HOSTNAME_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
)
HOSTS_FILE_ENTRY = re.compile(r"^([^\s#:][^:]*):\s*(?:#.*)?$")
ENTERPRISE_TOKEN_VARIABLES = ("GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")


class GitHubRemote(NamedTuple):
    host: str
    repository: str

    @property
    def qualified(self) -> str:
        """owner/repo on github.com, host/owner/repo elsewhere."""
        if self.host == DEFAULT_HOST:
            return self.repository
        return f"{self.host}/{self.repository}"


def normalize_host(value: str) -> str | None:
    host = value.strip().casefold()
    return host if HOSTNAME_PATTERN.fullmatch(host) else None


def gh_hosts_file(environ: Mapping[str, str]) -> Path:
    if environ.get("GH_CONFIG_DIR"):
        return Path(environ["GH_CONFIG_DIR"]) / "hosts.yml"
    if environ.get("XDG_CONFIG_HOME"):
        return Path(environ["XDG_CONFIG_HOME"]) / "gh" / "hosts.yml"
    return Path.home() / ".config" / "gh" / "hosts.yml"


def known_github_hosts(environ: Mapping[str, str] | None = None) -> frozenset[str]:
    environment = os.environ if environ is None else environ
    hosts = {DEFAULT_HOST}
    try:
        lines = gh_hosts_file(environment).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        lines = []
    for line in lines:
        entry = HOSTS_FILE_ENTRY.fullmatch(line)
        host = normalize_host(entry.group(1).strip("'\"")) if entry else None
        if host:
            hosts.add(host)
    if any(environment.get(name) for name in ENTERPRISE_TOKEN_VARIABLES):
        host = normalize_host(environment.get("GH_HOST", ""))
        if host:
            hosts.add(host)
    return frozenset(hosts)


def default_github_host(
    environ: Mapping[str, str] | None = None, hosts: Iterable[str] | None = None
) -> str:
    environment = os.environ if environ is None else environ
    known = known_github_hosts(environment) if hosts is None else frozenset(hosts)
    host = normalize_host(environment.get("GH_HOST", ""))
    return host if host and host in known else DEFAULT_HOST


def _trusted_host(
    hostname: str, hosts: frozenset[str], *, ssh: bool
) -> str | None:
    host = hostname.casefold()
    if host in hosts:
        return host
    if ssh and SSH_GITHUB_HOST_PATTERN.fullmatch(host):
        return DEFAULT_HOST
    return None


def _repository(owner: str, name: str) -> str | None:
    result = f"{owner}/{name.removesuffix('.git')}"
    return result if REPOSITORY_PATTERN.fullmatch(result) else None


def github_remote(
    remote_url: str, hosts: Iterable[str] = (DEFAULT_HOST,)
) -> GitHubRemote | None:
    """Parse a remote whose host is github.com, a github.com SSH alias, or in hosts."""
    trusted = frozenset(host.casefold() for host in hosts) | {DEFAULT_HOST}
    value = remote_url.strip()
    scp = re.fullmatch(
        r"(?:[^@/:]+@)?([^/:]+):([^/\s]+)/([^/\s]+?)(?:\.git)?/?",
        value,
        flags=re.IGNORECASE,
    )
    if scp:
        host = _trusted_host(scp.group(1), trusted, ssh=True)
        repository = _repository(scp.group(2), scp.group(3)) if host else None
        return GitHubRemote(host, repository) if host and repository else None

    try:
        parsed = urlparse(value if "://" in value else f"https://{value}")
        hostname = parsed.hostname or ""
    except ValueError:
        return None
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https", "ssh"}:
        return None
    host = _trusted_host(hostname, trusted, ssh=scheme == "ssh")
    if host is None or parsed.query or parsed.fragment or parsed.params:
        return None
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2:
        return None
    repository = _repository(*parts)
    return GitHubRemote(host, repository) if repository else None


def github_repository(
    remote_url: str, hosts: Iterable[str] = (DEFAULT_HOST,)
) -> str | None:
    remote = github_remote(remote_url, hosts)
    return remote.repository if remote else None


def main(argv: list[str]) -> int:
    """Print owner/repo for one remote on the default host; exit 1 for any other remote."""
    if len(argv) != 1:
        print("usage: github_remote.py REMOTE_URL", file=sys.stderr)
        return 2
    hosts = known_github_hosts()
    remote = github_remote(argv[0], hosts)
    if remote is None or remote.host != default_github_host(hosts=hosts):
        return 1
    print(remote.repository)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
