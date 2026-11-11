#!/usr/bin/env python3
"""Opt-in real macOS session probe, not a unit test.

Requires a built signed app, a Python environment with QuietClerk's HTTP
requirements, and `cargo build --example login_service_probe --release`.
Refuses any existing engine installation. Does not touch /Applications.
The throwaway app uses ~/Applications so LaunchServices can resolve its bundle.
"""
import argparse
import json
import os
import plistlib
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from quietclerk import install

LSREGISTER = '/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister'


def command(argv, *, check=True):
    result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=90)
    if check and result.returncode:
        raise RuntimeError(f'{argv[0]} failed: {result.stderr.strip()}')
    return result


def process():
    result = command(['launchctl', 'print', f'gui/{os.getuid()}/{install.LABEL}'], check=False)
    match = re.search(r'\n\s*pid = (\d+)', result.stdout)
    return result.returncode == 0, int(match[1]) if match else None


def until(predicate, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.2)
    raise RuntimeError('probe deadline expired')


def emit(step, **values):
    print(json.dumps({'step': step, **values}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--rust-probe', type=Path, required=True)
    parser.add_argument('--replacement', type=Path)
    args = parser.parse_args()
    args.python = args.python.absolute()
    support = install.SUPPORT
    plist = Path.home() / 'Library/LaunchAgents' / (install.LABEL + '.plist')
    app = Path.home() / 'Applications/QuietClerk-S1Dev.app'
    moved = app.with_name('QuietClerk-S1Moved.app')
    default_root = Path.home() / 'QuietClerk'
    for path in (support, plist, app, moved, default_root):
        if path.exists():
            raise SystemExit(f'refusing existing path: {path}')
    if process()[0]:
        raise SystemExit('refusing existing engine registration')
    app.parent.mkdir(parents=True, exist_ok=True)
    ui = None
    adapter = install.MacAdapter()
    with tempfile.TemporaryDirectory(prefix='quietclerk-login-probe-') as temporary:
        root = Path(temporary).resolve()
        try:
            shutil.copytree(args.bundle, app)
            info_path = app / 'Contents/Info.plist'
            info = plistlib.loads(info_path.read_bytes())
            info['CFBundleIdentifier'] = 'io.github.minigold92.quietclerk.s1dev'
            info['CFBundleName'] = 'QuietClerk S1 Dev'
            info_path.write_bytes(plistlib.dumps(info))
            command(['codesign', '--force', '--deep', '--sign', '-', app])
            support.mkdir(parents=True)
            (root / 'logs').mkdir()
            (root / 'inbox').mkdir()
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            settings = root / 'settings.toml'
            settings.write_text(f'root = {json.dumps(str(root))}\n[server]\nport = {port}\n')
            paths = install.Layout(root, Path.home(), root, plist.parent, support, settings)
            data = plistlib.loads(install.service_plist(paths, args.python.parent.parent, (), app_install=True))
            data['AssociatedBundleIdentifiers'] = ['io.github.minigold92.quietclerk.s1dev']
            content = plistlib.dumps(data)
            plist.parent.mkdir(parents=True, exist_ok=True)
            install._atomic(plist, content)
            install._record_app_service(paths, plist, args.python.parent.parent)
            plist.unlink()

            def bridge(action):
                output = command([args.rust_probe, action]).stdout.strip()
                emit('rust_' + action, result=output)
                return output

            def healthy():
                return command([args.python, '-m', 'quietclerk.cli', '--support', support, 'status'], check=False).returncode == 0

            def restart():
                old = process()[1]
                assert old
                os.kill(old, signal.SIGKILL)
                new = until(lambda: pid if (pid := process()[1]) and pid != old and healthy() else None)
                return {'old_pid': old, 'new_pid': new, 'authenticated': True}

            def launch_ui(executable):
                return subprocess.Popen([str(executable)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            bridge('register')
            assert healthy()
            emit('registered', pid=process()[1], authenticated=True, program=data['ProgramArguments'][0])
            executable = app / 'Contents/MacOS/quietclerk-app'
            ui = launch_ui(executable)
            time.sleep(2)
            ui.terminate()
            ui.wait(timeout=15)
            ui = None
            assert healthy()
            emit('app_exited_engine_remains', pid=process()[1])
            emit('keepalive', **restart())
            if args.replacement:
                old_pid = process()[1]
                shutil.copy2(args.replacement, executable)
                command(['codesign', '--force', '--deep', '--sign', '-', app])
                ui = launch_ui(executable)
                time.sleep(2)
                assert process()[1] == old_pid and healthy()
                ui.terminate()
                ui.wait(timeout=15)
                ui = None
                emit('replacement_keeps_engine', pid=old_pid, authenticated=True)
                emit('replacement_keepalive', **restart())
            app.rename(moved)
            emit('relocated_keepalive', **restart())
            bridge('unregister')
            until(lambda: not process()[0])
            assert not plist.exists()
            emit('unregistered', launchd_registered=False, login_plist_exists=False)
            # A fresh CLI installation wins; app register/unregister must not adopt it.
            (support / install.APP_RECORD).unlink()
            install._atomic(plist, content)
            adapter.register(plist)
            until(healthy)
            pid = process()[1]
            for action in ('status', 'register', 'unregister'):
                assert 'cli' in bridge(action)
                assert process()[1] == pid and healthy()
            emit('existing_cli_reused', pid=pid, second_service=False)
        finally:
            if ui is not None:
                ui.terminate()
                ui.wait(timeout=15)
            adapter.unload(install.LABEL)
            until(lambda: not process()[0])
            # launchctl returns before process locks are released.
            with install._lock(support / 'serve.lock', wait=60), install._lock(root / 'tick.lock', wait=60):
                plist.unlink(missing_ok=True)
            for path in (app, moved):
                command([LSREGISTER, '-u', path], check=False)
                if path.exists():
                    shutil.rmtree(path)
            shutil.rmtree(support)
            assert not default_root.exists()
            emit('cleaned', service_registered=process()[0], support_exists=support.exists(), cli_plist_exists=plist.exists(), default_root_exists=False)


if __name__ == '__main__':
    main()
