"""G synthetic-input policy: literal v1 settings + recognized SQLite rows migrate;
unknown schemas/keys, shell substitutions, live locks/children and root conflicts
fail closed. Legacy notes are opaque bytes and never migrated by installation.
All launchd operations use FakeMac with temporary home/LaunchAgents directories;
no real launchctl, models, recordings or operational roots are used here.
V2 updates accept existing schema-v2 SQLite + literal TOML and a matching plist;
unknown/corrupt state, mismatched roots and malformed plist commands fail closed.
Update fault injection covers preparation, cutover and rollback with byte checks;
no supplied source path is evaluated as shell code. These are synthetic inputs,
not a rehearsal against a live launchd service or actual model installation.
"""
import fcntl
import json
import os
import plistlib
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from quietclerk import cli, install
from quietclerk.migrate_v1 import V1_COLUMNS

SOURCE = Path(__file__).resolve().parent.parent


class FakeMac:
    def __init__(self, registered=('custom.rec.tick',), fail=None, children=False):
        self.labels = set(registered)
        self.calls = []
        self.fail = fail
        self.children = children

    def record(self, method, value=None):
        self.calls.append((method, value))
        if self.fail == method:
            raise RuntimeError('injected ' + method)

    def registered(self, label):
        return label in self.labels

    def unload(self, label):
        self.record('unload', label)
        self.labels.discard(label)

    def register(self, plist):
        label = plistlib.loads(Path(plist).read_bytes())['Label']
        self.labels.add(label)  # Simulate partial bootstrap before a failure.
        self.record('register_new' if label == install.LABEL else 'register_old', label)

    def start(self, label):
        self.record('start', label)

    def processes(self, root):
        self.record('processes')
        return {123456} if self.children else set()

    def surviving(self, pids):
        return pids

    def prepare_environment(self, source, venv):
        (venv / 'bin').mkdir(parents=True)
        (venv / 'bin/python').write_text('fake python')
        self.record('environment', venv)

    def check_models(self, venv, source):
        self.record('models')

    def healthy(self, label, support, settings, started):
        self.record('health')
        return self.fail != 'unhealthy'

    def machine_info(self, root):
        return {'chip': 'Synthetic Apple M1', 'memory': '17179869184', 'disk_free': '9999999',
                'ffmpeg': '/fake/ffmpeg', 'uv': '/fake/uv'}


@pytest.fixture
def old_root(tmp_path):
    home = tmp_path / 'home & sandbox'
    root = home / 'rec'
    agents = home / 'Library/LaunchAgents'
    agents.mkdir(parents=True)
    root.mkdir()
    (root / 'notes').mkdir()
    (root / 'notes/user.md').write_bytes('가상 사용자 노트\r\n- [x] 유지\n'.encode())
    (root / 'settings.env').write_text(
        f'REC_OUTPUT="{root}/notes"\nREC_SINCE=2026-01-02 03:04\n'
        'REC_MIN_DURATION_SEC=30\nREC_STABLE_SEC=10\nREC_CODEX_EFFORT=low\n')
    con = sqlite3.connect(root / 'state.sqlite3')
    for table, columns in V1_COLUMNS.items():
        con.execute(f'CREATE TABLE {table} (' + ','.join(f'{name} {kind}' for name, kind in columns) + ')')
    con.execute('INSERT INTO files VALUES(?,100,1,2,1)', ('sample.m4a',))
    con.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('20260102-030400-00000001', 'a' * 64, 'sample.m4a', '/virtual/source.m4a',
                 600, 'done', None, 0, None, None, str(root / 'notes/user.md'), 1, 2))
    con.commit()
    con.close()
    plist = agents / 'custom.rec.tick.plist'
    plist.write_bytes(plistlib.dumps({'Label': 'custom.rec.tick',
                                    'ProgramArguments': ['/virtual/python', '-m', 'rec.tick']}))
    return {'root': root, 'home': home, 'agents': agents,
            'support': home / 'Library/Application Support/QuietClerk', 'source': SOURCE}


def retained_bytes(paths):
    root = paths['root']
    return {str(path): path.read_bytes() for path in
            [root / 'state.sqlite3', root / 'settings.env', root / 'notes/user.md',
             paths['agents'] / 'custom.rec.tick.plist']}


def assert_restored(paths, before, adapter):
    for name, content in before.items():
        assert Path(name).read_bytes() == content
    assert adapter.labels == {'custom.rec.tick'}
    assert ('register_old', 'custom.rec.tick') in adapter.calls
    assert not (paths['root'] / 'settings.env.migrated').exists()
    assert not (paths['root'] / 'settings.toml').exists()
    assert not (paths['root'] / 'installation.json').exists()
    assert not (paths['agents'] / (install.LABEL + '.plist')).exists()
    assert list((paths['root'] / '.venvs').glob('*')) == []


