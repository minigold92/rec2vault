"""F2 web screens: input policy and abnormal/malicious input evidence (synthetic data, no real recordings).

| Input | Policy | Test |
|---|---|---|
| Any screen path or /static file without a session (none, forged, logged out, wrong Host) | 303 to / (screen) or 401 (file); no markup, no data | test_screen_paths_give_no_data_without_a_session, test_static_files_need_a_session |
| Request path used as a file name (../, %2e%2e, %00, directories) | static files come from an exact-name index, never a path join | test_static_lookup_is_an_exact_name_index |
| Job ID in /notes/<id> (unknown, path-like) | SQL parameter only; unknown = 404 with the same shell | test_note_screen_unknown_job_and_path_like_ids |
| Transcript/summary/title text with HTML, script, links, instructions (IN-22) | JSON in an HTML-safe data block, put in the page with textContent | test_note_data_block_is_html_safe_and_text_is_verbatim, test_front_end_has_no_markup_sinks |
| Artifacts that are tampered, unsigned, symlinked or malformed | not shown; the screen says the minutes were not found | test_unverified_artifacts_are_never_shown |
| Inline script/style, external URLs in the served pages and assets (CSP default-src 'self') | none exist | test_screens_are_one_fixed_shell_without_inline_code, test_front_end_has_no_markup_sinks |
| Note migration: no/odd consent, no CSRF, no session | 400 / 403 / 401 and nothing changed on disk | test_migration_policy_* |
| Note migration preview | read-only: vault bytes, backup dir and DB unchanged | test_migration_preview_changes_nothing |
| Migration that cannot be applied (blocking conflict) | 409 with a reason code, notes untouched | test_migration_conflict_is_409_with_reason |
"""
import json
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from starlette.testclient import TestClient

from quietclerk import artifacts, backfill, config, notes, store
from quietclerk.bootstrap_file import read_bootstrap
from quietclerk.serve import Runtime
from quietclerk.server import SCREENS, STATIC, create_app

SCREEN_PATHS = ['/home', '/jobs', '/notes', '/notes/some-job', '/backlog', '/settings', '/migrate',
                *(f'/setup/{n}' for n in range(1, 7))]
SCHEMA = json.loads((Path(__file__).parents[1] / 'quietclerk/server/schema.json').read_text())


class UnavailableSync:
    def __init__(self, settings):
        pass

    def folder(self):
        raise FileNotFoundError('synthetic unavailable')

    backlog = pairing = folder


class IdleExecutor:
    def __init__(self, *args):
        pass

    def run_one(self, **kwargs):
        return None


@pytest.fixture
def settings(tmp_path):
    return config.load(tmp_path / 'settings.toml', environ={
        'QC_ROOT': str(tmp_path), 'QC_SINCE': '1970-01-01 00:00', 'QC_STABLE_SEC': '0', 'QC_MIN_DURATION_SEC': '0'})


@pytest.fixture
def api(settings, tmp_path):
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False)
    app = create_app(runtime, start_runtime=False, sync_factory=UnavailableSync, provider_registry=lambda _: {})
    base = f"http://127.0.0.1:{settings.get('server.port')}"
    with TestClient(app, base_url=base) as client:
        yield client, runtime, base


@pytest.fixture
def live(settings, tmp_path):
    """A started runtime (execution lock held, executor idle) so migration can run on its thread."""
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False,
                      executor_factory=IdleExecutor, scan=lambda *a, **k: None)
    app = create_app(runtime, sync_factory=UnavailableSync, provider_registry=lambda _: {})
    base = f"http://127.0.0.1:{settings.get('server.port')}"
    with TestClient(app, base_url=base) as client:
        yield client, runtime, base


def login(client, runtime, base):
    token = read_bootstrap(runtime.support)['token']
    response = client.post('/api/session', json={'token': token}, headers={'Origin': base})
    assert response.status_code == 204
    client.headers.update({'Origin': base, 'X-CSRF-Token': response.headers['X-CSRF-Token']})
    return response


