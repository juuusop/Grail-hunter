#!/usr/bin/env python3
"""Resale value + expected profit for every find (config: resale.yaml).

The sniper's score (value / price) says a price is low. This layer says whether money is left
after selling: realistic sale price from comps, the best exit platform after its fees, minus the
buy price and delivery. Every find gets the numbers and where they came from.

Commands:
  python resale.py comps    collect sold comps from Huuto.net (official API, closed auctions)
                            into data/comps.json  (GitHub Actions runs this daily)
  python resale.py report   rank all known finds by expected profit -> data/PROFIT.md
"""
from __future__ import annotations

import statistics
import sys
import time
from functools import lru_cache

import sniper as S

COMPS_FILE = S.DATA / "comps.json"
PROFIT_MD = S.DATA / "PROFIT.md"


@lru_cache(maxsize=1)
def cfg() -> dict:
    try:
        return S.load_yaml("resale.yaml") or {}
    except FileNotFoundError:
        return {}


@lru_cache(maxsize=1)
def brand_values() -> dict:
    try:
        return {b.name: b.value for b in S.load_brands()}
    except Exception:
        return {}


@lru_cache(maxsize=1)
def comps() -> dict:
    return S.load_json(COMPS_FILE, {}).get("groups", {})


@lru_cache(maxsize=1)
def core_cfg() -> dict:
    return S.load_yaml("config.yaml") or {}


def reset_cache():
    core_cfg.cache_clear()
    cfg.cache_clear()
    brand_values.cache_clear()
    comps.cache_clear()


def tier(brand: str, value: float) -> str:
    th = cfg().get("tier_thresholds") or {"archive": 200, "designer": 90}
    v = brand_values().get(brand, value)
    if v >= th.get("archive", 200):
        return "archive"
    if v >= th.get("designer", 90):
        return "designer"
    return "mainstream"


def model_match(brand: str, text: str) -> dict | None:
    best, blen = None, -1
    for m in cfg().get("models") or []:
        if m.get("brand") != brand:
            continue
        if m.get("words") and not all(S.has_word(text, w) for w in m["words"]):
            continue
        hits = [w for w in (m.get("any_words") or []) if S.has_word(text, w)]
        if m.get("any_words") and not hits:
            continue
        ln = sum(len(w) for w in (m.get("words") or [])) + max((len(w) for w in hits), default=0)
        if ln > blen:
            best, blen = {**m, "_hit": (m.get("words") or hits)[0]}, ln
    return best


def local_comp(brand: str, category: str) -> dict | None:
    g = comps().get(f"{brand}|{category}") or {}
    n = int(g.get("n", 0))
    if n >= int(cfg().get("min_comps", 4)):
        return g
    return None


def resellable(text: str) -> bool:
    """Only garments, shoes, bags and jewellery resell; books, cases and nipple covers don't."""
    from markets import APPAREL, JUNK
    extra = ["mekko", "klänning", "takki", "laukku", "saappaat", "nilkkurit", "sormus", "ring", "kaulakoru",
             "rannekoru", "bleiseri", "liivi", "neule", "paita", "housut", "farkut", "kengät", "tennarit", "nahkatakki"]
    if any(S.has_word(text, w) for w in JUNK + ["nännisuoja", "osoitekirja", "muistikirja", "kirja", "taidekirja",
                                     "meikkipussi", "kosmetiikkalaukku", "toilettilaukku", "puhelinkuori", "kuori"]):
        return False
    return any(S.has_word(text, w) or w in text for w in APPAREL + extra if len(w) >= 5) or \
        any(S.has_word(text, w) for w in APPAREL + extra if len(w) < 5)


def evaluate(brand: str, category: str, price: float, value: float, text: str,
             kmult: float = 1.0, buy_source: str = "sellpy") -> dict | None:
    """Returns {resale, profit, roi, exit, why:[...]} for one item, None if it is not a resellable piece."""
    c = cfg()
    text = S.norm(text)
    why = []
    if not resellable(text):
        return None
    bn = S.norm(brand)
    for w in c.get("fabric_words") or []:
        if f"{S.norm(w)} {bn}" in text or f"{S.norm(w)} by {bn}" in text:
            return None  # "tyg Loro Piana": only the fabric is the brand
    m = model_match(brand, text)
    if m:
        intl = float(m["price"]) * kmult
        why.append(f"malli '{m['_hit']}' ~{m['price']} € (taulukko{': ' + m['why'] if m.get('why') else ''})")
    else:
        intl = float(value) * float(c.get("generic_factor", 0.75))
        hits = [(w, float(x)) for w, x in (c.get("collab_words") or {}).items()
                if S.norm(w) != bn and S.has_word(text, w)]
        if hits:
            w, x = min(hits, key=lambda h: h[1])
            intl *= x
            why.append(f"massakollaboraatio/diffuusio '{w}' ×{x:g}")
        why.insert(0, f"brändiarvio ~{intl:.0f} € (ei mallivertailua, geneerinen kappale)")
    t = tier(brand, value)
    lc = local_comp(brand, category)
    buy = price + float((c.get("buy_costs") or {}).get(buy_source, 6.0))
    best = None
    for name, e in (c.get("exits") or {"tori": {"price": 0.6, "liquidity": 0.95}}).items():
        if e.get("only_tiers") and t not in e["only_tiers"]:
            continue
        gross = intl * float(e.get("price", 1.0))
        src = ""
        if name == "tori" and lc:
            gross, src = float(lc["median"]), f" (Huudon toteutuneet: mediaani {lc['median']:.0f} €, n={lc['n']})"
        net = gross * float(e.get("liquidity", 1.0)) * (1 - float(e.get("fee", 0))) \
            - float(e.get("fixed", 0)) - float(e.get("ship", 0))
        if best is None or net > best[1]:
            best = (name, net, gross, src)
    name, net, gross, src = best
    profit = net - buy
    why.append(f"myynti {name} ~{gross:.0f} €{src} → käteen ~{net:.0f} € kulujen ja tinkimisen jälkeen")
    why.append(f"osto {price:.0f} € + toimitus = {buy:.0f} €")
    if category in (c.get("low_margin_categories") or []):
        why.append(f"{category}: matala kate-kategoria, paljon tarjontaa")
    return {"resale": round(gross), "profit": round(profit), "roi": round(profit / buy, 2) if buy else 0.0,
            "exit": name, "tier": t, "why": why}


