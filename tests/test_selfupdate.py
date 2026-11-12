"""Update input/abuse policy (synthetic source repositories; no user recordings).

A clean tracked branch may fetch metadata and install only a consented FF tip.
Wheels, missing upstreams, edits, divergence, failed networks and moved tips fail
closed. Git titles are text (including HTML), never evaluated. Invalid request
bodies, missing sessions, Host/Origin/CSRF violations and cookie replay after
logout are rejected. A fake launchd adapter exercises cutover/rollback; local
bare origins exercise real git. These tests are assumption-level, not live MLX.
"""
import hashlib
import json
import os
import plistlib
import subprocess
import threading
from contextlib import closing
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from starlette.testclient import TestClient

from quietclerk import config, install, selfupdate, store
from quietclerk.serve import Runtime
from quietclerk.server import create_app, status_snapshot
from quietclerk.server.auth import Auth, COOKIE
from test_install import FakeMac, UpdateMac


def git(path, *args):
    return subprocess.run(['git', '-C', str(path), *args], check=True, text=True,
                          capture_output=True, env=os.environ | {
                              'GIT_AUTHOR_NAME': 'Synthetic', 'GIT_AUTHOR_EMAIL': 'test@example.invalid',
                              'GIT_COMMITTER_NAME': 'Synthetic', 'GIT_COMMITTER_EMAIL': 'test@example.invalid'}).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    origin, writer, source = (tmp_path / name for name in ('origin.git', 'writer', 'checkout ; literal'))
    git(tmp_path, 'init', '--bare', '--initial-branch=main', str(origin))
    git(tmp_path, 'clone', str(origin), str(writer))
    (writer / 'pyproject.toml').write_text('[project]\nname="synthetic"\n')
    git(writer, 'add', '.')
    git(writer, 'commit', '-m', 'feat: initial')
    git(writer, 'push', '-u', 'origin', 'main')
    git(tmp_path, 'clone', str(origin), str(source))
    return origin, writer, source


def advance(writer, title='fix(api): 쉽게 업데이트'):
    with (writer / 'pyproject.toml').open('a') as stream:
        stream.write('# synthetic change\n')
    git(writer, 'add', '.')
    git(writer, 'commit', '-m', title)
    git(writer, 'push')


class Worker:
    def __init__(self):
        self.calls = []
        self.started = threading.Event()
        self.removed = []

    def start(self, runtime, identity, state):
        self.calls.append((identity, dict(state)))
        self.started.set()
        return 'synthetic.update'

    def remove(self, label):
        self.removed.append(label)


@pytest.fixture
def runtime(tmp_path, repo):
    settings = config.load(tmp_path / 'data/settings.toml', environ={'QC_ROOT': str(tmp_path / 'data')})
    result = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False, update_worker=Worker())
    selfupdate.record_source(result.support, repo[2])
    with closing(store.connect(result.db)):
        pass
    return result



def test_install_records_source_before_service_can_check_updates(tmp_path, repo):
    class StartingMac(FakeMac):
        def healthy(self, label, support, settings, started):
            identity = selfupdate.read_json(support / 'source.json')
            assert identity['installed'] == selfupdate.commit(repo[2])
            assert Path(identity['source']) == repo[2].resolve()
            return super().healthy(label, support, settings, started)
    install.run(root=tmp_path / 'home/data', home=tmp_path / 'home',
                agents=tmp_path / 'agents', support=tmp_path / 'support',
                source=repo[2], adapter=StartingMac(registered=()), environ={})

def test_current_behind_title_cleanup_persist_and_max_twenty(runtime, repo):
    assert runtime.updates.check()['state'] == 'current'
    for number in range(22):
        advance(repo[1], f'fix(api)!: change {number}')
    result = runtime.updates.check()
    assert result['state'] == 'available' and result['behind'] == 22
    assert len(result['changes']) == 20
    assert result['changes'][0]['title'] == 'change 21'
    assert result['changes'][-1]['title'] == 'change 2'
    assert result['checked_at'] and result['latest']['date']
    assert selfupdate.Updates(runtime).snapshot() == result
    schema = json.loads(Path('quietclerk/server/schema.json').read_text())
    Draft202012Validator(schema | {'$ref': '#/$defs/Update'}).validate(result)