def minutes(runtime, job_id='20261110-100000-abc12345', texts=('hello <b>one</b>', 'two'), summary=None, skip_meta=(), tamper=()):
    """A published job with verified run artifacts, as the pipeline writes them."""
    root = runtime.settings.root
    run_id = 'run-1'
    with closing(store.connect(runtime.db)) as con:
        store.add_job(con, job_id, 'sha-' + job_id, 'meeting.m4a', str(root / 'archive' / job_id / 'source.m4a'), 120)
        con.execute('INSERT INTO runs(run_id,job_id,mode,settings_json,consent_json,status,started_at,finished_at) '
                    "VALUES(?,?,'auto',?,?,'done',1,2)", (run_id, job_id, json.dumps({}), json.dumps({})))
        con.execute("UPDATE jobs SET status='done',current_run_id=?,note_path=?,review_reasons=? WHERE job_id=?",
                    (run_id, str(root / 'notes' / 'x.md'), json.dumps(['unknown_citation:t9']), job_id))
    directory = root / 'work' / job_id / 'runs' / run_id
    directory.mkdir(parents=True)
    payloads = {
        'turns.json': [{'start': 1.0 + i, 'end': 2.0 + i, 'speaker': 'S1', 'text': text} for i, text in enumerate(texts)],
        'corrected.json': {'texts': list(texts), 'notes': []},
        'classification.json': {'meta': {'title': 'T', 'type': 'meeting', 'division': 'work', 'speakers': {
            'S1': {'role': 'host', 'name': None, 'name_id': None, 'split_suspect': False}}}},
        'summary.json': {'text': summary or '## 핵심 요약\n- first point [t1]\n- second [t2, t9]\n'},
    }
    for name, payload in payloads.items():
        part = directory / (name + '.part')
        artifacts.write_json(part, payload)
        artifacts.commit(directory / name, part, stage=name, run_id=run_id, inputs={}, params={})
        if name in skip_meta:
            artifacts.metadata(directory / name).unlink()
        if name in tamper:
            (directory / name).write_text(json.dumps(payload) + ' ')
    return job_id, directory


def island(html):
    match = re.search(r'<script type="application/json" id="qc-data">(.*?)</script>', html, re.S)
    return match and match.group(1)


# ---- authentication boundary

def test_screen_paths_give_no_data_without_a_session(api):
    client, runtime, base = api
    job_id, _ = minutes(runtime, texts=('SECRET-TRANSCRIPT',))
    for path in [*SCREEN_PATHS, f'/notes/{job_id}']:
        for forged in (None, 'forged'):
            client.cookies.clear()
            if forged:
                client.cookies.set('qc_session', forged)
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 303 and response.headers['location'] == '/', path
            assert response.content == b'' and 'SECRET' not in response.text
            assert "default-src 'self'" in response.headers['content-security-policy']
    # The bootstrap shell the redirect lands on is data-free; it is the only HTML before sign-in.
    shell = client.get('/')
    assert shell.status_code == 200 and 'qc-data' not in shell.text and 'SECRET' not in shell.text
    # A rebinding Host is refused even for a signed-in browser.
    login(client, runtime, base)
    assert client.get('/home', headers={'Host': 'attacker.test'}).status_code == 403
    assert client.get('/notes/' + job_id, headers={'Host': 'attacker.test'}).status_code == 403
    # Signing out takes the screens away again.
    assert client.post('/api/logout').status_code == 204
    client.cookies.clear()
    assert client.get('/notes/' + job_id, follow_redirects=False).status_code == 303


def test_static_files_need_a_session(api):
    client, runtime, base = api
    names = sorted(path.relative_to(STATIC).as_posix() for path in STATIC.rglob('*') if path.is_file())
    assert {'qc.css', 'app.js', 'seogi.svg', 'lib/dom.js', 'screens/home.js'} <= set(names)
    for name in names:
        response = client.get('/static/' + name, follow_redirects=False)
        assert response.status_code == 401 and response.json() == {'error': 'unauthorized'}, name
    login(client, runtime, base)
    types = {'.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml'}
    for name in names:
        response = client.get('/static/' + name)
        assert response.status_code == 200 and response.content, name
        assert response.headers['content-type'].split(';')[0] == types[Path(name).suffix]
        assert response.headers['cache-control'] == 'no-store' and response.headers['x-content-type-options'] == 'nosniff'
        assert "default-src 'self'" in response.headers['content-security-policy']


