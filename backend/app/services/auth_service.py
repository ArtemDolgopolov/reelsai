from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import get_settings
from app.models import AuthChallenge, AuthChallengePurpose, AuthSession, User, UserStatus
from app.services.auth_email import send_otp_email
from app.services.auth_otp import generate_otp_code, hash_otp, hash_token, otp_expiry, verify_otp
from app.services.auth_password import hash_password, verify_password
from app.services.auth_tokens import create_access_token, new_refresh_token, refresh_expiry


def normalize_email(email: str) -> str:
    return email.strip().lower()


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    visible = local[:1] if local else "*"
    return f"{visible}***@{domain}"


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.exec(select(User).where(User.email == normalize_email(email))).first()


def create_challenge(
    session: Session,
    *,
    user: User,
    purpose: AuthChallengePurpose,
    ip: str | None,
    user_agent: str | None,
) -> tuple[AuthChallenge, str]:
    code = generate_otp_code()
    challenge = AuthChallenge(
        user_id=user.id,
        purpose=purpose,
        code_hash=hash_otp(code),
        expires_at=otp_expiry(),
        ip=ip,
        user_agent=(user_agent or "")[:400] or None,
    )
    session.add(challenge)
    session.commit()
    session.refresh(challenge)
    send_otp_email(to_email=user.email, code=code, purpose=purpose.value)
    return challenge, code


def challenge_response(challenge: AuthChallenge, email: str, code: str | None = None) -> dict:
    payload = {
        "challenge_id": str(challenge.id),
        "email_masked": mask_email(email),
        "expires_in_sec": get_settings().auth_otp_ttl_min * 60,
        "purpose": challenge.purpose.value,
    }
    if get_settings().auth_dev_expose_otp and code:
        payload["debug_code"] = code
    return payload


