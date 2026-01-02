"""Quality filtering and material detection from LEGACY_LOGIC.md."""

import re
from dataclasses import dataclass, field
from enum import Enum


class ItemStatus(str, Enum):
    """Item status after filtering."""

    VALID = "valid"
    TRASH = "trash"
    NEEDS_REVIEW = "needs_review"


# Trash filter regex - from LEGACY_LOGIC.md
# Items matching this are marked as trash
TRASH_REGEX = re.compile(
    r"(?i)\b(reikä|tahra|stained|hole|defect|broken|rikki|kids|junior|140|150|160|170|cm)\b"
)

# High value materials - from LEGACY_LOGIC.md
HIGH_VALUE_MATERIALS: dict[str, re.Pattern[str]] = {
    "silkki": re.compile(r"(?i)\b(silk|silkki|silkkiä)\b"),
    "kashmir": re.compile(r"(?i)\b(cashmere|kashmir|kasimir)\b"),
    "nahka": re.compile(r"(?i)\b(leather|nahka|nahkaa)\b"),
    "merino": re.compile(r"(?i)\b(merino)\b"),
    "gore-tex": re.compile(r"(?i)\b(gore-tex|goretex)\b"),
}

# Condition keywords for scoring
EXCELLENT_CONDITION = re.compile(r"(?i)\b(excellent|erinomainen|uusi|new|unused)\b")
GOOD_CONDITION = re.compile(r"(?i)\b(good|hyvä|very good|erittäin hyvä)\b")

# Special Levi's filter - only accept vintage/LVC
LEVIS_VINTAGE_REGEX = re.compile(r"(?i)\b(vintage|lvc|made in usa|big e|501)\b")


@dataclass
class FilterResult:
    """Result of quality filtering."""

    status: ItemStatus
    detected_materials: list[str] = field(default_factory=list)
    condition_score: int = 0  # 0-100
    trash_reason: str | None = None
    is_vintage_levis: bool = False


class QualityFilter:
    """Filter items based on quality and detect materials."""

    def filter(
        self,
        title: str | None,
        description: str | None,
        condition: str | None,
        brand: str | None = None,
    ) -> FilterResult:
        """
        Filter an item and detect its quality attributes.

        Args:
            title: Item title
            description: Item description
            condition: Item condition text
            brand: Brand name (for special filtering like Levi's)

        Returns:
            FilterResult with status, materials, and scores
        """
        # Combine all text fields for analysis
        all_text = " ".join(filter(None, [title, description, condition]))

        # Check for trash indicators
        if trash_match := TRASH_REGEX.search(all_text):
            return FilterResult(
                status=ItemStatus.TRASH,
                trash_reason=f"Matched trash pattern: {trash_match.group()}",
            )

        # Special Levi's handling
        is_vintage_levis = False
        if brand and "levi" in brand.lower():
            if not LEVIS_VINTAGE_REGEX.search(all_text):
                return FilterResult(
                    status=ItemStatus.TRASH,
                    trash_reason="Levi's without vintage/LVC indicators",
                )
            is_vintage_levis = True

        # Detect high-value materials
        detected_materials: list[str] = []
        for material_name, pattern in HIGH_VALUE_MATERIALS.items():
            if pattern.search(all_text):
                detected_materials.append(material_name)

        # Calculate condition score
        condition_score = self._calculate_condition_score(condition, all_text)

        return FilterResult(
            status=ItemStatus.VALID,
            detected_materials=detected_materials,
            condition_score=condition_score,
            is_vintage_levis=is_vintage_levis,
        )

    def _calculate_condition_score(
        self, condition: str | None, all_text: str
    ) -> int:
        """Calculate a condition score from 0-100."""
        score = 50  # Default to average

        text_to_check = condition or all_text

        if EXCELLENT_CONDITION.search(text_to_check):
            score = 90
        elif GOOD_CONDITION.search(text_to_check):
            score = 70

        return score

    def calculate_item_score(
        self,
        filter_result: FilterResult,
        tier_score: int,
        discount_pct: int | None = None,
    ) -> int:
        """
        Calculate overall item score combining all factors.

        Based on LEGACY_LOGIC.md scoring system.

        Args:
            filter_result: Result from filter() method
            tier_score: Score from brand tier (100 for T1, 50 for T2, etc.)
            discount_pct: Discount percentage if applicable

        Returns:
            Combined score
        """
        score = tier_score

        # Material bonus: +20 per high-value material
        score += len(filter_result.detected_materials) * 20

        # Discount bonus
        if discount_pct and discount_pct > 30:
            score += discount_pct // 10

        # Condition bonus
        if filter_result.condition_score >= 90:
            score += 15
        elif filter_result.condition_score >= 70:
            score += 10

        # Vintage Levi's bonus
        if filter_result.is_vintage_levis:
            score += 25

        return score
