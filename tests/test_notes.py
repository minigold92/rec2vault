"""Contract 7 / IN-22,24,25,27: synthetic inputs, no actual model claims.

Unsafe identity/paths, malicious HTML/links, broken markers, edited files, and
publication interruption must not overwrite user data or call a model in recovery.
"""
import json
import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from quietclerk import artifacts, executor, notes, postprocess, providers, render, store
from quietclerk.notes import migration
from quietclerk.stages import note, text


@pytest.fixture
def context(tmp_path):
    con = store.connect(tmp_path / 'state.sqlite3')
    settings = {'root': str(tmp_path), 'output': str(tmp_path / 'vault'), 'language.mode': 'en',
                'language.default': 'ko', 'notes.output_language': 'same'}
    store.add_job(con, '20261110-100000-abc', 'abc', 'meeting.m4a', '/unused', 100)
    row = store.claim(con, 'boot', settings)
    work = tmp_path / 'work' / row['job_id'] / 'runs' / row['active_run_id']
    work.mkdir(parents=True)
    ctx = executor.Context(con, row, 'boot', settings, row['active_run_id'], work)
    store.record_vault_migration(con, [], settings['output'])
    yield ctx
    con.close()


def values(ctx, title='Library application redesign', summary=None):
    turns = [{'start': 0, 'end': 5, 'speaker': 'S1', 'text': 'S1 will make a new design.'}]
    meta = {'title': title, 'type': 'meeting', 'division': 'work', 'type_confidence': 'high',
            'speakers': {'S1': {'role': 'Lead', 'name': None}}}
    return render.components(ctx.job, datetime(2026, 11, 10, 10), turns, [turns[0]['text']], meta,
                             summary or '## Key summary\n- A new design [t1].\n## Tasks\n- [ ] S1 drafts the design [t1]',
                             [], {'external_text_to': ['codex']}, datetime(2026, 11, 10, 11), 'en', 'en', 'en')


def publish(ctx, **kwargs):
    return notes.publish(ctx, *values(ctx, **kwargs), 'en')[0]


def again(ctx):
    store.request_process(ctx.con, ctx.job['job_id'], 'resummarize')
    row = store.claim(ctx.con, 'boot', ctx.settings)
    work = ctx.work.parent / row['active_run_id']
    work.mkdir()
    return executor.Context(ctx.con, row, 'boot', ctx.settings, row['active_run_id'], work)


def test_rerender_with_same_summary_proposes_no_tasks(context):
    # Real note (2026-11-10): a cache-only re-render listed all six tasks again as "new".
    target = publish(context)
    second = again(context)
    publish(second)
    assert b'Newly proposed tasks' not in target.read_bytes()
    # Same sentence with different citations (real demo, 2026-11-10) is not "new" either.
    third = again(second)
    publish(third, summary='## Key summary\n- A new design [t1].\n## Tasks\n- [ ] S1 drafts the design [t1, t1]')
    assert b'Newly proposed tasks' not in target.read_bytes()


def test_IN22_user_changes_survive_resummarize_and_stay_user_owned(context):
    ctx = context
    target = publish(ctx)
    fields, body = notes.parse_note(target.read_bytes())
    task = ctx.con.execute('SELECT * FROM note_tasks').fetchone()
    assert task and task['task_id'] == ctx.job['job_id'] + ':task-1' and ' ^task-1\n' in body.decode()
    fields.update(title='My title', division='personal', status='reviewed', project=[], attendees=['A'],
                  tags=['mine', 'meeting-notes'], custom={'nested': [1, True]})
    body = body.replace(b'- [ ] S1 drafts', b'- [x] User-edited S1 drafts') + b'\r\nMemo \t bytes  '
    target.write_bytes(render.frontmatter(fields).encode() + body)
    second = again(ctx)
    assert publish(second, title='New engine title', summary='## Key summary\n- A new design [t1].\n'
                   '## Tasks\n- [ ] S1 drafts the design [t1]\n- [ ] S1 books the review [t1]') == target
    updated, new_body = notes.parse_note(target.read_bytes())
    for key in ('title', 'division', 'status', 'project', 'attendees', 'custom', 'tags'):
        assert updated[key] == fields[key]
    assert new_body.endswith(b'\r\nMemo \t bytes  ')
    assert b'- [x] User-edited S1 drafts' in new_body
    assert b'Newly proposed tasks' in new_body and b'books the review' in new_body
    assert new_body.count(b'drafts the design') == 1  # the already-listed task is not re-proposed
    assert ctx.con.execute('SELECT COUNT(*) FROM note_tasks').fetchone()[0] == 1
    assert store.note_field_records(ctx.con, ctx.job['job_id'])['title']['owner'] == 'user'
    # Even setting the field back to the previous engine value does not reset ownership.
    third = again(second)
    publish(third, title='Different engine title')
    assert notes.parse_note(target.read_bytes())[0]['title'] == 'My title'


