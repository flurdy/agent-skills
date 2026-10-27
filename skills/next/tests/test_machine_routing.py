from __future__ import annotations

import json
import subprocess

from workspace_fixture import SKILL_DIR, WorkspaceFixture, issue

LIST = SKILL_DIR / "scripts/next-bd"
SELECT = SKILL_DIR / "scripts/next-select"


class MachineRoutingTest(WorkspaceFixture):
    def setUp(self) -> None:
        super().setUp()
        self.context = self.home / ".agents/AGENTS.local.md"
        self.context.parent.mkdir(parents=True)
        self.environment["HOME"] = str(self.home)
        self.identity("Rivelino.")
        self.root = self.create_workspace(root_data={
            "ready": [
                self.row("leo", ["run-on:leonidas"]),
                self.row("riv", ["run-on:rivelino"]),
                self.row("both", ["run-on:leonidas", "run-on:rivelino"]),
                self.row("any", []),
                self.row("future", ["run-on:desk-42"]),
                self.row("bad", ["run-on:", "run-on:rivelino"]),
                self.row("backlog", ["run-on:leonidas"], 4),
            ],
            "in_progress": [self.row("claimed", ["run-on:leonidas"])],
            "blocked": [self.row("blocked", ["run-on:leonidas"])],
            "deferred": [self.row("deferred", ["run-on:leonidas"])],
        })

    def row(self, name: str, labels: list[str], priority: int = 2) -> dict:
        return issue(name, priority, "task", "2026-01-01", labels=labels)

    def identity(self, text: str) -> None:
        self.context.write_text(f"# Local context\n\n- Machine: {text}\n", encoding="utf-8")

    def listing(self, *args: str):
        return self.run_script(LIST, self.root, *args)

    def select(self, *args: str):
        return self.run_script(SELECT, self.root, *args, check=False)

    def candidates(self) -> list[str]:
        return [row["id"] for row in json.loads(self.listing("--json").stdout)]

    def assert_no_claim(self) -> None:
        self.assertFalse(any(call["arguments"][0] == "update" or
                             call["arguments"][:2] == ["comments", "add"]
                             for call in self.recorded_calls()))

    def test_all_views_agree_and_other_machines_are_not_numbered(self) -> None:
        expected = ["any", "both", "riv"]
        self.assertEqual(self.candidates(), expected)
        for flag in ("--list", "--safe"):
            text = self.listing(flag).stdout
            self.assertIn("Machine: rivelino", text)
            self.assertIn(str(self.context), text)
            head, ready = text.split("## Ready to", 1)
            other = head.split("## Other machines", 1)[1]
            self.assertNotIn("| leo |", ready)
            self.assertIn("| leo |", other)
            self.assertIn("| backlog |", other)
            self.assertIn("| bad |", other)
            self.assertNotIn("| # |", head)
            for status in ("claimed", "blocked", "deferred"):
                self.assertIn(f"| {status} |", head)
        packet = json.loads(self.listing("--safe-json").stdout)
        self.assertEqual(packet["machine"]["id"], "rivelino")
        self.assertEqual([row["id"] for row in packet["candidates"]], expected)
        self.assertEqual({row["id"] for row in packet["other_machines"]},
                         {"leo", "future", "bad", "backlog"})
        self.assertEqual(self.select("resolve", "1", "--expect-id", "any").returncode, 0)
        self.assert_no_claim()

    def test_generic_identity_normalizes_case_and_sentence_period(self) -> None:
        self.identity("LeOnIdAs.")
        self.assertEqual(self.candidates(), ["any", "both", "leo"])
        self.identity("DESK-42.")
        self.assertEqual(self.candidates(), ["any", "future"])
        self.context.write_text("- Machine: Rivelino.\n- Machine: rivelino\n")
        self.assertEqual(self.candidates(), ["any", "both", "riv"])

    def test_unknown_conflicting_malformed_and_missing_identity_are_visible(self) -> None:
        for text in ("", "- Machine: Rivelino.\n- Machine: Leonidas.\n",
                     "- Machine: wrong / value\n", "Machine = Rivelino\n",
                     "```md\n- Machine: Rivelino.\n```\n"):
            with self.subTest(text=text):
                self.context.write_text(text)
                result = self.listing("--json")
                self.assertEqual([row["id"] for row in json.loads(result.stdout)], ["any"])
                self.assertIn("Machine:", result.stderr)
                self.assertIn(str(self.context), result.stderr)
                self.assertIn("## Other machines", self.listing("--list").stdout)
        self.context.unlink()
        self.assertEqual(self.candidates(), ["any"])
        self.assertIn("missing", self.listing("--list").stdout.lower())

    def test_malformed_run_on_labels_do_not_become_unrestricted(self) -> None:
        fixture = self.root / ".beads/fixture.json"
        for label in ("run-on", "run-on:", "run-on:x:y", "run-on:two words", "run-on:x_1", " run-on:rivelino"):
            data = json.loads(fixture.read_text())
            data["ready"] = [self.row("broken", [label, "run-on:rivelino"])]
            fixture.write_text(json.dumps(data))
            self.assertEqual(self.candidates(), [], label)
            self.assertIn("malformed", self.listing("--list").stdout.lower())
        data["ready"] = [self.row("case", ["RUN-ON:RIVELINO"])]
        fixture.write_text(json.dumps(data))
        self.assertEqual(self.candidates(), ["case"])

    def test_direct_mismatch_refuses_before_any_claim_and_override_is_explicit(self) -> None:
        result = self.select("start", "workspace:leo")
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "machine-mismatch")
        self.assert_no_claim()
        result = self.select("start", "1", "--allow-other-machine")
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_claim()
        result = self.select("start", "workspace:leo", "--allow-other-machine")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        comments = [call for call in self.recorded_calls() if call["arguments"][:2] == ["comments", "add"]]
        self.assertEqual(len(comments), 1)
        self.assertIn("machine-override", comments[0]["arguments"][3])
        self.assertIn("rivelino", comments[0]["arguments"][3])
        self.assertIn("leonidas", comments[0]["arguments"][3])

    def test_override_cannot_waive_unknown_identity_or_malformed_labels(self) -> None:
        self.assertEqual(self.select("start", "workspace:bad", "--allow-other-machine").returncode, 7)
        self.context.unlink()
        self.assertEqual(self.select("start", "workspace:leo", "--allow-other-machine").returncode, 7)
        self.assert_no_claim()

    def test_override_cannot_waive_blocked_deferred_or_closed_status(self) -> None:
        fixture = self.root / ".beads/fixture.json"
        for status in ("blocked", "deferred", "closed"):
            data = json.loads(fixture.read_text())
            next(row for row in data["ready"] if row["id"] == "leo")["status"] = status
            fixture.write_text(json.dumps(data))
            self.assertEqual(self.select("start", "workspace:leo", "--allow-other-machine").returncode, 7)
        self.assert_no_claim()

    def test_label_and_identity_changes_are_checked_again_before_start(self) -> None:
        self.assertEqual(self.select("resolve", "3", "--expect-id", "riv").returncode, 0)
        self.identity("Leonidas")
        self.assertEqual(self.select("start", "3", "--expect-id", "riv").returncode, 6)
        self.assertEqual(self.select("start", "workspace:riv", "--expect-id", "riv").returncode, 7)
        self.identity("Rivelino")
        fixture = self.root / ".beads/fixture.json"
        data = json.loads(fixture.read_text())
        next(row for row in data["ready"] if row["id"] == "riv")["labels"] = ["run-on:leonidas"]
        fixture.write_text(json.dumps(data))
        self.assertEqual(self.select("start", "workspace:riv").returncode, 7)
        self.assert_no_claim()

    def test_native_safe_uses_same_eligibility_and_fresh_recheck(self) -> None:
        module = (SKILL_DIR / "pi/lease-selection.ts").as_uri()
        code = f"""
            import assert from 'node:assert/strict';
            import {{writeFile}} from 'node:fs/promises';
            import {{inspectCandidates,renderSafeList}} from {json.dumps(module)};
            const cwd = {json.dumps(str(self.root))};
            let observed = 0;
            const loadObserver = async () => async roots => {{ observed++; return roots.map(root => ({{kind:'free',root}})); }};
            const data = await inspectCandidates(cwd, {{loadObserver}});
            assert.equal(data.machine.id, 'rivelino');
            assert.deepEqual(data.unknown.map(row => row.id), ['any','both','riv']);
            assert.equal(data.other_machines.length, 4);
            const rendered = renderSafeList(data);
            assert.match(rendered, /Machine: rivelino/);
            assert.match(rendered, /## Other machines/);
            assert.match(rendered, /\\| leo \\|/);
            assert.equal(observed, 0);
            await assert.rejects(inspectCandidates(cwd, {{selector:'workspace:leo',loadObserver}}), /machine/i);
            await writeFile({json.dumps(str(self.context))}, '- Machine: Leonidas.\\n');
            await assert.rejects(inspectCandidates(cwd, {{selector:'workspace:riv',loadObserver}}), /machine/i);
            const fresh = await inspectCandidates(cwd, {{selector:'workspace:leo',loadObserver}});
            assert.equal(fresh.unknown[0].id, 'leo');
            const {{readFile}} = await import('node:fs/promises');
            const file = cwd + '/.beads/fixture.json';
            const fixture = JSON.parse(await readFile(file, 'utf8'));
            fixture.ready.find(row => row.id === 'leo').labels = ['run-on:desk-42'];
            await writeFile(file, JSON.stringify(fixture));
            await assert.rejects(inspectCandidates(cwd, {{selector:'workspace:leo',loadObserver}}), /machine/i);
        """
        result = subprocess.run(["node", "--input-type=module", "-e", code],
                                env=self.environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_no_claim()
