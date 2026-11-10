"""Copy a single inbox entry without following links or trusting a changing name."""
import errno
import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import Path

from .probe import Rejected

MIN_FREE_BYTES = 2 << 30


class DiskLow(OSError):
    reason = 'disk_low'


class Changed(OSError):
    """The observed file no longer names the exact regular file we copied."""


def free_bytes(path):
    path = Path(path)
    while not path.exists():
        path = path.parent
    return shutil.disk_usage(path).free


def require_space(path, available=None):
    if (available or free_bytes)(path) < MIN_FREE_BYTES:
        raise DiskLow('disk_low')


def identity(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns


def copy(inbox, name, root, maximum, *, expected=None, available=None):
    """Return (private path, SHA-256); every failure removes the partial copy."""
    if (not name or name in ('.', '..') or '/' in name or '\\' in name or '\0' in name
            or any(ord(char) < 32 for char in name) or Path(name).name != name):
        raise Rejected('path')
    require_space(root, available)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    partial = None
    directory = source = None
    try:
        directory = os.open(inbox, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(source)
        if not stat.S_ISREG(before.st_mode) or (expected is not None and identity(before) != identity(expected)):
            raise Changed(name)
        if before.st_size > maximum:
            raise Rejected('too_big')
        descriptor, temporary = tempfile.mkstemp(prefix='input-', suffix='.part', dir=root)
        partial = Path(temporary)
        digest = hashlib.sha256()
        total = 0
        with os.fdopen(descriptor, 'wb') as output:
            while True:
                block = os.read(source, min(1 << 20, maximum - total + 1))
                if not block:
                    break
                total += len(block)
                if total > maximum:
                    raise Rejected('too_big')
                output.write(block)
                digest.update(block)
        after = os.fstat(source)
        current = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (identity(before) != identity(after) or identity(before) != identity(current)
                or not stat.S_ISREG(current.st_mode) or total != before.st_size):
            raise Changed(name)
        return partial, digest.hexdigest()
    except OSError as exc:
        if partial is not None:
            partial.unlink(missing_ok=True)
        if exc.errno == errno.ENOSPC:
            raise DiskLow('disk_low') from exc
        if exc.errno in (errno.ELOOP, errno.ENOENT, errno.ENOTDIR):
            raise Changed(name) from exc
        raise
    except BaseException:
        if partial is not None:
            partial.unlink(missing_ok=True)
        raise
    finally:
        if source is not None:
            os.close(source)
        if directory is not None:
            os.close(directory)
