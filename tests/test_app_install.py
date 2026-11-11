"""A1 synthetic adversarial inputs. Never touch real user paths or launchd."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from types import SimpleNamespace

import pytest

from quietclerk import app_install as app, install, models, procs
from test_app_service import app_paths  # noqa: F401
from test_install import UpdateMac


def payload(tmp_path):
    resources = tmp_path / 'resources'
    resources.mkdir()
    manifest = {'schema': 1, 'version': '0.1.0', 'wheel': 'quietclerk-0.1.0-py3-none-any.whl'}
    for name, key in ((manifest['wheel'], 'wheel_sha256'), ('requirements.txt', 'requirements_sha256'),
                      ('build-inputs.json', 'inputs_sha256'), ('bootstrap-requirements.txt', 'bootstrap_sha256')):
        (resources / name).write_bytes(name.encode())
        manifest[key] = hashlib.sha256(name.encode()).hexdigest()
    (resources / 'manifest.json').write_text(json.dumps(manifest))
    return resources, manifest


@pytest.mark.parametrize('name', ['quietclerk-0.1.0-py3-none-any.whl', 'requirements.txt', 'build-inputs.json'])
def test_damaged_bundle_stops_before_environment_creation(tmp_path, name):
    resources, _ = payload(tmp_path)
    app.load_payload(resources)
    (resources / name).write_bytes(b'damaged')
    with pytest.raises(install.InstallError, match='checksum'):
        app.AppAdapter(resources, tmp_path)


@pytest.mark.parametrize('wheel', ['../outside.whl', '/outside.whl', '', 'engine.py'])
def test_manifest_cannot_escape_bundle(tmp_path, wheel):
    resources, manifest = payload(tmp_path)
    manifest['wheel'] = wheel
    (resources / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(install.InstallError, match='manifest'):
        app.load_payload(resources)


@pytest.mark.parametrize('machine,release,reason', [
    ('x86_64', '14.0', 'Apple Silicon'),
    ('arm64', '13.9', 'macOS 14'),
])
def test_platform_fails_before_network(tmp_path, monkeypatch, machine, release, reason):
    monkeypatch.setattr(app.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('network must not be reached'))
    with pytest.raises(install.InstallError, match=reason):
        app.preflight(tmp_path, system='Darwin', machine=machine, release=release)


def test_network_disconnection_is_retryable_before_install(tmp_path, monkeypatch):
    def offline(*args, **kwargs):
        raise OSError('network down')
    monkeypatch.setattr(app.urllib.request, 'urlopen', offline)
    with pytest.raises(install.InstallError, match='internet connection'):
        app.preflight(tmp_path, system='Darwin', machine='arm64', release='14.0')
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('location', ['QuietClerk', 'Library/Application Support/QuietClerk', 'QuietClerk/.venvs'])
def test_symlinked_root_support_and_environment_are_rejected(tmp_path, location):
    outside = tmp_path / 'outside'
    outside.mkdir()
    link = tmp_path / 'home' / location
    link.parent.mkdir(parents=True)
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(install.InstallError, match='symbolic links'):
        app.reconcile(tmp_path, tmp_path, home=tmp_path / 'home', consent=True)
    assert list(outside.iterdir()) == []


def test_cli_coexistence_never_preflights_or_installs(tmp_path, monkeypatch):
    resources, _ = payload(tmp_path)
    monkeypatch.setattr(install, 'login_service', lambda *a, **k: {'manager': 'cli', 'registered': True, 'login_enabled': True})
    calls = []
    monkeypatch.setattr(app, 'authenticated_status', lambda support: calls.append('authenticated'))
    monkeypatch.setattr(app, 'preflight', lambda *a: pytest.fail('CLI engine must not be installed'))
    app.reconcile(resources, tmp_path, home=tmp_path / 'home', consent=True)
    assert calls == ['authenticated']


def test_pinned_dependencies_and_app_tools_do_not_change_cli_adapter(tmp_path, monkeypatch):
    resources, manifest = payload(tmp_path)
    tools = tmp_path / 'tools'
    tools.mkdir()
    for name in ('uv', 'ffmpeg', 'ffprobe'):
        (tools / name).write_bytes(b'signed-binary')
    adapter = app.AppAdapter(resources, tools)
    calls = []
    def command(argv, **kwargs):
        calls.append(argv)
        if argv[1] == 'venv':
            (Path(argv[-1]) / 'bin').mkdir(parents=True)
    monkeypatch.setattr(adapter, 'command', command)
    venv = tmp_path / 'venv'
    adapter.prepare_environment(resources / manifest['wheel'], venv)
    assert '--require-hashes' in calls[1] and '--only-binary' in calls[1]
    assert calls[1][calls[1].index('--python-platform') + 1] == 'aarch64-apple-darwin'
    assert '--no-deps' in calls[2]
    assert (venv / 'bin/ffmpeg').read_bytes() == b'signed-binary'
    assert install.MacAdapter.prepare_environment is not app.AppAdapter.prepare_environment


def test_engine_update_checks_local_models_without_downloading(tmp_path, monkeypatch):
    resources, _ = payload(tmp_path)
    adapter = app.AppAdapter(resources, tmp_path, download_models=False)
    calls = []
    monkeypatch.setattr(adapter, 'command', lambda argv: calls.append(argv))
    adapter.check_models(tmp_path, tmp_path)
    assert len(calls) == 1 and 'model_snapshot' in calls[0][-1]
    assert 'prefetch' not in repr(calls)


def test_model_download_restart_reuses_completed_files_and_reports_each_model(tmp_path, monkeypatch, capsys):
    # The library owns range requests/partial files. We must not clear its cache
    # or request force_download; a resumed call gets the same snapshot options.
    import types
    downloaded = []
    calls = []
    repos = list(models.MODELS.values())
    interrupted = [True]
    def snapshot(repo, **kwargs):
        assert not kwargs.get('force_download', False)
        calls.append(repo)
        cached = tmp_path / str(repos.index(repo))
        if interrupted[0] and repo == repos[1]:
            interrupted[0] = False
            raise OSError('disconnected')
        if not cached.exists():
            cached.write_bytes(b'completed-model')
            downloaded.append(repo)
        return str(cached)
    monkeypatch.setitem(sys.modules, 'huggingface_hub', types.SimpleNamespace(snapshot_download=snapshot))
    monkeypatch.setitem(sys.modules, 'huggingface_hub.constants', types.SimpleNamespace(HF_HUB_CACHE=str(tmp_path)))
    monkeypatch.setattr(models, 'download_sizes', lambda: dict.fromkeys(repos, 1))
    monkeypatch.setattr(models.shutil, 'disk_usage', lambda path: SimpleNamespace(free=10_000_000_000))
    with pytest.raises(OSError):
        models.prefetch(app_progress=True)
    models.prefetch(app_progress=True)
    assert downloaded == repos
    assert calls.count(repos[0]) == 2
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert any('4/4 complete' in event['en'] for event in events)


def test_killed_first_install_recovers_private_journal_before_retry(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    root = home / 'QuietClerk'
    support = home / 'Library/Application Support/QuietClerk'
    root.mkdir(parents=True)
    support.mkdir(parents=True)
    code = ('import os,signal; from pathlib import Path; from quietclerk.app_install import begin_journal; '
            'h=Path(os.environ["TEST_HOME"]); r=h/"QuietClerk"; s=h/"Library/Application Support/QuietClerk"; '
            'begin_journal(h,s,r,False); (r/"settings.toml").write_text("incomplete"); '
            'os.kill(os.getpid(),signal.SIGKILL)')
    child = subprocess.run([sys.executable, '-c', code], env=os.environ | {'TEST_HOME': str(home)}, check=False)
    assert child.returncode == -signal.SIGKILL
    monkeypatch.setattr(install, 'login_service', lambda *a, **k: {'manager': None})
    adapter = SimpleNamespace(unload=lambda label: None)
    app.recover(home, support, adapter)
    assert not (root / 'settings.toml').exists()
    assert not (support / 'app-transaction.json').exists()


def test_changed_app_engine_waits_for_job_then_uses_rollback_update(app_paths, tmp_path, monkeypatch):
    paths, original = app_paths
    resources, manifest = payload(tmp_path)
    login_service = install.login_service
    monkeypatch.setattr(install, 'login_service', lambda action, **kw: login_service(action, adapter=original, **kw))
    monkeypatch.setattr(app, 'preflight', lambda home: None)
    calls = []
    running = [True, False]
    def status(support, action=None):
        calls.append(action or 'status')
        return {'paused': False, 'current_job': ({'id': 'fictional'} if '/api/pause' in calls and action is None and running and running.pop(0) else None)}
    monkeypatch.setattr(app, 'authenticated_status', status)
    monkeypatch.setattr(app.time, 'sleep', lambda seconds: calls.append('wait'))
    before = install.read_app_installation(paths['support'] / install.APP_RECORD)['python']
    real_run = subprocess.run
    def run(command, **kwargs):
        if command[0] == 'git':
            return real_run(command, **kwargs)
        calls.append('update')
        assert 'update' in command and '--app-manifest' in command
        install.update(adapter=UpdateMac(paths), **paths)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(app.subprocess, 'run', run)
    app.reconcile(resources, tmp_path, home=paths['home'], consent=False)
    after = install.read_app_installation(paths['support'] / install.APP_RECORD)['python']
    assert before != after and Path(before).is_file()
    assert calls.index('/api/pause') < calls.index('wait') < calls.index('update') < calls.index('/api/resume')
    assert json.loads((paths['support'] / 'app-engine.json').read_text())['requirements_sha256'] == manifest['requirements_sha256']


def test_media_tool_override_is_explicit_and_absolute(monkeypatch):
    monkeypatch.setenv('QC_FFMPEG', 'relative/ffmpeg')
    with pytest.raises(ValueError, match='absolute'):
        procs.run(['ffmpeg', '-version'])


def test_lgpl_build_inputs_are_fixed_and_minimal():
    inputs = json.loads((Path(__file__).resolve().parent.parent / 'app/build-inputs.json').read_text())
    ffmpeg = inputs['ffmpeg']
    assert len(ffmpeg['sha256']) == 64 and ffmpeg['url'].startswith('https://ffmpeg.org/releases/')
    assert '--disable-autodetect' in ffmpeg['configure']
    assert '--enable-protocol=file' in ffmpeg['configure']
    assert not any('gpl' in arg or 'nonfree' in arg for arg in ffmpeg['configure'])


def test_wizard_checks_app_tools_without_homebrew(tmp_path, monkeypatch):
    from quietclerk.server.integrations import checks
    monkeypatch.setenv('PATH', str(tmp_path / 'empty-path'))
    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **k: b'17179869184')
    for name in ('uv', 'ffmpeg'):
        tool = tmp_path / name
        tool.write_bytes(b'packaged-tool')
        tool.chmod(0o700)
        monkeypatch.setenv('QC_' + name.upper(), str(tool))
    result = checks(tmp_path)
    assert result['ffmpeg']['installed'] and result['uv']['installed']


@pytest.mark.parametrize('command', ['install', 'upgrade', 'update'])
def test_app_packaging_options_cannot_modify_cli_owned_service(tmp_path, monkeypatch, command):
    from quietclerk.cli import main
    monkeypatch.setattr(install, 'login_service', lambda *a, **k: {'manager': 'cli'})
    resources, manifest = payload(tmp_path)
    args = [command, '--source', str(resources / manifest['wheel']),
            '--app-manifest', str(resources / 'manifest.json'), '--app-tools', str(tmp_path)]
    assert main(args) == 1


def test_uv_uses_macos14_wheels_even_on_a_newer_host(tmp_path, monkeypatch):
    resources, _ = payload(tmp_path)
    adapter = app.AppAdapter(resources, tmp_path)
    calls = []
    monkeypatch.setattr(app.subprocess, 'run', lambda argv, **kw: calls.append(kw) or SimpleNamespace(returncode=0))
    adapter.command(['/packaged/uv', '--version'])
    assert calls[0]['env']['MACOSX_DEPLOYMENT_TARGET'] == '14.0'


def test_bootstrap_yaml_uses_the_same_reviewed_hash_pins():
    from scripts.prepare_app import bootstrap_lock
    lock = (Path(__file__).parents[1] / 'app/engine-requirements.txt').read_text()
    bootstrap = bootstrap_lock(lock)
    assert bootstrap.startswith('pyyaml==') and '--hash=sha256:' in bootstrap
    assert bootstrap.strip() in lock and '\\nnumpy==' not in bootstrap
    with pytest.raises(RuntimeError, match='PyYAML'):
        bootstrap_lock('unrelated==1\\n')
