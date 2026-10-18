---
name: browser-screenshot
description: Take a screenshot of the running web application for visual verification of UI/CSS changes. Use when iterating on frontend changes and need to see the result.
allowed-tools: "Read,Bash(~/.agents/skills/browser-screenshot/scripts/screenshot.sh:*)"
model-tier: economy
model: haiku
effort: medium
version: "1.2.0"
author: "flurdy"
---

# Browser Screenshot

Capture screenshots of the web application for visual verification during UI/CSS iteration.

## Prerequisites

No project setup or link is needed. The project must already have Node.js, the `playwright`
package in a `node_modules` reachable from its dependency directory, and a matching Chromium.
Never install packages or browsers from this skill; when the helper reports them missing, hand the
user its command (`npm install playwright && npx playwright install chromium`) to run themselves.
Existing project `scripts/screenshot` links keep working; leave them alone.

## Locate the helper

The canonical helper is `~/.agents/skills/browser-screenshot/scripts/screenshot.sh`. Only when
it is absent or `SKILLS_DIR` is set, resolve and validate the installed root read-only first.
A nonempty absolute `SKILLS_DIR` is authoritative; never replace an invalid override silently.
Otherwise prefer the canonical root, falling back to the Claude alias root only when this skill
unit is absent. Legacy Codex-only roots require explicit `SKILLS_DIR`.

```bash
set -eu
if [[ -z "${SKILLS_DIR:-}" ]]; then
  SKILLS_DIR="$HOME/.agents/skills"
  if [[ ! -d "$SKILLS_DIR/browser-screenshot" ]]; then
    SKILLS_DIR="${CLAUDE_SKILLS_DIR:-${CLAUDE_HOME:-$HOME/.claude}/skills}"
  fi
fi
[[ "$SKILLS_DIR" = /* ]] || { echo "SKILLS_DIR must be absolute" >&2; exit 1; }
for resource in SKILL.md scripts/screenshot.sh; do
  [[ -f "$SKILLS_DIR/browser-screenshot/$resource" && -r "$SKILLS_DIR/browser-screenshot/$resource" ]] || {
    echo "Missing browser-screenshot resource: $resource" >&2; exit 1;
  }
done
[[ -x "$SKILLS_DIR/browser-screenshot/scripts/screenshot.sh" ]] || { echo "screenshot.sh is not executable" >&2; exit 1; }
```

Missing resources stop the run; do not repair the installation. Reuse the verified absolute path
in later tool calls, since shell variables may not persist between them.

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

3. Run the installed helper directly as one command, passing the directory whose
   `node_modules` contains Playwright with `-C` (for example a nested `web` app). Omit `-C`
   when the current directory already resolves it; parent `node_modules` directories also
   count. Quote paths containing spaces, and never prefix the call with `cd … &&`.

```bash
~/.agents/skills/browser-screenshot/scripts/screenshot.sh -C web <url> <viewport>
```

   With an override or fallback root, use its verified absolute path instead:
   `"<verified-root>/browser-screenshot/scripts/screenshot.sh" -C "<dependency dir>" <url> <viewport>`.
   A relative output path (third argument) stays relative to the invocation directory.

   **Permissions:** the frontmatter grant is Claude Code metadata matching the canonical
   `~/.agents/...` prefix, the convention other skills use; exact matching of an expanded or
   override path is not verified, so expect a prompt there. Pi does not enforce `allowed-tools`,
   and Codex applies its own sandbox and approval policy. Report any prompt rather than widening
   permissions.

Screenshots are saved to a fresh private directory (mode 0700) created per run, unless you pass an explicit output path as the third argument. The script prints the full path it wrote — read it from the output rather than assuming a location. Screenshots may capture authenticated pages, which is why the directory is not a predictable shared one.

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
