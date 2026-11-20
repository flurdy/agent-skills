#!/usr/bin/env python3
"""Read one branch on the default GitHub host; no mutation or retries."""
from github_branch import branch_target, gh_api

repository, branch = branch_target()
gh_api("--method", "GET", f"{repository}/branches/{branch}", "--jq", "{name, sha: .commit.sha}")
