"""Loopback service lifecycle (§1).

Invariants: one user-wide lock regardless of data root; each thread owns its DB
connection; pause prevents claims, never scans; an unhandled worker failure is
process-fatal. No installed service is unloaded or migrated by this command.
"""
import fcntl
import logging
import os
import queue
import secrets
import shutil
import subprocess
import threading
import time
from concurrent.futures import Future
from contextlib import closing
from pathlib import Path

from . import config, intake, selfupdate, store, store_ops
from .executor import Executor

SUPPORT = Path.home() / 'Library/Application Support/QuietClerk'


def _recover_publication(con, publication):
    # Notes implementation is owned by D; defer loading until recovery needs it.
    from .notes import recover_publication
    return recover_publication(con, publication)


class ServiceLock:
    def __init__(self, path):
        self.path, self.file = Path(path), None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = self.path.open('a')
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            self.file = None
            raise RuntimeError('QuietClerk is already serving this user') from exc
        return self

    def close(self):
        if self.file:
            self.file.close()
            self.file = None


def legacy_registered(label):
    if not label or '/' in label or any(ord(c) < 32 for c in label):
        raise ValueError('invalid launchd label')
    try:
        return subprocess.run(['launchctl', 'print', f'gui/{os.getuid()}/{label}'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=10).returncode == 0
    except FileNotFoundError:
        return False


OPS_SOURCE = 'rec-pipeline'  # name kept so the existing board and rules keep matching


class Runtime:
    def __init__(self, settings=None, *, support=None, legacy_labels=('local.rec.pipeline',),
                 label_check=legacy_registered, executor_factory=Executor, scan=intake.scan,
                 fatal=os._exit, scan_interval=60, recover_publication=None, update_worker=None):
        self.settings = settings or config.load()
        self.support = Path(support) if support is not None else SUPPORT
        self.lock = ServiceLock(self.support / 'serve.lock')
        self.execution_lock = ServiceLock(self.settings.root / 'tick.lock')
        self.boot = secrets.token_hex(16)
        self.db = self.settings.root / 'state.sqlite3'
        self.legacy_labels, self.label_check = legacy_labels, label_check
        self.executor_factory, self.scan, self.fatal = executor_factory, scan, fatal
        self.scan_interval = scan_interval
        self.recover_publication = recover_publication or _recover_publication
        self.stopping, self.scan_requested, self.wake = threading.Event(), threading.Event(), threading.Event()
        self.threads = []
        self.failure = None
        self.auth = None
        self.settings_lock = threading.Lock()
        self.maintenance = queue.Queue()
        self.monitor_interval = 60
        self.updates = selfupdate.Updates(self, worker=update_worker)

    def start(self):
        self.lock.acquire()
        try:
            if any(self.label_check(label) for label in self.legacy_labels):
                raise RuntimeError('업그레이드 이행이 필요해요: legacy launchd service is registered')
            self.execution_lock.acquire()
            with closing(store.connect(self.db)) as con:
                store.recover(con, self.boot, recover_publication=self.recover_publication)
            self.updates.recover()
            for name, target in (('scheduler', self._scheduler), ('executor', self._executor),
                                 ('bootstrap', self._bootstrap), ('monitor', self._monitor)):
                thread = threading.Thread(target=self._guard, args=(target,), name=f'quietclerk-{name}', daemon=True)
                self.threads.append(thread)
                thread.start()
        except BaseException:
            self.close()
            raise

    def _guard(self, target):
        try:
            target()
        except BaseException as exc:
            self.failure = type(exc).__name__  # Never log request content or tokens.
            self.stopping.set()
            self.fatal(1)

    def _scheduler(self):
        with closing(store.connect(self.db)) as con:
            while not self.stopping.is_set():
                self.scan_requested.clear()
                self.scan(con, settings=self.settings)
                self.wake.set()
                self.updates.check(automatic=True)
                self.scan_requested.wait(self.scan_interval)

    def _executor(self):
        with closing(store.connect(self.db)) as con:
            executor = self.executor_factory(con, self.boot, self.settings)
            while not self.stopping.is_set():
                self.wake.clear()
                with self.updates.lock:
                    blocked = self.updates.before_job()
                    if not blocked:
                        self.updates.busy = True
                if blocked:
                    self.wake.wait(0.25)
                    continue
                try:
                    self._run_maintenance(con)
                    self._delete_pending(con)
                    executor.settings = self.settings
                    started = time.time()
                    result = executor.run_one(paused=store_ops.paused(con))
                finally:
                    with self.updates.lock:
                        self.updates.busy = False
                if result is None:
                    self.wake.wait(0.25)
                elif result['status'] == 'done':
                    self._ops('emit', 'job_done', '--source', OPS_SOURCE, '--message', result['source_name'])
                    self._ops('metric', 'job_minutes', f'{(time.time() - started) / 60:.1f}', '--unit', '분',
                              '--source', OPS_SOURCE)
                elif result['status'] == 'failed':
                    self._ops('emit', 'job_failed', '--kind', 'error', '--source', OPS_SOURCE,
                              '--message', f"{result['source_name']}: {(result['last_error'] or '')[:200]}")

    def _ops(self, *args):
        """Report to the operator's `ops` board when <root>/.ops exists (agent-ops); best effort."""
        board = self.settings.root / '.ops'
        exe = shutil.which('ops') or str(Path.home() / '.local/bin/ops')
        if not board.is_dir() or not Path(exe).is_file():
            return
        try:
            subprocess.run([exe, *args, '--dir', str(self.settings.root)], capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass

    def _monitor(self):
        with closing(store.connect(self.db)) as con:
            while not self.stopping.is_set():
                counts = store.counts(con)
                self._ops('heartbeat', '--source', OPS_SOURCE)
                self._ops('metric', 'queue', str(counts.get('queued', 0) + counts.get('retry_wait', 0)),
                          '--unit', '건', '--source', OPS_SOURCE)
                self._ops('metric', 'failed_final', str(counts.get('failed', 0)), '--unit', '건', '--source', OPS_SOURCE)
                self.stopping.wait(self.monitor_interval)

    def _bootstrap(self):
        while not self.stopping.is_set():
            if self.auth:
                self.auth.refresh()
            self.stopping.wait(0.25)

    def submit(self, task):
        """Run task(con) on the executor thread between jobs, under the execution lock
        this process holds (e.g. note migration). Returns a Future."""
        future = Future()
        self.maintenance.put((task, future))
        self.wake.set()
        return future

    def _run_maintenance(self, con):
        while True:
            try:
                task, future = self.maintenance.get_nowait()
            except queue.Empty:
                return
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(task(con))
                except Exception as exc:  # reported to the caller, not fatal to the service
                    future.set_exception(exc)

    def _delete_pending(self, con):
        """Delete only DB-authorized processing directories, never inbox or notes."""
        for row in store_ops.pending_deletions(con):
            if row['status'] == 'running':
                continue
            for base in ('archive', 'work'):
                root = self.settings.root / base
                path = root / row['job_id']
                if path.parent.resolve() != root.resolve() or path.is_symlink():
                    raise RuntimeError('unsafe processing directory')
                if path.exists():
                    shutil.rmtree(path)
            store_ops.finish_delete_local(con, row['job_id'])

    def request_scan(self):
        self.scan_requested.set()

    def close(self):
        self.stopping.set()
        self.scan_requested.set()
        self.wake.set()
        for thread in self.threads:
            thread.join()
        self.threads.clear()
        if self.auth:
            self.auth.close()
        self.execution_lock.close()
        self.lock.close()


def main(settings=None, **runtime_options):
    import uvicorn
    from .server import create_app
    runtime = Runtime(settings, **runtime_options)
    logs = Path(runtime.settings.get('root')) / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=logs / 'pipeline.log', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    uvicorn.run(create_app(runtime), host='127.0.0.1', port=runtime.settings.get('server.port'),
                access_log=False, log_level='warning')
