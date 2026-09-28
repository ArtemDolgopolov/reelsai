"""One-time OAuth login tickets (bridge when Set-Cookie on 302 is flaky)."""

from __future__ import annotations

import secrets
import time
from threading import Lock

_lock = Lock()
_tickets: dict[str, dict] = {}
_TTL_SEC = 120


def create_login_ticket(*, access: str, refresh: str, user_id: str) -> str:
    token = secrets.token_urlsafe(24)
    with _lock:
        _tickets[token] = {
            "access": access,
            "refresh": refresh,
            "user_id": user_id,
            "exp": time.time() + _TTL_SEC,
        }
        # Opportunistic cleanup
        now = time.time()
        dead = [k for k, v in _tickets.items() if v["exp"] < now]
        for k in dead:
            _tickets.pop(k, None)
    return token


def claim_login_ticket(token: str) -> dict | None:
    with _lock:
        payload = _tickets.pop(token, None)
    if not payload:
        return None
    if payload["exp"] < time.time():
        return None
    return payload