@pytest.mark.parametrize('path', ['/static/../auth.py', '/static/%2e%2e/auth.py', '/static/..%2fauth.py', '/static/lib/../../auth.py',
                                  '/static/lib', '/static/lib/', '/static/', '/static', '/static//etc/passwd', '/static/qc.css%00',
                                  '/static/app.js/', '/static/%2Fetc%2Fpasswd', '/static/LIB/DOM.JS', '/static/.hidden'])
def test_static_lookup_is_an_exact_name_index(api, path):
    client, runtime, base = api
    login(client, runtime, base)
    response = client.get(path, follow_redirects=False)
    assert response.status_code in (307, 308, 404), (path, response.status_code)
    assert b'import ' not in response.content and b'class Auth' not in response.content


def test_screens_are_one_fixed_shell_without_inline_code(api):
    client, runtime, base = api
    login(client, runtime, base)
    job_id, _ = minutes(runtime)
    for path in [*(p for p in SCREEN_PATHS if p != '/notes/some-job'), f'/notes/{job_id}']:
        response = client.get(path)
        html = response.text
        assert response.status_code == 200, path
        assert response.headers['content-security-policy'] == ("default-src 'self'; object-src 'none'; base-uri 'none'; "
                                                               "frame-ancestors 'none'; form-action 'self'")
        assert response.headers['cache-control'] == 'no-store' and response.headers['referrer-policy'] == 'no-referrer'
        scripts = re.findall(r'<script\b([^>]*)>', html)
        expected = [' type="module" src="/static/app.js"'] + ([' type="application/json" id="qc-data"'] if path.startswith('/notes/') else [])
        assert scripts == expected, (path, scripts)
        assert not re.search(r'\sstyle\s*=', html) and not re.search(r'\son\w+\s*=', html) and 'javascript:' not in html
        assert not re.search(r'(?:src|href)\s*=\s*"(?:https?:)?//', html) and 'http://' not in html.replace('http://www.w3.org', '')
        assert 'qc-data' not in html or path.startswith('/notes/')
    assert client.get('/setup/7').status_code == 404 and client.get('/setup/0').status_code == 404


def test_language_attribute_follows_the_ui_language_setting(api):
    client, runtime, base = api
    login(client, runtime, base)
    assert client.put('/api/settings', json={'ui.language': 'en'}).status_code == 200
    assert '<html lang="en">' in client.get('/home').text
    assert client.put('/api/settings', json={'ui.language': 'ko'}).status_code == 200
    assert '<html lang="ko">' in client.get('/home').text


def test_unauthenticated_regex_covers_exactly_the_screen_routes():
    for path in SCREEN_PATHS:
        assert SCREENS.fullmatch(path), path
    for path in ['/', '/api/status', '/static/app.js', '/setup/7', '/notes/a/b', '/notes/', '/home/x', '/homepage']:
        assert not SCREENS.fullmatch(path), path


# ---- the minutes screen (the only one that carries text the engine or a speaker produced)

def test_note_data_block_is_html_safe_and_text_is_verbatim(api):
    client, runtime, base = api
    hostile = '</script><script>window.pwned=1</script><img src=x onerror=alert(1)> [x](https://evil.example) [[#^t1|x]] {{7*7}} \u2028'
    job_id, _ = minutes(runtime, texts=(hostile, 'second'), summary='## 핵심 요약\n- <b>bold</b> point [t1, t9]\n## 할 일\n- [ ] do it [t2]\n')
    login(client, runtime, base)
    response = client.get('/notes/' + job_id)
    assert response.status_code == 200
    block = island(response.text)
    assert block is not None and '<' not in block and '>' not in block and '</script' not in block
    assert response.text.count('<script') == 2   # the module and the data block only
    data = json.loads(block)
    assert data['found'] is True and data['turns'][0]['text'] == hostile and data['turns'][1]['id'] == 't2'
    first = data['sections'][0]['items'][0]
    assert first['text'] == '<b>bold</b> point' and [c['ok'] for c in first['cites']] == [True, False]
    assert first['cites'][0] == {'id': 't1', 'ok': True, 'start': 1.0, 'end': 2.0}
    assert data['sections'][1]['kind'] == 'tasks' and data['sections'][1]['items'][0]['task'] is True
    assert data['review_reasons'] == ['unknown_citation:t9'] and data['note_state'] == 'missing'


