#!/usr/bin/env python3
"""Real resale comps from Yahoo! Auctions Japan sold listings (closedsearch, public pages).

Why: brand `value` numbers in brands.yaml are estimates. Japan is the deepest second-hand
market for designer/archive clothing, and its sold prices are public. This collects the
last ~100 sold items per brand, maps them to the sniper's item categories and writes
  data/comps.json   {brand: {n, median, p25, p75, cats: {category: {n, median, p25}}}}  (EUR)
  data/COMPS.md     brands.yaml value vs. Japan sold vs. Sellpy, with ⚠️ where the estimate looks off.
The sniper only *shows* the comp in an alert's reasons ("Japanissa myyty ..."); it does not
change scoring, so values are re-tuned by a person looking at COMPS.md.

Usage: python comps.py [max_brands]
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
import time
from collections import Counter

import requests

import sniper as S

COMPS_FILE = S.DATA / "comps.json"
COMPS_MD = S.DATA / "COMPS.md"
URL = "https://auctions.yahoo.co.jp/closedsearch/closedsearch"
FASHION = 23000
UA = {"User-Agent": S.UA, "Accept-Language": "ja,en;q=0.8"}

# Yahoo category names -> sniper category (config.yaml), first match wins
JP_CATS = [
    ("nahkatakki", r"レザー.*(ジャケット|ブルゾン|コート)|ライダース"),
    ("asuste", r"ニット帽|ニットキャップ|帽子|キャップ|ハット|財布|ベルト|マフラー|ストール|ネクタイ|手袋|キーケース|小物|ソックス|靴下"),
    ("takki", r"ジャケット|コート|ブルゾン|アウター|ダウン|ジャンパー|ベスト|パーカー?・?ブルゾン"),
    ("kengät", r"スニーカー|ブーツ|シューズ|靴|サンダル|ローファー|革靴"),
    ("laukku", r"バッグ|リュック|鞄|ボストン|トート"),
    ("t-paita", r"Tシャツ|カットソー|ポロシャツ|タンクトップ"),
    ("neule", r"ニット|セーター|カーディガン"),
    ("huppari", r"パーカ|スウェット|トレーナー"),
    ("kauluspaita", r"シャツ"),
    ("housut", r"パンツ|スラックス|デニム|ジーンズ|ショーツ|ボトム"),
    ("korut", r"ネックレス|指輪|リング|ブレスレット|ペンダント|アクセサリー"),
]


def jp_category(item: dict) -> str:
    names = [c.get("name", "") for c in (item.get("categoryPath") or [])] + [(item.get("category") or {}).get("name", "")]
    txt = " ".join(names[::-1])  # most specific first
    for cat, rx in JP_CATS:
        if re.search(rx, txt):
            return cat
    return "muu"


def eur_rate() -> float:
    try:
        return float(requests.get("https://api.frankfurter.app/latest?from=EUR&to=JPY", timeout=15).json()["rates"]["JPY"])
    except Exception:
        return 175.0


def sold_items(session: requests.Session, query: str) -> list[dict]:
    r = session.get(URL, params={"p": query, "n": 100, "auccat": FASHION}, headers=UA, timeout=30)
    r.raise_for_status()
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        return []
    nd = json.loads(m.group(1))
    return (S.dig(nd, "props.pageProps.initialState.search.items.listing.items") or [])


def same_brand(items: list[dict]) -> list[dict]:
    """Keep items whose Yahoo brandId is the dominant one (drops 'kolor' = colour etc.)."""
    ids = Counter(i.get("brandId") for i in items if i.get("brandId"))
    if not ids:
        return items
    top, n = ids.most_common(1)[0]
    return [i for i in items if i.get("brandId") == top] if n >= 0.4 * len(items) else items


def summarize(prices: list[float]) -> dict:
    prices = sorted(prices)
    q = st.quantiles(prices, n=4) if len(prices) >= 4 else [prices[0], st.median(prices), prices[-1]]
    return {"n": len(prices), "median": round(st.median(prices)), "p25": round(q[0]), "p75": round(q[2])}


def brand_query(name: str) -> str:
    return S.norm(name).replace("(n)", "nine").replace("  ", " ").strip()


def collect(max_brands: int = 160) -> dict:
    brands = [b for b in S.load_brands() if b.value >= 100 or b.rare]
    brands.sort(key=lambda b: -b.value)
    brands = brands[:max_brands]
    jpy = eur_rate()
    session = requests.Session()
    out = {"generated": S.now_ts(), "jpy_per_eur": jpy, "source": "Yahoo! Auctions JP sold (closedsearch)", "brands": {}}
    for b in brands:
        try:
            items = same_brand(sold_items(session, brand_query(b.name)))
        except Exception as e:
            S.log(f"comps {b.name}: {e!r}")
            items = []
        time.sleep(2.0)
        prices = [(i["price"] / jpy, jp_category(i)) for i in items if i.get("price")]
        if len(prices) < 5:
            S.log(f"comps {b.name}: {len(prices)} sold, skipped")
            continue
        rec = summarize([p for p, _ in prices])
        cats = {}
        for c in {c for _, c in prices}:
            pc = [p for p, cc in prices if cc == c]
            if len(pc) >= 5:
                cats[c] = summarize(pc)
        rec["cats"] = cats
        out["brands"][b.name] = rec
        S.log(f"comps {b.name}: n={rec['n']} median={rec['median']}€")
    return out


def report(comps: dict) -> str:
    cfg = S.load_yaml("config.yaml")
    cmult = {c["name"]: float(c["mult"]) for c in cfg.get("categories", [])}
    resolved = (S.load_json(S.RESOLVED_FILE, {}) or {}).get("brands", {})
    brands = {b.name: b for b in S.load_brands()}
    rows = []
    for name, c in comps["brands"].items():
        b = brands.get(name)
        if not b:
            continue
        # compare per category: what the sniper thinks a jacket is worth vs. what jackets sold for
        diffs = []
        for cat, cc in c["cats"].items():
            if cat in cmult and cc["n"] >= 8:
                diffs.append((b.value * cmult[cat]) / max(cc["median"], 1))
        ratio = st.median(diffs) if diffs else b.value * 0.8 / max(c["median"], 1)
        sp = resolved.get(name) or {}
        flag = "⚠️ liian korkea?" if ratio >= 2 else ("⬆️ liian matala?" if ratio <= 0.5 else "")
        top = ", ".join(f"{k} {v['median']}€ ({v['n']})" for k, v in sorted(c["cats"].items(), key=lambda kv: -kv[1]["n"])[:3])
        rows.append((ratio, f"| {name} | {b.value:.0f} | {c['median']} ({c['n']}) | {top} | "
                            f"{sp.get('median', '-') if sp else '-'} | {ratio:.1f}× {flag} |"))
    rows.sort(key=lambda r: -r[0])
    head = (f"# Hintavertailu: Japanin myydyt (Yahoo! Auctions)\n\n"
            f"Päivitetty {time.strftime('%Y-%m-%d', time.gmtime(comps['generated']))}, "
            f"kurssi {comps['jpy_per_eur']:.0f} ¥/€. Hinnat euroina ilman toimitusta, viimeiset ~100 myytyä per brändi.\n\n"
            "**Suhde** = sniperin arvio (brands.yaml `value` × kategoriakerroin) / Japanin myyty mediaani samassa kategoriassa. "
            "Yli 2× tarkoittaa että sniper luultavasti yliarvioi brändiä (turhia hälytyksiä), alle 0.5× että aliarvioi (diilejä jää huomaamatta).\n\n"
            "**Lue näin:** Japani on maailman syvin designer-käytettyjen markkina, joten sen myyntihinta on käytännössä *lattiahinta*. "
            "Japanilaiset kotimaan brändit (Kapital, Kolor, Undercover, Yohji) ovat siellä halvempia kuin Euroopassa, joten niillä suhde 2–3× ei vielä todista virhettä. "
            "Pieni n tai outo mediaani (esim. alle 20 €) tarkoittaa yleensä että englanninkielinen haku osui vääriin tuotteisiin, ei että brändi on halpa.\n\n"
            "| Brändi | value | JP myyty mediaani € (n) | kategoriat | Sellpy mediaani € | suhde |\n|---|---|---|---|---|---|\n")
    return head + "\n".join(r for _, r in rows) + "\n"


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 160
    comps = collect(n)
    S.save_json(COMPS_FILE, comps)
    COMPS_MD.write_text(report(comps), encoding="utf-8")
    S.log(f"comps: {len(comps['brands'])} brands -> {COMPS_FILE.name}, {COMPS_MD.name}")


if __name__ == "__main__":
    main()