@pytest.mark.parametrize('case,reason', [('edit', 'local_changes'), ('untracked', 'local_changes'),
                                        ('diverged', 'diverged'), ('offline', 'offline'),
                                        ('no_remote', 'no_remote'), ('missing', 'no_checkout'),
                                        ('wheel', 'wheel_install')])
def test_unavailable_source_policies(runtime, repo, tmp_path, case, reason):
    origin, writer, source = repo
    if case == 'edit':
        (source / 'pyproject.toml').write_text('changed')
    elif case == 'untracked':
        (source / 'private.txt').write_text('never sent')
    elif case == 'diverged':
        advance(writer)
        (source / 'local.txt').write_text('local')
        git(source, 'add', '.')
        git(source, 'commit', '-m', 'local')
    elif case == 'offline':
        git(source, 'remote', 'set-url', 'origin', str(tmp_path / 'absent.git'))
    elif case == 'no_remote':
        git(source, 'branch', '--unset-upstream')
    elif case == 'missing':
        selfupdate.write_json(runtime.support / 'source.json', {'source': str(tmp_path / 'absent')})
    elif case == 'wheel':
        wheel = tmp_path / 'quietclerk.whl'
        wheel.write_bytes(b'wheel')
        selfupdate.record_source(runtime.support, wheel)
    assert runtime.updates.check()['reason'] == reason
    assert not runtime.updates.snapshot()['changes']


def test_fetch_timeout_privacy_and_automatic_setting(runtime, repo, monkeypatch):
    calls = []
    original = selfupdate.subprocess.run
    def run(argv, **kwargs):
        if argv[:1] == ['git']:
            calls.append((argv, kwargs))
            if 'fetch' in argv:
                raise subprocess.TimeoutExpired(argv, 30)
        return original(argv, **kwargs)
    monkeypatch.setattr(selfupdate.subprocess, 'run', run)
    runtime.settings = config.Settings(runtime.settings.snapshot() | {'updates.check': False}, {},
                                       frozenset(), runtime.settings.path)
    assert runtime.updates.check(automatic=True)['reason'] == 'check_disabled'
    assert calls == []
    assert runtime.updates.check()['reason'] == 'offline'
    assert next(options for argv, options in calls if 'fetch' in argv)['timeout'] == 30
    assert all(str(runtime.settings.root) not in ' '.join(argv) for argv, _ in calls)


def test_automatic_checks_once_each_day(runtime, monkeypatch):
    clock = [100000.0]
    runtime.updates.clock = lambda: clock[0]
    calls = []
    original = selfupdate.inspect
    def inspect(identity, now):
        calls.append(now)
        return original(identity, now)
    monkeypatch.setattr(selfupdate, 'inspect', inspect)
    runtime.updates.check(automatic=True)
    clock[0] += 86399
    runtime.updates.check(automatic=True)
    assert len(calls) == 1
    clock[0] += 1
    runtime.updates.check(automatic=True)
    assert len(calls) == 2


def test_scheduled_job_boundary_wins_over_next_claim(runtime, repo):
    advance(repo[1])
    runtime.updates.check()
    runtime.updates.busy = True
    with closing(store.connect(runtime.db)) as con:
        assert runtime.updates.apply(con) == {'state': 'scheduled'}
    assert not runtime.updates.worker.calls
    runtime.updates.busy = False
    with runtime.updates.lock:
        assert runtime.updates.before_job()
    assert len(runtime.updates.worker.calls) == 1
    assert runtime.updates.snapshot()['state'] == 'updating'
    with runtime.updates.lock:
        assert runtime.updates.before_job()
    assert len(runtime.updates.worker.calls) == 1


