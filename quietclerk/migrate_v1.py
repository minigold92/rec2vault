"""Offline v1 migration; inbox-relative observations are revalidated on the next scan.

Unknown file hashes stay NULL; outside-inbox observations are omitted and recorded
in meta.migration_report. Absent archives are never treated as promotion evidence.
Never called implicitly by store.connect().
"""
import argparse
import fcntl
import json
import os
import re
import sqlite3
import time
import unicodedata
from contextlib import closing
from pathlib import Path

from . import store

V1_COLUMNS = {
    'files': [('path', 'TEXT'), ('size', 'INTEGER'), ('mtime', 'REAL'), ('last_change', 'REAL'), ('handled', 'INTEGER')],
    'jobs': [('job_id', 'TEXT'), ('sha256', 'TEXT'), ('source_name', 'TEXT'), ('archive_path', 'TEXT'),
             ('duration_sec', 'REAL'), ('status', 'TEXT'), ('stage', 'TEXT'), ('attempts', 'INTEGER'),
             ('error', 'TEXT'), ('warnings', 'TEXT'), ('output_path', 'TEXT'), ('created_at', 'REAL'), ('updated_at', 'REAL')],
}


def _validate(con):
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    if 'meta' in names:
        version = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if version and version[0] == '2':
            return False
        raise ValueError('unsupported schema version')
    if names != set(V1_COLUMNS):
        raise ValueError('unknown v1 tables')
    for name, columns in V1_COLUMNS.items():
        if [(r[1], r[2]) for r in con.execute(f'PRAGMA table_info({name})')] != columns:
            raise ValueError(f'unknown v1 {name} structure')
    known = {'queued', 'done', 'skipped', 'failed_retryable', 'failed_final', 'running'}
    if any(r[0] not in known for r in con.execute('SELECT DISTINCT status FROM jobs')):
        raise ValueError('unknown v1 state')
    return True


def migrate(path, *, inbox=None, service_stopped=False, fault=None):
    if not service_stopped:
        raise ValueError('stop and reap the old service before migration')
    path = Path(path).resolve()
    inbox = Path(inbox).expanduser().resolve() if inbox is not None else path.parent / 'inbox'
    # Read-only validation happens before making a lock, backup, journal or new table.
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as check:
        if not _validate(check):
            return None
    # Do not flock the SQLite inode: on macOS that conflicts with SQLite's own locks.
    with path.with_name(path.name + '.migration.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        con = sqlite3.connect(path, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA busy_timeout=15000')
        con.execute('PRAGMA foreign_keys=ON')
        try:
            if not _validate(con):
                return None
            backup = path.with_name(path.name + f'.bak-{time.time_ns()}')
            part = backup.with_name(backup.name + '.part')
            try:
                with closing(sqlite3.connect(part)) as target:
                    con.backup(target)
                os.replace(part, backup)
            finally:
                part.unlink(missing_ok=True)
            if fault:
                fault('backed_up')
            names = re.findall(r'CREATE TABLE (\w+)', store.SCHEMA)
            schema = store.SCHEMA
            for name in names:
                schema = re.sub(r'\b' + name + r'\b', name + '_v2', schema)
            with store.transaction(con):
                for statement in schema.split(';'):
                    if statement.strip():
                        con.execute(statement)
                jobs = con.execute('SELECT * FROM jobs').fetchall()
                report = {'dropped_files': [], 'cleared_archives': []}
                seen = set()
                for row in con.execute('SELECT * FROM files').fetchall():
                    old_path = Path(row['path'])
                    candidate = old_path if old_path.is_absolute() else inbox / old_path
                    try:
                        relative = str(candidate.resolve().relative_to(inbox))
                    except ValueError:
                        report['dropped_files'].append({'path': row['path'], 'reason': 'outside_inbox'})
                        continue
                    if relative in seen:
                        raise ValueError(f'colliding inbox paths: {relative}')
                    seen.add(relative)
                    con.execute('INSERT INTO files_v2(path,name_nfc,source,size,mtime,last_change,'
                                'intake_status,reject_reason,sha256,first_seen) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                (relative, unicodedata.normalize('NFC', Path(relative).name), 'migrated',
                                 row['size'], row['mtime'], row['last_change'], 'waiting',
                                 None, None, row['last_change']))
                for row in jobs:
                    status = {'failed_retryable': 'retry_wait', 'failed_final': 'failed', 'running': 'retry_wait'}.get(row['status'], row['status'])
                    reason = row['error'] if row['error'] in ('too_short', 'before_cutoff') else None
                    rejected = row['error'] in ('decode', 'too_big', 'too_long', 'format')
                    if rejected:
                        status, reason = 'skipped', 'legacy_rejected'
                    archive = row['archive_path']
                    if not archive or not Path(archive).is_file():
                        if archive:
                            report['cleared_archives'].append(archive)
                        archive = None
                    con.execute('''INSERT INTO jobs_v2(job_id,sha256,source_name,recorded_at,archive_path,duration_sec,
                         status,skip_reason,stage,attempts,next_attempt_at,last_error,note_path,review_reasons,
                         legacy,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)''',
                                (row['job_id'], row['sha256'], row['source_name'], row['job_id'][:15], archive,
                                 row['duration_sec'], status, reason, None, row['attempts'],
                                 row['updated_at'] + 300 * row['attempts'] if row['status'] == 'failed_retryable' else 0,
                                 'interrupted' if row['status'] == 'running' else row['error'], row['output_path'],
                                 json.dumps(row['warnings'].splitlines()) if row['warnings'] else None,
                                 row['created_at'], row['updated_at']))
                if fault:
                    fault('converted')
                con.execute('DROP TABLE files')
                con.execute('DROP TABLE jobs')
                for name in names:
                    con.execute(f'ALTER TABLE {name}_v2 RENAME TO {name}')
                con.execute("INSERT INTO meta VALUES('schema_version','2')")
                con.execute("INSERT INTO meta VALUES('migration_report',?)", (json.dumps(report),))
                if fault:
                    fault('swapped')
            return backup
        finally:
            con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--service-stopped', action='store_true', required=True)
    parser.add_argument('--inbox', type=Path, help='receiving folder (default: database sibling inbox)')
    args = parser.parse_args()
    backup = migrate(args.database, inbox=args.inbox, service_stopped=args.service_stopped)
    print(backup or 'already v2')


if __name__ == '__main__':
    main()
