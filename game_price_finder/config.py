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

    rawg_api_key: str | None = None
    giant_bomb_api_key: str | None = None

    itad_api_key: str | None = None

    catalog_merge_max_results: int = 40
    igdb_search_limit: int = 30
    catalog_rawg_limit: int = 15
    catalog_gb_limit: int = 8

    catalog_suggestions_merge_max: int = 24
    catalog_suggestions_igdb_limit: int = 8
    catalog_suggestions_rawg_limit: int = 6
    catalog_suggestions_gb_limit: int = 4

    feedback_db_path: str = "data/feedback.db"
    feedback_admin_token: str | None = None

    default_currency: str = "USD"

    #: When True, HTML error responses may include exception detail (dev/troubleshooting only).
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
