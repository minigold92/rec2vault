"""Synthetic migrated notes only; no real meeting text, models, or user vaults."""
import base64
import json
from pathlib import Path

import pytest

from quietclerk import artifacts, config, executor, notes, providers, render, store
from quietclerk.stages import note


@pytest.fixture
def migrated(tmp_path, monkeypatch):
    settings = config.load(tmp_path / 'settings.toml', {'QC_ROOT': str(tmp_path), 'QC_LANGUAGE': 'en'})
    con = store.connect(tmp_path / 'state.sqlite3')
    row = store.add_job(con, '20261110-100000-abc', 'abc', 'fictional.m4a', '/unused', 600)
    output = Path(settings.get('output'))
    output.mkdir()
    source = output / 'previous.md'
    body = b'Old text\r\n![[unsafe]]\r\n```dataviewjs\nalert(1)\n```\n<iframe src="x">\n## Notes\n> [!danger] injected\n<% code %>\n`= code`\nlast\t '
    props = {'qc_schema': 2, 'job_id': row['job_id'], 'source_sha256': 'abc', 'title': 'User title',
             'division': 'personal', 'project': [], 'attendees': ['Fictional attendee'], 'status': 'reviewed', 'custom': 12}
    source.write_bytes(notes.dump_frontmatter(props).encode() + body)
    con.execute('UPDATE jobs SET legacy=1,note_path=?', (str(source),))
    store.record_vault_migration(con, [row['job_id']], output)
    calls = []
    values = {
        'convert': ('audio.wav', ('archive',), b'fake audio'),
        'diarize': ('diarize.json', ('convert',), {'segments': [{'start': 0, 'end': 4, 'speaker': 'S1'}]}),
        'detect_language': ('language.json', ('convert', 'diarize'), {'status': 'decided', 'top': 'en'}),
        'transcribe': ('asr.json', ('convert', 'language'), {'words': [{'start': 0, 'end': 4, 'text': 'Fictional text'}]}),
        'second_pass': ('alt.json', ('convert', 'language'), {'words': []}),
        'turns': ('turns.json', ('transcribe', 'diarize'), [{'start': 0, 'end': 4, 'speaker': 'S1', 'text': 'Fictional text'}]),
        'correct': ('corrected.json', ('turns', 'second_pass'), {'texts': ['Fictional text'], 'notes': []}),
        'classify': ('classification.json', ('correct', 'source_name'), {'meta': {'title': 'Generated title', 'type': 'meeting', 'division': 'work', 'speakers': {}, 'type_confidence': 'high'}}),
        'summarize': ('summary.json', ('correct', 'classify'), {'text': '## Key summary\n- Fictional text [t1]', 'review_reasons': []}),
    }
    versions = {}
    stages = []
    for name, (filename, inputs, value) in values.items():
        def execute(ctx, out, name=name, value=value):
            calls.append(name)
            out.write_bytes(value) if isinstance(value, bytes) else artifacts.write_json(out, value)
        stages.append(executor.Stage(name, filename, inputs, lambda c, name=name: {'revision': versions.get(name, 'one')}, execute))
    registry = (*stages, *note.stages())
    monkeypatch.setattr(providers, 'complete', lambda *a, **kw: pytest.fail('conversion called an LLM'))
    result = executor.Executor(con, 'boot', settings, registry).run_one()
    yield con, settings, result, source, body, calls, versions, registry
    con.close()


def test_migrated_conflict_waits_without_attempt_or_automatic_retry(migrated):
    con, settings, row, source, body, calls, versions, registry = migrated
    assert (row['status'], row['blocked_reason'], row['attempts']) == ('retry_wait', 'note_update_blocked', 0)
    assert executor.Executor(con, 'boot', settings, registry).run_one(now=1e20) is None
    assert notes.parse_note(source.read_bytes())[1] == body


@pytest.mark.parametrize('change', [None, 'revision', 'corrupt'])
def test_failed_legacy_run_reuses_verified_completed_stages(migrated, change):
    con, settings, row, source, body, calls, versions, registry = migrated
    calls.clear()
    if change == 'revision':
        versions['transcribe'] = 'two'
    elif change == 'corrupt':
        run_id = con.execute('SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1').fetchone()[0]
        path = settings.root / 'work' / row['job_id'] / 'runs' / run_id / 'asr.json'
        path.write_bytes(b'corrupt')
    store.request_process(con, row['job_id'], 'resume')
    executor.Executor(con, 'boot', settings, registry).run_one()
    assert calls == ([] if change is None else ['transcribe'])


def conversion():
    from quietclerk.notes import conversion
    return conversion


