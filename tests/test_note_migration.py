"""IN-27 migration fixtures: original English keys and the actual demo note format.

Custom fields/values are reported, never guessed. Markerless migrated notes stay
blocked, and journal resumption neither overwrites backups nor converts twice.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from quietclerk import artifacts, executor, notes, render, store
from quietclerk.notes import migration
from quietclerk.stages import note


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / 'root'
    output = tmp_path / 'vault'
    output.mkdir()
    con = store.connect(root / 'state.sqlite3')
    yield con, root, output
    con.close()


def add(con, job_id='20261110-100000-abc', sha='abc'):
    return store.add_job(con, job_id, sha, 'meeting.m4a', '/unused', 100)


def legacy_note(output, job_id, filename='old.md'):
    path = output / filename
    path.write_text('---\nsource: "meeting.m4a"\nrecorded: 2026-11-10 10:00\nduration_min: 1.7\n'
                    f'speakers: 2\njob_id: {job_id}\ntranscribe: asr\npostprocess: codex\ntags: [회의록, 자동전사]\n'
                    '---\n# My original title\n\n## 메모\nOriginal user body\r\n')
    return path


def test_IN27_original_job_id_format_and_cli_consent(vault):
    con, root, output = vault
    job = add(con)
    target = legacy_note(output, job['job_id'])
    before = target.read_bytes()
    plan = migration.migrate(con, root, output)
    assert target.read_bytes() == before and not (root / 'note-backups').exists()
    mapping = plan['entries'][0]['mapping']
    assert {'from_key': 'job_id', 'from_value': job['job_id'], 'to_key': 'job_id', 'to_value': job['job_id']} in mapping
    assert any(r['from_key'] == 'recorded' and r['to_key'] == 'started_at' for r in mapping)
    assert plan['entries'][0]['ownership']['title'] == 'user'
    with pytest.raises(ValueError, match='consent'):
        migration.migrate(con, root, output, apply=True)
    result = migration.migrate(con, root, output, apply=True, consent=True)
    props, body = notes.parse_note(target.read_bytes())
    assert props['qc_schema'] == 2 and props['job_id'] == job['job_id'] and props['source_sha256'] == 'abc'
    assert props['source_file'] == 'meeting.m4a' and props['started_at'] == '2026-11-10T10:00:00'
    assert props['speakers'] if 'speakers' in props else props['speaker_count'] == 2
    assert props['pipeline_llm'] == ['codex'] and props['tags'] == ['meeting-notes', '자동전사']
    assert body == notes.parse_note(before)[1]
    backup = Path(result['backup_dir']) / 'old.md'
    assert backup.read_bytes() == before and not backup.is_relative_to(output)
    assert store.vault_migrated(con, output) and store.note_was_migrated(con, job['job_id'], output)
    assert migration.migrate(con, root, output, apply=True, consent=True)['done']
    assert backup.read_bytes() == before


def test_current_demo_note_and_user_edited_title_status_attendees_project(vault):
    con, root, output = vault
    demo = Path(__file__).parent / 'fixtures/legacy-v1-note.md'  # a v1 note as the old engine wrote it
    props, body = notes.parse_note(demo.read_bytes())
    add(con, props['처리_작업ID'], props['원본해시'])
    props.update(상태='검토함', 참석자=['사용자'], 프로젝트=['My custom project'])
    body = body.replace('책마루 앱 홈 화면 개편과 대출 연장 기능 개선'.encode(), b'My user title', 1)
    props['내_속성'] = {'important': True}
    target = output / 'user-renamed.md'
    target.write_bytes(render.frontmatter(props).encode() + body)
    preview = migration.preview(con, root, output)
    assert any(c['reason'] == 'custom_value' and c['value'] == 'My custom project' for c in preview['conflicts'])
    assert any(c['reason'] == 'custom_key' and c['key'] == '내_속성' for c in preview['conflicts'])
    assert not any(c['blocking'] for c in preview['conflicts'])
    migration.migrate(con, root, output, apply=True, consent=True)
    result, result_body = notes.parse_note(target.read_bytes())
    assert result['title'] == 'My user title' and result['status'] == 'reviewed'
    assert result['attendees'] == ['사용자'] and result['project'] == ['My custom project']
    assert result['내_속성'] == {'important': True} and result_body == body
    assert store.note_field_records(con, props['처리_작업ID'])['title']['owner'] == 'user'


def test_custom_enum_and_duplicate_notes_are_blocking(vault):
    con, root, output = vault
    job = add(con)
    path = legacy_note(output, job['job_id'])
    data = path.read_bytes().replace(b'source:', '상태: "My status"\nsource:'.encode())
    path.write_bytes(data)
    (output / 'copy.md').write_bytes(data)
    plan = migration.preview(con, root, output)
    assert {'custom_value', 'duplicate_job'} <= {c['reason'] for c in plan['conflicts']}
    with pytest.raises(notes.NoteConflict, match='migration_conflicts'):
        migration.migrate(con, root, output, apply=True, consent=True)
    assert path.read_bytes() == data and not store.vault_migrated(con, output)


def test_interruption_after_replace_resumes_idempotently(vault, monkeypatch):
    con, root, output = vault
    job = add(con)
    target = legacy_note(output, job['job_id'])
    before = target.read_bytes()
    write = migration._write_manifest
    def stop_after_replace(path, manifest):
        if manifest['entries'][0].get('state') == 'done':
            raise RuntimeError('simulated process interruption after rename')
        write(path, manifest)
    monkeypatch.setattr(migration, '_write_manifest', stop_after_replace)
    with pytest.raises(RuntimeError):
        migration.migrate(con, root, output, apply=True, consent=True)
    after = target.read_bytes()
    assert after != before and not store.vault_migrated(con, output)
    monkeypatch.setattr(migration, '_write_manifest', write)
    result = migration.migrate(con, root, output, apply=True, consent=True)
    assert result['done'] and target.read_bytes() == after
    assert (Path(result['backup_dir']) / 'old.md').read_bytes() == before
    assert len(list((root / 'note-backups').glob('*/old.md'))) == 1


def test_backup_inside_vault_and_symlinks_refused(vault):
    con, root, output = vault
    with pytest.raises(notes.NoteConflict, match='outside_vault'):
        migration.preview(con, root, root)
    outside = root / 'outside.md'
    job = add(con)
    outside.parent.mkdir(exist_ok=True)
    outside.write_text('---\njob_id: ' + job['job_id'] + '\n---\n')
    (output / 'link.md').symlink_to(outside)
    assert migration.preview(con, root, output)['entries'] == []


def stage_context(con, root, output):
    job = add(con)
    settings = {'root': str(root), 'output': str(output), 'language.mode': 'en', 'notes.output_language': 'same'}
    row = store.claim(con, 'boot', settings)
    work = root / 'work' / row['active_run_id']
    work.mkdir(parents=True)
    ctx = executor.Context(con, row, 'boot', settings, row['active_run_id'], work)
    values = {'turns': [{'start': 0, 'end': 4, 'speaker': 'S1', 'text': 'English speech'}],
              'correct': {'texts': ['English speech'], 'notes': []},
              'classify': {'meta': {'title': 'English meeting title', 'type': 'meeting', 'division': 'work',
                                    'type_confidence': 'high', 'speakers': {}}, 'engine': 'fake'},
              'summarize': {'text': '## Key summary\n- English speech [t1]', 'engine': 'fake'}}
    for name, value in values.items():
        path = work / (name + '.json')
        artifacts.write_json(path, value)
        ctx.paths[name] = path
    return ctx


def test_vault_before_migration_is_never_written_and_keeps_run_draft(vault):
    con, root, output = vault
    ctx = stage_context(con, root, output)
    legacy = legacy_note(output, ctx.job['job_id'])
    before = legacy.read_bytes()
    with pytest.raises(executor.Blocked, match='vault_migration'):
        note._publish(ctx, ctx.work / 'note.json.part')
    assert legacy.read_bytes() == before
    assert sorted(output.iterdir()) == [legacy] and not store.vault_migrated(con, output)
    assert (ctx.work / 'note.md').exists()


def test_migrated_markerless_note_update_is_blocked(vault):
    con, root, output = vault
    ctx = stage_context(con, root, output)
    target = legacy_note(output, ctx.job['job_id'])
    migration.migrate(con, root, output, apply=True, consent=True)
    saved = target.read_bytes()
    with pytest.raises(executor.StageFailure, match='note_update_blocked'):
        note._publish(ctx, ctx.work / 'note.json.part')
    assert target.read_bytes() == saved and (ctx.work / 'note.md').exists()
    assert store.job(con, ctx.job['job_id'])['current_run_id'] is None


def test_cli_preview_apply_and_consent(vault):
    con, root, output = vault
    env = dict(os.environ, QC_ROOT=str(root), QC_OUTPUT=str(output), QC_SETTINGS=os.devnull)
    command = [sys.executable, '-m', 'quietclerk.notes', 'migrate']
    preview = subprocess.run([*command, '--preview'], env=env, capture_output=True, text=True, timeout=20)
    assert preview.returncode == 0 and json.loads(preview.stdout)['entries'] == []
    denied = subprocess.run([*command, '--apply'], env=env, capture_output=True, text=True, timeout=20)
    assert denied.returncode != 0 and '--consent' in denied.stderr
    applied = subprocess.run([*command, '--apply', '--consent'], env=env, capture_output=True, text=True, timeout=20)
    assert applied.returncode == 0, applied.stderr
    assert store.vault_migrated(con, output) and (output / render.BASE_FILE).exists()


def test_vault_without_legacy_notes_publishes_without_consent(vault):
    con, root, output = vault
    ctx = stage_context(con, root, output)
    note._publish(ctx, ctx.work / 'note.json.part')
    assert store.vault_migrated(con, output) and ctx.note_path.exists()


def test_vault_under_a_linked_parent_is_usable_but_links_inside_are_not(tmp_path):
    real = tmp_path / 'real'
    (real / 'vault' / 'sub').mkdir(parents=True)
    (tmp_path / 'alias').symlink_to(real)
    vault = tmp_path / 'alias' / 'vault'
    assert notes.safe_path(vault, vault / 'sub' / 'a.md')
    (real / 'vault' / 'linked').symlink_to(real / 'vault' / 'sub')
    assert not notes.safe_path(vault, vault / 'linked' / 'a.md')


def test_waiting_for_migration_uses_no_attempt_and_migration_requeues(vault):
    # Rehearsal finding (Mac mini copy, 2026-11-10): the wait consumed retry attempts and
    # would have ended in a final failure if the user took a while to consent.
    con, root, output = vault
    ctx = stage_context(con, root, output)
    legacy_note(output, ctx.job['job_id'])
    with pytest.raises(executor.Blocked) as blocked:
        note._publish(ctx, ctx.work / 'note.json.part')
    ctx.record(store.fail, str(blocked.value), blocked_reason=blocked.value.reason)
    row = store.job(con, ctx.job['job_id'])
    assert (row['status'], row['blocked_reason'], row['attempts']) == ('retry_wait', 'vault_migration', 0)
    migration.migrate(con, root, output, apply=True, consent=True)
    assert store.job(con, ctx.job['job_id'])['status'] == 'queued'


def test_migration_runs_inside_a_live_serve_but_not_beside_it(vault):
    # Rehearsal finding: serve holds tick.lock for its whole life, so a separate migration
    # process can never run; it must be refused clearly and run on the serve executor thread.
    from quietclerk import config
    from quietclerk.serve import Runtime
    con, root, output = vault
    job = add(con)
    target = legacy_note(output, job['job_id'])
    class Idle:
        def __init__(self, *args): pass
        def run_one(self, **kwargs): return None
    settings = config.load(environ={'QC_ROOT': str(root), 'QC_OUTPUT': str(output)})
    runtime = Runtime(settings, support=root / 'support', label_check=lambda _: False,
                      executor_factory=Idle, scan=lambda *a, **k: None)
    runtime.start()
    try:
        with pytest.raises(notes.NoteConflict, match='engine_running'):
            migration.migrate(con, root, output, apply=True, consent=True)
        assert notes.parse_note(target.read_bytes())[0].get('qc_schema') is None
        result = runtime.submit(lambda c: migration.migrate(c, root, output, apply=True, consent=True,
                                                            execution_lock_held=True)).result(timeout=10)
        assert result['done'] and notes.parse_note(target.read_bytes())[0]['qc_schema'] == 2
    finally:
        runtime.close()
