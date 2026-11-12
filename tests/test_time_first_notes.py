"""Synthetic regression cases for chronological note names and journal recovery."""
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from quietclerk import artifacts, daily, executor, notes, render, store
from quietclerk.stages import note
from test_notes import context, publish, again
from test_server import api, settings, login


@pytest.mark.parametrize('kind,prefix', [('meeting', ''), ('memo', '메모_')])
def test_time_first_names(kind, prefix):
    assert render.note_name(datetime(2026, 11, 10, 10), 'Library design', 'Recording', kind) == (
        f'2026-11-10_1000_{prefix}Library_design.md')


def legacy(ctx, name='2026-11-10_Original_slug_1000.md'):
    target = publish(ctx)
    old = target.with_name(name)
    target.rename(old)
    store_path = str(old)
    ctx.con.execute('UPDATE jobs SET note_path=?', (store_path,))
    ctx.con.execute('UPDATE publications SET target_path=?', (store_path,))
    return old


def test_legacy_rename_preserves_slug_user_bytes_and_paths(context):
    old = legacy(context)
    props, body = notes.parse_note(old.read_bytes())
    body = body.replace(b'- [ ]', b'- [x]') + b'\r\nUser memo\t  '
    old.write_bytes(render.frontmatter(props | {'title': 'User title'}).encode() + body)
    ctx = again(context)
    new = publish(ctx)
    assert new.name == '2026-11-10_1000_Original_slug.md'
    assert not old.exists()
    before_start, before_end = notes.record_span(body)
    updated = notes.parse_note(new.read_bytes())[1]
    start, end = notes.record_span(updated)
    assert updated[:start] == body[:before_start] and updated[end:] == body[before_end:]
    assert store.job(ctx.con, ctx.job['job_id'])['note_path'] == str(new)
    assert {r[0] for r in ctx.con.execute('SELECT target_path FROM publications')} == {str(new)}


@pytest.mark.parametrize('name', ['My own name.md', '2026-11-09_Title_1000.md',
                                  '2026-11-10_Title_1001.md'])
def test_user_names_and_wrong_timestamps_are_not_renamed(context, name):
    old = legacy(context, name)
    assert publish(again(context)) == old


def test_rename_target_collision_is_not_overwritten(context):
    old = legacy(context)
    target = old.with_name('2026-11-10_1000_Original_slug.md')
    target.write_bytes(b'user collision')
    assert publish(again(context)) == old
    assert target.read_bytes() == b'user collision' and old.exists()


class Crash(BaseException):
    pass


@pytest.mark.parametrize('phase', ['prepared', 'moved', 'replaced', 'renamed'])
def test_legacy_rename_crash_recovery_leaves_one_note(context, monkeypatch, phase):
    old = legacy(context)
    previous = old.read_bytes()
    ctx = again(context)
    if phase in ('prepared', 'renamed'):
        name = 'prepare_publication' if phase == 'prepared' else 'rename_publication'
        real = getattr(store, name)
        def stop(*args, **kwargs):
            real(*args, **kwargs)
            raise Crash()
        monkeypatch.setattr(store, name, stop)
    else:
        real = notes.sync_directory
        count = [0]
        def stop(path):
            real(path)
            if Path(path) == old.parent:
                count[0] += 1
                if count[0] == (1 if phase == 'moved' else 2):
                    raise Crash()
        monkeypatch.setattr(notes, 'sync_directory', stop)
    with pytest.raises(Crash):
        publish(ctx)
    monkeypatch.undo()
    store.recover(ctx.con, 'new-boot', recover_publication=notes.recover_publication)
    paths = notes.safe_notes(old.parent)
    assert len(paths) == 1
    if phase == 'renamed':
        assert paths[0].name == '2026-11-10_1000_Original_slug.md'
        assert store.job(ctx.con, ctx.job['job_id'])['note_path'] == str(paths[0])
        assert {r[0] for r in ctx.con.execute('SELECT target_path FROM publications')} == {str(paths[0])}
    else:
        assert paths == [old] and old.read_bytes() == previous


