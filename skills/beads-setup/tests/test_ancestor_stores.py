"""Read-only classification of target and ancestor .beads entries; disposable fixtures only."""
from contextlib import redirect_stdout
import builtins
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ancestor_stores.py"


def load():
    spec = importlib.util.spec_from_file_location("ancestor_stores", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def registry_only(path):
    path.mkdir(parents=True)
    for name in ("registry.json", "registry.json.bak-2026-01-01", "registry.lock", "machine-id"):
        (path / name).write_text("{}\n")
    (path / "eventsData").mkdir()


class AncestorStoreTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "missing read-only ancestor classifier")
        self.module = load()
        temp = tempfile.TemporaryDirectory(prefix="ancestor-stores-")
        self.addCleanup(temp.cleanup)
        self.base = Path(os.path.realpath(temp.name))
        self.root = self.base / "outer" / "target"
        self.root.mkdir(parents=True)
        # Bound the walk to the fixture so real host ancestors cannot affect results.
        patcher = patch.object(self.module, "SCAN_STOP", str(self.base))
        patcher.start()
        self.addCleanup(patcher.stop)

    def classify(self):
        return self.module.classify(str(self.root))

    def kinds(self, report):
        return {Path(entry["path"]).parent.name: entry["kind"] for entry in report["entries"]}

    def test_no_entries_is_clear(self):
        self.assertEqual(self.classify(), {"root": str(self.root), "status": "clear", "entries": []})

    def test_registry_only_ancestor_is_reported_but_does_not_block(self):
        registry_only(self.base / "outer" / ".beads")
        report = self.classify()
        self.assertEqual(report["status"], "clear")
        self.assertEqual(self.kinds(report), {"outer": "registry-only"})

    def test_project_markers_redirects_and_unusual_entries_block(self):
        for marker in ("metadata.json", "config.yaml", "dolt", "embeddeddolt", "issues.db", "old.backup.db", "vc.db"):
            with self.subTest(marker=marker):
                ancestor = self.base / "outer" / ".beads"
                registry_only(ancestor)
                (ancestor / marker).mkdir() if "." not in marker else (ancestor / marker).write_text("x")
                report = self.classify()
                self.assertEqual(report["status"], "blocked")
                self.assertEqual(self.kinds(report), {"outer": "project-store"})
                self.assertIn(marker, report["entries"][0]["markers"])
                for child in sorted(ancestor.rglob("*"), reverse=True):
                    child.rmdir() if child.is_dir() else child.unlink()
                ancestor.rmdir()
        cases = {
            "redirect": lambda path: (path.mkdir(), (path / "redirect").write_text("../elsewhere/.beads\n")),
            "symlink": lambda path: path.symlink_to(self.base / "missing"),
            "not-directory": lambda path: path.write_text("not a store\n"),
        }
        for kind, make in cases.items():
            with self.subTest(kind=kind):
                ancestor = self.base / "outer" / ".beads"
                make(ancestor)
                report = self.classify()
                self.assertEqual((report["status"], self.kinds(report)), ("blocked", {"outer": kind}))
                if ancestor.is_dir() and not ancestor.is_symlink():
                    for child in ancestor.iterdir():
                        child.unlink()
                    ancestor.rmdir()
                else:
                    ancestor.unlink()

    def test_unreadable_ancestor_blocks(self):
        ancestor = self.base / "outer" / ".beads"
        ancestor.mkdir()
        with patch.object(self.module.os, "scandir", side_effect=PermissionError("denied")):
            report = self.classify()
        self.assertEqual((report["status"], self.kinds(report)), ("blocked", {"outer": "unreadable"}))

    def test_any_target_entry_blocks_even_when_registry_only(self):
        for make in (registry_only, lambda path: path.mkdir(), lambda path: path.symlink_to(self.base / "x")):
            with self.subTest(make=make):
                target = self.root / ".beads"
                make(target)
                report = self.classify()
                self.assertEqual((report["status"], self.kinds(report)), ("blocked", {"target": "target-entry"}))
                if target.is_symlink() or not target.is_dir():
                    target.unlink()
                else:
                    for child in target.iterdir():
                        child.rmdir() if child.is_dir() else child.unlink()
                    target.rmdir()

    def test_classification_never_opens_files_or_changes_the_ancestor(self):
        ancestor = self.base / "outer" / ".beads"
        registry_only(ancestor)
        before = {path: (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
                  for path in ancestor.rglob("*")}
        with patch.object(builtins, "open", side_effect=AssertionError("classification opened a file")):
            self.assertEqual(self.classify()["status"], "clear")
        after = {path: (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
                 for path in ancestor.rglob("*")}
        self.assertEqual(before, after)

    def test_cli_requires_a_canonical_absolute_directory_and_reports_json(self):
        registry_only(self.base / "outer" / ".beads")
        out = io.StringIO()
        with redirect_stdout(out):
            code = self.module.main([str(self.root)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "clear")
        (self.base / "outer" / ".beads" / "config.yaml").write_text("x\n")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.module.main([str(self.root)]), 2)
        link = self.base / "link"
        link.symlink_to(self.root)
        for bad in ("relative/path", str(self.base / "missing"), str(link)):
            with self.subTest(bad=bad), redirect_stdout(io.StringIO()) as printed:
                self.assertEqual(self.module.main([bad]), 1)
                self.assertEqual(json.loads(printed.getvalue()), {"status": "invalid-root"})


if __name__ == "__main__":
    unittest.main()