def snapshot(root, con):
    return ({str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file() and p.suffix not in ('.sqlite3',) and '-wal' not in p.name and '-shm' not in p.name},
            list(con.iterdump()))


def test_conversion_preview_is_read_only_and_consent_required(migrated):
    con, settings, row, source, body, *_ = migrated
    before = snapshot(settings.root, con)
    preview = conversion().preview(con, settings, row['job_id'])
    assert preview['current_path'] == str(source)
    assert Path(preview['new_path']).name == '2026-11-10_1000_User_title.md'
    assert base64.b64decode(preview['previous_body_b64']) == body
    assert 'Fictional text' in preview['summary']
    with pytest.raises(ValueError, match='consent'):
        conversion().apply(con, settings, row['job_id'], consent=False, preview_token=preview['preview_token'])
    assert snapshot(settings.root, con) == before


def test_conversion_preserves_backup_fields_body_and_allows_rerender(migrated):
    con, settings, row, source, body, calls, versions, registry = migrated
    saved = source.read_bytes()
    preview = conversion().preview(con, settings, row['job_id'])
    result = conversion().apply(con, settings, row['job_id'], consent=True, preview_token=preview['preview_token'])
    target = Path(result['note_path'])
    assert not source.exists() and list(target.parent.glob('*.md')) == [target]
    assert Path(result['backup_path']).read_bytes() == saved
    assert '-convert' in Path(result['backup_path']).parent.name
    props, rendered = notes.parse_note(target.read_bytes())
    assert {key: props[key] for key in ('title', 'division', 'status', 'project', 'attendees', 'custom')} == {
        'title': 'User title', 'division': 'personal', 'status': 'reviewed', 'project': [], 'attendees': ['Fictional attendee'], 'custom': 12}
    assert b'> [!note]- Previous format body (' in rendered
    assert b'Base64' not in rendered
    assert b'![[unsafe]]' not in rendered and b'```dataviewjs' not in rendered and b'<iframe' not in rendered and b'<%' not in rendered
    assert rendered.count(b'\n## Notes\n') == 1
    updated = store.job(con, row['job_id'])
    assert (updated['status'], updated['blocked_reason'], updated['legacy']) == ('done', None, 0)
    assert not store.note_was_migrated(con, row['job_id'], target.parent)
    memo = rendered[rendered.index(b'\n## Notes\n'):]
    calls.clear()
    store.request_process(con, row['job_id'], 'resummarize')
    assert executor.Executor(con, 'boot', settings, registry).run_one()['status'] == 'done'
    assert calls == ['classify', 'summarize']
    assert notes.parse_note(target.read_bytes())[1].endswith(memo)


@pytest.mark.parametrize('change', ['missing', 'hash', 'ok', 'stage', 'inputs', 'note', 'newer_run', 'collision'])
def test_conversion_rejects_unverified_or_changed_inputs(migrated, change):
    con, settings, row, source, body, *_ = migrated
    preview = conversion().preview(con, settings, row['job_id'])
    path = settings.root / 'work' / row['job_id'] / 'runs' / preview['run_id'] / 'summary.json'
    if change == 'missing':
        path.unlink()
    elif change == 'hash':
        path.write_text('{}')
    elif change in ('ok', 'stage', 'inputs'):
        meta = json.loads(artifacts.metadata(path).read_text())
        meta[change] = {'bad': 'hash'} if change == 'inputs' else False if change == 'ok' else 'wrong'
        artifacts.write_json(artifacts.metadata(path), meta)
    elif change == 'note':
        source.write_bytes(source.read_bytes() + b'user edit')
    elif change == 'collision':
        Path(preview['new_path']).write_bytes(b'belongs to somebody else')
    else:
        store.request_process(con, row['job_id'], 'resume')
        claimed = store.claim(con, 'other', settings)
        store.fail(con, row['job_id'], claimed['active_run_id'], 'other', 'synthetic', retryable=False)
    before = source.read_bytes()
    with pytest.raises(notes.NoteConflict):
        conversion().apply(con, settings, row['job_id'], consent=True, preview_token=preview['preview_token'])
    assert source.read_bytes() == before
    assert not (settings.root / 'note-backups').exists()


