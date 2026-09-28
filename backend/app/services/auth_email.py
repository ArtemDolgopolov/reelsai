import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def send_otp_email(*, to_email: str, code: str, purpose: str) -> bool:
    """Send OTP email. Returns True if delivered (or skipped without key), False on provider error."""
    settings = get_settings()
    if purpose == "register":
        subject = "Код подтверждения регистрации — AI Рилс Продюсер"
        body = (
            f"Ваш код подтверждения: {code}\n\n"
            f"Код действует {settings.auth_otp_ttl_min} минут.\n"
            "Если вы не регистрировались — просто игнорируйте письмо."
        )
    else:
        subject = "Код входа — AI Рилс Продюсер"
        body = (
            f"Ваш код для входа: {code}\n\n"
            f"Код действует {settings.auth_otp_ttl_min} минут.\n"
            "Никому не сообщайте этот код."
        )

    logger.info("OTP for %s (%s): %s", to_email, purpose, code)

    if not settings.resend_api_key:
        logger.warning("RESEND_API_KEY is not set — OTP only logged, email not sent")
        return False

    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.email_from,
                "to": [to_email],
                "subject": subject,
                "text": body,
            },
            timeout=20.0,
        )
    except Exception:
        logger.exception("Resend request failed")
        return False

    if response.status_code >= 400:
        # Typical: onboarding@resend.dev can only send to the Resend account email.
        logger.error("Resend failed: %s %s", response.status_code, response.text)
        return False
    return True
