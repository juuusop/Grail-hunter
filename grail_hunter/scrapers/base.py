"""Base scraper with retry logic and rate limiting.

Implements the reliability patterns from the development guide:
- Tenacity retry with exponential backoff
- Semaphore-based rate limiting
- Structured logging
- Error handling
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from grail_hunter.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T")


@dataclass
class ScraperConfig:
    """Configuration for a scraper."""

    name: str
    base_url: str
    max_concurrent: int = 5
    max_retries: int = 3
    timeout: float = 30.0
    rate_limit_delay: float = 0.5  # seconds between requests


class ScraperError(Exception):
    """Base exception for scraper errors."""

    pass


class RateLimitError(ScraperError):
    """Raised when rate limited by the target."""

    pass


class AuthenticationError(ScraperError):
    """Raised when authentication fails."""

    pass


class BaseScraper(ABC):
    """
    Abstract base class for all scrapers.

    Provides:
    - Automatic retry with exponential backoff
    - Rate limiting via semaphore
    - Structured logging
    - Common error handling
    """

    def __init__(self, config: ScraperConfig) -> None:
        """Initialize the scraper with configuration."""
        self.config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrent)
        self._client: httpx.AsyncClient | None = None
        self._request_count = 0
        self._error_count = 0

    async def __aenter__(self) -> "BaseScraper":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            timeout=self.config.timeout,
            headers=self._get_headers(),
        )
        log.info(
            "scraper_started",
            scraper=self.config.name,
            base_url=self.config.base_url,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
        log.info(
            "scraper_stopped",
            scraper=self.config.name,
            requests=self._request_count,
            errors=self._error_count,
        )

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for requests. Override in subclasses."""
        return {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def _fetch(
        self,
        url: str,
        method: str = "GET",
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Fetch a URL with retry logic and rate limiting.

        Args:
            url: URL to fetch
            method: HTTP method
            **kwargs: Additional arguments for httpx

        Returns:
            HTTP response

        Raises:
            ScraperError: On unrecoverable errors
        """
        if not self._client:
            raise ScraperError("Scraper not initialized. Use async with statement.")

        async with self._semaphore:
            self._request_count += 1

            log.debug(
                "request_start",
                scraper=self.config.name,
                method=method,
                url=url,
            )

            try:
                response = await self._client.request(method, url, **kwargs)

                # Check for rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    log.warning(
                        "rate_limited",
                        scraper=self.config.name,
                        retry_after=retry_after,
                    )
                    raise RateLimitError(f"Rate limited, retry after {retry_after}s")

                # Check for auth errors
                if response.status_code in (401, 403):
                    self._error_count += 1
                    log.error(
                        "auth_error",
                        scraper=self.config.name,
                        status=response.status_code,
                    )
                    raise AuthenticationError(f"Authentication failed: {response.status_code}")

                response.raise_for_status()

                log.debug(
                    "request_success",
                    scraper=self.config.name,
                    status=response.status_code,
                    size=len(response.content),
                )

                # Rate limit delay
                await asyncio.sleep(self.config.rate_limit_delay)

                return response

            except httpx.HTTPError as e:
                self._error_count += 1
                log.error(
                    "request_failed",
                    scraper=self.config.name,
                    url=url,
                    error=str(e),
                )
                raise

    async def _fetch_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """Fetch and parse JSON response."""
        response = await self._fetch(url, **kwargs)
        return response.json()

    async def _post_json(
        self,
        url: str,
        data: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """POST JSON data and parse response."""
        response = await self._fetch(url, method="POST", json=data, **kwargs)
        return response.json()

    @abstractmethod
    async def search(self, query: str, **kwargs: Any) -> list[Any]:
        """
        Search for items.

        Must be implemented by subclasses.
        """
        ...

    @abstractmethod
    async def get_price_range(self, query: str) -> dict[str, float | None]:
        """
        Get price statistics for a query.

        Must be implemented by subclasses.
        """
        ...

    def get_stats(self) -> dict[str, int]:
        """Get scraper statistics."""
        return {
            "requests": self._request_count,
            "errors": self._error_count,
            "error_rate": (
                round(self._error_count / self._request_count * 100, 1)
                if self._request_count > 0
                else 0
            ),
        }
