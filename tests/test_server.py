"""F1 input/abuse policy and acceptance evidence (synthetic, not real recordings).

Unauthenticated API/audio/SSE, rebinding Host, cross Origin, absent CSRF,
expired/replayed file tokens: reject. JSON types/unknown settings/path-like job
IDs: reject without writes. DB archive only; malformed ranges: 416, missing: 410.
Synthetic AAC with real intake and fake processing exercises serve + live SSE.
No launchd registration, installed settings, user vaults or remote APIs are used.
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import uvicorn
from jsonschema import Draft202012Validator
from starlette.testclient import TestClient

from quietclerk import artifacts, cli, config, executor, intake, store, store_ops
from quietclerk.serve import Runtime, ServiceLock, legacy_registered
from quietclerk.server import create_app
from quietclerk.bootstrap_file import read_bootstrap
from quietclerk.server.auth import Auth
from quietclerk.server.integrations import Syncthing
from quietclerk.providers import Completion, ProviderStatus


class UnavailableSync:
    def __init__(self, settings):
        pass

    def folder(self):
        raise FileNotFoundError('synthetic unavailable')

    backlog = folder


@pytest.fixture
def settings(tmp_path):
    return config.load(tmp_path / 'settings.toml', environ={
        'QC_ROOT': str(tmp_path), 'QC_SINCE': '1970-01-01 00:00',
        'QC_STABLE_SEC': '0', 'QC_MIN_DURATION_SEC': '0'})


@pytest.fixture
def api(settings, tmp_path):
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False)
    clock = [1000.0]
    app = create_app(runtime, start_runtime=False, sync_factory=UnavailableSync,
                     provider_registry=lambda _: {}, auth_clock=lambda: clock[0])
    base = f"http://127.0.0.1:{settings.get('server.port')}"
    with TestClient(app, base_url=base) as client:
        yield client, app, clock, base


def login(client, app, base):
    token = read_bootstrap(app.state.runtime.support, clock=lambda: 1000)['token']
    response = client.post('/api/session', json={'token': token}, headers={'Origin': base})
    assert response.status_code == 204
    client.headers.update({'Origin': base, 'X-CSRF-Token': response.headers['X-CSRF-Token']})
    return token, response


def add_job(runtime, job_id='job', status='queued'):
    target = runtime.settings.root / 'archive' / job_id / 'source.m4a'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b'0123456789')
    with closing(store.connect(runtime.db)) as con:
        return dict(store.add_job(con, job_id, artifacts.sha256(target), 'sample.m4a', str(target), 600,
                                  status=status, skip_reason='user_excluded' if status == 'skipped' else None))


def test_in30_unauthenticated_get_audio_sse_and_bootstrap_headers(api, caplog):
    client, app, clock, base = api
    for path in ('/api/status', '/api/jobs', '/api/jobs/job/audio', '/api/events'):
        assert client.get(path).status_code == 401
    token = read_bootstrap(app.state.runtime.support, clock=lambda: clock[0])['token']
    for path in ('/', '/bootstrap.js'):
        response = client.get(path)
        assert response.status_code == 200
        assert token not in response.text
        assert response.headers['Cache-Control'] == 'no-store'
        assert response.headers['Referrer-Policy'] == 'no-referrer'
        assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']
        assert 'Access-Control-Allow-Origin' not in response.headers
    assert token not in caplog.text


@pytest.mark.parametrize('host', ['attacker.test', '127.0.0.1', '127.0.0.1:1', 'localhost.attacker.test:8000', '[::1]:8000'])
def test_in30_rebinding_host(api, host):
    client, app, clock, base = api
    assert client.get('/', headers={'Host': host}).status_code == 403
    assert client.get('/api/status', headers={'Host': host}).status_code == 403


def test_in30_invalid_token_types_and_duplicate_host(api):
    client, app, clock, base = api
    for token in (None, 1, [], {}, '한글', '\ud800'):
        response = client.post('/api/session', content=json.dumps({'token': token}),
                               headers={'Origin': base, 'Content-Type': 'application/json'})
        assert response.status_code == 401
    host = base.removeprefix('http://')
    assert client.get('/', headers=[('Host', host), ('Host', host)]).status_code == 403


def test_in30_missing_host_rejected_before_origin_indexing(api):
    import asyncio
    from quietclerk.server import Security
    _, app, _, base = api
    messages = []
    async def forbidden_app(scope, receive, send):
        raise AssertionError('invalid Host reached application')
    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}
    async def send(message):
        messages.append(message)
    security = Security(forbidden_app, auth=app.state.auth)
    scope = {'type': 'http', 'method': 'POST', 'path': '/api/session', 'query_string': b'',
             'headers': [(b'origin', base.encode())], 'scheme': 'http'}
    asyncio.run(security(scope, receive, send))
    assert messages[0]['status'] == 403


def test_in30_origin_csrf_cookie_replay_logout_and_no_mutating_get(api):
    client, app, clock, base = api
    token = read_bootstrap(app.state.runtime.support, clock=lambda: 1000)['token']
    assert client.post('/api/session', json={'token': token}).status_code == 403
    assert client.post('/api/session', json={'token': token}, headers={'Origin': 'http://evil.test'}).status_code == 403
    original, response = login(client, app, base)
    cookie = response.headers['Set-Cookie']
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Path=/' in cookie
    assert client.post('/api/session', json={'token': original}).status_code == 401
    for headers in ({'X-CSRF-Token': ''}, {'Origin': 'null'}, {'Origin': 'http://evil.test'}, {'Origin': base + '/'},
                    {'Origin': base.replace('127.0.0.1', 'localhost')}):
        assert client.post('/api/pause', headers=headers).status_code == 403
    assert client.post('/api/pause').status_code == 204
    assert client.get('/api/pause').status_code == 405
    assert client.options('/api/status').headers.get('Access-Control-Allow-Origin') is None
    session_cookie = client.cookies.get('qc_session')
    assert client.post('/api/logout').status_code == 204
    client.cookies.set('qc_session', session_cookie)
    assert client.get('/api/status').status_code == 401


def test_in30_expiry_idle_and_absolute(api):
    client, app, clock, base = api
    token = read_bootstrap(app.state.runtime.support, clock=lambda: 1000)['token']
    clock[0] = 1060
    assert client.post('/api/session', json={'token': token}, headers={'Origin': base}).status_code == 401
    app.state.auth.refresh()
    login(client, app, base)
    clock[0] += 12 * 3600
    assert client.get('/api/events').status_code == 401
    app.state.auth.refresh()
    login(client, app, base)
    for _ in range(15):
        clock[0] += 11 * 3600
        assert client.get('/api/session').status_code == 200
    clock[0] += 3 * 3600
    assert client.get('/api/status').status_code == 401


def test_private_file_open_fragment_only_and_no_secret_logs(api, monkeypatch, capsys, caplog):
    client, app, clock, base = api
    path = app.state.auth.path
    assert path.stat().st_mode & 0o777 == 0o600
    urls = []
    monkeypatch.setattr(cli.webbrowser, 'open', lambda url: urls.append(url) or True)
    # CLI uses wall clock, whereas this fixture deliberately uses an old clock.
    monkeypatch.setattr(cli, 'read_bootstrap', lambda _: read_bootstrap(app.state.runtime.support, clock=lambda: clock[0]))
    assert cli.main(['--support', str(path.parent), 'open']) == 0
    assert urls[0].startswith(base + '/#bootstrap=')
    token = urls[0].split('=', 1)[1]
    assert token not in capsys.readouterr().out + caplog.text
    path.chmod(0o644)
    with pytest.raises(RuntimeError):
        read_bootstrap(path.parent, clock=lambda: clock[0])
    path.chmod(0o600)
    saved = path.with_name('saved')
    path.rename(saved)
    path.symlink_to(saved)
    with pytest.raises(OSError):
        read_bootstrap(path.parent, clock=lambda: clock[0])


@pytest.mark.parametrize(('header', 'code', 'content', 'content_range'), [
    (None, 200, b'0123456789', None), ('bytes=0-0', 206, b'0', 'bytes 0-0/10'),
    ('bytes=9-', 206, b'9', 'bytes 9-9/10'), ('bytes=0-999', 206, b'0123456789', 'bytes 0-9/10'),
    ('bytes=-2', 206, b'89', 'bytes 8-9/10'), ('bytes=-999', 206, b'0123456789', 'bytes 0-9/10'),
    ('bytes=10-', 416, b'', 'bytes */10'), ('bytes=4-3', 416, b'', 'bytes */10'),
    ('bytes=-0', 416, b'', 'bytes */10'), ('bytes=-', 416, b'', 'bytes */10'),
    ('bytes=0-1,3-4', 416, b'', 'bytes */10'), ('bytes=../../etc/passwd-', 416, b'', 'bytes */10'),
    ('items=0-1', 416, b'', 'bytes */10')])
def test_audio_range_boundaries(api, header, code, content, content_range):
    client, app, clock, base = api
    add_job(app.state.runtime)
    login(client, app, base)
    response = client.get('/api/jobs/job/audio', headers={'Range': header} if header else {})
    assert response.status_code == code and response.content == content
    assert response.headers.get('Content-Range') == content_range


def test_audio_missing_empty_symlink_and_path_escape(api, tmp_path):
    client, app, clock, base = api
    row = add_job(app.state.runtime)
    path = Path(row['archive_path'])
    login(client, app, base)
    assert client.get('/api/jobs/%2e%2e%2foutside/audio').status_code == 404
    assert client.get('/api/jobs/job/audio?path=../../outside').content == b'0123456789'
    path.write_bytes(b'')
    assert client.get('/api/jobs/job/audio', headers={'Range': 'bytes=0-'}).status_code == 416
    assert client.get('/api/jobs/job/audio').status_code == 200
    path.unlink()
    assert client.get('/api/jobs/job/audio').status_code == 410
    outside = tmp_path / 'secret'
    outside.write_text('not audio')
    path.symlink_to(outside)
    assert client.get('/api/jobs/job/audio').status_code == 410
    with closing(store.connect(app.state.runtime.db)) as con:
        store.add_job(con, 'outside', 'b' * 64, 'outside.m4a', str(outside), 1)
    assert client.get('/api/jobs/outside/audio').status_code == 410


def test_jobs_transitions_idempotency_history_and_language(api):
    client, app, clock, base = api
    row = add_job(app.state.runtime)
    login(client, app, base)
    assert client.post('/api/jobs/job/process', json={'mode': 'bad'}).status_code == 400
    assert client.post('/api/jobs/job/process', json={'mode': 'resume'}).status_code == 204
    assert client.put('/api/jobs/job/language', json={'override': 'en'}).status_code == 204
    assert client.put('/api/jobs/job/language', json={'override': 'ja'}).status_code == 400
    assert client.post('/api/jobs/job/exclude').status_code == 202
    before = client.get('/api/jobs/job').json()['job']['updated_at']
    assert client.post('/api/jobs/job/exclude').status_code == 202
    assert client.get('/api/jobs/job').json()['job']['updated_at'] == before
    assert client.post('/api/jobs/job/include').status_code == 202
    assert client.post('/api/jobs/job/include').status_code == 204
    with closing(store.connect(app.state.runtime.db)) as con:
        claimed = store.claim(con, 'testboot', app.state.runtime.settings)
        store.start_stage(con, 'job', claimed['active_run_id'], 'testboot', 'summarize',
                          provider='codex', endpoint_class='external', sent_fields=['transcript'])
    response = client.post('/api/jobs/job/process', json={'mode': 'auto'})
    assert response.status_code == 409 and response.json() == {'status': 'running'}
    detail = client.get('/api/jobs/job').json()
    assert detail['runs'][0]['stages'][0]['sent_fields'] == ['transcript']
    assert client.put('/api/jobs/job/language', json={'override': None}).status_code == 409
    assert client.post('/api/jobs/missing/process', json={}).status_code == 404
    assert client.get('/api/jobs?limit=0').status_code == 400
    assert client.get('/api/jobs?limit=abc').status_code == 400
    assert client.get('/api/jobs?status=unknown').status_code == 400
    assert client.get('/api/jobs?status=running').json()['items'][0]['job_id'] == 'job'


def test_pause_scan_settings_types_atomicity_and_environment_locks(api):
    client, app, clock, base = api
    login(client, app, base)
    assert client.post('/api/pause').status_code == 204
    assert client.get('/api/status').json()['paused']
    assert client.post('/api/resume').status_code == 204
    assert not client.get('/api/status').json()['paused']
    assert client.post('/api/scan').status_code == 204
    assert app.state.runtime.scan_requested.is_set()
    for changes, code in [({'unknown': 1}, 400), ({'language.mode': 'ja'}, 400),
                          ({'server.port': True}, 400), ({'stable_sec': 1}, 409),
                          ({'root': '/other'}, 409), ({'inbox': '/other'}, 409)]:
        response = client.put('/api/settings', json=changes)
        assert response.status_code == code
        assert 'field' in response.json()
        assert not app.state.runtime.settings.path.exists()
    changes = {'language': {'mode': 'en'}, 'providers': {'consent': {'codex': ['transcript']}}, 'ui.language': 'ko'}
    response = client.put('/api/settings', json=changes)
    assert response.status_code == 200
    assert response.json()['effective']['language.mode'] == 'en'
    assert response.json()['effective']['providers.consent'] == {'codex': ['transcript']}
    content = app.state.runtime.settings.path.read_bytes()
    assert client.put('/api/settings', json={'ui.language': 'invalid'}).status_code == 400
    assert app.state.runtime.settings.path.read_bytes() == content
    reloaded = config.load(app.state.runtime.settings.path, {'QC_ROOT': str(app.state.runtime.settings.root)})
    assert reloaded.get('language.mode') == 'en'
    assert client.post('/api/pause', content='[]', headers={'Content-Type': 'application/json'}).status_code == 400
    assert client.post('/api/pause', content='{}', headers={'Content-Type': 'text/plain'}).status_code == 400
    assert client.post('/api/pause', content='a' * 65537).status_code == 413


def test_idempotency_key_avoids_repeated_mutation_and_rejects_mismatch(api):
    client, app, clock, base = api
    login(client, app, base)
    key = {'Idempotency-Key': 'one-request'}
    assert client.post('/api/scan', headers=key).status_code == 204
    app.state.runtime.scan_requested.clear()
    assert client.post('/api/scan', headers=key).status_code == 204
    assert not app.state.runtime.scan_requested.is_set()
    assert client.post('/api/pause', headers=key).status_code == 409


def test_delete_local_durable_tombstone_audio_410_and_protected_paths(api):
    client, app, clock, base = api
    row = add_job(app.state.runtime)
    runtime = app.state.runtime
    work = runtime.settings.root / 'work' / 'job'
    work.mkdir(parents=True)
    (work / 'transcript.json').write_text('private conversation')
    inbox = Path(runtime.settings.get('inbox'))
    inbox.mkdir()
    (inbox / 'sample.m4a').write_bytes(b'0123456789')
    notes = Path(runtime.settings.get('output'))
    notes.mkdir()
    (notes / 'keep.md').write_text('user note')
    login(client, app, base)
    assert client.post('/api/jobs/job/delete-local', json={'scope': 'all'}).status_code == 400
    assert client.post('/api/jobs/job/delete-local', json={'scope': 'processing_data'}).status_code == 202
    assert client.post('/api/jobs/job/delete-local', json={'scope': 'processing_data'}).status_code == 202
    assert client.get('/api/jobs/job/audio').status_code == 410
    with closing(store.connect(runtime.db)) as con:
        runtime._delete_pending(con)
        assert store_ops.deleted(con, 'job')
        assert store.job(con, 'job')['source_name'] == ''
        assert not store_ops.pending_deletions(con)
    assert not work.exists() and not Path(row['archive_path']).exists()
    assert (inbox / 'sample.m4a').exists() and (notes / 'keep.md').read_text() == 'user note'
    assert client.post('/api/jobs/job/process', json={'mode': 'auto'}).status_code == 409


def test_response_schemas_for_local_endpoints(api, monkeypatch, tmp_path):
    client, app, clock, base = api
    add_job(app.state.runtime)
    login(client, app, base)
    monkeypatch.setattr('quietclerk.server.integrations.vaults', lambda: [{'path': str(tmp_path), 'exists': True}])
    schema = json.loads(Path('quietclerk/server/schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    for path, name in [('/api/session', 'Session'), ('/api/status', 'Status'), ('/api/jobs', 'Jobs'),
                       ('/api/jobs/job', 'Detail'), ('/api/settings', 'Settings'), ('/api/backlog', 'Backlog'),
                       ('/api/providers', 'Providers'), ('/api/setup/checks', 'Checks'), ('/api/setup/vaults', 'Vaults')]:
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)
        Draft202012Validator(schema | {'$ref': '#/$defs/' + name}).validate(response.json())


@pytest.mark.parametrize('version', ['0.1.2', None])
@pytest.mark.parametrize('app_install', [False, True])
def test_authenticated_status_engine_identity(api, monkeypatch, version, app_install):
    from quietclerk import server
    client, app, clock, base = api
    def package_version(name):
        assert name == 'quietclerk'
        if version is None:
            raise server.metadata.PackageNotFoundError(name)
        return version
    monkeypatch.setattr(server.metadata, 'version', package_version)
    support = app.state.runtime.support
    if app_install:
        record = {'schema': 1, 'manager': 'app', 'label': 'local.quietclerk.serve',
                  **{key: str(support / key) for key in ('python', 'settings', 'support', 'root', 'plist')}}
        server.install._atomic(support / server.install.APP_RECORD, json.dumps(record).encode())
    assert client.get('/api/status').status_code == 401
    login(client, app, base)
    status = client.get('/api/status').json()
    assert status['engine_version'] == version
    assert status['installation_method'] == ('app' if app_install else 'cli')
    assert status['last_updated_at'] is None
    monkeypatch.setattr(app.state.runtime.updates, 'snapshot',
                        lambda: {'state': 'done', 'behind': 0, 'finished_at': '2026-11-11T00:00:00+00:00'})
    assert client.get('/api/status').json()['last_updated_at'] == '2026-11-11T00:00:00+00:00'
    monkeypatch.setattr(app.state.runtime.updates, 'snapshot',
                        lambda: {'state': 'failed', 'behind': 0, 'finished_at': '2026-11-11T00:00:00+00:00'})
    assert client.get('/api/status').json()['last_updated_at'] is None


class IdleExecutor:
    def __init__(self, *args):
        pass

    def run_one(self, **kwargs):
        return None


def test_service_lock_is_user_wide_and_legacy_labels_refuse(settings, tmp_path):
    path = tmp_path / 'support' / 'serve.lock'
    first = ServiceLock(path).acquire()
    try:
        with pytest.raises(RuntimeError, match='already serving'):
            ServiceLock(path).acquire()
    finally:
        first.close()
    runtime = Runtime(settings, support=path.parent, legacy_labels=('custom.old',),
                      label_check=lambda name: name == 'custom.old')
    with pytest.raises(RuntimeError, match='업그레이드'):
        runtime.start()
    assert not runtime.threads
    ServiceLock(path).acquire().close()


def test_launchd_label_query_is_not_shell_input(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, 'run', lambda argv, **kwargs: calls.append(argv) or subprocess.CompletedProcess(argv, 0))
    assert legacy_registered('local.rec.pipeline')
    assert calls[0] == ['launchctl', 'print', f'gui/{os.getuid()}/local.rec.pipeline']
    with pytest.raises(ValueError):
        legacy_registered('bad/label')


def test_runtime_recovers_stale_claim_and_scans_while_paused(settings, tmp_path):
    scans = threading.Event()
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False,
                      executor_factory=IdleExecutor, scan=lambda *a, **k: scans.set())
    add_job(runtime)
    with closing(store.connect(runtime.db)) as con:
        store.claim(con, 'oldboot', settings)
        store_ops.set_paused(con, True)
    runtime.start()
    try:
        assert scans.wait(2)
        with closing(store.connect(runtime.db)) as con:
            row = store.job(con, 'job')
            assert row['status'] == 'retry_wait' and row['interrupt_count'] == 1
            assert store_ops.paused(con)
        scans.clear()
        runtime.request_scan()
        assert scans.wait(2)
        assert len(runtime.boot) == 32
    finally:
        runtime.close()


def test_executor_thread_exception_exits_entire_process(settings, tmp_path):
    program = '''
import threading
from quietclerk import config
from quietclerk.serve import Runtime
class Broken:
    def __init__(self, *args): pass
    def run_one(self, **kwargs): raise RuntimeError('synthetic executor crash')
settings = config.load()
r = Runtime(settings, support=settings.root / 'support',
            label_check=lambda _: False, executor_factory=Broken, scan=lambda *a, **k: None)
r.start()
threading.Event().wait(20)
'''
    env = os.environ | {'QC_ROOT': str(tmp_path / 'child'), 'QC_SETTINGS': os.devnull}
    result = subprocess.run([sys.executable, '-c', program], env=env, capture_output=True, timeout=10)
    assert result.returncode == 1
    assert 'synthetic executor crash' not in result.stderr.decode()


@contextmanager
def live_service(settings, support, **runtime_options):
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    port = sock.getsockname()[1]
    settings = replace(settings, _values=settings.snapshot() | {'server.port': port})
    runtime = Runtime(settings, support=support, label_check=lambda _: False, **runtime_options)
    app = create_app(runtime, provider_registry=lambda _: {}, sync_factory=UnavailableSync)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=5) as client:
            yield client, runtime
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
        assert not thread.is_alive()


def test_synthetic_m4a_serve_queued_done_and_live_sse(settings, tmp_path):
    inbox = Path(settings.get('inbox'))
    inbox.mkdir()
    source = inbox / 'synthetic.m4a'
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                    'sine=frequency=440', '-t', '0.2', '-c:a', 'aac', str(source)], check=True)
    with closing(store.connect(settings.root / 'state.sqlite3')) as con:
        store_ops.set_paused(con, True)
    gate = threading.Event()
    def stage(ctx, out):
        assert gate.wait(5)
        artifacts.write_json(out, {'synthetic': True})
        note = Path(ctx.settings['output']) / 'synthetic.md'
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text('# synthetic\n')
        ctx.note_path = note
    def factory(con, boot, settings):
        return executor.Executor(con, boot, settings,
            [executor.Stage('note', 'note.json', ('archive',), {}, stage, cache=False)])
    states = set()
    with live_service(settings, tmp_path / 'support', executor_factory=factory) as (client, runtime):
        base = str(client.base_url).rstrip('/')
        token = read_bootstrap(runtime.support)['token']
        response = client.post('/api/session', json={'token': token}, headers={'Origin': base})
        client.headers.update({'Origin': base, 'X-CSRF-Token': response.headers['X-CSRF-Token']})
        with client.stream('GET', '/api/events') as events:
            assert events.status_code == 200
            for line in events.iter_lines():
                if not line.startswith('data: '):
                    continue
                payload = json.loads(line[6:])
                for row in payload['jobs']:
                    states.add(row['status'])
                if 'queued' in states and 'running' not in states:
                    assert client.post('/api/resume').status_code == 204
                if 'running' in states:
                    gate.set()
                if 'done' in states:
                    break
        assert states >= {'queued', 'running', 'done'}
        assert source.exists()
        assert Path(settings.get('output'), 'synthetic.md').exists()
        assert cli.main(['--support', str(runtime.support), 'status']) == 0
