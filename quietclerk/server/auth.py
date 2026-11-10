"""§9.1 token/session boundary. Secrets are never in URLs sent to HTTP or logs.

Only the empty bootstrap shell and its fixed JS are public: a browser cannot
execute the fragment exchange otherwise. They contain no application data.
"""
import hashlib
import json
import os
import secrets
import stat
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ..install import _atomic

COOKIE = 'qc_session'


@dataclass
class Session:
    csrf: str
    created: float
    touched: float


class Auth:
    def __init__(self, support, port, *, clock=time.time):
        self.path = Path(support) / 'bootstrap.json'
        self.port, self.clock = port, clock
        self.lock = threading.Lock()
        self.token, self.expires = None, 0
        self.sessions = {}
        self.resume_path = Path(support) / 'update-sessions.json'
        self._restore()

    @staticmethod
    def _key(sid):
        return hashlib.sha256(sid.encode()).hexdigest() if isinstance(sid, str) else None

    def _restore(self):
        """Only pre-authorized update restarts resume sessions, for at most 15 minutes."""
        try:
            fd = os.open(self.resume_path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd) as stream:
                info = os.fstat(stream.fileno())
                if (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or
                        not stat.S_ISREG(info.st_mode) or info.st_size > 1 << 20):
                    return
                data = json.load(stream)
            if data['port'] != self.port or not self.clock() < data['expires'] <= self.clock() + 900:
                return
            for key, value in data['sessions'].items():
                if len(key) == 64 and all(c in '0123456789abcdef' for c in key):
                    self.sessions[key] = Session(value['csrf'], value['created'], value['touched'])
        except (OSError, ValueError, KeyError, TypeError):
            self.sessions.clear()

    def preserve_for_update(self):
        with self.lock:
            self.resume_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            now = self.clock()
            sessions = {key: {'csrf': value.csrf, 'created': value.created, 'touched': value.touched}
                        for key, value in self.sessions.items()
                        if self._valid(value, now)}
            _atomic(self.resume_path, json.dumps({'port': self.port, 'expires': now + 900,
                                                  'sessions': sessions}).encode())

    @staticmethod
    def _valid(session, now):
        return now - session.touched < 12 * 3600 and now - session.created < 7 * 86400

    def _issue(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.token, self.expires = secrets.token_urlsafe(32), self.clock() + 60
        fd, temporary = tempfile.mkstemp(prefix='.bootstrap-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump({'token': self.token, 'port': self.port, 'expires': self.expires}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def refresh(self):
        with self.lock:
            if self.token is None or self.clock() >= self.expires:
                self._issue()
            now = self.clock()
            self.sessions = {key: value for key, value in self.sessions.items()
                             if self._valid(value, now)}

    def exchange(self, token):
        with self.lock:
            if (not isinstance(token, str) or not token.isascii() or not self.token or
                    self.clock() >= self.expires or not secrets.compare_digest(token, self.token)):
                return None
            sid, csrf, now = secrets.token_urlsafe(32), secrets.token_urlsafe(32), self.clock()
            self.sessions[self._key(sid)] = Session(csrf, now, now)
            self._issue()  # A later `open` reads a new token; replay never succeeds.
            return sid, csrf

    def session(self, sid, *, touch=True):
        with self.lock:
            session = self.sessions.get(self._key(sid))
            now = self.clock()
            if session and self._valid(session, now):
                if touch:
                    session.touched = now
                return session
            self.sessions.pop(self._key(sid), None)
            return None

    def logout(self, sid):
        with self.lock:
            key = self._key(sid)
            self.sessions.pop(key, None)
            # A logged-out cookie must not reappear on the next restart.
            try:
                data = json.loads(self.resume_path.read_text())
                data['sessions'].pop(key, None)
                _atomic(self.resume_path, json.dumps(data).encode())
            except (OSError, ValueError, KeyError, TypeError):
                pass

    def close(self):
        self.path.unlink(missing_ok=True)
        with self.lock:
            self.sessions.clear()
            self.token = None