def annotate(f, text: str, kmult: float = 1.0, buy_source: str = "sellpy"):
    """Adds resale fields + a one-line reason to a sniper.Find. Never fails the find."""
    try:
        brand = f.brand.split(" · ")[0]
        r = evaluate(brand, f.category, f.price, f.value, f"{f.title} {text}", kmult, buy_source)
    except Exception as e:  # pragma: no cover
        S.log(f"resale: {e!r}")
        return f
    if r is None:
        f.reasons.append("kate: ei arvioitavissa (ei vaate/kenkä/laukku tai vain materiaali)")
        return f
    f.resale, f.profit, f.roi, f.exit, f.resale_why = r["resale"], r["profit"], r["roi"], r["exit"], r["why"]
    c = cfg()
    tag = "💰 " if r["profit"] >= float(c.get("min_profit", 60)) and r["roi"] >= float(c.get("min_roi", 0.5)) else ""
    if r["profit"] < 0:
        tag = "⚠️ "
    f.reasons.append(f"{tag}kate ~{r['profit']} € (ROI {r['roi']:.0%}, myy {r['exit']} ~{r['resale']} €; {r['why'][0]})")
    return f


def rank_key(f) -> tuple:
    p = getattr(f, "profit", None) if not isinstance(f, dict) else f.get("profit")
    s = getattr(f, "score", 0) if not isinstance(f, dict) else f.get("score", 0)
    return (-(p if p is not None else -1e9), -s)


# ---------------------------------------------------------------- comps from Huuto.net
def _category(title: str) -> str:
    t = S.norm(title)
    for c in core_cfg().get("categories", []):
        if any(S.has_word(t, w) for w in c["words"]):
            return c["name"]
    return "muu"


