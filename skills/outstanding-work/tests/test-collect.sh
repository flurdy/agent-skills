#!/usr/bin/env bash
set -euo pipefail
TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
python3 -m unittest discover -s "$TEST_DIR" -p 'test_*.py'
