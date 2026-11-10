"""Contract 10.8 A/B — synthetic inputs only; no real recording/model claims.

Input type / policy / exercised cases
-----------------------------------
Name, line text / trim, bounded, reject Unicode C / empty, long, NUL, bidi, newline
Labels, line IDs / existing meeting-local IDs only / traversal, missing, other job
JSON / exact keys, strict boolean/string/null / wrong types, extra keys, malformed
Links and plugins / inert renderer, no name replacement inside links / HTML, wiki, URL
Artifacts and notes / verified hash, identity, no symlinks / tamper, duplicate, escape
Running/deleted jobs / reject before mutation / 409 job_running, no overlay saved
Concurrent writes / optimistic job revision + journal claim / parallel API requests
Scratch / discard changed speaker mapping or original hash / committed review reasons
Publication / journal rollback/recovery, user bytes preserved / prepared, renamed, hash race
Summary-only / edited text and merge, not confirmed name, sent to fake LLM / captured args
Demo / loopback uvicorn, temporary root, stored fictional meeting / names, merge, edit

Verification level: synthetic assumptions and real local HTTP/file/SQLite execution,
not actual audio, ASR, or external LLM validation. No samples or operating vault used.
"""
import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import uvicorn
from jsonschema import Draft202012Validator
from starlette.testclient import TestClient

from quietclerk import artifacts, config, executor, hooks, notes, overrides, render, store
from quietclerk.bootstrap_file import read_bootstrap
from quietclerk.server import create_app
from quietclerk.serve import Runtime
from quietclerk.stages import note, text


TURNS = [
    {'start': 1., 'end': 21., 'speaker': 'S1', 'text': 'We will build the library app.'},
    {'start': 22., 'end': 30., 'speaker': 'S2', 'text': 'I will draft the screen.'},
    {'start': 31., 'end': 34., 'speaker': 'S3', 'text': 'I agree with the design.'},
]
META = {'title': 'Library app design', 'type': 'meeting', 'division': 'work', 'type_confidence': 'high',
        'speakers': {'S1': {'role': 'Lead', 'name': None},
                     'S2': {'role': 'Designer', 'name': 'EngineGuess', 'name_id': 't2'},
                     'S3': {'role': None, 'name': None}}}
SUMMARY = '## Key summary\n- S1 asked S2 to draft the design [t1, t2].\n## Tasks\n- [ ] Draft the screen [t2]'


def seed(settings, job_id='meeting', demo=False):
    root = settings.root
    with closing(store.connect(root / 'state.sqlite3')) as con:
        store.add_job(con, job_id, job_id + '-hash', 'Recording 261110_100000.m4a', '/unused', 160,
                      recorded_at='20261110-100000')
        job = store.claim(con, 'seed', settings)
        work = root / 'work' / job_id / 'runs' / job['active_run_id']
        work.mkdir(parents=True)
        values = {'turns': TURNS, 'correct': {'texts': [t['text'] for t in TURNS], 'notes': []},
                  'classify': {'meta': META}, 'summarize': {'text': SUMMARY}}
        if demo:
            directory = Path(__file__).parents[1] / 'docs/examples/demo-meeting/work'
            values = {stage: json.loads((directory / (stage + '.json')).read_text()) for stage in values}
        names = {'turns': 'turns.json', 'correct': 'corrected.json', 'classify': 'classification.json', 'summarize': 'summary.json'}
        ctx = executor.Context(con, job, 'seed', settings.snapshot(), job['active_run_id'], work)
        for stage, value in values.items():
            path = work / names[stage]
            part = Path(str(path) + '.part')
            artifacts.write_json(part, value)
            artifacts.commit(path, part, stage=stage, run_id=ctx.run_id, inputs={}, params={})
            ctx.paths[stage] = path
        store.record_vault_migration(con, [], settings.get('output'))
        props, generated, tasks = render.components(job, datetime(2026, 11, 10, 10), values['turns'], values['correct']['texts'],
                                                    values['classify']['meta'], values['summarize']['text'], [], {},
                                                    datetime(2026, 11, 10, 11), 'en', 'en', 'ko' if demo else 'en')
        target, _ = notes.publish(ctx, props, generated, tasks, 'ko' if demo else 'en')
        return target, ctx.run_id, values


