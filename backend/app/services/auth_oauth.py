from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import get_settings
from app.models import AuthChallengePurpose, OAuthAccount, User, UserStatus
from app.services.auth_service import (
    challenge_response,
    create_challenge,
    get_user_by_email,
    normalize_email,
)


SUPPORTED_PROVIDERS = ("google", "yandex")


@dataclass
class OAuthProfile:
    provider: str
    provider_user_id: str
    email: str
    name: str | None = None


def provider_enabled(provider: str) -> bool:
    settings = get_settings()
    if provider == "google":
        return bool(settings.google_client_id and settings.google_client_secret)
    if provider == "yandex":
        return bool(settings.yandex_client_id and settings.yandex_client_secret)
    return False


def providers_status() -> dict[str, bool]:
    return {name: provider_enabled(name) for name in SUPPORTED_PROVIDERS}


def make_oauth_state() -> str:
    """Signed opaque state — no cookie required for CSRF check after redirect."""
    raw = secrets.token_urlsafe(18)
    from app.services.auth_otp import hash_token

    return f"{raw}.{hash_token(raw)}"


def verify_oauth_state(state: str | None) -> bool:
    if not state or "." not in state:
        return False
    raw, _, sig = state.rpartition(".")
    if not raw or not sig:
        return False
    from app.services.auth_otp import hash_token
    import hmac

    return hmac.compare_digest(hash_token(raw), sig)


def authorize_url(provider: str, *, redirect_uri: str, state: str) -> str:
    settings = get_settings()
    if provider == "google":
        if not provider_enabled("google"):
            raise HTTPException(status_code=503, detail="Google OAuth не настроен")
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    if provider == "yandex":
        if not provider_enabled("yandex"):
            raise HTTPException(status_code=503, detail="Яндекс OAuth не настроен")
        # Do not pass `scope` here: new Yandex ID apps use permissions from the
        # console only. Requesting login:email/... that aren't linked → invalid_scope.
        params = {
            "response_type": "code",
            "client_id": settings.yandex_client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "force_confirm": "yes",
        }
        return f"https://oauth.yandex.ru/authorize?{urlencode(params)}"

    raise HTTPException(status_code=404, detail="Неизвестный провайдер")


def _exchange_google(code: str, redirect_uri: str) -> OAuthProfile:
    settings = get_settings()
    token_resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20.0,
    )
    if token_resp.status_code >= 400:
        raise HTTPException(status_code=400, detail="Не удалось получить токен Google")
    access = token_resp.json().get("access_token")
    if not access:
        raise HTTPException(status_code=400, detail="Google не вернул access_token")

    info = httpx.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access}"},
        timeout=20.0,
    )
    if info.status_code >= 400:
        raise HTTPException(status_code=400, detail="Не удалось получить профиль Google")
    data = info.json()
    email = (data.get("email") or "").strip().lower()
    sub = str(data.get("sub") or "")
    if not email or not sub:
        raise HTTPException(status_code=400, detail="Google не вернул email")
    return OAuthProfile(
        provider="google",
        provider_user_id=sub,
        email=email,
        name=(data.get("name") or data.get("given_name") or None),
    )


def _exchange_yandex(code: str, redirect_uri: str) -> OAuthProfile:
    settings = get_settings()
    token_resp = httpx.post(
        "https://oauth.yandex.ru/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.yandex_client_id,
            "client_secret": settings.yandex_client_secret,
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20.0,
    )
    if token_resp.status_code >= 400:
        raise HTTPException(
            status_code=400,
            detail=f"Не удалось получить токен Яндекс ({token_resp.status_code})",
        )
    access = token_resp.json().get("access_token")
    if not access:
        raise HTTPException(status_code=400, detail="Яндекс не вернул access_token")

    info = httpx.get(
        "https://login.yandex.ru/info",
        params={"format": "json"},
        headers={"Authorization": f"OAuth {access}"},
        timeout=20.0,
    )
    if info.status_code >= 400:
        raise HTTPException(
            status_code=400,
            detail=f"Не удалось получить профиль Яндекс ({info.status_code})",
        )
    data = info.json()
    emails = data.get("emails") or []
    email = (
        (data.get("default_email") or "")
        or (emails[0] if emails else "")
        or ""
    )
    email = str(email).strip().lower()
    uid = str(data.get("id") or data.get("psuid") or "")
    if not uid:
        raise HTTPException(status_code=400, detail="Яндекс не вернул id пользователя")
    if not email:
        # Fallback: synthetic mailbox so OAuth can continue; OTP still goes there if real.
        raise HTTPException(
            status_code=400,
            detail="Яндекс не вернул email. В приложении включите право «Адрес электронной почты».",
        )
    name = data.get("real_name") or data.get("display_name") or data.get("first_name")
    return OAuthProfile(
        provider="yandex",
        provider_user_id=uid,
        email=email,
        name=name,
    )


def exchange_code(provider: str, code: str, redirect_uri: str) -> OAuthProfile:
    if provider == "google":
        return _exchange_google(code, redirect_uri)
    if provider == "yandex":
        return _exchange_yandex(code, redirect_uri)
    raise HTTPException(status_code=404, detail="Неизвестный провайдер")


def upsert_oauth_user(session: Session, profile: OAuthProfile) -> User:
    email = normalize_email(profile.email)
    linked = session.exec(
        select(OAuthAccount).where(
            OAuthAccount.provider == profile.provider,
            OAuthAccount.provider_user_id == profile.provider_user_id,
        )
    ).first()
    now = datetime.now(timezone.utc)

    if linked:
        user = session.get(User, linked.user_id)
        if not user or user.status == UserStatus.disabled:
            raise HTTPException(status_code=403, detail="Аккаунт недоступен")
        linked.email = email
        linked.updated_at = now
        session.add(linked)
        if not user.email_verified_at:
            user.email_verified_at = now
        if user.status == UserStatus.pending_verification:
            user.status = UserStatus.active
        if profile.name and not user.name:
            user.name = profile.name
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

    user = get_user_by_email(session, email)
    if user:
        if user.status == UserStatus.disabled:
            raise HTTPException(status_code=403, detail="Аккаунт недоступен")
        if user.status == UserStatus.pending_verification:
            user.status = UserStatus.active
        user.email_verified_at = user.email_verified_at or now
        if profile.name and not user.name:
            user.name = profile.name
        session.add(user)
    else:
        user = User(
            email=email,
            password_hash=None,
            name=profile.name,
            status=UserStatus.active,
            email_verified_at=now,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    account = OAuthAccount(
        user_id=user.id,
        provider=profile.provider,
        provider_user_id=profile.provider_user_id,
        email=email,
    )
    session.add(account)
    session.commit()
    session.refresh(user)
    return user


def start_oauth_login_2fa(
    session: Session,
    *,
    user: User,
    ip: str | None,
    user_agent: str | None,
) -> dict:
    """OAuth is factor 1 — still require mandatory email OTP (factor 2)."""
    challenge, code, email_sent = create_challenge(
        session,
        user=user,
        purpose=AuthChallengePurpose.login_2fa,
        ip=ip,
        user_agent=user_agent,
    )
    return challenge_response(challenge, user.email, code, email_sent=email_sent)
