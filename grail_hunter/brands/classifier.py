"""Brand classification and tier assignment."""

import re
from dataclasses import dataclass

from grail_hunter.brands.categories import (
    ALL_BRANDS,
    BRAND_CATEGORIES,
    BRAND_LOOKUP,
    TIER_1_GRAILS,
    TIER_2_HYPE,
    BrandCategory,
    Tier,
)


@dataclass
class BrandMatch:
    """Result of brand classification."""

    brand: str | None
    category: BrandCategory
    tier: Tier
    confidence: float  # 0.0 to 1.0


class BrandClassifier:
    """Classify brands and assign tiers."""

    def __init__(self) -> None:
        """Initialize classifier with brand patterns."""
        # Build regex patterns for fuzzy matching
        self._patterns: dict[str, re.Pattern[str]] = {}
        for brand in ALL_BRANDS:
            # Create pattern that handles common variations
            escaped = re.escape(brand)
            # Allow for slight variations (e.g., "Comme des Garcons" vs "Comme des Garçons")
            pattern = escaped.replace(r"\ ", r"\s+")
            self._patterns[brand] = re.compile(pattern, re.IGNORECASE)

    def classify(self, brand_name: str | None) -> BrandMatch:
        """
        Classify a brand name and return its category and tier.

        Args:
            brand_name: The brand name to classify (can be messy input)

        Returns:
            BrandMatch with brand info, category, tier, and confidence
        """
        if not brand_name:
            return BrandMatch(
                brand=None,
                category=BrandCategory.UNKNOWN,
                tier=Tier.UNKNOWN,
                confidence=0.0,
            )

        # Try exact match first (case-insensitive)
        normalized = brand_name.strip().lower()
        if normalized in BRAND_LOOKUP:
            matched_brand = BRAND_LOOKUP[normalized]
            return BrandMatch(
                brand=matched_brand,
                category=self._get_category(matched_brand),
                tier=self._get_tier(matched_brand),
                confidence=1.0,
            )

        # Try regex pattern matching
        for brand, pattern in self._patterns.items():
            if pattern.search(brand_name):
                return BrandMatch(
                    brand=brand,
                    category=self._get_category(brand),
                    tier=self._get_tier(brand),
                    confidence=0.9,
                )

        # No match found
        return BrandMatch(
            brand=brand_name,  # Keep original for reference
            category=BrandCategory.UNKNOWN,
            tier=Tier.UNKNOWN,
            confidence=0.0,
        )

    def _get_category(self, brand: str) -> BrandCategory:
        """Get the category for a known brand."""
        for category_name, brands in BRAND_CATEGORIES.items():
            if brand in brands:
                return BrandCategory(category_name)
        return BrandCategory.UNKNOWN

    def _get_tier(self, brand: str) -> Tier:
        """Get the tier for a known brand."""
        if brand in TIER_1_GRAILS:
            return Tier.TIER_1
        elif brand in TIER_2_HYPE:
            return Tier.TIER_2
        else:
            return Tier.TIER_3

    def is_tracked(self, brand_name: str | None) -> bool:
        """Check if a brand is in our tracking list."""
        if not brand_name:
            return False
        match = self.classify(brand_name)
        return match.confidence > 0.0 and match.category != BrandCategory.UNKNOWN

    def is_grail(self, brand_name: str | None) -> bool:
        """Check if a brand is a Tier 1 grail."""
        if not brand_name:
            return False
        match = self.classify(brand_name)
        return match.tier == Tier.TIER_1
