import json
import os
import signal
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from quietclerk import config, store


@pytest.fixture
def state(tmp_path):
    con = store.connect(tmp_path / 'state.sqlite3')
    yield con
    con.close()


def add(con, suffix='a', status='queued', skip_reason=None, archive='/synthetic/source.m4a'):
    return store.add_job(con, '20261109-101500-' + suffix, suffix * 64, suffix + '.m4a', archive, 600,
                         status, skip_reason=skip_reason, now=1)


def claim(con, boot='boot', now=10):
    return store.claim(con, boot, {'root': '/synthetic', 'language.mode': 'ko', 'providers.consent': {}}, now=now)


def owner(row, boot='boot'):
    return row['job_id'], row['active_run_id'], boot


def test_schema_and_connection_pragmas(state):
    assert state.execute('PRAGMA foreign_keys').fetchone()[0] == 1
    assert state.execute('PRAGMA busy_timeout').fetchone()[0] == 15000
    assert state.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
    assert state.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == '2'


@pytest.mark.parametrize('outcome', ['done', 'failed', 'retry_wait', 'blocked', 'too_short', 'before_cutoff', 'no_speech', 'user_excluded'])
def test_allowed_process_transitions_reset_counters(state, tmp_path, outcome):
    archive = tmp_path / 'source.m4a'
    archive.write_bytes(b'verified recording')
    if outcome in ('too_short', 'before_cutoff'):
        row = add(state, status='skipped', skip_reason=outcome, archive=str(archive))
    else:
        add(state, archive=str(archive))
        row = claim(state)
        args = owner(row)
        if outcome == 'done':
            store.complete(state, *args, '/synthetic/note.md')
        elif outcome in ('failed', 'retry_wait', 'blocked'):
            store.fail(state, *args, 'error', retryable=outcome != 'failed',
                       blocked_reason='auth' if outcome == 'blocked' else None)
        elif outcome == 'no_speech':
            store.skip_no_speech(state, *args)
        else:
            store.exclude(state, row['job_id'])
            assert store.checkpoint(state, *args) is False
    state.execute('UPDATE jobs SET sha256=?', (store.sha256(archive),))
    assert store.request_process(state, row['job_id'], 'resummarize') is True
    new = store.job(state, row['job_id'])
    assert (new['status'], new['requested_mode'], new['attempts'], new['interrupt_count'],
            new['next_attempt_at'], new['blocked_reason']) == ('queued', 'resummarize', 0, 0, 0, None)
    assert store.request_process(state, row['job_id']) is False


def test_disallowed_requests_and_stale_writes(state):
    row = add(state)
    running = claim(state)
    with pytest.raises(store.Conflict) as err:
        store.request_process(state, row['job_id'])
    assert err.value.status == 'running'
    for args in ((row['job_id'], 'wrong-run', 'boot'), (*owner(running)[:2], 'other-boot')):
        with pytest.raises(store.LostClaim):
            store.start_stage(state, *args, 'convert')
        with pytest.raises(store.LostClaim):
            store.complete(state, *args, '/wrong.md')
        with pytest.raises(store.LostClaim):
            store.fail(state, *args, 'wrong')
    assert state.execute('SELECT COUNT(*) FROM stage_runs').fetchone()[0] == 0
    with pytest.raises(ValueError):
        store.request_process(state, row['job_id'], 'invalid')
    with pytest.raises(KeyError):
        store.request_process(state, 'missing')
    store.fail(state, *owner(running), 'error')
    # A migrated non-overridable rejection must not be promoted.
    state.execute("UPDATE jobs SET status='skipped',skip_reason='legacy_rejected'")
    with pytest.raises(store.Conflict):
        store.request_process(state, row['job_id'])


@pytest.mark.parametrize('status', ['queued', 'retry_wait', 'failed', 'done', 'skipped'])
def test_exclude_from_any_nonrunning_state(state, tmp_path, status):
    archive = tmp_path / 'source.m4a'
    archive.write_bytes(b'verified recording')
    row = add(state, archive=str(archive))
    state.execute('UPDATE jobs SET sha256=?', (store.sha256(archive),))
    state.execute('UPDATE jobs SET status=?', (status,))
    store.exclude(state, row['job_id'])
    result = store.job(state, row['job_id'])
    assert (result['status'], result['skip_reason']) == ('skipped', 'user_excluded')
    store.request_process(state, row['job_id'])
    assert store.job(state, row['job_id'])['status'] == 'queued'


