#!/usr/bin/env python3
"""Path-free, stateless transport for the existing review-panel coordinator."""
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time

MAX_BYTES = 16 * 1024 * 1024
MAX_PROMPT_BYTES = 65536
HELPER = Path(__file__).resolve().with_name("review-panel.sh")
COMMON = {"version", "action", "panel", "prompt", "routeModels", "routeEfforts"}
DIGESTS = {"panelSha256", "promptSha256", "openrouterSha256"}
ACTIONS = {"check", "run-local", "run-openrouter", "decline-openrouter", "evaluate"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def text(value, pattern, message):
    require(isinstance(value, str) and re.fullmatch(pattern, value, flags=re.ASCII), message)
    return value


def validate(request):
    require(isinstance(request, dict), "request must be an object")
    require(type(request.get("version")) is int and request["version"] == 1, "version must be 1")
    action = request.get("action")
    require(isinstance(action, str) and action in ACTIONS, "unsupported action")
    allowed = COMMON | DIGESTS | {"timeout"} if action != "evaluate" else COMMON | {"policy", "check", "results"}
    if action == "run-openrouter":
        allowed |= {"consent"}
    require(not request.keys() - allowed, "unknown request fields; paths, commands and environment overrides are not supported")
    if action == "check":
        require(not request.keys() & DIGESTS, "check does not accept expected digests")
    prompt = request.get("prompt")
    require(isinstance(prompt, str) and 0 < len(prompt.encode("utf-8")) <= MAX_PROMPT_BYTES,
            "prompt must contain 1..65536 UTF-8 bytes")
    text(request.get("panel", "focused"), r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", "invalid panel")
    for field in ("routeModels", "routeEfforts"):
        values = request.get(field, {})
        require(isinstance(values, dict) and len(values) <= 8, "invalid route overrides")
        for key, value in values.items():
            text(key, r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", "invalid route ID")
            text(value, r"[A-Za-z0-9][A-Za-z0-9._/+:-]{0,255}", "invalid route override")
    timeout = request.get("timeout", 1800)
    require(type(timeout) is int and 1 <= timeout <= 1800, "timeout must be 1..1800 seconds")
    if action in {"run-local", "run-openrouter", "decline-openrouter"}:
        required = DIGESTS if action != "run-local" else DIGESTS - {"openrouterSha256"}
        for key in required | (request.keys() & DIGESTS):
            text(request.get(key), r"[a-f0-9]{64}", "missing or invalid digest")
    if action == "run-openrouter":
        require(request.get("consent") in ("confirmed", "configured"),
                "consent must be confirmed or configured; authorization is separate from this transport")
    if action == "evaluate":
        require(request.get("policy") in ("quorum", "consensus"), "invalid evaluation policy")
        require(isinstance(request.get("check"), dict), "check must be the check response")
        results = request.get("results")
        require(isinstance(results, list) and len(results) <= 2
                and all(isinstance(rows, list) and len(rows) <= 8 for rows in results),
                "results must contain at most two route-result arrays")
    return action


def save(directory, name, value):
    path = directory / name
    with path.open("x", encoding="utf-8") as output:
        output.write(value)
    return str(path)


def arguments(request, directory):
    action = request["action"]
    args = [str(HELPER), action]
    if action == "evaluate":
        args += ["--policy", request["policy"], "--check-file",
                 save(directory, "check.json", json.dumps(request["check"]))]
        for index, rows in enumerate(request["results"]):
            args += ["--results-file", save(directory, f"results-{index}.json", json.dumps(rows))]
        return args
    args += ["--panel", request.get("panel", "focused"), "--prompt-file",
             save(directory, "prompt", request["prompt"])]
    for field, flag in (("routeModels", "--route-model"), ("routeEfforts", "--route-effort")):
        for key, value in request.get(field, {}).items():
            args += [flag, f"{key}={value}"]
    for field, flag in (("panelSha256", "--panel-sha256"), ("promptSha256", "--prompt-sha256"),
                        ("openrouterSha256", "--openrouter-sha256")):
        if field in request:
            args += [flag, request[field]]
    if "timeout" in request and action != "check":
        args += ["--timeout", str(request["timeout"])]
    if action == "run-openrouter":
        args.append("--confirmed" if request["consent"] == "confirmed" else "--configured-consent")
    return args


def stop(process):
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def run(args, directory, timeout):
    # Nested coordinator artifacts stay inside the same disposable private directory.
    env = {**os.environ, "TMPDIR": str(directory)}
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True, env=env)
    output = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                require(time.monotonic() < deadline, "panel operation timed out")
                for key, _ in selector.select(timeout=0.1):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    destination = output[key.data]
                    limit = MAX_BYTES if key.data == "stdout" else 8192
                    require(len(destination) + len(chunk) <= limit, "panel output exceeded transport limit")
                    destination.extend(chunk)
            process.wait(timeout=max(0.01, deadline - time.monotonic()))
        if process.returncode != 0:
            # Coordinator diagnostics are bounded; no raw request is echoed here.
            sys.stderr.buffer.write(output["stderr"])
            raise ValueError(f"panel coordinator failed (exit {process.returncode})")
        require(bool(output["stdout"]), "empty coordinator response")
        json.loads(output["stdout"])
        sys.stdout.buffer.write(output["stdout"])
    finally:
        stop(process)
        process.stdout.close()
        process.stderr.close()


class PanelInterrupted(Exception):
    pass


def interrupted(signum, _frame):
    raise PanelInterrupted(f"panel operation interrupted ({signum})")


def main():
    try:
        require(len(sys.argv) == 1, "pass one JSON request on stdin; CLI arguments are not supported")
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES, "request exceeds 16 MiB transport limit")
        request = json.loads(raw, object_pairs_hook=unique_object)
        action = validate(request)
        # Install before allocation; TemporaryDirectory handles ordinary errors and signals.
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, interrupted)
        previous_umask = os.umask(0o077)
        try:
            with tempfile.TemporaryDirectory(prefix="second-opinion-") as root:
                directory = Path(root)
                # At most eight sequential routes, each with its existing per-route deadline.
                timeout = 8 * request.get("timeout", 1800) + 30 if action.startswith("run-") else 30
                run(arguments(request, directory), directory, timeout)
        finally:
            os.umask(previous_umask)
        return 0
    except (ValueError, OSError, UnicodeError, RecursionError, subprocess.TimeoutExpired, PanelInterrupted) as error:
        # JSONDecodeError includes input locations, not request content; avoid repr of payloads.
        if isinstance(error, (json.JSONDecodeError, UnicodeError, RecursionError)):
            print("ERROR: malformed JSON request/response", file=sys.stderr)
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
