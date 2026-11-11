"""Probe which second-hand marketplaces answer machine requests from GitHub Actions."""
import json, re, time
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0 Safari/537.36",
      "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8"}
out = {}

def probe(name, fn):
    try:
        out[name] = fn()
    except Exception as e:
        out[name] = {"error": repr(e)[:300]}
    time.sleep(1)

def get(url, s=None, **kw):
    r = (s or requests).get(url, headers={**UA, **kw.pop("headers", {})}, timeout=20, **kw)
    return {"status": r.status_code, "ctype": r.headers.get("content-type"), "len": len(r.text), "head": r.text[:1500]}

def finds(text, pats):
    return {p: sorted(set(re.findall(p, text)))[:10] for p in pats}

probe("huuto_api", lambda: get("https://api.huuto.net/1.1/items?words=margiela&sort=newest"))
probe("tori_html", lambda: get("https://www.tori.fi/recommerce/forsale/search?q=margiela"))
probe("tori_api", lambda: get("https://www.tori.fi/recommerce-search-page/api/search/SEARCH_ID_BAP_COMMON?q=margiela"))
def vinted():
    s = requests.Session()
    h = s.get("https://www.vinted.fi/", headers=UA, timeout=20)
    r = get("https://www.vinted.fi/api/v2/catalog/items?search_text=margiela&order=newest_first&per_page=20", s,
            headers={"Accept": "application/json"})
    r["home_status"] = h.status_code
    r["cookies"] = list(s.cookies.keys())
    return r
probe("vinted", vinted)
probe("emmy_products", lambda: get("https://emmy.fi/products.json?limit=5"))
def emmy_html():
    r = requests.get("https://emmy.fi/", headers=UA, timeout=20)
    return {"status": r.status_code, "len": len(r.text), "hints": finds(r.text, [r"algolia[^\"']{0,60}", r"shopify[^\"']{0,40}", r"https://[a-z0-9.-]*api[a-z0-9./-]*", r"_next/static", r"graphql[^\"']{0,60}"])}
probe("emmy_html", emmy_html)
probe("zadaa", lambda: get("https://www.zadaa.co/fi/search?q=margiela"))
probe("tradera_html", lambda: get("https://www.tradera.com/search?q=margiela"))
def grailed():
    r = requests.get("https://www.grailed.com/shop", headers=UA, timeout=20)
    js = re.findall(r'src="([^"]+\.js)"', r.text)[:40]
    hints = finds(r.text, [r"[A-Z0-9]{10}", r"algolia[^\"']{0,80}", r"[a-f0-9]{32}"])
    for u in js:
        if not u.startswith("http"):
            u = "https://www.grailed.com" + u
        try:
            t = requests.get(u, headers=UA, timeout=20).text
        except Exception:
            continue
        if "algolia" in t.lower():
            hints[u] = finds(t, [r'"[A-Z0-9]{10}"', r'"[a-f0-9]{32}"', r'Listing_[A-Za-z_]+'])
    return {"status": r.status_code, "len": len(r.text), "hints": hints}
probe("grailed", grailed)
probe("depop", lambda: get("https://webapi.depop.com/api/v2/search/products/?what=margiela&country=fi&currency=EUR&itemsPerPage=5"))
probe("vestiaire", lambda: {"status": (r := requests.post("https://search.vestiairecollective.com/v1/product/search",
       json={"pagination": {"offset": 0, "limit": 5}, "fields": ["name", "price", "brand", "link"], "q": "margiela", "locale": {"country": "FI", "currency": "EUR", "language": "en", "sizeType": "FR", "site": 1}},
       headers={**UA, "Content-Type": "application/json"}, timeout=20)).status_code, "head": r.text[:1500]})
def sellpy_other():
    res = {}
    for m in ["se", "de", "nl", "at", "dk", "pl", "fr", "be"]:
        r = requests.post("https://50LBQU2I4A-dsn.algolia.net/1/indexes/*/queries",
            headers={"X-Algolia-Application-Id": "50LBQU2I4A", "X-Algolia-API-Key": "4e696a94df3469d5356870d63c118c87", **UA},
            json={"requests": [{"indexName": f"prod_marketItem_{m}_saleStartedAt_desc", "params": "query=&hitsPerPage=1&facets=%5B%22metadata.brand%22%5D&maxValuesPerFacet=3"}]}, timeout=20)
        j = r.json() if r.status_code == 200 else {}
        rr = (j.get("results") or [{}])[0]
        h = (rr.get("hits") or [{}])[0]
        res[m] = {"status": r.status_code, "nb": rr.get("nbHits"), "price_keys": [k for k in h if k.startswith("price")], "err": r.text[:200] if r.status_code != 200 else None}
    # does the fi index contain items from other markets?
    return res
probe("sellpy_markets", sellpy_other)
json.dump(out, open("data/probe.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: (v.get("status") if isinstance(v, dict) else v) for k, v in out.items()}))