def test_two_connections_claim_only_one_run(tmp_path):
    path = tmp_path / 'state.sqlite3'
    con = store.connect(path)
    add(con)
    con.close()
    barrier = threading.Barrier(2)

    def concurrent(boot):
        connection = store.connect(path)
        try:
            barrier.wait(timeout=5)
            result = claim(connection, boot)
            return result is not None
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as threads:
        assert sorted(threads.map(concurrent, ('one', 'two'))) == [False, True]
    con = store.connect(path)
    assert con.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 1
    con.close()


def test_retry_budget_and_blocked_not_time_released(state):
    row = add(state)
    for attempt in range(1, 4):
        running = claim(state, now=10000 * attempt)
        store.fail(state, *owner(running), 'temporary', now=10000 * attempt)
        result = store.job(state, row['job_id'])
        assert result['attempts'] == attempt
        assert result['status'] == ('failed' if attempt == 3 else 'retry_wait')
        if attempt < 3:
            assert result['next_attempt_at'] == 10000 * attempt + 300 * attempt
            assert claim(state, now=result['next_attempt_at'] - 1) is None
    assert result['last_error'] == 'max_attempts'
    store.request_process(state, row['job_id'])
    running = claim(state)
    store.fail(state, *owner(running), 'login required', blocked_reason='auth')
    assert claim(state, now=1e20) is None
    assert store.job(state, row['job_id'])['attempts'] == 0
    store.request_process(state, row['job_id'])
    assert claim(state) is not None


def test_interruption_three_times_attempts_unchanged(state):
    row = add(state)
    for number in range(1, 4):
        running = claim(state, boot=f'boot{number}', now=number * 10)
        store.start_stage(state, *owner(running, f'boot{number}'), 'convert')
        assert store.recover(state, f'boot{number}', now=number * 10) == []
        assert store.recover(state, f'new{number}', now=number * 10) == [row['job_id']]
        result = store.job(state, row['job_id'])
        assert result['interrupt_count'] == number
        assert result['attempts'] == 0
        assert result['status'] == ('failed' if number == 3 else 'retry_wait')
    assert result['last_error'] == 'interrupted_repeatedly'
    assert {r[0] for r in state.execute('SELECT status FROM runs')} == {'interrupted'}
    assert {r[0] for r in state.execute('SELECT status FROM stage_runs')} == {'interrupted'}


