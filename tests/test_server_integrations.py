"""Integration acceptance using an actual loopback fake Syncthing HTTP server.

Device IDs and recording names are untrusted: reject traversal/non-pending IDs
and invalid names before sending a REST mutation. Provider probes use only fixed
synthetic text and never exceed consent/local-only/tool-block policy.
"""
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from starlette.testclient import TestClient

from quietclerk import config, store, syncthing
from quietclerk.providers import Completion, ProviderStatus
from quietclerk.serve import Runtime
from quietclerk.server import create_app
from quietclerk.bootstrap_file import read_bootstrap
from quietclerk.server.integrations import vaults

DEVICE = '-'.join(['AAAAAAA'] * 8)
LOCAL = '-'.join(['BBBBBBB'] * 8)


@contextmanager
def fake_syncthing(tmp_path, monkeypatch, settings):
    calls = []
    state = {'devices': [], 'ignore': ['old.m4a', '*.m4a']}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_request(self):
            assert self.headers['X-API-Key'] == 'fake-key'
            path = urlsplit(self.path).path.removeprefix('/rest/')
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'null')
            calls.append((self.command, path, body))
            values = {'system/status': {'myID': LOCAL}, 'cluster/pending/devices': {DEVICE: {'name': 'Phone'}},
                      'config/devices': state['devices'],
                      'config/folders': [{'id': 'recordings', 'path': settings.get('inbox'),
                                          'devices': [{'deviceID': LOCAL}, {'deviceID': DEVICE}]}],
                      'system/connections': {'connections': {DEVICE: {'connected': True}}},
                      'db/completion': {'remoteState': 'valid'},
                      'cluster/pending/folders': {}, 'db/ignores': {'ignore': state['ignore']},
                      'db/need': {'progress': [], 'queued': [{'name': 'old.m4a'}],
                                  'rest': [{'name': '../escape.m4a'}, {'name': '통화.m4a'}]}}
            if self.command == 'PUT' and path == 'config/devices/' + DEVICE:
                state['devices'].append(body)
                value = None
            elif self.command == 'POST' and path == 'db/ignores':
                state['ignore'] = body['ignore']
                value = None
            elif self.command == 'POST' and path == 'db/scan':
                value = None
            else:
                value = values[path]
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

        do_GET = handle_request
        do_POST = handle_request
        do_PUT = handle_request
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    xml = tmp_path / 'syncthing.xml'
    xml.write_text(f'<configuration><gui><address>127.0.0.1:{server.server_port}</address>'
                   f'<apikey>fake-key</apikey></gui><folder id="recordings" path="{settings.get("inbox")}"/></configuration>')
    monkeypatch.setattr(syncthing, 'CONFIG', xml)
    try:
        yield calls, state
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.fixture
def settings(tmp_path):
    return config.load(tmp_path / 'settings.toml', {'QC_ROOT': str(tmp_path)})


@contextmanager
def client_for(settings, tmp_path, **kwargs):
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False)
    app = create_app(runtime, start_runtime=False, **kwargs)
    base = f"http://127.0.0.1:{settings.get('server.port')}"
    with TestClient(app, base_url=base) as client:
        token = read_bootstrap(runtime.support)['token']
        response = client.post('/api/session', json={'token': token}, headers={'Origin': base})
        assert response.status_code == 204
        client.headers.update({'Origin': base, 'X-CSRF-Token': response.headers['X-CSRF-Token']})
        yield client, runtime