def test_executor_finishes_current_job_then_starts_update(runtime, repo):
    started, finish = threading.Event(), threading.Event()
    claims = []
    class Executor:
        def __init__(self, *args): pass
        def run_one(self, **kwargs):
            claims.append('job')
            started.set()
            assert finish.wait(5)
            return None
    runtime.executor_factory = Executor
    runtime.scan = lambda *args, **kwargs: None
    runtime._ops = lambda *args: None
    advance(repo[1])
    runtime.updates.check()
    runtime.start()
    try:
        assert started.wait(5)
        with closing(store.connect(runtime.db)) as con:
            assert runtime.updates.apply(con)['state'] == 'scheduled'
        finish.set()
        assert runtime.updates.worker.started.wait(5)
        assert claims == ['job']
    finally:
        finish.set()
        runtime.close()


def test_worker_success_failure_checkout_plist_restore_and_dismiss(tmp_path, repo):
    origin, writer, source = repo
    paths = dict(root=tmp_path / 'home/data', home=tmp_path / 'home', source=source,
                 agents=tmp_path / 'agents', support=tmp_path / 'support')
    install.run(adapter=FakeMac(registered=()), environ={}, **paths)
    settings = config.load(paths['root'] / 'settings.toml', environ={'QC_ROOT': str(paths['root'])})
    runtime = Runtime(settings, support=paths['support'], update_worker=Worker())
    advance(writer)
    before = runtime.updates.check()
    plist = paths['agents'] / (install.LABEL + '.plist')
    old_service = plistlib.loads(plist.read_bytes())
    old_service['ProcessType'] = 'Background'
    plist.write_bytes(plistlib.dumps(old_service).replace(b'<dict>', b'<dict>\n\n', 1))
    original_plist = plist.read_bytes()
    # Health failure exercises real install.update rollback, not a fake updater.
    adapter = UpdateMac(paths, fail='unhealthy')
    failed = selfupdate.run_worker(settings=settings.path, previous=before['installed']['commit'],
                                   target=before['latest']['commit'], updater=lambda **kw: install.update(
                                       **kw, adapter=adapter), **paths)
    assert failed['state'] == 'failed' and failed['finished_at']
    assert plist.read_bytes() == original_plist
    assert git(source, 'rev-parse', '--short', 'HEAD') == before['installed']['commit']
    assert runtime.updates.snapshot()['state'] == 'failed'
    assert selfupdate.Updates(runtime).snapshot()['state'] == 'failed'
    assert runtime.updates.check()['state'] == 'failed'
    assert runtime.updates.dismiss()['state'] == 'available'
    adapter = UpdateMac(paths)
    done = selfupdate.run_worker(settings=settings.path, previous=before['installed']['commit'],
                                 target=before['latest']['commit'], updater=lambda **kw: install.update(
                                     **kw, adapter=adapter), **paths)
    assert done['state'] == 'done' and done['installed'] == before['latest']
    assert plistlib.loads(plist.read_bytes())['ProcessType'] == 'Interactive'
    assert done['previous_commit'] == before['installed']['commit']
    assert selfupdate.Updates(runtime).snapshot()['state'] == 'done'
    assert runtime.updates.dismiss()['state'] == 'current'
    assert runtime.updates.snapshot()['finished_at'] is None


def test_worker_never_discards_user_edits_or_installs_new_unconsented_tip(runtime, repo):
    advance(repo[1])
    state = runtime.updates.check()
    calls = []
    advance(repo[1], 'fix: newer unseen tip')
    result = selfupdate.run_worker(root=runtime.settings.root, support=runtime.support,
        settings=runtime.settings.path, source=repo[2], previous=state['installed']['commit'],
        target=state['latest']['commit'], updater=lambda **kw: calls.append(kw))
    assert result['state'] == 'failed' and not calls
    assert result['reason'] is None
    assert git(repo[2], 'rev-parse', '--short', 'HEAD') == state['installed']['commit']
    assert result['installed'] == state['installed']


