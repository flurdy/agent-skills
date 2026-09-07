import concurrent.futures
from datetime import date, timedelta
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'watch_telemetry.py'
TODAY = date(2026, 9, 7)


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), 'the execution-counter helper is missing')
        spec = importlib.util.spec_from_file_location('watch_telemetry', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'state' / 'agent-skills' / 'watch-telemetry'
        self.env = {**os.environ, 'HOME': str(self.base / 'home'),
                    'XDG_STATE_HOME': str(self.base / 'state'), 'SECRET_CANARY': 'DO_NOT_RETAIN_THIS'}

    def run_cli(self, *args, input_text=''):
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=self.env,
                              cwd=self.base, input=input_text, text=True,
                              capture_output=True, timeout=10, check=False)

    def operate(self, action, day=TODAY, **kwargs):
        return self.module.operate(self.root, action, day, **kwargs)

    def record(self, watcher='watch-prs', harness='pi', event='tick', day=TODAY):
        return self.operate('record', day, watcher=watcher, harness=harness, event=event)

    def count(self, result, watcher='watch-prs', harness='pi', field='ticks'):
        return next(row[field] for row in result['rows']
                    if row['watcher'] == watcher and row['harness'] == harness)

    def test_default_off_never_creates_storage(self):
        result = self.run_cli('record', 'watch-prs', 'pi', 'tick')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        report = json.loads(self.run_cli('counts').stdout)
        self.assertEqual(report['status'], 'disabled')
        self.assertEqual(report['coverage'], 'unavailable')
        self.assertEqual(report['rows'], [])
        self.assertFalse(self.root.exists())

    def test_counters_separate_watchers_harnesses_and_events(self):
        self.operate('enable')
        for watcher in self.module.WATCHERS:
            for harness in ('pi', 'claude'):
                self.record(watcher, harness, 'invocation')
                if watcher != 'watch-rollout':
                    self.record(watcher, harness, 'tick')
        result = self.operate('counts')
        self.assertEqual(result['source'], 'agent-reported')
        self.assertEqual(result['coverage'], 'partial')
        self.assertEqual(len(result['rows']), 14)
        for row in result['rows']:
            self.assertEqual(row['invocations'], 1)
            self.assertEqual(row['ticks'], None if row['watcher'] == 'watch-rollout' else 1)

    def test_success_is_silent_and_payload_is_closed(self):
        self.assertEqual(self.run_cli('enable').returncode, 0)
        result = self.run_cli('record', 'watch-prs', 'claude', 'tick',
                              input_text='DO_NOT_RETAIN_THIS transcript https://private.example')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        raw = (self.root / 'counts.json').read_text()
        data = json.loads(raw)
        self.assertEqual(set(data), {'version', 'enabled', 'policy_day', 'days'})
        self.assertNotIn('DO_NOT_RETAIN_THIS', raw)
        self.assertNotIn('private.example', raw)
        self.assertNotIn(str(self.base), raw)
        self.assertEqual({p.name for p in self.root.iterdir()}, {'counts.json', '.lock'})
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        for path in self.root.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_bad_arguments_never_write_or_echo_values(self):
        for args in [('record', 'DO_NOT_RETAIN_THIS', 'pi', 'tick'),
                     ('record', 'watch-prs', 'DO_NOT_RETAIN_THIS', 'tick'),
                     ('record', 'watch-prs', 'pi', 'DO_NOT_RETAIN_THIS'),
                     ('record', 'watch-rollout', 'pi', 'tick'),
                     ('counts', '--days', '0'), ('counts', '--days', '91'),
                     ('counts', '--output', 'DO_NOT_RETAIN_THIS')]:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('DO_NOT_RETAIN_THIS', result.stdout + result.stderr)
                self.assertFalse(self.root.exists())

    def test_disable_preserves_history_but_does_not_record(self):
        self.operate('enable')
        self.record()
        self.operate('disable')
        before = (self.root / 'counts.json').read_bytes()
        self.record()
        self.assertEqual((self.root / 'counts.json').read_bytes(), before)
        report = self.operate('counts')
        self.assertEqual(report['status'], 'disabled')
        self.assertEqual(self.count(report), 1)
        self.assertEqual(report['settings_days']['mixed'], 1)

    def test_configuration_periods_are_not_execution_coverage(self):
        self.operate('enable', TODAY - timedelta(days=4))
        self.operate('disable', TODAY - timedelta(days=2))
        self.operate('enable')
        report = self.operate('counts', days=7)
        self.assertEqual(report['settings_days'], {'enabled': 2, 'disabled': 1, 'mixed': 2, 'unknown': 2})
        self.assertEqual(report['coverage'], 'partial')
        self.assertEqual(self.count(report), 0)

    def test_retention_is_90_utc_days_including_today(self):
        first = TODAY - timedelta(days=90)
        self.operate('enable', first)
        self.record(day=first)
        self.record(day=first + timedelta(days=1))
        self.record()
        report = self.operate('counts')
        self.assertEqual(self.count(report), 2)
        self.assertEqual(self.count(self.operate('counts', days=1)), 1)
        stored = json.loads((self.root / 'counts.json').read_text())
        self.assertNotIn(first.isoformat(), stored['days'])
        self.assertEqual(len(stored['days']), 90)
        self.assertEqual(report['window']['end_exclusive'], (TODAY + timedelta(days=1)).isoformat())

    def test_query_is_read_only_and_explicit_prune_handles_idle_retention(self):
        old = TODAY - timedelta(days=91)
        self.operate('enable', old)
        self.record(day=old)
        before = (self.root / 'counts.json').read_bytes()
        self.assertEqual(self.count(self.operate('counts')), 0)
        self.assertEqual((self.root / 'counts.json').read_bytes(), before)
        self.operate('prune')
        self.assertNotIn(old.isoformat(), (self.root / 'counts.json').read_text())

    def test_corrupt_unknown_oversized_and_future_state_are_unavailable(self):
        self.operate('enable')
        path = self.root / 'counts.json'
        valid = json.loads(path.read_text())
        cases = ['not-json', 'x' * (self.module.MAX_BYTES + 1),
                 json.dumps({**valid, 'prompt': 'DO_NOT_RETAIN_THIS'}),
                 json.dumps({**valid, 'policy_day': '2099-01-01'}),
                 json.dumps({**valid, 'version': 999}),
                 json.dumps({**valid, 'enabled': 1})]
        for raw in cases:
            with self.subTest(size=len(raw)):
                path.write_text(raw)
                result = self.run_cli('record', 'watch-prs', 'pi', 'tick')
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
                query = self.run_cli('counts')
                self.assertNotEqual(query.returncode, 0)
                self.assertEqual(json.loads(query.stdout)['status'], 'unavailable')
                self.assertNotIn('DO_NOT_RETAIN_THIS', query.stdout + query.stderr)
                self.assertEqual(path.read_text(), raw)

    def test_symlink_storage_is_refused_without_touching_target(self):
        self.root.parent.mkdir(parents=True)
        target = self.base / 'target'
        target.mkdir()
        self.root.symlink_to(target, target_is_directory=True)
        result = self.run_cli('enable')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(target.iterdir()), [])

    def test_symlink_and_hardlink_files_are_refused(self):
        self.operate('enable')
        path = self.root / 'counts.json'
        target = self.base / 'target.json'
        target.write_bytes(path.read_bytes())
        target.chmod(0o600)
        before = target.read_bytes()
        for link in ('symlink', 'hardlink'):
            path.unlink()
            if link == 'symlink':
                path.symlink_to(target)
            else:
                os.link(target, path)
            self.assertNotEqual(self.run_cli('counts').returncode, 0)
            self.assertEqual(self.run_cli('record', 'watch-prs', 'pi', 'tick').returncode, 0)
            self.assertEqual(target.read_bytes(), before)

    def test_permissive_storage_is_rejected_not_chmodded(self):
        self.operate('enable')
        self.root.chmod(0o755)
        result = self.run_cli('counts')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o755)

    def test_concurrent_processes_do_not_lose_increments(self):
        self.assertEqual(self.run_cli('enable').returncode, 0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.run_cli('record', 'watch-prs', 'pi', 'tick'), range(24)))
        self.assertTrue(all((r.returncode, r.stdout, r.stderr) == (0, '', '') for r in results))
        self.assertEqual(self.count(json.loads(self.run_cli('counts').stdout)), 24)

    def test_locked_store_skips_silently_without_increment(self):
        self.assertEqual(self.run_cli('enable').returncode, 0)
        before = (self.root / 'counts.json').read_bytes()
        with (self.root / '.lock').open('r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = self.run_cli('record', 'watch-prs', 'pi', 'tick')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertEqual((self.root / 'counts.json').read_bytes(), before)

    def test_missing_lock_is_unavailable_without_recreating_it(self):
        self.operate('enable')
        lock = self.root / '.lock'
        lock.unlink()
        result = self.run_cli('counts')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['error'], 'missing_lock')
        self.assertNotEqual(self.run_cli('enable').returncode, 0)
        self.assertFalse(lock.exists())

    def test_lock_symlink_cannot_modify_another_file(self):
        self.operate('enable')
        target = self.base / 'DO_NOT_RETAIN_THIS'
        target.write_text('untouched')
        lock = self.root / '.lock'
        lock.unlink()
        lock.symlink_to(target)
        self.assertNotEqual(self.run_cli('counts').returncode, 0)
        self.assertEqual(self.run_cli('record', 'watch-prs', 'pi', 'tick').returncode, 0)
        self.assertEqual(target.read_text(), 'untouched')

    def test_parent_symlink_is_refused_even_during_enable(self):
        target = self.base / 'target'
        target.mkdir()
        (self.base / 'state').symlink_to(target, target_is_directory=True)
        self.assertNotEqual(self.run_cli('enable').returncode, 0)
        self.assertEqual(list(target.iterdir()), [])

    def test_nested_payloads_and_invalid_counters_never_escape_validation(self):
        self.operate('enable')
        path = self.root / 'counts.json'
        original = path.read_text()
        bad_rows = [{'enabled': True, 'disabled': False, 'counts': {'DO_NOT_RETAIN_THIS': 1}},
                    {'enabled': True, 'disabled': False, 'counts': {}, 'note': 'DO_NOT_RETAIN_THIS'}]
        for value in (True, -1, 1.5, self.module.MAX_COUNT + 1, 'DO_NOT_RETAIN_THIS'):
            bad_rows.append({'enabled': True, 'disabled': False, 'counts': {'watch-prs:pi:tick': value}})
        for row in bad_rows:
            data = json.loads(original)
            data['days'][TODAY.isoformat()] = row
            raw = json.dumps(data)
            path.write_text(raw)
            result = self.run_cli('counts')
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('DO_NOT_RETAIN_THIS', result.stdout + result.stderr)
            self.assertEqual(path.read_text(), raw)

    def test_interrupted_write_is_bounded_and_requires_explicit_prune(self):
        self.operate('enable')
        pending = self.root / '.counts.tmp'
        pending.write_bytes((self.root / 'counts.json').read_bytes())
        pending.chmod(0o600)
        result = self.run_cli('counts')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['error'], 'pending_write')
        before = (self.root / 'counts.json').read_bytes()
        self.run_cli('record', 'watch-prs', 'pi', 'tick')
        self.assertEqual((self.root / 'counts.json').read_bytes(), before)
        self.assertTrue(pending.exists())
        self.operate('prune')
        self.assertFalse(pending.exists())
        self.assertEqual(self.count(self.operate('counts')), 0)

    def test_interrupted_first_enable_can_be_pruned_without_enrolling(self):
        self.operate('enable')
        (self.root / 'counts.json').rename(self.root / '.counts.tmp')
        self.assertNotEqual(self.run_cli('counts').returncode, 0)
        result = self.operate('prune')
        self.assertEqual(result['status'], 'disabled')
        self.assertFalse((self.root / 'counts.json').exists())
        self.assertFalse((self.root / '.counts.tmp').exists())

    def test_extreme_date_is_unavailable_without_traceback(self):
        self.operate('enable')
        path = self.root / 'counts.json'
        raw = json.dumps({'version': 1, 'enabled': True, 'policy_day': '0001-01-01',
                          'days': {'0001-01-01': {'enabled': True, 'disabled': False, 'counts': {}}}})
        path.write_text(raw)
        result = self.run_cli('record', 'watch-prs', 'pi', 'tick')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        result = self.run_cli('counts')
        self.assertEqual(result.stderr, '')
        self.assertEqual(json.loads(result.stdout)['status'], 'unavailable')
        self.assertEqual(path.read_text(), raw)

    def test_failed_disable_is_not_reported_as_absent_storage(self):
        self.operate('enable')
        before = (self.root / 'counts.json').read_bytes()
        with patch.object(self.module.os, 'replace', side_effect=FileNotFoundError('write disappeared')):
            with self.assertRaises(FileNotFoundError):
                self.operate('disable')
        self.assertEqual((self.root / 'counts.json').read_bytes(), before)
        self.assertTrue(json.loads(before)['enabled'])

    def test_atomic_replace_failure_keeps_old_file_and_no_temp(self):
        self.operate('enable')
        before = (self.root / 'counts.json').read_bytes()
        with patch.object(self.module.os, 'replace', side_effect=OSError('DO_NOT_RETAIN_THIS')):
            with self.assertRaises(OSError):
                self.record()
        self.assertEqual((self.root / 'counts.json').read_bytes(), before)
        self.assertEqual({p.name for p in self.root.iterdir()}, {'counts.json', '.lock'})


if __name__ == '__main__':
    unittest.main()