@pytest.fixture
def settings(tmp_path):
    return config.load(tmp_path / 'settings.toml', environ={'QC_ROOT': str(tmp_path), 'QC_PORT': '8643'})


def authenticated(client, runtime, base):
    token = read_bootstrap(runtime.support)['token']
    result = client.post('/api/session', json={'token': token}, headers={'Origin': base})
    assert result.status_code == 204
    client.headers.update({'Origin': base, 'X-CSRF-Token': result.headers['X-CSRF-Token']})


@pytest.fixture
def api(settings):
    target, run_id, values = seed(settings)
    runtime = Runtime(settings, support=settings.root / 'support', label_check=lambda _: False)
    app = create_app(runtime, start_runtime=False, provider_registry=lambda _: {})
    base = 'http://127.0.0.1:8643'
    with TestClient(app, base_url=base) as client:
        authenticated(client, runtime, base)
        yield client, target, run_id, runtime, values


def mutate(client, path, data=None, method='PUT', **kwargs):
    response = client.request(method, '/api/jobs/meeting/' + path, json=data, **kwargs)
    assert response.status_code == 204, response.text
    return response


def test_speaker_names_merge_undo_and_user_regions(api, monkeypatch):
    client, target, original_run, runtime, _ = api
    changed = []
    monkeypatch.setattr(hooks, 'after_publish', lambda con, job: changed.append(job))
    original = target.read_bytes().replace(b'title: Library app design', b'title: My personal title')
    original = original.replace(b'- [ ] Draft', b'- [x] Draft') + b'Private memo\r\nexact bytes\n'
    target.write_bytes(original)
    _, before = notes.parse_note(original)
    lo, hi = notes.record_span(before)
    response = client.get('/api/jobs/meeting/speakers').json()['speakers']
    assert response[0]['sample'] == {'start': 1., 'end': 16.}
    assert response[2]['sample'] is None
    assert response[1]['name_source'] == 'engine' and not response[1]['confirmed']
    mutate(client, 'speakers/S1', {'name': '  Alice  ', 'confirmed': True})
    props, after = notes.parse_note(target.read_bytes())
    assert props['title'] == 'My personal title' and props['speakers'][0] == 'S1: Alice · Lead'
    assert '**[00:01] Alice (S1)**' in after.decode()
    assert '- Alice asked S2' in after.decode() and 'EngineGuess (estimated)' in after.decode()
    start, end = notes.record_span(after)
    assert before[:lo] == after[:start] and before[hi:] == after[end:]
    mutate(client, 'speakers/merge', {'from': 'S3', 'into': 'S2'}, method='POST')
    lines = client.get('/api/jobs/meeting/transcript').json()['lines']
    assert lines[2]['speaker'] == 'S2' and lines[2]['id'] == 't3' and lines[2]['text'] == TURNS[2]['text']
    assert '**[00:31] S2**' in target.read_text()
    mutate(client, 'speakers/merge', {'from': 'S3', 'into': None}, method='POST')
    assert client.get('/api/jobs/meeting/transcript').json()['lines'][2]['speaker'] == 'S3'
    mutate(client, 'speakers/S1', {'name': 'Unconfirmed', 'confirmed': False})
    assert 'Unconfirmed' not in target.read_text() and 'Alice' not in target.read_text()
    assert changed == ['meeting'] * 4
    with closing(store.connect(runtime.db)) as con:
        assert store.job(con, 'meeting')['current_run_id'] == original_run
        assert store.claim(con, 'no-fake-run', runtime.settings) is None
        assert con.execute("SELECT COUNT(*) FROM runs WHERE status='running'").fetchone()[0] == 0


def test_name_token_boundaries_and_links():
    values = {'S1': {'confirmed': True, 'name': 'Alice'}, 'S10': {'confirmed': True, 'name': 'Ten'}}
    original = 'S1 / S10 / S1a / aS1 / 한S1글 / (S1), [S1](https://x/S1) [[S1|S1]] [S1][ref] https://x/S1'
    assert render.replace_speaker_names(original, values) == 'Alice / Ten / S1a / aS1 / 한S1글 / (Alice), [S1](https://x/S1) [[S1|S1]] [S1][ref] https://x/S1'
    assert render.replace_speaker_names('S10 S1a S1', {'S1': values['S1']}) == 'S10 S1a Alice'
    # Korean particles attach directly to labels (real note, 2026-11-10).
    assert render.replace_speaker_names('S1는 S1가 S1의 S1에게', {'S1': values['S1']}) == 'Alice는 Alice가 Alice의 Alice에게'
    # ...and the particle agrees with the name's last syllable.
    ko = {'S2': {'confirmed': True, 'name': '오지안'}, 'S3': {'confirmed': True, 'name': '하나'},
          'S4': {'confirmed': True, 'name': '서울'}}
    assert (render.replace_speaker_names('S2는 S2가 S2를 S2와 S2로 S3은 S3이 S3을 S3과 S3으로 S4으로', ko)
            == '오지안은 오지안이 오지안을 오지안과 오지안으로 하나는 하나가 하나를 하나와 하나로 서울로')


