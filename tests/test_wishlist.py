import wishlist as W


def test_parse_comment():
    p = W.parse_comment("twelve south curve, läppäriteline\nmax 60\nuusi 98 €\n-ipad, -tabletti")
    assert p["queries"] == ["twelve south curve", "läppäriteline"]
    assert p["name"] == "twelve south curve" and p["max_price"] == 60 and p["new_price"] == 98
    assert p["exclude"] == ["ipad", "tabletti"]
    assert W.parse_comment("pois twelve south curve") == {"remove": "twelve south curve"}
    assert W.parse_comment("   ") is None


def test_matches():
    it = {"queries": ["näyttövarsi", "monitor arm"], "exclude": ["dual", "kahdelle"]}
    assert W.matches(it, "Näyttövarsi kaasujousella", "")
    assert W.matches(it, "Ergotron LX Monitor Arm", "")
    assert not W.matches(it, "Dual monitor arm", "")
    assert not W.matches(it, "Näyttöteline", "")
    assert W.matches({"queries": ["läppäriteline"]}, "Läppäritelineet 2kpl", "")


def test_load_items_comments():
    cs = [{"user": {"type": "User"}, "body": "polkupyörä, maantiepyörä\nmax 300"},
          {"user": {"type": "Bot"}, "body": "### 🛒 kissa"},
          {"user": {"type": "User"}, "body": "pois näyttövarsi"}]
    names = [i["name"] for i in W.load_items(cs)]
    assert "polkupyörä" in names and not any("Näyttövarsi" in n for n in names)
    assert any("Läppäriteline" in n for n in names)
