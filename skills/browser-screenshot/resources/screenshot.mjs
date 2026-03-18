#!/usr/bin/env node

import { chromium } from 'playwright';
import { resolve } from 'path';

const url = process.argv[2] || process.env.SCREENSHOT_URL || 'http://localhost:3000';
const viewport = process.argv[3] || 'desktop';
const outputPath = process.argv[4] || `screenshot-${Date.now()}.png`;

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