@pytest.mark.parametrize('phase', ['claim', 'prepared', 'rename_gap', 'renamed'])
def test_conversion_sigkill_recovers_without_models(migrated, phase, monkeypatch):
    import signal
    import subprocess
    import sys
    con, settings, row, source, body, *_ = migrated
    preview = conversion().preview(con, settings, row['job_id'])
    saved = source.read_bytes()
    script = r'''
import json, os, signal, sys
from pathlib import Path
from quietclerk import config, store, notes
from quietclerk.notes import conversion
root, job_id, token, phase = sys.argv[1:]
settings = config.load(Path(root) / 'settings.toml', {'QC_ROOT': root, 'QC_LANGUAGE': 'en'})
con = store.connect(Path(root) / 'state.sqlite3')
name = {'claim': 'begin_note_conversion', 'prepared': 'prepare_publication', 'renamed': 'rename_publication'}.get(phase)
if name:
    original = getattr(store, name)
    def stop(*a, **kw):
        original(*a, **kw)
        os.kill(os.getpid(), signal.SIGKILL)
    setattr(store, name, stop)
else:
    original = notes.sync_directory
    def stop(path):
        original(path)
        if path == Path(settings.get('output')): os.kill(os.getpid(), signal.SIGKILL)
    notes.sync_directory = stop
conversion.apply(con, settings, job_id, consent=True, preview_token=token)
'''
    result = subprocess.run([sys.executable, '-c', script, str(settings.root), row['job_id'], preview['preview_token'], phase], timeout=20)
    assert result.returncode == -signal.SIGKILL
    store.recover(con, 'new-boot', recover_publication=notes.recover_publication)
    current = store.job(con, row['job_id'])
    target = Path(preview['new_path'])
    if phase == 'renamed':
        assert current['status'] == 'done' and current['legacy'] == 0
        assert target.is_file() and not source.exists()
        assert b'> [!note]- ' in target.read_bytes()
    else:
        assert current['status'] == row['status'] and current['blocked_reason'] == row['blocked_reason']
        assert source.read_bytes() == saved and not target.exists()
        # A fresh preview after recovery can still complete the same execution.
        fresh = conversion().preview(con, settings, row['job_id'])
        conversion().apply(con, settings, row['job_id'], consent=True, preview_token=fresh['preview_token'])
    assert not con.execute("SELECT 1 FROM meta WHERE key LIKE 'note_conversion:%'").fetchone()


def test_conversion_failed_max_attempts_and_daily_search_hooks(migrated):
    from quietclerk import search
    con, settings, row, source, body, *_ = migrated
    con.execute("UPDATE jobs SET status='failed',last_error='max_attempts',blocked_reason=NULL,attempts=3")
    output = source.parent
    (output / '.obsidian').mkdir()
    settings = config.Settings(settings.snapshot() | {'daily_note.path': 'Daily/{date}.md'}, {}, frozenset(), settings.path)
    daily = output / 'Daily/2026-11-10.md'
    daily.parent.mkdir()
    daily.write_text('## Meetings\n- 10:00 [[previous|Custom alias]]\nUnchanged text\n')
    preview = conversion().preview(con, settings, row['job_id'])
    result = conversion().apply(con, settings, row['job_id'], consent=True, preview_token=preview['preview_token'])
    assert store.job(con, row['job_id'])['status'] == 'done'
    target = Path(result['note_path'])
    assert daily.read_text() == f'## Meetings\n- 10:00 [[{target.stem}|Custom alias]]\nUnchanged text\n'
    assert search.query(con, 'Fictional')['total'] > 0


@pytest.mark.parametrize('mode', ['resummarize', 'from_transcribe'])
def test_automatic_retry_reuses_completed_forced_mode_stages(migrated, mode):
    from dataclasses import replace
    con, settings, row, source, body, calls, versions, registry = migrated
    if mode == 'resummarize':
        versions.update(transcribe='two', diarize='two', correct='two')
    def fail(ctx, out):
        raise executor.StageFailure('temporary publication issue')
    runner = executor.Executor(con, 'boot', settings, (*registry[:-1], replace(registry[-1], execute=fail)))
    store.request_process(con, row['job_id'], mode)
    failed = runner.run_one()
    assert failed['attempts'] == 1
    calls.clear()
    assert runner.run_one(now=1e20)['attempts'] == 2
    assert calls == []


def test_generic_note_conflict_also_waits_without_attempt(migrated):
    con, settings, row, source, body, calls, versions, registry = migrated
    con.execute("DELETE FROM meta WHERE key LIKE 'note_migrated:%'")
    store.request_process(con, row['job_id'], 'resume')
    result = executor.Executor(con, 'boot', settings, registry).run_one()
    assert (result['status'], result['blocked_reason'], result['attempts']) == ('retry_wait', 'note_conflict', 0)


