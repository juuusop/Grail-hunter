"""Offline tests for the resale / profit layer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import resale  # noqa: E402


def test_model_comp_beats_brand_guess():
    r = resale.evaluate("Rick Owens", "kengät", 120, 672, "Rick Owens Geobasket nahka tennarit", 1.0, "sellpy")
    assert r["exit"] == "grailed"
    assert "geobasket" in r["why"][0]
    # 420 × 0.8 liquidity × 0.875 fees − 0.5 − (120 + 5.9)
    assert 160 <= r["profit"] <= 170


def test_collab_is_discounted():
    plain = resale.evaluate("Raf Simons", "takki", 50, 500, "Raf Simons takki", 1.0, "tori")
    collab = resale.evaluate("Raf Simons", "takki", 50, 500, "Raf Simons x Calvin Klein takki", 1.0, "tori")
    assert collab["profit"] < plain["profit"]
    assert any("calvin klein" in w for w in collab["why"])


def test_non_garments_and_fabric_mentions_are_skipped():
    assert resale.evaluate("Undercover", "muu", 20, 400, "Undercover osoitekirja") is None
    assert resale.evaluate("Loro Piana", "takki", 60, 500, "Rose & Born kavaj tyg Loro Piana") is None


def test_mainstream_brand_has_no_grailed_exit():
    r = resale.evaluate("Comme des Garçons Play", "t-paita", 10, 30, "CDG Play t-paita", 1.0, "sellpy")
    assert r["exit"] != "grailed"
    assert r["profit"] < 0


def test_rank_key_prefers_profit():
    a = {"profit": 200, "score": 2.0}
    b = {"profit": 50, "score": 9.0}
    c = {"profit": None, "score": 20}
    assert sorted([c, b, a], key=resale.rank_key) == [a, b, c]


def test_yahoo_comps_anchor_generic_pieces(monkeypatch):
    fake = {"Helmut Lang": {"cats": {"takki": {"n": 10, "median": 400, "p25": 200, "p75": 900}}}}
    monkeypatch.setattr(resale, "yahoo", lambda: fake)
    r = resale.evaluate("Helmut Lang", "takki", 20, 999, "Helmut Lang takki", 1.0, "sellpy")
    assert r["why"][0].startswith("Yahoo JP")
    assert r["resale"] == round((400 + 200) / 2 * 1.15)


def _ev():
    import sniper
    cfg = sniper.load_yaml("config.yaml")
    ev = sniper.Evaluator(cfg, sniper.BrandMatcher(sniper.load_brands()), {"brands": {}}, "fi")
    ev.buy_source = "auctionet"
    return ev


def _hit(title, eur):
    return {"objectID": "x1", "_price": eur, "title": title, "images": [],
            "metadata": {"brand": "Hermès", "type": title, "size": "", "condition": "Hyvä"},
            "categories": {"lvl0": ""}, "description": ""}


class _P:
    def price(self, hit):
        return hit["_price"]


def test_kelly_at_auction_alerts_on_profit_scarf_does_not():
    ev = _ev()
    f = ev.evaluate(_hit("Hermès Kelly 32 väska box calf", 4500), _P())
    assert f is not None and f.profit > 300
    assert any("kelly" in r for r in f.reasons)
    assert ev.evaluate(_hit("Hermès carré silk scarf huivi", 150), _P()) is None
