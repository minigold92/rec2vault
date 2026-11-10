"""Transactional v2 state boundary. Callers never write job state directly."""
import json
import sqlite3
import time
import unicodedata
import uuid
from contextlib import contextmanager
from pathlib import Path

from .artifacts import sha256

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE files (
  path TEXT PRIMARY KEY, name_nfc TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('syncthing','upload','migrated')),
  size INTEGER NOT NULL, mtime REAL NOT NULL, last_change REAL NOT NULL,
  intake_status TEXT NOT NULL CHECK (intake_status IN ('waiting','rejected','registered','duplicate')),
  reject_reason TEXT, sha256 TEXT, first_seen REAL NOT NULL);
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY, sha256 TEXT UNIQUE NOT NULL,
  source_name TEXT NOT NULL, recorded_at TEXT NOT NULL, archive_path TEXT, duration_sec REAL,
  status TEXT NOT NULL CHECK (status IN ('skipped','queued','running','retry_wait','failed','done')),
  skip_reason TEXT, stage TEXT, requested_mode TEXT NOT NULL DEFAULT 'auto',
  attempts INTEGER NOT NULL DEFAULT 0, interrupt_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at REAL NOT NULL DEFAULT 0, blocked_reason TEXT, last_error TEXT,
  exclude_requested INTEGER NOT NULL DEFAULT 0,
  language_override TEXT CHECK (language_override IN ('ko','en')),
  claimed_by TEXT, claimed_at REAL, active_run_id TEXT, current_run_id TEXT,
  note_path TEXT, review_reasons TEXT, legacy INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE runs (
  run_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(job_id),
  mode TEXT NOT NULL CHECK (mode IN ('auto','resume','from_transcribe','resummarize')),
  settings_json TEXT NOT NULL, consent_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('running','done','failed','interrupted','skipped','cancelled')),
  started_at REAL NOT NULL, finished_at REAL, error TEXT);
CREATE UNIQUE INDEX one_active_run ON runs(job_id) WHERE status='running';
CREATE TABLE stage_runs (
  run_id TEXT NOT NULL REFERENCES runs(run_id), stage TEXT NOT NULL, seq INTEGER NOT NULL,
  parent_seq INTEGER, chunk TEXT,
  status TEXT NOT NULL CHECK (status IN ('running','reused','done','failed','timeout','interrupted','cancelled','not_run')),
  backend TEXT, model TEXT, provider TEXT,
  endpoint_class TEXT CHECK (endpoint_class IN ('local','external','unknown')),
  sent_fields TEXT, reused_from TEXT,
  started_at REAL, finished_at REAL, error TEXT,
  PRIMARY KEY (run_id, stage, seq));
CREATE TABLE publications (
  run_id TEXT PRIMARY KEY REFERENCES runs(run_id), job_id TEXT NOT NULL,
  target_path TEXT NOT NULL, prev_hash TEXT, new_hash TEXT NOT NULL, temp_path TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('prepared','renamed','committed','conflict')), updated_at REAL NOT NULL);
CREATE TABLE note_fields (
  job_id TEXT NOT NULL REFERENCES jobs(job_id), field TEXT NOT NULL,
  owner TEXT NOT NULL CHECK (owner IN ('engine','user')), last_generated TEXT,
  PRIMARY KEY (job_id, field));