def test_line_edit_reset_suggestions_and_summary_stays(api):
    client, target, _, runtime, _ = api
    before = target.read_text().split('## Full transcript')[0]
    mutate(client, 'transcript/t1', {'text': '  We will build the catalogue app.  '})
    response = client.get('/api/jobs/meeting/transcript').json()
    assert response['vocabulary_suggestions'] == [{'from': 'library', 'to': 'catalogue'}]
    assert response['lines'][0] == dict(id='t1', start=1., end=21., speaker='S1',
                                      text='We will build the catalogue app.', edited=True, original=TURNS[0]['text'])
    assert 'catalogue app.' in target.read_text() and '^t1' in target.read_text()
    # processed_at can change; the body summary and its evidence links cannot.
    assert notes.parse_note(before.encode())[1] == notes.parse_note(target.read_text().split('## Full transcript')[0].encode())[1]
    assert runtime.settings.get('vocabulary.terms') == []
    mutate(client, 'transcript/t1', method='DELETE', headers={'Idempotency-Key': 'reset'})
    restored = target.read_bytes()
    mutate(client, 'transcript/t1', method='DELETE', headers={'Idempotency-Key': 'reset'})
    assert target.read_bytes() == restored
    assert not client.get('/api/jobs/meeting/transcript').json()['lines'][0]['edited']


@pytest.mark.parametrize('path,data', [
    ('speakers/S1', {'name': '', 'confirmed': True}),
    ('speakers/S1', {'name': ' ' * 4, 'confirmed': True}),
    ('speakers/S1', {'name': 'x' * 41, 'confirmed': True}),
    ('speakers/S1', {'name': 'a\x00b', 'confirmed': True}),
    ('speakers/S1', {'name': 'a\u202eb', 'confirmed': True}),
    ('speakers/S1', {'name': 'a\nb', 'confirmed': True}),
    ('speakers/S1', {'name': None, 'confirmed': True}),
    ('speakers/S1', {'name': 'A', 'confirmed': 1}),
    ('speakers/S1', {'name': [], 'confirmed': True}),
    ('speakers/S1', {'name': 'A', 'confirmed': True, 'extra': 1}),
    ('transcript/t1', {'text': ''}), ('transcript/t1', {'text': 'x' * 2001}),
    ('transcript/t1', {'text': 'a\tb'}), ('transcript/t1', {'text': '\ud800'}),
    ('transcript/t1', {'text': 12}), ('transcript/t1', {'text': 'x', 'original': 'y'}),
])
def test_invalid_user_inputs_are_atomic(api, path, data):
    client, target, _, runtime, _ = api
    before = target.read_bytes()
    result = client.put('/api/jobs/meeting/' + path, content=json.dumps(data), headers={'Content-Type': 'application/json'})
    assert result.status_code == 400
    assert target.read_bytes() == before
    with closing(store.connect(runtime.db)) as con:
        assert con.execute('SELECT COUNT(*) FROM speaker_overrides').fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM transcript_edits').fetchone()[0] == 0


@pytest.mark.parametrize('suffix', ['speakers/S999', 'transcript/t999', 'transcript/t0', 'transcript/t01', 'transcript/..%2F..%2Fescape'])
def test_unknown_and_traversal_ids_never_touch_files(api, suffix):
    client, target, _, _, _ = api
    before = target.read_bytes()
    assert client.put('/api/jobs/meeting/' + suffix, json={'text': 'evil'}).status_code == 404
    assert client.put('/api/jobs/other/transcript/t1', json={'text': 'evil'}).status_code == 404
    assert target.read_bytes() == before


