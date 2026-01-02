"""Application configuration using Pydantic Settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Grail Hunter"
    debug: bool = False

    # Database
    database_url: str = "sqlite+aiosqlite:///./grail_hunter.db"

    # Sellpy/Algolia API (from LEGACY_LOGIC.md)
    algolia_app_id: str = "50LBQU2I4A"
    algolia_api_key: str = "4e696a94df3469d5356870d63c118c87"
    algolia_url: str = "https://50LBQU2I4A-dsn.algolia.net/1/indexes/*/queries"

    # Scraping settings
    scrape_interval_seconds: int = 300  # 5 minutes
    hits_per_page: int = 60
    max_pages: int = 5

    # Filtering
    min_price: float = 0.0
    max_price: float = 500.0

    @property
    def algolia_headers(self) -> dict[str, str]:
        """Get Algolia API headers."""
        return {
            "x-algolia-application-id": self.algolia_app_id,
            "x-algolia-api-key": self.algolia_api_key,
            "Content-Type": "application/json",
        }


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
