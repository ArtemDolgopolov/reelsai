import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

from app.config import get_settings


def create_access_token(*, user_id: UUID, session_id: UUID) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.auth_access_ttl_min)).timestamp()),
    }
    return jwt.encode(payload, settings.auth_jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    payload = jwt.decode(token, settings.auth_jwt_secret, algorithms=["HS256"])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    return payload


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def refresh_expiry() -> datetime:
    days = get_settings().auth_refresh_ttl_days
    return datetime.now(timezone.utc) + timedelta(days=days)
