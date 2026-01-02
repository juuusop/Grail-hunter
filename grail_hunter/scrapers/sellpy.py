"""Sellpy scraper using Algolia API - async implementation with httpx.

API configuration from LEGACY_LOGIC.md.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from grail_hunter.brands import BrandClassifier
from grail_hunter.config import Settings, get_settings
from grail_hunter.filters import QualityFilter, FilterResult, ItemStatus


@dataclass
class SellpyItem:
    """Parsed item from Sellpy API."""

    object_id: str
    title: str
    brand: str | None
    price: float
    original_price: float | None
    discount_pct: int | None
    condition: str | None
    description: str | None
    size: str | None
    color: str | None
    category: str | None
    image_url: str
    item_url: str
    sale_started_at: datetime | None

    # Classification results
    brand_tier: str | None = None
    brand_category: str | None = None
    item_score: int = 0
    detected_materials: list[str] | None = None
    filter_status: str = "valid"

    @classmethod
    def from_hit(cls, hit: dict[str, Any]) -> "SellpyItem":
        """
        Parse an Algolia hit into a SellpyItem.

        Uses parsing logic from LEGACY_LOGIC.md.
        """
        object_id = hit.get("objectID", "")

        # Price parsing - amounts are in cents
        price_data = hit.get("price_FI", {})
        price_now = price_data.get("amount", 0) / 100

        new_price_data = hit.get("newPrice", {})
        price_new = new_price_data.get("amount", 0) / 100 if new_price_data else None

        # Calculate discount
        discount_pct = None
        if price_new and price_new > 0 and price_now < price_new:
            discount_pct = round((1 - price_now / price_new) * 100)

        # Image URL construction from LEGACY_LOGIC.md
        image_url = f"https://img.sellpy.net/photo/{object_id}/1.jpg"

        # Item URL construction
        item_url = f"https://www.sellpy.fi/item/{object_id}"

        # Parse sale started timestamp
        sale_started_at = None
        if timestamp := hit.get("saleStartedAt"):
            try:
                sale_started_at = datetime.fromtimestamp(timestamp / 1000)
            except (ValueError, TypeError):
                pass

        # Extract brand from various possible fields
        brand = hit.get("brand") or hit.get("brandName")

        # Get category path
        categories = hit.get("categories", {})
        category = categories.get("lvl1") or categories.get("lvl0")

        return cls(
            object_id=object_id,
            title=hit.get("title", ""),
            brand=brand,
            price=price_now,
            original_price=price_new,
            discount_pct=discount_pct,
            condition=hit.get("condition"),
            description=hit.get("description"),
            size=hit.get("size"),
            color=hit.get("color"),
            category=category,
            image_url=image_url,
            item_url=item_url,
            sale_started_at=sale_started_at,
        )


class SellpyScraper:
    """Async Sellpy scraper using Algolia API."""

    # Index name from LEGACY_LOGIC.md
    INDEX_NAME = "prod_marketItem_fi_saleStartedAt_desc"

    def __init__(
        self,
        settings: Settings | None = None,
        classifier: BrandClassifier | None = None,
        quality_filter: QualityFilter | None = None,
    ) -> None:
        """Initialize scraper with configuration."""
        self.settings = settings or get_settings()
        self.classifier = classifier or BrandClassifier()
        self.quality_filter = quality_filter or QualityFilter()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "SellpyScraper":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            headers=self.settings.algolia_headers,
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    def _build_params(
        self,
        query: str = "",
        category: str = "Miehet",
        page: int = 0,
        brand_filter: str | None = None,
    ) -> str:
        """
        Build Algolia params string.

        Based on LEGACY_LOGIC.md payload structure.
        """
        params_parts = [
            f"query={query}",
            f'facetFilters=[["{f"categories.lvl0:{category}"}"]]',
            f"numericFilters=price_FI.amount>{int(self.settings.min_price * 100)}",
            f"hitsPerPage={self.settings.hits_per_page}",
            f"page={page}",
        ]

        if brand_filter:
            params_parts[1] = (
                f'facetFilters=[["categories.lvl0:{category}"],["brand:{brand_filter}"]]'
            )

        return "&".join(params_parts)

    async def fetch_page(
        self,
        query: str = "",
        category: str = "Miehet",
        page: int = 0,
        brand_filter: str | None = None,
    ) -> list[SellpyItem]:
        """
        Fetch a single page of results from Sellpy.

        Args:
            query: Search query string
            category: Category to filter (default: Miehet/Men)
            page: Page number (0-indexed)
            brand_filter: Optional brand to filter by

        Returns:
            List of parsed SellpyItems
        """
        if not self._client:
            raise RuntimeError("Scraper not initialized. Use async with statement.")

        # Build request payload from LEGACY_LOGIC.md
        payload = {
            "requests": [
                {
                    "indexName": self.INDEX_NAME,
                    "params": self._build_params(query, category, page, brand_filter),
                }
            ]
        }

        response = await self._client.post(
            self.settings.algolia_url,
            json=payload,
        )
        response.raise_for_status()

        data = response.json()
        results = data.get("results", [])

        if not results:
            return []

        hits = results[0].get("hits", [])
        items = [SellpyItem.from_hit(hit) for hit in hits]

        # Classify and filter items
        return self._process_items(items)

    def _process_items(self, items: list[SellpyItem]) -> list[SellpyItem]:
        """Apply brand classification and quality filtering to items."""
        processed: list[SellpyItem] = []

        for item in items:
            # Classify brand
            brand_match = self.classifier.classify(item.brand)
            item.brand_tier = brand_match.tier.value
            item.brand_category = brand_match.category.value

            # Apply quality filter
            filter_result = self.quality_filter.filter(
                title=item.title,
                description=item.description,
                condition=item.condition,
                brand=item.brand,
            )

            item.filter_status = filter_result.status.value
            item.detected_materials = filter_result.detected_materials

            # Calculate score
            tier_score = 100 if brand_match.tier.value == "TIER_1" else (
                50 if brand_match.tier.value == "TIER_2" else 10
            )
            item.item_score = self.quality_filter.calculate_item_score(
                filter_result, tier_score, item.discount_pct
            )

            processed.append(item)

        return processed

    async def fetch_all_pages(
        self,
        query: str = "",
        category: str = "Miehet",
        max_pages: int | None = None,
        brand_filter: str | None = None,
    ) -> list[SellpyItem]:
        """
        Fetch multiple pages of results.

        Args:
            query: Search query
            category: Category filter
            max_pages: Maximum pages to fetch (default from settings)
            brand_filter: Optional brand filter

        Returns:
            Combined list of items from all pages
        """
        max_pages = max_pages or self.settings.max_pages
        all_items: list[SellpyItem] = []

        for page in range(max_pages):
            items = await self.fetch_page(query, category, page, brand_filter)
            all_items.extend(items)

            # Stop if we got fewer items than requested (last page)
            if len(items) < self.settings.hits_per_page:
                break

            # Small delay between requests
            await asyncio.sleep(0.1)

        return all_items

    async def hunt_grails(
        self,
        category: str = "Miehet",
        include_trash: bool = False,
    ) -> list[SellpyItem]:
        """
        Hunt for grail items - filter for tracked brands and valid items.

        Args:
            category: Category to search
            include_trash: Whether to include items marked as trash

        Returns:
            List of valid grail candidates, sorted by score
        """
        items = await self.fetch_all_pages(category=category)

        # Filter for tracked brands only
        grails = [
            item for item in items
            if self.classifier.is_tracked(item.brand)
            and (include_trash or item.filter_status == "valid")
        ]

        # Sort by score (highest first)
        grails.sort(key=lambda x: x.item_score, reverse=True)

        return grails

    async def search_brand(self, brand: str, category: str = "Miehet") -> list[SellpyItem]:
        """
        Search for a specific brand.

        Args:
            brand: Brand name to search
            category: Category filter

        Returns:
            List of items matching the brand
        """
        items = await self.fetch_all_pages(
            query=brand,
            category=category,
            brand_filter=brand,
        )

        # Filter for valid items only
        return [item for item in items if item.filter_status == "valid"]