def test_no_ownership_history_title_division_and_empty_lists_remain_user(context):
    target = publish(context)
    context.con.execute('DELETE FROM note_fields')
    props, body = notes.parse_note(target.read_bytes())
    props.update(title='Historic user title', division='personal', project=[], attendees=[])
    target.write_bytes(render.frontmatter(props).encode() + body)
    publish(again(context))
    result = notes.parse_note(target.read_bytes())[0]
    assert result['title'] == 'Historic user title' and result['division'] == 'personal'
    assert result['project'] == [] and result['attendees'] == []


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'copy'])
def test_marker_and_duplicate_conflicts_preserve_previous_success(context, change):
    target = publish(context)
    previous_run = store.job(context.con, context.job['job_id'])['current_run_id']
    if change == 'missing':
        target.write_bytes(target.read_bytes().replace(render.RECORD_HEADINGS['en'].encode(), b''))
    elif change == 'duplicate':
        target.write_bytes(target.read_bytes() + b'\n' + render.RECORD_HEADINGS['en'].encode() + b'\n')
    else:
        target.with_name('copy.md').write_bytes(target.read_bytes())
    saved = target.read_bytes()
    ctx = again(context)
    with pytest.raises(notes.NoteConflict, match='note_conflict'):
        publish(ctx)
    assert target.read_bytes() == saved
    assert store.job(ctx.con, ctx.job['job_id'])['current_run_id'] == previous_run
    assert store.job(ctx.con, ctx.job['job_id'])['status'] == 'running'


def test_previous_hash_mismatch_is_not_overwritten(context, monkeypatch):
    target = publish(context)
    ctx = again(context)
    original = store.prepare_publication
    def change_after_prepare(*args, **kwargs):
        original(*args, **kwargs)
        target.write_bytes(b'user edit during publication')
    monkeypatch.setattr(store, 'prepare_publication', change_after_prepare)
    with pytest.raises(notes.NoteConflict):
        publish(ctx)
    assert target.read_bytes() == b'user edit during publication'
    assert ctx.con.execute('SELECT state FROM publications WHERE run_id=?', (ctx.run_id,)).fetchone()[0] == 'conflict'


