import json
import subprocess
import time
import sqlite3
from pathlib import Path

import pytest

from quietclerk import artifacts, config, intake, migrate_v1, store

V1_SCHEMA = '''
CREATE TABLE files(path TEXT PRIMARY KEY,size INTEGER NOT NULL,mtime REAL NOT NULL,
                   last_change REAL NOT NULL,handled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE jobs(job_id TEXT PRIMARY KEY,sha256 TEXT UNIQUE NOT NULL,source_name TEXT NOT NULL,
                  archive_path TEXT NOT NULL,duration_sec REAL,status TEXT NOT NULL,stage TEXT,
                  attempts INTEGER NOT NULL DEFAULT 0,error TEXT,warnings TEXT,output_path TEXT,
                  created_at REAL NOT NULL,updated_at REAL NOT NULL);
'''


def fixture(path):
    con = sqlite3.connect(path)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA wal_autocheckpoint=0')
    con.executescript(V1_SCHEMA)
    rows = [('done', None), ('skipped', 'before_cutoff'), ('skipped', 'decode'),
            ('failed_retryable', 'temporary'), ('failed_final', 'final'), ('running', None),
            ('skipped', 'too_short'), ('skipped', 'too_big'), ('skipped', 'too_long'), ('skipped', 'format')]
    for i, (status, error) in enumerate(rows):
        name = f'sample{i}.m4a'
        con.execute('INSERT INTO files VALUES(?,100,10,20,1)', (name,))
        con.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (f'20261109-101500-{i:08x}', f'{i:064x}', name, f'/virtual/archive/{i}/source.m4a',
                     600, status, 'asr', 2, error, 'warning one\nwarning two', f'/virtual/notes/{i}.md', 100, 200))
    con.commit()
    con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    # Keep this connection open: the last commit exists only in WAL, not the main DB.
    con.execute("UPDATE jobs SET output_path='/wal-only.md' WHERE source_name='sample0.m4a'")
    con.commit()
    return con


def test_mapping_backup_includes_wal_and_virtual_archives(tmp_path):
    path = tmp_path / 'state.sqlite3'
    old = fixture(path)
    assert Path(str(path) + '-wal').stat().st_size > 0
    backup = migrate_v1.migrate(path, service_stopped=True)
    with sqlite3.connect(backup) as saved:
        assert saved.execute("SELECT output_path FROM jobs WHERE source_name='sample0.m4a'").fetchone()[0] == '/wal-only.md'
        assert saved.execute("SELECT name FROM sqlite_master WHERE name='meta'").fetchone() is None
    old.close()
    con = store.connect(path)
    rows = {r['source_name']: r for r in con.execute('SELECT * FROM jobs')}
    assert len(rows) == 10
    assert (rows['sample0.m4a']['status'], rows['sample0.m4a']['note_path']) == ('done', '/wal-only.md')
    assert rows['sample1.m4a']['skip_reason'] == 'before_cutoff'
    assert rows['sample2.m4a']['skip_reason'] == 'legacy_rejected'
    assert rows['sample3.m4a']['status'] == 'retry_wait'
    assert rows['sample3.m4a']['next_attempt_at'] == 800
    assert rows['sample4.m4a']['status'] == 'failed'
    assert (rows['sample5.m4a']['status'], rows['sample5.m4a']['last_error'], rows['sample5.m4a']['attempts']) == ('retry_wait', 'interrupted', 2)
    assert rows['sample6.m4a']['skip_reason'] == 'too_short'
    for row in rows.values():
        assert row['recorded_at'] == row['job_id'][:15]
        assert row['legacy'] == 1 and row['current_run_id'] is None
        assert row['review_reasons'] == '["warning one", "warning two"]'
    assert {r[0] for r in con.execute('SELECT source FROM files')} == {'migrated'}
    for file in con.execute('SELECT * FROM files'):
        assert (file['intake_status'], file['sha256'], file['reject_reason']) == ('waiting', None, None)
    assert all(row['archive_path'] is None for row in rows.values())
    for i in (1, 6):
        with pytest.raises(store.Conflict):
            store.request_process(con, rows[f'sample{i}.m4a']['job_id'])
    report = json.loads(con.execute("SELECT value FROM meta WHERE key='migration_report'").fetchone()[0])
    assert len(report['cleared_archives']) == 10
    with pytest.raises(store.Conflict):
        store.request_process(con, rows['sample2.m4a']['job_id'])
    assert migrate_v1.migrate(path, service_stopped=True) is None
    con.close()


@pytest.mark.parametrize('point', ['backed_up', 'converted', 'swapped'])
def test_failure_leaves_v1_and_can_retry(tmp_path, point):
    path = tmp_path / 'state.sqlite3'
    old = fixture(path)
    before = list(old.iterdump())

    def fail(phase):
        if phase == point:
            raise RuntimeError('injected migration failure')

    with pytest.raises(RuntimeError, match='injected'):
        migrate_v1.migrate(path, service_stopped=True, fault=fail)
    assert list(old.iterdump()) == before
    assert migrate_v1.migrate(path, service_stopped=True).exists()
    old.close()


@pytest.mark.parametrize('schema', [
    'CREATE TABLE alien(x TEXT);',
    'CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL); INSERT INTO meta VALUES("schema_version","3");',
    V1_SCHEMA.replace('handled INTEGER', 'alien INTEGER'),
])
def test_unknown_structure_and_future_version_have_no_writes(tmp_path, schema):
    path = tmp_path / 'unknown.sqlite3'
    with sqlite3.connect(path) as con:
        con.executescript(schema)
    before = path.read_bytes()
    names = set(tmp_path.iterdir())
    with pytest.raises(ValueError):
        migrate_v1.migrate(path, service_stopped=True)
    assert path.read_bytes() == before
    assert set(tmp_path.iterdir()) == names


