"""Persistent record of decoy tool-block checks, one row per provider version (contract 8.5).

A row says whether that exact version passed the decoy test; the row holds the verdict, the
reason code and a count of event kinds, never a response body. Reading it never creates a
database: a provider status read must not write files.
"""
import json
import sqlite3
from pathlib import Path

from .store import transaction

SOURCES = ('auto', 'manual')


def ensure_schema(con):
    con.executescript('''
    CREATE TABLE IF NOT EXISTS provider_tool_checks (
      provider TEXT NOT NULL, version TEXT NOT NULL, checked_at REAL NOT NULL,
      passed INTEGER NOT NULL CHECK (passed IN (0,1)), reason TEXT NOT NULL, events TEXT NOT NULL,
      source TEXT NOT NULL CHECK (source IN ('auto','manual')),
      PRIMARY KEY (provider, version));
    ''')


def record(con, provider, version, passed, reason, events, source, checked_at):
    if source not in SOURCES:
        raise ValueError(source)
    with transaction(con):
        con.execute('''INSERT INTO provider_tool_checks(provider,version,checked_at,passed,reason,events,source)
                       VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(provider,version) DO UPDATE SET checked_at=excluded.checked_at,
                       passed=excluded.passed,reason=excluded.reason,events=excluded.events,source=excluded.source''',
                    (provider, version, checked_at, 1 if passed else 0, reason, json.dumps(events, sort_keys=True), source))


def recorded(root, provider, version):
    """The stored verdict for this exact version, or None (no database, no table or no row)."""
    if not root or not version:
        return None
    path = Path(root) / 'state.sqlite3'
    if not path.is_file():
        return None
    try:
        con = sqlite3.connect(path, timeout=5)
        try:
            row = con.execute('SELECT checked_at,passed,reason,events,source FROM provider_tool_checks '
                              'WHERE provider=? AND version=?', (provider, version)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return {'version': version, 'checked_at': row[0], 'passed': bool(row[1]), 'reason': row[2],
            'events': json.loads(row[3]), 'source': row[4]}