CREATE TABLE note_tasks (
  task_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(job_id),
  first_run_id TEXT NOT NULL, text TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE tombstones (sha256 TEXT PRIMARY KEY, deleted_at REAL NOT NULL);
"""

class Conflict(RuntimeError):
    """Maps to HTTP 409, carrying the current job status."""
    def __init__(self, status):
        self.status = status
        super().__init__(status)


class LostClaim(Conflict):
    pass


@contextmanager
def transaction(con):
    con.execute('BEGIN IMMEDIATE')
    try:
        yield
        con.commit()
    except BaseException:
        con.rollback()
        raise


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA busy_timeout=15000')
    con.execute('PRAGMA foreign_keys=ON')
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if tables:
        version = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() if 'meta' in tables else None
        if version is None or version[0] != '2':
            con.close()
            raise ValueError('database requires explicit v1 migration or is unsupported')
    con.execute('PRAGMA journal_mode=WAL')
    if not tables:
        con.executescript('BEGIN IMMEDIATE;\n' + SCHEMA +
                          "\nINSERT INTO meta VALUES('schema_version','2');\nCOMMIT;")
    _migrate_vault_state(con, path.parent)
    from . import overrides, search
    overrides.ensure_schema(con)
    search.ensure_schema(con)
    return con


def job(con, job_id):
    row = con.execute('SELECT * FROM jobs WHERE job_id=?', (job_id,)).fetchone()
    if row is None:
        raise KeyError(job_id)
    return row


def job_by_sha(con, sha):
    return con.execute('SELECT * FROM jobs WHERE sha256=?', (sha,)).fetchone()


def observe(con, path, size, mtime, now, source='syncthing'):
    with transaction(con):
        con.execute("""INSERT INTO files(path,name_nfc,source,size,mtime,last_change,intake_status,first_seen)
                       VALUES(?,?,?,?,?,?,'waiting',?) ON CONFLICT(path) DO UPDATE SET
                       size=excluded.size,mtime=excluded.mtime,last_change=excluded.last_change,
                       intake_status='waiting',reject_reason=NULL,sha256=NULL
                       WHERE files.size<>excluded.size OR files.mtime<>excluded.mtime""",
                    (path, unicodedata.normalize('NFC', Path(path).name), source, size, mtime, now, now))
    return con.execute('SELECT * FROM files WHERE path=?', (path,)).fetchone()


def finish_intake(con, path, status, sha=None, reason=None):
    if status not in ('registered', 'duplicate', 'rejected'):
        raise ValueError(status)
    with transaction(con):
        con.execute('UPDATE files SET intake_status=?,sha256=?,reject_reason=? WHERE path=?',
                    (status, sha, reason, path))


def add_job(con, job_id, sha, source_name, archive_path, duration, status='queued', skip_reason=None,
            recorded_at=None, now=None):
    if status not in ('queued', 'skipped') or (status == 'skipped' and skip_reason not in
                                             ('too_short', 'before_cutoff')):
        raise ValueError('invalid intake state')
    now = time.time() if now is None else now
    with transaction(con):
        con.execute("""INSERT INTO jobs(job_id,sha256,source_name,recorded_at,archive_path,duration_sec,
                       status,skip_reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (job_id, sha, source_name, recorded_at or job_id[:15], archive_path, duration,
                     status, skip_reason, now, now))
    return job(con, job_id)


MODES = ('auto', 'resume', 'from_transcribe', 'resummarize')
POLICY_REASONS = ('too_short', 'before_cutoff', 'no_speech', 'user_excluded')
BLOCKED_REASONS = ('auth', 'no_local_provider', 'no_verified_provider', 'disk_low', 'vault_migration')


def _check_request(row):
    legacy_rejected = row['legacy'] and row['last_error'] in ('decode', 'too_big', 'too_long', 'format')
    if (row['status'] == 'running' or legacy_rejected or
            (row['status'] == 'skipped' and row['skip_reason'] not in POLICY_REASONS)):
        raise Conflict(row['status'])


def _check_not_deleted(con, row):
    if (con.execute('SELECT 1 FROM tombstones WHERE sha256=?', (row['sha256'],)).fetchone() or
            con.execute('SELECT 1 FROM meta WHERE key=?', ('delete_local:' + row['job_id'],)).fetchone()):
        raise Conflict(row['status'])


def _queue(con, job_id, mode, now):
    con.execute("""UPDATE jobs SET requested_mode=?,attempts=0,interrupt_count=0,next_attempt_at=0,
                   blocked_reason=NULL,status='queued',skip_reason=NULL,exclude_requested=0,
                   updated_at=? WHERE job_id=?""", (mode, now, job_id))


def request_process(con, job_id, mode='auto', now=None):
    if mode not in MODES:
        raise ValueError(mode)
    now = time.time() if now is None else now
    with transaction(con):
        row = job(con, job_id)
        _check_not_deleted(con, row)
        if row['status'] == 'queued':
            return False
        _check_request(row)
        if row['status'] == 'skipped':
            try:
                verified = (row['archive_path'] and Path(row['archive_path']).is_file() and
                            sha256(row['archive_path']) == row['sha256'])
            except OSError:
                verified = False
            if not verified:
                raise Conflict(row['status'])  # B must revalidate and archive before promotion.
        _queue(con, job_id, mode, now)
    return True


def promote(con, job_id, verified_sha256, archive_path, mode='auto', now=None):
    """B calls only after revalidation and archive finalization, never on raw input."""
    if mode not in MODES or not archive_path:
        raise ValueError('invalid promotion')
    now = time.time() if now is None else now
    with transaction(con):
        row = job(con, job_id)
        _check_not_deleted(con, row)
        _check_request(row)
        if row['status'] != 'skipped' or row['sha256'] != verified_sha256:
            raise Conflict(row['status'])
        con.execute('UPDATE jobs SET archive_path=? WHERE job_id=?', (str(archive_path), job_id))
        _queue(con, job_id, mode, now)


def exclude(con, job_id, now=None):
    now = time.time() if now is None else now
    with transaction(con):
        row = job(con, job_id)
        if row['status'] == 'running':
            con.execute('UPDATE jobs SET exclude_requested=1,updated_at=? WHERE job_id=?', (now, job_id))
        else:
            con.execute("""UPDATE jobs SET status='skipped',skip_reason='user_excluded',
                           exclude_requested=0,updated_at=? WHERE job_id=?""", (now, job_id))


def claim(con, boot, settings, now=None, paused=False):
    if paused:
        return None
    now = time.time() if now is None else now
    snapshot = settings.snapshot() if hasattr(settings, 'snapshot') else dict(settings)
    with transaction(con):
        row = con.execute("""SELECT * FROM jobs WHERE
              (status='queued' OR (status='retry_wait' AND blocked_reason IS NULL AND next_attempt_at<=?))
              AND exclude_requested=0
              AND NOT EXISTS (SELECT 1 FROM tombstones WHERE tombstones.sha256=jobs.sha256)
              AND NOT EXISTS (SELECT 1 FROM meta WHERE meta.key='delete_local:'||jobs.job_id)
              ORDER BY created_at,job_id LIMIT 1""", (now,)).fetchone()
        if row is None:
            return None
        changed = con.execute("""UPDATE jobs SET status='running',claimed_by=?,claimed_at=?,updated_at=?
                     WHERE job_id=? AND exclude_requested=0 AND
                     (status='queued' OR (status='retry_wait' AND blocked_reason IS NULL AND next_attempt_at<=?))""",
                              (boot, now, now, row['job_id'], now)).rowcount
        if changed != 1:
            return None
        run_id = uuid.uuid4().hex
        snapshot['language_override'] = row['language_override']
        con.execute("""INSERT INTO runs(run_id,job_id,mode,settings_json,consent_json,status,started_at)
                       VALUES(?,?,?,?,?,'running',?)""",
                    (run_id, row['job_id'], row['requested_mode'], json.dumps(snapshot, sort_keys=True),
                     json.dumps(snapshot.get('providers.consent', {}), sort_keys=True), now))
        con.execute('UPDATE jobs SET active_run_id=? WHERE job_id=?', (run_id, row['job_id']))
    return job(con, row['job_id'])


def _owned(con, job_id, run_id, boot):
    row = job(con, job_id)
    if row['status'] != 'running' or row['active_run_id'] != run_id or row['claimed_by'] != boot:
        raise LostClaim(row['status'])
    return row


def checkpoint(con, job_id, run_id, boot, now=None):
    now = time.time() if now is None else now
    with transaction(con):
        row = _owned(con, job_id, run_id, boot)
        if not row['exclude_requested']:
            return True
        _skip_excluded(con, row, run_id, now)
    return False


def start_stage(con, job_id, run_id, boot, stage, seq=1, **fields):
    allowed = {'parent_seq', 'chunk', 'backend', 'model', 'provider', 'endpoint_class', 'sent_fields'}
    if fields.keys() - allowed:
        raise ValueError('unknown stage fields')
    with transaction(con):
        _owned(con, job_id, run_id, boot)
        now = time.time()
        fields = {**fields, 'started_at': now, 'status': 'running'}
        if 'sent_fields' in fields:
            fields['sent_fields'] = json.dumps(fields['sent_fields'])
        columns = ','.join(fields)
        con.execute(f"INSERT INTO stage_runs(run_id,stage,seq,{columns}) VALUES(?,?,?,{','.join('?' for _ in fields)})",
                    (run_id, stage, seq, *fields.values()))
        con.execute('UPDATE jobs SET stage=?,updated_at=? WHERE job_id=?', (stage, now, job_id))


def annotate_stage(con, job_id, run_id, boot, stage, seq=1, **fields):
    allowed = {'backend', 'model', 'provider', 'endpoint_class', 'sent_fields'}
    if not fields or fields.keys() - allowed:
        raise ValueError('unknown stage fields')
    with transaction(con):
        _owned(con, job_id, run_id, boot)
        if 'sent_fields' in fields:
            fields['sent_fields'] = json.dumps(fields['sent_fields'])
        changed = con.execute(f"UPDATE stage_runs SET {','.join(k + '=?' for k in fields)} "
                              "WHERE run_id=? AND stage=? AND seq=? AND status='running'",
                              (*fields.values(), run_id, stage, seq)).rowcount
        if changed != 1:
            raise Conflict('stage_not_running')


def finish_stage(con, job_id, run_id, boot, stage, status='done', seq=1, error=None, reused_from=None):
    if status not in ('done', 'reused', 'failed', 'timeout', 'cancelled', 'not_run'):
        raise ValueError(status)
    with transaction(con):
        _owned(con, job_id, run_id, boot)
        changed = con.execute("""UPDATE stage_runs SET status=?,finished_at=?,error=?,reused_from=?,
                     sent_fields=CASE WHEN ?='reused' THEN '[]' ELSE sent_fields END
                     WHERE run_id=? AND stage=? AND seq=? AND status='running'""",
                             (status, time.time(), error, reused_from, status, run_id, stage, seq)).rowcount
        if changed != 1:
            raise Conflict('stage_not_running')


def _finish(con, row, run_id, status, now, error=None):
    con.execute('UPDATE runs SET status=?,finished_at=?,error=? WHERE run_id=?', (status, now, error, run_id))
    con.execute("""UPDATE stage_runs SET status=?,finished_at=?,error=? WHERE run_id=? AND status='running'""",
                ('cancelled' if status == 'skipped' else 'failed', now, error, run_id))


def _skip_excluded(con, row, run_id, now):
    _finish(con, row, run_id, 'skipped', now, 'user_excluded')
    con.execute("""UPDATE jobs SET status='skipped',skip_reason='user_excluded',exclude_requested=0,
                   interrupt_count=0,stage=NULL,active_run_id=NULL,claimed_by=NULL,claimed_at=NULL,
                   updated_at=? WHERE job_id=?""", (now, row['job_id']))


def complete(con, job_id, run_id, boot, note_path, review_reasons=None, now=None):
    now = time.time() if now is None else now
    with transaction(con):
        row = _owned(con, job_id, run_id, boot)
        if row['exclude_requested']:
            _skip_excluded(con, row, run_id, now)
            return False
        _finish(con, row, run_id, 'done', now)
        con.execute("""UPDATE jobs SET status='done',current_run_id=?,note_path=?,review_reasons=?,
                  active_run_id=NULL,claimed_by=NULL,claimed_at=NULL,stage=NULL,interrupt_count=0,
                  blocked_reason=NULL,last_error=NULL,updated_at=? WHERE job_id=?""",
                    (run_id, str(note_path), json.dumps(review_reasons or []), now, job_id))
    return True


def fail(con, job_id, run_id, boot, error, retryable=True, blocked_reason=None, now=None):
    if blocked_reason is not None and blocked_reason not in BLOCKED_REASONS:
        raise ValueError(blocked_reason)
    now = time.time() if now is None else now
    with transaction(con):
        row = _owned(con, job_id, run_id, boot)
        if row['exclude_requested']:
            _skip_excluded(con, row, run_id, now)
            return
        attempts = row['attempts'] + (0 if blocked_reason else 1)
        status = 'retry_wait' if blocked_reason or (retryable and attempts < 3) else 'failed'
        last_error = 'max_attempts' if retryable and not blocked_reason and attempts >= 3 else error
        _finish(con, row, run_id, 'failed', now, error)
        con.execute("""UPDATE jobs SET status=?,attempts=?,next_attempt_at=?,blocked_reason=?,last_error=?,
                   interrupt_count=0,stage=NULL,active_run_id=NULL,claimed_by=NULL,claimed_at=NULL,
                   updated_at=? WHERE job_id=?""",
                    (status, attempts, now + 300 * attempts if status == 'retry_wait' else 0,
                     blocked_reason, last_error, now, job_id))


def skip_no_speech(con, job_id, run_id, boot, now=None):
    now = time.time() if now is None else now
    with transaction(con):
        row = _owned(con, job_id, run_id, boot)
        if row['exclude_requested']:
            _skip_excluded(con, row, run_id, now)
            return
        _finish(con, row, run_id, 'skipped', now, 'no_speech')
        con.execute("""UPDATE jobs SET status='skipped',skip_reason='no_speech',interrupt_count=0,
                       stage=NULL,active_run_id=NULL,claimed_by=NULL,claimed_at=NULL,updated_at=?
                       WHERE job_id=?""", (now, job_id))


def recover(con, boot, now=None, recover_publication=None):
    now = time.time() if now is None else now
    recovered = []
    # Publication recovery is deliberately before the interruption transaction.
    publications = con.execute("""SELECT publications.* FROM publications JOIN jobs USING(job_id)
        WHERE publications.state IN ('prepared','renamed') AND
        (jobs.status<>'running' OR jobs.active_run_id<>publications.run_id OR
         jobs.claimed_by IS NULL OR jobs.claimed_by<>?)""", (boot,)).fetchall()
    for publication in publications:
        if recover_publication is None:
            raise RuntimeError('publication recovery handler required')
        recover_publication(con, publication)
    with transaction(con):
        rows = con.execute("SELECT * FROM jobs WHERE status='running' AND (claimed_by IS NULL OR claimed_by<>?)",
                           (boot,)).fetchall()
        for row in rows:
            count = row['interrupt_count'] + 1
            run_id = row['active_run_id']
            con.execute("UPDATE runs SET status='interrupted',finished_at=?,error='interrupted' WHERE run_id=? AND status='running'",
                        (now, run_id))
            con.execute("""UPDATE stage_runs SET status='interrupted',finished_at=?,error='interrupted'
                           WHERE run_id=? AND status='running'""", (now, run_id))
            con.execute("""UPDATE jobs SET status=?,last_error=?,interrupt_count=?,next_attempt_at=?,
                       blocked_reason=NULL,active_run_id=NULL,claimed_by=NULL,claimed_at=NULL,stage=NULL,
                       updated_at=? WHERE job_id=?""",
                        ('failed' if count >= 3 else 'retry_wait',
                         'interrupted_repeatedly' if count >= 3 else 'interrupted', count, now, now, row['job_id']))
            recovered.append(row['job_id'])
    for row in rows:
        if row['exclude_requested']:
            exclude(con, row['job_id'], now=now)
    return recovered


def engine_state(con):
    row = con.execute("SELECT value FROM meta WHERE key='engine_state'").fetchone()
    return row['value'] if row else None


def set_engine_state(con, state):
    """Persist the engine warning independently of any unclaimed job."""
    with transaction(con):
        if state is None:
            con.execute("DELETE FROM meta WHERE key='engine_state'")
        else:
            con.execute("INSERT INTO meta(key,value) VALUES('engine_state',?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (state,))


def release_disk_low(con):
    """Space recovery unblocks only disk failures, preserving other policy blocks."""
    with transaction(con):
        con.execute("""UPDATE jobs SET blocked_reason=NULL,next_attempt_at=0
                       WHERE status='retry_wait' AND blocked_reason='disk_low'""")


def counts(con):
    return {r['status']: r['n'] for r in con.execute('SELECT status,COUNT(*) n FROM jobs GROUP BY status')}


def note_field_records(con, job_id):
    return {row['field']: dict(row) for row in con.execute('SELECT * FROM note_fields WHERE job_id=?', (job_id,))}


def provenance_rows(con, run_id, stage=None):
    """Stage rows that actually produced a run's outputs: a reused row is replaced by the
    rows of the run it was reused from, so engine and send disclosure survive caching."""
    query = 'SELECT * FROM stage_runs WHERE run_id=?' + (' AND stage=?' if stage else '')
    rows = []
    for row in con.execute(query, (run_id, stage) if stage else (run_id,)).fetchall():
        if row['status'] == 'reused' and row['reused_from']:
            source_run, source_stage = row['reused_from'].split('/', 1)
            rows.extend(provenance_rows(con, source_run, source_stage))
        else:
            rows.append(row)
    return rows


def requeue_resolved_blocks(con, reasons, now=None, *, permitted_fields=None):
    """Reset only resolved blocked jobs, preserving deletion/exclusion authority."""
    reasons = set(reasons)
    if not reasons <= set(BLOCKED_REASONS):
        raise ValueError('unknown blocked reason')
    now = time.time() if now is None else now
    queued = []
    with transaction(con):
        rows = con.execute("SELECT * FROM jobs WHERE status='retry_wait' AND blocked_reason IS NOT NULL").fetchall()
        for row in rows:
            if row['blocked_reason'] not in reasons or row['exclude_requested']:
                continue
            try:
                _check_not_deleted(con, row)
            except Conflict:
                continue
            if permitted_fields is not None:
                stage = con.execute("""SELECT stage FROM stage_runs JOIN runs USING(run_id)
                    WHERE runs.job_id=? ORDER BY runs.started_at DESC,runs.rowid DESC,stage_runs.started_at DESC LIMIT 1""",
                                    (row['job_id'],)).fetchone()
                required = {'transcript'} if stage and stage['stage'] in ('correct', 'summarize') else {
                    'transcript', 'source_name', 'project_list'}
                if not any(required <= fields for fields in permitted_fields.get(row['blocked_reason'], [])):
                    continue
            _queue(con, row['job_id'], row['requested_mode'], now)
            queued.append(row['job_id'])
    return queued


def vault_identity(output):
    return str(Path(output).expanduser().resolve())


def _migrate_vault_state(con, root):
    """Bind old global consent only to its recorded vault, never today's output."""
    old = con.execute("SELECT value FROM meta WHERE key='vault_migration'").fetchone()
    if old is None:
        return
    output = None
    manifest = root / 'note-backups' / 'migration.json'
    if manifest.is_file():
        manifest_state = json.loads(manifest.read_text())
        if manifest_state.get('done') is True:
            output = manifest_state.get('output')
    if output is None:
        run = con.execute("SELECT settings_json FROM runs WHERE status='done' ORDER BY finished_at DESC LIMIT 1").fetchone()
        if run:
            output = json.loads(run['settings_json']).get('output')
    with transaction(con):
        if con.execute("SELECT 1 FROM meta WHERE key='vault_migration'").fetchone() is None:
            return
        markers = con.execute("SELECT key FROM meta WHERE key LIKE 'note_migrated:%'").fetchall()
        con.execute("DELETE FROM meta WHERE key='vault_migration' OR key LIKE 'note_migrated:%'")
        if output is not None and old['value'] == 'done':
            identity = vault_identity(output)
            con.execute("INSERT OR REPLACE INTO meta VALUES(?,'done')", ('vault_migration:' + identity,))
            for row in markers:
                con.execute("INSERT OR REPLACE INTO meta VALUES(?,'done')",
                            ('note_migrated:' + identity + ':' + row['key'].removeprefix('note_migrated:'),))


def vault_migrated(con, output):
    row = con.execute("SELECT value FROM meta WHERE key=?", ('vault_migration:' + vault_identity(output),)).fetchone()
    return row is not None and row['value'] == 'done'


def note_was_migrated(con, job_id, output):
    return con.execute('SELECT 1 FROM meta WHERE key=?',
                       ('note_migrated:' + vault_identity(output) + ':' + job_id,)).fetchone() is not None


def record_vault_migration(con, jobs, output):
    identity = vault_identity(output)
    with transaction(con):
        for job_id in jobs:
            con.execute("INSERT OR REPLACE INTO meta VALUES(?, 'done')", ('note_migrated:' + identity + ':' + job_id,))
            for field in ('title', 'division', 'project', 'attendees', 'status'):
                con.execute("""INSERT OR IGNORE INTO note_fields(job_id,field,owner,last_generated)
                               VALUES(?,?,'user','null')""", (job_id, field))
        con.execute("INSERT OR REPLACE INTO meta VALUES(?,'done')", ('vault_migration:' + identity,))


def prepare_publication(con, job_id, run_id, boot, target, previous_hash, new_hash, temp):
    with transaction(con):
        row = _owned(con, job_id, run_id, boot)
        if row['exclude_requested']:
            raise Conflict('user_excluded')
        con.execute("""INSERT INTO publications VALUES(?,?,?,?,?,?,'prepared',?)""",
                    (run_id, job_id, str(target), previous_hash, new_hash, str(temp), time.time()))


def publication_conflict(con, job_id, run_id, boot):
    with transaction(con):
        _owned(con, job_id, run_id, boot)
        con.execute("UPDATE publications SET state='conflict',updated_at=? WHERE run_id=?", (time.time(), run_id))


def rename_publication(con, job_id, run_id, boot):
    with transaction(con):
        _owned(con, job_id, run_id, boot)
        if con.execute("""UPDATE publications SET state='renamed',updated_at=?
                          WHERE run_id=? AND state='prepared'""", (time.time(), run_id)).rowcount != 1:
            raise Conflict('publication_not_prepared')


def _commit_publication(con, publication, pending):
    now = time.time()
    job_id, run_id = publication['job_id'], publication['run_id']
    row = job(con, job_id)
    if 'overrides' in pending:
        from .overrides import commit_overrides
        if commit_overrides(con, publication, pending):
            return
    for field, record in pending['fields'].items():
        con.execute("""INSERT INTO note_fields VALUES(?,?,?,?) ON CONFLICT(job_id,field)
                       DO UPDATE SET owner=excluded.owner,last_generated=excluded.last_generated""",
                    (job_id, field, record['owner'], record['last_generated']))
    for task in pending['tasks']:
        con.execute("INSERT OR IGNORE INTO note_tasks VALUES(?,?,?,?,?)",
                    (f"{job_id}:{task['task_id']}", job_id, run_id, task['text'], now))
    con.execute("UPDATE runs SET status='done',finished_at=?,error=NULL WHERE run_id=?", (now, run_id))
    con.execute("""UPDATE stage_runs SET status='done',finished_at=?,error=NULL
                   WHERE run_id=? AND stage='note' AND status='running'""", (now, run_id))
    con.execute("""UPDATE jobs SET status='done',current_run_id=?,note_path=?,review_reasons=?,
                   active_run_id=NULL,claimed_by=NULL,claimed_at=NULL,stage=NULL,interrupt_count=0,
                   blocked_reason=NULL,last_error=NULL,updated_at=? WHERE job_id=?""",
                (run_id, publication['target_path'], json.dumps(pending['review_reasons']), now, job_id))
    con.execute("UPDATE publications SET state='committed',updated_at=? WHERE run_id=?", (now, run_id))
    if row['exclude_requested'] or (row['status'] == 'skipped' and row['skip_reason'] == 'user_excluded'):
        _skip_excluded(con, row, run_id, now)
        # The bytes and ownership are committed, but exclusion preserves the last
        # successful run pointer instead of presenting this run as a success.
        con.execute("UPDATE jobs SET current_run_id=? WHERE job_id=?", (row['current_run_id'], job_id))


def commit_publication(con, job_id, run_id, boot, pending):
    with transaction(con):
        _owned(con, job_id, run_id, boot)
        publication = con.execute("SELECT * FROM publications WHERE run_id=? AND state='renamed'", (run_id,)).fetchone()
        if publication is None:
            raise Conflict('publication_not_renamed')
        _commit_publication(con, publication, pending)


def publication_committed(con, run_id):
    return con.execute("SELECT 1 FROM publications WHERE run_id=? AND state='committed'", (run_id,)).fetchone() is not None


def discard_prepared_publication(con, run_id):
    with transaction(con):
        con.execute("DELETE FROM publications WHERE run_id=? AND state='prepared'", (run_id,))


def recover_publication_conflict(con, run_id):
    with transaction(con):
        con.execute("UPDATE publications SET state='conflict',updated_at=? WHERE run_id=?", (time.time(), run_id))
        con.execute("UPDATE jobs SET last_error='note_conflict' WHERE active_run_id=?", (run_id,))


def finish_recovered_publication(con, run_id, pending):
    with transaction(con):
        publication = con.execute("SELECT * FROM publications WHERE run_id=? AND state='renamed'", (run_id,)).fetchone()
        if publication is None:
            return
        row = job(con, publication['job_id'])
        if row['active_run_id'] not in (None, run_id):
            raise LostClaim(row['status'])
        _commit_publication(con, publication, pending)
