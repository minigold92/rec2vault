"""Installation and reversible in-place upgrades (contracts §3.3 and §10.2).

Invariants: never merge roots, never run old and new engines together, and keep
legacy plists until the new service answers authenticated status. A failed step
restores exact DB/config bytes (including WAL), then re-registers stopped agents.
Held locks, surviving legacy children, unknown settings/schema and failed startup
are hard failures, not reasons to continue. Notes are never migrated here.

Platform operations are isolated in MacAdapter; tests must supply a fake adapter
and temporary home/LaunchAgents directories. Importing this module is read-only.
"""
import fcntl
import hashlib
import json
import os
import platform
import plistlib
import re
import shlex
import shutil
import sys
import sqlite3
import subprocess
import tempfile
import time
import tomllib
import urllib.request
import uuid
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from xml.sax.saxutils import escape
from xml.parsers.expat import ExpatError

LABEL = 'local.quietclerk.serve'
LEGACY_LABEL = 'local.rec.pipeline'
STOP_WAIT_SEC = 60  # serve finishes or interrupts its current stage on SIGTERM
SUPPORT = Path.home() / 'Library/Application Support/QuietClerk'
LEGACY_KEYS = {'REC_ROOT': 'root', 'REC_INBOX': 'inbox', 'REC_OUTPUT': 'output',
               'REC_SINCE': 'since', 'REC_MIN_DURATION_SEC': 'min_duration_sec',
               'REC_STABLE_SEC': 'stable_sec', 'REC_LANGUAGE': 'language.mode',
               'REC_LOCAL_ONLY': 'providers.local_only', 'REC_PORT': 'server.port',
               'REC_CODEX_EFFORT': 'providers.codex.effort'}


class InstallError(RuntimeError):
    pass


