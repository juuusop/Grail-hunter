import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import risk as R  # noqa: E402
import sniper as S  # noqa: E402
import yaml  # noqa: E402


def _cond(c):
    class X:
        cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text(encoding="utf-8"))
    return S.Evaluator._condition(X(), c)


def test_condition_grades_ordered():
    # "Hyväksyttävä" used to fall through to 0.95 (better than "Hyvä")
    assert _cond("Hyväksyttävä") == 0.7
    assert _cond("Uusi") > _cond("Erittäin hyvä") > _cond("Hyvä") > _cond("Hyväksyttävä") > _cond("Huono")
    assert _cond("Zo goed als nieuw") == 1.0 and _cond("Gebruikt") == 0.7


def test_fake_risk_levels():
    lv = R.assess("Louis Vuitton", "laukku", 40, 600, "Louis Vuitton Neverfull", source="tori")
    assert lv["fake_level"] == "korkea"
    same_sellpy = R.assess("Louis Vuitton", "laukku", 40, 600, "Louis Vuitton Neverfull", source="sellpy")
    assert same_sellpy["fake"] < lv["fake"]
    blazer = R.assess("Thierry Mugler", "takki", 14, 380, "Thierry Mugler Bleiseri", source="sellpy")
    assert blazer["fake_level"] == "matala"


def test_margiela_replica_is_not_a_fake_word():
    r = R.assess("Maison Margiela", "kengät", 150, 330, "Maison Margiela Replica sneakers", source="sellpy")
    assert not any("tekstissä" in w for w in r["why"])
    r2 = R.assess("Gucci", "laukku", 150, 330, "Gucci replica bag 1:1", source="tori")
    assert any("tekstissä" in w for w in r2["why"])


def test_condition_flag():
    assert R.condition("Hyväksyttävä", "kengät")[0] == "kulunut"
    assert R.condition("Erittäin hyvä")[0] == "ok"
    assert R.condition("-")[0] == "?"
