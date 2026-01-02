"""eBay scraper for price arbitrage comparison.

Uses eBay's browse API via web scraping approach.
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

import httpx


@dataclass
class EbayListing:
    """A listing from eBay."""

    id: str
    title: str
    price: float
    currency: str
    shipping: float | None
    total_price: float
    condition: str | None
    image_url: str
    item_url: str
    seller: str | None
    location: str | None
    is_auction: bool = False
    bids: int | None = None

    @classmethod
    def from_search_result(cls, item: dict[str, Any]) -> "EbayListing":
        """Parse an eBay search result item."""
        item_id = str(item.get("itemId", ""))

        # Price parsing
        price_info = item.get("price", {})
        price = float(price_info.get("value", 0))
        currency = price_info.get("currency", "USD")

        # Shipping
        shipping_info = item.get("shippingOptions", [{}])[0] if item.get("shippingOptions") else {}
        shipping_cost = shipping_info.get("shippingCost", {})
        shipping = float(shipping_cost.get("value", 0)) if shipping_cost else None

        total = price + (shipping or 0)

        # Image
        image = item.get("image", {})
        image_url = image.get("imageUrl", "") if isinstance(image, dict) else ""

        # Seller
        seller_info = item.get("seller", {})
        seller = seller_info.get("username") if isinstance(seller_info, dict) else None

        return cls(
            id=item_id,
            title=item.get("title", ""),
            price=price,
            currency=currency,
            shipping=shipping,
            total_price=total,
            condition=item.get("condition"),
            image_url=image_url,
            item_url=item.get("itemWebUrl", f"https://www.ebay.com/itm/{item_id}"),
            seller=seller,
            location=item.get("itemLocation", {}).get("country"),
            is_auction=item.get("buyingOptions", [None])[0] == "AUCTION" if item.get("buyingOptions") else False,
            bids=item.get("bidCount"),
        )


class EbayScraper:
    """Async eBay scraper using their API."""

    # eBay API endpoint (Browse API)
    BASE_URL = "https://api.ebay.com/buy/browse/v1"

    # For web scraping fallback
    SEARCH_URL = "https://www.ebay.com/sch/i.html"

    def __init__(self, marketplace: str = "EBAY_US") -> None:
        """
        Initialize eBay scraper.

        Args:
            marketplace: EBAY_US, EBAY_GB, EBAY_DE, EBAY_FR, etc.
        """
        self.marketplace = marketplace
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "EbayScraper":
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json",
            },
            timeout=30.0,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    def _parse_web_results(self, html: str) -> list[dict[str, Any]]:
        """Parse eBay search results from HTML (fallback method)."""
        results = []

        # Simple regex parsing for eBay listings
        # Looking for s-item containers
        item_pattern = re.compile(
            r'class="s-item__link"[^>]*href="([^"]+)".*?'
            r'class="s-item__title"[^>]*>([^<]+)<.*?'
            r'class="s-item__price"[^>]*>([^<]+)<',
            re.DOTALL | re.IGNORECASE
        )

        for match in item_pattern.finditer(html):
            url, title, price_str = match.groups()

            # Parse price
            price_match = re.search(r"[\d,]+\.?\d*", price_str.replace(",", ""))
            price = float(price_match.group()) if price_match else 0

            # Extract item ID from URL
            item_id_match = re.search(r"/itm/(\d+)", url)
            item_id = item_id_match.group(1) if item_id_match else ""

            if item_id and price > 0:
                results.append({
                    "itemId": item_id,
                    "title": title.strip(),
                    "price": {"value": price, "currency": "USD"},
                    "itemWebUrl": url,
                })

        return results

    async def search(
        self,
        query: str,
        max_results: int = 20,
        min_price: float | None = None,
        max_price: float | None = None,
        condition: str | None = None,  # NEW, USED, etc.
        buy_it_now_only: bool = True,
    ) -> list[EbayListing]:
        """
        Search eBay for listings.

        Args:
            query: Search query
            max_results: Maximum results
            min_price: Minimum price filter
            max_price: Maximum price filter
            condition: Item condition filter
            buy_it_now_only: Only show Buy It Now listings

        Returns:
            List of EbayListing objects
        """
        if not self._client:
            raise RuntimeError("Scraper not initialized. Use async with statement.")

        # Build search URL for web scraping
        params = {
            "_nkw": query,
            "_ipg": min(max_results, 100),
            "_sop": 12,  # Sort by Best Match
        }

        if buy_it_now_only:
            params["LH_BIN"] = 1

        if min_price is not None:
            params["_udlo"] = min_price
        if max_price is not None:
            params["_udhi"] = max_price

        if condition:
            condition_map = {"NEW": 1000, "USED": 3000, "OPEN_BOX": 1500}
            if condition.upper() in condition_map:
                params["LH_ItemCondition"] = condition_map[condition.upper()]

        try:
            response = await self._client.get(self.SEARCH_URL, params=params)
            response.raise_for_status()

            # Parse HTML results
            items = self._parse_web_results(response.text)

            return [EbayListing.from_search_result(item) for item in items[:max_results]]

        except httpx.HTTPError as e:
            print(f"eBay search error: {e}")
            return []

    async def search_brand(
        self,
        brand: str,
        item_type: str | None = None,
        max_results: int = 20,
    ) -> list[EbayListing]:
        """Search for a specific brand on eBay."""
        query = f"{brand} {item_type}" if item_type else brand
        return await self.search(query=query, max_results=max_results)

    async def get_price_range(
        self,
        brand: str,
        item_type: str | None = None,
    ) -> dict[str, float | None]:
        """
        Get price statistics for a brand/item on eBay.

        Returns dict with min, max, avg, median prices.
        """
        query = f"{brand} {item_type}" if item_type else brand
        listings = await self.search(query=query, max_results=50)

        if not listings:
            return {"min": None, "max": None, "avg": None, "median": None, "count": 0}

        prices = sorted([l.total_price for l in listings if l.total_price > 0])

        if not prices:
            return {"min": None, "max": None, "avg": None, "median": None, "count": 0}

        return {
            "min": prices[0],
            "max": prices[-1],
            "avg": sum(prices) / len(prices),
            "median": prices[len(prices) // 2],
            "count": len(prices),
        }

    async def get_sold_prices(
        self,
        query: str,
        max_results: int = 30,
    ) -> list[EbayListing]:
        """
        Get recently sold items for price comparison.

        This is crucial for accurate market value assessment.
        """
        if not self._client:
            raise RuntimeError("Scraper not initialized.")

        # Sold listings search
        params = {
            "_nkw": query,
            "_ipg": min(max_results, 100),
            "LH_Complete": 1,  # Completed listings
            "LH_Sold": 1,  # Sold only
            "_sop": 13,  # Sort by end date (recent first)
        }

        try:
            response = await self._client.get(self.SEARCH_URL, params=params)
            response.raise_for_status()

            items = self._parse_web_results(response.text)
            return [EbayListing.from_search_result(item) for item in items[:max_results]]

        except httpx.HTTPError as e:
            print(f"eBay sold search error: {e}")
            return []
