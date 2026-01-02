"""Vinted scraper for European market arbitrage.

Vinted is the largest second-hand marketplace in Europe.
Uses their web API for searching.
"""

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from grail_hunter.config import get_settings
from grail_hunter.scrapers.base import BaseScraper, ScraperConfig


@dataclass
class VintedListing:
    """A listing from Vinted."""

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
    location: str | None
    favorites: int = 0

    @classmethod
    def from_item(cls, item: dict[str, Any], domain: str = "vinted.fr") -> "VintedListing":
        """Parse a Vinted API item."""
        item_id = str(item.get("id", ""))

        # Price
        price = item.get("price", 0)
        if isinstance(price, str):
            price = float(re.sub(r"[^\d.]", "", price) or 0)

        # Image
        photo = item.get("photo", {})
        if isinstance(photo, dict):
            image_url = photo.get("url", "") or photo.get("full_size_url", "")
        else:
            image_url = ""

        # User/seller
        user = item.get("user", {})
        seller = user.get("login") if isinstance(user, dict) else None
        location = user.get("city") if isinstance(user, dict) else None

        return cls(
            id=item_id,
            title=item.get("title", ""),
            brand=item.get("brand_title"),
            price=float(price),
            currency=item.get("currency", "EUR"),
            size=item.get("size_title"),
            condition=item.get("status"),
            image_url=image_url,
            item_url=f"https://www.{domain}/items/{item_id}",
            seller=seller,
            location=location,
            favorites=item.get("favourite_count", 0),
        )


class VintedScraper(BaseScraper):
    """Async Vinted scraper with retry and rate limiting."""

    # Vinted domains for different countries
    DOMAINS = {
        "fr": "vinted.fr",
        "de": "vinted.de",
        "it": "vinted.it",
        "es": "vinted.es",
        "nl": "vinted.nl",
        "be": "vinted.be",
        "at": "vinted.at",
        "pl": "vinted.pl",
        "cz": "vinted.cz",
        "lt": "vinted.lt",
        "uk": "vinted.co.uk",
    }

    def __init__(self, country: str = "fr") -> None:
        """
        Initialize Vinted scraper.

        Args:
            country: Country code (fr, de, it, es, etc.)
        """
        self.country = country
        self.domain = self.DOMAINS.get(country, "vinted.fr")

        settings = get_settings()
        config = ScraperConfig(
            name="vinted",
            base_url=f"https://www.{self.domain}/api/v2/catalog/items",
            max_concurrent=settings.max_concurrent_requests,
            max_retries=3,
            timeout=30.0,
            rate_limit_delay=settings.request_delay_seconds * 2,  # Vinted is stricter
        )
        super().__init__(config)

    def _get_headers(self) -> dict[str, str]:
        """Get headers for Vinted requests."""
        return {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"https://www.{self.domain}/",
            "Origin": f"https://www.{self.domain}",
        }

    async def search(
        self,
        query: str,
        max_results: int = 20,
        min_price: float | None = None,
        max_price: float | None = None,
        brand_ids: list[int] | None = None,
        catalog_ids: list[int] | None = None,
        **kwargs: Any,
    ) -> list[VintedListing]:
        """
        Search Vinted for listings.

        Args:
            query: Search query
            max_results: Maximum results
            min_price: Minimum price filter
            max_price: Maximum price filter
            brand_ids: Vinted brand IDs to filter
            catalog_ids: Vinted catalog/category IDs

        Returns:
            List of VintedListing objects
        """
        # Build search params
        params: dict[str, Any] = {
            "search_text": query,
            "per_page": min(max_results, 96),
            "order": "newest_first",
        }

        if min_price is not None:
            params["price_from"] = min_price
        if max_price is not None:
            params["price_to"] = max_price
        if brand_ids:
            params["brand_ids"] = ",".join(str(b) for b in brand_ids)
        if catalog_ids:
            params["catalog_ids"] = ",".join(str(c) for c in catalog_ids)

        try:
            url = f"{self.config.base_url}?{urlencode(params)}"
            data = await self._fetch_json(url)

            items = data.get("items", [])
            return [VintedListing.from_item(item, self.domain) for item in items]

        except Exception:
            # Error already logged by BaseScraper
            return []

    async def search_brand(
        self,
        brand: str,
        max_results: int = 20,
    ) -> list[VintedListing]:
        """Search for a specific brand on Vinted."""
        return await self.search(query=brand, max_results=max_results)

    async def get_price_range(
        self,
        brand: str,
        item_type: str | None = None,
    ) -> dict[str, float | None]:
        """
        Get price statistics for a brand/item on Vinted.

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

    async def get_brand_id(self, brand_name: str) -> int | None:
        """
        Look up Vinted brand ID from name.

        Useful for filtering by specific brands.
        """
        # This would require hitting Vinted's brand search endpoint
        # For now, return None - would need session cookie for this
        return None


# Common Vinted brand IDs for reference (these may change)
VINTED_BRAND_IDS = {
    "Rick Owens": 2319,
    "Maison Margiela": 169,
    "Raf Simons": 773,
    "Comme des Garçons": 12,
    "Yohji Yamamoto": 2188,
    "Issey Miyake": 36,
    "Undercover": 2165,
    "Acne Studios": 7,
    "Our Legacy": 2329,
    "Stone Island": 55,
    "C.P. Company": 2260,
    "Arc'teryx": 6027,
    # Add more as needed
}
