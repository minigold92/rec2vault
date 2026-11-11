"""App-only packaging policy, built on the existing rollback installer.

No GUI, plist or launchd implementation is duplicated in Rust. This module also
runs in the wheel-only bootstrap environment, so imports stay standard-library.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import stat
import subprocess
import sys
import time
import urllib.request

from . import install


def stage(ko, en):
    print(json.dumps({'ko': ko, 'en': en}), flush=True)


def safe_path(path):
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise install.InstallError('symbolic links are not allowed in app installation paths')
        if parent.exists() and parent.stat().st_uid not in (os.getuid(), 0):
            raise install.InstallError('app installation path belongs to another user')
    return path


def load_payload(resources, source=None):
    resources = Path(resources)
    manifest = json.loads((resources / 'manifest.json').read_text())
    wheel_name = manifest.get('wheel', '')
    if manifest.get('schema') != 1 or Path(wheel_name).name != wheel_name or not wheel_name.endswith('.whl'):
        raise install.InstallError('invalid bundled engine manifest')
    wheel = resources / wheel_name
    for path, key in ((wheel, 'wheel_sha256'), (resources / 'requirements.txt', 'requirements_sha256'),
                      (resources / 'build-inputs.json', 'inputs_sha256'),
                      (resources / 'bootstrap-requirements.txt', 'bootstrap_sha256')):
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest.get(key):
            raise install.InstallError('bundled engine resource checksum mismatch')
    if source is not None and Path(source).resolve() != wheel.resolve():
        raise install.InstallError('app source must match the bundled engine wheel')
    return manifest, wheel


def preflight(home, *, system=None, machine=None, release=None, network=True):
    if (system or platform.system()) != 'Darwin' or (machine or platform.machine()) != 'arm64':
        raise install.InstallError('Apple Silicon이 필요합니다. / An Apple Silicon Mac is required.')
    if int((release or platform.mac_ver()[0]).split('.')[0]) < 14:
        raise install.InstallError('macOS 14 이상이 필요합니다. / macOS 14 or later is required.')
    safe_path(install.SUPPORT if home == Path.home() else home / 'Library/Application Support/QuietClerk')
    safe_path(home / 'QuietClerk')
    if network:
        try:
            for url in ('https://pypi.org/simple/', 'https://huggingface.co/'):
                with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=15):
                    pass
        except OSError as exc:
            raise install.InstallError('인터넷 연결을 확인하고 다시 시도하세요. / Check your internet connection and retry.') from exc


def authenticated_status(support, action=None):
    from .bootstrap_file import read_bootstrap
    data = read_bootstrap(support)
    base = f"http://127.0.0.1:{data['port']}"
    request = urllib.request.Request(base + '/api/session', data=json.dumps({'token': data['token']}).encode(),
                                     headers={'Content-Type': 'application/json', 'Origin': base})
    with urllib.request.urlopen(request, timeout=10) as response:
        cookie = response.headers['Set-Cookie'].split(';', 1)[0]
        csrf = response.headers['X-CSRF-Token']
    try:
        if action is not None:
            request = urllib.request.Request(base + action, data=b'{}', headers={
                'Cookie': cookie, 'Origin': base, 'X-CSRF-Token': csrf, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=10):
                pass
        with urllib.request.urlopen(urllib.request.Request(base + '/api/status', headers={'Cookie': cookie}), timeout=10) as response:
            return json.load(response)
    finally:
        request = urllib.request.Request(base + '/api/logout', data=b'{}', headers={
            'Cookie': cookie, 'Origin': base, 'X-CSRF-Token': csrf, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=10):
            pass


class AppAdapter(install.MacAdapter):
    def __init__(self, resources, tools, source=None, *, download_models=True):
        super().__init__()
        self.resources = Path(resources)
        self.tools = Path(tools)
        self.manifest, self.wheel = load_payload(resources, source)
        self.download_models = download_models

    def command(self, argv, **kwargs):
        # Never print argv: health/authentication must not leak bootstrap tokens.
        kwargs.setdefault('env', os.environ | {'MACOSX_DEPLOYMENT_TARGET': '14.0'})
        result = subprocess.run(argv, check=False, **kwargs)
        if result.returncode:
            raise install.InstallError('설치 명령이 실패했습니다. 로그를 확인하세요. / Installation command failed; see the log.')
        return ''

    def prepare_environment(self, source, venv):
        stage('엔진 의존성 설치 중 (약 2GB)', 'Installing engine dependencies (~2GB)')
        uv = self.tools / 'uv'
        self.command([str(uv), 'venv', '--managed-python', '--python', '3.12', str(venv)])
        self.command([str(uv), 'pip', 'install', '--python', str(venv / 'bin/python'),
                      '--python-platform', 'aarch64-apple-darwin', '--require-hashes', '--only-binary', ':all:',
                      '-r', str(self.resources / 'requirements.txt')])
        self.command([str(uv), 'pip', 'install', '--python', str(venv / 'bin/python'), '--no-deps', str(source)])
        for name in ('uv', 'ffmpeg', 'ffprobe'):
            shutil.copy2(self.tools / name, venv / 'bin' / name)
        self.command([str(venv / 'bin/python'), '-I', '-c',
                      'import mlx.core, starlette, uvicorn, yaml, jinja2; import quietclerk.cli'])

    def check_models(self, venv, source):
        stage('없는 모델만 받습니다(최대 약 6GB)', 'Downloads only missing model files (up to about 6 GB)')
        if self.download_models:
            self.command([str(venv / 'bin/python'), '-I', '-m', 'quietclerk.models', 'prefetch', '--app-progress'])
        self.command([str(venv / 'bin/python'), '-I', '-c',
                      'from quietclerk.backends.mlx import MODELS, model_snapshot; '
                      '[model_snapshot(repo) for repo in MODELS.values()]'])
        stage('로그인 서비스 등록·인증 중', 'Registering and authenticating the login service')

    # launchctl probes and lifecycle commands need their stdout, unlike downloads.
    def registered(self, label):
        return install.MacAdapter.registered(self, label)

    def processes(self, root):
        return install.MacAdapter.processes(install.MacAdapter(), root)


def journal_paths(home, support, root, updating):
    paths = [home / 'Library/LaunchAgents' / (install.LABEL + '.plist'),
             support / install.APP_RECORD, support / 'service.plist', support / 'source.json',
             support / 'app-engine.json']
    if not updating:
        paths += [root / name for name in ('state.sqlite3', 'state.sqlite3-wal', 'state.sqlite3-shm',
                                          'state.sqlite3-journal', 'settings.toml', 'installation.json', 'installation.lock')]
    return paths


def begin_journal(home, support, root, updating):
    entries = []
    for path in journal_paths(home, support, root, updating):
        safe_path(path)
        entries.append({'path': str(path), 'content': base64.b64encode(path.read_bytes()).decode() if path.exists() else None,
                        'mode': stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600})
    paused = authenticated_status(support).get('paused', False) if updating else False
    install._atomic(support / 'app-transaction.json', json.dumps({'updating': updating, 'paused': paused, 'entries': entries}).encode())


def recover(home, support, adapter):
    journal = support / 'app-transaction.json'
    if not journal.exists():
        return
    stage('중단된 설치를 안전하게 복구 중', 'Recovering an interrupted installation')
    saved = json.loads(journal.read_text())
    root = home / 'QuietClerk'
    allowed = {str(path) for path in journal_paths(home, support, root, saved['updating'])}
    if {entry['path'] for entry in saved['entries']} != allowed:
        raise install.InstallError('invalid app recovery journal')
    if install.login_service('status', home=home, support=support)['manager'] == 'cli':
        raise install.InstallError('CLI service replaced an interrupted app installation; left unchanged')
    with install._lock(support / 'upgrade.lock'):
        adapter.unload(install.LABEL)
        with install._lock(support / 'serve.lock', wait=install.STOP_WAIT_SEC), install._lock(root / 'tick.lock', wait=install.STOP_WAIT_SEC):
            for entry in saved['entries']:
                path = safe_path(Path(entry['path']))
                if entry['content'] is None:
                    path.unlink(missing_ok=True)
                else:
                    install._atomic(path, base64.b64decode(entry['content']), entry['mode'])
        plist = home / 'Library/LaunchAgents' / (install.LABEL + '.plist')
        if saved['updating'] and plist.exists():
            adapter.register(plist)
            adapter.start(install.LABEL)
            service = plistlib.loads(plist.read_bytes())
            paths = install.Layout(root, home, root, plist.parent, support, root / 'settings.toml')
            settings = install._update_settings(paths, service)
            if not adapter.healthy(install.LABEL, support, settings, 0):
                raise install.InstallError('recovered service failed authenticated status')
            if not saved.get('paused', False):
                authenticated_status(support, '/api/resume')
        journal.unlink()


def reconcile(resources, tools, *, home=None, consent=False):
    home = Path(home or Path.home())
    support = safe_path(home / 'Library/Application Support/QuietClerk')
    root = safe_path(home / 'QuietClerk')
    safe_path(root / '.venvs')
    adapter = AppAdapter(resources, tools)
    recover(home, support, adapter)
    state = install.login_service('status', home=home, support=support)
    if state['manager'] == 'cli':
        authenticated_status(support)
        return
    identity = support / 'app-engine.json'
    target = {key: adapter.manifest[key] for key in ('version', 'wheel_sha256', 'requirements_sha256', 'inputs_sha256')}
    if state['manager'] == 'app':
        if not state['login_enabled']:
            raise install.InstallError('백그라운드 서비스를 다시 켜세요. / Enable the background service before retrying.')
        install.login_service('register', home=home, support=support)
        if identity.is_file() and json.loads(identity.read_text()) == target:
            authenticated_status(support)
            return
        record = install.read_app_installation(support / install.APP_RECORD)
        if Path(record['root']) != root:
            raise install.InstallError('app-managed root does not match the default installation')
        updating = True
    else:
        if not consent:
            raise install.InstallError('설치 동의가 필요합니다. / Installation consent is required.')
        updating = False
    stage('Mac·디스크·네트워크 점검 중', 'Checking Mac, disk space and network')
    preflight(home)
    begin_journal(home, support, root, updating)
    if updating:
        authenticated_status(support, '/api/pause')
        stage('처리 중인 작업이 끝나기를 기다리는 중', 'Waiting for the current job to finish')
        while authenticated_status(support).get('current_job') is not None:
            time.sleep(2)
    command = [sys.executable, '-I', '-m', 'quietclerk.cli', '--support', str(support)]
    command += ['update' if updating else 'install', '--source', str(adapter.wheel),
                '--app-manifest', str(Path(resources) / 'manifest.json'), '--app-tools', str(tools)]
    if not updating:
        command.append('--app-install')
    result = subprocess.run(command, check=False)
    if result.returncode:
        # Existing installer has already rolled back on ordinary exceptions.
        # SIGKILL/power-loss leaves this durable journal for the next attempt.
        recover(home, support, adapter)
        raise install.InstallError('엔진 설치에 실패했습니다. 로그를 확인하고 다시 시도하세요. / Engine installation failed; check the log and retry.')
    install.login_service('register', home=home, support=support)
    authenticated_status(support)
    if updating:
        saved = json.loads((support / 'app-transaction.json').read_text())
        if not saved.get('paused', False):
            authenticated_status(support, '/api/resume')
    install._atomic(identity, json.dumps(target).encode())
    if not updating:
        install._atomic(support / 'app-open-setup', b'pending\n')
    (support / 'app-transaction.json').unlink()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--consent', action='store_true')
    args = parser.parse_args()
    try:
        reconcile(args.resources, args.tools, consent=args.consent)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(json.dumps({'error': str(exc).splitlines()[0]}), flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
