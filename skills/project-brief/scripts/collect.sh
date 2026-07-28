#!/usr/bin/env bash
# Collect fresh, read-only local evidence for /project-brief.
# Remote Jira, GitHub, and release evidence remains the calling agent's responsibility.
set -u

MAX_REPOSITORIES=10
MAX_DOCUMENTS=8
MAX_DOCUMENT_BYTES=131072
MAX_BEADS_PER_STATUS=50

section() {
    printf '%s\n' "---$1---"
}

emit_payload() {
    local payload=${1:-}
    local line

    while IFS= read -r line || [ -n "$line" ]; do
        printf 'data=%s\n' "$line"
    done <<<"$payload"
}

run_probe() {
    local name=$1
    shift
    local output

    section "$name"
    if output=$("$@" 2>&1); then
        echo "status=OK"
        [ -n "$output" ] && emit_payload "$output"
        return 0
    fi

    echo "status=ERROR"
    [ -n "$output" ] && emit_payload "$output"
    return 1
}

run_beads_probe() {
    local name=$1
    local stored_status=$2
    local count_output list_output included omitted
    local count_status=0 list_status=0

    count_output=$(bd count --status "$stored_status" --readonly 2>&1) || count_status=$?
    list_output=$(bd list --status="$stored_status" --limit "$MAX_BEADS_PER_STATUS" --json --readonly 2>&1) || list_status=$?

    section "$name"
    if [ "$count_status" -ne 0 ] || [ "$list_status" -ne 0 ]; then
        echo "status=ERROR"
        [ -n "$count_output" ] && emit_payload "count: $count_output"
        [ -n "$list_output" ] && emit_payload "list: $list_output"
        return 1
    fi
    if ! [[ "$count_output" =~ ^[0-9]+$ ]]; then
        echo "status=ERROR"
        emit_payload "invalid count: $count_output"
        return 1
    fi
    if ! included=$(printf '%s\n' "$list_output" | python3 -c 'import json, sys; value=json.load(sys.stdin); assert isinstance(value, list); print(len(value))' 2>/dev/null); then
        echo "status=ERROR"
        emit_payload "list output was not a JSON array"
        return 1
    fi

    omitted=$((count_output - included))
    if [ "$omitted" -lt 0 ]; then
        echo "status=ERROR"
        emit_payload "list returned more rows than the count probe"
        return 1
    fi
    if [ "$omitted" -gt 0 ]; then
        echo "status=TRUNCATED"
    else
        echo "status=OK"
    fi
    printf 'data=total=%s\n' "$count_output"
    printf 'data=included=%s\n' "$included"
    printf 'data=omitted=%s\n' "$omitted"
    [ -n "$list_output" ] && emit_payload "$list_output"
}

section "TIMESTAMP"
emit_payload "$(date '+%Y-%m-%d %H:%M:%S %Z')"

if ! WORKSPACE_ROOT=$(pwd -P 2>&1); then
    section "SCOPE"
    echo "status=ERROR"
    emit_payload "$WORKSPACE_ROOT"
    exit 2
fi

if [ ! -f workspace.json ]; then
    section "SCOPE"
    echo "status=INVALID"
    echo "reason=workspace.json not found in current directory"
    exit 2
fi

if ! command -v project-workspace >/dev/null 2>&1; then
    section "SCOPE"
    echo "status=UNAVAILABLE"
    echo "reason=project-workspace command not found"
    exit 3
fi

DOCTOR_OUTPUT=$(project-workspace doctor --workspace . 2>&1)
DOCTOR_STATUS=$?
section "WORKSPACE-DOCTOR"
if [ "$DOCTOR_STATUS" -eq 0 ]; then
    echo "status=OK"
else
    echo "status=ERROR"
fi
[ -n "$DOCTOR_OUTPUT" ] && emit_payload "$DOCTOR_OUTPUT"
if [ "$DOCTOR_STATUS" -ne 0 ] && ! printf '%s\n' "$DOCTOR_OUTPUT" | grep -Fxq -- "Workspace: PASS"; then
    section "SCOPE"
    echo "status=INVALID"
    echo "reason=project-workspace topology validation failed"
    exit 2
fi

section "WORKSPACE"
echo "status=OK"
printf 'data=root=%s\n' "$WORKSPACE_ROOT"

TOPOLOGY_OUTPUT=$(python3 - "$MAX_REPOSITORIES" <<'PY'
import json
import pathlib
import sys

limit = int(sys.argv[1])
path = pathlib.Path("workspace.json")
try:
    manifest = json.loads(path.read_text(encoding="utf-8"))
except (OSError, UnicodeError, json.JSONDecodeError) as error:
    print(f"error={error}")
    raise SystemExit(2)

name = manifest.get("name")
repositories = manifest.get("repositories")
if not isinstance(name, str) or not name.strip() or not isinstance(repositories, list):
    print("error=workspace.json must contain a non-empty name and repositories array")
    raise SystemExit(2)

print(f"workspace={name}")
print(f"repository_total={len(repositories)}")
print(f"repository_included={min(len(repositories), limit)}")
print(f"repository_omitted={max(0, len(repositories) - limit)}")
for repository in repositories[:limit]:
    if not isinstance(repository, dict):
        print("error=repository entry must be an object")
        raise SystemExit(2)
    repository_name = repository.get("name")
    repository_path = repository.get("path")
    repository_role = repository.get("role", "")
    if not isinstance(repository_name, str) or not isinstance(repository_path, str):
        print("error=repository entry requires string name and path")
        raise SystemExit(2)
    print(f"repository={repository_name}|{repository_path}|{repository_role}")
PY
)
TOPOLOGY_STATUS=$?
section "TOPOLOGY"
if [ "$TOPOLOGY_STATUS" -ne 0 ]; then
    echo "status=ERROR"
    emit_payload "$TOPOLOGY_OUTPUT"
    section "SCOPE"
    echo "status=INVALID"
    echo "reason=workspace.json topology could not be parsed"
    exit 2