def test_worker_preserves_edits_made_during_failed_install(runtime, repo):
    advance(repo[1])
    state = runtime.updates.check()
    def fail(**kwargs):
        (repo[2] / 'pyproject.toml').write_text('user edit during update')
        raise RuntimeError('broken installer')
    result = selfupdate.run_worker(root=runtime.settings.root, support=runtime.support,
        settings=runtime.settings.path, source=repo[2], previous=state['installed']['commit'],
        target=state['latest']['commit'], updater=fail)
    assert result['state'] == 'failed' and result['reason'] == 'diverged'
    assert (repo[2] / 'pyproject.toml').read_text() == 'user edit during update'


def test_launch_failure_is_durable_and_does_not_hold_executor(runtime, repo):
    advance(repo[1])
    runtime.updates.check()
    class BrokenWorker:
        def start(self, *args):
            raise OSError('launchctl refused')
    runtime.updates.worker = BrokenWorker()
    with closing(store.connect(runtime.db)) as con:
        assert runtime.updates.apply(con) == {'state': 'updating'}
    assert selfupdate.Updates(runtime).snapshot()['state'] == 'failed'
    assert not runtime.updates.before_job()


def test_restart_cleans_interrupted_job_but_never_a_live_worker(runtime, repo):
    advance(repo[1])
    state = runtime.updates.check()
    label = 'local.quietclerk.update.' + 'a' * 32
    orphan = 'local.quietclerk.update.' + 'b' * 32
    for name in (label, orphan):
        (runtime.support / (name + '.plist')).write_bytes(b'synthetic job')
    selfupdate.write_json(runtime.updates.path, state | {'state': 'updating', 'worker_label': label})
    with install._lock(runtime.support / 'selfupdate.lock'):
        runtime.updates.recover()
        assert runtime.updates.snapshot()['state'] == 'updating'
        assert not runtime.updates.worker.removed
    runtime.updates.recover()
    assert set(runtime.updates.worker.removed) == {label, orphan}
    assert not list(runtime.support.glob('local.quietclerk.update.*.plist'))
    assert runtime.updates.snapshot()['state'] == 'failed'
    assert selfupdate.read_json(runtime.updates.path)['failure'] == 'interrupted'
    assert selfupdate.Updates(runtime).snapshot()['state'] == 'failed'


def test_launchd_worker_has_external_literal_command(runtime, repo, monkeypatch):
    advance(repo[1])
    state = runtime.updates.check()
    calls = []
    monkeypatch.setattr(selfupdate.subprocess, 'run', lambda argv, **kw: calls.append((argv, kw)))
    label = selfupdate.LaunchdWorker().start(runtime, runtime.updates.identity(), state)
    argv, options = calls[0]
    assert argv[:3] == ['launchctl', 'bootstrap', f'gui/{os.getuid()}']
    job = plistlib.loads(Path(argv[3]).read_bytes())
    assert label.startswith('local.quietclerk.update.') and job['Label'] == label
    assert job['KeepAlive'] is False and job['RunAtLoad'] is True
    assert job['ProcessType'] == 'Background'  # One-shot updates do not serve the UI.
    assert job['EnvironmentVariables']['PATH'] == os.environ['PATH']
    assert job['EnvironmentVariables']['HF_HUB_OFFLINE'] == '1'
    command = job['ProgramArguments']
    assert command[1:4] == ['-I', '-m', 'quietclerk.selfupdate']
    assert command[command.index('--source') + 1] == str(repo[2])
    assert command[command.index('--label') + 1] == label
    assert options['timeout'] == 30 and not options.get('shell')


