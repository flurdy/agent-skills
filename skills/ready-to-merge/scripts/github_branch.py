"""Validated branch targets shared by the fixed-method entry points."""
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pr-status" / "scripts"))
from github_remote import default_github_host, normalize_host  # noqa: E402


def target_host():
    """GH_HOST when gh knows it, else github.com; an unknown GH_HOST is refused."""
    host = default_github_host()
    requested = os.environ.get("GH_HOST", "")
    if requested and normalize_host(requested) != host:
        print("GH_HOST is not a GitHub host known to gh", file=sys.stderr)
        raise SystemExit(2)
    return host


def branch_target():
    if len(sys.argv) != 4:
        print("usage: helper <owner> <repo> <branch>", file=sys.stderr)
        raise SystemExit(2)
    owner, repo, branch = sys.argv[1:]
    if not all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", part) for part in (owner, repo)):
        print("invalid repository identifier", file=sys.stderr)
        raise SystemExit(2)
    if not branch or branch.startswith("-") or branch == "HEAD":
        print("invalid branch name", file=sys.stderr)
        raise SystemExit(2)
    try:
        valid = subprocess.run(
            ["git", "check-ref-format", f"refs/heads/{branch}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    except FileNotFoundError:
        print("git is required", file=sys.stderr)
        raise SystemExit(127) from None
    if valid.returncode:
        print("invalid branch name", file=sys.stderr)
        raise SystemExit(2)
    return f"repos/{owner}/{repo}", quote(branch, safe="/")


def gh_api(*args):
    host = target_host()
    try:
        result = subprocess.run(["gh", "api", "--hostname", host, *args], check=False)
    except FileNotFoundError:
        print("gh is required", file=sys.stderr)
        raise SystemExit(127) from None
    raise SystemExit(result.returncode if result.returncode >= 0 else 128 - result.returncode)
