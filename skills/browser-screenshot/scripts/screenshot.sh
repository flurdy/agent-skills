#!/usr/bin/env bash
# Takes a screenshot using playwright, resolved from the dependency directory's node_modules
# (and its parents). That directory is -C <dir> when given, otherwise the current directory.
# Usage: screenshot.sh [-C dependency-dir] [url] [viewport] [output-path]

set -euo pipefail

dependency_dir="$PWD"
if [ "${1:-}" = "-C" ]; then
  if [ -z "${2:-}" ] || [ ! -d "$2" ]; then
    echo "Error: -C needs an existing dependency directory" >&2
    exit 2
  fi
  dependency_dir="$(cd -- "$2" && pwd)"
  shift 2
fi

export SCREENSHOT_ARG_URL="${1:-}"
export SCREENSHOT_ARG_VIEWPORT="${2:-desktop}"
export SCREENSHOT_DEPENDENCY_DIR="$dependency_dir"

# Fail on missing dependencies before creating any output directory.
if ! (cd -- "$dependency_dir" && node --input-type=module -e 'import.meta.resolve("playwright")') 2>/dev/null; then
  echo "Error: Playwright is not resolvable from $dependency_dir." >&2
  echo "Pass the directory whose node_modules has Playwright with -C, or install it there yourself:" >&2
  echo "  npm install playwright && npx playwright install chromium" >&2
  exit 1
fi

if [ -n "${3:-}" ]; then
  case "$3" in
    /*) export SCREENSHOT_ARG_OUTPUT="$3" ;;
    *) export SCREENSHOT_ARG_OUTPUT="$PWD/$3" ;;
  esac
else
  # A fixed /tmp path is pre-claimable by another local user, as a world-readable
  # directory or as a symlink. Screenshots may capture authenticated pages.
  screenshot_dir="$(mktemp -d "${TMPDIR:-/tmp}/claude-screenshots.XXXXXX")"
  chmod 700 "$screenshot_dir"
  export SCREENSHOT_ARG_OUTPUT="$screenshot_dir/screenshot-${2:-desktop}.png"
fi

cd -- "$dependency_dir"
node --input-type=module <<'SCRIPT'
import { chromium } from 'playwright';
import { resolve } from 'path';

const url = process.env.SCREENSHOT_ARG_URL || process.env.SCREENSHOT_URL || 'http://localhost:3000';
const viewport = process.env.SCREENSHOT_ARG_VIEWPORT || 'desktop';
const outputPath = process.env.SCREENSHOT_ARG_OUTPUT;
if (!outputPath) {
  console.error('Error: SCREENSHOT_ARG_OUTPUT is not set');
  process.exit(1);
}

const viewports = {
  desktop: { width: 1280, height: 900 },
  tablet: { width: 768, height: 1024 },
  mobile: { width: 375, height: 812 },
};

// Support custom dimensions: "1024x768"
const customMatch = viewport.match(/^(\d+)x(\d+)$/);
const selected = customMatch
  ? { width: parseInt(customMatch[1]), height: parseInt(customMatch[2]) }
  : viewports[viewport] || viewports.desktop;

let browser;
try {
  browser = await chromium.launch({ headless: true });
} catch (err) {
  console.error(`Error: ${err.message}`);
  console.error(`Install the matching browser yourself from ${process.env.SCREENSHOT_DEPENDENCY_DIR}: npx playwright install chromium`);
  process.exit(1);
}
const context = await browser.newContext({ viewport: selected });
const page = await context.newPage();

try {
  await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
  const fullPath = resolve(outputPath);
  await page.screenshot({ path: fullPath, fullPage: false });
  console.log(fullPath);
} catch (err) {
  console.error(`Error: ${err.message}`);
  process.exit(1);
} finally {
  await browser.close();
}
SCRIPT
