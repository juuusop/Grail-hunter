# 📜 LEGACY_LOGIC.md - Source of Truth

> **Context**: This document contains the proven business logic, API configurations, and brand data from the previous MVP.
> **Task**: Use this logic to implement the new FastAPI Backend. Do not invent new API parameters. Use exactly these.

---

## 1. 💎 The Master Brand Database (Updated)

Use this exact structure for the Brand classification logic.

```python
BRAND_CATEGORIES = {
    "EURO_LUXURY": [
        "Acne Studios", "A.P.C.", "Balenciaga", "Bottega Veneta", "Burberry",
        "Diesel", "Dolce & Gabbana", "Dries Van Noten", "Dsquared2",
        "Haider Ackermann", "Helmut Lang", "Iceberg", "Jil Sander", "Kenzo",
        "Lanvin", "Loewe", "Maison Margiela", "Marni", "Miu Miu", "Moschino",
        "Our Legacy", "Prada", "Raf Simons", "Vetements"
    ],
    "JAPAN_AVANTGARDE": [
        "Comme des Garçons", "Doublet", "Evisu", "Facetasm", "Issey Miyake",
        "Junya Watanabe", "Kapital", "Kolor", "Needles", "Neighborhood",
        "Sacai", "Undercover", "Visvim", "Wacko Maria", "WTAPS", "Yohji Yamamoto"
    ],
    "STREET_MODERN": [
        "1017 ALYX 9SM", "Amiri", "Entire Studios", "Fear of God",
        "Gosha Rubchinskiy", "Heron Preston", "Off-White", "Palm Angels",
        "Rhude", "Saint Michael", "Stüssy", "Supreme", "Thug Club"
    ],
    "TECH_GORP": [
        "Arc'teryx", "Veilance", "C.P. Company", "Kiko Kostadinov", "Patagonia",
        "Post Archive Faction", "ROA", "Salomon", "Stone Island", "The North Face"
    ],
    "ARTISANAL_DARK": [
        "Carol Christian Poell", "Guidi", "Paul Harnden", "Rick Owens"
    ],
    "WORKWEAR_DENIM": [
        "Carhartt", "Levi's"  # Note: Levi's needs filtering for "Vintage" or "LVC"
    ]
}

# Tier Mapping for Alerts
TIER_1_GRAILS = (
    BRAND_CATEGORIES["ARTISANAL_DARK"] +
    ["Maison Margiela", "Raf Simons", "Visvim", "Kapital", "Saint Michael"]
)

TIER_2_HYPE = (
    BRAND_CATEGORIES["EURO_LUXURY"] +
    BRAND_CATEGORIES["JAPAN_AVANTGARDE"] +
    BRAND_CATEGORIES["STREET_MODERN"] +
    BRAND_CATEGORIES["TECH_GORP"]
)
```

---

## 2. 🦅 Sellpy API Configuration (Tested & Working)

The endpoint uses Algolia. Refactor this from `requests` (sync) to `httpx` (async) but **KEEP the headers and payload exact**.

### Config
| Key | Value |
|-----|-------|
| App ID | `50LBQU2I4A` |
| API Key | `4e696a94df3469d5356870d63c118c87` |
| URL | `https://50LBQU2I4A-dsn.algolia.net/1/indexes/*/queries` |

### Headers
```python
HEADERS = {
    "x-algolia-application-id": "50LBQU2I4A",
    "x-algolia-api-key": "4e696a94df3469d5356870d63c118c87",
    "Content-Type": "application/json"
}
```

### Payload Structure
```json
{
    "requests": [
        {
            "indexName": "prod_marketItem_fi_saleStartedAt_desc",
            "params": "query=&facetFilters=[[\"categories.lvl0:Miehet\"]]&numericFilters=price_FI.amount>0&hitsPerPage=60"
        }
    ]
}
```

---

## 3. 🧹 Filtering Logic (Regex Rules)

Logic for cleaning results. Use Python `re` module.

### Trash Filter (Must implement)
If `title`, `condition`, or `description` matches these, `status = 'trash'`.

```python
TRASH_REGEX = r"(?i)\b(reikä|tahra|stained|hole|defect|broken|rikki|kids|junior|140|150|160|170|cm)\b"
```

### Material Detection
Used to score items (Silk/Leather = High Score).

```python
HIGH_VALUE_MATERIALS = {
    "silkki": r"(?i)\b(silk|silkki|silkkiä)\b",
    "kashmir": r"(?i)\b(cashmere|kashmir|kasimir)\b",
    "nahka": r"(?i)\b(leather|nahka|nahkaa)\b",
    "merino": r"(?i)\b(merino)\b",
    "gore-tex": r"(?i)\b(gore-tex|goretex)\b"
}
```

---

## 4. 🧮 Data Parsing (Helper Functions)

### Image URL Construction
Sellpy doesn't always provide full URL. Use this fallback:

```python
# item_id comes from objectID
image_url = f"https://img.sellpy.net/photo/{item_id}/1.jpg"
```

### Discount Calculation
Check `newPrice` vs `price`:

```python
price_now = hit.get('price_FI', {}).get('amount', 0) / 100
price_new = hit.get('newPrice', {}).get('amount', 0) / 100

if price_new > 0 and price_now < price_new:
    discount_pct = round((1 - price_now / price_new) * 100)
```

### Item URL Construction
```python
item_url = f"https://www.sellpy.fi/item/{object_id}"
```

---

## 5. 📊 Scoring System

Combine multiple signals for item scoring:

```python
def calculate_score(item):
    score = 0

    # Brand tier bonus
    if item.brand in TIER_1_GRAILS:
        score += 100
    elif item.brand in TIER_2_HYPE:
        score += 50

    # Material bonus
    for material, regex in HIGH_VALUE_MATERIALS.items():
        if re.search(regex, item.description or ""):
            score += 20

    # Discount bonus
    if item.discount_pct and item.discount_pct > 30:
        score += item.discount_pct // 10

    # Condition bonus (if "Excellent" or similar)
    if "excellent" in (item.condition or "").lower():
        score += 15

    return score
```

---

## 6. 🔔 Alert Priorities

| Tier | Brands | Alert Type |
|------|--------|------------|
| TIER_1 | ARTISANAL_DARK + Margiela, Raf, Visvim, Kapital, Saint Michael | 🚨 INSTANT |
| TIER_2 | All other premium brands | ⚡ HIGH |
| TIER_3 | WORKWEAR_DENIM with "vintage" | 📢 MEDIUM |

---

*Last updated: 2025*
