#!/usr/bin/env bash
# Takes a screenshot using playwright. Resolves playwright from cwd's node_modules.
# Usage: screenshot.sh [url] [viewport] [output-path]

SCREENSHOT_DIR="/tmp/claude-screenshots"
mkdir -p "$SCREENSHOT_DIR"

export SCREENSHOT_ARG_URL="${1:-}"
export SCREENSHOT_ARG_VIEWPORT="${2:-desktop}"
export SCREENSHOT_ARG_OUTPUT="${3:-$SCREENSHOT_DIR/screenshot-${2:-desktop}.png}"

node --input-type=module <<'SCRIPT'
import { chromium } from 'playwright';
import { resolve } from 'path';

const url = process.env.SCREENSHOT_ARG_URL || process.env.SCREENSHOT_URL || 'http://localhost:3000';
const viewport = process.env.SCREENSHOT_ARG_VIEWPORT || 'desktop';
const outputPath = process.env.SCREENSHOT_ARG_OUTPUT || `/tmp/screenshot-${Date.now()}.png`;

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

const browser = await chromium.launch({ headless: true });
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
