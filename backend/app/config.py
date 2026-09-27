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


@lru_cache
def get_settings() -> Settings:
    return Settings()