def test_syncthing_pair_approve_folder_backlog_through_fake_rest(settings, tmp_path, monkeypatch):
    with fake_syncthing(tmp_path, monkeypatch, settings) as (calls, state):
        with client_for(settings, tmp_path, provider_registry=lambda _: {}) as (client, runtime):
            pairing = client.get('/api/sync/pairing').json()
            assert pairing['device_id'] == LOCAL and pairing['qr_data'] == LOCAL
            assert pairing['pending'][0]['device_id'] == DEVICE
            assert client.post('/api/sync/pairing/approve', json={'device_id': '../escape'}).status_code == 400
            assert not any(method == 'PUT' for method, _, _ in calls)
            assert client.post('/api/sync/pairing/approve', json={'device_id': DEVICE}).status_code == 204
            assert client.post('/api/sync/pairing/approve', json={'device_id': DEVICE}).status_code == 204
            assert sum(method == 'PUT' for method, _, _ in calls) == 1
            folder = client.get('/api/sync/folder').json()
            assert folder['state'] == 'connected' and folder['phone_recordings'] is None
            backlog = client.get('/api/backlog').json()
            assert backlog['names'] == ['old.m4a'] and backlog['inventory'] == 'partial'
            before = len(calls)
            assert client.post('/api/backlog/request', json={'names': ['../escape.m4a']}).status_code == 400
            assert len(calls) == before
            assert client.post('/api/backlog/request', json={'names': ['old.m4a']}).status_code == 202
            assert client.post('/api/backlog/request', json={'names': ['old.m4a']}).status_code == 202
            assert state['ignore'] == ['*.m4a']
            assert (settings.root / 'include.txt').read_text() == 'old.m4a\n'
            assert sum(method == 'POST' and path == 'db/ignores' for method, path, _ in calls) == 1


class FakeProvider:
    name = 'codex'

    def __init__(self):
        self.sent = []
        self.endpoint = 'external'
        self.tool_block = 'verified'

    def status(self):
        return ProviderStatus(True, True, 'synthetic-1', self.tool_block)

    def endpoint_class(self):
        return self.endpoint

    def complete(self, prompt, *, timeout):
        self.sent.append(prompt)
        return Completion('OK', 'synthetic', self.endpoint, 0.01)


def test_provider_check_never_sends_user_text_and_respects_consent(settings, tmp_path):
    provider = FakeProvider()
    with client_for(settings, tmp_path, provider_registry=lambda _: {'codex': provider}) as (client, runtime):
        assert client.get('/api/providers').json()['items'][0]['tool_block'] == 'verified'
        assert not client.post('/api/providers/codex/check').json()['ok']
        assert not provider.sent
        assert client.put('/api/settings', json={'providers.consent': {'codex': ['transcript']}}).status_code == 200
        response = client.post('/api/providers/codex/check', json={'text': 'PRIVATE TITLE'}, headers={'Idempotency-Key': 'probe'})
        assert response.json()['ok'] and response.json()['synthetic']
        assert client.post('/api/providers/codex/check', json={'text': 'PRIVATE TITLE'}, headers={'Idempotency-Key': 'probe'}).json()['ok']
        assert len(provider.sent) == 1 and 'PRIVATE TITLE' not in provider.sent[0]
        assert client.put('/api/settings', json={'providers.local_only': True}).status_code == 200
        assert not client.post('/api/providers/codex/check').json()['ok']
        assert len(provider.sent) == 1
        provider.endpoint = 'unknown'
        assert not client.post('/api/providers/codex/check').json()['ok']
        provider.endpoint, provider.tool_block = 'local', 'unverified'
        assert not client.post('/api/providers/codex/check').json()['ok']
        assert client.put('/api/settings', json={'providers.allow_unverified': ['codex']}).status_code == 200
        assert client.post('/api/providers/codex/check').json()['ok']
        assert len(provider.sent) == 2
        assert client.post('/api/providers/missing/check').status_code == 404


def test_vault_candidates_read_only_existing_and_missing(tmp_path):
    path = tmp_path / 'Library/Application Support/obsidian/obsidian.json'
    assert vaults(tmp_path) == []
    path.parent.mkdir(parents=True)
    existing = tmp_path / 'vault'
    existing.mkdir()
    missing = tmp_path / 'not-created'
    path.write_text(json.dumps({'vaults': {'one': {'path': str(existing)}, 'two': {'path': str(missing)}}}))
    assert vaults(tmp_path) == [{'path': str(existing), 'exists': True}, {'path': str(missing), 'exists': False}]
    assert not missing.exists()
