#!/usr/bin/env python3
"""Opt-in, local, agent-reported counters. Never reads transcripts or sends data."""

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import stat
import sys
import time

WATCHERS = ('watch-prs', 'watch-release', 'watch-pr-feedback', 'watch-review-requests',
            'watch-rollout', 'watch-actions-rollout', 'watch-flux-rollout')
HARNESSES = ('pi', 'claude')
EVENTS = ('invocation', 'tick')
KEYS = {f'{watcher}:{harness}:{event}' for watcher in WATCHERS for harness in HARNESSES
        for event in EVENTS if watcher != 'watch-rollout' or event != 'tick'}
MAX_BYTES = 256 * 1024
MAX_COUNT = 2 ** 53 - 1
RETENTION_DAYS = 90
LOCK_SECONDS = 2


class Unavailable(Exception):
    pass


class MissingStore(Exception):
    pass


def parse_day(value):
    if not isinstance(value, str) or len(value) != 10:
        raise Unavailable('invalid_store')
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise Unavailable('invalid_store')
    return parsed


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Unavailable('invalid_store')
        result[key] = value
    return result


def validate(data, today):
    if not isinstance(data, dict) or set(data) != {'version', 'enabled', 'policy_day', 'days'}:
        raise Unavailable('invalid_store')
    if type(data['version']) is not int or data['version'] != 1 or type(data['enabled']) is not bool:
        raise Unavailable('invalid_store')
    policy_day = parse_day(data['policy_day'])
    if policy_day > today:
        raise Unavailable('clock_backward')
    days = data['days']
    if not isinstance(days, dict) or not 1 <= len(days) <= RETENTION_DAYS or data['policy_day'] not in days:
        raise Unavailable('invalid_store')
    for day, row in days.items():
        if not policy_day - timedelta(days=89) <= parse_day(day) <= policy_day:
            raise Unavailable('invalid_store')
        if not isinstance(row, dict) or set(row) != {'enabled', 'disabled', 'counts'}:
            raise Unavailable('invalid_store')
        if any(type(row[key]) is not bool for key in ('enabled', 'disabled')):
            raise Unavailable('invalid_store')
        if not (row['enabled'] or row['disabled']):
            raise Unavailable('invalid_store')
        counts = row['counts']
        if not isinstance(counts, dict) or not set(counts) <= KEYS or (counts and not row['enabled']):
            raise Unavailable('invalid_store')
        if any(type(n) is not int or not 0 <= n <= MAX_COUNT for n in counts.values()):
            raise Unavailable('invalid_store')
    return data


def check_directory(fd, private=False):
    info = os.fstat(fd)
    if private:
        valid = info.st_uid == os.geteuid() and not info.st_mode & 0o077
    else:
        sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
        valid = info.st_uid in (0, os.geteuid()) and (not info.st_mode & 0o022 or sticky_root)
    if not valid:
        raise Unavailable('unsafe_storage')


@contextmanager
def open_directory(root, create):
    if not root.is_absolute() or '..' in root.parts or root == Path('/'):
        raise Unavailable('unsafe_storage')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open('/', flags)
    try:
        for component in root.parts[1:]:
            check_directory(fd)
            try:
                child = os.open(component, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise MissingStore from None
                try:
                    os.mkdir(component, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        check_directory(fd, private=True)
        yield fd
    finally:
        os.close(fd)


def check_file(fd):
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077 or info.st_nlink != 1):
        raise Unavailable('unsafe_storage')


@contextmanager
def locked(directory, create=False):
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_CREAT if create else 0)
    try:
        fd = os.open('.lock', flags, 0o600, dir_fd=directory)
    except FileNotFoundError:
        raise Unavailable('missing_lock') from None
    try:
        check_file(fd)
        deadline = time.monotonic() + LOCK_SECONDS
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise Unavailable('locked') from None
                time.sleep(0.02)
        yield
    finally:
        os.close(fd)


