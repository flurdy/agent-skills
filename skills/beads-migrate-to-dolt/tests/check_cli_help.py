"""Opt-in command-surface checks; never a migration or a live database probe."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


BD = shutil.which('bd')


def check_help(output, command, flags):
    """Check command identity and declared flags, not incidental English prose."""
    usage = re.search(r'(?m)^Usage:\s*\n((?:[ \t]+[^\n]+\n?)+)', output)
    if not usage or not re.search(rf'(?m)^\s*{re.escape(command)}(?=\s|$)', usage[1]):
        raise AssertionError(f'Help did not identify command: {command}')
    declared = set()
    in_flags = False
    for line in output.splitlines():
        if line in ('Flags:', 'Global Flags:'):
            in_flags = True
        elif line and not line[0].isspace():
            in_flags = False
        elif in_flags:
            match = re.match(r'^\s+(?:(-\w),\s+)?(--[\w-]+)(?=\s|=|$)', line)
            if match:
                declared.update(flag for flag in match.groups() if flag)
    missing = set(flags) - declared
    if missing:
        raise AssertionError(f'{command}: missing declared flags: {", ".join(sorted(missing))}')


@unittest.skipUnless(BD, 'bd unavailable: CLI-help evidence skipped')
class CliHelpTests(unittest.TestCase):
    def test_documented_command_surface_without_database(self):
        commands = [
            ([], ['-C', '--directory', '--readonly', '--sandbox', '--json']),
            (['migrate'], ['--inspect', '--dry-run', '--json']),
            (['migrate', 'schema'], ['--json']),
            (['init'], ['--skip-hooks', '--skip-agents', '--non-interactive',
                        '--reinit-local', '--from-jsonl', '--discard-remote', '--destroy-token']),
            (['import'], ['--dry-run', '--allow-stale', '--json']),
            (['export'], ['--all', '--output']),
            (['list'], ['--all', '--limit', '--include-infra', '--include-templates',
                        '--include-gates', '--json']),
            (['backup'], []),
            (['bootstrap'], ['--dry-run', '--json', '--yes']),
            (['dolt', 'stop'], []),
            (['dolt', 'push'], []),
            (['migrate', 'hooks'], ['--dry-run', '--apply']),
            (['migrate', 'sync'], ['--dry-run']),
            (['doctor'], ['--migration', '--check']),
        ]
        with tempfile.TemporaryDirectory() as directory:
            home, cwd = Path(directory) / 'home', Path(directory) / 'cwd'
            home.mkdir()
            cwd.mkdir()
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(('BD_', 'BEADS_', 'GIT_', 'DOLT_'))}
            env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / 'config'))

            def run(arguments):
                result = subprocess.run([BD, *arguments], cwd=cwd, env=env,
                                        capture_output=True, text=True, timeout=15, check=False)
                self.assertEqual(0, result.returncode,
                                 f'bd {" ".join(arguments)} failed: {result.stderr[:2000]}')
                return result.stdout

            version = run(['--version']).strip()
            self.assertRegex(version, r'^bd version \S+')
            print(f'CLI help only: {version}; no database migration exercised', flush=True)
            for args, flags in commands:
                command = ' '.join(['bd', *args])
                with self.subTest(command=command):
                    check_help(run([*args, '--help']), command, flags)
            check_help(run(['help', 'init-safety']), 'bd init-safety', [])
            self.assertFalse((cwd / '.beads').exists(), 'help created a database directory')


if __name__ == '__main__':
    unittest.main()