def test_note_screen_unknown_job_and_path_like_ids(api):
    client, runtime, base = api
    login(client, runtime, base)
    for job_id in ('nope', "x'; DROP TABLE jobs;--", 'a' * 5000):
        response = client.get('/notes/' + job_id)
        assert response.status_code == 404, job_id
        data = json.loads(island(response.text))
        assert data['found'] is False and data['unknown'] is True and 'turns' not in data
    # An encoded slash makes it two path segments: no screen route matches, so there is not even a shell.
    for job_id in ('..%2f..%2fetc%2fpasswd', 'a%2fb'):
        response = client.get('/notes/' + job_id)
        assert response.status_code == 404 and island(response.text) is None
    assert client.get('/notes/a/b').status_code == 404
    with closing(store.connect(runtime.db)) as con:
        assert con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0   # the table still exists and nothing was written


@pytest.mark.parametrize('how', ['no-meta', 'tampered', 'symlink', 'malformed', 'wrong-shape'])
def test_unverified_artifacts_are_never_shown(api, tmp_path, how):
    client, runtime, base = api
    job_id, directory = minutes(runtime, skip_meta=('turns.json',) if how == 'no-meta' else (),
                                tamper=('summary.json',) if how == 'tampered' else ())
    if how == 'symlink':
        outside = tmp_path / 'outside.json'
        outside.write_text('{"text": "## 핵심 요약\\n- leaked [t1]"}')
        (directory / 'summary.json').unlink()
        (directory / 'summary.json').symlink_to(outside)
    if how == 'malformed':
        (directory / 'turns.json').write_text('{not json')
    if how == 'wrong-shape':
        part = directory / 'corrected.json.part'
        artifacts.write_json(part, {'texts': ['only one'], 'notes': []})   # fewer texts than turns
        artifacts.commit(directory / 'corrected.json', part, stage='corrected', run_id='run-1', inputs={}, params={})
    login(client, runtime, base)
    data = json.loads(island(client.get('/notes/' + job_id).text))
    assert data == {'job_id': job_id, 'found': False}


def test_deleted_and_legacy_jobs_show_no_minutes(api):
    client, runtime, base = api
    job_id, _ = minutes(runtime)
    with closing(store.connect(runtime.db)) as con:
        con.execute("UPDATE jobs SET legacy=1 WHERE job_id=?", (job_id,))
    login(client, runtime, base)
    assert json.loads(island(client.get('/notes/' + job_id).text)) == {'job_id': job_id, 'found': False}


# ---- the front-end sources are part of the policy

def test_front_end_has_no_markup_sinks(api):
    sinks = [r'\.innerHTML', r'\.outerHTML', r'insertAdjacentHTML', r'document\.write', r'\beval\s*\(', r'new\s+Function', r'setAttribute\(\s*[\'"]style',
             r'srcdoc', r'javascript:', r'createContextualFragment', r'DOMParser', r'\.srcObject', r'importScripts', r'new\s+Worker', r'XMLHttpRequest']
    for path in sorted(STATIC.rglob('*.js')):
        source = path.read_text()
        for sink in sinks:
            assert not re.search(sink, source), (path.name, sink)
        # No absolute URLs: only same-origin paths and the SVG namespace may appear.
        assert not re.findall(r'https?://(?!www\.w3\.org/2000/svg)', source), path.name
        assert not re.search(r'(?<![\w.])fetch\(\s*[\'"`]https?:', source), path.name
    css = (STATIC / 'qc.css').read_text()
    assert '@import' not in css and not re.search(r'url\(\s*[\'"]?(?:https?:|//|data:)', css)
    bootstrap = (Path(__file__).parents[1] / 'quietclerk/server/bootstrap.js').read_text()
    assert bootstrap.index("fetch('/api/session'") < bootstrap.index("location.replace('/home')")


