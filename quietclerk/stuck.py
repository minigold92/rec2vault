"""Recordings that have waited a long time in the same state without any progress (operations metric `stuck_jobs`).

An unfinished recording is "waiting" while it is `queued` or `retry_wait`, and its state is the pair
(status, blocked_reason). `job_state_since` holds when the job entered its current state. The row is written by
SQLite triggers inside the very transaction that changes `status` or `blocked_reason`, so the date is exact
and no polling is involved: any change of state, running included, starts a new date (progress resets the
clock), and a job that leaves the waiting states loses its row. The date is the transition's `updated_at`
(or the clock when a writer did not move it). Recordings already waiting when the table appeared are dated from
their `updated_at` once, by `observe`. `failed`, `skipped` and `done` recordings are never counted.

While the engine is paused nothing can start, so `queued` and plain back-off waits are not counted (a person
chose that wait); `retry_wait` with a blocked reason still is. Resuming restarts the clock of those waits.
"""
import time

from . import store_ops
from .store import transaction

WAITING = ('queued', 'retry_wait')
_NOW = "(julianday('now') - 2440587.5) * 86400.0"


def ensure_schema(con):
    con.executescript(f'''
    CREATE TABLE IF NOT EXISTS job_state_since (
      job_id TEXT PRIMARY KEY, state TEXT NOT NULL, since REAL NOT NULL);
    CREATE TRIGGER IF NOT EXISTS job_state_since_insert AFTER INSERT ON jobs
    WHEN NEW.status IN ('queued','retry_wait')
    BEGIN
      INSERT OR REPLACE INTO job_state_since(job_id,state,since)
      VALUES(NEW.job_id, NEW.status || ':' || COALESCE(NEW.blocked_reason, ''), NEW.updated_at);
    END;
    CREATE TRIGGER IF NOT EXISTS job_state_since_update AFTER UPDATE OF status, blocked_reason ON jobs
    WHEN OLD.status IS NOT NEW.status OR OLD.blocked_reason IS NOT NEW.blocked_reason
    BEGIN
      DELETE FROM job_state_since WHERE job_id = NEW.job_id;
      INSERT INTO job_state_since(job_id,state,since)
      SELECT NEW.job_id, NEW.status || ':' || COALESCE(NEW.blocked_reason, ''),
             CASE WHEN NEW.updated_at > OLD.updated_at THEN NEW.updated_at ELSE {_NOW} END
      WHERE NEW.status IN ('queued','retry_wait');
    END;
    CREATE TRIGGER IF NOT EXISTS job_state_since_delete AFTER DELETE ON jobs
    BEGIN
      DELETE FROM job_state_since WHERE job_id = OLD.job_id;
    END;
    ''')


def state(row):
    return f"{row['status']}:{row['blocked_reason'] or ''}"


def reason(row):
    return row['blocked_reason'] or row['status']


def restart_plain_waits(con, now):
    """Resume: a wait that only the pause caused starts counting from now. Call inside the resume transaction."""
    con.execute("UPDATE job_state_since SET since=? WHERE state IN ('queued:','retry_wait:')", (now,))


def since_map(con):
    return {row['job_id']: (row['state'], row['since']) for row in con.execute('SELECT * FROM job_state_since')}


def since(row, known):
    """When this job entered its current waiting state (the trigger's record when it matches, else updated_at)."""
    entry = known.get(row['job_id'])
    return entry[1] if entry and entry[0] == state(row) else row['updated_at']


def counts_now(row, paused):
    return row['status'] in WAITING and not row['exclude_requested'] and not (paused and not row['blocked_reason'])


def hours_waiting(row, known, threshold_hours, now, paused=False):
    """Whole hours a waiting job has been in its state once that reaches the threshold, else None."""
    if not counts_now(row, paused):
        return None
    elapsed = now - min(since(row, known), now)
    return int(elapsed // 3600) if elapsed >= threshold_hours * 3600 else None


def observe(con, threshold_hours, now=None):
    """Count the jobs waiting at least `threshold_hours` (dating once any that predate the triggers).

    Returns {'count', 'reasons': {code: n}, 'started'}; `started` is true exactly when the count went from 0
    to positive since the previous call (kept in `meta`, so a restart does not announce it again).
    """
    now = time.time() if now is None else now
    paused = store_ops.paused(con)
    rows = con.execute("SELECT job_id,status,blocked_reason,updated_at,exclude_requested FROM jobs "
                       "WHERE status IN ('queued','retry_wait')").fetchall()
    reasons = {}
    with transaction(con):
        known = since_map(con)
        for row in rows:
            if row['job_id'] not in known or known[row['job_id']][0] != state(row):
                known[row['job_id']] = (state(row), min(row['updated_at'], now))
                con.execute('INSERT INTO job_state_since(job_id,state,since) VALUES(?,?,?) '
                            'ON CONFLICT(job_id) DO UPDATE SET state=excluded.state,since=excluded.since',
                            (row['job_id'], *known[row['job_id']]))
            if counts_now(row, paused) and now - known[row['job_id']][1] >= threshold_hours * 3600:
                reasons[reason(row)] = reasons.get(reason(row), 0) + 1
        con.execute("DELETE FROM job_state_since WHERE job_id NOT IN "
                    "(SELECT job_id FROM jobs WHERE status IN ('queued','retry_wait'))")
        count = sum(reasons.values())
        previous = con.execute("SELECT value FROM meta WHERE key='stuck_jobs'").fetchone()
        con.execute("INSERT INTO meta(key,value) VALUES('stuck_jobs',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(count),))
    return {'count': count, 'reasons': reasons, 'started': count > 0 and int(previous['value'] if previous else 0) == 0}