def test_cache_params_use_metadata_json_representation(tmp_path):
    path, part = tmp_path / 'out', tmp_path / 'out.part'
    params = {'models': {'asr': 'fictional@revision'}, 'segments': [(0, 1)]}
    part.write_bytes(b'output')
    artifacts.commit(path, part, stage='transcribe', run_id='one', inputs={}, params=params)
    assert artifacts.reusable(path, 'transcribe', {}, params)
    assert not artifacts.reusable(path, 'transcribe', {}, params | {'models': {'asr': 'fictional@other'}})


def test_conversion_api_security_consent_idempotency_and_schema(migrated, tmp_path):
    from jsonschema import Draft202012Validator
    from starlette.testclient import TestClient
    from quietclerk.bootstrap_file import read_bootstrap
    from quietclerk.serve import Runtime
    from quietclerk.server import create_app
    con, settings, row, source, body, *_ = migrated
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False)
    app = create_app(runtime, start_runtime=False, provider_registry=lambda _: {})
    base = f"http://127.0.0.1:{settings.get('server.port')}"
    path = f"/api/jobs/{row['job_id']}/convert-note"
    schema = json.loads((Path(__file__).parents[1] / 'quietclerk/server/schema.json').read_text())
    with TestClient(app, base_url=base) as client:
        assert client.get(path).status_code == 401
        response = client.post('/api/session', json={'token': read_bootstrap(runtime.support)['token']}, headers={'Origin': base})
        csrf = response.headers['X-CSRF-Token']
        before = snapshot(settings.root, con)
        preview = client.get(path)
        assert preview.status_code == 200
        Draft202012Validator(schema | {'$ref': '#/$defs/NoteConversionPreview'}).validate(preview.json())
        assert snapshot(settings.root, con) == before
        payload = {'consent': True, 'preview_token': preview.json()['preview_token']}
        assert client.post(path, json=payload, headers={'Origin': base}).status_code == 403
        assert client.post(path, json=payload, headers={'Origin': 'http://foreign.invalid', 'X-CSRF-Token': csrf}).status_code == 403
        client.headers.update({'Origin': base, 'X-CSRF-Token': csrf})
        for bad in ({}, payload | {'consent': False}, payload | {'consent': 1}, payload | {'extra': 1}):
            assert client.post(path, json=bad).status_code == 400
        assert snapshot(settings.root, con) == before
        response = client.post(path, json=payload, headers={'Idempotency-Key': 'convert-once'})
        assert response.status_code == 200, response.text
        Draft202012Validator(schema | {'$ref': '#/$defs/NoteConversionDone'}).validate(response.json())
        assert client.post(path, json=payload, headers={'Idempotency-Key': 'convert-once'}).json() == response.json()
        assert len(list((settings.root / 'note-backups').glob('*-convert'))) == 1
        assert client.post(path, json=payload | {'consent': False}, headers={'Idempotency-Key': 'convert-once'}).status_code == 409


@pytest.fixture(scope='module')
def conversion_ui_harness(tmp_path_factory):
    from test_server_screens import UPDATE_UI_HARNESS
    script = r'''
scenarios.noteConversion = async (params) => {
  FakeElement.prototype.closest = function(sel) {
    for (let n = this; n && n.nodeType === 1; n = n.parentNode) {
      if (matches(n, compound(sel))) return n;
    }
    return null;
  };
  const w = await boot({lang: params.lang, screen: params.screen});
  let row = params.row;
  routes['GET /api/jobs?limit=200'] = () => reply(200, {items: [row], next_cursor: null});
  routes['GET /api/providers'] = () => reply(200, {items: []});
  routes['GET /api/settings'] = () => reply(200, {effective: {}});
  routes['GET /api/setup/checks'] = () => reply(200, {disk_free_bytes: 10000000000});
  routes[`GET /api/jobs/${row.job_id}`] = () => reply(200, {job: row, runs: []});
  routes[`GET /api/jobs/${row.job_id}/convert-note`] = () => reply(200, params.preview);
  routes[`POST /api/jobs/${row.job_id}/convert-note`] = () => {
    row = {...row, status: 'done', legacy: 0, blocked_reason: null};
    return reply(200, {backup_path: '/synthetic/note-backups/utc-convert/previous.md'});
  };
  if (params.screen === 'note') {
    const data = document.createElement('script');
    data.setAttribute('id', 'qc-data'); data.textContent = JSON.stringify({found: false});
    document.body.append(data);
  }
  await (await load(`screens/${params.screen}.js`)).mount({...w.shell, jobId: row.job_id});
  await settle();
  const before = text(w.shell.content);
  const button = qa('button').find((b) => /^(새 형식으로 바꾸기|Convert to new format)$/.test(text(b)));
  if (!button) throw new Error('no conversion action: ' + before);
  button.click(); await settle();
  const panel = qa('section').find((n) => n.getAttribute('aria-label') === (params.lang === 'ko' ? '노트 교체 미리보기' : 'Note conversion preview'));
  const previewText = text(panel);
  const apply = panel.querySelectorAll('button').find((b) => /^(동의하고|Consent and)/.test(text(b)));
  const disabled = apply.disabled;
  apply.click(); await settle();
  const beforeConsent = posts().filter((p) => p.path.endsWith('/convert-note')).length;
  const check = panel.querySelector('input');
  check.checked = true; check.dispatchEvent({type: 'change'});
  apply.click(); apply.click(); await settle();
  return {before, previewText, disabled, beforeConsent, after: text(w.shell.content), posts: posts(),
    injected: panel.querySelectorAll('iframe, script, img').length};
};
'''
    marker = 'const out = await scenarios[scenario](params);'
    path = tmp_path_factory.mktemp('conversion-ui') / 'harness.mjs'
    path.write_text(UPDATE_UI_HARNESS.replace(marker, script + '\n' + marker))
    return path