def test_daily_legacy_stem_replacement_preserves_alias_and_other_bytes(context):
    output = Path(context.settings['output'])
    (output.parent / '.obsidian').mkdir()
    context.settings['daily_note.path'] = 'Daily/{date}.md'
    old = legacy(context)
    target = output.parent / 'Daily/2026-11-10.md'
    target.parent.mkdir(exist_ok=True)
    original = (b'User prefix\r\n## Meetings\r\n- 10:00 [[' + old.stem.encode() +
                b'|My alias]]\r\n- 11:00 [[other|Other]]\r\n## Notes\r\nKeep\t ')
    target.write_bytes(original)
    new = publish(again(context))
    assert target.read_bytes() == original.replace(old.stem.encode(), new.stem.encode())


def test_daily_disabled_does_not_touch_existing_link(context):
    old = legacy(context)
    daily_file = old.parent / 'daily.md'
    content = f'- 10:00 [[{old.stem}|Alias]]\n'.encode()
    daily_file.write_bytes(content)
    publish(again(context))
    assert daily_file.read_bytes() == content


@pytest.mark.parametrize('variant', ['bytes', 'reserialized', 'custom_view', 'invalid'])
def test_base_known_template_upgrade_and_user_edits(context, variant):
    output = Path(context.settings['output'])
    output.mkdir()
    old = render.LEGACY_BASE_TEMPLATES[0]
    if variant in ('reserialized', 'custom_view'):
        parsed = yaml.safe_load(old)
        if variant == 'custom_view':
            parsed['views'].append({'type': 'table', 'name': 'My view'})
        old = yaml.safe_dump(parsed, allow_unicode=True, sort_keys=False)
    elif variant == 'invalid':
        old = 'views: [invalid'
    path = output / render.BASE_FILE
    path.write_text(old)
    render.ensure_base(output)
    if variant in ('custom_view', 'invalid'):
        assert path.read_text() == old
    else:
        assert path.read_text() == render.BASE_TEMPLATE and path.read_text() != old
        parsed = yaml.safe_load(path.read_text())
        assert parsed['formulas']['when'] == 'date(started_at).format("YYYY-MM-DD HH:mm")'
        assert parsed['properties']['formula.when']['displayName'] == '녹음 시각'
        for view in parsed['views']:
            assert 'formula.when' in view['order'] and 'date' not in view['order']
            assert view['sort'] == [{'property': 'started_at', 'direction': 'DESC'}]


def test_resume_api_reuses_all_artifacts_and_renames_note(context, monkeypatch, api):
    ctx = context
    store.fail(ctx.con, ctx.job['job_id'], ctx.run_id, 'boot', 'seed reset')
    store.request_process(ctx.con, ctx.job['job_id'])
    seeded = {'turns': [{'start': 0, 'end': 5, 'speaker': 'S1', 'text': 'Library design.'}],
              'correct': {'texts': ['Library design.'], 'notes': []},
              'classify': {'meta': {'title': 'Library design', 'type': 'meeting', 'division': 'work',
                                   'type_confidence': 'high', 'speakers': {}}},
              'summarize': {'text': '## Key summary\n- Library design [t1]'}}
    calls = []
    def seed(name, value):
        def run(ctx, out):
            calls.append(name)
            artifacts.write_json(out, value)
        return executor.Stage(name, name + '.json', (), {}, run)
    registry = tuple(seed(k, v) for k, v in seeded.items()) + note.stages()
    monkeypatch.setattr(note.syncthing, 'rescan', lambda *_: None)
    first = executor.Executor(ctx.con, 'boot', ctx.settings, registry).run_one()
    assert first['status'] == 'done'
    current = Path(first['note_path'])
    old = current.with_name('2026-11-10_Library_design_1000.md')
    current.rename(old)
    ctx.con.execute('UPDATE jobs SET note_path=?', (str(old),))
    ctx.con.execute('UPDATE publications SET target_path=?', (str(old),))
    calls.clear()
    client, app, _, base = api
    login(client, app, base)
    response = client.post(f"/api/jobs/{ctx.job['job_id']}/process", json={'mode': 'resume'})
    assert response.status_code == 202
    result = executor.Executor(ctx.con, 'boot', ctx.settings, registry).run_one()
    assert result['status'] == 'done' and calls == []
    assert Path(result['note_path']).name == '2026-11-10_1000_Library_design.md'
    assert not old.exists()
    assert all(r[0] == 'reused' for r in ctx.con.execute(
        "SELECT status FROM stage_runs WHERE run_id=? AND stage<>'note'", (result['current_run_id'],)))


