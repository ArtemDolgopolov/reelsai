import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from app.config import get_settings


def generate_otp_code(digits: int = 6) -> str:
    upper = 10**digits
    return str(secrets.randbelow(upper)).zfill(digits)


def hash_otp(code: str) -> str:
    pepper = get_settings().auth_otp_pepper.encode("utf-8")
    return hmac.new(pepper, code.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_otp(code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(code.strip()), code_hash)


def otp_expiry(minutes: int | None = None) -> datetime:
    ttl = minutes if minutes is not None else get_settings().auth_otp_ttl_min
    return datetime.now(timezone.utc) + timedelta(minutes=ttl)


def hash_token(token: str) -> str:
    pepper = get_settings().auth_otp_pepper.encode("utf-8")
    return hmac.new(pepper, token.encode("utf-8"), hashlib.sha256).hexdigest()