@pytest.mark.parametrize('lang', ['ko', 'en'])
@pytest.mark.parametrize('screen', ['home', 'jobs', 'note'])
def test_conversion_buttons_preview_and_consent_in_both_languages(migrated, conversion_ui_harness, lang, screen):
    from test_server_screens import run_ui
    con, settings, row, source, body, *_ = migrated
    preview = conversion().preview(con, settings, row['job_id'])
    preview['previous_body'] += '\n<iframe>unsafe</iframe><img src=x>'
    result = run_ui(conversion_ui_harness, 'noteConversion', lang=lang, screen=screen, row=dict(row), preview=preview)
    assert ('새 형식으로 바꾸기' if lang == 'ko' else 'Convert to new format') in result['before']
    assert ('자동 재시도하지' if lang == 'ko' else 'No automatic retry') in result['before']
    assert preview['current_path'] in result['previewText'] and preview['new_path'] in result['previewText']
    assert '<iframe>unsafe</iframe>' in result['previewText'] and result['injected'] == 0
    assert result['disabled'] and result['beforeConsent'] == 0
    posted = [p for p in result['posts'] if p['path'].endswith('/convert-note')]
    assert len(posted) == 1 and posted[0]['body'] == {'consent': True, 'preview_token': preview['preview_token']}
    assert posted[0]['csrf'] == 'csrf-1' and posted[0]['key']
    assert ('새 형식으로 바꿨어요' if lang == 'ko' else 'Converted to the new format') in result['after']


@pytest.mark.parametrize('mode,forced', [('resummarize', 'classify'), ('from_transcribe', 'transcribe')])
def test_retry_cannot_reuse_forced_work_from_before_user_request(migrated, mode, forced):
    from dataclasses import replace
    con, settings, row, source, body, calls, versions, registry = migrated
    old = next(stage for stage in registry if stage.name == forced)
    first = [True]
    def fail_once(ctx, out):
        if first[0]:
            first[0] = False
            raise executor.StageFailure('temporary stage issue')
        return old.execute(ctx, out)
    registry = tuple(replace(stage, execute=fail_once) if stage.name == forced else stage for stage in registry)
    store.request_process(con, row['job_id'], mode)
    runner = executor.Executor(con, 'boot', settings, registry)
    assert runner.run_one()['attempts'] == 1
    calls.clear()
    runner.run_one(now=1e20)
    assert forced in calls


@pytest.mark.parametrize('change', ['identity', 'edit', 'collision'])
def test_conversion_rechecks_note_after_backup(migrated, monkeypatch, change):
    con, settings, row, source, body, *_ = migrated
    preview = conversion().preview(con, settings, row['job_id'])
    original = conversion().durable_write
    def change_after_backup(path, data):
        original(path, data)
        if change == 'identity':
            props, text = notes.parse_note(source.read_bytes())
            props['source_sha256'] = 'other'
            source.write_bytes(notes.dump_frontmatter(props).encode() + text)
        elif change == 'edit':
            source.write_bytes(source.read_bytes() + b'fresh user edit')
        else:
            Path(preview['new_path']).write_bytes(b'another note')
    monkeypatch.setattr(conversion(), 'durable_write', change_after_backup)
    with pytest.raises(notes.NoteConflict):
        conversion().apply(con, settings, row['job_id'], consent=True, preview_token=preview['preview_token'])
    assert source.is_file()
    assert store.job(con, row['job_id'])['status'] == row['status']
    if change == 'edit':
        assert source.read_bytes().endswith(b'fresh user edit')
    if change == 'collision':
        assert Path(preview['new_path']).read_bytes() == b'another note'