def test_update_sessions_hash_only_short_expiry_logout_and_unsafe_file(tmp_path):
    clock = [1000.0]
    auth = Auth(tmp_path, 1234, clock=lambda: clock[0])
    auth.refresh()
    sid, csrf = auth.exchange(auth.token)
    auth.preserve_for_update()
    content = auth.resume_path.read_text()
    assert sid not in content and hashlib.sha256(sid.encode()).hexdigest() in content
    assert auth.resume_path.stat().st_mode & 0o777 == 0o600
    auth.close()
    resumed = Auth(tmp_path, 1234, clock=lambda: clock[0])
    assert resumed.session(sid).csrf == csrf
    resumed.logout(sid)
    assert Auth(tmp_path, 1234, clock=lambda: clock[0]).session(sid) is None
    auth = Auth(tmp_path, 1234, clock=lambda: clock[0])
    auth.refresh()
    sid, _ = auth.exchange(auth.token)
    auth.preserve_for_update()
    assert Auth(tmp_path, 4321, clock=lambda: clock[0]).session(sid) is None
    auth.resume_path.chmod(0o644)
    assert Auth(tmp_path, 1234, clock=lambda: clock[0]).session(sid) is None
    auth.resume_path.chmod(0o600)
    clock[0] += 901
    assert Auth(tmp_path, 1234, clock=lambda: clock[0]).session(sid) is None


def test_update_routes_security_settings_idempotency_restart_and_sse(runtime, repo):
    base = f"http://127.0.0.1:{runtime.settings.get('server.port')}"
    app = create_app(runtime, start_runtime=False)
    with TestClient(app, base_url=base) as client:
        assert client.get('/api/update').status_code == 401
        for action in ('check', 'apply', 'dismiss'):
            assert client.post('/api/update/' + action, headers={'Origin': base}).status_code == 401
        token = json.loads(app.state.auth.path.read_text())['token']
        response = client.post('/api/session', json={'token': token}, headers={'Origin': base})
        csrf = response.headers['x-csrf-token']
        sid = client.cookies.get(COOKIE)
        assert client.post('/api/update/check', headers={'Origin': base}).status_code == 403
        client.headers.update({'Origin': base, 'X-CSRF-Token': csrf})
        assert client.post('/api/update/check', headers={'Origin': 'http://attacker.invalid'}).status_code == 403
        assert client.get('/api/update', headers={'Host': 'attacker.invalid'}).status_code == 403
        assert client.post('/api/update/check', json={'source': '/secret'}).status_code == 400
        assert client.post('/api/update/apply').status_code == 409
        assert client.put('/api/settings', json={'updates.check': 'false'}).status_code == 400
        assert client.put('/api/settings', json={'updates': {'check': False}}).json()['effective']['updates.check'] is False
        assert config.load(runtime.settings.path, environ={'QC_ROOT': str(runtime.settings.root)}).get('updates.check') is False
        advance(repo[1], 'fix(ui): <script>not executed</script>')
        assert client.post('/api/update/check').json()['changes'][0]['title'] == '<script>not executed</script>'
        response = client.post('/api/update/apply', headers={'Idempotency-Key': 'once'})
        assert response.status_code == 202 and response.json() == {'state': 'updating'}
        assert client.post('/api/update/apply', headers={'Idempotency-Key': 'once'}).json() == response.json()
        assert len(runtime.updates.worker.calls) == 1
        assert status_snapshot(runtime)['update'] == {'state': 'updating', 'behind': 1}
    replacement = Runtime(runtime.settings, support=runtime.support, update_worker=Worker())
    app = create_app(replacement, start_runtime=False)
    with TestClient(app, base_url=base) as client:
        client.cookies.set(COOKIE, sid)
        assert client.get('/api/session').json()['csrf_token'] == csrf
        assert client.get('/api/update').status_code == 200
        assert client.post('/api/update/dismiss', headers={'Origin': base}).status_code == 403
        assert client.post('/api/update/dismiss', headers={'Origin': base, 'X-CSRF-Token': csrf}).status_code == 200
