"""Recordings that have waited a long time in the same state without any progress (operations metric `stuck_jobs`).

An unfinished recording is "waiting" while it is `queued` or `retry_wait`, and its state is the pair
(status, blocked_reason). `job_state_since` remembers when the monitor first saw the job in its current
state, starting from the job's `updated_at` (the moment of the transition, so recordings that were already
blocked before this table existed are dated correctly). Any change of state, including running, forgets the
date: progress resets the clock. `failed` and `skipped` recordings are never counted.
"""
import time

from .store import transaction

WAITING = ('queued', 'retry_wait')


def ensure_schema(con):
    con.executescript('''
    CREATE TABLE IF NOT EXISTS job_state_since (
      job_id TEXT PRIMARY KEY, state TEXT NOT NULL, since REAL NOT NULL);
    ''')


def state(row):
    return f"{row['status']}:{row['blocked_reason'] or ''}"


def reason(row):
    return row['blocked_reason'] or row['status']


def since_map(con):
    return {row['job_id']: (row['state'], row['since']) for row in con.execute('SELECT * FROM job_state_since')}


def since(row, known):
    """When this job entered its current waiting state (the monitor's record when it matches, else updated_at)."""
    entry = known.get(row['job_id'])
    return entry[1] if entry and entry[0] == state(row) else row['updated_at']


def hours_waiting(row, known, threshold_hours, now):
    """Whole hours a waiting job has been in its state once that reaches the threshold, else None."""
    if row['status'] not in WAITING or row['exclude_requested']:
        return None
    elapsed = now - min(since(row, known), now)
    return int(elapsed // 3600) if elapsed >= threshold_hours * 3600 else None


def observe(con, threshold_hours, now=None):
    """Refresh the state dates and count the jobs waiting at least `threshold_hours`.

    Returns {'count', 'reasons': {code: n}, 'started'}; `started` is true exactly when the count went from 0
    to positive since the previous call (kept in `meta`, so a restart does not announce it again).
    """
    now = time.time() if now is None else now
    rows = con.execute("SELECT job_id,status,blocked_reason,updated_at,exclude_requested FROM jobs "
                       "WHERE status IN ('queued','retry_wait') AND exclude_requested=0").fetchall()
    reasons = {}
    with transaction(con):
        known = since_map(con)
        live = set()
        for row in rows:
            live.add(row['job_id'])
            if row['job_id'] in known and known[row['job_id']][0] == state(row):
                date = known[row['job_id']][1]
            else:
                date = min(row['updated_at'], now)
                con.execute('INSERT INTO job_state_since(job_id,state,since) VALUES(?,?,?) '
                            'ON CONFLICT(job_id) DO UPDATE SET state=excluded.state,since=excluded.since',
                            (row['job_id'], state(row), date))
            if now - date >= threshold_hours * 3600:
                reasons[reason(row)] = reasons.get(reason(row), 0) + 1
        for job_id in set(known) - live:
            con.execute('DELETE FROM job_state_since WHERE job_id=?', (job_id,))
        count = sum(reasons.values())
        previous = con.execute("SELECT value FROM meta WHERE key='stuck_jobs'").fetchone()
        con.execute("INSERT INTO meta(key,value) VALUES('stuck_jobs',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(count),))
    return {'count': count, 'reasons': reasons, 'started': count > 0 and int(previous['value'] if previous else 0) == 0}
