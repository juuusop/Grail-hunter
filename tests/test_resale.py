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
