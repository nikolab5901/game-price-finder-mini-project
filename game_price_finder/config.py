from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    use_fixtures: bool = False

    twitch_client_id: str | None = None
    twitch_client_secret: str | None = None

    ebay_client_id: str | None = None
    ebay_client_secret: str | None = None
    ebay_environment: str = "production"
    ebay_marketplace_id: str = "EBAY_US"

    default_currency: str = "USD"


@lru_cache
def get_settings() -> Settings:
    return Settings()
