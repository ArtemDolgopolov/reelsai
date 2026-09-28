from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Reels Finder API"
    database_url: str = "postgresql+psycopg://reelsai:reelsai@localhost:5432/reelsai"
    editor_ip: str | None = None
    seed_on_startup: bool = True
    # Free Groq Whisper large-v3 (optional). Get a key at https://console.groq.com/keys
    groq_api_key: str | None = None
    groq_whisper_model: str = "whisper-large-v3"
    # Local free fallback via faster-whisper (tiny|base|small). "base" fits t3.micro; use Groq for best quality.
    whisper_model: str = "base"

    # Auth
    auth_jwt_secret: str = "change-me-in-production-reelsai-auth-secret"
    auth_otp_pepper: str = "change-me-otp-pepper"
    auth_access_ttl_min: int = 15
    auth_refresh_ttl_days: int = 30
    auth_otp_ttl_min: int = 10
    auth_cookie_secure: bool = False
    auth_dev_expose_otp: bool = False
    resend_api_key: str | None = None
    email_from: str = "AI Рилс Продюсер <onboarding@resend.dev>"
    public_app_url: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    yandex_client_id: str | None = None
    yandex_client_secret: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
