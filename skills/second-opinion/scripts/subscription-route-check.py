#!/usr/bin/env python3
"""Report subscription login classification without credential values."""
import json
import os
import pathlib
import re
import subprocess
import sys

OVERRIDES = {
    "claude": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"),
    "codex": ("OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"),
}

def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in OVERRIDES or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/+:-]{0,127}", sys.argv[2]):
        print("usage: subscription-route-check.py claude|codex model", file=sys.stderr)
        return 2
    route, model = sys.argv[1:]
    policy_basis = "missing"
    allowed_models = []
    try:
        config = json.loads((pathlib.Path.home() / ".agents/second-opinion/config.json").read_text())
        routes = config.get("subscriptionRoutes")
        candidate = routes.get(route) if config.get("version") == 1 and isinstance(routes, dict) else None
        if isinstance(candidate, list) and 1 <= len(candidate) <= 8 and all(isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/+:-]{0,127}", item) for item in candidate) and len(set(candidate)) == len(candidate):
            allowed_models = candidate
            policy_basis = "configured"
        elif candidate is not None or routes is not None:
            policy_basis = "invalid"
    except (OSError, json.JSONDecodeError):
        pass
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
    subscription_login = subscribed and not present
    output = {"route": route, "model": model, "subscriptionLogin": subscription_login, "auth": auth, "apiOverridesPresent": present, "policyBasis": policy_basis, "authorized": subscription_login and policy_basis == "configured" and model in allowed_models}
    print(json.dumps(output, separators=(",", ":")))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
