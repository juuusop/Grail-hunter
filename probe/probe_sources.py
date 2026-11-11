#!/usr/bin/env python3
"""Probe round 3: real price data. Yahoo Auctions JP sold vs open per brand, Auctionet fashion volume, Kleinanzeigen."""
import json, re, time, statistics as st
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "ja,en;q=0.8"}
S = requests.Session(); S.headers.update(UA)
def get(u, **kw):
    r = S.get(u, timeout=25, **kw); time.sleep(1.2); return r
def nextdata(t):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
    return json.loads(m.group(1)) if m else None

try:
    rates = requests.get("https://api.frankfurter.app/latest?from=EUR&to=JPY,SEK", timeout=15).json()["rates"]
except Exception:
    rates = {"JPY": 170.0, "SEK": 11.3}
JPY = rates["JPY"]; print("rates", rates)

def yahoo(q, closed):
    base = "https://auctions.yahoo.co.jp/closedsearch/closedsearch" if closed else "https://auctions.yahoo.co.jp/search/search"
    # category 23000 = ファッション
    nd = nextdata(get(base, params={"p": q, "n": 100, "auccat": 23000, "s1": "new" if not closed else "end", "o1": "d"}).text)
    items = nd["props"]["pageProps"]["initialState"]["search"]["items"]["listing"]["items"]
    return items

first = True
rows = []
for q, label in [("yohji yamamoto pour homme", "Yohji Yamamoto"), ("comme des garcons homme plus", "CDG Homme Plus"),
                 ("junya watanabe man", "Junya Watanabe MAN"), ("homme plisse issey miyake", "Homme Plissé"),
                 ("undercover", "Undercover"), ("number nine", "Number (N)ine"), ("kapital", "Kapital"),
                 ("visvim", "Visvim"), ("sacai", "Sacai"), ("kolor", "Kolor"),
                 ("rick owens", "Rick Owens"), ("maison margiela", "Maison Margiela"), ("helmut lang", "Helmut Lang")]:
    try:
        sold = yahoo(q, True); live = yahoo(q, False)
        if first:
            print("ITEM KEYS", list(sold[0])); print("SAMPLE", {k: sold[0][k] for k in list(sold[0])[:40]}); first = False
        sp = [i.get("price") or i.get("currentPrice") for i in sold]; sp = [p for p in sp if p]
        bn = [i.get("buyNowPrice") for i in live if i.get("buyNowPrice")]
        cp = [i.get("price") or i.get("currentPrice") for i in live]; cp = [p for p in cp if p]
        r = dict(brand=label, sold_n=len(sp), sold_med_eur=round(st.median(sp) / JPY) if sp else None,
                 sold_p25_eur=round(st.quantiles(sp, n=4)[0] / JPY) if len(sp) > 4 else None,
                 live_n=len(cp), live_med_eur=round(st.median(cp) / JPY) if cp else None,
                 buynow_n=len(bn), buynow_p25_eur=round(st.quantiles(bn, n=4)[0] / JPY) if len(bn) > 4 else None)
        rows.append(r); print("ROW", json.dumps(r, ensure_ascii=False))
    except Exception as e:
        print("ERR", label, repr(e)[:200])

print("\n===== auctionet =====")
try:
    j = get("https://auctionet.com/api/v2/categories.json").json()
    print("cat keys", list(j)[:5]); cats = j.get("categories") or j
    for c in (cats if isinstance(cats, list) else [])[:200]:
        n = (c.get("name") or c.get("title") or "")
        if re.search(r"(?i)cloth|fashion|kläder|accessor|bag|väsk|shoe|sko|textil|watch|klock|jewel|smycke", str(c)):
            print("  CAT", c)
except Exception as e: print("ERR cats", e)
for q in ["hermes", "chanel", "louis vuitton", "prada", "gucci", "rolex", "comme des garcons", "margiela", "rick owens", "acne"]:
    try:
        j = get("https://auctionet.com/api/v2/items.json", params={"q": q}).json()
        it = j["items"]
        print(f"  {q:20} total={j['pagination']['total_entries']} houses={len({i['house'] for i in it})} "
              f"ex={[(i['title'][:45], i['currency'], i.get('estimate'), i.get('next_bid_amount')) for i in it[:2]]}")
    except Exception as e: print("ERR", q, e)

print("\n===== kleinanzeigen =====")
try:
    t = get("https://www.kleinanzeigen.de/s-mode-beauty/rick-owens/k0c153", headers={"Accept-Language": "de-DE"}).text
    pr = re.findall(r'price-shipping--price[^>]*>\s*([^<]+?)\s*<', t)
    print(" prices", pr[:15])
except Exception as e: print("ERR", e)
