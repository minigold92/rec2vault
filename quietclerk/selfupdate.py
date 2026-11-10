"""Checkout-only self updates. Git sees source code, never recordings or settings.

The launchd-submitted worker is outside serve's process group. Durable results
are separate from installation identity, so a restored service reports failures.
"""
import argparse
import copy
import fcntl
import json
import os
import plistlib
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import install

INTERVAL = 86400
RESULTS = ('done', 'failed')
ACTIVE = ('scheduled', 'updating')


def stamp(now=None):
    return datetime.fromtimestamp(time.time() if now is None else now, timezone.utc).isoformat()


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path, value):
    install._atomic(path, json.dumps(value, ensure_ascii=False).encode())


def git(source, *args):
    return subprocess.run(['git', '-C', str(source), *args], check=True,
                          capture_output=True, text=True, timeout=30,
                          env=os.environ | {'GIT_TERMINAL_PROMPT': '0'}).stdout.strip()


def commit(source, revision='HEAD'):
    value = git(source, 'show', '-s', '--format=%h%x00%cI', revision).split('\0')
    return {'commit': value[0], 'date': value[1]}


def record_source(support, source):
    source = Path(source).resolve()
    installed = {'commit': '', 'date': None}
    kind = 'wheel_install' if source.suffix == '.whl' else 'no_checkout'
    if source.is_dir():
        try:
            if Path(git(source, 'rev-parse', '--show-toplevel')).resolve() == source:
                installed, kind = commit(source), None
        except (OSError, subprocess.SubprocessError, IndexError):
            pass
    write_json(Path(support) / 'source.json',
               {'source': str(source), 'reason': kind, 'installed': installed})


def clean(source):
    return not git(source, 'status', '--porcelain', '--untracked-files=normal')


def inspect(identity, now):
    result = {'state': 'unavailable', 'reason': identity.get('reason') or 'no_checkout',
              'installed': identity.get('installed', {'commit': '', 'date': None}),
              'latest': None, 'behind': 0, 'changes': [], 'checked_at': stamp(now),
              'finished_at': None, 'last_error': None}
    if identity.get('reason'):
        return result
    source = Path(identity.get('source', ''))
    try:
        if not source.is_dir() or Path(git(source, 'rev-parse', '--show-toplevel')).resolve() != source:
            return result
        if not clean(source):
            return result | {'reason': 'local_changes'}
        try:
            upstream = git(source, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}')
            remote = git(source, 'config', '--get', 'branch.' + git(source, 'branch', '--show-current') + '.remote')
            if remote == '.' or not remote:
                return result | {'reason': 'no_remote'}
        except subprocess.CalledProcessError:
            return result | {'reason': 'no_remote'}
        try:
            git(source, 'fetch', '--no-tags', '--', remote)
        except (OSError, subprocess.SubprocessError):
            return result | {'reason': 'offline', 'last_error': 'offline'}
        installed = result['installed']['commit']
        # A manual checkout move must not silently describe uninstalled code as current.
        if git(source, 'rev-parse', 'HEAD') != git(source, 'rev-parse', installed):
            return result | {'reason': 'diverged', 'latest': commit(source, upstream)}
        ahead, behind = map(int, git(source, 'rev-list', '--left-right', '--count', 'HEAD...' + upstream).split())
        result.update(latest=commit(source, upstream), behind=behind)
        if ahead:
            return result | {'reason': 'diverged'}
        changes = git(source, 'log', '-20', '--format=%h%x00%cI%x00%s', 'HEAD..' + upstream)
        for line in changes.splitlines():
            sha, date, title = line.split('\0', 2)
            title = re.sub(r'^[A-Za-z][\w-]*(?:\([^)]*\))?!?:\s*', '', title)
            result['changes'].append({'commit': sha, 'date': date, 'title': title})
        return result | {'state': 'available' if behind else 'current', 'reason': None}
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return result | {'reason': 'no_checkout'}


