import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import markets as M  # noqa: E402
import sniper as S  # noqa: E402


def test_text_brand_finder():
    f = M.TextBrandFinder(S.load_brands())
    assert f.find("Rick Owens geobasket 44").name == "Rick Owens"
    assert f.find("Maison Margiela tabi saappaat").name == "Maison Margiela"
    assert f.find("Ikea sohva") is None


def test_tradera_regex():
    raw = ('{"itemId":7607,"price":3000,"shortDescription":"Maison Margiela boots stl 43",'
           '"imageUrlTemplate":"https://img.tradera.net/{format}/1.jpg","imageHeight":1,'
           '"itemUrl":"https://www.tradera.com/item/1/7607/x","itemType":"AuctionBin","buyNowPrice":900,"isActive":true}')
    m = list(M.TRADERA_ITEM.finditer(raw))
    assert len(m) == 1 and m[0].group(1) == "7607"


def test_tori_jsonld(monkeypatch):
    ld = {"mainEntity": {"itemListElement": [{"item": {"name": "Rick Owens nahkatakki", "url": "https://www.tori.fi/recommerce/forsale/item/42",
                                                          "offers": {"price": "20"}, "image": "https://img.tori.net/x"}}]}}
    html = f'<script type="application/ld+json" id="seoStructuredData">{json.dumps(ld)}</script>'

    class R:
        text = html

        def raise_for_status(self):
            pass
    monkeypatch.setattr(M.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(M.time, "sleep", lambda *_: None)
    got = M.tori({}, ["rick owens"], 1)
    assert got[0].id == "tori-42" and got[0].price == 20.0
