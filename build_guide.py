"""Renders guide.html (Brändiopas) from brand_guide.yaml + brands.yaml + data files.

python build_guide.py  ->  guide.html (self-contained, published as an Artifact)
"""
import collections
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent


def load(name, default):
    try:
        p = ROOT / name
        return json.loads(p.read_text()) if name.endswith(".json") else yaml.safe_load(p.read_text())
    except FileNotFoundError:
        return default


def main():
    guide = load("brand_guide.yaml", {})
    brands = load("brands.yaml", {}).get("brands", [])
    resolved = load("data/brands_resolved.json", {}).get("brands", {})
    comps = load("data/comps.json", {}).get("brands", {})
    finds = collections.Counter(f["brand"] for f in load("data/finds.json", []))
    rows = []
    for i, b in enumerate(brands):
        n = b["name"]
        g = guide.get(n) or {}
        s = resolved.get(n) or {}
        j = comps.get(n) or {}
        boost = {**(g.get("kw") or {}), **(b.get("boost") or {})}
        rows.append({
            "i": i, "n": n, "v": b["value"], "rare": bool(b.get("rare")),
            "al": b.get("aliases") or [],
            "t": g.get("tier", "C"), "h": g.get("hype", 0), "q": g.get("quality", 0), "f": g.get("fake", 0),
            "st": g.get("status", ""), "good": g.get("good", ""), "bad": g.get("bad", ""),
            "buy": g.get("buy", ""), "avoid": g.get("avoid", ""), "tells": g.get("tells", ""),
            "kw": boost,
            "sm": s.get("median") if (s.get("count") or 0) >= 10 else None, "sn": s.get("count") or 0,
            "jm": j.get("median") if (j.get("n") or 0) >= 20 else None, "jn": j.get("n") or 0,
            "fc": finds.get(n, 0),
        })
    tpl = (ROOT / "guide_template.html").read_text()
    out = tpl.replace("/*DATA*/[]", json.dumps(rows, ensure_ascii=False))
    (ROOT / "guide.html").write_text(out)
    print(f"guide.html: {len(rows)} brands, {len(out) // 1024} KB")


if __name__ == "__main__":
    main()
