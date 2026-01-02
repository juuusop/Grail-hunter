"""Grailed scraper for price arbitrage comparison.

Grailed uses Algolia for search, similar to Sellpy.
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Any

import httpx


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


class GrailedScraper:
    """Async Grailed scraper using their search API."""

    # Grailed's Algolia credentials (public, from their website)
    ALGOLIA_APP_ID = "MNRWEFSS2Q"
    ALGOLIA_API_KEY = "a3a4de2e05d9e9b463911705fb6323ad"
    ALGOLIA_URL = "https://MNRWEFSS2Q-dsn.algolia.net/1/indexes/*/queries"
    INDEX_NAME = "Listing_production"

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "GrailedScraper":
        self._client = httpx.AsyncClient(
            headers={
                "x-algolia-application-id": self.ALGOLIA_APP_ID,
                "x-algolia-api-key": self.ALGOLIA_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    async def search(
        self,
        query: str,
        max_results: int = 20,
        min_price: float | None = None,
        max_price: float | None = None,
        category: str = "tops",  # tops, bottoms, outerwear, footwear, etc.
    ) -> list[GrailedListing]:
        """
        Search Grailed for listings.

        Args:
            query: Search query (brand name, item description)
            max_results: Maximum results to return
            min_price: Minimum price filter
            max_price: Maximum price filter
            category: Category filter

        Returns:
            List of GrailedListing objects
        """
        if not self._client:
            raise RuntimeError("Scraper not initialized. Use async with statement.")

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
            response = await self._client.post(self.ALGOLIA_URL, json=payload)
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            if not results:
                return []

            hits = results[0].get("hits", [])
            return [GrailedListing.from_hit(hit) for hit in hits]

        except httpx.HTTPError as e:
            print(f"Grailed search error: {e}")
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

        prices = sorted([l.price for l in listings if l.price > 0])

        if not prices:
            return {"min": None, "max": None, "avg": None, "median": None, "count": 0}

        return {
            "min": prices[0],
            "max": prices[-1],
            "avg": sum(prices) / len(prices),
            "median": prices[len(prices) // 2],
            "count": len(prices),
        }
