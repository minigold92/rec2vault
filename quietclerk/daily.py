"""Opt-in daily-note links; never regenerate or normalize user-owned bytes.

The writer locks cooperating publications, checks content again immediately before
atomic replacement, and refuses an observed concurrent edit rather than losing it.
All path traversal uses no-follow directory descriptors, including the vault root.
"""
import fcntl
import os
import re
import stat
import threading
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

_writer_lock = threading.Lock()


class DailyConflict(ValueError):
    """Unsafe path or concurrently changed daily note; publication stays intact."""


def template_path(template, recorded):
    if (not isinstance(template, str) or not template or len(template) > 4096 or
            any(unicodedata.category(c).startswith('C') for c in template)):
        raise DailyConflict('invalid daily-note path')
    remainder = template.replace('{date}', '')
    if '{' in remainder or '}' in remainder or '\\' in template:
        raise DailyConflict('only {date} is supported in daily-note paths')
    path = Path(template.replace('{date}', recorded.strftime('%Y-%m-%d'))).expanduser()
    if '..' in path.parts or path.suffix.lower() != '.md':
        raise DailyConflict('daily-note path must be a Markdown file without ..')
    return path


def _safe_ancestors(path):
    if '..' in path.parts:
        raise DailyConflict('parent traversal is not allowed')
    for parent in (*reversed(path.parents), path):
        if parent.is_symlink():
            raise DailyConflict('symbolic links are not allowed')


def destination(settings, recorded):
    """Validate the configured template, output ancestry and enclosing vault."""
    # System-level links (/tmp -> /private/tmp, a symlinked home) are resolved first;
    # the containment check below then rejects any link that leaves the vault.
    output = Path(settings.get('output')).expanduser().resolve()
    _safe_ancestors(output)
    vault = None
    for parent in (output, *output.parents):
        marker = parent / '.obsidian'
        if marker.is_symlink():
            raise DailyConflict('symbolic vault marker is not allowed')
        if marker.is_dir():
            vault = parent
            break
    if vault is None:
        raise DailyConflict('output has no enclosing Obsidian vault')
    target = template_path(settings.get('daily_note.path'), recorded)
    target = target if target.is_absolute() else vault / target
    if target.is_symlink():
        raise DailyConflict('symbolic links are not allowed')
    target = target.parent.resolve() / target.name
    if not target.is_relative_to(vault):
        raise DailyConflict('daily note must be inside the output vault')
    _safe_ancestors(target)
    if target.exists() and not target.is_file():
        raise DailyConflict('daily note must be a regular file')
    return vault, target


@contextmanager
def _directory(path):
    """Pin every ancestor; a later symlink swap cannot redirect writes outside it."""
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _read(fd, name):
    try:
        source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except FileNotFoundError:
        return None, None
    with os.fdopen(source, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise DailyConflict('daily note must be a regular file')
        return stream.read(), (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size)


def _append(data, heading, stem, line):
    """Insert inside just this H2 section; preserve all existing bytes verbatim."""
    rows = data.splitlines(keepends=True)
    start = next((i for i, row in enumerate(rows) if row.rstrip(b'\r\n') == heading), None)
    newline = b'\r\n' if b'\r\n' in data else b'\n'
    if start is None:
        prefix = b'' if not data or data.endswith(b'\n') else newline
        return data + prefix + heading + newline + line + newline
    end = next((i for i in range(start + 1, len(rows)) if re.match(rb'^#{1,2} ', rows[i])), len(rows))
    identity = re.compile(rb'\[\[' + re.escape(stem.encode('utf-8')) + rb'(?:\||\]\])')
    if any(identity.search(row) for row in rows[start + 1:end]):
        return data
    prefix = b'' if rows[start].endswith(b'\n') else newline
    return b''.join(rows[:start + 1]) + prefix + line + newline + b''.join(rows[start + 1:])


def link(settings, note_path, title, recorded):
    """Add one recording-date link; return the daily path, or None when disabled.

    `recorded` accepts a datetime or the engine's YYYYMMDD-HHMMSS timestamp.
    Failures raise DailyConflict/OSError for the post-publication hook to report;
    they never roll back or modify the published meeting note.
    """
    if not settings.get('daily_note.path'):
        return None
    if not isinstance(recorded, datetime):
        recorded = datetime.strptime(recorded, '%Y%m%d-%H%M%S')
    vault, target = destination(settings, recorded)
    note = Path(note_path).expanduser()
    if note.is_symlink():
        raise DailyConflict('symbolic links are not allowed')
    note = note.parent.resolve() / note.name
    _safe_ancestors(note)
    if not note.is_relative_to(vault) or note == target or not note.is_file():
        raise DailyConflict('published note must be a different regular file in the vault')
    if not isinstance(title, str) or not title.strip() or len(title) > 500 or any(
            unicodedata.category(c).startswith('C') for c in title):
        raise DailyConflict('invalid daily-link title')
    # Display text cannot close a wiki link or enable an HTML/plugin expression.
    alias = title.strip().translate(str.maketrans({'[': '［', ']': '］', '|': '｜', '<': '＜', '>': '＞', '`': '｀', '=': '＝'}))
    stem = note.stem
    if any(c in stem for c in '[]|\\\r\n'):
        raise DailyConflict('invalid published note name')
    language = settings.get('notes.output_language')
    if language == 'same':
        from .notes import NoteConflict, parse_note
        with _directory(note.parent) as source_fd:
            note_data, _ = _read(source_fd, note.name)
        try:
            props, _ = parse_note(note_data or b'')
        except NoteConflict as exc:
            raise DailyConflict('published note has invalid language metadata') from exc
        language = props.get('language')
        if language not in ('ko', 'en'):
            raise DailyConflict('published note has invalid language metadata')
    heading = ('## Meetings' if language == 'en' else '## 회의록').encode('utf-8')
    entry = f'- {recorded:%H:%M} [[{stem}|{alias}]]'.encode('utf-8')
    with _writer_lock, _directory(target.parent) as fd:
        try:
            lock_fd = os.open('.quietclerk-daily.lock', os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW,
                              0o600, dir_fd=fd)
        except FileExistsError:
            lock_fd = os.open('.quietclerk-daily.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(lock_fd, 'a') as lock:
            if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
                raise DailyConflict('invalid daily-note lock')
            fcntl.flock(lock, fcntl.LOCK_EX)
            original, identity = _read(fd, target.name)
            updated = _append(original or b'', heading, stem, entry)
            if updated == original:
                return target
            temporary = f'.quietclerk-daily-{uuid.uuid4().hex}.part'
            try:
                temp_fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                                  0o600, dir_fd=fd)
                with os.fdopen(temp_fd, 'wb') as stream:
                    stream.write(updated)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Both file identity and exact bytes must still match the snapshot.
                current, current_identity = _read(fd, target.name)
                if current != original or current_identity != identity:
                    raise DailyConflict('daily note changed while adding a link')
                destination(settings, recorded)  # Recheck externally renamed ancestry.
                pinned = os.fstat(fd)
                actual = target.parent.stat()
                if (pinned.st_dev, pinned.st_ino) != (actual.st_dev, actual.st_ino):
                    raise DailyConflict('daily-note directory changed')
                if original is None:
                    # A newly created user file must never be overwritten.
                    os.link(temporary, target.name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                else:
                    os.replace(temporary, target.name, src_dir_fd=fd, dst_dir_fd=fd)
            finally:
                try:
                    os.unlink(temporary, dir_fd=fd)
                except FileNotFoundError:
                    pass
    return target