def collect_comps(per_run: int = 40):
    """Closed Huuto.net auctions with bids = real sale prices on the Finnish market."""
    import requests
    from markets import TextBrandFinder, UA, JUNK

    data = S.load_json(COMPS_FILE, {"items": {}, "i": 0})
    items = data.setdefault("items", {})
    brands = [b for b in S.load_brands() if b.value >= 90 or b.rare]
    brands.sort(key=lambda b: -b.value)
    finder = TextBrandFinder(brands)
    i = data.get("i", 0) % max(1, len(brands))
    pick = (brands[i:] + brands[:i])[:per_run]
    data["i"] = i + per_run
    logged = False
    added = 0
    for b in pick:
        try:
            r = requests.get("https://api.huuto.net/1.1/items", headers=UA, timeout=25,
                             params={"words": b.name, "status": "closed", "sort": "newest"})
            r.raise_for_status()
            js = r.json()
        except Exception as e:
            S.log(f"comps {b.name}: {e}")
            continue
        for it in js.get("items") or []:
            if not logged:
                S.log("comps sample keys: " + ", ".join(sorted(it.keys())))
                S.log("comps sample: " + str({k: it.get(k) for k in ("status", "saleMethod", "currentPrice", "buyNowPrice",
                                                                    "bidderCount", "bids", "hasReservePrice",
                                                                    "hasReservePriceExceeded", "closingTime")}))
                logged = True
            title = it.get("title") or ""
            if finder.find(title) is not b or any(S.has_word(S.norm(title), w) for w in JUNK):
                continue
            bids = it.get("bidderCount") or it.get("bids") or 0
            if isinstance(bids, list):
                bids = len(bids)
            if not bids or (it.get("hasReservePrice") and not it.get("hasReservePriceExceeded", True)):
                continue  # no sale happened
            p = float(it.get("currentPrice") or 0)
            if p <= 0:
                continue
            key = str(it.get("id"))
            if key not in items:
                added += 1
            items[key] = {"brand": b.name, "cat": _category(title), "price": p, "title": title[:90],
                          "closed": it.get("closingTime"), "ts": S.now_ts()}
        time.sleep(1.5)
    cutoff = S.now_ts() - 365 * 86400
    data["items"] = {k: v for k, v in items.items() if v["ts"] >= cutoff}
    groups: dict[str, list[float]] = {}
    for v in data["items"].values():
        groups.setdefault(f"{v['brand']}|{v['cat']}", []).append(v["price"])
    data["groups"] = {k: {"n": len(v), "median": round(statistics.median(v), 1),
                          "p25": round(sorted(v)[len(v) // 4], 1), "p75": round(sorted(v)[3 * len(v) // 4], 1)}
                      for k, v in groups.items()}
    data["generated"] = S.now_ts()
    S.save_json(COMPS_FILE, data)
    S.log(f"comps: {len(pick)} brands, +{added} sold, total {len(data['items'])}, groups {len(data['groups'])}")


# ---------------------------------------------------------------- report
def _cond_mult(cond: str) -> float:
    n = S.norm(cond or "")
    best = None
    for c in core_cfg().get("conditions", []):
        for w in c["words"]:
            if S.has_word(n, w) and (best is None or len(S.norm(w)) > best[0]):
                best = (len(S.norm(w)), float(c["mult"]))
    return best[1] if best else 0.95


def score_dict(d: dict) -> dict | None:
    brand = (d.get("brand") or "").split(" · ")[0]
    if brand.startswith("Tuntematon"):
        return None
    src = d.get("source") or "sellpy"
    text = " ".join(str(x) for x in [d.get("title"), d.get("type"), d.get("model"), d.get("keywords"),
                                      d.get("details"), " ".join(d.get("reasons") or [])] if x)
    kmult = _cond_mult(d.get("condition", ""))
    base = brand_values().get(brand)
    if base is None:
        return None
    # rebuild the brand-level estimate without the keyword boosts (the model table replaces those)
    cmult = next((float(c["mult"]) for c in core_cfg().get("categories", [])
                  if c["name"] == d.get("category")), 0.8)
    cat = _category(" ".join(str(x) for x in [d.get("title"), d.get("type")] if x))
    cmult = next((float(c["mult"]) for c in core_cfg().get("categories", [])
                  if c["name"] == cat), 0.8)
    r = evaluate(brand, cat, float(d["price"]), base * cmult * kmult, text, kmult, src)
    return {**d, **r, "category": cat} if r else None


def report(limit: int = 60):
    seen, rows = set(), []
    for path, key in [(S.FINDS_FILE, None), (S.DATA / "scan.json", "items"), (S.DATA / "markets_scan.json", "items")]:
        js = S.load_json(path, [] if key is None else {})
        for d in (js if key is None else js.get(key, [])):
            if d.get("id") in seen or not d.get("price"):
                continue
            seen.add(d.get("id"))
            r = score_dict(d)
            if r:
                rows.append(r)
    rows.sort(key=lambda r: -r["profit"])
    good = [r for r in rows if r["profit"] >= float(cfg().get("min_profit", 60))]
    by_exit: dict[str, int] = {}
    for r in good:
        by_exit[r["exit"]] = by_exit.get(r["exit"], 0) + 1
    md = ["# 💰 Kate-ranking", "",
          f"{len(rows)} löytöä arvioitu, {len(good)} joissa odotettu kate ≥ {cfg().get('min_profit', 60)} €. "
          f"Paras myyntikanava: " + ", ".join(f"{k} {v}" for k, v in sorted(by_exit.items(), key=lambda x: -x[1])) + ".",
          "", "Kate = arvioitu myyntihinta parhaassa kanavassa × likviditeetti − palkkiot − (ostohinta + toimitus). "
          "Lähde näkyy perusteluissa: *malli* = käsin koottu vertailutaulukko, *Huudon toteutuneet* = oikeat kaupat, "
          "*brändiarvio* = karkein. Tuote voi olla jo myyty.", "",
          "| Löytö | Hinta | Myynti | Kate | ROI | Miksi |", "|---|---|---|---|---|---|"]
    for r in rows[:limit]:
        title = (r.get("title") or "").replace("|", "/")[:50]
        md.append(f"| **[{r['brand']}]({r['link']})**<br>{title}<br>{r.get('category')} · {r.get('size')} | "
                  f"{r['price']:.0f} € | {r['exit']} ~{r['resale']} € | **{r['profit']} €** | {r['roi']:.0%} | "
                  f"{'<br>'.join(x.replace('|', '/') for x in r['why'])} |")
    PROFIT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    S.log(f"report: {len(rows)} rated, {len(good)} with profit >= min, top: "
          + "; ".join(f"{r['brand']} {r['price']:.0f}€→{r['profit']}€" for r in rows[:5]))
    return rows


if __name__ == "__main__":
    S.DATA.mkdir(exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"comps": collect_comps, "report": report}[cmd]()
