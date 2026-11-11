#!/usr/bin/env python3
"""Feasibility probe round 2: parse the reachable sources and print real sample rows."""
import json, re, time, statistics
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8"}
S = requests.Session(); S.headers.update(UA)

def get(u, **kw):
    r = S.get(u, timeout=25, **kw); time.sleep(1); return r

def ld(t):
    out = []
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', t, re.S):
        try: out.append(json.loads(m.group(1)))
        except Exception: pass
    return out

def nextdata(t):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
    return json.loads(m.group(1)) if m else None

def walk_keys(o, depth=0, path=""):
    if depth > 6: return
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, list) and v and isinstance(v[0], dict) and len(v) >= 5:
                print(f"   list {path}.{k} len={len(v)} keys={list(v[0])[:14]}")
            walk_keys(v, depth + 1, f"{path}.{k}")
    elif isinstance(o, list) and o:
        walk_keys(o[0], depth + 1, path + "[0]")

def sec(n): print(f"\n===== {n} =====", flush=True)

# --- Yahoo Auctions: open + sold (closed) ---
for kind, url in [("open", "https://auctions.yahoo.co.jp/search/search?p=yohji+yamamoto&n=100&s1=new&o1=d"),
                  ("sold", "https://auctions.yahoo.co.jp/closedsearch/closedsearch?p=yohji+yamamoto+pour+homme&n=100")]:
    sec(f"yahoo {kind}")
    try:
        t = get(url).text
        nd = nextdata(t)
        if nd: walk_keys(nd)
        prices = [int(x.replace(",", "")) for x in re.findall(r'data-auction-price="(\d+)"', t)] or \
                 [int(x.replace(",", "")) for x in re.findall(r'"price"\s*:\s*(\d+)', t)]
        titles = re.findall(r'data-auction-title="([^"]+)"', t)[:5]
        print(" n_prices", len(prices), "median_yen", statistics.median(prices) if prices else None, titles)
        for d in ld(t): print(" ld", str(d)[:300])
    except Exception as e: print(" ERR", e)

# --- Rakuma / Mercari (SSR?) ---
for n, u in [("rakuma", "https://fril.jp/s?query=yohji+yamamoto&sort=created_at&order=desc"),
             ("mercari", "https://jp.mercari.com/search?keyword=yohji%20yamamoto&order=desc&sort=created_time")]:
    sec(n)
    try:
        t = get(u).text
        print(" item links", len(set(re.findall(r'(?:item\.fril\.jp/|/item/m)\w+', t))), "yen", re.findall(r'[¥￥]\s?[\d,]+', t)[:8])
        print(" captcha ctx", re.findall(r'.{60}(?:captcha|challenge).{60}', t, re.I)[:2])
    except Exception as e: print(" ERR", e)

# --- Grailed ---
sec("grailed")
try:
    t = get("https://www.grailed.com/shop?query=yohji%20yamamoto").text
    nd = nextdata(t)
    if nd: walk_keys(nd)
    print(" algolia?", re.findall(r'(?i)algolia[^"\']{0,60}', t)[:3])
    print(" captcha ctx", re.findall(r'.{60}(?:captcha|challenge).{40}', t, re.I)[:2])
except Exception as e: print(" ERR", e)

# --- Auctionet ---
sec("auctionet")
for u in ["https://auctionet.com/api/v2/items.json?q=yohji", "https://auctionet.com/api/v2/items.json?query=yohji",
          "https://auctionet.com/api/v2/items.json?category_id=&q=hermes", "https://auctionet.com/api/v2/items.json"]:
    try:
        j = get(u).json(); it = j.get("items", [])
        print(f" {u} -> {len(it)} pag={j.get('pagination')}")
        if it: print("  keys", list(it[0])[:25]); print("  sample", {k: it[0].get(k) for k in ['title','currency','estimate','upcoming_bid','state','ends_at','house','category_id'] if k in it[0]})
    except Exception as e: print(" ERR", u, e)
try:
    t = get("https://auctionet.com/en/search?q=yohji+yamamoto").text
    for d in ld(t): print(" ld", str(d)[:400])
    print(" item links", len(set(re.findall(r'/en/(\d+)-[\w-]+', t))), re.findall(r'/en/\d+-[\w-]+', t)[:5])
except Exception as e: print(" ERR", e)

# --- Zadaa ---
sec("zadaa")
for u in ["https://zadaa.co/fi", "https://zadaa.co/fi/search?q=acne", "https://zadaa.co/fi/brands/acne-studios",
          "https://zadaa.co/api/products?search=acne", "https://zadaa.co/robots.txt", "https://zadaa.co/sitemap.xml"]:
    try:
        r = get(u); t = r.text
        print(f" {u} {r.status_code} {len(t)}B ct={r.headers.get('content-type','')[:25]} eur={len(re.findall('€', t))} prodlinks={len(set(re.findall(r'/(?:fi/)?(?:p|product|products|item)/[\w-]+', t)))}")
        if u.endswith(".txt"): print(t[:600])
        if "api" in t[:0]: pass
        apis = set(re.findall(r'https?://[\w.-]*(?:api|graphql)[\w./-]*', t))
        if apis: print("  apis", list(apis)[:6])
        for d in ld(t)[:2]: print("  ld", str(d)[:300])
    except Exception as e: print(" ERR", u, e)

# --- Kleinanzeigen ---
sec("kleinanzeigen")
try:
    t = get("https://www.kleinanzeigen.de/s-mode-beauty/rick-owens/k0c153").text
    items = re.findall(r'data-adid="(\d+)"', t)
    pr = re.findall(r'aditem-main--middle--price-shipping--price">\s*([^<]+)<', t)
    print(" ads", len(items), "prices", [p.strip() for p in pr[:10]])
    print(" versand", len(re.findall(r'Versand möglich', t)))
except Exception as e: print(" ERR", e)

# --- Hagelstam / Helander quick content check ---
sec("auction houses fi")
for u in ["https://www.hagelstam.fi/", "https://www.helander.com/"]:
    try:
        t = get(u).text
        print(" ", u, re.findall(r'(?i)(muoti|fashion|laukku|hermès|hermes|chanel|louis vuitton|kello|watch)', t)[:10])
    except Exception as e: print(" ERR", e)