class LaunchdWorker:
    def start(self, runtime, identity, state):
        label = 'local.quietclerk.update.' + uuid.uuid4().hex
        logs = runtime.settings.root / 'logs'
        logs.mkdir(exist_ok=True)
        command = [sys.executable, '-I', '-m', 'quietclerk.selfupdate',
                   '--root', str(runtime.settings.root), '--support', str(runtime.support),
                   '--settings', str(runtime.settings.path), '--source', identity['source'],
                   '--previous', state['installed']['commit'], '--target', state['latest']['commit'],
                   '--label', label]
        job = runtime.support / (label + '.plist')
        install._atomic(job, plistlib.dumps({
            'Label': label, 'ProgramArguments': command, 'RunAtLoad': True, 'KeepAlive': False,
            'WorkingDirectory': str(runtime.settings.root), 'ProcessType': 'Background',
            'StandardOutPath': str(logs / 'update.out'), 'StandardErrorPath': str(logs / 'update.err'),
            'EnvironmentVariables': {'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
                                    'HF_HUB_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1',
                                    'HF_HUB_DISABLE_XET': '1'}}))
        write_json(runtime.support / 'update.json', state | {'worker_label': label})
        # submit creates a keepalive job, even after success. Bootstrap a genuine
        # one-shot instead, outside serve's process group and without app data.
        try:
            subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(job)],
                           check=True, capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            job.unlink(missing_ok=True)
            raise
        return label

    def remove(self, label):
        subprocess.run(['launchctl', 'remove', label], capture_output=True, timeout=30)


class Updates:
    def __init__(self, runtime, *, worker=None, clock=time.time):
        self.runtime, self.clock = runtime, clock
        self.path = runtime.support / 'update.json'
        self.worker = worker or LaunchdWorker()
        self.lock = threading.RLock()
        self.busy = False

    def identity(self):
        return read_json(self.runtime.support / 'source.json')

    def recover(self):
        """A held worker lock distinguishes a normal cutover from a killed job.

        One-shot plists live in support, not LaunchAgents, so reboot never loads
        them. The next serve removes any stale registration/file and reports an
        interrupted update without claiming that uninstalled source is running.
        """
        with self.lock, (self.runtime.support / 'selfupdate.lock').open('a') as guard:
            try:
                fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            state = read_json(self.path)
            labels = {path.stem for path in self.runtime.support.glob('local.quietclerk.update.*.plist')}
            if state.get('worker_label'):
                labels.add(state['worker_label'])
            for label in labels:
                if not re.fullmatch(r'local\.quietclerk\.update\.[0-9a-f]{32}', label):
                    continue
                self.worker.remove(label)
                (self.runtime.support / (label + '.plist')).unlink(missing_ok=True)
            if state.get('state') == 'updating':
                identity = self.identity()
                installed = identity.get('installed', state['installed'])
                reason = None
                try:
                    if git(identity['source'], 'rev-parse', 'HEAD') != git(identity['source'], 'rev-parse', installed['commit']):
                        reason = 'diverged'
                except (KeyError, OSError, subprocess.SubprocessError):
                    reason = 'no_checkout'
                state.update(state='failed', reason=reason, installed=installed,
                             failure='interrupted', finished_at=stamp(self.clock()),
                             last_error='interrupted')
                write_json(self.path, state)

    def snapshot(self):
        with self.lock:
            state = read_json(self.path)
            if not state:
                identity = self.identity()
                # Not checked yet: a usable checkout is assumed current until the first check
                # (checked_at stays null); only a real obstacle is reported as unavailable.
                obstacle = identity.get('reason') or (None if identity.get('source') else 'no_checkout')
                reason = obstacle or (None if self.runtime.settings.get('updates.check') else 'check_disabled')
                state = {'state': 'unavailable' if obstacle else 'current',
                         'reason': reason,
                         'installed': identity.get('installed', {'commit': '', 'date': None}),
                         'latest': None, 'behind': 0, 'changes': [], 'checked_at': None,
                         'finished_at': None, 'last_error': None}
            result = {key: copy.deepcopy(state[key]) for key in
                      ('state', 'reason', 'installed', 'latest', 'behind', 'changes',
                       'checked_at', 'finished_at', 'last_error')}
            if result['last_error']:
                result['last_error'] = message(result['last_error'],
                                               self.runtime.settings.get('ui.language'))
            return result

    def check(self, *, automatic=False):
        with self.lock:
            old = self.snapshot()
            if old['state'] in ACTIVE + RESULTS:
                return old
            if automatic:
                if not self.runtime.settings.get('updates.check'):
                    return old
                if old['checked_at'] and self.clock() - datetime.fromisoformat(old['checked_at']).timestamp() < INTERVAL:
                    return old
            state = inspect(self.identity(), self.clock())
            write_json(self.path, state)
            return state

    def apply(self, con):
        with self.lock:
            state = self.snapshot()
            if state['state'] != 'available':
                raise UpdateConflict(state['reason'])
            running = self.busy or con.execute("SELECT 1 FROM jobs WHERE status='running' LIMIT 1").fetchone()
            state.update(state='scheduled' if running else 'updating', reason='job_running' if running else None)
            write_json(self.path, state)
            accepted = state['state']
            if not running:
                self._start(state)
            self.runtime.wake.set()
            return {'state': accepted}

    def _start(self, state):
        state.update(state='updating', reason=None)
        write_json(self.path, state)
        try:
            if self.runtime.auth:
                self.runtime.auth.preserve_for_update()
            self.worker.start(self.runtime, self.identity(), state)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            state.update(state='failed', finished_at=stamp(self.clock()),
                         last_error='start_failed')
            write_json(self.path, state)

    def before_job(self):
        """Called under lock before claiming: pending update wins over new work."""
        state = self.snapshot()
        if state['state'] == 'scheduled':
            self._start(state)
        return state['state'] in ACTIVE

    def dismiss(self):
        with self.lock:
            state = read_json(self.path)
            if state.get('state') in RESULTS:
                state.update(state='current' if state.get('state') == 'done' else (
                             'available' if state.get('reason') is None and state.get('behind') else 'unavailable'),
                             finished_at=None, last_error=None)
                if state['state'] == 'current':
                    state.update(changes=[], latest=state['installed'])
                write_json(self.path, state)
            return self.snapshot()


