"""Validated branch targets shared by the fixed-method entry points."""
import re
import subprocess
import sys
from urllib.parse import quote


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
    try:
        result = subprocess.run(["gh", "api", "--hostname", "github.com", *args], check=False)
    except FileNotFoundError:
        print("gh is required", file=sys.stderr)
        raise SystemExit(127) from None
    raise SystemExit(result.returncode if result.returncode >= 0 else 128 - result.returncode)
