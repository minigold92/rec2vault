"""Persistent record of decoy tool-block checks (contract 8.5).

A row binds one verdict to what was actually tested: the provider, the full version string (suffixes such as
`-beta.1` included, never normalised), the real path of the executable and the SHA-256 of that file. A
different version, path or file content has no row, so it is simply not verified.

Two kinds of failure are kept apart. A security failure (canary exposed, a tool or unknown event, a changed
working directory) is permanent for that exact version and file. A transient failure (exit code, timeout, no
output: sign-in, rate limit, network) is not a verdict: it only schedules the next automatic test with a
back-off. The row holds the verdict, a reason code and event-kind counts, never a response body.
Reading it never creates a database: a provider status read must not write files.
"""
import json
import sqlite3
from pathlib import Path

from .store import transaction

SOURCES = ('auto', 'manual')
BACKOFF = (30 * 60, 2 * 3600, 6 * 3600)   # after the 1st, 2nd and 3rd transient failure; 6 h from then on


def backoff(attempts):
    return BACKOFF[min(max(attempts, 1), len(BACKOFF)) - 1]


def ensure_schema(con):
    columns = [row[1] for row in con.execute("SELECT * FROM pragma_table_info('provider_tool_checks')")]
    if columns and 'sha256' not in columns:
        con.execute('DROP TABLE provider_tool_checks')   # unbound verdicts of the first version cannot be trusted
    con.executescript('''
    CREATE TABLE IF NOT EXISTS provider_tool_checks (
      provider TEXT NOT NULL, version TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL,
      checked_at REAL NOT NULL, passed INTEGER NOT NULL CHECK (passed IN (0,1)), reason TEXT NOT NULL,
      events TEXT NOT NULL, source TEXT NOT NULL CHECK (source IN ('auto','manual')),
      transient INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL,
      PRIMARY KEY (provider, version, path, sha256));
    ''')


def record(con, provider, version, path, sha256, passed, reason, events, source, checked_at, transient=False):
    if source not in SOURCES or (passed and transient):
        raise ValueError(source)
    with transaction(con):
        row = con.execute('SELECT attempts,transient FROM provider_tool_checks WHERE provider=? AND version=? '
                          'AND path=? AND sha256=?', (provider, version, path, sha256)).fetchone()
        attempts = (row['attempts'] if row and row['transient'] else 0) + 1 if transient else 0
        con.execute('''INSERT INTO provider_tool_checks(provider,version,path,sha256,checked_at,passed,reason,events,
                       source,transient,attempts,retry_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(provider,version,path,sha256) DO UPDATE SET checked_at=excluded.checked_at,
                       passed=excluded.passed,reason=excluded.reason,events=excluded.events,source=excluded.source,
                       transient=excluded.transient,attempts=excluded.attempts,retry_at=excluded.retry_at''',
                    (provider, version, path, sha256, checked_at, 1 if passed else 0, reason,
                     json.dumps(events, sort_keys=True), source, 1 if transient else 0, attempts,
                     checked_at + backoff(attempts) if transient else None))


def recorded(root, provider, version, path, sha256):
    """The stored verdict for exactly this version, file path and file content, or None (also: no database)."""
    if not root or not version or not path or not sha256:
        return None
    database = Path(root) / 'state.sqlite3'
    if not database.is_file():
        return None
    try:
        con = sqlite3.connect(database, timeout=5)
        try:
            row = con.execute('SELECT checked_at,passed,reason,events,source,transient,attempts,retry_at '
                              'FROM provider_tool_checks WHERE provider=? AND version=? AND path=? AND sha256=?',
                              (provider, version, path, sha256)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return {'version': version, 'checked_at': row[0], 'passed': bool(row[1]), 'reason': row[2],
            'events': json.loads(row[3]), 'source': row[4], 'transient': bool(row[5]), 'attempts': row[6],
            'retry_at': row[7]}


def settled(row, now):
    """Whether an automatic test has nothing left to do for this row: a verdict, or a back-off not yet over."""
    return row is not None and (row['passed'] or not row['transient'] or now < row['retry_at'])
