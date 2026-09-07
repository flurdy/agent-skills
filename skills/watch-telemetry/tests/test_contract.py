from collections import Counter
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WATCHERS = ('watch-prs', 'watch-release', 'watch-pr-feedback', 'watch-review-requests',
            'watch-rollout', 'watch-actions-rollout', 'watch-flux-rollout')
HELPER = '~/.agents/skills/watch-telemetry/scripts/watch_telemetry.py'


class ConsumerContracts(unittest.TestCase):
    def test_every_entry_has_only_a_narrow_record_permission(self):
        for name in WATCHERS:
            with self.subTest(watcher=name):
                text = (ROOT / name / 'SKILL.md').read_text()
                self.assertIn(f'Bash({HELPER} record:*)', text.split('---', 2)[1])
                self.assertIn(f'{HELPER} record {name} {{harness}} invocation', text)
                self.assertIn('not when reading this file', text)
                self.assertIn('Never enable collection', text)
                self.assertNotIn(f'Bash({HELPER}:*)', text)
                self.assertNotIn(f'Bash({HELPER} enable', text)

    def test_every_pi_tick_prompt_records_before_work(self):
        for name in WATCHERS:
            if name == 'watch-rollout':
                continue
            with self.subTest(watcher=name):
                text = re.split(r'^#{3,4} Claude Code fallback$', (ROOT / name / 'SKILL.md').read_text(), flags=re.M)[0]
                prompts = [block for block in re.findall(r'```text\n(.*?)```', text, re.S)
                           if 'Load and follow the skill named' in block]
                self.assertEqual(len(prompts), 1)
                command = f'{HELPER} record {name} pi tick'
                self.assertEqual(prompts[0].count(command), 1)
                self.assertLess(prompts[0].index(command), prompts[0].index('Load and follow'))
                self.assertIn('telemetry failure must not block', prompts[0])

    def test_every_claude_template_records_with_claude_attribution(self):
        expected_blocks = {'watch-prs': 2, 'watch-release': 2, 'watch-pr-feedback': 1,
                           'watch-review-requests': 1, 'watch-actions-rollout': 1, 'watch-flux-rollout': 1}
        for name, number in expected_blocks.items():
            with self.subTest(watcher=name):
                text = re.split(r'^#{3,4} Claude Code fallback$', (ROOT / name / 'SKILL.md').read_text(), flags=re.M)[1]
                blocks = [block for block in re.findall(r'```(?:text)?\n(.*?)```', text, re.S)
                          if '/loop ' in block or 'ScheduleWakeup(' in block]
                self.assertEqual(len(blocks), number)
                command = f'{HELPER} record {name} claude tick'
                for block in blocks:
                    self.assertEqual(block.count(command), 1)
                    self.assertNotIn(f'record {name} pi tick', block)
                if name in ('watch-pr-feedback', 'watch-review-requests'):
                    self.assertIn(f'replace the Pi recorder call with `{command}`', text)

    def test_documented_commands_execute_against_an_isolated_install(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            installed = home / '.agents/skills/watch-telemetry'
            installed.parent.mkdir(parents=True)
            installed.symlink_to(ROOT / 'watch-telemetry', target_is_directory=True)
            env = {**os.environ, 'HOME': str(home), 'XDG_STATE_HOME': str(home / 'state')}

            def run(command):
                result = subprocess.run(['/bin/bash', '-c', command], cwd=home, env=env,
                                        text=True, capture_output=True, timeout=10, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout

            run(f'{HELPER} enable')
            expected = Counter()
            for watcher in WATCHERS:
                text = (ROOT / watcher / 'SKILL.md').read_text()
                for harness in ('pi', 'claude'):
                    invocation = f'{HELPER} record {watcher} {{harness}} invocation'
                    self.assertIn(invocation, text)
                    self.assertEqual(run(invocation.replace('{harness}', harness)), '')
                    expected[watcher, harness, 'invocations'] += 1
                pattern = re.escape(HELPER) + rf' record {watcher} (pi|claude) tick'
                for match in re.finditer(pattern, text):
                    self.assertEqual(run(match.group()), '')
                    expected[watcher, match.group(1), 'ticks'] += 1
            report = json.loads(run(f'{HELPER} counts --days 1'))
            self.assertEqual(report['coverage'], 'partial')
            for row in report['rows']:
                for field in ('invocations', 'ticks'):
                    if row['watcher'] == 'watch-rollout' and field == 'ticks':
                        self.assertIsNone(row[field])
                    else:
                        self.assertEqual(row[field], expected[row['watcher'], row['harness'], field])

    def test_dispatcher_stays_invocation_only(self):
        text = (ROOT / 'watch-rollout/SKILL.md').read_text()
        self.assertNotIn('watch_loop', text)
        self.assertNotRegex(text, r'record watch-rollout \S+ tick')
        self.assertIn('telemetry is the only command exception', text)
        self.assertIn('Forward all remaining arguments unchanged.', text)

    def test_read_only_boundaries_have_a_named_counter_exception(self):
        for name in ('watch-pr-feedback', 'watch-review-requests'):
            text = (ROOT / name / 'SKILL.md').read_text()
            self.assertIn('sole local-write exception', text)
            self.assertIn('never stores feedback, queue state, or review content', text)

    def test_telemetry_contract_documents_limitations_and_is_gated(self):
        path = ROOT / 'watch-telemetry/SKILL.md'
        self.assertTrue(path.exists(), 'missing owning skill')
        text = path.read_text()
        for term in ('agent-reported', 'partial', '90 UTC', 'disabled by default',
                     'not proof of zero use', 'old scheduled prompts', 'duplicate',
                     'no background cleanup', 'XDG_STATE_HOME', 'Python 3.10', 'counts --days 90'):
            self.assertIn(term.casefold(), ' '.join(text.split()).casefold())
        self.assertIn('test-watch-telemetry', (ROOT.parent / 'Makefile').read_text())


if __name__ == '__main__':
    unittest.main()
