#!/usr/bin/env python3
"""Read one public-GitHub branch; no mutation or retries."""
from github_branch import branch_target, gh_api

repository, branch = branch_target()
gh_api("--method", "GET", f"{repository}/branches/{branch}", "--jq", "{name, sha: .commit.sha}")
