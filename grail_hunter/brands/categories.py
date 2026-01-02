"""Master brand database from LEGACY_LOGIC.md."""

from enum import Enum


class BrandCategory(str, Enum):
    """Brand category enumeration."""

    EURO_LUXURY = "EURO_LUXURY"
    JAPAN_AVANTGARDE = "JAPAN_AVANTGARDE"
    STREET_MODERN = "STREET_MODERN"
    TECH_GORP = "TECH_GORP"
    ARTISANAL_DARK = "ARTISANAL_DARK"
    WORKWEAR_DENIM = "WORKWEAR_DENIM"
    UNKNOWN = "UNKNOWN"


class Tier(str, Enum):
    """Item tier for alert priority."""

    TIER_1 = "TIER_1"  # Grails - instant alert
    TIER_2 = "TIER_2"  # Hype - high priority
    TIER_3 = "TIER_3"  # Standard - medium priority
    UNKNOWN = "UNKNOWN"


# Master brand database - exact copy from LEGACY_LOGIC.md
BRAND_CATEGORIES: dict[str, list[str]] = {
    "EURO_LUXURY": [
        "Acne Studios",
        "A.P.C.",
        "Balenciaga",
        "Bottega Veneta",
        "Burberry",
        "Diesel",
        "Dolce & Gabbana",
        "Dries Van Noten",
        "Dsquared2",
        "Haider Ackermann",
        "Helmut Lang",
        "Iceberg",
        "Jil Sander",
        "Kenzo",
        "Lanvin",
        "Loewe",
        "Maison Margiela",
        "Marni",
        "Miu Miu",
        "Moschino",
        "Our Legacy",
        "Prada",
        "Raf Simons",
        "Vetements",
    ],
    "JAPAN_AVANTGARDE": [
        "Comme des Garçons",
        "Doublet",
        "Evisu",
        "Facetasm",
        "Issey Miyake",
        "Junya Watanabe",
        "Kapital",
        "Kolor",
        "Needles",
        "Neighborhood",
        "Sacai",
        "Undercover",
        "Visvim",
        "Wacko Maria",
        "WTAPS",
        "Yohji Yamamoto",
    ],
    "STREET_MODERN": [
        "1017 ALYX 9SM",
        "Amiri",
        "Entire Studios",
        "Fear of God",
        "Gosha Rubchinskiy",
        "Heron Preston",
        "Off-White",
        "Palm Angels",
        "Rhude",
        "Saint Michael",
        "Stüssy",
        "Supreme",
        "Thug Club",
    ],
    "TECH_GORP": [
        "Arc'teryx",
        "Veilance",
        "C.P. Company",
        "Kiko Kostadinov",
        "Patagonia",
        "Post Archive Faction",
        "ROA",
        "Salomon",
        "Stone Island",
        "The North Face",
    ],
    "ARTISANAL_DARK": [
        "Carol Christian Poell",
        "Guidi",
        "Paul Harnden",
        "Rick Owens",
    ],
    "WORKWEAR_DENIM": [
        "Carhartt",
        "Levi's",  # Note: needs filtering for "Vintage" or "LVC"
    ],
}

# Tier mapping for alerts - from LEGACY_LOGIC.md
TIER_1_GRAILS: list[str] = BRAND_CATEGORIES["ARTISANAL_DARK"] + [
    "Maison Margiela",
    "Raf Simons",
    "Visvim",
    "Kapital",
    "Saint Michael",
]

TIER_2_HYPE: list[str] = (
    BRAND_CATEGORIES["EURO_LUXURY"]
    + BRAND_CATEGORIES["JAPAN_AVANTGARDE"]
    + BRAND_CATEGORIES["STREET_MODERN"]
    + BRAND_CATEGORIES["TECH_GORP"]
)

# All tracked brands flattened
ALL_BRANDS: set[str] = set()
for brands in BRAND_CATEGORIES.values():
    ALL_BRANDS.update(brands)

# Create lowercase lookup for case-insensitive matching
BRAND_LOOKUP: dict[str, str] = {brand.lower(): brand for brand in ALL_BRANDS}
