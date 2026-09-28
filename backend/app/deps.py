from datetime import datetime, timezone
from uuid import UUID

import jwt
from fastapi import Cookie, Depends, HTTPException, Request
from sqlmodel import Session

from app.db import get_session
from app.models import AuthSession, User, UserStatus
from app.services.auth_tokens import decode_access_token

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


def client_meta(request: Request) -> tuple[str | None, str | None]:
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else None
    )
    if ip:
        ip = ip.replace("::ffff:", "")[:64]
    ua = (request.headers.get("user-agent") or "")[:400] or None
    return ip, ua


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
    access_token: str | None = Cookie(default=None, alias=ACCESS_COOKIE),
) -> User:
    token = access_token
    auth_header = request.headers.get("authorization") or ""
    if not token and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Требуется вход")

    try:
        payload = decode_access_token(token)
        user_id = UUID(payload["sub"])
        session_id = UUID(payload["sid"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Сессия истекла, войдите снова") from None

    auth_session = session.get(AuthSession, session_id)
    if not auth_session or auth_session.revoked_at or auth_session.user_id != user_id:
        raise HTTPException(status_code=401, detail="Сессия недействительна")
    expires = auth_session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Сессия истекла")

    user = session.get(User, user_id)
    if not user or user.status != UserStatus.active:
        raise HTTPException(status_code=401, detail="Требуется вход")
    return user