# ---- note migration API

def legacy_note(output, job_id, filename='old.md', kind='회의'):
    path = output / filename
    path.write_text('---\nsource: "meeting.m4a"\nrecorded: 2026-11-10 10:00\nduration_min: 1.7\n'
                    f'speakers: 2\njob_id: {job_id}\ntranscribe: asr\npostprocess: codex\ntags: [회의록, 자동전사]\n유형: {kind}\n'
                    '---\n# My original title\n\n## 메모\nOriginal user body\r\n')
    return path


def vault_state(root, output):
    files = {str(p.relative_to(output)): (p.read_bytes(), p.stat().st_mtime_ns) for p in output.rglob('*') if p.is_file()}
    with closing(sqlite3.connect(root / 'state.sqlite3')) as con:
        meta = sorted(con.execute('SELECT key,value FROM meta').fetchall())
    return files, meta, (root / 'note-backups').exists()


def seed_legacy(runtime, kind='회의'):
    output = Path(runtime.settings.get('output'))
    output.mkdir(parents=True, exist_ok=True)
    with closing(store.connect(runtime.db)) as con:
        job = store.add_job(con, '20261110-100000-abc', 'abc', 'meeting.m4a', '/unused', 100)
    return output, legacy_note(output, job['job_id'], kind=kind)


def test_migration_policy_unauthenticated_is_401_and_no_csrf_is_403(api):
    client, runtime, base = api
    output, target = seed_legacy(runtime)
    before = vault_state(runtime.settings.root, output)
    assert client.get('/api/notes/migration').status_code == 401
    assert client.post('/api/notes/migration', json={'consent': True}, headers={'Origin': base}).status_code == 401
    login(client, runtime, base)
    headers = {'X-CSRF-Token': ''}
    assert client.post('/api/notes/migration', json={'consent': True}, headers=headers).status_code == 403
    assert client.post('/api/notes/migration', json={'consent': True}, headers={'Origin': 'http://attacker.test'}).status_code == 403
    assert vault_state(runtime.settings.root, output) == before


@pytest.mark.parametrize('body', [{}, {'consent': False}, {'consent': 'true'}, {'consent': 1}, {'consent': None},
                                  {'consent': True, 'extra': 1}, {'consent': [True]}, {'apply': True}])
def test_migration_policy_without_exact_consent_is_400_and_changes_nothing(live, body):
    client, runtime, base = live
    output, target = seed_legacy(runtime)
    login(client, runtime, base)
    before = vault_state(runtime.settings.root, output)
    response = client.post('/api/notes/migration', json=body)
    assert response.status_code == 400 and 'consent' in response.json()['error']
    assert vault_state(runtime.settings.root, output) == before
    assert client.post('/api/notes/migration', content=b'not json', headers={'Content-Type': 'application/json'}).status_code == 400
    assert client.post('/api/notes/migration', content=b'[true]', headers={'Content-Type': 'application/json'}).status_code == 400
    assert vault_state(runtime.settings.root, output) == before


def test_migration_preview_changes_nothing(api):
    client, runtime, base = api
    output, target = seed_legacy(runtime)
    login(client, runtime, base)
    before = vault_state(runtime.settings.root, output)
    response = client.get('/api/notes/migration')
    assert response.status_code == 200
    body = response.json()
    Draft202012Validator(SCHEMA | {'$ref': '#/$defs/MigrationState'}).validate(body)
    entry = body['preview']['entries'][0]
    assert body['migrated'] is False and body['task'] is None and entry['job_id'] == '20261110-100000-abc'
    assert {'from_key': 'recorded', 'from_value': '2026-11-10 10:00', 'to_key': 'started_at', 'to_value': '2026-11-10T10:00:00'} in entry['mapping']
    assert not body['preview']['conflicts'] or all(not c['blocking'] for c in body['preview']['conflicts'])
    assert vault_state(runtime.settings.root, output) == before and notes.parse_note(target.read_bytes())[0].get('qc_schema') is None


