"""Client-side reader of the server's private bootstrap file.

Standard library only: the installer and CLI read it without importing the server
package (which needs the web dependencies and initializes configuration).
"""
import json
import os
import stat
import time
from pathlib import Path


def read_bootstrap(support, *, clock=time.time):
    """CLI file-only exchange; reject symlinks, wrong owner, and broad modes."""
    fd = os.open(Path(support) / 'bootstrap.json', os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or not stat.S_ISREG(info.st_mode):
            raise RuntimeError('bootstrap file must be owned by this user with mode 0600')
        data = json.load(stream)
    if data['expires'] <= clock() or not isinstance(data['token'], str) or not 1 <= data['port'] <= 65535:
        raise RuntimeError('bootstrap token expired; wait for the running server')
    return data