def test_offline_acknowledgement_required(tmp_path):
    with pytest.raises(ValueError, match='stop and reap'):
        migrate_v1.migrate(tmp_path / 'absent')
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('handled', [0, 1])
@pytest.mark.parametrize('known_content', [False, True])
def test_absolute_paths_and_reused_names_revalidate_with_new_scanner(tmp_path, handled, known_content):
    inbox = tmp_path / 'custom-inbox'
    inbox.mkdir()
    audio = inbox / 'sample.m4a'
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                    'sine=frequency=440:duration=1', '-c:a', 'aac', str(audio)], check=True)
    digest, stat = artifacts.sha256(audio), audio.stat()
    path = tmp_path / 'state.sqlite3'
    with sqlite3.connect(path) as old:
        old.executescript(V1_SCHEMA)
        old.execute('INSERT INTO files VALUES(?,?,?,?,?)', (str(audio), stat.st_size, stat.st_mtime, 1, handled))
        old.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    ('20261109-101500-11111111', '1' * 64, audio.name, '/virtual/old/source.m4a',
                     None, 'skipped', None, 0, 'decode', None, None, 1, 2))
        if known_content:
            old.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        ('20261109-101500-22222222', digest, audio.name, '/virtual/new/source.m4a',
                         1, 'done', None, 0, None, None, None, 1, 2))
    migrate_v1.migrate(path, inbox=inbox, service_stopped=True)
    con = store.connect(path)
    file = con.execute('SELECT * FROM files').fetchone()
    assert (file['path'], file['sha256'], file['intake_status'], file['reject_reason']) == (
        'sample.m4a', None, 'waiting', None)
    settings = config.load(tmp_path / 'settings.toml', {'QC_ROOT': str(tmp_path), 'QC_INBOX': str(inbox),
                           'QC_SINCE': '1970-01-01 00:00', 'QC_STABLE_SEC': '0', 'QC_MIN_DURATION_SEC': '0'})
    created = intake.scan(con, now=time.time() + 60, settings=settings)
    files = con.execute('SELECT * FROM files').fetchall()
    assert len(files) == 1 and files[0]['path'] == 'sample.m4a'
    assert files[0]['sha256'] == digest
    assert files[0]['intake_status'] == ('duplicate' if known_content else 'registered')
    assert len(created) == (0 if known_content else 1)
    if not known_content:
        assert store.job(con, created[0])['status'] == 'queued'
    con.close()


def test_migration_drops_outside_paths_and_reports_them(tmp_path):
    inbox = tmp_path / 'inbox'
    inbox.mkdir()
    outside = tmp_path / 'outside.m4a'
    outside.write_bytes(b'outside')
    (inbox / 'escape.m4a').symlink_to(outside)
    path = tmp_path / 'state.sqlite3'
    invalid = [str(outside), '../outside.m4a', str(inbox / 'escape.m4a')]
    with sqlite3.connect(path) as old:
        old.executescript(V1_SCHEMA)
        for name in invalid:
            old.execute('INSERT INTO files VALUES(?,1,1,1,1)', (name,))
        old.execute('INSERT INTO files VALUES(?,1,1,1,0)', (str(inbox / 'inside.m4a'),))
    migrate_v1.migrate(path, inbox=inbox, service_stopped=True)
    con = store.connect(path)
    assert [r['path'] for r in con.execute('SELECT * FROM files')] == ['inside.m4a']
    report = json.loads(con.execute("SELECT value FROM meta WHERE key='migration_report'").fetchone()[0])
    assert report['dropped_files'] == [{'path': name, 'reason': 'outside_inbox'} for name in invalid]
    con.close()


def test_migration_path_collision_rolls_back_instead_of_overwriting(tmp_path):
    inbox = tmp_path / 'inbox'
    path = tmp_path / 'state.sqlite3'
    with sqlite3.connect(path) as old:
        old.executescript(V1_SCHEMA)
        old.execute('INSERT INTO files VALUES(?,1,1,1,1)', (str(inbox / 'same.m4a'),))
        old.execute('INSERT INTO files VALUES(?,2,2,2,0)', ('same.m4a',))
    with pytest.raises(ValueError, match='colliding inbox paths'):
        migrate_v1.migrate(path, inbox=inbox, service_stopped=True)
    with sqlite3.connect(path) as old:
        assert old.execute('SELECT COUNT(*) FROM files').fetchone()[0] == 2
        assert old.execute("SELECT name FROM sqlite_master WHERE name='meta'").fetchone() is None


def test_migrated_schema_supports_not_run_stage(tmp_path):
    path = tmp_path / 'state.sqlite3'
    old = fixture(path)
    migrate_v1.migrate(path, service_stopped=True)
    old.close()
    con = store.connect(path)
    running = store.claim(con, 'boot', {'root': str(tmp_path)}, now=1000)
    args = (running['job_id'], running['active_run_id'], 'boot')
    store.start_stage(con, *args, 'detect_language')
    store.finish_stage(con, *args, 'detect_language', status='not_run')
    assert con.execute('SELECT status FROM stage_runs').fetchone()[0] == 'not_run'
    con.close()
