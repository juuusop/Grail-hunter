"""Grailed scraper for price arbitrage comparison.

Grailed uses Algolia for search, similar to Sellpy.
Refactored to use BaseScraper for reliability.
"""

import re
from dataclasses import dataclass
from typing import Any

from grail_hunter.config import get_settings
from grail_hunter.scrapers.base import BaseScraper, ScraperConfig


@dataclass
class GrailedListing:
    """A listing from Grailed."""

    id: str
    title: str
    brand: str | None
    price: float
    currency: str
    size: str | None
    condition: str | None
    image_url: str
    item_url: str
    seller: str | None
    sold: bool = False

    @classmethod
    def from_hit(cls, hit: dict[str, Any]) -> "GrailedListing":
        """Parse a Grailed Algolia hit."""
        listing_id = str(hit.get("id", ""))

        # Price handling
        price = hit.get("price", 0)
        if isinstance(price, str):
            price = float(re.sub(r"[^\d.]", "", price) or 0)

        # Image
        photos = hit.get("photos", [])
        image_url = ""
        if photos and isinstance(photos, list):
            first_photo = photos[0]
            if isinstance(first_photo, dict):
                image_url = first_photo.get("url", "")
            elif isinstance(first_photo, str):
                image_url = first_photo

        return cls(
            id=listing_id,
            title=hit.get("title", ""),
            brand=hit.get("designer", {}).get("name") if isinstance(hit.get("designer"), dict) else hit.get("designer"),
            price=float(price),
            currency=hit.get("currency", "USD"),
            size=hit.get("size"),
            condition=hit.get("condition"),
            image_url=image_url,
            item_url=f"https://www.grailed.com/listings/{listing_id}",
            seller=hit.get("seller", {}).get("username") if isinstance(hit.get("seller"), dict) else None,
            sold=hit.get("sold", False),
        )


class GrailedScraper(BaseScraper):
    """Async Grailed scraper using Algolia API with retry and rate limiting."""

    INDEX_NAME = "Listing_production"

    def __init__(self) -> None:
        """Initialize with configuration from settings."""
        settings = get_settings()
        config = ScraperConfig(
            name="grailed",
            base_url="https://MNRWEFSS2Q-dsn.algolia.net/1/indexes/*/queries",
            max_concurrent=settings.max_concurrent_requests,
            max_retries=3,
            timeout=30.0,
            rate_limit_delay=settings.request_delay_seconds,
        )
        super().__init__(config)
        self._settings = settings

    def _get_headers(self) -> dict[str, str]:
        """Get Grailed Algolia API headers."""
        return {
            "x-algolia-application-id": self._settings.grailed_algolia_app_id,
            "x-algolia-api-key": self._settings.grailed_algolia_api_key,
            "Content-Type": "application/json",
        }

    async def search(
        self,
        query: str,
        max_results: int = 20,
        min_price: float | None = None,
        max_price: float | None = None,
        **kwargs: Any,
    ) -> list[GrailedListing]:
        """
        Search Grailed for listings with retry logic.

        Args:
            query: Search query (brand name, item description)
            max_results: Maximum results to return
            min_price: Minimum price filter
            max_price: Maximum price filter

        Returns:
            List of GrailedListing objects
        """
        # Build filters
        filters = ["sold:false"]  # Only active listings

        if min_price is not None:
            filters.append(f"price >= {min_price}")
        if max_price is not None:
            filters.append(f"price <= {max_price}")

        # Build request
        payload = {
            "requests": [
                {
                    "indexName": self.INDEX_NAME,
                    "params": f"query={query}&hitsPerPage={max_results}&filters={' AND '.join(filters)}",
                }
            ]
        }

        try:
            data = await self._post_json(self.config.base_url, payload)
            results = data.get("results", [])

            if not results:
                return []

            hits = results[0].get("hits", [])
            return [GrailedListing.from_hit(hit) for hit in hits]

        except Exception:
            # Error already logged by BaseScraper
            return []

    async def search_brand(
        self,
        brand: str,
        max_results: int = 20,
    ) -> list[GrailedListing]:
        """Search for a specific brand on Grailed."""
        return await self.search(query=brand, max_results=max_results)

    async def get_price_range(
        self,
        brand: str,
        item_type: str | None = None,
    ) -> dict[str, float | None]:
        """
        Get price statistics for a brand/item on Grailed.

        Returns dict with min, max, avg, median prices.
        """
        query = f"{brand} {item_type}" if item_type else brand
        listings = await self.search(query=query, max_results=50)

        if not listings:
            return {"min": None, "max": None, "avg": None, "median": None, "count": 0}

        prices = sorted([listing.price for listing in listings if listing.price > 0])

        if not prices:
            return {"min": None, "max": None, "avg": None, "median": None, "count": 0}

        return {
            "min": prices[0],
            "max": prices[-1],
            "avg": sum(prices) / len(prices),
            "median": prices[len(prices) // 2],
            "count": len(prices),
        }
