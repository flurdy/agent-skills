---
name: browser-screenshot
description: Take a screenshot of the running web application for visual verification of UI/CSS changes. Use when iterating on frontend changes and need to see the result.
---

# Browser Screenshot

Capture screenshots of the web application for visual verification during UI/CSS iteration.

## Setup

1. Install playwright in the project (if not already):

```bash
npm install playwright
npx playwright install chromium
```

2. Symlink the screenshot script into the project's `scripts/` directory:

```bash
ln -sfn ~/.claude/skills/browser-screenshot/resources/screenshot.sh scripts/screenshot
```

## Usage

```
/browser-screenshot
/browser-screenshot http://localhost:3000
/browser-screenshot http://localhost:3000 mobile
```

## Instructions

1. Determine the URL to screenshot:
   - If `$ARGUMENTS` contains a URL, use it
   - Otherwise use the `SCREENSHOT_URL` env var if set
   - Default: `http://localhost:3000`

2. Determine the viewport:
   - If `$ARGUMENTS` contains `mobile`, use mobile viewport (375x812)
   - Default: desktop viewport (1280x800)
   - If `$ARGUMENTS` contains `both`, take two screenshots (desktop and mobile)

3. Run the screenshot script via the project symlink:

```bash
scripts/screenshot <url> <viewport>
```

If the symlink doesn't exist yet, create it first (see Setup above).

Screenshots are saved to `/tmp/claude-screenshots/screenshot-<viewport>.png` by default (e.g. `screenshot-desktop.png`, `screenshot-mobile.png`). Each run overwrites the previous screenshot for that viewport.

4. **Read the screenshot** using the Read tool to view the captured image. This is the critical step — you are a multimodal model and can see images.

5. Analyze the screenshot and report what you see, especially:
   - Layout issues (overlapping elements, alignment problems)
   - Spacing/margin problems
   - Color or styling discrepancies
   - Responsive behavior (if both viewports captured)

6. If the user asked you to fix a specific CSS issue, compare what you see against their description and suggest or apply fixes.

## Notes

- The script uses `waitUntil: 'networkidle'` with a 15s timeout — if the page loads async content, the screenshot will wait for it.
- Screenshots are full-page (scrollable content captured).
- For rapid iteration: make the CSS change, then run `/browser-screenshot` to verify, repeat.
