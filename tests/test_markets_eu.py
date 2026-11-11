"""Offline tests for the Nordic/Benelux parsers (no network)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import markets_eu as EU  # noqa: E402


def _card(iid, ship):
    badge = '<w-icon name="Shipping" size="16px"></w-icon>Kan skickas' if ship else ""
    return f'<a href="https://www.blocket.se/recommerce/forsale/item/{iid}">x</a><div>Stockholm</div>{badge}'


def _page(items, ships):
    ld = {"mainEntity": {"itemListElement": [{"item": {
        "name": n, "offers": {"price": str(p), "priceCurrency": "SEK"}, "brand": {"name": b},
        "image": "https://img/x.jpg", "url": f"https://www.blocket.se/recommerce/forsale/item/{i}",
        "itemCondition": "https://schema.org/UsedCondition"}} for i, n, p, b in items]}}
    return (f'<script type="application/ld+json" id="seoStructuredData">{json.dumps(ld)}</script>'
            + "".join(_card(i, s) for (i, *_), s in zip(items, ships)))


def test_recommerce_shipping_badge_per_card():
    html = _page([("1", "Acne Studios jacka str L", 1200, "Acne Studios"), ("2", "Acne skor", 900, "Acne Studios")],
                 [True, False])
    d = {x["id"]: x for x in EU.parse_recommerce(html)}
    assert d["1"]["ships"] is True and d["2"]["ships"] is False
    assert d["1"]["price"] == 1200 and d["1"]["cur"] == "SEK" and d["1"]["brand"] == "Acne Studios"


def test_recommerce_no_badges_means_unknown():
    html = _page([("1", "x", 10, "")], [False])
    assert EU.parse_recommerce(html)[0]["ships"] is None
    assert EU.parse_recommerce("<html></html>") == []


def test_lrp_filters_pickup_and_bidding():
    j = {"listings": [
        {"itemId": "m1", "title": "Stone Island jas maat XL", "priceInfo": {"priceCents": 15000, "priceType": "FIXED"},
         "vipUrl": "/v/kleding/m1", "verticals": ["clothes_men"],
         "extendedAttributes": [{"key": "brand_mens_clothing", "value": "Stone Island"},
                                {"key": "delivery", "value": "Ophalen of Verzenden"}]},
        {"itemId": "m2", "title": "x", "priceInfo": {"priceCents": 15000, "priceType": "FIXED"},
         "attributes": [{"key": "delivery", "value": "Ophalen"}]},
        {"itemId": "m3", "title": "y", "priceInfo": {"priceCents": 0, "priceType": "BIDDING"}}]}
    out = EU.parse_lrp(j, "www.marktplaats.nl")
    assert [o["id"] for o in out] == ["m1"]
    assert out[0]["brand"] == "Stone Island" and out[0]["fashion"] and out[0]["url"].endswith("/v/kleding/m1")


def test_title_size():
    assert EU.title_size("Acne jacka str L") == "MEN-INT-L"
    assert EU.title_size("Genser XS sort") == "MEN-INT-XS"
    assert EU.title_size("Colbert maat 52") == "MEN-EU-52"
    assert EU.title_size("Stone Island takki") == ""
    assert EU.title_size("Small bag") == ""


def test_landed_price_norway_includes_vat():
    p, note = EU.landed("finn", 100)
    assert p == round((100 + 22) * 1.255 + 8, 2) and "ALV" in note
    assert EU.landed("blocket", 100)[0] == 115
    assert EU.landed("dba", 100, {"dba": 5})[0] == 105


def test_auctionet_uses_estimate_and_skips_unknown_currency():
    j = {"items": [
        {"id": 1, "title": "HERMÈS laukku", "currency": "SEK", "next_bid_amount": 500, "estimate": 20000,
         "upper_estimate": 25000, "ends_at": 9999999999, "house": "Stockholms Auktionsverk", "category_id": 49,
         "images": [{"medium": "https://img/1.jpg"}]},
        {"id": 2, "title": "x", "currency": "CHF", "next_bid_amount": 100, "estimate": 100}]}
    out = EU.parse_auctionet(j)
    assert [o["id"] for o in out] == ["1"]
    assert out[0]["base"] == 20000 and out[0]["img"] == "https://img/1.jpg"