def load(directory, today):
    try:
        fd = os.open('counts.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as stream:
        check_file(stream.fileno())
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise Unavailable('oversized_store')
    return validate(json.loads(raw, object_pairs_hook=unique_keys), today)


def advance(data, today):
    cutoff = today - timedelta(days=RETENTION_DAYS - 1)
    data['days'] = {key: value for key, value in data['days'].items() if parse_day(key) >= cutoff}
    current = max(parse_day(data['policy_day']), cutoff)
    while current <= today:
        row = data['days'].setdefault(current.isoformat(), {'enabled': False, 'disabled': False, 'counts': {}})
        row['enabled' if data['enabled'] else 'disabled'] = True
        current += timedelta(days=1)
    data['policy_day'] = today.isoformat()


def handle_pending(directory, prune=False):
    try:
        fd = os.open('.counts.tmp', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        return
    try:
        check_file(fd)
        if not prune:
            raise Unavailable('pending_write')
        os.unlink('.counts.tmp', dir_fd=directory)
    finally:
        os.close(fd)


def exists(directory, name):
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def save(directory, data):
    raw = (json.dumps(data, sort_keys=True, separators=(',', ':')) + '\n').encode()
    if len(raw) > MAX_BYTES:
        raise Unavailable('oversized_store')
    name = '.counts.tmp'
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, 'counts.json', src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(name, dir_fd=directory)
        except FileNotFoundError:
            pass


def report(data, today, days):
    start = today - timedelta(days=days - 1)
    settings = {'enabled': 0, 'disabled': 0, 'mixed': 0, 'unknown': 0}
    rows = []
    if data is not None:
        selected = {key: value for key, value in data['days'].items() if parse_day(key) >= start}
        for row in selected.values():
            category = 'mixed' if row['enabled'] and row['disabled'] else 'enabled' if row['enabled'] else 'disabled'
            settings[category] += 1
        for watcher in WATCHERS:
            for harness in HARNESSES:
                row = {'watcher': watcher, 'harness': harness}
                for event, field in (('invocation', 'invocations'), ('tick', 'ticks')):
                    row[field] = (sum(item['counts'].get(f'{watcher}:{harness}:{event}', 0)
                                      for item in selected.values())
                                  if watcher != 'watch-rollout' or event != 'tick' else None)
                rows.append(row)
    settings['unknown'] = days - sum(settings.values())
    return {'schema': 'watch-telemetry/v1', 'source': 'agent-reported',
            'status': 'enabled' if data and data['enabled'] else 'disabled',
            'coverage': 'partial' if data is not None else 'unavailable',
            'window': {'start': start.isoformat(), 'end_exclusive': (today + timedelta(days=1)).isoformat()},
            'settings_days': settings, 'rows': rows}


def operate(root, action, today, *, watcher=None, harness=None, event=None, days=90):
    key = f'{watcher}:{harness}:{event}'
    if action not in ('record', 'counts', 'enable', 'disable', 'prune'):
        raise ValueError('invalid arguments')
    if type(days) is not int or not 1 <= days <= RETENTION_DAYS or (action == 'record' and key not in KEYS):
        raise ValueError('invalid arguments')
    try:
        with open_directory(root, create=action == 'enable') as directory:
            has_state = any(exists(directory, name) for name in ('counts.json', '.counts.tmp'))
            if action != 'enable' and not has_state:
                return report(None, today, days)
            with locked(directory, create=action == 'enable' and not has_state):
                handle_pending(directory, prune=action == 'prune')
                data = load(directory, today)
                if data is None:
                    if action != 'enable':
                        return report(None, today, days)
                    data = {'version': 1, 'enabled': True, 'policy_day': today.isoformat(), 'days': {}}
                if action == 'record' and not data['enabled']:
                    return None
                advance(data, today)
                if action in ('enable', 'disable'):
                    data['enabled'] = action == 'enable'
                    data['days'][today.isoformat()]['enabled' if data['enabled'] else 'disabled'] = True
                elif action == 'record':
                    counts = data['days'][today.isoformat()]['counts']
                    if counts.get(key, 0) == MAX_COUNT:
                        raise Unavailable('counter_limit')
                    counts[key] = counts.get(key, 0) + 1
                if action != 'counts':
                    save(directory, data)
                return report(data, today, days)
    except MissingStore:
        return report(None, today, days)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'watch-telemetry: invalid arguments (use --help)\n')


def main(argv=None):
    parser = Parser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    record = actions.add_parser('record')
    record.add_argument('watcher', choices=WATCHERS)
    record.add_argument('harness', choices=HARNESSES)
    record.add_argument('event', choices=EVENTS)
    counts = actions.add_parser('counts')
    counts.add_argument('--days', type=int, default=90)
    for action in ('enable', 'disable', 'prune'):
        actions.add_parser(action)
    args = parser.parse_args(argv)
    values = vars(args).copy()
    action = values.pop('action')
    if not 1 <= values.get('days', 90) <= 90 or (action == 'record' and f'{args.watcher}:{args.harness}:{args.event}' not in KEYS):
        parser.error('invalid arguments')
    try:
        base = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state')
        result = operate(base / 'agent-skills/watch-telemetry', action,
                         datetime.now(timezone.utc).date(), **values)
    except (OSError, ValueError, Unavailable, RecursionError, OverflowError) as error:
        if action == 'record':
            return 0
        code = str(error) if isinstance(error, Unavailable) else 'storage_io' if isinstance(error, OSError) else 'invalid_store'
        print(json.dumps({'status': 'unavailable', 'coverage': 'unavailable', 'error': code, 'rows': []}))
        return 1
    if action != 'record':
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
