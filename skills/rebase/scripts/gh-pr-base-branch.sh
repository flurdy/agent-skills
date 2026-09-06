#!/usr/bin/env bash
gh pr view --json baseRefName --jq '.baseRefName'