@pytest.mark.parametrize('point', ['claimed', 'stage', 'run_inserted'])
def test_sigkill_recovery_at_transaction_boundaries(tmp_path, point):
    path = tmp_path / 'state.sqlite3'
    con = store.connect(path)
    row = add(con)
    con.close()
    script = '''
import signal, sys
from quietclerk import store
con=store.connect(sys.argv[1])
point=sys.argv[2]
if point == 'run_inserted':
    def trace(sql):
        if sql.startswith('UPDATE jobs SET active_run_id='):
            print('ready', flush=True)
            signal.pause()
    con.set_trace_callback(trace)
row=store.claim(con,'killed',{'root':'/synthetic'},now=10)
if point == 'stage':
    store.start_stage(con,row['job_id'],row['active_run_id'],'killed','convert')
print('ready',flush=True)
signal.pause()
'''
    child = subprocess.Popen([sys.executable, '-c', script, str(path), point], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == 'ready'
        child.kill()
        child.communicate(timeout=5)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
    con = store.connect(path)
    recovered = store.recover(con, 'new', now=20)
    result = store.job(con, row['job_id'])
    assert result['attempts'] == 0
    if point == 'run_inserted':
        assert recovered == []
        assert result['status'] == 'queued'
        assert con.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 0
    else:
        assert recovered == [row['job_id']]
        assert (result['status'], result['interrupt_count']) == ('retry_wait', 1)
        assert con.execute('SELECT status FROM runs').fetchone()[0] == 'interrupted'
        if point == 'stage':
            assert con.execute('SELECT status FROM stage_runs').fetchone()[0] == 'interrupted'
    con.close()


def test_snapshot_and_last_success_pointer(state):
    row = add(state)
    settings = {'root': '/synthetic', 'providers.consent': {'codex': ['transcript']}, 'language.mode': 'ko'}
    running = store.claim(state, 'boot', settings)
    settings['providers.consent']['codex'].append('source_name')
    saved = json.loads(state.execute('SELECT settings_json FROM runs').fetchone()[0])
    assert saved['providers.consent']['codex'] == ['transcript']
    store.complete(state, *owner(running), '/first.md')
    store.request_process(state, row['job_id'])
    next_run = store.claim(state, 'boot', settings)
    assert next_run['current_run_id'] == running['active_run_id']
    store.fail(state, *owner(next_run), 'temporary')
    assert store.job(state, row['job_id'])['note_path'] == '/first.md'
    saved = json.loads(state.execute('SELECT settings_json FROM runs WHERE run_id=?', (next_run['active_run_id'],)).fetchone()[0])
    assert saved['providers.consent']['codex'] == ['transcript', 'source_name']


def test_pending_exclusion_survives_interruption(state):
    row = add(state)
    running = claim(state)
    store.exclude(state, row['job_id'])
    store.recover(state, 'new', now=20)
    result = store.job(state, row['job_id'])
    assert (result['status'], result['skip_reason']) == ('skipped', 'user_excluded')
    assert result['attempts'] == 0


@pytest.mark.parametrize('outcome', ['blocked', 'failure', 'success'])
def test_blocked_failure_and_success_reset_interrupt_count(state, outcome):
    add(state)
    running = claim(state)
    store.recover(state, 'new', now=10)
    running = claim(state, boot='new', now=10)
    assert running['interrupt_count'] == 1
    if outcome == 'success':
        store.complete(state, *owner(running, 'new'), '/synthetic/note.md')
    else:
        store.fail(state, *owner(running, 'new'), 'temporary',
                   blocked_reason='auth' if outcome == 'blocked' else None)
    assert store.job(state, running['job_id'])['interrupt_count'] == 0


def test_late_exclusion_wins_over_success_commit(state):
    row = add(state)
    running = claim(state)
    store.exclude(state, row['job_id'])
    assert store.complete(state, *owner(running), '/must-not-be-current.md') is False
    result = store.job(state, row['job_id'])
    assert (result['status'], result['skip_reason'], result['current_run_id']) == ('skipped', 'user_excluded', None)


def test_promotion_requires_matching_verified_archive(state):
    row = add(state, status='skipped', skip_reason='too_short', archive=None)
    with pytest.raises(store.Conflict):
        store.request_process(state, row['job_id'])
    with pytest.raises(store.Conflict):
        store.promote(state, row['job_id'], 'wrong', '/verified/source.m4a')
    assert store.job(state, row['job_id'])['status'] == 'skipped'
    store.promote(state, row['job_id'], row['sha256'], '/verified/source.m4a')
    result = store.job(state, row['job_id'])
    assert (result['status'], result['archive_path']) == ('queued', '/verified/source.m4a')


@pytest.mark.parametrize('outcome', ['failure', 'terminal', 'blocked', 'timeout', 'no_speech'])
def test_pending_exclusion_wins_over_all_failure_paths(state, outcome):
    row = add(state)
    running = claim(state)
    args = owner(running)
    store.start_stage(state, *args, 'convert')
    store.exclude(state, row['job_id'])
    if outcome == 'no_speech':
        store.skip_no_speech(state, *args)
    else:
        store.fail(state, *args, 'timeout:convert' if outcome == 'timeout' else 'error',
                   retryable=outcome != 'terminal', blocked_reason='auth' if outcome == 'blocked' else None)
    result = store.job(state, row['job_id'])
    assert (result['status'], result['skip_reason'], result['exclude_requested']) == ('skipped', 'user_excluded', 0)
    assert result['attempts'] == 0 and result['active_run_id'] is None
    assert state.execute('SELECT status,error FROM runs').fetchone()[:] == ('skipped', 'user_excluded')
    assert state.execute('SELECT status FROM stage_runs').fetchone()[0] == 'cancelled'


@pytest.mark.parametrize('archive_kind', ['missing', 'directory', 'wrong_hash', 'verified'])
def test_skipped_request_requires_existing_hash_verified_archive(state, tmp_path, archive_kind):
    archive = tmp_path / 'archive'
    if archive_kind == 'directory':
        archive.mkdir()
    elif archive_kind != 'missing':
        archive.write_bytes(b'recording')
    row = add(state, status='skipped', skip_reason='before_cutoff', archive=str(archive))
    if archive_kind == 'verified':
        state.execute('UPDATE jobs SET sha256=?', (store.sha256(archive),))
        assert store.request_process(state, row['job_id'])
        assert store.job(state, row['job_id'])['status'] == 'queued'
    else:
        with pytest.raises(store.Conflict):
            store.request_process(state, row['job_id'])
        assert store.job(state, row['job_id'])['status'] == 'skipped'


def test_stage_can_finish_not_run(state):
    add(state)
    running = claim(state)
    store.start_stage(state, *owner(running), 'detect_language')
    store.finish_stage(state, *owner(running), 'detect_language', status='not_run')
    assert state.execute('SELECT status FROM stage_runs').fetchone()[0] == 'not_run'
