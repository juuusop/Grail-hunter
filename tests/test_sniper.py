"""Offline tests: fake Algolia responses, no network.  Run: python -m pytest tests -q"""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sniper  # noqa: E402


def hit(oid, brand, title, eur, cond="Hyvä", size="M", lvl1="Takit"):
    return {"objectID": oid, "brand": brand, "title": title, "price_FI": {"amount": int(eur * 100), "currency": "EUR"},
            "condition": cond, "size": size, "categories": {"lvl0": "Miehet", "lvl1": lvl1},
            "images": [f"https://img.example/{oid}.jpg"]}


CATALOG = [
    hit("a1", "Rick Owens", "Rick Owens nahkatakki", 120, lvl1="Takit"),
    hit("a2", "Rick Owens DRKSHDW", "DRKSHDW t-paita", 60, lvl1="T-paidat"),
    hit("a3", "Guidi", "Guidi 788z saappaat", 180, lvl1="Kengät"),
    hit("a4", "Patagonia", "Patagonia fleece takki", 70),
    hit("a5", "Comme des Garçons Homme Plus", "CDG Homme Plus bleiseri AW04", 290),
    hit("a6", "Okänt märke", "Musta nahkatakki, Rick Owens tyylinen", 40),
    hit("a7", "Tuntematon", "Maison Margiela tabi saappaat", 60, lvl1="Kengät"),
    hit("a8", "Maison Margiela", "Margiela x H&M takki", 40),
    hit("a9", "Carol Christian Poell", "CCP housut", 500, lvl1="Housut"),
]


class FakeSellpy:
    def __init__(self, market, state):
        self.market, self.state = market, state
        self.price_attr, self.index = "price_FI", "prod_marketItem_fi_saleStartedAt_desc"
        state["creds"] = {"app_id": "X", "key": "k", "index": self.index, "ts": 0}

    price = sniper.Sellpy.price

    def queries(self, reqs):
        out = []
        for r in reqs:
            q = sniper.norm(r.get("query", ""))
            ff = [v.split(":", 1)[1] for grp in r.get("facetFilters", []) for v in grp if v.startswith("brand:")]
            hs = [h for h in CATALOG if (not ff or h["brand"] in ff)
                  and (not q or q in sniper.norm(json.dumps(h, ensure_ascii=False)))]
            facets = {}
            for h in hs:
                facets[h["brand"]] = facets.get(h["brand"], 0) + 1
            out.append({"hits": hs[: r.get("hitsPerPage", 20)] if r.get("hitsPerPage", 20) else [],
                        "nbHits": len(hs), "nbPages": 1, "facets": {"brand": facets}})
        return out


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    for f in ("brands.yaml", "config.yaml"):
        shutil.copy(root / f, tmp_path / f)
    monkeypatch.setattr(sniper, "ROOT", tmp_path)
    monkeypatch.setattr(sniper, "DATA", tmp_path / "data")
    monkeypatch.setattr(sniper, "STATE_FILE", tmp_path / "data/state.json")
    monkeypatch.setattr(sniper, "RESOLVED_FILE", tmp_path / "data/brands_resolved.json")
    monkeypatch.setattr(sniper, "FINDS_FILE", tmp_path / "data/finds.json")
    monkeypatch.setattr(sniper, "FINDS_MD", tmp_path / "FINDS.md")
    monkeypatch.setattr(sniper, "REPORT_MD", tmp_path / "data/BRAND_REPORT.md")
    monkeypatch.setattr(sniper, "Sellpy", FakeSellpy)
    monkeypatch.setattr(sniper.time, "sleep", lambda s: None)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    (tmp_path / "data").mkdir()
    return tmp_path


def test_matcher_longest_alias():
    m = sniper.BrandMatcher(sniper.load_brands())
    assert m.match("Comme des Garçons Homme Plus").name == "Comme des Garçons Homme Plus"
    assert m.match("COMME DES GARCONS").name == "Comme des Garçons"
    assert m.match("Rick Owens DRKSHDW").name == "Rick Owens"
    assert m.match("Arc'teryx Veilance").name == "Arc'teryx Veilance"
    assert m.match("Arcteryx").name == "Arc'teryx"
    assert m.match("Number (N)ine").name == "Number (N)ine"
    assert m.match("Julius") is not None and m.match("Juliusz Store") is None
    assert m.match("Okänt märke") is None


def test_run_end_to_end(env):
    cfg = sniper.load_yaml("config.yaml")
    sniper.run(cfg)
    finds = {f["id"]: f for f in json.loads((env / "data/finds.json").read_text())}
    # Rick leather jacket at 120 €: value 320 * 2.0 * 0.9 * boosts → clear deal
    assert "a1" in finds and finds["a1"]["score"] >= 2
    assert "a3" in finds                       # Guidi 788z boots
    assert "a5" in finds and "HARVINAINEN" in finds["a5"]["label"] or finds["a5"]["score"] >= 2
    assert "a7" in finds and finds["a7"]["source"] == "haku"   # misattributed tabi
    assert "a6" not in finds                   # "-tyylinen" excluded
    assert "a8" not in finds                   # H&M collab excluded
    assert "a4" not in finds                   # Patagonia fleece at 70 € is not a deal
    assert "a9" in finds                       # CCP: rare brand, near value
    report = (env / "data/BRAND_REPORT.md").read_text()
    assert "Rick Owens" in report

    # second run: nothing new → no new finds; then a price drop → alert again
    n = len(json.loads((env / "data/finds.json").read_text()))
    sniper.run(cfg)
    assert len(json.loads((env / "data/finds.json").read_text())) == n
    CATALOG[0]["price_FI"]["amount"] = 9000
    st = json.loads((env / "data/state.json").read_text()); st["last_sweep"] = 0
    (env / "data/state.json").write_text(json.dumps(st))
    sniper.run(cfg)
    finds2 = json.loads((env / "data/finds.json").read_text())
    assert finds2[0]["id"] == "a1" and finds2[0]["old_price"] == 120
    assert "FINDS" not in "" and (env / "FINDS.md").read_text().count("a1") >= 1
