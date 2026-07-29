#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat >&2 <<'EOF'
usage: confirmed-bd.sh <proposal-sha256> <confirmed-sha256> <action> [arguments]
actions:
  preflight-create|create --title VALUE --type VALUE --priority VALUE \
    --description VALUE --acceptance VALUE --metadata VALUE [--parent ID]
  update-type ID
  set-parent ID PARENT_ID
  add-blocker DEPENDENT_ID PREREQUISITE_ID
EOF
    exit 2
}

fail() {
    printf 'confirmed-bd: %s\n' "$*" >&2
    exit 2
}

valid_sha256() {
    [[ $1 =~ ^[0-9a-f]{64}$ ]]
}

valid_id() {
    [[ $1 =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]
}

[[ $# -ge 3 ]] || usage
proposal_sha=$1
confirmed_sha=$2
action=$3
shift 3

valid_sha256 "$proposal_sha" || fail 'proposal fingerprint must be 64 lowercase hex characters'
valid_sha256 "$confirmed_sha" || fail 'confirmed fingerprint must be 64 lowercase hex characters'
[[ $proposal_sha == "$confirmed_sha" ]] || fail 'confirmed fingerprint does not match proposal'

case "$action" in
    preflight-create|create)
        title=''
        type=''
        priority=''
        description=''
        acceptance=''
        metadata=''
        parent=''
        while [[ $# -gt 0 ]]; do
            [[ $# -ge 2 ]] || usage
            value=$2
            case "$1" in
                --title)
                    [[ -z $title ]] || fail 'duplicate --title'
                    title=$value
                    ;;
                --type)
                    [[ -z $type ]] || fail 'duplicate --type'
                    type=$value
                    ;;
                --priority)
                    [[ -z $priority ]] || fail 'duplicate --priority'
                    priority=$value
                    ;;
                --description)
                    [[ -z $description ]] || fail 'duplicate --description'
                    description=$value
                    ;;
                --acceptance)
                    [[ -z $acceptance ]] || fail 'duplicate --acceptance'
                    acceptance=$value
                    ;;
                --metadata)
                    [[ -z $metadata ]] || fail 'duplicate --metadata'
                    metadata=$value
                    ;;
                --parent)
                    [[ -z $parent ]] || fail 'duplicate --parent'
                    parent=$value
                    ;;
                *)
                    fail "unsupported create flag: $1"
                    ;;
            esac
            shift 2
        done
        [[ -n $title && -n $type && -n $priority && -n $description && -n $acceptance && -n $metadata ]] || \
            fail 'create requires title, type, priority, description, acceptance, and metadata'
        [[ $type =~ ^(task|feature|bug|epic|decision|chore)$ ]] || fail "unsupported issue type: $type"
        [[ $priority =~ ^(P?[0-4])$ ]] || fail "invalid priority: $priority"
        [[ $description == *'Source plan:'* ]] || fail 'description must contain a Source plan citation'
        metadata_error=''
        if ! metadata_error=$(python3 - "$metadata" <<'PY'
import json
import re
import sys

try:
    value = json.loads(sys.argv[1])
except (json.JSONDecodeError, TypeError):
    print("metadata must be valid JSON")
    raise SystemExit(1)

if not isinstance(value, dict):
    print("metadata must be a JSON object")
    raise SystemExit(1)

requirements = {
    "plan_source": lambda item: isinstance(item, str) and bool(item.strip()),
    "plan_source_sha256": lambda item: isinstance(item, str) and bool(re.fullmatch(r"[0-9a-f]{64}", item)),
    "plan_proposal_ref": lambda item: isinstance(item, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", item)),
}
for key, valid in requirements.items():
    if key not in value or not valid(value[key]):
        print(f"metadata must contain a valid non-empty {key}")
        raise SystemExit(1)
PY
        ); then
            fail "${metadata_error:-metadata validation failed}"
        fi
        if [[ -n $parent ]]; then
            valid_id "$parent" || fail "invalid parent ID: $parent"
        fi

        command=(bd create --title "$title" --type "$type" --priority "$priority" \
            --description "$description" --acceptance "$acceptance" --metadata "$metadata")
        if [[ -n $parent ]]; then
            command+=(--parent "$parent")
        fi
        if [[ $action == preflight-create ]]; then
            command+=(--dry-run)
        fi
        command+=(--json)
        "${command[@]}"
        ;;
    update-type)
        [[ $# -eq 1 ]] || usage
        valid_id "$1" || fail "invalid issue ID: $1"
        bd update "$1" --type epic --json
        ;;
    set-parent)
        [[ $# -eq 2 ]] || usage
        valid_id "$1" || fail "invalid issue ID: $1"
        valid_id "$2" || fail "invalid parent ID: $2"
        bd update "$1" --parent "$2" --json
        ;;
    add-blocker)
        [[ $# -eq 2 ]] || usage
        valid_id "$1" || fail "invalid dependent ID: $1"
        valid_id "$2" || fail "invalid prerequisite ID: $2"
        bd dep add "$1" "$2" --type blocks --json
        ;;
    *)
        fail "unsupported action: $action"
        ;;
esac
