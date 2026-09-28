from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.deps import ACCESS_COOKIE, REFRESH_COOKIE, client_meta, get_current_user
from app.models import User
from app.services import auth_oauth, auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=120)
    username: str | None = Field(default=None, max_length=80)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class VerifyOtpRequest(BaseModel):
    challenge_id: UUID
    code: str = Field(min_length=4, max_length=12)


class ResendOtpRequest(BaseModel):
    challenge_id: UUID


class ChallengeResponse(BaseModel):
    challenge_id: str
    email_masked: str
    expires_in_sec: int
    purpose: str
    debug_code: str | None = None
    email_sent: bool = True


class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None = None
    username: str | None = None
    status: str
    email_verified_at: str | None = None


class SessionResponse(BaseModel):
    user: UserResponse
    ok: bool = True


def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    settings = get_settings()
    common = {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(
        ACCESS_COOKIE,
        access,
        max_age=settings.auth_access_ttl_min * 60,
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=settings.auth_refresh_ttl_days * 24 * 3600,
        **common,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")


@router.post("/register", response_model=ChallengeResponse)
def register(
    body: RegisterRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> ChallengeResponse:
    ip, ua = client_meta(request)
    try:
        payload = auth_service.register_user(
            session,
            email=str(body.email),
            password=body.password,
            name=body.name,
            username=body.username,
            ip=ip,
            user_agent=ua,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChallengeResponse(**payload)


@router.post("/login", response_model=ChallengeResponse)
def login(
    body: LoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> ChallengeResponse:
    ip, ua = client_meta(request)
    try:
        payload = auth_service.login_with_password(
            session,
            email=str(body.email),
            password=body.password,
            ip=ip,
            user_agent=ua,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChallengeResponse(**payload)


@router.post("/verify-otp", response_model=SessionResponse)
def verify_otp(
    body: VerifyOtpRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> SessionResponse:
    ip, ua = client_meta(request)
    user, access, refresh = auth_service.verify_challenge_and_issue_session(
        session,
        challenge_id=body.challenge_id,
        code=body.code,
        ip=ip,
        user_agent=ua,
    )
    _set_auth_cookies(response, access, refresh)
    return SessionResponse(user=UserResponse(**auth_service.user_public(user)))


@router.post("/otp/resend", response_model=ChallengeResponse)
def resend_otp(
    body: ResendOtpRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> ChallengeResponse:
    ip, ua = client_meta(request)
    try:
        payload = auth_service.resend_otp(
            session,
            challenge_id=body.challenge_id,
            ip=ip,
            user_agent=ua,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChallengeResponse(**payload)


@router.post("/refresh", response_model=SessionResponse)
def refresh(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> SessionResponse:
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Нет refresh-токена")
    ip, ua = client_meta(request)
    user, access, new_refresh = auth_service.rotate_refresh_session(
        session,
        refresh_token=refresh_token,
        ip=ip,
        user_agent=ua,
    )
    _set_auth_cookies(response, access, new_refresh)
    return SessionResponse(user=UserResponse(**auth_service.user_public(user)))


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict:
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    # Best-effort revoke; always clear cookies.
    try:
        from uuid import UUID

        import jwt

        from app.services.auth_tokens import decode_access_token

        access = request.cookies.get(ACCESS_COOKIE)
        sid = None
        if access:
            try:
                sid = UUID(decode_access_token(access)["sid"])
            except (jwt.PyJWTError, KeyError, ValueError):
                sid = None
        auth_service.revoke_session(session, session_id=sid, refresh_token=refresh_token)
    except Exception:
        pass
    _clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(**auth_service.user_public(user))


OAUTH_STATE_COOKIE = "oauth_state"
PENDING_CHALLENGE_COOKIE = "pending_challenge"


def _public_base(request: Request) -> str:
    settings = get_settings()
    if settings.public_app_url:
        return settings.public_app_url.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if not host:
        raise HTTPException(status_code=500, detail="Не удалось определить URL приложения")
    return f"{proto}://{host}"


def _oauth_redirect_uri(request: Request, provider: str) -> str:
    return f"{_public_base(request)}/api/auth/oauth/{provider}/callback"


@router.get("/oauth/providers")
def oauth_providers() -> dict:
    return auth_oauth.providers_status()


@router.get("/oauth/{provider}/start")
def oauth_start(provider: str, request: Request):
    from fastapi.responses import RedirectResponse

    if provider not in auth_oauth.SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=404, detail="Неизвестный провайдер")
    state = auth_oauth.make_oauth_state()
    redirect_uri = _oauth_redirect_uri(request, provider)
    url = auth_oauth.authorize_url(provider, redirect_uri=redirect_uri, state=state)
    return RedirectResponse(url=url, status_code=302)


@router.get("/oauth/{provider}/callback")
def oauth_callback(
    provider: str,
    request: Request,
    session: Session = Depends(get_session),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    import json
    import logging
    from urllib.parse import quote, urlencode

    from fastapi.responses import RedirectResponse

    logger = logging.getLogger(__name__)
    base = _public_base(request)

    def fail(reason: str) -> RedirectResponse:
        logger.warning("OAuth %s failed: %s", provider, reason)
        qs = urlencode({"oauth_error": reason})
        return RedirectResponse(url=f"{base}/?{qs}#login", status_code=302)

    if error:
        return fail(f"Провайдер вернул ошибку: {error}")
    if provider not in auth_oauth.SUPPORTED_PROVIDERS:
        return fail("Неизвестный провайдер")
    if not code or not state:
        return fail("Нет code/state от провайдера")
    if not auth_oauth.verify_oauth_state(state):
        return fail("Неверный state (обновите страницу и попробуйте снова)")

    ip, ua = client_meta(request)
    redirect_uri = _oauth_redirect_uri(request, provider)
    try:
        profile = auth_oauth.exchange_code(provider, code, redirect_uri)
        user = auth_oauth.upsert_oauth_user(session, profile)
        challenge = auth_oauth.start_oauth_login_2fa(
            session, user=user, ip=ip, user_agent=ua
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Ошибка OAuth"
        return fail(detail)
    except Exception as exc:
        logger.exception("OAuth %s unexpected error", provider)
        return fail(f"Внутренняя ошибка: {exc}")

    settings = get_settings()
    response = RedirectResponse(url=f"{base}/?auth=verify-otp", status_code=302)
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    response.set_cookie(
        PENDING_CHALLENGE_COOKIE,
        quote(json.dumps(challenge, ensure_ascii=False)),
        max_age=600,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    return response
