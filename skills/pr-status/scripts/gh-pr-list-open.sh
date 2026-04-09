#!/usr/bin/env bash
gh pr list --author "@me" --state open \
  --json number,title,headRefName,baseRefName,headRepositoryOwner,headRepository \
  --jq '.[] | {number, title, branch: .headRefName, base: .baseRefName, owner: .headRepositoryOwner.login, repo: .headRepository.name}'
