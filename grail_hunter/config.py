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

    # Grailed API (for arbitrage)
    grailed_algolia_app_id: str = "MNRWEFSS2Q"
    grailed_algolia_api_key: str = "a3a4de2e05d9e9b463911705fb6323ad"

    # eBay API
    ebay_app_id: str = ""

    # Telegram notifications
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Discord webhook (alternative)
    discord_webhook_url: str = ""

    # Notification settings
    notification_min_rating: str = "GREAT"

    # Scraping settings
    scrape_interval_minutes: int = 5
    hits_per_page: int = 60
    max_pages: int = 5

    # Rate limiting
    max_concurrent_requests: int = 5
    request_delay_seconds: float = 0.5

    # Filtering
    min_price: float = 0.0
    max_price: float = 500.0

    # Scheduler
    scheduler_enabled: bool = True

    @property
    def algolia_headers(self) -> dict[str, str]:
        """Get Sellpy Algolia API headers."""
        return {
            "x-algolia-application-id": self.algolia_app_id,
            "x-algolia-api-key": self.algolia_api_key,
            "Content-Type": "application/json",
        }

    @property
    def grailed_algolia_headers(self) -> dict[str, str]:
        """Get Grailed Algolia API headers."""
        return {
            "x-algolia-application-id": self.grailed_algolia_app_id,
            "x-algolia-api-key": self.grailed_algolia_api_key,
            "Content-Type": "application/json",
        }

    @property
    def notifications_enabled(self) -> bool:
        """Check if any notification method is configured."""
        return bool(self.telegram_bot_token and self.telegram_chat_id) or bool(
            self.discord_webhook_url
        )

    # Legacy compatibility
    @property
    def scrape_interval_seconds(self) -> int:
        """Convert minutes to seconds for backwards compatibility."""
        return self.scrape_interval_minutes * 60


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
