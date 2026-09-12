#!/usr/bin/env python3
"""Report subscription login classification without credential values."""
import json
import os
import subprocess
import sys

OVERRIDES = {
    "claude": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"),
    "codex": ("OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"),
}

def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in OVERRIDES:
        print("usage: subscription-route-check.py claude|codex", file=sys.stderr)
        return 2
    route = sys.argv[1]
    present = [name for name in OVERRIDES[route] if os.environ.get(name)]
    auth = "unavailable"
    subscribed = False
    try:
        if route == "claude":
            result = subprocess.run(["claude", "auth", "status", "--json"], capture_output=True, text=True, check=True, timeout=15)
            status = json.loads(result.stdout)
            subscribed = status.get("loggedIn") is True and status.get("authMethod") == "claude.ai" and status.get("apiProvider") == "firstParty"
            auth = "claude.ai" if subscribed else "other"
        else:
            result = subprocess.run(["codex", "login", "status"], capture_output=True, text=True, check=True, timeout=15)
            subscribed = (result.stdout + result.stderr).strip() == "Logged in using ChatGPT"
            auth = "ChatGPT" if subscribed else "other"
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        pass
    output = {"version": 1, "route": route, "subscriptionLogin": subscribed and not present, "auth": auth, "apiOverridesPresent": present}
    print(json.dumps(output, separators=(",", ":")))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
