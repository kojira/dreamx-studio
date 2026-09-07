"""In-memory eight-hour sessions; restart deliberately invalidates all sessions."""
import hmac
import secrets
import threading
import time
from dataclasses import dataclass

class Unauthorized(Exception): pass
class RateLimited(Exception): pass

@dataclass(frozen=True)
class Session:
    token: str
    csrf: str
    expires: float

class Sessions:
    def __init__(self, secret: str, clock=time.monotonic):
        if len(secret.encode('utf-8')) < 32:
            raise ValueError('Access secret must have at least 32 bytes')
        self._secret = secret.encode('utf-8')
        self._clock = clock
        self._sessions = {}
        self._failures = []
        self._lock = threading.Lock()

    def login(self, secret: str) -> Session:
        with self._lock:
            now = self._clock()
            self._failures = [t for t in self._failures if now-t < 60]
            if len(self._failures) >= 5:
                raise RateLimited()
            if not hmac.compare_digest(self._secret, secret.encode('utf-8')):
                self._failures.append(now)
                raise Unauthorized()
            self._sessions = {k:s for k,s in self._sessions.items() if s.expires > now}
            session = Session(secrets.token_urlsafe(32), secrets.token_urlsafe(32), now+8*3600)
            self._sessions[session.token] = session
            return session

    def require(self, token: str, csrf: str | None = None, *, modifying=False):
        with self._lock:
            session = self._sessions.get(token)
            if session is None or session.expires <= self._clock():
                self._sessions.pop(token, None)
                raise Unauthorized()
            if modifying and (csrf is None or not hmac.compare_digest(session.csrf.encode(), csrf.encode())):
                raise Unauthorized()
            return session

    def logout(self, token: str):
        with self._lock:
            self._sessions.pop(token, None)


def check_origin(host: str, origin: str | None, *, modifying: bool):
    if host != '127.0.0.1:8780':
        raise Unauthorized()
    if origin is not None and origin != 'http://127.0.0.1:8780':
        raise Unauthorized()
    if modifying and origin != 'http://127.0.0.1:8780':
        raise Unauthorized()
