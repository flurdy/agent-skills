---
name: browser-screenshot
description: Take a screenshot of the running web application for visual verification of UI/CSS changes. Use when iterating on frontend changes and need to see the result.
allowed-tools: "Read,Bash(npm:*),Bash(npx:*),Bash(scripts/screenshot:*),Bash(ln:*)"
version: "1.0.0"
author: "flurdy"
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
SKILLS_DIR="${SKILLS_DIR:-${CODEX_HOME:-$HOME/.codex}/skills}"
if [[ ! -d "$SKILLS_DIR" ]]; then
  SKILLS_DIR="${CLAUDE_HOME:-$HOME/.claude}/skills"
fi
ln -sfn "$SKILLS_DIR/browser-screenshot/scripts/screenshot.sh" scripts/screenshot
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
   - If `$ARGUMENTS` contains `tablet`, use tablet viewport (768x1024)
   - If `$ARGUMENTS` contains a custom size like `1024x768`, use those dimensions
   - Default: desktop viewport (1280x900)
   - If `$ARGUMENTS` contains `both`, take two screenshots (desktop and mobile)
   - Keep both dimensions under 2000px to avoid image limit errors

3. Run the screenshot script via the project symlink:

```bash
scripts/screenshot <url> <viewport>
```

If the symlink doesn't exist yet, create it first (see Setup above).

Screenshots are saved to `/tmp/claude-screenshots/screenshot-<viewport>.png` by default (e.g. `screenshot-desktop.png`, `screenshot-mobile.png`). Each run overwrites the previous screenshot for that viewport.

4. **Read the screenshot** using the available image-reading tool to view the captured image. This is the critical step because the model can inspect the captured UI directly.

5. Analyze the screenshot and report what you see, especially:
   - Layout issues (overlapping elements, alignment problems)
   - Spacing/margin problems
   - Color or styling discrepancies
   - Responsive behavior (if both viewports captured)

6. If the user asked you to fix a specific CSS issue, compare what you see against their description and suggest or apply fixes.

## Notes

- The script uses `waitUntil: 'networkidle'` with a 15s timeout — if the page loads async content, the screenshot will wait for it.
- Screenshots capture the viewport only (not full-page scroll) to stay within the 2000px image dimension limit.
- For rapid iteration: make the CSS change, then run `/browser-screenshot` to verify, repeat.