def _label(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', value):
        raise InstallError(f'invalid launchd label: {value!r}')
    return value


def _atomic(path, content, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def _lock(path, wait=0.0):
    """wait > 0: a just-stopped service may still be exiting (launchctl bootout returns
    before the process releases its locks), so poll up to `wait` seconds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait
    with path.open('a') as stream:
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise InstallError(f'lock is held; stop the existing execution: {path}') from exc
                time.sleep(0.2)
        yield


class MacAdapter:
    """All launchctl, environment creation, model and machine probes live here."""
    def __init__(self):
        self.domain = f'gui/{os.getuid()}'

    def command(self, argv, **kwargs):
        try:
            return subprocess.run(argv, check=True, text=True, capture_output=True, **kwargs).stdout
        except subprocess.CalledProcessError as exc:
            raise InstallError(f'{argv[0]} failed: {exc.stderr.strip() or exc}') from exc

    def registered(self, label):
        result = subprocess.run(['launchctl', 'print', f'{self.domain}/{_label(label)}'],
                                text=True, capture_output=True)
        if result.returncode and 'Could not find service' not in result.stderr:
            raise InstallError(result.stderr.strip() or 'launchctl print failed')
        return result.returncode == 0

    def unload(self, label):
        if self.registered(label):
            self.command(['launchctl', 'bootout', f'{self.domain}/{_label(label)}'])

    def register(self, plist):
        self.command(['launchctl', 'bootstrap', self.domain, str(plist)])

    def start(self, label):
        self.command(['launchctl', 'kickstart', f'{self.domain}/{_label(label)}'])

    def processes(self, root):
        rows = []
        for line in self.command(['ps', '-axo', 'pid=,ppid=,uid=,command=']).splitlines():
            fields = line.split(None, 3)
            if len(fields) == 4:
                pid, parent, uid, command = fields
                if int(uid) == os.getuid():
                    rows.append((int(pid), int(parent), command))
        # An installer launched from root/app is not an old model child.
        excluded = {os.getpid()}
        while True:
            parents = {parent for pid, parent, _ in rows if pid in excluded}
            if parents <= excluded:
                break
            excluded |= parents
        legacy = {pid for pid, _, command in rows if pid not in excluded and (
                  any(token in command for token in ('-m rec.tick', '-m quietclerk.tick',
                                                       '-m rec.worker', '-m quietclerk.worker')) or
                  (str(root / 'app') in command and 'python' in command))}
        while True:
            children = {pid for pid, parent, _ in rows if parent in legacy}
            if children <= legacy:
                return legacy
            legacy |= children

    def surviving(self, pids):
        alive = set()
        for pid in pids:
            try:
                os.kill(pid, 0)
                alive.add(pid)
            except ProcessLookupError:
                pass
        return alive

    def prepare_environment(self, source, venv):
        if platform.system() != 'Darwin' or platform.machine() != 'arm64':
            raise InstallError('MLX requires an Apple Silicon Mac')
        for binary in ('uv', 'ffmpeg'):
            if shutil.which(binary) is None:
                raise InstallError(f'missing executable: {binary}')
        self.command(['uv', 'venv', '--python', '3.12', str(venv)])
        # Install the project itself, not just its dependencies. A wheel install
        # supplies --source /path/to/quietclerk.whl instead of a checkout.
        self.command(['uv', 'pip', 'install', '--python', str(venv / 'bin/python'),
                      str(source)])
        self.command([str(venv / 'bin/python'), '-I', '-c',
                      'import mlx.core, starlette, uvicorn, yaml, jinja2; import quietclerk.cli'])

    def check_models(self, venv, source):
        self.command([str(venv / 'bin/python'), '-I', '-m', 'quietclerk.models', 'prefetch'])
        self.command([str(venv / 'bin/python'), '-I', '-c',
                      'from quietclerk.backends.mlx import MODELS, model_snapshot; '
                      '[model_snapshot(repo) for repo in MODELS.values()]'])

    def healthy(self, label, support, settings, started):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                bootstrap = support / 'bootstrap.json'
                if bootstrap.stat().st_mtime_ns < started:
                    raise ValueError('waiting for a fresh bootstrap')
                from .bootstrap_file import read_bootstrap
                data = read_bootstrap(support)
                if data['port'] != settings.get('server.port') or not self.registered(label):
                    raise ValueError('service port or registration mismatch')
                base = f"http://127.0.0.1:{data['port']}"
                request = urllib.request.Request(base + '/api/session',
                    data=json.dumps({'token': data['token']}).encode(),
                    headers={'Content-Type': 'application/json', 'Origin': base})
                with urllib.request.urlopen(request, timeout=2) as response:
                    cookie = response.headers['Set-Cookie'].split(';', 1)[0]
                    csrf = response.headers['X-CSRF-Token']
                try:
                    request = urllib.request.Request(base + '/api/status', headers={'Cookie': cookie})
                    with urllib.request.urlopen(request, timeout=2) as response:
                        json.load(response)
                    return True
                finally:
                    request = urllib.request.Request(base + '/api/logout', data=b'{}', headers={
                        'Cookie': cookie, 'Origin': base, 'X-CSRF-Token': csrf,
                        'Content-Type': 'application/json'})
                    with urllib.request.urlopen(request, timeout=2):
                        pass
            except (OSError, ValueError, KeyError):
                time.sleep(.2)
        return False

    def machine_info(self, root):
        def probe(argv):
            try:
                return self.command(argv).strip()
            except (OSError, RuntimeError, subprocess.SubprocessError):
                return 'unavailable'
        existing = root
        while not existing.exists():
            existing = existing.parent
        memory = probe(['sysctl', '-n', 'hw.memsize'])
        return {'chip': probe(['sysctl', '-n', 'machdep.cpu.brand_string']),
                'architecture': platform.machine(),
                'memory': f'{int(memory) / (1 << 30):.1f} GiB' if memory.isdigit() else memory,
                'disk_free': f'{shutil.disk_usage(existing).free / (1 << 30):.1f} GiB',
                'ffmpeg': shutil.which('ffmpeg') or 'missing',
                'uv': shutil.which('uv') or 'missing'}


APP_RECORD = 'engine-installation.json'


def read_app_installation(path):
    """Private app ownership record, not an alternative engine configuration."""
    import stat
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
            info = os.fstat(stream.fileno())
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or not stat.S_ISREG(info.st_mode):
                raise ValueError('record must be an owned regular file with mode 0600')
            record = json.load(stream)
        if (record.get('schema') != 1 or record.get('manager') != 'app' or record.get('label') != LABEL or
                not all(isinstance(record.get(key), str) and Path(record[key]).is_absolute()
                        for key in ('python', 'settings', 'support', 'root', 'plist'))):
            raise ValueError('invalid app installation record')
        return record
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise InstallError(f'invalid app installation record: {exc}') from exc


def _record_app_service(paths, plist, venv):
    content = Path(plist).read_bytes()
    record = {'schema': 1, 'manager': 'app', 'label': LABEL,
              'python': str(venv / 'bin/python'), 'root': str(paths.root),
              'settings': str(paths.settings), 'support': str(paths.support),
              'plist': str(plist), 'plist_sha256': hashlib.sha256(content).hexdigest()}
    _atomic(paths.support / 'service.plist', content)
    _atomic(paths.support / APP_RECORD, json.dumps(record).encode())


@dataclass(frozen=True)
class Layout:
    root: Path
    home: Path
    source: Path
    agents: Path
    support: Path
    settings: Path


def layout(root=None, *, home=None, source=None, agents=None, support=None, settings=None,
           upgrading=False, updating=False):
    home = Path(home or Path.home()).expanduser().resolve()
    old, new = home / 'rec', home / 'QuietClerk'
    if old.exists() and new.exists() and old.resolve() != new.resolve():
        raise InstallError(f'root conflict: both {old} and {new} exist; no automatic merge')
    chosen = Path(root).expanduser().resolve() if root is not None else (
        old if (upgrading or updating) and old.exists() else new)
    if root is not None and any(p.exists() and p.resolve() != chosen for p in (old, new)):
        raise InstallError('root conflict: another default data root already exists')
    if upgrading and not (chosen / 'state.sqlite3').is_file():
        raise InstallError(f'no existing database in {chosen}')
    if not (upgrading or updating) and any((chosen / name).exists() for name in
                             ('state.sqlite3', 'settings.toml', 'settings.env')):
        raise InstallError('existing installation: use quietclerk upgrade')
    source = Path(source or Path(__file__).resolve().parent.parent).expanduser().resolve()
    if not ((source.is_dir() and (source / 'pyproject.toml').is_file()) or
            (source.is_file() and source.suffix == '.whl')):
        raise InstallError('provide --source /path/to/quietclerk.whl or a source checkout')
    return Layout(chosen, home, source,
                  Path(agents or home / 'Library/LaunchAgents'),
                  Path(support or home / 'Library/Application Support/QuietClerk'),
                  Path(settings or chosen / 'settings.toml'))


def legacy_services(paths, labels=(), environ=None):
    env = os.environ if environ is None else environ
    names = {LEGACY_LABEL, *labels}
    if env.get('REC_LABEL'):
        names.add(env['REC_LABEL'])
    legacy_file = paths.root / 'settings.env'
    if legacy_file.exists():
        for line in legacy_file.read_text().splitlines():
            match = re.match(r'^\s*(?:export\s+)?REC_LABEL\s*=(.*)$', line)
            if match:
                parts = shlex.split(match[1], comments=True)
                if len(parts) != 1:
                    raise InstallError('invalid REC_LABEL in settings.env')
                names.add(parts[0])
    for path in paths.agents.glob('*.plist'):
        try:
            data = plistlib.loads(path.read_bytes())
        except (OSError, plistlib.InvalidFileException, ValueError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get('ProgramArguments', []), list):
            continue
        arguments = data.get('ProgramArguments', [])
        if any(module in arguments for module in ('rec.tick', 'quietclerk.tick')):
            names.add(data['Label'])
    return tuple(sorted(_label(name) for name in names))


def _legacy_values(path, env):
    values = {}
    if path.exists():
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if stripped.startswith('export '):
                stripped = stripped[7:]
            key, sep, text = stripped.partition('=')
            key = key.strip()
            if not sep or not re.fullmatch(r'REC_[A-Z_]+', key):
                raise InstallError(f'unsupported settings.env line {number}')
            # Parse shell quoting, never evaluate substitutions or execute a file.
            try:
                pieces = shlex.split(text, comments=True)
            except ValueError as exc:
                raise InstallError(f'invalid settings.env line {number}') from exc
            value = ' '.join(pieces)
            if '$(' in value or '`' in value or '${' in value:
                raise InstallError(f'nonliteral settings.env line {number}')
            values[key] = value
    values.update({key: value for key, value in env.items() if key.startswith('REC_')})
    unknown = values.keys() - LEGACY_KEYS.keys() - {'REC_LABEL'}
    if unknown:
        raise InstallError('unsupported legacy settings: ' + ', '.join(sorted(unknown)))
    return values


def migrate_settings(paths, env):
    # config has module-level constants. Its first import must initialize
    # the adopted root, not accidentally create a second ~/QuietClerk root.
    if 'quietclerk.config' not in sys.modules:
        saved = {key: value for key, value in os.environ.items() if key.startswith('QC_')}
        try:
            for key in saved:
                del os.environ[key]
            os.environ.update(QC_ROOT=str(paths.root), QC_SETTINGS=str(paths.settings))
            from . import config
        finally:
            for key in list(os.environ):
                if key.startswith('QC_'):
                    del os.environ[key]
            os.environ.update(saved)
    else:
        from . import config
    legacy = _legacy_values(paths.root / 'settings.env', env)
    values = config._flatten(tomllib.loads(paths.settings.read_text())) if paths.settings.exists() else {}
    for old, key in LEGACY_KEYS.items():
        if old not in legacy:
            continue
        value = legacy[old]
        if key in ('min_duration_sec', 'stable_sec', 'server.port'):
            value = int(value)
        elif key == 'providers.local_only':
            if value.lower() not in ('true', 'false', '1', '0'):
                raise InstallError(f'invalid boolean {old}')
            value = value.lower() in ('true', '1')
        values[key] = config._validate(key, value)
    if 'root' in values and Path(values['root']).expanduser().resolve() != paths.root:
        raise InstallError('configured root differs from adopted root; root moves are not upgrades')
    values['root'] = str(paths.root)
    if (paths.root / 'settings.env').exists():
        # v1 only ever processed Korean and wrote Korean notes; keep that behaviour
        # instead of inheriting a machine locale that may be English.
        values.setdefault('language.default', 'ko')
        values.setdefault('ui.language', 'ko')
    # Defaults are persisted once; QC overrides remain runtime-only, not baked in.
    defaults = config.load(paths.settings, environ={'QC_ROOT': str(paths.root)})
    for key in ('since', 'server.port', 'language.default', 'ui.language'):
        values.setdefault(key, defaults.get(key))
    def toml(value):
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        if type(value) is bool:
            return 'true' if value else 'false'
        if type(value) is int:
            return str(value)
        if isinstance(value, list):
            return '[' + ', '.join(toml(item) for item in value) + ']'
        return '{' + ', '.join(json.dumps(k) + ' = ' + toml(v) for k, v in value.items()) + '}'
    content = ''.join(json.dumps(key) + ' = ' + toml(value) + '\n' for key, value in values.items())
    temporary = paths.settings.with_name(paths.settings.name + '.part')
    try:
        _atomic(temporary, content.encode())
        validated = config.load(temporary, environ={'QC_ROOT': str(paths.root)})
        os.replace(temporary, paths.settings)
    finally:
        temporary.unlink(missing_ok=True)
    old = paths.root / 'settings.env'
    if old.exists():
        if old.with_suffix('.env.migrated').exists():
            raise InstallError('settings.env.migrated already exists')
        old.rename(old.with_suffix('.env.migrated'))
    return validated


def service_plist(paths, venv, legacy_labels, *, app_install=False):
    resource = files('quietclerk').joinpath('deploy/launchd.plist.in')
    template = (resource.read_text(encoding='utf-8') if resource.is_file() else
                (Path(__file__).resolve().parent.parent / 'deploy/launchd.plist.in').read_text(encoding='utf-8'))
    values = {'LABEL': LABEL, 'PYTHON': venv / 'bin/python',
              'SETTINGS': paths.settings, 'SUPPORT': paths.support,
              'SOURCE': paths.root, 'ROOT': paths.root, 'HOME': paths.home}
    template = re.sub(r'@(LABEL|PYTHON|SETTINGS|SUPPORT|SOURCE|ROOT|HOME)@',
                      lambda match: escape(str(values[match[1]])), template)
    data = plistlib.loads(template.encode())
    for name in legacy_labels:
        data['ProgramArguments'] += ['--legacy-label', name]
    if app_install:
        data['AssociatedBundleIdentifiers'] = ['io.github.minigold92.quietclerk']
        for binary in ('uv', 'ffmpeg', 'ffprobe'):
            if (venv / 'bin' / binary).is_file():
                data['EnvironmentVariables']['QC_' + binary.upper()] = str(venv / 'bin' / binary)
    return plistlib.dumps(data)


def link_cli(paths, venv):
    """Publish only our managed symlink; never replace an unrelated command."""
    link = paths.home / '.local/bin/quietclerk'
    target = venv / 'bin/quietclerk'
    temporary = link.with_name('.quietclerk-' + uuid.uuid4().hex)
    try:
        if link.is_symlink():
            old = link.resolve()
            if (old.name != 'quietclerk' or old.parent.name != 'bin' or
                    old.parent.parent.parent != paths.root / '.venvs' or
                    not re.fullmatch(r'[0-9a-f]{32}', old.parent.parent.name)):
                return f'CLI not linked: {link} belongs to another program; left unchanged.'
        elif link.exists():
            return f'CLI not linked: {link} already exists; left unchanged.'
        if any(parent.is_symlink() for parent in (link.parent, link.parent.parent)):
            return f'CLI not linked: {link.parent} is a symlink; left unchanged.'
        link.parent.mkdir(parents=True, exist_ok=True)
        temporary.symlink_to(target)
        os.replace(temporary, link)
        return f'CLI linked: {link} -> {target}. Add ~/.local/bin to PATH if needed.'
    except OSError as exc:
        return f'CLI not linked: {link}: {exc}. Service is still healthy.'
    finally:
        temporary.unlink(missing_ok=True)


class Snapshot:
    """Byte-for-byte rollback, including files absent before the transaction."""
    def __init__(self, paths):
        self.files = {path: (path.read_bytes(), path.stat().st_mode & 0o777) if path.exists()
                      else None for path in paths}

    def restore(self):
        for path, saved in self.files.items():
            if saved is None:
                path.unlink(missing_ok=True)
            else:
                _atomic(path, *saved)


def run(*, upgrading=False, root=None, dry_run=False, adapter=None, legacy_labels=(),
        environ=None, fault=None, app_install=False, **locations):
    """Perform one upgrade/install. fault(stage) is for deterministic failure tests."""
    paths = layout(root, upgrading=upgrading, **locations)
    env = dict(os.environ if environ is None else environ)
    labels = legacy_services(paths, legacy_labels, env)
    plan = [f'Adopt existing root: {paths.root}' if upgrading else f'Create root: {paths.root}',
            'Unload legacy labels: ' + ', '.join(labels),
            'Acquire tick.lock; reject surviving legacy children',
            'Create a fresh venv; install dependencies; verify models',
            f'Migrate settings to {paths.settings}',
            'Migrate state.sqlite3 with migrate_v1' if upgrading else 'Initialize schema v2',
            f'Register/start {LABEL}; verify authenticated status',
            'On failure: stop new service; restore DB/config; re-register old services',
            'Keep legacy service files and notes unchanged']
    if dry_run:
        return '\n'.join(plan)
    adapter = adapter or MacAdapter()
    paths.root.mkdir(parents=True, exist_ok=True)
    venv = paths.root / '.venvs' / uuid.uuid4().hex
    stopped = []
    new_attempted = False
    snapshot = None
    def point(name):
        if fault:
            fault(name)
    with ExitStack() as locks:
        service_guard = locks.enter_context(ExitStack())
        execution_guard = locks.enter_context(ExitStack())
        locks.enter_context(_lock(paths.support / 'upgrade.lock'))
        if adapter.registered(LABEL):
            raise InstallError('new service is already registered; stop it before upgrading')
        try:
            active = [(name, paths.agents / (name + '.plist')) for name in labels if adapter.registered(name)]
            if any(not plist.is_file() for _, plist in active):
                raise InstallError('registered legacy service has no restorable plist')
            for name, plist in active:
                if plistlib.loads(plist.read_bytes()).get('Label') != name:
                    raise InstallError(f'legacy plist label mismatch: {plist}')
            pids = adapter.processes(paths.root)
            for name, plist in active:
                # Include a possibly partially completed unload in rollback.
                stopped.append((name, plist))
                adapter.unload(name)
            point('unloaded')
            execution_guard.enter_context(_lock(paths.root / 'tick.lock'))
            point('locked')
            if adapter.surviving(pids) or adapter.processes(paths.root):
                raise InstallError('legacy child processes still exist')
            point('children_checked')
            service_guard.enter_context(_lock(paths.support / 'serve.lock'))
            database = paths.root / 'state.sqlite3'
            tracked = [database, *(database.with_name(database.name + suffix) for suffix in
                                  ('-wal', '-shm', '-journal')), paths.settings,
                       paths.root / 'settings.env', paths.root / 'settings.env.migrated',
                       paths.root / 'installation.json', paths.root / 'installation.lock',
                       paths.agents / (LABEL + '.plist'), paths.support / APP_RECORD,
                       paths.support / 'service.plist', paths.support / 'source.json']
            snapshot = Snapshot(tracked)
            venv.parent.mkdir(parents=True, exist_ok=True)
            adapter.prepare_environment(paths.source, venv)
            point('environment')
            adapter.check_models(venv, paths.source)
            point('models')
            settings = migrate_settings(paths, env)
            point('settings')
            if upgrading:
                from .migrate_v1 import migrate
                migrate(database, inbox=Path(settings.get('inbox')), service_stopped=True)
            else:
                from . import store
                store.connect(database).close()
            point('database')
            (paths.root / 'logs').mkdir(exist_ok=True)
            plist = paths.agents / (LABEL + '.plist')
            _atomic(plist, service_plist(paths, venv, labels, app_install=app_install))
            if app_install:
                _record_app_service(paths, plist, venv)
            from .selfupdate import record_source
            record_source(paths.support, paths.source)
            execution_guard.close()  # Hand both execution locks to the new serve.
            service_guard.close()
            new_attempted = True
            started = time.time_ns()
            adapter.register(plist)
            point('registered')
            adapter.start(LABEL)
            point('started')
            if not adapter.healthy(LABEL, paths.support, settings, started):
                raise InstallError('new service failed authenticated status check')
            point('healthy')
            # Trim only after startup is confirmed, still inside rollback scope.
            backups = sorted(paths.root.glob('state.sqlite3.bak-*'), key=lambda p: p.name, reverse=True)
            for backup in backups[3:]:
                backup.unlink()
        except BaseException as error:
            failures = []
            if new_attempted:
                try:
                    adapter.unload(LABEL)
                    service_guard.enter_context(_lock(paths.support / 'serve.lock', wait=STOP_WAIT_SEC))
                    execution_guard.enter_context(_lock(paths.root / 'tick.lock', wait=STOP_WAIT_SEC))
                except BaseException as exc:
                    # Never restore an old DB while the new service may still write it.
                    raise InstallError(f'rollback blocked: cannot stop new service: {exc}; original: {error}') from error
            if snapshot:
                try:
                    snapshot.restore()
                except BaseException as exc:
                    raise InstallError(f'rollback blocked: cannot restore data: {exc}; original: {error}') from error
            shutil.rmtree(venv, ignore_errors=True)
            service_guard.close()
            for name, plist in stopped:
                try:
                    if not adapter.registered(name):
                        adapter.register(plist)
                except BaseException as exc:
                    failures.append(f'{name}: {exc}')
            if failures:
                raise InstallError(f'old service restore failed: {failures}; original: {error}') from error
            raise
    return '\n'.join(plan) + '\nService is healthy. Notes require separate consent to migrate.\n' + link_cli(paths, venv)


def _require_v2(paths):
    database = paths.root / 'state.sqlite3'
    if not database.is_file():
        raise InstallError('not installed: use quietclerk install')
    # Even SQLite mode=ro creates WAL/SHM files in the source directory. Query a
    # disposable copy, including committed WAL, to keep preflight/dry-run inert.
    with tempfile.TemporaryDirectory(prefix='quietclerk-update-') as temporary:
        probe = Path(temporary) / database.name
        shutil.copyfile(database, probe)
        wal = database.with_name(database.name + '-wal')
        if wal.is_file():
            shutil.copyfile(wal, probe.with_name(probe.name + '-wal'))
        try:
            with closing(sqlite3.connect(probe.as_uri() + '?mode=ro', uri=True)) as con:
                tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                version = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() if 'meta' in tables else None
                if version != ('2',):
                    if version == ('1',) or ('meta' not in tables and tables == {'files', 'jobs'}):
                        raise InstallError('v1 installation: use quietclerk upgrade')
                    raise InstallError('unsupported database schema: update requires schema v2')
        except sqlite3.DatabaseError as exc:
            raise InstallError(f'invalid installed database: {exc}') from exc


def _update_settings(paths, service):
    """Read settings without config.load's installation-default initialization."""
    if not paths.settings.is_file():
        raise InstallError('not installed: missing settings.toml; use quietclerk install')
    from . import config
    try:
        values = {key: config._validate(key, value) for key, value in
                  config._flatten(tomllib.loads(paths.settings.read_text(encoding='utf-8'))).items()}
        env = service.get('EnvironmentVariables', {})
        if not isinstance(env, dict):
            raise ValueError('EnvironmentVariables must be a dictionary')
        configured_root = env.get('QC_ROOT', values.get('root', str(paths.root)))
        if Path(configured_root).expanduser().resolve() != paths.root:
            raise InstallError('configured root differs from installed root; update cannot move data')
        if 'QC_PORT' in env:
            values['server.port'] = config._validate('server.port', int(env['QC_PORT']))
        elif 'server.port' not in values:
            defaults = json.loads((paths.root / 'installation.json').read_text(encoding='utf-8'))
            values['server.port'] = config._validate('server.port', defaults['server.port'])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise InstallError(f'invalid installed settings: {exc}') from exc
    return values


def update(*, root=None, dry_run=False, adapter=None, fault=None, **locations):
    """Replace only a v2 service's interpreter, never migrate or restore user data.

    Prepare while the old engine runs; hold both execution locks across cutover,
    then hand them to serve. Partial unload/bootstrap and failed health checks
    restore the exact old plist and verify the old service. Dry-run is read-only
    and cannot probe launchd registration. Keep the immediate previous venv;
    trim only older UUID-named environments owned by this installer.
    """
    if locations.get('source') is None:
        from .selfupdate import read_json
        identity = read_json(Path(locations.get('support') or SUPPORT) / 'source.json')
        if identity.get('source'):
            locations['source'] = identity['source']
        elif (Path.cwd() / 'pyproject.toml').is_file():
            locations['source'] = Path.cwd()
    paths = layout(root, updating=True, **locations)
    plist = paths.agents / (LABEL + '.plist')
    # Check the database first so a v1 root receives the migration instruction.
    _require_v2(paths)
    if not plist.is_file():
        raise InstallError('not installed: missing service plist; use quietclerk install')
    snapshot = Snapshot([plist, paths.support / 'source.json', paths.support / APP_RECORD,
                         paths.support / 'service.plist'])
    try:
        service = plistlib.loads(snapshot.files[plist][0])
        if not isinstance(service, dict):
            raise ValueError('expected a plist dictionary')
        argv = service['ProgramArguments']
        if not isinstance(argv, list) or not all(isinstance(arg, str) for arg in argv):
            raise ValueError('expected a string argument array')
        if (service.get('Label') != LABEL or argv[1:3] != ['-m', 'quietclerk.cli'] or
                'serve' not in argv or not Path(argv[0]).is_absolute() or
                Path(service['WorkingDirectory']).resolve() != paths.root or
                Path(argv[argv.index('--settings') + 1]).resolve() != paths.settings.resolve() or
                Path(argv[argv.index('--support') + 1]).resolve() != paths.support.resolve()):
            raise ValueError('service paths or command do not match')
        previous = Path(argv[0]).parent.parent
        settings = _update_settings(paths, service)
    except (ValueError, KeyError, IndexError, TypeError, plistlib.InvalidFileException, ExpatError) as exc:
        raise InstallError(f'invalid installed service plist: {exc}') from exc
    plan = [f'Update installed v2 root: {paths.root}',
            f'Check {LABEL} is registered (not probed in dry-run)',
            'Prepare fresh venv, imports and models while the old service runs',
            'Stop service; wait for serve.lock and tick.lock before cutover',
            'Replace plist interpreter; restart; verify authenticated status',
            'On failure: restore exact old plist; restart and verify old service',
            'Keep previous venv; remove older managed venvs; leave DB/settings/notes untouched']
    if dry_run:
        return '\n'.join(plan)
    venv = paths.root / '.venvs' / uuid.uuid4().hex
    stopped = False
    adapter = adapter or MacAdapter()
    new_attempted = False
    def point(stage):
        if fault:
            fault(stage)
    with _lock(paths.support / 'upgrade.lock'), ExitStack() as guard:
        if plist.read_bytes() != snapshot.files[plist][0]:
            raise InstallError('service plist changed during update preparation; retry update')
        if not adapter.registered(LABEL):
            raise InstallError('not installed: service is not registered; use quietclerk install (v1: use upgrade)')
        try:
            venv.parent.mkdir(parents=True, exist_ok=True)
            adapter.prepare_environment(paths.source, venv)
            point('environment')
            adapter.check_models(venv, paths.source)
            point('models')
            stopped = True  # Include a partially successful bootout in rollback.
            adapter.unload(LABEL)
            point('unloaded')
            guard.enter_context(_lock(paths.support / 'serve.lock', wait=STOP_WAIT_SEC))
            guard.enter_context(_lock(paths.root / 'tick.lock', wait=STOP_WAIT_SEC))
            point('locked')
            settings = _update_settings(paths, service)  # Include settings saved during preparation.
            service['ProgramArguments'] = [str(venv / 'bin/python'), *argv[1:]]
            if (paths.support / APP_RECORD).exists():
                for binary in ('uv', 'ffmpeg', 'ffprobe'):
                    if (venv / 'bin' / binary).is_file():
                        service.setdefault('EnvironmentVariables', {})['QC_' + binary.upper()] = str(venv / 'bin' / binary)
            _atomic(plist, plistlib.dumps(service), snapshot.files[plist][1])
            if (paths.support / APP_RECORD).exists():
                read_app_installation(paths.support / APP_RECORD)
                _record_app_service(paths, plist, venv)
            point('plist')
            from .selfupdate import record_source
            record_source(paths.support, paths.source)
            guard.close()
            new_attempted = True
            started = time.time_ns()
            adapter.register(plist)
            point('registered')
            adapter.start(LABEL)
            point('started')
            if not adapter.healthy(LABEL, paths.support, settings, started):
                raise InstallError('updated service failed authenticated status check')
            point('healthy')
        except BaseException as error:
            guard.close()
            if stopped:
                try:
                    if new_attempted:
                        adapter.unload(LABEL)
                    # A failed bootout may leave the old registration in place.
                    # Stop it before restoring/re-registering the saved plist.
                    elif adapter.registered(LABEL):
                        adapter.unload(LABEL)
                    guard.enter_context(_lock(paths.support / 'serve.lock', wait=STOP_WAIT_SEC))
                    guard.enter_context(_lock(paths.root / 'tick.lock', wait=STOP_WAIT_SEC))
                    snapshot.restore()
                    guard.close()  # Hand execution locks back to the restored serve.
                    started = time.time_ns()
                    adapter.register(plist)
                    adapter.start(LABEL)
                    if not adapter.healthy(LABEL, paths.support, settings, started):
                        raise InstallError('old service failed authenticated status check')
                except BaseException as exc:
                    raise InstallError(f'update rollback failed: {exc}; original: {error}') from error
            shutil.rmtree(venv, ignore_errors=True)
            raise
        link_report = link_cli(paths, venv)
        # Only UUID-named, non-symlink directories are ours to prune. Keep the
        # immediately previous interpreter even when it lives outside .venvs.
        for candidate in venv.parent.iterdir():
            if (candidate not in (venv, previous) and not candidate.is_symlink() and
                    candidate.is_dir() and re.fullmatch(r'[0-9a-f]{32}', candidate.name)):
                shutil.rmtree(candidate, ignore_errors=True)
    return '\n'.join(plan) + '\nService is healthy.\n' + link_report


def doctor(*, root=None, adapter=None, home=None, agents=None, legacy_labels=()):
    """Read-only human-facing diagnostics; missing probes are reported, not hidden."""
    home = Path(home or Path.home())
    root = Path(root).expanduser() if root else (home / 'rec' if (home / 'rec').exists() else home / 'QuietClerk')
    adapter = adapter or MacAdapter()
    paths = Layout(root, home, Path(__file__).parent.parent, Path(agents or home / 'Library/LaunchAgents'),
                   home / 'Library/Application Support/QuietClerk', root / 'settings.toml')
    rows = list(adapter.machine_info(root).items())
    cache = Path(os.environ.get('HF_HUB_CACHE', Path(os.environ.get('HF_HOME', home / '.cache/huggingface')) / 'hub'))
    from .backends.mlx import MODELS
    for name, repo in MODELS.items():
        snapshots = cache / ('models--' + repo.replace('/', '--')) / 'snapshots'
        try:
            found = any(p.is_dir() and any(p.iterdir()) for p in snapshots.glob('*'))
            state = 'snapshot present (not load-verified)' if found else 'missing'
        except OSError:
            state = 'unavailable'
        rows.append((f'model {name}', f'{state}: {snapshots}'))
    for label in (LABEL, *legacy_services(paths, legacy_labels)):
        try:
            state = 'registered' if adapter.registered(label) else 'not registered'
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            state = f'unavailable: {exc}'
        rows.append((f'service {label}', state))
    width = max(len(key) for key, _ in rows)
    return '\n'.join(f'{key:<{width}} | {value}' for key, value in rows)


def login_service(action, *, support=None, home=None, adapter=None):
    """App OS lifecycle API. CLI-owned services are read-only, never adopted."""
    if action not in ('status', 'register', 'unregister'):
        raise InstallError('invalid login service action')
    support = Path(support or SUPPORT).absolute()
    home = Path(home or Path.home()).absolute()
    adapter = adapter or MacAdapter()
    plist = home / 'Library/LaunchAgents' / (LABEL + '.plist')
    record_path = support / APP_RECORD

    def inspect():
        registered = adapter.registered(LABEL)
        if not record_path.exists():
            return {'manager': 'cli' if plist.exists() or registered else None,
                    'registered': registered, 'login_enabled': plist.exists()}, None
        record = read_app_installation(record_path)
        if Path(record['support']) != support or Path(record['plist']) != plist:
            raise InstallError('app installation locations do not match this user')
        content = (support / 'service.plist').read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != record.get('plist_sha256'):
            raise InstallError('saved app service definition changed')
        # A CLI/user replacement wins over stale app ownership metadata.
        conflict = ((plist.exists() and plist.read_bytes() != content) or
                    (registered and not plist.exists()))
        return {'manager': 'cli' if conflict else 'app', 'registered': registered,
                'login_enabled': plist.exists()}, (record, content)

    state, installed = inspect()
    if action == 'status' or state['manager'] != 'app':
        return state
    with _lock(support / 'upgrade.lock'):
        state, installed = inspect()
        if state['manager'] != 'app':
            return state
        record, content = installed
        paths = Layout(Path(record['root']), home, Path(__file__).parent.parent,
                       plist.parent, support, Path(record['settings']))
        if action == 'unregister':
            adapter.unload(LABEL)
            with _lock(support / 'serve.lock', wait=STOP_WAIT_SEC), _lock(paths.root / 'tick.lock', wait=STOP_WAIT_SEC):
                plist.unlink(missing_ok=True)
        elif not state['registered']:
            service = plistlib.loads(content)
            settings = _update_settings(paths, service)
            before = Snapshot([plist])
            attempted = False
            try:
                # Do not start a second engine beside a manually running serve.
                with _lock(support / 'serve.lock'), _lock(paths.root / 'tick.lock'):
                    _atomic(plist, content)
                attempted = True
                started = time.time_ns()
                adapter.register(plist)
                adapter.start(LABEL)
                if not adapter.healthy(LABEL, support, settings, started):
                    raise InstallError('login service failed authenticated status check')
            except BaseException:
                if attempted:
                    adapter.unload(LABEL)
                with _lock(support / 'serve.lock', wait=STOP_WAIT_SEC), _lock(paths.root / 'tick.lock', wait=STOP_WAIT_SEC):
                    before.restore()
                raise
        return inspect()[0]
