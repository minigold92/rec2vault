"""Service state transactions, separate from the executor's owned store module.

Deletion is durable and idempotent: tombstone and exclusion precede filesystem
cleanup; metadata is removed only after that cleanup succeeds. A running claim
must reach its normal exclusion checkpoint before cleanup can finish.
"""
import time

from .store import Conflict, job, transaction


def paused(con):
    row = con.execute("SELECT value FROM meta WHERE key='paused'").fetchone()
    return row is not None and row['value'] == 'true'


def set_paused(con, value):
    if type(value) is not bool:
        raise ValueError('expected boolean')
    with transaction(con):
        con.execute("INSERT INTO meta(key,value) VALUES('paused',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value", ('true' if value else 'false',))


def deleted(con, job_id):
    row = job(con, job_id)
    return con.execute('SELECT 1 FROM tombstones WHERE sha256=?', (row['sha256'],)).fetchone() is not None


def set_language_override(con, job_id, override):
    if override not in ('ko', 'en', None):
        raise ValueError('expected ko, en, or null')
    with transaction(con):
        row = job(con, job_id)
        if row['status'] == 'running' or deleted(con, job_id):
            raise Conflict(row['status'])
        if row['language_override'] != override:
            con.execute('UPDATE jobs SET language_override=?,updated_at=? WHERE job_id=?',
                        (override, time.time(), job_id))


def request_delete_local(con, job_id):
    now = time.time()
    with transaction(con):
        row = job(con, job_id)
        key = 'delete_local:' + job_id
        if con.execute('SELECT 1 FROM meta WHERE key=?', (key,)).fetchone():
            return False
        if deleted(con, job_id):
            return False
        con.execute('INSERT INTO tombstones(sha256,deleted_at) VALUES(?,?)', (row['sha256'], now))
        con.execute('INSERT INTO meta(key,value) VALUES(?,?)', (key, job_id))
        if row['status'] == 'running':
            con.execute('UPDATE jobs SET exclude_requested=1,updated_at=? WHERE job_id=?', (now, job_id))
        else:
            con.execute("UPDATE jobs SET status='skipped',skip_reason='user_excluded',exclude_requested=0,"
                        'updated_at=? WHERE job_id=?', (now, job_id))
    return True


def pending_deletions(con):
    return con.execute("SELECT jobs.* FROM jobs JOIN meta ON meta.key='delete_local:'||jobs.job_id "
                       "ORDER BY jobs.job_id").fetchall()


def finish_delete_local(con, job_id):
    with transaction(con):
        row = job(con, job_id)
        if row['status'] == 'running':
            raise Conflict(row['status'])
        key = 'delete_local:' + job_id
        if not con.execute('SELECT 1 FROM meta WHERE key=?', (key,)).fetchone():
            return False
        con.execute('DELETE FROM publications WHERE job_id=?', (job_id,))
        con.execute('DELETE FROM stage_runs WHERE run_id IN (SELECT run_id FROM runs WHERE job_id=?)', (job_id,))
        con.execute('DELETE FROM runs WHERE job_id=?', (job_id,))
        con.execute('DELETE FROM note_fields WHERE job_id=?', (job_id,))
        con.execute('DELETE FROM note_tasks WHERE job_id=?', (job_id,))
        con.execute('DELETE FROM speaker_overrides WHERE job_id=?', (job_id,))
        con.execute('DELETE FROM transcript_edits WHERE job_id=?', (job_id,))
        con.execute('DELETE FROM search WHERE job_id=?', (job_id,))
        con.execute("UPDATE jobs SET status='skipped',skip_reason='user_excluded',exclude_requested=0,"
                    "source_name='',archive_path=NULL,duration_sec=NULL,stage=NULL,"
                    "language_override=NULL,claimed_by=NULL,claimed_at=NULL,active_run_id=NULL,current_run_id=NULL,"
                    "note_path=NULL,review_reasons=NULL,last_error=NULL,blocked_reason=NULL,attempts=0,"
                    "interrupt_count=0,next_attempt_at=0,updated_at=? WHERE job_id=?", (time.time(), job_id))
        con.execute('DELETE FROM meta WHERE key=?', (key,))
    return True
