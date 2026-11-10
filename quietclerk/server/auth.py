"""§9.1 token/session boundary. Secrets are never in URLs sent to HTTP or logs.

Only the empty bootstrap shell and its fixed JS are public: a browser cannot
execute the fragment exchange otherwise. They contain no application data.
"""
import json
import os
import secrets
import stat
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

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
                             if now - value.touched < 12 * 3600 and now - value.created < 7 * 86400}

    def exchange(self, token):
        with self.lock:
            if (not isinstance(token, str) or not token.isascii() or not self.token or
                    self.clock() >= self.expires or not secrets.compare_digest(token, self.token)):
                return None
            sid, csrf, now = secrets.token_urlsafe(32), secrets.token_urlsafe(32), self.clock()
            self.sessions[sid] = Session(csrf, now, now)
            self._issue()  # A later `open` reads a new token; replay never succeeds.
            return sid, csrf

    def session(self, sid, *, touch=True):
        with self.lock:
            session = self.sessions.get(sid)
            now = self.clock()
            if session and now - session.touched < 12 * 3600 and now - session.created < 7 * 86400:
                if touch:
                    session.touched = now
                return session
            self.sessions.pop(sid, None)
            return None

    def logout(self, sid):
        with self.lock:
            self.sessions.pop(sid, None)

    def close(self):
        self.path.unlink(missing_ok=True)
        with self.lock:
            self.sessions.clear()
            self.token = None