def test_migration_runs_on_the_executor_thread_and_reports_completion(live):
    client, runtime, base = live
    output, target = seed_legacy(runtime)
    login(client, runtime, base)
    original = target.read_bytes()
    response = client.post('/api/notes/migration', json={'consent': True})
    assert response.status_code == 200
    manifest = response.json()
    Draft202012Validator(SCHEMA | {'$ref': '#/$defs/MigrationDone'}).validate(manifest)
    assert manifest['done'] is True and manifest['entries'][0]['state'] == 'done' and 'mapping' not in manifest['entries'][0]
    props, body = notes.parse_note(target.read_bytes())
    assert props['qc_schema'] == 2 and body == notes.parse_note(original)[1]
    backup = Path(manifest['backup_dir']) / 'old.md'
    assert backup.read_bytes() == original and not backup.is_relative_to(output)
    state = client.get('/api/notes/migration').json()
    Draft202012Validator(SCHEMA | {'$ref': '#/$defs/MigrationState'}).validate(state)
    assert state['migrated'] is True and state['task'] == {'state': 'done'}
    assert not [e for e in state['preview']['entries'] if not e.get('skip')]
    assert client.post('/api/notes/migration', json={'consent': True}).status_code == 200   # idempotent: nothing left to convert


def test_migration_still_waiting_is_202_and_a_later_get_shows_it_running(api):
    client, runtime, base = api   # the runtime is not started: nothing ever runs the queued task
    output, target = seed_legacy(runtime)
    login(client, runtime, base)
    before = target.read_bytes()
    started = time.monotonic()
    response = client.post('/api/notes/migration', json={'consent': True})
    assert response.status_code == 202 and response.content == b'' and 0.9 < time.monotonic() - started < 5
    assert target.read_bytes() == before
    state = client.get('/api/notes/migration').json()
    assert state['migrated'] is False and state['task'] == {'state': 'running'}


def test_migration_conflict_is_409_with_reason(live):
    client, runtime, base = live
    output, target = seed_legacy(runtime, kind='워크숍')   # a type value the table does not know: blocking
    login(client, runtime, base)
    before = vault_state(runtime.settings.root, output)
    response = client.post('/api/notes/migration', json={'consent': True})
    assert response.status_code == 409
    body = response.json()
    Draft202012Validator(SCHEMA | {'$ref': '#/$defs/NoteConflictError'}).validate(body)
    assert body['error'] == 'note_conflict' and body['reason'] == 'migration_conflicts'
    assert vault_state(runtime.settings.root, output)[0] == before[0]
    assert client.get('/api/notes/migration').json()['task'] == {'state': 'failed', 'reason': 'migration_conflicts'}


def test_migration_preview_of_a_vault_inside_the_backup_root_is_409(api, tmp_path):
    client, runtime, base = api
    login(client, runtime, base)
    # The backup root (<root>/note-backups) may not be inside the vault.
    assert client.put('/api/settings', json={'output': str(tmp_path)}).status_code == 200
    response = client.get('/api/notes/migration')
    assert response.status_code == 409 and response.json()['reason'] == 'backup_must_be_outside_vault'


# ---- other API behaviour found while wiring the screens

def test_integration_runtime_error_is_503_not_500(api, monkeypatch):
    client, runtime, base = api
    login(client, runtime, base)

    def refuse(names, settings=None):
        raise RuntimeError('no Syncthing folder at the inbox')
    monkeypatch.setattr(backfill, 'request', refuse)
    response = client.post('/api/backlog/request', json={'names': ['a.m4a']})
    assert response.status_code == 503 and response.json() == {'error': 'local integration unavailable'}