def test_upgrade_adopts_v1_root_and_keeps_notes_and_legacy_plists(old_root):
    before = retained_bytes(old_root)
    adapter = FakeMac()
    report = install.run(upgrading=True, adapter=adapter, environ={}, **old_root)
    root = old_root['root']
    assert 'Service is healthy' in report
    assert adapter.labels == {install.LABEL}
    con = sqlite3.connect(root / 'state.sqlite3')
    assert con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() == ('2',)
    assert con.execute('SELECT legacy,note_path FROM jobs').fetchone() == (1, str(root / 'notes/user.md'))
    con.close()
    assert (root / 'settings.env.migrated').read_bytes() == before[str(root / 'settings.env')]
    assert not (root / 'settings.env').exists()
    settings = install.tomllib.loads((root / 'settings.toml').read_text())
    assert settings['root'] == str(root)
    assert settings['since'] == '2026-01-02 03:04'
    assert settings['min_duration_sec'] == 30
    assert settings['providers.codex.effort'] == 'low'
    # v1 was Korean-only: an English machine locale must not switch the user's notes to English.
    assert settings['language.default'] == settings['ui.language'] == 'ko'
    assert (root / 'notes/user.md').read_bytes() == before[str(root / 'notes/user.md')]
    assert (old_root['agents'] / 'custom.rec.tick.plist').exists()
    plist = plistlib.loads((old_root['agents'] / (install.LABEL + '.plist')).read_bytes())
    assert plist['KeepAlive'] is True and plist['RunAtLoad'] is True
    assert 'StartInterval' not in plist
    assert plist['ProgramArguments'][1:3] == ['-m', 'quietclerk.cli']
    assert 'serve' in plist['ProgramArguments'] and 'quietclerk.tick' not in plist['ProgramArguments']
    assert '--legacy-label' in plist['ProgramArguments'] and 'custom.rec.tick' in plist['ProgramArguments']
    assert plist['StandardErrorPath'] == str(root / 'logs/launchd.err')
    assert plist['WorkingDirectory'] == str(root)
    assert len(list(root.glob('state.sqlite3.bak-*'))) == 1
    methods = [name for name, _ in adapter.calls]
    assert methods.index('unload') < methods.index('environment') < methods.index('models') < methods.index('register_new')


@pytest.mark.parametrize('healthy', [True, False])
def test_F04_upgrade_hands_execution_lock_to_live_serve(old_root, healthy):
    from quietclerk.serve import Runtime
    class Idle:
        def __init__(self, *args): pass
        def run_one(self, **kwargs): return None
    class LiveMac(FakeMac):
        runtime = None
        def healthy(self, label, support, settings, started):
            self.runtime = Runtime(settings, support=support, label_check=lambda _: False,
                                   executor_factory=Idle, scan=lambda *a, **k: None)
            self.runtime.start()
            return healthy
        def unload(self, label):
            if label == install.LABEL and self.runtime:
                self.runtime.close()
            super().unload(label)
    adapter = LiveMac()
    before = retained_bytes(old_root)
    try:
        if healthy:
            assert 'Service is healthy' in install.run(upgrading=True, adapter=adapter, environ={}, **old_root)
        else:
            with pytest.raises(install.InstallError, match='authenticated status'):
                install.run(upgrading=True, adapter=adapter, environ={}, **old_root)
            assert_restored(old_root, before, adapter)
    finally:
        if adapter.runtime:
            adapter.runtime.close()


def test_rollback_waits_for_a_stopping_serve_to_release_its_locks(old_root):
    # Found on the Mac mini rehearsal (2026-11-10): launchctl bootout returns before the
    # serve process exits, so an immediate non-blocking lock made rollback give up
    # without restoring the database or re-registering the old service.
    import threading
    from quietclerk.serve import Runtime
    class Idle:
        def __init__(self, *args): pass
        def run_one(self, **kwargs): return None
    class SlowStopMac(FakeMac):
        runtime = None
        def healthy(self, label, support, settings, started):
            self.runtime = Runtime(settings, support=support, label_check=lambda _: False,
                                   executor_factory=Idle, scan=lambda *a, **k: None)
            self.runtime.start()
            return False
        def unload(self, label):
            if label == install.LABEL and self.runtime:
                threading.Timer(1.0, self.runtime.close).start()
            super().unload(label)
    adapter = SlowStopMac()
    before = retained_bytes(old_root)
    with pytest.raises(install.InstallError, match='authenticated status'):
        install.run(upgrading=True, adapter=adapter, environ={}, **old_root)
    assert_restored(old_root, before, adapter)


def test_installer_reads_bootstrap_without_web_dependencies():
    # The installer may run from an interpreter without starlette (rehearsal finding).
    code = ('import sys; sys.modules["starlette"] = None; '
            'from quietclerk.bootstrap_file import read_bootstrap; import quietclerk.install')
    subprocess.run([sys.executable, '-c', code], check=True, cwd=SOURCE)


@pytest.mark.parametrize('stage', ['unloaded', 'locked', 'children_checked', 'environment', 'models',
                                    'settings', 'database', 'registered', 'started', 'healthy'])
