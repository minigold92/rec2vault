import json
import os
import subprocess
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import pytest

from quietclerk import config, store


def test_imports_leave_empty_home_untouched_without_qc_environment(tmp_path):
    """Import-only input must not initialize a root, settings, locks or caches."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith('QC_')}
    environment['HOME'] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, '-c',
         'import quietclerk.cli, quietclerk.serve, quietclerk.config, '
         'quietclerk.intake, quietclerk.providers'],
        env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_precedence_file_values_and_environment_locks(tmp_path):
    path = tmp_path / 'settings.toml'
    path.write_text('root="' + str(tmp_path / 'file-root') + '"\nmin_duration_sec=30\n'
                    'stable_sec=5\n[language]\nmode="en"\n[providers]\nlocal_only=false\n')
    settings = config.load(path, {'QC_ROOT': str(tmp_path / 'env-root'), 'QC_MIN_DURATION_SEC': '90',
                                  'QC_LANGUAGE': 'ko', 'QC_LOCAL_ONLY': 'true'})
    assert settings.root == tmp_path / 'env-root'
    assert settings.get('inbox') == str(tmp_path / 'env-root' / 'inbox')
    assert settings.get('min_duration_sec') == 90
    assert settings.get('stable_sec') == 5
    assert settings.get('language.mode') == 'ko'
    assert settings.get('providers.local_only') is True
    assert settings.file_values['min_duration_sec'] == 30
    assert settings.environment_keys == frozenset(('root', 'min_duration_sec', 'language.mode', 'providers.local_only'))
    assert settings.get('retention.wav_days') == 7


@pytest.mark.parametrize('content', ['stable_sec=true', 'min_duration_sec="5"', 'root=1', 'extra=1',
                                    'since="not a date"', '[language]\nmode="fr"',
                                    '[providers]\norder=["agy"]', '[providers]\nlocal_only="false"',
                                    '[providers.consent]\ncodex=["audio"]',
                                    '[server]\nport=70000', '[retention]\nwav_days=-1'])
def test_file_types_are_strict(tmp_path, content):
    path = tmp_path / 'settings.toml'
    path.write_text(content)
    with pytest.raises(config.SettingsError):
        config.load(path, {})


@pytest.mark.parametrize('key,value', [('QC_MIN_DURATION_SEC', 'abc'), ('QC_STABLE_SEC', '-1'),
                                      ('QC_LOCAL_ONLY', '1'), ('QC_PORT', '0'), ('QC_LANGUAGE', 'fr')])
def test_environment_types_are_strict(tmp_path, key, value):
    with pytest.raises(config.SettingsError):
        config.load(tmp_path / 'missing.toml', {key: value})


def test_run_snapshot_changes_only_on_next_claim(tmp_path):
    path = tmp_path / 'settings.toml'
    path.write_text(f'root="{tmp_path}"\noutput="{tmp_path}/first"\n')
    first = config.load(path, {})
    con = store.connect(tmp_path / 'state.sqlite3')
    row = store.add_job(con, '20261109-101500-12345678', '1' * 64, 'sample.m4a', '/synthetic/source.m4a', 600)
    running = store.claim(con, 'boot', first)
    path.write_text(f'root="{tmp_path}"\noutput="{tmp_path}/second"\n')
    second = config.load(path, {})
    assert first.get('output') == str(tmp_path / 'first')
    snapshot = json.loads(con.execute('SELECT settings_json FROM runs').fetchone()[0])
    assert snapshot['output'] == str(tmp_path / 'first')
    store.fail(con, row['job_id'], running['active_run_id'], 'boot', 'retry')
    store.request_process(con, row['job_id'])
    running = store.claim(con, 'boot', second)
    snapshot = json.loads(con.execute('SELECT settings_json FROM runs WHERE run_id=?', (running['active_run_id'],)).fetchone()[0])
    assert snapshot['output'] == str(tmp_path / 'second')
    con.close()


def test_old_environment_never_aliases(tmp_path):
    settings = config.load(tmp_path / 'missing', {'QC_ROOT': str(tmp_path),
                                                'REC_ROOT': '/must-not-read', 'REC_MIN_DURATION_SEC': '0'})
    assert settings.root == tmp_path
    assert settings.get('min_duration_sec') == 300


def test_installation_defaults_survive_reload_clock_and_locale_change(tmp_path, monkeypatch):
    class FirstClock(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 11, 9, 10, 0)

    class LaterClock(FirstClock):
        @classmethod
        def now(cls):
            return cls(2026, 11, 10, 12, 0)

    env = {'QC_ROOT': str(tmp_path)}
    monkeypatch.setattr(config, 'datetime', FirstClock)
    monkeypatch.setattr(config.locale, 'getlocale', lambda *args: ('ko_KR', 'UTF-8'))
    first = config.load(tmp_path / 'settings.toml', env)
    monkeypatch.setattr(config, 'datetime', LaterClock)
    monkeypatch.setattr(config.locale, 'getlocale', lambda *args: ('en_US', 'UTF-8'))
    def no_new_socket():
        raise AssertionError('installation port must not be reallocated')
    monkeypatch.setattr(config.socket, 'socket', no_new_socket)
    second = config.load(tmp_path / 'settings.toml', env)
    assert first.get('since') == second.get('since') == '2026-11-09 10:00'
    assert first.get('server.port') == second.get('server.port')
    assert first.get('language.default') == second.get('language.default') == 'ko'
    assert first.get('ui.language') == second.get('ui.language') == 'ko'
    overridden = config.load(tmp_path / 'settings.toml', {**env, 'QC_SINCE': '1970-01-01 00:00', 'QC_PORT': '8001'})
    assert overridden.get('since') == '1970-01-01 00:00' and overridden.get('server.port') == 8001
    assert json.loads((tmp_path / 'installation.json').read_text())['since'] == '2026-11-09 10:00'


def test_concurrent_installation_initialization_uses_one_snapshot(tmp_path):
    def load(_):
        return config.load(tmp_path / 'settings.toml', {'QC_ROOT': str(tmp_path)}).snapshot()
    with ThreadPoolExecutor(max_workers=4) as pool:
        snapshots = list(pool.map(load, range(4)))
    assert all(value == snapshots[0] for value in snapshots)
    assert not list(tmp_path.glob('*.part'))


def test_invalid_installation_defaults_are_not_silently_recomputed(tmp_path):
    (tmp_path / 'installation.json').write_text('{"since":"broken"}')
    with pytest.raises(config.SettingsError, match='invalid persisted defaults'):
        config.load(tmp_path / 'settings.toml', {'QC_ROOT': str(tmp_path)})
    assert (tmp_path / 'installation.json').read_text() == '{"since":"broken"}'


def test_provider_contract_settings_and_defaults(tmp_path):
    path = tmp_path / 'settings.toml'
    env = {'QC_ROOT': str(tmp_path)}
    defaults = config.load(path, env)
    assert defaults.get('providers.allow_unverified') == []
    assert defaults.get('providers.ollama.endpoint') == 'http://127.0.0.1:11434'
    assert defaults.get('providers.omp.profile') == 'quietclerk'
    path.write_text('[providers]\norder=["omp","ollama"]\nallow_unverified=["omp"]\n'
                    '[providers.consent]\nomp=["transcript"]\n[providers.ollama]\n'
                    'endpoint="http://localhost:11435"\n[providers.omp]\nprofile="isolated"\n')
    settings = config.load(path, env)
    assert settings.get('providers.order') == ['omp', 'ollama']
    assert settings.get('providers.allow_unverified') == ['omp']
    assert settings.get('providers.consent') == {'omp': ['transcript']}
    assert settings.get('providers.ollama.endpoint') == 'http://localhost:11435'
    assert settings.get('providers.omp.profile') == 'isolated'


@pytest.mark.parametrize('content', [
    '[providers]\norder=["agy"]', '[providers]\nallow_unverified=["agy"]',
    '[providers.consent]\nagy=["transcript"]', '[providers.agy]\nmodel="old"',
    '[providers.agy]',
])
def test_agy_settings_explain_security_removal(tmp_path, content):
    path = tmp_path / 'settings.toml'
    path.write_text(content)
    with pytest.raises(config.SettingsError, match='agy was removed.*tool execution'):
        config.load(path, {'QC_ROOT': str(tmp_path)})


@pytest.mark.parametrize('content', [
    '[providers]\nallow_unverified=["omp","omp"]', '[providers]\nallow_unverified=["unknown"]',
    '[providers]\nallow_unverified=[{}]', '[providers.ollama]\nendpoint=123',
    '[providers.omp]\nprofile=true',
])
def test_provider_contract_settings_reject_invalid_types_and_names(tmp_path, content):
    path = tmp_path / 'settings.toml'
    path.write_text(content)
    with pytest.raises(config.SettingsError):
        config.load(path, {'QC_ROOT': str(tmp_path)})


def test_codex_speed_accepts_only_standard_or_fast(tmp_path):
    from quietclerk import config
    assert config._validate('providers.codex.speed', 'fast') == 'fast'
    with pytest.raises(config.SettingsError):
        config._validate('providers.codex.speed', 'turbo')
