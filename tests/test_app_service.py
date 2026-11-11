"""Synthetic launchd app lifecycle; no real user paths or platform calls."""
import json
import plistlib
from pathlib import Path

import pytest

from quietclerk import cli, install
from test_install import FakeMac, UpdateMac

SOURCE = Path(__file__).resolve().parent.parent


@pytest.fixture
def app_paths(tmp_path):
    home = tmp_path / 'home & literal'
    paths = {'home': home, 'root': home / 'QuietClerk',
             'support': home / 'Library/Application Support/QuietClerk',
             'source': SOURCE, 'agents': home / 'Library/LaunchAgents'}
    adapter = FakeMac(registered=())
    install.run(adapter=adapter, environ={}, app_install=True, **paths)
    return paths, adapter


def lifecycle(paths, adapter, action):
    return install.login_service(action, support=paths['support'], home=paths['home'], adapter=adapter)


def test_app_install_keeps_python_launch_and_adds_private_ownership_record(app_paths):
    paths, _ = app_paths
    record = install.read_app_installation(paths['support'] / install.APP_RECORD)
    plist = paths['agents'] / (install.LABEL + '.plist')
    service = plistlib.loads(plist.read_bytes())
    assert service['ProgramArguments'][0] == record['python']
    assert service['ProgramArguments'][1:3] == ['-m', 'quietclerk.cli']
    assert service['AssociatedBundleIdentifiers'] == ['io.github.minigold92.quietclerk']
    assert record['manager'] == 'app' and record['label'] == install.LABEL
    assert (paths['support'] / 'service.plist').read_bytes() == plist.read_bytes()
    assert (paths['support'] / install.APP_RECORD).stat().st_mode & 0o777 == 0o600
    assert 'helper' not in record


def test_disable_removes_login_registration_and_enable_checks_authenticated_status(app_paths):
    paths, adapter = app_paths
    before = lifecycle(paths, adapter, 'status')
    assert before == {'manager': 'app', 'registered': True, 'login_enabled': True}
    assert lifecycle(paths, adapter, 'unregister') == {'manager': 'app', 'registered': False, 'login_enabled': False}
    assert not (paths['agents'] / (install.LABEL + '.plist')).exists()
    assert (paths['support'] / 'service.plist').exists()
    assert lifecycle(paths, adapter, 'register') == before
    assert ('health', None) in adapter.calls


def test_failed_enable_restores_disabled_state(app_paths):
    paths, adapter = app_paths
    lifecycle(paths, adapter, 'unregister')
    adapter.fail = 'unhealthy'
    with pytest.raises(install.InstallError, match='authenticated status'):
        lifecycle(paths, adapter, 'register')
    assert not (paths['agents'] / (install.LABEL + '.plist')).exists()
    assert not adapter.registered(install.LABEL)


def test_manual_serve_lock_blocks_a_second_engine(app_paths):
    paths, adapter = app_paths
    lifecycle(paths, adapter, 'unregister')
    with install._lock(paths['support'] / 'serve.lock'):
        with pytest.raises(install.InstallError, match='lock is held'):
            lifecycle(paths, adapter, 'register')
    assert not (paths['agents'] / (install.LABEL + '.plist')).exists()


def test_app_update_refreshes_record_and_saved_definition(app_paths):
    paths, _ = app_paths
    before = install.read_app_installation(paths['support'] / install.APP_RECORD)
    adapter = UpdateMac(paths)
    install.update(adapter=adapter, **paths)
    after = install.read_app_installation(paths['support'] / install.APP_RECORD)
    assert before['python'] != after['python']
    assert Path(before['python']).is_file() and Path(after['python']).is_file()
    assert (paths['support'] / 'service.plist').read_bytes() == (paths['agents'] / (install.LABEL + '.plist')).read_bytes()
    lifecycle(paths, adapter, 'unregister')
    lifecycle(paths, adapter, 'register')
    assert adapter.python == after['python']


@pytest.mark.parametrize('stage', ['plist', 'registered', 'started', 'healthy'])
def test_update_failure_restores_app_metadata_and_service(app_paths, stage):
    paths, _ = app_paths
    tracked = [paths['support'] / name for name in (install.APP_RECORD, 'service.plist')]
    before = [path.read_bytes() for path in tracked]
    def fail(point):
        if point == stage:
            raise RuntimeError('synthetic failure')
    adapter = UpdateMac(paths)
    with pytest.raises(RuntimeError, match='synthetic failure'):
        install.update(adapter=adapter, fault=fail, **paths)
    assert [path.read_bytes() for path in tracked] == before
    assert adapter.registered(install.LABEL)


@pytest.mark.parametrize('action', ['status', 'register', 'unregister'])
def test_existing_cli_installation_is_read_only(tmp_path, action):
    home = tmp_path / 'home'
    agents = home / 'Library/LaunchAgents'
    agents.mkdir(parents=True)
    plist = agents / (install.LABEL + '.plist')
    content = plistlib.dumps({'Label': install.LABEL})
    plist.write_bytes(content)
    adapter = FakeMac(registered=(install.LABEL,))
    result = install.login_service(action, home=home, support=home / 'support', adapter=adapter)
    assert result == {'manager': 'cli', 'registered': True, 'login_enabled': True}
    assert plist.read_bytes() == content and not (home / 'support').exists()
    assert not adapter.calls


def test_cli_replacement_wins_over_stale_app_metadata(app_paths):
    paths, adapter = app_paths
    plist = paths['agents'] / (install.LABEL + '.plist')
    plist.write_bytes(plistlib.dumps({'Label': install.LABEL, 'ProgramArguments': ['/another/python']}))
    assert lifecycle(paths, adapter, 'unregister')['manager'] == 'cli'
    assert adapter.registered(install.LABEL)


def test_record_reader_rejects_symlink_and_world_readable_metadata(app_paths):
    paths, _ = app_paths
    path = paths['support'] / install.APP_RECORD
    path.chmod(0o644)
    with pytest.raises(install.InstallError, match='0600'):
        install.read_app_installation(path)
    path.chmod(0o600)
    link = paths['support'] / 'linked.json'
    link.symlink_to(path)
    with pytest.raises(install.InstallError):
        install.read_app_installation(link)


def test_cli_dispatches_lifecycle_json_and_explains_failures(monkeypatch, capsys):
    monkeypatch.setattr(install, 'login_service', lambda action, **kw: {'manager': 'app', 'registered': False, 'login_enabled': False})
    assert cli.main(['login-service', 'status']) == 0
    assert json.loads(capsys.readouterr().out)['manager'] == 'app'
    def fail(*args, **kwargs):
        raise install.InstallError('service definition changed')
    monkeypatch.setattr(install, 'login_service', fail)
    assert cli.main(['login-service', 'register']) == 1
    assert 'service definition changed' in capsys.readouterr().err