def test_running_job_and_security_and_idempotency(api):
    client, target, _, runtime, _ = api
    result = client.put('/api/jobs/meeting/transcript/t1', json={'text': 'one'}, headers={'X-CSRF-Token': 'invalid'})
    assert result.status_code == 403
    mutate(client, 'transcript/t1', {'text': 'one'}, headers={'Idempotency-Key': 'once'})
    before = target.read_bytes()
    mutate(client, 'transcript/t1', {'text': 'one'}, headers={'Idempotency-Key': 'once'})
    assert before == target.read_bytes()
    assert client.put('/api/jobs/meeting/transcript/t1', json={'text': 'two'}, headers={'Idempotency-Key': 'once'}).status_code == 409
    with closing(store.connect(runtime.db)) as con:
        store.request_process(con, 'meeting', 'resummarize')
        assert store.claim(con, 'busy', runtime.settings)
    result = client.delete('/api/jobs/meeting/transcript/t1')
    assert result.status_code == 409 and result.json()['reason'] == 'job_running'
    assert target.read_bytes() == before


def test_merge_cycle_rejected_and_chain_is_reversible(api):
    client, target, _, _, _ = api
    mutate(client, 'speakers/merge', {'from': 'S3', 'into': 'S2'}, method='POST')
    mutate(client, 'speakers/merge', {'from': 'S2', 'into': 'S1'}, method='POST')
    before = target.read_bytes()
    result = client.post('/api/jobs/meeting/speakers/merge', json={'from': 'S1', 'into': 'S3'})
    assert result.status_code == 409 and result.json()['reason'] == 'merge_cycle'
    assert client.post('/api/jobs/meeting/speakers/merge', json={'from': 'S1', 'into': 'S1'}).status_code == 400
    assert target.read_bytes() == before
    mutate(client, 'speakers/merge', {'from': 'S2', 'into': None}, method='POST')
    assert client.get('/api/jobs/meeting/transcript').json()['lines'][2]['speaker'] == 'S2'


@pytest.mark.parametrize('attack', ['note_symlink', 'duplicate', 'artifact_symlink', 'artifact_tamper', 'wrong_identity'])
def test_unsafe_note_and_artifact_paths_refused(api, attack, tmp_path):
    client, target, run_id, runtime, _ = api
    original = target.read_bytes()
    if attack == 'note_symlink':
        outside = tmp_path / 'outside.md'
        target.replace(outside)
        target.symlink_to(outside)
    elif attack == 'duplicate':
        target.with_name('copy.md').write_bytes(original)
    elif attack == 'wrong_identity':
        target.write_bytes(original.replace(b'job_id: meeting', b'job_id: another'))
    else:
        path = runtime.settings.root / 'work/meeting/runs' / run_id / 'corrected.json'
        if attack == 'artifact_symlink':
            outside = tmp_path / 'outside.json'
            path.replace(outside)
            path.symlink_to(outside)
        else:
            path.write_text('{}')
    before = target.read_bytes()
    result = client.put('/api/jobs/meeting/transcript/t1', json={'text': 'change'})
    assert result.status_code == 409
    assert target.read_bytes() == before
    with closing(store.connect(runtime.db)) as con:
        assert not con.execute('SELECT 1 FROM transcript_edits').fetchone()


def test_html_plugin_input_is_inert(api):
    client, target, _, _, _ = api
    mutate(client, 'transcript/t1', {'text': '<script>x</script> [[outside]] <% bad %> `=bad`'})
    text = target.read_text()
    assert '<script>' not in text and '&lt;script&gt;' in text
    assert '\\[\\[outside\\]\\]' in text and '<%' not in text and '`=bad`' not in text


def test_parallel_writes_are_serialized_or_conflicted(api):
    client, target, _, runtime, _ = api
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda word: client.put('/api/jobs/meeting/transcript/t1', json={'text': word}), ['first', 'second']))
    assert all(r.status_code in (204, 409) for r in responses)
    assert any(r.status_code == 204 for r in responses)
    final = client.get('/api/jobs/meeting/transcript').json()['lines'][0]['text']
    assert final in ('first', 'second') and final in target.read_text()
    with closing(store.connect(runtime.db)) as con:
        assert store.job(con, 'meeting')['status'] == 'done'
        assert not con.execute("SELECT 1 FROM publications WHERE state IN ('prepared','renamed')").fetchone()