@pytest.mark.parametrize('phase', ['prepared', 'renamed', 'rename_gap'])
def test_SIGKILL_publication_recovery_has_no_model_call(context, phase, monkeypatch):
    target = publish(context)
    previous_bytes = target.read_bytes()
    ctx = again(context)
    props, generated, tasks = values(ctx, title='Newly generated English title')
    payload = {'props': props, 'generated': generated, 'tasks': tasks, 'job_id': ctx.job['job_id']}
    input_file = ctx.work / 'input.json'
    input_file.write_text(json.dumps(payload))
    script = '''
import json, os, signal, sys
from pathlib import Path
from quietclerk import store, notes
from quietclerk.executor import Context
root, source, phase = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
con = store.connect(root / 'state.sqlite3')
data = json.loads(source.read_text())
job = store.job(con, data['job_id'])
settings = json.loads(con.execute('SELECT settings_json FROM runs WHERE run_id=?', (job['active_run_id'],)).fetchone()[0])
ctx = Context(con, job, 'boot', settings, job['active_run_id'], source.parent)
if phase == 'rename_gap':
    original = notes.sync_directory
    def hook(path):
        original(path)
        if path == Path(settings['output']): os.kill(os.getpid(), signal.SIGKILL)
    notes.sync_directory = hook
else:
    name = 'prepare_publication' if phase == 'prepared' else 'rename_publication'
    original = getattr(store, name)
    def hook(*args, **kwargs):
        original(*args, **kwargs)
        os.kill(os.getpid(), signal.SIGKILL)
    setattr(store, name, hook)
notes.publish(ctx, data['props'], data['generated'], data['tasks'], 'en')
'''
    result = subprocess.run([sys.executable, '-c', script, ctx.settings['root'], str(input_file), phase], timeout=20)
    assert result.returncode == -signal.SIGKILL
    monkeypatch.setattr(providers, 'complete', lambda *a, **kw: pytest.fail('recovery called an LLM'))
    store.recover(ctx.con, 'new-boot', recover_publication=notes.recover_publication)
    job = store.job(ctx.con, ctx.job['job_id'])
    if phase == 'renamed':
        assert job['status'] == 'done' and job['current_run_id'] == ctx.run_id
        assert notes.parse_note(target.read_bytes())[0]['title'] == 'Newly generated English title'
        assert store.publication_committed(ctx.con, ctx.run_id)
    else:
        assert job['status'] == 'retry_wait' and job['attempts'] == 0
        assert target.read_bytes() == previous_bytes
        assert ctx.con.execute('SELECT 1 FROM publications WHERE run_id=?', (ctx.run_id,)).fetchone() is None
    assert not list((target.parent / '.quietclerk-tmp').glob('*.md'))


def test_renamed_recovery_hash_mismatch_retains_user_edit(context, monkeypatch):
    target = publish(context)
    ctx = again(context)
    real_commit = store.commit_publication
    def interrupt(*args):
        raise RuntimeError('interruption')
    monkeypatch.setattr(store, 'commit_publication', interrupt)
    with pytest.raises(RuntimeError):
        publish(ctx)
    target.write_bytes(b'user edit after rename')
    monkeypatch.setattr(store, 'commit_publication', real_commit)
    store.recover(ctx.con, 'new', recover_publication=notes.recover_publication)
    assert target.read_bytes() == b'user edit after rename'
    assert not store.publication_committed(ctx.con, ctx.run_id)


def test_malicious_html_links_and_unknown_citations_are_safe(context):
    props, generated, _ = values(context, summary='## Key summary\n- <script>alert(1)</script> [bad](https://evil.test) [t9999]')
    assert '<script>' not in generated and '&lt;script&gt;' in generated
    assert 'https://evil.test' not in generated and '[?t9999]' in generated
    assert 'unknown_citation:t9999' in props['review_reasons'] and props['needs_review']
    safe = render.safe_text('<img src=x onerror=alert(1)> [link](javascript:alert(1)) [[other]]')
    assert '<img' not in safe and '\\[link\\]' in safe