def register_user(
    session: Session,
    *,
    email: str,
    password: str,
    name: str | None,
    username: str | None,
    ip: str | None,
    user_agent: str | None,
) -> dict:
    email_norm = normalize_email(email)
    existing = get_user_by_email(session, email_norm)
    if existing and existing.status == UserStatus.active:
        raise HTTPException(status_code=409, detail="Аккаунт с этой почтой уже существует")

    if existing and existing.status == UserStatus.pending_verification:
        user = existing
        user.password_hash = hash_password(password)
        user.name = (name or "").strip() or user.name
        user.username = (username or "").strip() or user.username
        user.updated_at = datetime.now(timezone.utc)
        session.add(user)
        session.commit()
        session.refresh(user)
    else:
        user = User(
            email=email_norm,
            password_hash=hash_password(password),
            name=(name or "").strip() or None,
            username=(username or "").strip() or None,
            status=UserStatus.pending_verification,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    challenge, code = create_challenge(
        session,
        user=user,
        purpose=AuthChallengePurpose.register,
        ip=ip,
        user_agent=user_agent,
    )
    return challenge_response(challenge, user.email, code)


def login_with_password(
    session: Session,
    *,
    email: str,
    password: str,
    ip: str | None,
    user_agent: str | None,
) -> dict:
    user = get_user_by_email(session, email)
    # Generic message to avoid account enumeration on password check failures.
    invalid = HTTPException(status_code=401, detail="Неверный email или пароль")
    if not user or not user.password_hash:
        raise invalid
    if user.status == UserStatus.disabled:
        raise HTTPException(status_code=403, detail="Аккаунт отключён")
    if not verify_password(user.password_hash, password):
        raise invalid
    if user.status == UserStatus.pending_verification:
        challenge, code = create_challenge(
            session,
            user=user,
            purpose=AuthChallengePurpose.register,
            ip=ip,
            user_agent=user_agent,
        )
        return challenge_response(challenge, user.email, code)

    challenge, code = create_challenge(
        session,
        user=user,
        purpose=AuthChallengePurpose.login_2fa,
        ip=ip,
        user_agent=user_agent,
    )
    return challenge_response(challenge, user.email, code)


def resend_otp(
    session: Session,
    *,
    challenge_id: UUID,
    ip: str | None,
    user_agent: str | None,
) -> dict:
    old = session.get(AuthChallenge, challenge_id)
    if not old or old.consumed_at:
        raise HTTPException(status_code=400, detail="Запрос кода недействителен")
    user = session.get(User, old.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Запрос кода недействителен")
    # Invalidate previous challenge
    old.consumed_at = datetime.now(timezone.utc)
    session.add(old)
    session.commit()
    challenge, code = create_challenge(
        session,
        user=user,
        purpose=old.purpose,
        ip=ip,
        user_agent=user_agent,
    )
    return challenge_response(challenge, user.email, code)


def verify_challenge_and_issue_session(
    session: Session,
    *,
    challenge_id: UUID,
    code: str,
    ip: str | None,
    user_agent: str | None,
) -> tuple[User, str, str]:
    challenge = session.get(AuthChallenge, challenge_id)
    if not challenge:
        raise HTTPException(status_code=400, detail="Неверный или просроченный код")
    if challenge.consumed_at:
        raise HTTPException(status_code=400, detail="Код уже использован")
    now = datetime.now(timezone.utc)
    expires = challenge.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(status_code=400, detail="Срок действия кода истёк")
    if challenge.attempts >= challenge.max_attempts:
        raise HTTPException(status_code=429, detail="Слишком много попыток. Запросите новый код")

    if not verify_otp(code, challenge.code_hash):
        challenge.attempts += 1
        session.add(challenge)
        session.commit()
        raise HTTPException(status_code=400, detail="Неверный код")

    user = session.get(User, challenge.user_id)
    if not user or user.status == UserStatus.disabled:
        raise HTTPException(status_code=403, detail="Аккаунт недоступен")

    challenge.consumed_at = now
    session.add(challenge)

    if challenge.purpose == AuthChallengePurpose.register:
        user.status = UserStatus.active
        user.email_verified_at = now

    user.last_login_at = now
    session.add(user)

    refresh_raw = new_refresh_token()
    auth_session = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_token(refresh_raw),
        expires_at=refresh_expiry(),
        ip=ip,
        user_agent=(user_agent or "")[:400] or None,
    )
    session.add(auth_session)
    session.commit()
    session.refresh(auth_session)
    session.refresh(user)

    access = create_access_token(user_id=user.id, session_id=auth_session.id)
    return user, access, refresh_raw


def rotate_refresh_session(
    session: Session,
    *,
    refresh_token: str,
    ip: str | None,
    user_agent: str | None,
) -> tuple[User, str, str]:
    token_hash = hash_token(refresh_token)
    auth_session = session.exec(
        select(AuthSession).where(AuthSession.refresh_token_hash == token_hash)
    ).first()
    if not auth_session or auth_session.revoked_at:
        raise HTTPException(status_code=401, detail="Сессия недействительна")
    now = datetime.now(timezone.utc)
    expires = auth_session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(status_code=401, detail="Сессия истекла")

    user = session.get(User, auth_session.user_id)
    if not user or user.status != UserStatus.active:
        raise HTTPException(status_code=401, detail="Сессия недействительна")

    auth_session.revoked_at = now
    session.add(auth_session)

    refresh_raw = new_refresh_token()
    new_session = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_token(refresh_raw),
        expires_at=refresh_expiry(),
        ip=ip,
        user_agent=(user_agent or "")[:400] or None,
    )
    session.add(new_session)
    session.commit()
    session.refresh(new_session)

    access = create_access_token(user_id=user.id, session_id=new_session.id)
    return user, access, refresh_raw


def revoke_session(session: Session, *, session_id: UUID | None, refresh_token: str | None) -> None:
    now = datetime.now(timezone.utc)
    target: AuthSession | None = None
    if session_id:
        target = session.get(AuthSession, session_id)
    elif refresh_token:
        target = session.exec(
            select(AuthSession).where(AuthSession.refresh_token_hash == hash_token(refresh_token))
        ).first()
    if target and not target.revoked_at:
        target.revoked_at = now
        session.add(target)
        session.commit()


def user_public(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "username": user.username,
        "status": user.status.value if hasattr(user.status, "value") else str(user.status),
        "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
    }
