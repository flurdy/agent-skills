#!/usr/bin/env bash
gh pr view --json number,url,title,headRepositoryOwner,headRepository \
  --jq '{number, url, title, owner: .headRepositoryOwner.login, repo: .headRepository.name}'