fi
if printf '%s\n' "$TOPOLOGY_OUTPUT" | grep -Eq '^repository_omitted=[1-9][0-9]*$'; then
    echo "status=TRUNCATED"
else
    echo "status=OK"
fi
emit_payload "$TOPOLOGY_OUTPUT"

section "SCOPE"
echo "status=OK"
echo "freshness=LOCAL_SNAPSHOT"
echo "note=Git remote-tracking refs are not fetched"

REPOSITORY_OMITTED=$(printf '%s\n' "$TOPOLOGY_OUTPUT" | awk -F= '$1 == "repository_omitted" { print $2; exit }')
if [ "${REPOSITORY_OMITTED:-0}" -gt 0 ]; then
    section "GIT-STATUS"
    echo "status=TRUNCATED"
    echo "reason=workspace status skipped because registered repositories exceed the fixed cap"
    section "BEADS-STATUS"
    echo "status=TRUNCATED"
    echo "reason=workspace status skipped because registered repositories exceed the fixed cap"
else
    run_probe "GIT-STATUS" project-workspace status --workspace . --section git || true
    run_probe "BEADS-STATUS" project-workspace status --workspace . --section beads || true
fi

if command -v bd >/dev/null 2>&1 && [ -d .beads ]; then
    run_beads_probe "BEADS-IN-PROGRESS" in_progress || true
    run_beads_probe "BEADS-OPEN" open || true
    run_beads_probe "BEADS-BLOCKED" blocked || true
else
    section "BEADS-IN-PROGRESS"
    echo "status=UNAVAILABLE"
    echo "reason=workspace Beads store or bd command not found"
    section "BEADS-OPEN"
    echo "status=UNAVAILABLE"
    echo "reason=workspace Beads store or bd command not found"
    section "BEADS-BLOCKED"
    echo "status=UNAVAILABLE"
    echo "reason=workspace Beads store or bd command not found"
fi

DOCUMENT_OUTPUT=$(python3 - "$MAX_DOCUMENTS" "$MAX_DOCUMENT_BYTES" <<'PY'
import pathlib
import sys

max_documents = int(sys.argv[1])
max_bytes = int(sys.argv[2])
roots = [pathlib.Path("docs/prds"), pathlib.Path("docs/architecture"), pathlib.Path("docs/adrs")]
extensions = {".md", ".txt", ".yaml", ".yml", ".json"}
files = []
unsafe_entries = []
for root in roots:
    if root.is_symlink():
        unsafe_entries.append(root)
        continue
    if not root.is_dir():
        continue
    root_resolved = root.resolve(strict=True)
    for path in sorted(root.rglob("*")):
        if path.name == ".gitkeep" or path.suffix.lower() not in extensions:
            continue
        if path.is_symlink():
            unsafe_entries.append(path)
            continue
        try:
            path.resolve(strict=True).relative_to(root_resolved)
        except (OSError, ValueError):
            unsafe_entries.append(path)
            continue
        if path.is_file():
            files.append(path)

included = []
used_bytes = 0
content_truncated = False
for path in files[:max_documents]:
    raw = path.read_bytes()
    remaining = max_bytes - used_bytes
    if remaining <= 0:
        content_truncated = True
        break
    selected = raw[:remaining]
    if len(selected) < len(raw):
        content_truncated = True
    included.append((path, selected, len(raw)))
    used_bytes += len(selected)
    if content_truncated:
        break

document_omitted = len(files) - len(included)
truncated = len(files) > max_documents or content_truncated or document_omitted > 0
if unsafe_entries:
    status = "ERROR"
elif truncated:
    status = "TRUNCATED"
elif not files:
    status = "EMPTY"
else:
    status = "OK"
print(f"status={status}")
print(f"unsafe_entry_count={len(unsafe_entries)}")
for unsafe_entry in unsafe_entries:
    print(f"unsafe_entry={unsafe_entry.as_posix()}")
print(f"document_total={len(files)}")
print(f"document_included={len(included)}")
print(f"document_omitted={max(0, document_omitted)}")
print(f"content_bytes={used_bytes}")
print(f"content_cap_bytes={max_bytes}")
for path, selected, original_size in included:
    print(f"path={path.as_posix()}|included_bytes={len(selected)}|original_bytes={original_size}")
    print("content-begin")
    text = selected.decode("utf-8", errors="replace")
    for line in text.splitlines():
        print(line)
    print("content-end")
PY
)
DOCUMENT_STATUS=$?
section "INTENT-DOCUMENTS"
if [ "$DOCUMENT_STATUS" -eq 0 ]; then
    DOC_CONTROL_STATUS=$(printf '%s\n' "$DOCUMENT_OUTPUT" | head -n 1 | cut -d= -f2-)
    case "$DOC_CONTROL_STATUS" in
        OK|EMPTY|TRUNCATED) echo "status=$DOC_CONTROL_STATUS" ;;
        *) echo "status=ERROR" ;;
    esac
    emit_payload "$(printf '%s\n' "$DOCUMENT_OUTPUT" | tail -n +2)"
else
    echo "status=ERROR"
    emit_payload "$DOCUMENT_OUTPUT"
fi
