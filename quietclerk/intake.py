"""Contract §5 input lifecycle: stable source → private validation → immutable archive.

Invariants: untrusted names are never archive paths; only a complete stable copy is
probed; duplicates and policy skips never retain quarantine data. Replacements
stay waiting, and a failed promotion never changes the original skipped job.
"""
import errno
import hashlib
import os
import re
import stat
import time
from datetime import datetime
from pathlib import Path

from . import backfill, config, probe, quarantine, store

DiskLow = quarantine.DiskLow


class ScanResult(list):
    """Created IDs, plus a scan-level warning (not a fabricated job)."""
    blocked_reason = None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def recorded_at(name: str, mtime: float) -> datetime:
    match = re.search(r'(\d{6})_(\d{6})', name)
    if match:
        try:
            return datetime.strptime(match.group(1) + match.group(2), '%y%m%d%H%M%S')
        except ValueError:
            pass
    return datetime.fromtimestamp(mtime)


def candidates(inbox: Path):
    """Only immediate non-hidden regular .m4a entries; never follow a symlink."""
    if not inbox.is_dir():
        return
    for path in sorted(inbox.iterdir()):
        if path.suffix.lower() != '.m4a' or backfill.nfc(path.name).startswith(('.', '통화')):
            continue
        try:
            if stat.S_ISREG(path.lstat().st_mode):
                yield path
        except FileNotFoundError:
            continue


def waiting_info(row, now=None):
    """Display-only: a long-empty file remains waiting and can later grow."""
    now = time.time() if now is None else now
    return 'empty_file' if (row['intake_status'] == 'waiting' and row['size'] == 0
                            and now - row['last_change'] >= 3600) else None


def _options(settings):
    return (Path(settings.get('inbox')), settings.root / 'archive', settings.root / 'quarantine',
            settings.get('stable_sec'), min(settings.get('min_duration_sec'), settings.get('memo.min_sec'))
            if settings.get('memo.enabled') else settings.get('min_duration_sec'),
            datetime.strptime(settings.get('since'), '%Y-%m-%d %H:%M'), settings.root / 'include.txt')


def _job_id(con, when, digest):
    for length in (8, 16, 32):
        candidate = f'{when:%Y%m%d-%H%M%S}-{digest[:length]}'
        row = con.execute('SELECT sha256 FROM jobs WHERE job_id=?', (candidate,)).fetchone()
        if row is None or row['sha256'] == digest:
            return candidate
    raise RuntimeError('job_id collision after 32 hash characters')


def _archive(partial, archive_root, job_id, available):
    quarantine.require_space(archive_root, available)
    target = archive_root / job_id / 'source.m4a'
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        partial.replace(target)
    except OSError as exc:
        if exc.errno == errno.ENOSPC:
            raise DiskLow('disk_low') from exc
        raise
    return target


def _register(con, path, st, partial, digest, duration, options, now, available):
    inbox, archive_root, _, _, minimum, since, include = options
    relative = path.name
    if store.job_by_sha(con, digest):
        store.finish_intake(con, relative, 'duplicate', digest)
        return None
    if con.execute('SELECT 1 FROM tombstones WHERE sha256=?', (digest,)).fetchone():
        store.finish_intake(con, relative, 'rejected', digest, 'deleted_by_user')
        return None
    when = recorded_at(path.name, st.st_mtime)
    # Safety limits cannot be bypassed by the include list or a policy override.
    if duration > config.MAX_DURATION_SEC:
        store.finish_intake(con, relative, 'rejected', reason='too_long')
        return None
    reason = 'too_short' if duration < minimum else None
    if reason is None and since and when < since and backfill.nfc(path.name) not in backfill.included(include):
        reason = 'before_cutoff'
    job_id = _job_id(con, when, digest)
    archive = _archive(partial, archive_root, job_id, available) if reason is None else None
    store.add_job(con, job_id, digest, backfill.nfc(path.name), str(archive) if archive else None,
                  duration, 'queued' if reason is None else 'skipped', skip_reason=reason,
                  recorded_at=when.strftime('%Y%m%d-%H%M%S'), now=now)
    store.finish_intake(con, relative, 'registered', digest)
    return job_id


