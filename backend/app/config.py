from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Reels Finder API"
    database_url: str = "postgresql+psycopg://reelsai:reelsai@localhost:5432/reelsai"
    editor_ip: str | None = None
    apify_token: str | None = None
    apify_actor_id: str = "apify/instagram-reel-scraper"
    seed_on_startup: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