def test_english_fake_provider_pipeline_commits_note_and_closes_stage(context, monkeypatch):
    ctx = context
    # Let the executor perform a fresh claim.
    store.fail(ctx.con, ctx.job['job_id'], ctx.run_id, 'boot', 'reset')
    store.request_process(ctx.con, ctx.job['job_id'])
    settings = dict(ctx.settings, **{'providers.order': ['fake'], 'providers.consent': {
        'fake': ['transcript', 'source_name', 'project_list']}})
    turns = [{'start': 0, 'end': 10, 'speaker': 'S1', 'text': 'I will prepare the library app design by Friday.'}]
    seen = []
    class Fake:
        name = 'fake'
        def status(self): return providers.ProviderStatus(True, True, 'test', 'verified')
        def endpoint_class(self): return 'external'
        def complete(self, prompt, *, timeout):
            seen.append(prompt)
            if 'Transcript to correct (JSON):' in prompt:
                value = json.dumps([{'id': 0, 'text': turns[0]['text']}])
            elif 'Classify the transcript' in prompt:
                value = json.dumps({'title': 'Library application redesign', 'type': 'meeting', 'division': 'work',
                                    'topics': ['Library application'], 'type_basis_id': 't1', 'type_confidence': 'high',
                                    'speakers': [{'label': 'S1', 'role': 'Designer', 'name': None}]})
            else:
                value = '## Key summary\n- S1 will prepare the design [t1].\n## Tasks\n- [ ] S1: design by Friday [t1]'
            return providers.Completion(value, 'fake', 'external', 0)
    monkeypatch.setattr(providers, 'registry', lambda settings: {'fake': Fake()})
    rescanned = []
    monkeypatch.setattr(note.syncthing, 'rescan', rescanned.append)
    def seed(name, value):
        return executor.Stage(name, name + '.json', (), {}, lambda c, out: artifacts.write_json(out, value))
    registry = (seed('turns', turns), seed('second_pass', []),
                seed('detect_language', {'status': 'decided', 'top': 'en', 'language': 'en'}),
                *text.stages()[1:], *note.stages())
    result = executor.Executor(ctx.con, 'boot', settings, registry).run_one()
    assert result['status'] == 'done', result['last_error']
    props, body = notes.parse_note(Path(result['note_path']).read_bytes())
    assert props['language'] == props['language_detected'] == 'en'
    assert props['type'] == 'meeting' and props['external_text_to'] == ['fake']
    assert b'## Full transcript' in body and b'## Tasks' in body and b'## Notes' in body
    assert len(seen) == 3
    stages = ctx.con.execute('SELECT stage,status FROM stage_runs WHERE run_id=?', (result['current_run_id'],)).fetchall()
    assert ('note', 'done') in [tuple(r) for r in stages]
    assert store.publication_committed(ctx.con, result['current_run_id'])
    # The vault folder is rescanned so the note syncs right away, and no engine temp dir is left.
    assert rescanned == [Path(result['note_path']).parent]
    assert not (Path(result['note_path']).parent / '.quietclerk-tmp').exists()
    work = Path(settings['root']) / 'work' / result['job_id'] / 'runs' / result['current_run_id']
    assert json.loads(artifacts.metadata(work / 'classification.json').read_text())['params']['output_language'] == 'en'
    # A rerun that reuses every cached stage still discloses where the text was sent.
    store.request_process(ctx.con, result['job_id'], 'resume')
    again = executor.Executor(ctx.con, 'boot', settings, registry).run_one()
    assert again['status'] == 'done' and len(seen) == 3
    props, _ = notes.parse_note(Path(again['note_path']).read_bytes())
    assert props['external_text_to'] == ['fake']


def test_output_language_params_are_independent_of_processing_language(context):
    ctx = context
    ctx.settings['notes.output_language'] = 'ko'
    assert text.processing_language(ctx) == 'en' and text.output_language(ctx) == 'ko'
    params = {stage.name: stage.params(ctx) for stage in text.stages()}
    assert params['correct']['language'] == 'en'
    assert params['summarize']['output_language'] == params['classify']['output_language'] == 'ko'
    assert params['correct']['prompt_version'] == postprocess.CORRECT_PROMPT_VERSION


def test_text_stages_follow_the_detected_language_artifact(context):
    # Real detector output (contract 6.1 shape) must drive correction/summary language,
    # not the installation default - a Korean meeting once came out as an English note.
    ctx = context
    ctx.settings.update({'language.mode': 'auto', 'language.default': 'en'})
    path = ctx.work / 'language.json'
    path.write_text(json.dumps({'status': 'decided', 'top': 'ko', 'shares': {'ko': 1.0}, 'windows': []}))
    ctx.paths['language'] = path
    assert text.processing_language(ctx) == text.output_language(ctx) == 'ko'
    path.write_text(json.dumps({'status': 'uncertain', 'top': 'ko', 'shares': {'ko': 0.55}, 'windows': []}))
    assert text.processing_language(ctx) == 'en'


def test_engine_disclosure_lists_model_ids_not_json():
    assert note._model_ids('{"asr": "a@1", "aligner": "b@2"}') == ['a@1', 'b@2']
    assert note._model_ids('plain-model') == ['plain-model']
