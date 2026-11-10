"""One locked pass: recover stale claims, scan, then execute queued jobs serially.

python -m quietclerk.tick. This is not the future serve/HTTP service.
"""
import fcntl
import logging
import sys
import uuid

from . import config, intake, notes, store
from .executor import Executor


def main(*, settings=None, registry=None):
    settings = config.load() if settings is None else settings
    root = settings.root
    root.mkdir(parents=True, exist_ok=True)
    (root / 'logs').mkdir(exist_ok=True)
    logging.basicConfig(filename=root / 'logs' / 'pipeline.log', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    with (root / 'tick.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        con = store.connect(root / 'state.sqlite3')
        try:
            boot = uuid.uuid4().hex
            store.recover(con, boot, recover_publication=notes.recover_publication)
            scanned = intake.scan(con, settings=settings)
            if getattr(scanned, 'blocked_reason', None) == 'disk_low':
                store.set_engine_state(con, 'disk_low')
            executor = Executor(con, boot, settings, registry=registry)
            while executor.run_one() is not None:
                pass
        finally:
            con.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