def test_every_stage_failure_restores_exact_db_config_and_old_registration(old_root, stage):
    before = retained_bytes(old_root)
    adapter = FakeMac()
    def fail(point):
        if point == stage:
            raise RuntimeError('fault at ' + point)
    with pytest.raises(RuntimeError, match='fault at'):
        install.run(upgrading=True, adapter=adapter, environ={}, fault=fail, **old_root)
    assert_restored(old_root, before, adapter)


@pytest.mark.parametrize('method', ['environment', 'models', 'register_new', 'start', 'health', 'unhealthy'])
def test_adapter_failures_including_partial_bootstrap_roll_back(old_root, method):
    before = retained_bytes(old_root)
    adapter = FakeMac(fail=method)
    with pytest.raises(RuntimeError, match='injected|authenticated status'):
        install.run(upgrading=True, adapter=adapter, environ={}, **old_root)
    assert_restored(old_root, before, adapter)


def test_lock_holder_prevents_environment_or_migration_and_reregisters_old(old_root):
    adapter = FakeMac()
    before = retained_bytes(old_root)
    with (old_root['root'] / 'tick.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(install.InstallError, match='lock is held'):
            install.run(upgrading=True, adapter=adapter, environ={}, **old_root)
    assert_restored(old_root, before, adapter)
    assert all(name != 'environment' for name, _ in adapter.calls)


def test_surviving_legacy_child_refuses_upgrade(old_root):
    adapter = FakeMac(children=True)
    before = retained_bytes(old_root)
    with pytest.raises(install.InstallError, match='child processes'):
        install.run(upgrading=True, adapter=adapter, environ={}, **old_root)
    assert_restored(old_root, before, adapter)


def test_both_roots_conflict_before_any_platform_operation(old_root):
    (old_root['home'] / 'QuietClerk').mkdir()
    adapter = FakeMac()
    with pytest.raises(install.InstallError, match='root conflict'):
        install.run(upgrading=True, adapter=adapter, environ={}, **old_root)
    assert adapter.calls == []


def tree_bytes(path):
    return {str(p.relative_to(path)): p.read_bytes() if p.is_file() else None for p in path.rglob('*')}


def test_dry_run_is_entirely_read_only_without_any_adapter_calls(old_root):
    before = tree_bytes(old_root['home'])
    adapter = FakeMac()
    report = install.run(upgrading=True, adapter=adapter, environ={}, dry_run=True, **old_root)
    assert str(old_root['root']) in report and 'tick.lock' in report
    assert tree_bytes(old_root['home']) == before
    assert adapter.calls == []
    assert adapter.labels == {'custom.rec.tick'}


def test_fresh_install_and_install_dry_run(tmp_path):
    home = tmp_path / 'home'
    adapter = FakeMac(registered=())
    options = {'home': home, 'source': SOURCE, 'adapter': adapter, 'environ': {}}
    assert 'Create root:' in install.run(dry_run=True, **options)
    assert not home.exists()
    install.run(**options)
    root = home / 'QuietClerk'
    assert (root / 'settings.toml').exists()
    assert adapter.labels == {install.LABEL}
    con = sqlite3.connect(root / 'state.sqlite3')
    assert con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() == ('2',)
    con.close()


@pytest.mark.parametrize('content', ['REC_OUTPUT=$(touch /never-execute)\n',
                                     'REC_OUTPUT=`touch /never-execute`\n',
                                     'REC_OUTPUT=${HOME}/notes\n',
                                     'REC_UNKNOWN=value\n', 'source /bad/file\n',
                                     'REC_MIN_DURATION_SEC=not-an-int\n'])
def test_malicious_or_unknown_legacy_settings_fail_closed(old_root, content):
    (old_root['root'] / 'settings.env').write_text(content)
    before = retained_bytes(old_root)
    adapter = FakeMac()
    with pytest.raises((install.InstallError, ValueError)):
        install.run(upgrading=True, adapter=adapter, environ={}, **old_root)
    assert_restored(old_root, before, adapter)


def test_unknown_database_schema_rolls_back_settings(old_root):
    con = sqlite3.connect(old_root['root'] / 'state.sqlite3')
    con.execute('CREATE TABLE unexpected(value TEXT)')
    con.commit()
    con.close()
    before = retained_bytes(old_root)
    adapter = FakeMac()
    with pytest.raises(ValueError, match='unknown v1 tables'):
        install.run(upgrading=True, adapter=adapter, environ={}, **old_root)
    assert_restored(old_root, before, adapter)


def test_existing_settings_and_installation_bytes_are_restored(old_root):
    root = old_root['root']
    settings = root / 'settings.toml'
    settings.write_bytes(b'# retain comments\nmin_duration_sec = 123\n')
    defaults = root / 'installation.json'
    defaults.write_text(json.dumps({'since': '2025-01-01 00:00', 'server.port': 8021,
                                   'language.default': 'ko', 'ui.language': 'ko'}))
    original = {p: p.read_bytes() for p in (settings, defaults, root / 'settings.env', root / 'state.sqlite3')}
    adapter = FakeMac(fail='health')
    with pytest.raises(RuntimeError, match='injected health'):
        install.run(upgrading=True, adapter=adapter, environ={}, **old_root)
    assert all(p.read_bytes() == content for p, content in original.items())
    assert adapter.labels == {'custom.rec.tick'}


def test_wal_only_data_and_bytes_survive_rollback(old_root):
    root = old_root['root']
    # Leave committed WAL behind as a crashed v1 process would, without retaining
    # a live SQLite connection/inode across the installer transaction.
    script = """import os, sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute('PRAGMA journal_mode=WAL')
con.execute('PRAGMA wal_autocheckpoint=0')
con.execute("UPDATE jobs SET output_path='wal-only-synthetic.md'")
con.commit()
os._exit(0)
"""
    subprocess.run([sys.executable, '-c', script, str(root / 'state.sqlite3')], check=True)
    original = {p: p.read_bytes() for p in (root / 'state.sqlite3', root / 'state.sqlite3-wal')}
    with pytest.raises(RuntimeError, match='injected health'):
        install.run(upgrading=True, adapter=FakeMac(fail='health'), environ={}, **old_root)
    assert all(p.read_bytes() == content for p, content in original.items())
    with sqlite3.connect(root / 'state.sqlite3') as restored:
        assert restored.execute('SELECT output_path FROM jobs').fetchone() == ('wal-only-synthetic.md',)


def test_all_discovered_and_explicit_old_labels_unload_and_restore(old_root):
    plist = old_root['agents'] / 'second.old.plist'
    plist.write_bytes(plistlib.dumps({'Label': 'second.old', 'ProgramArguments': ['custom-tick']}))
    adapter = FakeMac(registered=('custom.rec.tick', 'second.old'), fail='models')
    with pytest.raises(RuntimeError, match='injected models'):
        install.run(upgrading=True, adapter=adapter, environ={}, legacy_labels=['second.old'], **old_root)
    assert adapter.labels == {'custom.rec.tick', 'second.old'}
    assert {value for name, value in adapter.calls if name == 'unload'} == adapter.labels


def test_missing_restorable_plist_does_not_unload_any_service(old_root):
    (old_root['agents'] / 'custom.rec.tick.plist').unlink()
    adapter = FakeMac()
    with pytest.raises(install.InstallError, match='no restorable plist'):
        install.run(upgrading=True, adapter=adapter, environ={}, legacy_labels=['custom.rec.tick'], **old_root)
    assert all(name != 'unload' for name, _ in adapter.calls)


def test_doctor_reports_machine_models_and_legacy_service_read_only(old_root, monkeypatch):
    monkeypatch.setenv('HF_HOME', str(old_root['home'] / 'empty-cache'))
    before = tree_bytes(old_root['home'])
    report = install.doctor(root=old_root['root'], home=old_root['home'],
                            agents=old_root['agents'], adapter=FakeMac())
    for expected in ('chip', 'memory', 'disk_free', 'ffmpeg', 'uv', 'model asr', 'missing:',
                     install.LABEL, 'custom.rec.tick', 'registered'):
        assert expected in report
    assert tree_bytes(old_root['home']) == before


def test_cli_installer_dry_run_has_no_import_time_root_writes(old_root, tmp_path):
    home = tmp_path / 'fresh-cli-home'
    home.mkdir()
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(('QC_', 'REC_')):
            del env[key]
    env['HOME'] = str(home)
    result = subprocess.run([sys.executable, '-m', 'quietclerk.cli', 'install', '--dry-run'],
                            env=env, cwd=SOURCE, text=True, capture_output=True, check=True)
    assert 'Create root:' in result.stdout
    assert list(home.iterdir()) == []


def test_cli_dispatches_install_upgrade_doctor_and_surfaces_failures(monkeypatch, capsys, tmp_path):
    calls = []
    monkeypatch.setattr(install, 'run', lambda **kwargs: calls.append(kwargs) or 'planned')
    assert cli.main(['upgrade', '--root', str(tmp_path), '--dry-run']) == 0
    assert calls[0]['upgrading'] is True and calls[0]['dry_run'] is True
    monkeypatch.setattr(install, 'doctor', lambda **kwargs: 'chip | fake')
    assert cli.main(['doctor']) == 0
    def error(**kwargs):
        raise install.InstallError('root conflict')
    monkeypatch.setattr(install, 'run', error)
    assert cli.main(['install']) == 1
    assert 'root conflict' in capsys.readouterr().err


def test_launchctl_and_venv_adapters_use_argument_arrays(monkeypatch, tmp_path):
    calls = []
    def execute(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout='ok', stderr='')
    monkeypatch.setattr(subprocess, 'run', execute)
    monkeypatch.setattr(install.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(install.platform, 'machine', lambda: 'arm64')
    monkeypatch.setattr(install.shutil, 'which', lambda binary: '/fake/' + binary)
    adapter = install.MacAdapter()
    adapter.prepare_environment(SOURCE, tmp_path / 'venv & safe')
    adapter.check_models(tmp_path / 'venv & safe', SOURCE)
    adapter.register(tmp_path / 'agent with spaces.plist')
    adapter.start(install.LABEL)
    adapter.unload(install.LABEL)
    assert all(isinstance(argv, list) and not kwargs.get('shell') for argv, kwargs in calls)
    assert ['uv', 'pip', 'install', '--python',
            str(tmp_path / 'venv & safe/bin/python'), str(SOURCE)] in [argv for argv, _ in calls]
    assert all('cwd' not in kwargs for _, kwargs in calls)
    with pytest.raises(install.InstallError, match='invalid launchd label'):
        adapter.registered('bad/label')


def test_automatic_upgrade_adopts_rec_without_creating_second_root(old_root):
    options = {key: value for key, value in old_root.items() if key != 'root'}
    install.run(upgrading=True, adapter=FakeMac(), environ={}, **options)
    assert not (old_root['home'] / 'QuietClerk').exists()
    assert (old_root['root'] / 'settings.toml').is_file()


def test_legacy_environment_overrides_file_once(old_root):
    install.run(upgrading=True, adapter=FakeMac(),
                environ={'REC_MIN_DURATION_SEC': '45', 'REC_STABLE_SEC': '12'}, **old_root)
    values = install.tomllib.loads((old_root['root'] / 'settings.toml').read_text())
    assert values['min_duration_sec'] == 45 and values['stable_sec'] == 12


def test_configured_root_move_is_rejected_and_restored(old_root):
    before = retained_bytes(old_root)
    adapter = FakeMac()
    with pytest.raises(install.InstallError, match='root moves are not upgrades'):
        install.run(upgrading=True, adapter=adapter,
                    environ={'REC_ROOT': str(old_root['home'] / 'elsewhere')}, **old_root)
    assert_restored(old_root, before, adapter)


def test_settings_file_custom_label_is_discovered_without_module_hint(old_root):
    label = 'explicit.legacy'
    with (old_root['root'] / 'settings.env').open('a') as stream:
        stream.write(f'REC_LABEL={label}\n')
    (old_root['agents'] / (label + '.plist')).write_bytes(
        plistlib.dumps({'Label': label, 'ProgramArguments': ['/virtual/custom-tick-script']}))
    adapter = FakeMac(registered=(label,))
    install.run(upgrading=True, adapter=adapter, environ={}, **old_root)
    assert ('unload', label) in adapter.calls
    assert adapter.labels == {install.LABEL}


def test_manual_serve_lock_prevents_migration(old_root):
    before = retained_bytes(old_root)
    adapter = FakeMac()
    old_root['support'].mkdir(parents=True)
    with (old_root['support'] / 'serve.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(install.InstallError, match='lock is held'):
            install.run(upgrading=True, adapter=adapter, environ={}, **old_root)
    assert_restored(old_root, before, adapter)


def test_partial_legacy_unload_failure_reregisters_old_agent(old_root):
    class PartialUnload(FakeMac):
        def unload(self, label):
            super().unload(label)
            raise RuntimeError('partial unload')
    adapter = PartialUnload()
    before = retained_bytes(old_root)
    with pytest.raises(RuntimeError, match='partial unload'):
        install.run(upgrading=True, adapter=adapter, environ={}, **old_root)
    assert_restored(old_root, before, adapter)


def test_process_probe_captures_descendants_but_not_installer(monkeypatch, tmp_path):
    uid = os.getuid()
    own = os.getpid()
    adapter = install.MacAdapter()
    rows = f'''{own} 1 {uid} {tmp_path}/app/.venv/bin/python -m quietclerk.cli upgrade
991001 1 {uid} python -m rec.tick
991002 991001 {uid} codex exec
991003 991002 {uid} nested-child
991004 1 {uid + 1} python -m rec.tick
'''
    monkeypatch.setattr(adapter, 'command', lambda argv: rows)
    assert adapter.processes(tmp_path) == {991001, 991002, 991003}


def test_deploy_wrappers_are_valid_shell():
    for name in ('setup.sh', 'install.sh'):
        subprocess.run(['sh', '-n', str(SOURCE / 'deploy' / name)], check=True)


def test_wheel_source_is_supported_without_using_it_as_working_directory(tmp_path):
    wheel = tmp_path / 'quietclerk-0.1.0-py3-none-any.whl'
    wheel.write_bytes(b'synthetic wheel path; never installed by this test')
    paths = install.layout(home=tmp_path / 'home', source=wheel)
    plist = plistlib.loads(install.service_plist(paths, tmp_path / 'venv', ()))
    assert paths.source == wheel
    assert plist['WorkingDirectory'] == str(paths.root)
    assert plist['ProgramArguments'][0] == str(tmp_path / 'venv/bin/python')


def test_installed_layout_requires_an_explicit_wheel_before_any_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(install, '__file__', str(tmp_path / 'site-packages/quietclerk/install.py'))
    with pytest.raises(install.InstallError, match='provide --source'):
        install.layout(home=tmp_path / 'home')
    assert not (tmp_path / 'home').exists()


class UpdateMac(FakeMac):
    """One-shot faults let the restored service prove its own health."""
    def __init__(self, paths, fail=None):
        super().__init__(registered=(install.LABEL,), fail=fail)
        self.paths = paths
        self.plist = paths['agents'] / (install.LABEL + '.plist')
        self.python = plistlib.loads(self.plist.read_bytes())['ProgramArguments'][0]
        self.health_interpreters = []

    def record(self, method, value=None):
        self.calls.append((method, value))
        if self.fail == method:
            self.fail = None
            raise RuntimeError('injected ' + method)

    def registered(self, label):
        self.record('registration_probe', label)
        return super().registered(label)

    def prepare_environment(self, source, venv):
        assert self.labels == {install.LABEL}, 'prepare without stopping the installed service'
        super().prepare_environment(source, venv)

    def check_models(self, venv, source):
        assert self.labels == {install.LABEL}
        super().check_models(venv, source)

    def register(self, plist):
        self.python = plistlib.loads(plist.read_bytes())['ProgramArguments'][0]
        # A real serve must be able to take both locks immediately at bootstrap.
        with install._lock(self.paths['support'] / 'serve.lock'), install._lock(self.paths['root'] / 'tick.lock'):
            pass
        super().register(plist)

    def healthy(self, label, support, settings, started):
        assert label == install.LABEL
        assert support == self.paths['support']
        assert settings.get('server.port') > 0
        assert started > 0
        self.health_interpreters.append(self.python)
        if self.fail == 'unhealthy':
            self.fail = None
            self.record('health')
            return False
        return super().healthy(label, support, settings, started)


@pytest.fixture
def v2_root(old_root):
    install.run(upgrading=True, adapter=FakeMac(), environ={}, **old_root)
    return old_root


def update_bytes(paths):
    root = paths['root']
    return {path: path.read_bytes() for path in
            (root / 'state.sqlite3', root / 'settings.toml', root / 'installation.json',
             root / 'notes/user.md', paths['agents'] / (install.LABEL + '.plist'))}


def assert_update_restored(paths, before, adapter):
    assert all(path.read_bytes() == content for path, content in before.items())
    assert adapter.labels == {install.LABEL}
    old_python = plistlib.loads(before[adapter.plist])['ProgramArguments'][0]
    assert Path(old_python).is_file()
    assert list((paths['root'] / '.venvs').iterdir()) == [Path(old_python).parent.parent]
    if any(method == 'unload' for method, _ in adapter.calls):
        assert adapter.health_interpreters[-1] == old_python
        assert adapter.calls[-1] == ('health', None)


@pytest.mark.parametrize('wheel', [False, True])
def test_update_restarts_new_interpreter_and_preserves_user_bytes(v2_root, tmp_path, wheel):
    paths = dict(v2_root)
    if wheel:
        paths['source'] = tmp_path / 'quietclerk ; literal.whl'
        paths['source'].write_bytes(b'synthetic wheel; FakeMac never installs it')
    before = update_bytes(paths)
    adapter = UpdateMac(paths)
    root = paths['root']
    old_plist = plistlib.loads(before[adapter.plist])
    # Preserve operational overrides and legacy-label guards, not just defaults.
    old_plist['EnvironmentVariables']['EXAMPLE_LITERAL'] = '$(must not execute)'
    adapter.plist.write_bytes(plistlib.dumps(old_plist))
    old_python = old_plist['ProgramArguments'][0]
    stale = root / '.venvs' / ('f' * 32)
    stale.mkdir()
    unowned = root / '.venvs' / 'user-environment'
    unowned.mkdir()
    target = tmp_path / 'do-not-delete'
    target.mkdir()
    (root / '.venvs' / ('e' * 32)).symlink_to(target, target_is_directory=True)
    report = install.update(adapter=adapter, **paths)
    new_plist = plistlib.loads(adapter.plist.read_bytes())
    new_python = new_plist['ProgramArguments'][0]
    assert 'Service is healthy' in report
    assert new_python != old_python and Path(new_python).is_file()
    assert Path(old_python).is_file()
    expected = dict(old_plist)
    expected['ProgramArguments'] = [new_python, *old_plist['ProgramArguments'][1:]]
    assert new_plist == expected
    assert adapter.health_interpreters == [new_python]
    assert adapter.labels == {install.LABEL}
    methods = [method for method, _ in adapter.calls]
    assert methods.index('environment') < methods.index('models') < methods.index('unload')
    assert methods.index('unload') < methods.index('register_new') < methods.index('start') < methods.index('health')
    assert all(path.read_bytes() == content for path, content in before.items() if path != adapter.plist)
    assert not stale.exists() and unowned.exists() and target.exists()
    assert (root / '.venvs' / ('e' * 32)).is_symlink()


@pytest.mark.parametrize('stage', ['environment', 'models', 'unloaded', 'locked',
                                    'plist', 'registered', 'started', 'healthy'])
def test_update_every_stage_failure_restores_plist_registration_and_user_bytes(v2_root, stage):
    before = update_bytes(v2_root)
    adapter = UpdateMac(v2_root)
    def fail(point):
        if point == stage:
            raise RuntimeError('fault at ' + stage)
    with pytest.raises(RuntimeError, match='fault at'):
        install.update(adapter=adapter, fault=fail, **v2_root)
    assert_update_restored(v2_root, before, adapter)


@pytest.mark.parametrize('method', ['environment', 'models', 'unload', 'register_new', 'start', 'health', 'unhealthy'])
def test_update_adapter_failures_restore_old_service(v2_root, method):
    before = update_bytes(v2_root)
    adapter = UpdateMac(v2_root, fail=method)
    with pytest.raises(RuntimeError, match='injected|authenticated status'):
        install.update(adapter=adapter, **v2_root)
    assert_update_restored(v2_root, before, adapter)


def test_update_partial_unload_failure_restores_old_service(v2_root):
    class PartialUnload(UpdateMac):
        failed = False
        def unload(self, label):
            super().unload(label)
            if not self.failed:
                self.failed = True
                raise RuntimeError('partial unload')
    before = update_bytes(v2_root)
    adapter = PartialUnload(v2_root)
    with pytest.raises(RuntimeError, match='partial unload'):
        install.update(adapter=adapter, **v2_root)
    assert_update_restored(v2_root, before, adapter)


def test_update_plist_write_failure_restores_exact_old_bytes(v2_root, monkeypatch):
    before = update_bytes(v2_root)
    adapter = UpdateMac(v2_root)
    atomic = install._atomic
    def fail_once(path, content, mode=0o600):
        if path == adapter.plist and content != before[path]:
            raise OSError('injected plist write')
        return atomic(path, content, mode)
    monkeypatch.setattr(install, '_atomic', fail_once)
    with pytest.raises(OSError, match='injected plist write'):
        install.update(adapter=adapter, **v2_root)
    assert_update_restored(v2_root, before, adapter)


@pytest.mark.parametrize('rollback_failure', ['register_new', 'start', 'health', 'unhealthy'])
def test_update_reports_failed_old_service_recovery_without_rewriting_user_data(v2_root, rollback_failure):
    before = update_bytes(v2_root)
    adapter = UpdateMac(v2_root)
    def fail(stage):
        if stage == 'started':
            adapter.fail = rollback_failure
            raise RuntimeError('cutover fault')
    with pytest.raises(install.InstallError, match='update rollback failed:.*original: cutover fault'):
        install.update(adapter=adapter, fault=fail, **v2_root)
    assert all(path.read_bytes() == content for path, content in before.items())
    assert Path(plistlib.loads(before[adapter.plist])['ProgramArguments'][0]).is_file()


@pytest.mark.parametrize('fail_cutover', [False, True])
def test_update_waits_for_stopping_service_and_hands_off_both_locks(v2_root, fail_cutover):
    import threading
    adapter = UpdateMac(v2_root)
    before = update_bytes(v2_root)
    held = []
    for path in (v2_root['support'] / 'serve.lock', v2_root['root'] / 'tick.lock'):
        stream = path.open('a')
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held.append(stream)
    class SlowStop(UpdateMac):
        def unload(self, label):
            super().unload(label)
            threading.Timer(0.1, lambda: [stream.close() for stream in held]).start()
    adapter = SlowStop(v2_root, fail='unhealthy' if fail_cutover else None)
    try:
        if fail_cutover:
            with pytest.raises(install.InstallError, match='authenticated status'):
                install.update(adapter=adapter, **v2_root)
            assert_update_restored(v2_root, before, adapter)
        else:
            assert 'Service is healthy' in install.update(adapter=adapter, **v2_root)
    finally:
        for stream in held:
            stream.close()


def test_update_dry_run_never_probes_adapter_or_changes_files(v2_root):
    before = tree_bytes(v2_root['home'])
    adapter = UpdateMac(v2_root)
    assert 'not probed in dry-run' in install.update(dry_run=True, adapter=adapter, **v2_root)
    assert adapter.calls == []
    assert tree_bytes(v2_root['home']) == before


def test_update_refuses_uninstalled_and_v1_roots_without_platform_operations(old_root, tmp_path):
    adapter = FakeMac()
    with pytest.raises(install.InstallError, match='v1 installation: use quietclerk upgrade'):
        install.update(adapter=adapter, **old_root)
    with pytest.raises(install.InstallError, match='not installed: use quietclerk install'):
        install.update(home=tmp_path / 'empty-home', source=SOURCE, adapter=adapter)
    assert adapter.calls == []
    assert not (tmp_path / 'empty-home').exists()


def test_update_requires_registered_v2_service(v2_root):
    before = update_bytes(v2_root)
    adapter = UpdateMac(v2_root)
    adapter.labels.clear()
    with pytest.raises(install.InstallError, match='not installed: service is not registered'):
        install.update(adapter=adapter, **v2_root)
    assert all(path.read_bytes() == content for path, content in before.items())
    assert adapter.calls == [('registration_probe', install.LABEL)]


@pytest.mark.parametrize('invalid', ['missing-settings', 'unknown-settings', 'corrupt-db',
                                     'unknown-schema', 'missing-plist', 'corrupt-plist', 'xml-plist',
                                     'plist-command', 'plist-root', 'settings-root'])
def test_update_invalid_or_mismatched_state_fails_closed(v2_root, invalid):
    root = v2_root['root']
    adapter = UpdateMac(v2_root)
    if invalid == 'missing-settings':
        (root / 'settings.toml').unlink()
    elif invalid == 'unknown-settings':
        with (root / 'settings.toml').open('a') as stream:
            stream.write('\nunknown = "$(touch /never-execute)"\n')
    elif invalid == 'corrupt-db':
        (root / 'state.sqlite3').write_bytes(b'not SQLite')
    elif invalid == 'unknown-schema':
        with sqlite3.connect(root / 'state.sqlite3') as con:
            con.execute("UPDATE meta SET value='99' WHERE key='schema_version'")
    elif invalid == 'missing-plist':
        adapter.plist.unlink()
    elif invalid == 'corrupt-plist':
        adapter.plist.write_bytes(b'not plist')
    elif invalid == 'xml-plist':
        adapter.plist.write_bytes(b'<?xml version="1.0"?><plist><dict>')
    elif invalid.startswith('plist-'):
        service = plistlib.loads(adapter.plist.read_bytes())
        if invalid == 'plist-command':
            service['ProgramArguments'] = ['sh', '-c', 'touch /never-execute']
        else:
            service['WorkingDirectory'] = str(root / 'other')
        adapter.plist.write_bytes(plistlib.dumps(service))
    else:
        text = (root / 'settings.toml').read_text().replace(str(root), str(root / 'other'))
        (root / 'settings.toml').write_text(text)
    before = tree_bytes(v2_root['home'])
    with pytest.raises(install.InstallError):
        install.update(adapter=adapter, **v2_root)
    assert adapter.calls == []
    assert tree_bytes(v2_root['home']) == before


def test_update_cli_dispatch_and_errors(monkeypatch, capsys, tmp_path):
    calls = []
    monkeypatch.setattr(install, 'update', lambda **kwargs: calls.append(kwargs) or 'planned update')
    assert cli.main(['update', '--root', str(tmp_path), '--source', str(SOURCE), '--dry-run']) == 0
    assert calls[0]['root'] == tmp_path and calls[0]['source'] == SOURCE
    assert calls[0]['dry_run'] is True
    def error(**kwargs):
        raise install.InstallError('not installed: use install')
    monkeypatch.setattr(install, 'update', error)
    assert cli.main(['update']) == 1
    assert 'QuietClerk update failed: not installed: use install' in capsys.readouterr().err


def test_update_checks_wal_state_without_changing_database_or_sidecars(v2_root):
    database = v2_root['root'] / 'state.sqlite3'
    script = """import os, sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute('PRAGMA journal_mode=WAL')
con.execute('PRAGMA wal_autocheckpoint=0')
con.execute("UPDATE meta SET value='99' WHERE key='schema_version'")
con.commit()
os._exit(0)
"""
    subprocess.run([sys.executable, '-c', script, str(database)], check=True)
    assert database.with_name(database.name + '-wal').is_file()
    before = tree_bytes(v2_root['home'])
    adapter = UpdateMac(v2_root)
    with pytest.raises(install.InstallError, match='unsupported database schema'):
        install.update(dry_run=True, adapter=adapter, **v2_root)
    assert adapter.calls == []
    assert tree_bytes(v2_root['home']) == before


def test_update_defaults_to_current_checkout_from_installed_cli(v2_root, monkeypatch, tmp_path):
    monkeypatch.chdir(SOURCE)
    monkeypatch.setattr(install, '__file__', str(tmp_path / 'site-packages/quietclerk/install.py'))
    options = {key: value for key, value in v2_root.items() if key != 'source'}
    adapter = UpdateMac(v2_root)
    assert 'Service is healthy' in install.update(adapter=adapter, **options)


def test_update_keeps_only_immediate_previous_managed_environment(v2_root):
    root = v2_root['root']
    original = set((root / '.venvs').iterdir())
    install.update(adapter=UpdateMac(v2_root), **v2_root)
    intermediate = set((root / '.venvs').iterdir()) - original
    install.update(adapter=UpdateMac(v2_root), **v2_root)
    remaining = set((root / '.venvs').iterdir())
    assert len(remaining) == 2
    assert not remaining & original
    assert intermediate <= remaining
