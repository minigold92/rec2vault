"""Extra receiving folders (contract 3.3 `extra_inboxes`, 5.1, 9.2): the phone's interpreter recordings arrive in a
second Syncthing folder. All data is generated AAC in tmp directories; no installed path and no real recording.
"""
import json
import os
import sqlite3
import unicodedata
from contextlib import closing
from pathlib import Path

import pytest

from quietclerk import backfill, config, intake, store, syncthing
from quietclerk.server import integrations
from quietclerk.server.settings import LockedSetting, save
from test_intake import tone


def load(tmp_path, extra=None, **env):
    """Settings whose root and notes live in tmp_path/root, so extra folders can sit next to them (outside the root)."""
    environ = {'QC_ROOT': str(tmp_path / 'root'), 'QC_INBOX': str(tmp_path / 'inbox'), 'QC_MIN_DURATION_SEC': '0',
               'QC_STABLE_SEC': '0', 'QC_SINCE': '1970-01-01 00:00'} | env
    path = tmp_path / 'settings.toml'
    if extra is not None:
        path.write_text('extra_inboxes = ' + json.dumps([str(p) for p in extra]) + '\n', encoding='utf-8')
    return config.load(path, environ=environ)


@pytest.fixture
def folders(tmp_path):
    primary, extra = tmp_path / 'inbox', tmp_path / 'inbox-interpreter'
    primary.mkdir()
    extra.mkdir()
    (tmp_path / 'root').mkdir()
    return primary, extra


@pytest.fixture
def db(tmp_path):
    con = store.connect(tmp_path / 'root' / 'state.sqlite3')
    yield con
    con.close()


# ---- the setting (contract 3.3)

def test_extra_inboxes_default_is_an_empty_list(tmp_path):
    assert load(tmp_path).get('extra_inboxes') == []


