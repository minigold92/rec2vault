"""Service-state invariants with synthetic DB rows; no real input recordings."""
from contextlib import closing

import pytest

from quietclerk import config, store, store_ops


@pytest.fixture
def state(tmp_path):
    with closing(store.connect(tmp_path / 'state.sqlite3')) as con:
        row = store.add_job(con, 'job', 'a' * 64, 'private title.m4a', '/archive/job/source.m4a', 600)
        settings = config.load(tmp_path / 'settings.toml', {'QC_ROOT': str(tmp_path)})
        yield con, row, settings


def test_pause_persists_independently_of_disk_low_and_does_not_claim(state):
    con, row, settings = state
    store.set_engine_state(con, 'disk_low')
    store_ops.set_paused(con, True)
    assert store_ops.paused(con) and store.engine_state(con) == 'disk_low'
    assert store.claim(con, 'boot', settings, paused=store_ops.paused(con)) is None
    store.set_engine_state(con, None)
    assert store_ops.paused(con)
    store_ops.set_paused(con, False)
    assert store.claim(con, 'boot', settings, paused=store_ops.paused(con))['job_id'] == 'job'
    with pytest.raises(ValueError):
        store_ops.set_paused(con, 1)


def test_language_override_validates_and_does_not_modify_active_snapshot(state):
    con, row, settings = state
    store_ops.set_language_override(con, 'job', 'en')
    timestamp = store.job(con, 'job')['updated_at']
    store_ops.set_language_override(con, 'job', 'en')
    assert store.job(con, 'job')['updated_at'] == timestamp
    with pytest.raises(ValueError):
        store_ops.set_language_override(con, 'job', 'ja')
    claimed = store.claim(con, 'boot', settings)
    with pytest.raises(store.Conflict):
        store_ops.set_language_override(con, 'job', None)
    assert '"language_override": "en"' in con.execute('SELECT settings_json FROM runs').fetchone()[0]
    assert store.job(con, 'job')['active_run_id'] == claimed['active_run_id']


def test_running_delete_defers_until_checkpoint_and_cleans_conversation_fields(state):
    con, row, settings = state
    claimed = store.claim(con, 'boot', settings)
    run_id = claimed['active_run_id']
    store.start_stage(con, 'job', run_id, 'boot', 'transcribe', sent_fields=['transcript'])
    assert store_ops.request_delete_local(con, 'job')
    assert not store_ops.request_delete_local(con, 'job')
    # Names, edits and the search index are conversation data too (contract 10.8).
    con.execute("INSERT INTO speaker_overrides VALUES('job','S1','이름',1,NULL,0)")
    con.execute("INSERT INTO transcript_edits VALUES('job','t1','고친 말','x',0)")
    con.execute("INSERT INTO search(job_id,kind,line_id,start,speaker,text,compact) VALUES('job','line','t1',0,'S1','말','말')")
    assert store_ops.deleted(con, 'job')
    assert store.job(con, 'job')['exclude_requested']
    assert store_ops.pending_deletions(con)[0]['status'] == 'running'
    with pytest.raises(store.Conflict):
        store_ops.finish_delete_local(con, 'job')
    assert not store.checkpoint(con, 'job', run_id, 'boot')
    assert store_ops.finish_delete_local(con, 'job')
    assert not store_ops.finish_delete_local(con, 'job')
    assert not store_ops.pending_deletions(con)
    for table in ('runs', 'stage_runs', 'publications', 'note_fields', 'note_tasks',
                  'speaker_overrides', 'transcript_edits', 'search'):
        assert con.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0
    row = store.job(con, 'job')
    assert row['source_name'] == '' and row['archive_path'] is None and row['note_path'] is None
    assert row['active_run_id'] is None and row['language_override'] is None
    assert row['status'] == 'skipped' and row['skip_reason'] == 'user_excluded'
    assert con.execute('SELECT sha256 FROM tombstones').fetchone()[0] == 'a' * 64
    with pytest.raises(store.Conflict):
        store_ops.set_language_override(con, 'job', 'ko')


def test_pending_delete_survives_connection_restart(state, tmp_path):
    con, row, settings = state
    store_ops.request_delete_local(con, 'job')
    with closing(store.connect(tmp_path / 'state.sqlite3')) as second:
        assert store_ops.pending_deletions(second)[0]['job_id'] == 'job'
        assert store_ops.deleted(second, 'job')
    with pytest.raises(KeyError):
        store_ops.request_delete_local(con, 'missing')