def test_time_first_title_ending_in_recording_time_is_not_renamed_twice(context):
    target = publish(context, title='Design 1000')
    assert publish(again(context), title='Design 1000') == target


def test_legacy_memo_keeps_prefix(context):
    old = legacy(context, '2026-11-10_메모_Original_slug_1000.md')
    new = publish(again(context))
    assert new.name == '2026-11-10_1000_메모_Original_slug.md' and not old.exists()


def test_collision_after_prepare_keeps_original_path(context, monkeypatch):
    old = legacy(context)
    target = old.with_name('2026-11-10_1000_Original_slug.md')
    ctx = again(context)
    real = store.prepare_publication
    def collide(*args, **kwargs):
        real(*args, **kwargs)
        target.write_bytes(b'user arrived during preparation')
    monkeypatch.setattr(store, 'prepare_publication', collide)
    assert publish(ctx) == old
    assert target.read_bytes() == b'user arrived during preparation'
    assert store.job(ctx.con, ctx.job['job_id'])['note_path'] == str(old)


def test_base_symlink_is_never_followed_or_replaced(context, tmp_path):
    output = Path(context.settings['output'])
    output.mkdir()
    user = tmp_path / 'user.base'
    user.write_text(render.LEGACY_BASE_TEMPLATES[0])
    path = output / render.BASE_FILE
    path.symlink_to(user)
    render.ensure_base(output)
    assert path.is_symlink() and user.read_text() == render.LEGACY_BASE_TEMPLATES[0]


def test_daily_rename_replays_after_renamed_crash(context, monkeypatch):
    output = Path(context.settings['output'])
    (output.parent / '.obsidian').mkdir()
    context.settings['daily_note.path'] = 'Daily/{date}.md'
    old = legacy(context)
    target = output.parent / 'Daily/2026-11-10.md'
    target.parent.mkdir(exist_ok=True)
    content = f'## Meetings\n- 10:00 [[{old.stem}|My alias]]\n'.encode()
    target.write_bytes(content)
    ctx = again(context)
    real = store.rename_publication
    def stop(*args, **kwargs):
        real(*args, **kwargs)
        raise Crash()
    monkeypatch.setattr(store, 'rename_publication', stop)
    with pytest.raises(Crash):
        publish(ctx)
    monkeypatch.undo()
    store.recover(ctx.con, 'new-boot', recover_publication=notes.recover_publication)
    new = Path(store.job(ctx.con, ctx.job['job_id'])['note_path'])
    assert new != old and target.read_bytes() == content.replace(old.stem.encode(), new.stem.encode())


def test_daily_stem_update_is_exact_and_idempotent_outside_engine_heading(context):
    output = Path(context.settings['output'])
    (output.parent / '.obsidian').mkdir()
    context.settings['daily_note.path'] = 'Daily/{date}.md'
    new = publish(context)
    target = output.parent / 'Daily/2026-11-10.md'
    target.parent.mkdir(exist_ok=True)
    old_stem = '2026-11-10_User_slug_1000'
    original = (f'## My recordings\r\n- 10:00 [[{old_stem}|My alias]]\r\n'
                f'- 11:00 [[{old_stem}|Not this job time]]\r\nOther\t ').encode()
    target.write_bytes(original)
    daily.link(context.settings, new, 'New title', context.job['recorded_at'], previous_stem=old_stem)
    expected = original.replace(f'- 10:00 [[{old_stem}|'.encode(), f'- 10:00 [[{new.stem}|'.encode())
    assert target.read_bytes() == expected
    daily.link(context.settings, new, 'New title', context.job['recorded_at'], previous_stem=old_stem)
    daily.link(context.settings, new, 'New title', context.job['recorded_at'])
    assert target.read_bytes() == expected
