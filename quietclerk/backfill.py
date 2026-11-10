"""Select not-yet-received recordings; never promote a skipped job.

Names enter the NFC include list and are removed from exact Syncthing ignore
patterns. Pairing and folder creation remain an installation/user operation.
"""
import fcntl
import os
import tempfile
import sys
import unicodedata
from pathlib import Path

from . import config, syncthing


def nfc(name: str) -> str:
    return unicodedata.normalize('NFC', name)


def valid_name(name):
    return (isinstance(name, str) and bool(name) and name == name.strip()
            and not nfc(name).startswith(('.', '통화')) and name.lower().endswith('.m4a')
            and '/' not in name and '\\' not in name and not any(ord(c) < 32 for c in name))


def included(path) -> set[str]:
    path = Path(path)
    if not path.exists():
        return set()
    return {nfc(line.strip()) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()}


def request(names, *, settings):
    """Return removed ignore patterns; reject all bad names before writing anything."""
    if not names or any(not valid_name(name) for name in names):
        raise ValueError('expected immediate, non-hidden .m4a recording names, excluding calls')
    names = list(dict.fromkeys(nfc(name) for name in names))
    include = settings.root / 'include.txt'
    inbox = Path(settings.get('inbox'))
    include.parent.mkdir(parents=True, exist_ok=True)
    # All callers, including separate CLI processes, serialize the remote
    # GET/POST and the local read/replace as one root-scoped operation.
    with (include.parent / 'backfill.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        removed = syncthing.unignore(inbox, names)
        existing = included(include)
        if set(names) - existing:
            fd, name = tempfile.mkstemp(prefix='.include-', suffix='.part', dir=include.parent)
            part = Path(name)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    stream.write('\n'.join(sorted(existing | set(names))) + '\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                part.replace(include)
            finally:
                part.unlink(missing_ok=True)
        return removed


def main(names: list[str]) -> int:
    try:
        removed = request(names, settings=config.load())
    except ValueError as exc:
        print(f'usage: python -m quietclerk.backfill <recording.m4a>... ({exc})', file=sys.stderr)
        return 2
    print(f"included: {names}\nunignored: {removed or 'none (already syncing or not in the ignore list)'}")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