def context_for_current(runtime):
    con = store.connect(runtime.db)
    job = store.job(con, 'meeting')
    work = runtime.settings.root / 'work/meeting/runs' / job['current_run_id']
    paths = {stage: work / name for stage, name in [('turns', 'turns.json'), ('correct', 'corrected.json'),
                                                   ('classify', 'classification.json'), ('summarize', 'summary.json')]}
    return executor.Context(con, job, 'seed', runtime.settings.snapshot(), job['current_run_id'], work, paths=paths)


def test_summary_only_uses_edits_and_merges_but_names_are_render_only(api, monkeypatch, tmp_path):
    client, _, _, runtime, _ = api
    ctx = context_for_current(runtime)
    before = overrides.fingerprint(ctx)
    mutate(client, 'speakers/S1', {'name': 'Alice', 'confirmed': True})
    assert overrides.fingerprint(ctx) == before
    mutate(client, 'transcript/t1', {'text': 'Corrected library requirement.'})
    mutate(client, 'speakers/merge', {'from': 'S3', 'into': 'S2'}, method='POST')
    assert overrides.fingerprint(ctx) != before
    seen = []
    def fake(turns, texts, meta, language, **kwargs):
        seen.append((turns, texts, meta))
        return '## Key summary\n- Corrected library requirement [t1]', 'fake'
    monkeypatch.setattr(text.postprocess, 'summarize', fake)
    text._summarize(ctx, tmp_path / 'summary.part')
    assert seen[0][0][2]['speaker'] == 'S2'
    assert seen[0][1][0] == 'Corrected library requirement.'
    assert seen[0][2]['speakers']['S1']['name'] is None
    ctx.con.close()


def test_scratch_discards_stale_overlays_at_publication(api, monkeypatch):
    client, target, _, runtime, _ = api
    mutate(client, 'speakers/S1', {'name': 'Alice', 'confirmed': True})
    mutate(client, 'transcript/t1', {'text': 'My correction'})
    with closing(store.connect(runtime.db)) as con:
        store.request_process(con, 'meeting', 'from_transcribe')
        claimed = store.claim(con, 'scratch', runtime.settings)
        work = runtime.settings.root / 'work/meeting/runs' / claimed['active_run_id']
        work.mkdir()
        ctx = executor.Context(con, claimed, 'scratch', runtime.settings.snapshot(), claimed['active_run_id'], work)
        previous = overrides.load_current(con, claimed, runtime.settings.root)
        previous['turns'][0]['speaker'] = 'S2'
        previous['correct']['texts'][0] = 'Fresh recognition differs'
        names = {'turns': 'turns.json', 'correct': 'corrected.json', 'classify': 'classification.json', 'summarize': 'summary.json'}
        for stage, value in previous.items():
            path = work / names[stage]
            artifacts.write_json(path, value)
            ctx.paths[stage] = path
        turns, texts, meta, reasons = overrides.stage_view(ctx, previous['classify']['meta'])
        assert reasons == ['speaker_overrides_dropped', 'transcript_edits_dropped']
        # A preview/drop decision is not destructive before journal commit.
        assert con.execute('SELECT 1 FROM transcript_edits').fetchone()
        props, generated, tasks = render.components(claimed, datetime(2026, 11, 10, 10), turns, texts, meta, SUMMARY, [], {},
                                                    datetime.now(), 'en', 'en', 'en', review_reasons=reasons)
        notes.publish(ctx, props, generated, tasks, 'en')
        row = store.job(con, 'meeting')
        assert set(json.loads(row['review_reasons'])) >= set(reasons)
        assert not con.execute('SELECT 1 FROM speaker_overrides').fetchone()
        assert not con.execute('SELECT 1 FROM transcript_edits').fetchone()
    assert 'Alice' not in target.read_text() and 'Fresh recognition differs' in target.read_text()


