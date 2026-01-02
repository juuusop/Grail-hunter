"""Arbitrage service - compare prices across platforms.

This is the core value proposition: find underpriced items on Sellpy
by comparing to Grailed and eBay market prices.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from grail_hunter.scrapers.sellpy import SellpyItem
from grail_hunter.scrapers.grailed import GrailedScraper, GrailedListing
from grail_hunter.scrapers.ebay import EbayScraper, EbayListing


class DealRating(str, Enum):
    """How good is the deal."""

    INSANE = "INSANE"      # 60%+ below market
    GREAT = "GREAT"        # 40-60% below market
    GOOD = "GOOD"          # 20-40% below market
    FAIR = "FAIR"          # 0-20% below market
    OVERPRICED = "OVERPRICED"  # Above market
    UNKNOWN = "UNKNOWN"    # Not enough data


@dataclass
class PriceComparison:
    """Price data from a single platform."""

    platform: str
    min_price: float | None = None
    max_price: float | None = None
    avg_price: float | None = None
    median_price: float | None = None
    sample_count: int = 0
    sample_listings: list[dict[str, Any]] = field(default_factory=list)
    currency: str = "EUR"


@dataclass
class ArbitrageResult:
    """Complete arbitrage analysis for an item."""

    sellpy_item: SellpyItem
    sellpy_price_eur: float

    # Market data
    grailed_data: PriceComparison | None = None
    ebay_data: PriceComparison | None = None

    # Analysis
    estimated_market_value: float | None = None
    potential_profit: float | None = None
    profit_margin_pct: float | None = None
    deal_rating: DealRating = DealRating.UNKNOWN

    # Confidence
    confidence_score: float = 0.0  # 0-100
    data_sources: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "sellpy_item": {
                "object_id": self.sellpy_item.object_id,
                "title": self.sellpy_item.title,
                "brand": self.sellpy_item.brand,
                "price": self.sellpy_item.price,
                "image_url": self.sellpy_item.image_url,
                "item_url": self.sellpy_item.item_url,
                "size": self.sellpy_item.size,
                "condition": self.sellpy_item.condition,
            },
            "sellpy_price_eur": self.sellpy_price_eur,
            "grailed_data": {
                "min": self.grailed_data.min_price,
                "avg": self.grailed_data.avg_price,
                "max": self.grailed_data.max_price,
                "count": self.grailed_data.sample_count,
            } if self.grailed_data else None,
            "ebay_data": {
                "min": self.ebay_data.min_price,
                "avg": self.ebay_data.avg_price,
                "max": self.ebay_data.max_price,
                "count": self.ebay_data.sample_count,
            } if self.ebay_data else None,
            "estimated_market_value": self.estimated_market_value,
            "potential_profit": self.potential_profit,
            "profit_margin_pct": self.profit_margin_pct,
            "deal_rating": self.deal_rating.value,
            "confidence_score": self.confidence_score,
        }


class ArbitrageService:
    """Service for analyzing price arbitrage opportunities."""

    # USD to EUR conversion (approximate)
    USD_TO_EUR = 0.92

    def __init__(self) -> None:
        self._grailed: GrailedScraper | None = None
        self._ebay: EbayScraper | None = None

    async def __aenter__(self) -> "ArbitrageService":
        self._grailed = GrailedScraper()
        self._ebay = EbayScraper()
        await self._grailed.__aenter__()
        await self._ebay.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._grailed:
            await self._grailed.__aexit__(*args)
        if self._ebay:
            await self._ebay.__aexit__(*args)

    def _build_search_query(self, item: SellpyItem) -> str:
        """Build an effective search query from Sellpy item."""
        parts = []

        if item.brand:
            parts.append(item.brand)

        # Extract key terms from title
        if item.title:
            # Remove brand from title to avoid duplication
            title_clean = item.title
            if item.brand:
                title_clean = title_clean.replace(item.brand, "").strip()

            # Take first few meaningful words
            words = title_clean.split()[:3]
            parts.extend(words)

        return " ".join(parts)

    async def _get_grailed_prices(
        self,
        query: str,
    ) -> PriceComparison:
        """Fetch Grailed market prices."""
        if not self._grailed:
            return PriceComparison(platform="grailed")

        try:
            listings = await self._grailed.search(query=query, max_results=30)

            if not listings:
                return PriceComparison(platform="grailed")

            prices = [l.price * self.USD_TO_EUR for l in listings if l.price > 0]

            if not prices:
                return PriceComparison(platform="grailed")

            prices_sorted = sorted(prices)

            return PriceComparison(
                platform="grailed",
                min_price=prices_sorted[0],
                max_price=prices_sorted[-1],
                avg_price=sum(prices) / len(prices),
                median_price=prices_sorted[len(prices) // 2],
                sample_count=len(prices),
                sample_listings=[
                    {
                        "title": l.title,
                        "price": l.price,
                        "url": l.item_url,
                        "image": l.image_url,
                    }
                    for l in listings[:5]
                ],
                currency="EUR",
            )
        except Exception as e:
            print(f"Grailed fetch error: {e}")
            return PriceComparison(platform="grailed")

    async def _get_ebay_prices(
        self,
        query: str,
    ) -> PriceComparison:
        """Fetch eBay market prices."""
        if not self._ebay:
            return PriceComparison(platform="ebay")

        try:
            # Get both active and sold listings for better price accuracy
            active_task = self._ebay.search(query=query, max_results=20)
            sold_task = self._ebay.get_sold_prices(query=query, max_results=20)

            active_listings, sold_listings = await asyncio.gather(
                active_task, sold_task, return_exceptions=True
            )

            if isinstance(active_listings, Exception):
                active_listings = []
            if isinstance(sold_listings, Exception):
                sold_listings = []

            all_listings = list(active_listings) + list(sold_listings)

            if not all_listings:
                return PriceComparison(platform="ebay")

            # Convert to EUR
            prices = [l.total_price * self.USD_TO_EUR for l in all_listings if l.total_price > 0]

            if not prices:
                return PriceComparison(platform="ebay")

            prices_sorted = sorted(prices)

            return PriceComparison(
                platform="ebay",
                min_price=prices_sorted[0],
                max_price=prices_sorted[-1],
                avg_price=sum(prices) / len(prices),
                median_price=prices_sorted[len(prices) // 2],
                sample_count=len(prices),
                sample_listings=[
                    {
                        "title": l.title,
                        "price": l.total_price,
                        "url": l.item_url,
                        "image": l.image_url,
                    }
                    for l in list(active_listings)[:5]
                ],
                currency="EUR",
            )
        except Exception as e:
            print(f"eBay fetch error: {e}")
            return PriceComparison(platform="ebay")

    def _calculate_market_value(
        self,
        grailed: PriceComparison | None,
        ebay: PriceComparison | None,
    ) -> tuple[float | None, float]:
        """
        Calculate estimated market value from multiple sources.

        Returns (market_value, confidence_score)
        """
        values = []
        weights = []

        # Grailed is usually more accurate for designer items
        if grailed and grailed.median_price and grailed.sample_count >= 3:
            values.append(grailed.median_price)
            weights.append(grailed.sample_count * 2)  # Weight Grailed higher

        if ebay and ebay.median_price and ebay.sample_count >= 3:
            values.append(ebay.median_price)
            weights.append(ebay.sample_count)

        if not values:
            return None, 0.0

        # Weighted average
        total_weight = sum(weights)
        weighted_value = sum(v * w for v, w in zip(values, weights)) / total_weight

        # Confidence based on sample size and source count
        total_samples = (grailed.sample_count if grailed else 0) + (ebay.sample_count if ebay else 0)
        source_count = len(values)

        confidence = min(100.0, (total_samples * 2) + (source_count * 20))

        return weighted_value, confidence

    def _rate_deal(
        self,
        sellpy_price: float,
        market_value: float | None,
    ) -> tuple[DealRating, float | None, float | None]:
        """
        Rate the deal quality.

        Returns (rating, potential_profit, profit_margin_pct)
        """
        if market_value is None or market_value <= 0:
            return DealRating.UNKNOWN, None, None

        profit = market_value - sellpy_price
        margin = (profit / market_value) * 100

        if margin >= 60:
            rating = DealRating.INSANE
        elif margin >= 40:
            rating = DealRating.GREAT
        elif margin >= 20:
            rating = DealRating.GOOD
        elif margin >= 0:
            rating = DealRating.FAIR
        else:
            rating = DealRating.OVERPRICED

        return rating, profit, margin

    async def analyze_item(self, item: SellpyItem) -> ArbitrageResult:
        """
        Perform full arbitrage analysis on a Sellpy item.

        Args:
            item: SellpyItem to analyze

        Returns:
            ArbitrageResult with market comparison data
        """
        query = self._build_search_query(item)

        # Fetch prices from both platforms concurrently
        grailed_task = self._get_grailed_prices(query)
        ebay_task = self._get_ebay_prices(query)

        grailed_data, ebay_data = await asyncio.gather(
            grailed_task, ebay_task
        )

        # Calculate market value
        market_value, confidence = self._calculate_market_value(grailed_data, ebay_data)

        # Rate the deal
        rating, profit, margin = self._rate_deal(item.price, market_value)

        # Count data sources
        data_sources = sum([
            1 if grailed_data and grailed_data.sample_count > 0 else 0,
            1 if ebay_data and ebay_data.sample_count > 0 else 0,
        ])

        return ArbitrageResult(
            sellpy_item=item,
            sellpy_price_eur=item.price,
            grailed_data=grailed_data if grailed_data.sample_count > 0 else None,
            ebay_data=ebay_data if ebay_data.sample_count > 0 else None,
            estimated_market_value=market_value,
            potential_profit=profit,
            profit_margin_pct=margin,
            deal_rating=rating,
            confidence_score=confidence,
            data_sources=data_sources,
        )

    async def analyze_items(
        self,
        items: list[SellpyItem],
        concurrency: int = 3,
    ) -> list[ArbitrageResult]:
        """
        Analyze multiple items with controlled concurrency.

        Args:
            items: List of SellpyItems to analyze
            concurrency: Max concurrent API calls

        Returns:
            List of ArbitrageResults
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def analyze_with_limit(item: SellpyItem) -> ArbitrageResult:
            async with semaphore:
                result = await self.analyze_item(item)
                await asyncio.sleep(0.5)  # Rate limiting
                return result

        tasks = [analyze_with_limit(item) for item in items]
        results = await asyncio.gather(*tasks)

        return list(results)

    async def find_deals(
        self,
        items: list[SellpyItem],
        min_rating: DealRating = DealRating.GOOD,
        min_confidence: float = 30.0,
    ) -> list[ArbitrageResult]:
        """
        Find the best deals from a list of items.

        Args:
            items: Items to analyze
            min_rating: Minimum deal rating to include
            min_confidence: Minimum confidence score

        Returns:
            Sorted list of deals (best first)
        """
        rating_order = {
            DealRating.INSANE: 4,
            DealRating.GREAT: 3,
            DealRating.GOOD: 2,
            DealRating.FAIR: 1,
            DealRating.OVERPRICED: 0,
            DealRating.UNKNOWN: -1,
        }
        min_rating_value = rating_order[min_rating]

        results = await self.analyze_items(items)

        # Filter by rating and confidence
        deals = [
            r for r in results
            if rating_order[r.deal_rating] >= min_rating_value
            and r.confidence_score >= min_confidence
        ]

        # Sort by profit margin
        deals.sort(
            key=lambda x: (rating_order[x.deal_rating], x.profit_margin_pct or 0),
            reverse=True,
        )

        return deals
