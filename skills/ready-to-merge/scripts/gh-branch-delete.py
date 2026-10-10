#!/usr/bin/env python3
"""Delete one remote public-GitHub branch after caller confirmation; never retry."""
import sys

from github_branch import branch_target, gh_api

repository, branch = branch_target()
if branch in {"main", "master"}:
    print("refusing to delete a common trunk branch", file=sys.stderr)
    raise SystemExit(2)
gh_api("--method", "DELETE", f"{repository}/git/refs/heads/{branch}")