def scan(con, now: float | None = None, *, settings, free_space=None) -> list[str]:
    """One pass. A disk_low result stops copying/archiving, not observation."""
    now = time.time() if now is None else now
    options = _options(settings)
    inbox, _, root, stable, _, _, _ = options
    created = ScanResult()
    for path in candidates(inbox):
        partial = None
        try:
            st = path.lstat()
            if not stat.S_ISREG(st.st_mode):
                continue
            row = store.observe(con, path.name, st.st_size, st.st_mtime, now)
            if row['intake_status'] != 'waiting' or st.st_size == 0:
                continue
            if now - row['last_change'] < stable or now - st.st_mtime < stable:
                continue
            if created.blocked_reason:
                continue
            partial, digest = quarantine.copy(inbox, path.name, root, config.MAX_BYTES,
                                               expected=st, available=free_space)
            duration = probe.duration(partial)
            job_id = _register(con, path, st, partial, digest, duration, options, now, free_space)
            if job_id:
                created.append(job_id)
        except (quarantine.Changed, FileNotFoundError, NotADirectoryError):
            continue
        except DiskLow:
            created.blocked_reason = 'disk_low'
        except probe.Rejected as exc:
            store.finish_intake(con, path.name, 'rejected', reason=exc.reason)
        finally:
            if partial is not None:
                partial.unlink(missing_ok=True)
    return created


def promote(con, job_id, mode='auto', *, settings, now=None, free_space=None):
    """Revalidate current originals, including renamed files. False means no original.

    A changed original is registered by the normal policy path, never substituted
    for the skipped job. Non-policy rejections remain impossible to override.
    """
    row = store.job(con, job_id)
    if (row['status'] != 'skipped' or row['skip_reason'] not in store.POLICY_REASONS
            or (row['legacy'] and row['last_error'] in ('decode', 'too_big', 'too_long', 'format'))):
        raise store.Conflict(row['status'])
    if mode not in store.MODES:
        raise ValueError(mode)
    now = time.time() if now is None else now
    options = _options(settings)
    inbox, archive_root, root, _, _, _, _ = options
    known = {r['path'] for r in con.execute('SELECT path FROM files WHERE sha256=?', (row['sha256'],))}
    paths = sorted(candidates(inbox), key=lambda p: (p.name not in known, p.name))
    for path in paths:
        partial = None
        try:
            st = path.lstat()
            partial, digest = quarantine.copy(inbox, path.name, root, config.MAX_BYTES,
                                               expected=st, available=free_space)
            duration = probe.duration(partial)
            if digest != row['sha256']:
                if path.name in known:
                    store.observe(con, path.name, st.st_size, st.st_mtime, now)
                    _register(con, path, st, partial, digest, duration, options, now, free_space)
                continue
            store.observe(con, path.name, st.st_size, st.st_mtime, now)
            if duration > config.MAX_DURATION_SEC:
                store.finish_intake(con, path.name, 'rejected', reason='too_long')
                continue
            if con.execute('SELECT 1 FROM tombstones WHERE sha256=?', (digest,)).fetchone():
                store.finish_intake(con, path.name, 'rejected', digest, 'deleted_by_user')
                continue
            archive = _archive(partial, archive_root, job_id, free_space)
            store.promote(con, job_id, digest, archive, mode=mode, now=now)
            store.finish_intake(con, path.name, 'registered', digest)
            return True
        except (quarantine.Changed, FileNotFoundError, NotADirectoryError):
            continue
        except probe.Rejected as exc:
            if path.name in known:
                store.observe(con, path.name, st.st_size, st.st_mtime, now)
                store.finish_intake(con, path.name, 'rejected', reason=exc.reason)
        finally:
            if partial is not None:
                partial.unlink(missing_ok=True)
    return False
