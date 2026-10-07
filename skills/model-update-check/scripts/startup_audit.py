"""Read-only startup configuration projection; never resolve credentials or launch Pi."""
from __future__ import annotations

import re

SOURCES = ("launcherConfig", "piSettings")
THINKING = {"off", "minimal", "low", "medium", "high", "xhigh", "max"}
MAX_SCOPE = 256


def expression(value):
    return (isinstance(value, str) and 0 < len(value) <= 512
            and re.fullmatch(r"[A-Za-z0-9_.*?~:/\[\]{}!+@=-]+", value) is not None)


def exact_reference(value):
    # Conservative lexical evidence, not Pi's fuzzy/provider/auth resolver.
    return (value if isinstance(value, str)
            and re.fullmatch(r"[a-z][a-z0-9_-]*/[a-z0-9_~.-]+(?:/[a-z0-9_~.-]+)*", value)
            else None)


def fields(value, source):
    validators = {"defaultModel": expression}
    if source == "launcherConfig":
        validators["defaultThinking"] = lambda v: isinstance(v, str) and v in THINKING
    else:
        validators.update(
            defaultProvider=lambda v: isinstance(v, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", v) is not None,
            defaultThinkingLevel=lambda v: isinstance(v, str) and v in THINKING,
            enabledModels=lambda v: isinstance(v, list) and len(v) <= MAX_SCOPE and all(expression(x) for x in v),
        )
    return {name: "missing" if name not in value else "ok" if check(value[name]) else "invalid"
            for name, check in validators.items()}


def scope_membership(identity, scope, healthy):
    if identity is None or not healthy:
        return "unknown"
    if not scope:
        return "unrestricted"
    if identity in scope:
        return "exact-match"
    if any(exact_reference(item) is None for item in scope):
        return "unresolved-patterns"
    return "not-exactly-listed"


def router_membership(identity, rows, sources, router):
    if identity is None or sources["routerConfig"]["status"] != "ok":
        return "unknown"
    if router.get("enabled") is False:
        return "router-disabled"
    candidates = [r for r in rows if r["source"] == "routerConfig" and r["identity"] == identity]
    if any(r.get("enabled") is not False for r in candidates):
        return "enabled-candidate"
    return "disabled-candidate" if candidates else "not-configured"


def audit(startup_paths, snapshot, sources, router, rows):
    """Read the same private snapshots as the collector; export only named fields."""
    configs, field_states, findings = {}, {}, []

    def finding(code, source, message):
        findings.append({"kind": "startup", "severity": "review", "code": code,
                         "source": source, "message": message})

    for name in SOURCES:
        selected = startup_paths[name]
        value, meta = snapshot(selected["snapshot"])
        meta.update(path=selected["path"], required=selected.get("required", False))
        states = fields(value, name) if meta["status"] == "ok" else {}
        if "invalid" in states.values():
            meta["status"] = "invalid"
        meta["fields"] = states
        sources[name] = meta
        field_states[name] = states
        configs[name] = value if meta["status"] == "ok" else {}
        if meta["status"] == "invalid" or (meta["status"] == "missing" and meta["required"]):
            finding("startup-config-unavailable", name,
                    "Startup configuration is invalid/unreadable or an explicitly selected file is missing; no defaults inferred.")

    launcher, settings = (configs[name] for name in SOURCES)
    scope = settings.get("enabledModels", [])
    defaults = {}
    for name in SOURCES:
        config = configs[name]
        model = config.get("defaultModel")
        provider = config.get("defaultProvider") if name == "piSettings" else None
        selected = f"{provider}/{model}" if provider and model else model if name == "launcherConfig" else None
        identity = exact_reference(selected)
        thinking_field = "defaultThinking" if name == "launcherConfig" else "defaultThinkingLevel"
        membership = scope_membership(identity, scope, sources["piSettings"]["status"] == "ok")
        router_state = router_membership(identity, rows, sources, router)
        defaults[name] = {
            "source": name, "config": sources[name]["path"], "sourceSha256": sources[name]["sha256"],
            "modelPath": "/defaultModel", "providerPath": "/defaultProvider" if name == "piSettings" else None,
            "configuredModel": model, "configuredProvider": provider, "identity": identity,
            "resolution": "exact-reference" if identity else "runtime-dependent",
            "thinking": config.get(thinking_field), "thinkingPath": "/" + thinking_field,
            "fields": field_states[name], "enabledModelsMembership": membership, "routerMembership": router_state,
        }
        if membership == "not-exactly-listed":
            finding("startup-default-not-listed", name,
                    "Configured default is not exactly listed in enabledModels; this is scope drift, not proof of denied access.")
        if router_state in {"disabled-candidate", "not-configured"}:
            finding("startup-not-router-enabled", name,
                    "Configured startup default is not an enabled global router candidate; startup and skill routing are separate choices.")
    left, right = (defaults[name]["identity"] for name in SOURCES)
    if left and right and left != right:
        finding("startup-defaults-disagree", "launcherConfig",
                "Fresh pl and saved Pi defaults name different models; this may be intentional. Review before changing either.")

    return {
        "schemaVersion": 1, "auditOnly": True, "scope": "selected user-level files; no project/session/host overrides",
        "defaults": defaults,
        "enabledModels": {"config": sources["piSettings"]["path"], "path": "/enabledModels",
                          "sourceSha256": sources["piSettings"]["sha256"],
                          "status": (field_states["piSettings"].get("enabledModels", "missing")
                                     if sources["piSettings"]["status"] == "ok" else sources["piSettings"]["status"]),
                          "entries": [{"expression": item, "resolution": "exact-reference" if exact_reference(item) else "runtime-dependent"}
                                      for item in scope]},
        "enabledRouterCandidates": [r["identity"] for r in rows if r["source"] == "routerConfig"
                                    and r.get("enabled") is not False and r.get("routerEnabled") is not False],
        "launchPaths": [
            {"path": "fresh-pl", "configuredSelection": launcher.get("defaultModel"), "runtimeModel": None,
             "selectionRule": "Explicit pl --model wins; otherwise fresh pl passes its configured defaultModel. Missing/ignored fields use launcher built-ins, not Pi settings. Built-ins and installed launcher are not probed."},
            {"path": "plain-pi", "configuredSelection": right, "firstEnabledExpression": scope[0] if scope else None,
             "runtimeModel": None,
             "selectionRule": "Pi 1.0 CLI: explicit model wins; fresh startup prefers saved default in resolved enabledModels, else first resolved scope entry. Empty resolved scope falls back to saved/authenticated defaults. Trusted project settings override user settings; patterns, auth and other Pi versions require native resolution."},
            {"path": "resume-continue", "runtimeModel": None,
             "selectionRule": "Restore saved session model unless explicitly overridden; runtime availability may force fallback. pl does not inject fresh defaults. No session files inspected."},
            {"path": "orca", "runtimeModel": None,
             "selectionRule": "Depends on host launch arguments, CLI/SDK settings and saved session. No Orca invocation inspected; do not assume pl defaults apply."},
        ],
        "limitations": [
            "Exact references are configuration evidence, not runtime model identity, availability or launch authorization.",
            "enabledModels membership is lexical only; aliases, globs, case variants and thinking suffixes require native resolution.",
            "Missing optional files are normal fallback states; built-in defaults are not guessed or copied from another source.",
            "No startup config is included in migration proposals or companion-applier authority.",
        ],
        "findings": findings,
    }