# last_error is stored as a code and worded in the screen language when read.
MESSAGES = {
    'offline': ('업데이트 서버에 연결하지 못했어요. 잠시 후 다시 확인해 주세요.',
                'Could not reach the update server. Try again later.'),
    'interrupted': ('업데이트가 중단됐어요. 다시 확인해 주세요.',
                    'The update was interrupted. Check again.'),
    'start_failed': ('업데이트를 시작하지 못했어요. 다시 확인해 주세요.',
                     'The update could not start. Check again.'),
    'rolled_back': ('업데이트하지 못해 이전 버전으로 돌아왔어요.',
                    'The update failed, so the previous version was restored.'),
    'checkout_mismatch': ('업데이트에 실패했어요. 소스 체크아웃이 실행 중 버전과 달라 수동 확인이 필요해요.',
                          'The update failed and the source checkout no longer matches the running version; check it by hand.'),
    'not_available': ('지금은 업데이트할 수 없어요. 먼저 업데이트를 확인해 주세요.',
                      'No update can be applied now. Check for updates first.'),
}


def message(code, language):
    if code not in MESSAGES:
        return code
    return MESSAGES[code][1 if language == 'en' else 0]


class UpdateConflict(RuntimeError):
    def __init__(self, reason):
        self.reason = reason


def run_worker(*, root, support, settings, source, previous, target, updater=None, **locations):
    """Installed old interpreter runs this even when the fetched source is broken."""
    root, support, source = Path(root), Path(support), Path(source)
    path = support / 'update.json'
    state = read_json(path)
    moved = False
    pulled_head = None
    try:
        with install._lock(support / 'selfupdate.lock'):
            if not clean(source) or git(source, 'rev-parse', 'HEAD') != git(source, 'rev-parse', previous):
                raise RuntimeError('checkout changed')
            # Fetch/check occurred at consent time. Do not install a newer, unseen tip.
            git(source, 'pull', '--ff-only')
            moved = True
            pulled_head = git(source, 'rev-parse', 'HEAD')
            if pulled_head != git(source, 'rev-parse', target):
                raise RuntimeError('upstream changed since consent')
            (updater or install.update)(root=root, support=support, settings=settings, source=source, **locations)
            state.update(state='done', installed=commit(source), behind=0, reason=None,
                         previous_commit=previous, applied_commit=target, last_error=None)
    except Exception:
        try:
            restored = not moved and git(source, 'rev-parse', 'HEAD') == git(source, 'rev-parse', previous)
        except (OSError, subprocess.SubprocessError):
            restored = False
        if moved:
            try:
                # Never destroy edits made by a person during installation.
                if clean(source) and git(source, 'rev-parse', 'HEAD') == pulled_head:
                    git(source, 'reset', '--hard', previous)
                    restored = True
            except (OSError, subprocess.SubprocessError):
                pass
        state.update(state='failed', reason=None if restored else 'diverged',
                     previous_commit=previous, applied_commit=target,
                     last_error=('rolled_back' if restored else
                                 'checkout_mismatch'))
    state['finished_at'] = stamp()
    write_json(path, state)
    return state


def main():
    parser = argparse.ArgumentParser()
    for name in ('root', 'support', 'settings', 'source', 'previous', 'target'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--label')
    args = vars(parser.parse_args())
    label = args.pop('label')
    run_worker(**args)
    if label and re.fullmatch(r'local\.quietclerk\.update\.[0-9a-f]{32}', label):
        (Path(args['support']) / (label + '.plist')).unlink(missing_ok=True)
        # The result is durable before removing our own one-shot registration.
        subprocess.run(['launchctl', 'remove', label], capture_output=True, timeout=30)


if __name__ == '__main__':
    main()