@pytest.mark.parametrize('phase', ['prepared', 'renamed'])
def test_rewrite_journal_recovery_does_not_retry_synthetic_run(api, monkeypatch, phase):
    client, target, original_run, runtime, _ = api
    before = target.read_bytes()
    real_recover = notes.recover_publication
    class Crash(BaseException):
        pass
    with closing(store.connect(runtime.db)) as con:
        row = store.job(con, 'meeting')
        payload = overrides.load_current(con, row, runtime.settings.root)
        speakers, edits = overrides._stored(con, 'meeting')
        edits['t1'] = {'line_id': 't1', 'text': 'Recovered correction', 'original_sha256': overrides._hash(TURNS[0]['text']), 'updated_at': time.time()}
        with monkeypatch.context() as patch:
            patch.setattr(overrides, 'rollback_rewrite', lambda *args: None)
            patch.setattr(notes, 'recover_publication', lambda *args: None)
            if phase == 'prepared':
                real_replace = Path.replace
                def crash_replace(path, other):
                    if path.suffix == '.md' and path.parent.name == '.quietclerk-tmp':
                        raise Crash()
                    return real_replace(path, other)
                patch.setattr(Path, 'replace', crash_replace)
            else:
                patch.setattr(store, 'commit_publication', lambda *args: (_ for _ in ()).throw(Crash()))
            with pytest.raises(Crash):
                overrides._rewrite(con, row, runtime.settings, payload, speakers, edits)
        assert store.recover(con, 'new-boot', recover_publication=real_recover) == []
        current = store.job(con, 'meeting')
        assert current['status'] == 'done' and current['current_run_id'] == original_run
        assert current['attempts'] == row['attempts'] and current['interrupt_count'] == row['interrupt_count']
        assert store.claim(con, 'next', runtime.settings) is None
        assert ('Recovered correction' in target.read_text()) == (phase == 'renamed')
        assert bool(con.execute('SELECT 1 FROM transcript_edits').fetchone()) == (phase == 'renamed')
        if phase == 'prepared':
            assert target.read_bytes() == before
        # An explicit real retry still starts from real artifacts, not the rewrite journal.
        store.request_process(con, 'meeting', 'resummarize')
        claimed = store.claim(con, 'next', runtime.settings)
        assert claimed['current_run_id'] == original_run
        assert claimed['active_run_id'] != original_run


def test_rewrite_hash_race_preserves_external_edit(api, monkeypatch):
    client, target, _, runtime, _ = api
    real_prepare = notes.sync_directory
    changed = []
    def racing_sync(path):
        real_prepare(path)
        if Path(path).name == '.quietclerk-tmp' and not changed:
            target.write_bytes(target.read_bytes() + b'User external edit\n')
            changed.append(True)
    monkeypatch.setattr(notes, 'sync_directory', racing_sync)
    result = client.put('/api/jobs/meeting/transcript/t1', json={'text': 'must not publish'})
    assert result.status_code == 409 and target.read_bytes().endswith(b'User external edit\n')
    with closing(store.connect(runtime.db)) as con:
        assert not con.execute('SELECT 1 FROM transcript_edits').fetchone()
        assert store.job(con, 'meeting')['status'] == 'done'


def test_response_contract_schemas(api):
    client, _, _, _, _ = api
    schema = json.loads((Path(__file__).parents[1] / 'quietclerk/server/schema.json').read_text())
    for path, name in [('speakers', 'Speakers'), ('transcript', 'Transcript')]:
        response = client.get('/api/jobs/meeting/' + path)
        assert response.status_code == 200
        Draft202012Validator(schema | {'$ref': '#/$defs/' + name}).validate(response.json())


def test_live_demo_http_names_merge_and_edit_without_models(settings):
    # The demo is a fictional meeting. Seed its stored text, never invoke its audio/model.
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    port = sock.getsockname()[1]
    settings = replace(settings, _values=settings.snapshot() | {'server.port': port})
    target, original_run, _ = seed(settings, demo=True)
    runtime = Runtime(settings, support=settings.root / 'support', label_check=lambda _: False)
    app = create_app(runtime, start_runtime=False, provider_registry=lambda _: {})
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    try:
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.01)
        assert server.started
        base = f'http://127.0.0.1:{port}'
        with httpx.Client(base_url=base, timeout=5) as client:
            authenticated(client, runtime, base)
            mutate(client, 'speakers/S1', {'name': '김도윤', 'confirmed': True})
            mutate(client, 'speakers/merge', {'from': 'S3', 'into': 'S2'}, method='POST')
            mutate(client, 'transcript/t3', {'text': '대출 연장 문의는 39%였습니다'})
            note_text = target.read_text()
            assert '**[00:00] 김도윤 (S1)**' in note_text
            assert '**[01:00] S2**' in note_text
            assert '대출 연장 문의는 39%였습니다' in note_text and '^t3' in note_text
            lines = client.get('/api/jobs/meeting/transcript').json()['lines']
            assert lines[2]['edited'] and lines[6]['speaker'] == 'S2'
            with closing(store.connect(runtime.db)) as con:
                assert store.job(con, 'meeting')['current_run_id'] == original_run
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
    assert not thread.is_alive()


