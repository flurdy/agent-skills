#!/usr/bin/env python3
"""Read-only classification of target and ancestor .beads entries for a fresh setup preview.

Lists entry names only: never opens, follows, repairs or changes an entry or store.
"""
import json
import os
import sys

SCAN_STOP = "/"
# bd 1.3.4 hasBeadsProjectFiles() markers; redirect and every *.db block too, stricter than bd.
PROJECT_MARKERS = {"metadata.json", "config.yaml", "dolt", "embeddeddolt"}


def classify_entry(path):
    if os.path.islink(path):
        return {"kind": "symlink"}
    if not os.path.isdir(path):
        return {"kind": "not-directory"}
    try:
        with os.scandir(path) as listing:
            names = sorted(entry.name for entry in listing)
    except OSError:
        return {"kind": "unreadable"}
    if "redirect" in names:
        return {"kind": "redirect"}
    markers = [name for name in names if name in PROJECT_MARKERS or name.endswith(".db")]
    if markers:
        return {"kind": "project-store", "markers": markers}
    return {"kind": "registry-only"}


def classify(root):
    entries = []
    directory = root
    while True:
        candidate = os.path.join(directory, ".beads")
        try:
            os.lstat(candidate)
        except FileNotFoundError:
            pass
        except OSError:
            entries.append({"path": candidate, "kind": "unreadable"})
        else:
            kind = {"kind": "target-entry"} if directory == root else classify_entry(candidate)
            entries.append({"path": candidate, **kind})
        parent = os.path.dirname(directory)
        if directory == SCAN_STOP or parent == directory:
            break
        directory = parent
    blocked = any(entry["kind"] != "registry-only" for entry in entries)
    return {"root": root, "status": "blocked" if blocked else "clear", "entries": entries}


def main(argv):
    if len(argv) != 1 or not os.path.isabs(argv[0]) or os.path.realpath(argv[0]) != argv[0] \
            or not os.path.isdir(argv[0]):
        print(json.dumps({"status": "invalid-root"}))
        return 1
    report = classify(argv[0])
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "clear" else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