def test_extra_inboxes_are_read_expanded_and_normalized(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    settings = load(tmp_path, extra=['~/rec/inbox-interpreter', str(tmp_path / 'a' / '.' / 'b' / '')])
    assert settings.get('extra_inboxes') == [str(tmp_path / 'home' / 'rec' / 'inbox-interpreter'), str(tmp_path / 'a' / 'b')]


@pytest.mark.parametrize('value, why', [
    (['relative/inbox'], 'absolute'), ([''], 'nonempty'), ([5], 'nonempty'), ('/x', 'list'),
    (['/a/../b'], '..'), ([f'/many/{i}' for i in range(9)], 'at most 8'), (['/same', '/same/'], 'duplicate'),
])
def test_extra_inboxes_shape_is_validated(tmp_path, value, why):
    path = tmp_path / 'settings.toml'
    path.write_text('extra_inboxes = ' + json.dumps(value) + '\n')
    with pytest.raises(config.SettingsError) as error:
        config.load(path, environ={'QC_ROOT': str(tmp_path / 'root')})
    assert error.value.field == 'extra_inboxes' and why in str(error.value)


def test_exactly_eight_extra_inboxes_are_allowed(tmp_path):
    assert len(load(tmp_path, extra=[tmp_path / f'x{i}' for i in range(8)]).get('extra_inboxes')) == 8


def test_extra_inbox_equal_to_the_primary_inbox_is_refused(tmp_path, folders):
    primary, _ = folders
    for value in (primary, str(primary) + '/', primary / '.'):
        with pytest.raises(config.SettingsError, match='primary inbox') as error:
            load(tmp_path, extra=[value])
        assert error.value.field == 'extra_inboxes'


def test_extra_inbox_that_is_a_symlink_to_the_primary_inbox_is_refused(tmp_path, folders):
    primary, _ = folders
    alias = tmp_path / 'alias'
    alias.symlink_to(primary)
    with pytest.raises(config.SettingsError, match='primary inbox'):
        load(tmp_path, extra=[alias])


@pytest.mark.parametrize('where', ['root', 'root/archive', 'root/archive/x', 'root/work', 'root/quarantine', 'root/logs/a', 'root/note-backups',
                                   'root/.venvs/x', 'root/.ops', 'root/notes', 'root/notes/sub'])
def test_extra_inbox_that_is_the_data_folder_an_engine_folder_or_inside_the_notes_folder_is_refused(tmp_path, folders, where):
    with pytest.raises(config.SettingsError, match='must not be') as error:
        load(tmp_path, extra=[tmp_path / where])
    assert error.value.field == 'extra_inboxes'


@pytest.mark.parametrize('where', ['root/inbox-interpreter', 'root/inbox2', 'root/other/deeper', 'root/archive2'])
def test_a_sibling_of_the_primary_inbox_inside_the_data_folder_is_fine(tmp_path, folders, where):
    # installations that adopted ~/rec keep every receiving folder there (~/rec/inbox, ~/rec/inbox-interpreter)
    assert load(tmp_path, extra=[tmp_path / where]).get('extra_inboxes') == [str(tmp_path / where)]


def test_extra_inbox_inside_a_custom_notes_folder_or_through_a_link_is_refused(tmp_path, folders):
    vault = tmp_path / 'vault'
    (vault / 'meetings').mkdir(parents=True)
    with pytest.raises(config.SettingsError, match='notes folder'):
        load(tmp_path, extra=[vault / 'meetings' / 'in'], QC_OUTPUT=str(vault / 'meetings'))
    (tmp_path / 'root' / 'archive').mkdir()
    link = tmp_path / 'link'
    link.symlink_to(tmp_path / 'root' / 'archive')
    with pytest.raises(config.SettingsError, match='engine folders'):
        load(tmp_path, extra=[link / 'sub'])


def test_the_install_layout_with_the_root_next_to_the_inboxes_is_accepted(tmp_path):
    # root = ~/rec, inbox = ~/rec/inbox, interpreter inbox = ~/rec/inbox-interpreter
    root = tmp_path / 'rec'
    settings = config.load(None, environ={'QC_ROOT': str(root), 'QC_SETTINGS': str(tmp_path / 's.toml'), 'QC_EXTRA_INBOXES': str(root / 'inbox-interpreter')})
    assert settings.get('inbox') == str(root / 'inbox') and settings.get('extra_inboxes') == [str(root / 'inbox-interpreter')]


def test_a_symlinked_extra_inbox_is_kept_as_written_like_the_primary_and_never_scanned(tmp_path, folders, db):
    # Same rule as `inbox`: the path is not resolved, and quarantine.copy opens the folder with O_NOFOLLOW, so a
    # link to a folder yields no recordings (primary and extra behave alike).
    real = tmp_path / 'real'
    real.mkdir()
    tone(real / 'a.m4a')
    link = tmp_path / 'link-inbox'
    link.symlink_to(real)
    settings = load(tmp_path, extra=[link])
    assert settings.get('extra_inboxes') == [str(link)]
    assert intake.scan(db, now=2000, settings=settings) == []


def test_environment_variable_sets_and_locks_the_list(tmp_path, folders):
    a, b = tmp_path / 'a', tmp_path / 'b'
    settings = load(tmp_path, extra=[tmp_path / 'file'], QC_EXTRA_INBOXES=f'{a}:{b}')
    assert settings.get('extra_inboxes') == [str(a), str(b)] and 'extra_inboxes' in settings.environment_keys
    assert load(tmp_path, QC_EXTRA_INBOXES='').get('extra_inboxes') == []
    with pytest.raises(config.SettingsError, match='absolute'):
        load(tmp_path, QC_EXTRA_INBOXES='relative')
    with pytest.raises(LockedSetting):
        save(settings, {'extra_inboxes': [str(tmp_path / 'c')]})
    # a save that changes something else keeps the locked value in the file check and does not rewrite it
    assert save(settings, {'retention.wav_days': 3}).get('extra_inboxes') == [str(a), str(b)]


def test_saving_extra_inboxes_validates_and_persists_them(tmp_path, folders):
    settings = load(tmp_path)
    for bad in ([str(tmp_path / 'root' / 'work')], [str(folders[0])], ['relative'], [str(tmp_path / f'n{i}') for i in range(9)]):
        with pytest.raises(config.SettingsError) as error:
            save(settings, {'extra_inboxes': bad})
        assert error.value.field == 'extra_inboxes'
        assert 'extra_inboxes' not in settings.path.read_text() if settings.path.exists() else True
    updated = save(settings, {'extra_inboxes': [str(folders[1])]})
    assert updated.get('extra_inboxes') == [str(folders[1])]
    assert load(tmp_path).get('extra_inboxes') == [str(folders[1])]


# ---- files table identity (contract 3.1)

def old_files_table(path):
    """Turn a freshly made database back into the shape before `folder` existed, holding two observed files."""
    store.connect(path).close()
    with closing(sqlite3.connect(path, isolation_level=None)) as con:
        con.executescript("""
            DROP TABLE files;
            CREATE TABLE files (
              path TEXT PRIMARY KEY, name_nfc TEXT NOT NULL,
              source TEXT NOT NULL CHECK (source IN ('syncthing','upload','migrated')),
              size INTEGER NOT NULL, mtime REAL NOT NULL, last_change REAL NOT NULL,
              intake_status TEXT NOT NULL CHECK (intake_status IN ('waiting','rejected','registered','duplicate')),
              reject_reason TEXT, sha256 TEXT, first_seen REAL NOT NULL);
            INSERT INTO files VALUES('음성 261106_142617.m4a','음성 261106_142617.m4a','syncthing',10,1.5,2.5,'registered',NULL,'abc',1.0);
            INSERT INTO files VALUES('b.m4a','b.m4a','upload',20,3.5,4.5,'waiting',NULL,NULL,3.0);
        """)


def test_old_files_rows_become_primary_inbox_rows_and_the_move_is_safe_to_repeat(tmp_path):
    database = tmp_path / 'state.sqlite3'
    old_files_table(database)
    expected = None
    for _ in range(3):   # every start of every process runs the move; repeating it changes nothing
        with closing(store.connect(database)) as con:
            rows = [dict(row) for row in con.execute('SELECT * FROM files ORDER BY path')]
            assert [r['folder'] for r in rows] == ['', '']
            assert [(r['path'], r['intake_status'], r['sha256'], r['size'], r['source']) for r in rows] == [
                ('b.m4a', 'waiting', None, 20, 'upload'), ('음성 261106_142617.m4a', 'registered', 'abc', 10, 'syncthing')]
            expected = expected or rows
            assert rows == expected
            # the identity is now (folder, path): the same name may live in another folder
            con.execute("INSERT INTO files(folder,path,name_nfc,source,size,mtime,last_change,intake_status,first_seen) "
                        "VALUES('/x','b.m4a','b.m4a','syncthing',1,1,1,'waiting',1)")
            con.execute("DELETE FROM files WHERE folder='/x'")


def test_two_processes_opening_an_old_database_at_once_move_it_once(tmp_path):
    import threading
    database = tmp_path / 'state.sqlite3'
    old_files_table(database)
    errors = []

    def open_it():
        try:
            store.connect(database).close()
        except BaseException as exc:   # noqa: BLE001 - the test reports whatever happened
            errors.append(exc)
    threads = [threading.Thread(target=open_it) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    with closing(store.connect(database)) as con:
        assert con.execute('SELECT COUNT(*) FROM files').fetchone()[0] == 2


def test_a_new_database_has_the_folder_as_the_first_column_of_files(tmp_path):
    with closing(store.connect(tmp_path / 'state.sqlite3')) as con:
        assert [c[1] for c in con.execute("SELECT * FROM pragma_table_info('files')")][:2] == ['folder', 'path']


# ---- intake over several folders (contract 5.1)

def names(con):
    return sorted((r['folder'], r['path'], r['intake_status']) for r in con.execute('SELECT * FROM files'))


def test_a_recording_in_an_extra_folder_is_received_like_one_in_the_primary(tmp_path, folders, db):
    primary, extra = folders
    tone(primary / '음성 261120_090000.m4a', 1)
    tone(extra / '통역_261120_100000.m4a', 2)
    settings = load(tmp_path, extra=[extra])
    created = intake.scan(db, now=2000, settings=settings)
    assert len(created) == 2 and created.missing_inboxes == []
    jobs = {r['source_name']: r for r in db.execute('SELECT * FROM jobs')}
    assert set(jobs) == {'음성 261120_090000.m4a', '통역_261120_100000.m4a'}
    assert all(r['status'] == 'queued' and Path(r['archive_path']).is_file() for r in jobs.values())
    assert jobs['통역_261120_100000.m4a']['recorded_at'] == '20261120-100000'
    assert names(db) == [('', '음성 261120_090000.m4a', 'registered'), (str(extra), '통역_261120_100000.m4a', 'registered')]
    assert intake.scan(db, now=3000, settings=settings) == []   # nothing is copied or registered twice
    assert not list((tmp_path / 'root' / 'quarantine').glob('*'))


def test_the_same_file_name_in_two_folders_does_not_collide(tmp_path, folders, db):
    primary, extra = folders
    tone(primary / 'same_261120_090000.m4a', 1)
    tone(extra / 'same_261120_090000.m4a', 2, noise=True)   # another recording that happens to have the same name
    settings = load(tmp_path, extra=[extra])
    assert len(intake.scan(db, now=2000, settings=settings)) == 2
    assert names(db) == [('', 'same_261120_090000.m4a', 'registered'), (str(extra), 'same_261120_090000.m4a', 'registered')]
    assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 2
    # growth of one of them restarts only its own stability clock
    tone(extra / 'same_261120_090000.m4a', 3, noise=True)
    os.utime(extra / 'same_261120_090000.m4a', (5000, 5000))
    intake.scan(db, now=5001, settings=load(tmp_path, extra=[extra], QC_STABLE_SEC='1000'))
    rows = {r['folder']: r for r in db.execute('SELECT * FROM files')}
    assert rows['']['intake_status'] == 'registered' and rows[str(extra)]['intake_status'] == 'waiting'


def test_the_same_content_in_two_folders_makes_one_job(tmp_path, folders, db):
    primary, extra = folders
    tone(primary / 'a_261120_090000.m4a', 1)
    (extra / 'copy_of_a.m4a').write_bytes((primary / 'a_261120_090000.m4a').read_bytes())
    os.utime(extra / 'copy_of_a.m4a', (1000, 1000))
    settings = load(tmp_path, extra=[extra])
    assert len(intake.scan(db, now=2000, settings=settings)) == 1
    assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 1
    assert names(db) == [('', 'a_261120_090000.m4a', 'registered'), (str(extra), 'copy_of_a.m4a', 'duplicate')]
    assert len(list((tmp_path / 'root' / 'archive').iterdir())) == 1


def test_the_same_content_arriving_in_the_extra_folder_first_is_also_one_job(tmp_path, folders, db):
    primary, extra = folders
    tone(extra / 'a.m4a', 1)
    settings = load(tmp_path, extra=[extra])
    assert len(intake.scan(db, now=2000, settings=settings)) == 1
    (primary / 'later.m4a').write_bytes((extra / 'a.m4a').read_bytes())
    os.utime(primary / 'later.m4a', (1000, 1000))
    assert intake.scan(db, now=3000, settings=settings) == []
    assert names(db) == [('', 'later.m4a', 'duplicate'), (str(extra), 'a.m4a', 'registered')]


def test_a_missing_extra_folder_is_skipped_without_error_and_reported(tmp_path, folders, db):
    primary, extra = folders
    gone = tmp_path / 'not-shared-yet'
    tone(primary / 'a_261120_090000.m4a', 1)
    settings = load(tmp_path, extra=[gone, extra])
    created = intake.scan(db, now=2000, settings=settings)
    assert len(created) == 1 and created.missing_inboxes == [str(gone)]
    file = tmp_path / 'inbox-interpreter' / 'ok.m4a'
    tone(file, 1, noise=True)
    created = intake.scan(db, now=3000, settings=settings)
    assert len(created) == 1 and created.missing_inboxes == [str(gone)]   # still reported, the others still work
    assert not gone.exists()                                              # never created by the engine


def test_a_file_where_the_extra_folder_should_be_is_also_just_missing(tmp_path, folders, db):
    primary, _ = folders
    plain = tmp_path / 'plain-file'
    plain.write_text('x')
    created = intake.scan(db, now=2000, settings=load(tmp_path, extra=[plain]))
    assert created == [] and created.missing_inboxes == [str(plain)]


def test_candidate_rules_apply_unchanged_in_an_extra_folder(tmp_path, folders, db):
    primary, extra = folders
    tone(extra / '.hidden.m4a')
    tone(extra / '통화 홍길동_261120_090000.m4a')
    (extra / 'plain.mp3').write_bytes(b'x')
    (extra / 'sub').mkdir()
    tone(extra / 'sub' / 'nested.m4a')
    tone(tmp_path / 'target.m4a')
    (extra / 'link.m4a').symlink_to(tmp_path / 'target.m4a')
    (extra / 'half.m4a.part').write_bytes(b'x')
    assert intake.scan(db, now=2000, settings=load(tmp_path, extra=[extra])) == []
    assert db.execute('SELECT COUNT(*) FROM files').fetchone()[0] == 0


def test_cutoff_include_and_minimum_length_apply_in_an_extra_folder(tmp_path, folders, db):
    primary, extra = folders
    old, included, recent = '통역_261105_083634.m4a', '통역_261106_142617.m4a', '통역_261120_090000.m4a'
    for seconds, name in enumerate((old, included, recent), start=1):
        tone(extra / name, seconds)
    settings = load(tmp_path, extra=[extra], QC_SINCE='2026-11-09 10:59', QC_MIN_DURATION_SEC='0')
    (settings.root / 'include.txt').write_text(unicodedata.normalize('NFD', included) + '\n', encoding='utf-8')
    intake.scan(db, now=2000, settings=settings)
    jobs = {r['source_name']: (r['status'], r['skip_reason'], r['archive_path'] is None) for r in db.execute('SELECT * FROM jobs')}
    assert jobs == {old: ('skipped', 'before_cutoff', True), included: ('queued', None, False), recent: ('queued', None, False)}
    assert db.execute("SELECT COUNT(*) FROM files WHERE intake_status='registered' AND folder=?", (str(extra),)).fetchone()[0] == 3


def test_the_minimum_length_applies_in_an_extra_folder(tmp_path, folders, db):
    primary, extra = folders
    tone(extra / 'short.m4a', 1)
    tone(extra / 'long.m4a', 3)
    intake.scan(db, now=2000, settings=load(tmp_path, extra=[extra], QC_MIN_DURATION_SEC='2'))
    assert {r['source_name']: (r['status'], r['skip_reason']) for r in db.execute('SELECT * FROM jobs')} == {
        'short.m4a': ('skipped', 'too_short'), 'long.m4a': ('queued', None)}


def test_a_tombstoned_recording_is_refused_in_an_extra_folder(tmp_path, folders, db):
    primary, extra = folders
    audio = tone(extra / 'gone.m4a', 1)
    db.execute('INSERT INTO tombstones VALUES(?,?)', (intake.sha256(audio), 1.0))
    intake.scan(db, now=2000, settings=load(tmp_path, extra=[extra]))
    row = db.execute('SELECT * FROM files').fetchone()
    assert row['intake_status'] == 'rejected' and row['reject_reason'] == 'deleted_by_user'
    assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0


def test_a_skipped_recording_from_an_extra_folder_can_be_promoted(tmp_path, folders, db):
    primary, extra = folders
    tone(extra / 'old_261105_083634.m4a', 1)
    settings = load(tmp_path, extra=[extra], QC_SINCE='2026-11-09 10:59')
    [job_id] = intake.scan(db, now=2000, settings=settings)
    assert store.job(db, job_id)['skip_reason'] == 'before_cutoff'
    assert intake.promote(db, job_id, settings=settings, now=3000) is True
    assert store.job(db, job_id)['status'] == 'queued'
    assert [r['intake_status'] for r in db.execute('SELECT * FROM files')] == ['registered']


def test_disk_low_stops_copying_in_every_folder(tmp_path, folders, db):
    primary, extra = folders
    tone(primary / 'a.m4a', 1)
    tone(extra / 'b.m4a', 2)
    created = intake.scan(db, now=2000, settings=load(tmp_path, extra=[extra]), free_space=lambda _: 0)
    assert created == [] and created.blocked_reason == 'disk_low'
    assert {r['intake_status'] for r in db.execute('SELECT * FROM files')} == {'waiting'}   # observed, not copied


def test_without_extra_folders_nothing_changes(tmp_path, folders, db):
    primary, _ = folders
    tone(primary / 'a.m4a', 1)
    created = intake.scan(db, now=2000, settings=load(tmp_path))
    assert len(created) == 1 and created.missing_inboxes == []
    assert [r['folder'] for r in db.execute('SELECT * FROM files')] == ['']


# ---- backfill and the folder state (contract 5.3, 9.2)

def test_backfill_names_the_folder_and_edits_only_that_folders_ignore_list(tmp_path, folders, monkeypatch):
    primary, extra = folders
    settings = load(tmp_path, extra=[extra])
    calls = []
    monkeypatch.setattr(syncthing, 'unignore', lambda folder, names: calls.append((folder, names)) or [])
    backfill.request(['통역_261105_083634.m4a'], settings=settings, folder=str(extra))
    backfill.request(['a.m4a'], settings=settings)
    backfill.request(['b.m4a'], settings=settings, folder=str(primary))
    assert calls == [(extra, ['통역_261105_083634.m4a']), (primary, ['a.m4a']), (primary, ['b.m4a'])]
    assert backfill.included(settings.root / 'include.txt') == {'통역_261105_083634.m4a', 'a.m4a', 'b.m4a'}


def test_backfill_refuses_a_folder_that_is_not_configured_before_any_io(tmp_path, folders, monkeypatch):
    settings = load(tmp_path, extra=[folders[1]])
    monkeypatch.setattr(syncthing, 'unignore', lambda *_: pytest.fail('unknown folder reached Syncthing'))
    for folder in (str(tmp_path / 'elsewhere'), '', '/', str(folders[1]) + '/../inbox'):
        with pytest.raises(ValueError, match='receiving folder'):
            backfill.request(['a.m4a'], settings=settings, folder=folder)
    assert not (settings.root / 'include.txt').exists()


def test_backfill_command_line_takes_a_folder(tmp_path, folders, monkeypatch, capsys):
    settings = load(tmp_path, extra=[folders[1]])
    calls = []
    monkeypatch.setattr(syncthing, 'unignore', lambda folder, names: calls.append((folder, names)) or ['x'])
    monkeypatch.setattr(config, 'load', lambda *a, **k: settings)
    assert backfill.main(['--folder', str(folders[1]), 'a.m4a']) == 0
    assert backfill.main(['a.m4a']) == 0
    assert backfill.main(['--folder', '/nowhere', 'a.m4a']) == 2
    assert calls == [(folders[1], ['a.m4a']), (folders[0], ['a.m4a'])]
    assert 'receiving folder' in capsys.readouterr().err


FOLDERS = [
    {'id': 'rec', 'path': None, 'devices': [{'deviceID': 'ME'}, {'deviceID': 'PHONE'}]},
    {'id': 'interp', 'path': None, 'devices': [{'deviceID': 'ME'}, {'deviceID': 'PHONE'}]},
    {'id': 'alone', 'path': None, 'devices': [{'deviceID': 'ME'}]},
]


def fake_api(settings, shared, need):
    """A Syncthing REST double: `shared` is the list of (folder id, path); `need` maps folder id to names."""
    calls = []
    folders = [{'id': fid, 'path': path, 'devices': [{'deviceID': 'ME'}, {'deviceID': 'PHONE'}]} for fid, path in shared]

    def api(method, endpoint, params, body=None):
        calls.append((method, endpoint, dict(params)))
        if endpoint == 'config/folders':
            return folders
        if endpoint == 'system/status':
            return {'myID': 'ME'}
        if endpoint == 'system/connections':
            return {'connections': {'PHONE': {'connected': True}}}
        if endpoint == 'db/completion':
            return {'remoteState': 'valid'}
        if endpoint == 'db/need':
            return {'progress': [], 'queued': [{'name': n} for n in need[params['folder']]], 'rest': []}
        raise AssertionError(endpoint)
    return api, calls


def test_folder_state_covers_every_receiving_folder_and_says_which_are_missing(tmp_path, folders):
    primary, extra = folders
    gone = tmp_path / 'not-yet'
    settings = load(tmp_path, extra=[extra, gone])
    api, _ = fake_api(settings, [('rec', str(primary)), ('interp', str(extra))], {})
    state = integrations.Syncthing(settings, api).folder()
    assert state['state'] == 'connected' and state['folder_id'] == 'rec'
    assert state['extra'] == [
        {'path': str(extra), 'exists': True, 'state': 'connected', 'folder_id': 'interp', 'phone_recordings': None,
         'count_reason': 'remote_inventory_unavailable'},
        {'path': str(gone), 'exists': False, 'state': 'not_shared', 'folder_id': None, 'phone_recordings': None,
         'count_reason': 'remote_inventory_unavailable'}]


def test_folder_state_without_extra_folders_has_an_empty_list(tmp_path, folders):
    settings = load(tmp_path)
    api, _ = fake_api(settings, [('rec', str(folders[0]))], {})
    assert integrations.Syncthing(settings, api).folder()['extra'] == []


def test_backlog_lists_the_names_of_each_folder_with_the_folder_they_are_in(tmp_path, folders):
    primary, extra = folders
    settings = load(tmp_path, extra=[extra, tmp_path / 'unshared'])
    api, calls = fake_api(settings, [('rec', str(primary)), ('interp', str(extra))],
                          {'rec': ['same.m4a', '../escape.m4a', '통화 a.m4a'], 'interp': ['same.m4a', '통역_261105_083634.m4a']})
    assert integrations.Syncthing(settings, api).backlog() == [
        {'name': 'same.m4a', 'folder': str(primary)}, {'name': 'same.m4a', 'folder': str(extra)},
        {'name': '통역_261105_083634.m4a', 'folder': str(extra)}]
    assert [c[2]['folder'] for c in calls if c[1] == 'db/need'] == ['rec', 'interp']   # the unshared folder is not asked


def test_backlog_with_only_the_primary_folder_is_unchanged(tmp_path, folders):
    settings = load(tmp_path)
    api, _ = fake_api(settings, [('rec', str(folders[0]))], {'rec': ['old.m4a']})
    assert integrations.Syncthing(settings, api).backlog() == [{'name': 'old.m4a', 'folder': str(folders[0])}]


def test_the_status_shows_extra_folders_even_when_syncthing_is_unreachable(tmp_path, folders):
    from quietclerk.server import sync_summary
    settings = load(tmp_path, extra=[folders[1], tmp_path / 'gone'])

    class Down:
        def __init__(self, settings):
            pass

        def folder(self):
            raise OSError('syncthing is down')
    assert sync_summary(settings, Down) == {'state': 'unavailable', 'extra': [
        {'path': str(folders[1]), 'exists': True}, {'path': str(tmp_path / 'gone'), 'exists': False}]}


# ---- the API (contract 9.2)

class FakeSync:
    """The Syncthing adapter as the app uses it, with a fixed answer."""
    items, down = [], False

    def __init__(self, settings):
        self.settings = settings

    def folder(self):
        if self.down:
            raise OSError('syncthing is down')
        return {'state': 'connected', 'folder_id': 'rec', 'phone_recordings': None, 'count_reason': 'remote_inventory_unavailable', 'extra': []}

    def backlog(self):
        if self.down:
            raise OSError('syncthing is down')
        return list(self.items)


@pytest.fixture
def served(tmp_path, folders):
    from test_server_integrations import client_for
    settings = load(tmp_path, extra=[folders[1]], QC_PORT='18765')
    FakeSync.items, FakeSync.down = [], False
    with client_for(settings, tmp_path, sync_factory=FakeSync, provider_registry=lambda _: {}) as (client, runtime):
        yield client, runtime, settings


def test_backlog_request_edits_only_the_named_folder_and_refuses_unknown_ones(served, tmp_path, folders, monkeypatch):
    client, runtime, settings = served
    primary, extra = folders
    calls = []
    monkeypatch.setattr(syncthing, 'unignore', lambda folder, names: calls.append((folder, names)) or [])
    assert client.post('/api/backlog/request', json={'names': ['a.m4a'], 'folder': str(extra)}).status_code == 202
    assert client.post('/api/backlog/request', json={'names': ['b.m4a']}).status_code == 202
    assert client.post('/api/backlog/request', json={'names': ['c.m4a'], 'folder': None}).status_code == 202
    assert client.post('/api/backlog/request', json={'names': ['d.m4a'], 'folder': str(primary)}).status_code == 202
    assert calls == [(extra, ['a.m4a']), (primary, ['b.m4a']), (primary, ['c.m4a']), (primary, ['d.m4a'])]
    for folder in ('/etc', str(tmp_path / 'inbox-interpreter' / 'sub'), '', 7):
        answer = client.post('/api/backlog/request', json={'names': ['e.m4a'], 'folder': folder})
        assert answer.status_code == 400, folder
    assert len(calls) == 4


def test_backlog_lists_items_with_their_folder_and_skipped_jobs_with_where_they_arrived(served, folders):
    client, runtime, settings = served
    primary, extra = folders
    FakeSync.items = [{'name': 'x.m4a', 'folder': str(primary)}, {'name': 'x.m4a', 'folder': str(extra)}]
    with closing(store.connect(runtime.db)) as con:
        for job_id, sha, folder in (('20261105-083634-aaaaaaaa', 'a' * 64, ''), ('20261105-083635-bbbbbbbb', 'b' * 64, str(extra)),
                                    ('20261105-083636-cccccccc', 'c' * 64, None)):
            store.add_job(con, job_id, sha, 'n.m4a', None, 1, 'skipped', skip_reason='too_short')
            if folder is not None:
                store.observe(con, 'n.m4a', 1, 1.0, 1.0, folder=folder)
                store.finish_intake(con, 'n.m4a', 'registered', sha, folder=folder)
    body = client.get('/api/backlog').json()
    assert body['items'] == FakeSync.items and body['inventory'] == 'partial'
    assert {job['job_id'][-8:]: job['folder'] for job in body['skipped']} == {'aaaaaaaa': str(primary), 'bbbbbbbb': str(extra), 'cccccccc': None}
    from jsonschema import Draft202012Validator
    schema = json.loads((Path(store.__file__).parent / 'server' / 'schema.json').read_text())
    Draft202012Validator(schema | {'$ref': '#/$defs/Backlog'}).validate(body)
    FakeSync.down = True
    down = client.get('/api/backlog').json()
    assert down['items'] == [] and down['inventory'] == 'unavailable' and len(down['skipped']) == 3


def test_status_names_the_extra_folders_even_when_syncthing_is_down(served, tmp_path, folders):
    client, runtime, settings = served
    assert client.get('/api/status').json()['sync']['extra'] == []
    FakeSync.down = True
    assert client.get('/api/status').json()['sync'] == {'state': 'unavailable', 'extra': [{'path': str(folders[1]), 'exists': True}]}
    folders[1].rmdir()
    assert client.get('/api/status').json()['sync']['extra'] == [{'path': str(folders[1]), 'exists': False}]


def test_the_settings_api_saves_extra_inboxes_and_reports_what_is_wrong(served, tmp_path, folders):
    client, runtime, settings = served
    assert client.get('/api/settings').json()['effective']['extra_inboxes'] == [str(folders[1])]
    other = tmp_path / 'other'
    assert client.put('/api/settings', json={'extra_inboxes': [str(folders[1]), str(other)]}).status_code == 200
    assert runtime.settings.get('extra_inboxes') == [str(folders[1]), str(other)]   # the next scan reads the new list
    for bad, text in (([str(tmp_path / 'root' / 'archive' / 'x')], 'must not be'), ([str(folders[0])], 'primary inbox'), (['rel'], 'absolute')):
        answer = client.put('/api/settings', json={'extra_inboxes': bad})
        assert answer.status_code == 400 and answer.json()['field'] == 'extra_inboxes' and text in answer.json()['error']
    assert runtime.settings.get('extra_inboxes') == [str(folders[1]), str(other)]


def test_the_engine_scans_extra_folders_through_the_runtime_scan(served, folders):
    client, runtime, settings = served
    tone(folders[1] / 'x_261120_090000.m4a', 1)
    with closing(store.connect(runtime.db)) as con:
        assert len(intake.scan(con, now=2000, settings=runtime.settings)) == 1