def test_link_targets_with_nested_parentheses_and_reference_definitions():
    speakers = {'S1': {'confirmed': True, 'name': 'Alice'}}
    value = 'S1 [S1](https://host/(S1)/S1 "S1") S1\n[S1]: https://host/S1\n[[S1]]'
    assert render.replace_speaker_names(value, speakers) == 'Alice [S1](https://host/(S1)/S1 "S1") Alice\n[S1]: https://host/S1\n[[S1]]'


def test_trimmed_maximum_lengths_and_null_name_reset(api):
    client, target, _, _, _ = api
    mutate(client, 'speakers/S1', {'name': ' ' + '가' * 40 + ' ', 'confirmed': True})
    assert client.get('/api/jobs/meeting/speakers').json()['speakers'][0]['name'] == '가' * 40
    mutate(client, 'speakers/S1', {'name': None, 'confirmed': False})
    assert client.get('/api/jobs/meeting/speakers').json()['speakers'][0]['name'] is None
    mutate(client, 'transcript/t1', {'text': ' ' + '가' * 2000 + ' '})
    assert '가' * 2000 in target.read_text()


def test_deleted_job_refuses_overlay_before_cleanup(api):
    from quietclerk import store_ops
    client, target, _, runtime, _ = api
    with closing(store.connect(runtime.db)) as con:
        store_ops.request_delete_local(con, 'meeting')
    before = target.read_bytes()
    response = client.put('/api/jobs/meeting/transcript/t1', json={'text': 'must not retain'})
    assert response.status_code == 409 and response.json()['reason'] == 'processing_data_deleted'
    assert target.read_bytes() == before


def test_unchanged_scratch_keeps_overlays_and_empty_speaker_stats(api):
    client, _, _, runtime, _ = api
    mutate(client, 'speakers/S1', {'name': 'Alice', 'confirmed': True})
    mutate(client, 'transcript/t1', {'text': 'My correction'})
    ctx = context_for_current(runtime)
    turns, texts, meta, reasons = overrides.stage_view(ctx, META)
    assert reasons == [] and texts[0] == 'My correction'
    assert meta['speakers']['S1']['confirmed']
    assert overrides.speakers_response([], [], {}, {}, {}) == {'speakers': []}
    ctx.con.close()


def test_publish_hook_reindexes_search_and_links_the_daily_note(tmp_path, monkeypatch):
    """Main wiring (2026-11-10): a published note becomes searchable and is linked once from
    the daily note; a failing integration never undoes the publication."""
    from quietclerk import daily, hooks, search
    con = store.connect(tmp_path / 'state.sqlite3')
    calls = []
    monkeypatch.setattr(search, 'reindex', lambda c, job_id, root: calls.append(('search', job_id, root)))
    monkeypatch.setattr(daily, 'link', lambda settings, note, title, recorded: calls.append(('daily', title, recorded)))
    note = tmp_path / 'notes' / 'n.md'
    note.parent.mkdir()
    note.write_text("---\ntitle: '책마루 회의'\n---\nbody\n", encoding='utf-8')
    con.execute("INSERT INTO jobs(job_id,sha256,source_name,recorded_at,status,created_at,updated_at,note_path,current_run_id) "
                "VALUES('j','s','a.m4a','20261110-100000','done',0,0,?, 'r')", (str(note),))
    con.execute("INSERT INTO runs(run_id,job_id,mode,settings_json,consent_json,status,started_at) "
                "VALUES('r','j','auto','{\"daily_note.path\": \"x\"}','{}','done',0)")
    hooks.after_publish(con, 'j')
    assert calls == [('search', 'j', tmp_path), ('daily', '책마루 회의', '20261110-100000')]
    monkeypatch.setattr(search, 'reindex', lambda *a: (_ for _ in ()).throw(OSError('disk')))
    hooks.after_publish(con, 'j')  # logged, not raised
