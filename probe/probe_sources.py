#!/usr/bin/env python3
"""One-off feasibility probe for new deal sources. Prints status, size and item counts.
Runs in GitHub Actions (the dev sandbox can't reach these hosts)."""
import json, re, time
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8"}
Q = "yohji yamamoto"
PAGES = {
    "auctionet_api": f"https://auctionet.com/api/v2/items.json?q={Q}&per_page=50",
    "auctionet_html": f"https://auctionet.com/en/search?q={Q}",
    "lauritz": f"https://www.lauritz.com/en/search?q={Q}",
    "catawiki_api": f"https://www.catawiki.com/buyer/api/v1/search?q={Q}&per_page=24",
    "catawiki_html": f"https://www.catawiki.com/en/s?q={Q}",
    "bukowskis": f"https://www.bukowskis.com/en/search?q={Q}",
    "helander": "https://www.helander.com/",
    "hagelstam": "https://www.hagelstam.fi/",
    "yahoo_auctions": f"https://auctions.yahoo.co.jp/search/search?p={Q}&n=50",
    "yahoo_closed": f"https://auctions.yahoo.co.jp/closedsearch/closedsearch?p={Q}&n=50",
    "mercari_jp": f"https://jp.mercari.com/search?keyword={Q}",
    "rakuma": f"https://fril.jp/s?query={Q}",
    "2ndstreet_jp": f"https://www.2ndstreet.jp/search?keyword={Q}",
    "ragtag": f"https://www.ragtag.jp/search?q={Q}",
    "zenmarket": f"https://zenmarket.jp/en/yahoo.aspx?q={Q}",
    "buyee": f"https://buyee.jp/item/search/query/{Q}",
    "grailed": f"https://www.grailed.com/shop?query={Q}",
    "zadaa": "https://zadaa.co/fi",
    "ebay_de": f"https://www.ebay.de/sch/i.html?_nkw={Q}&_sop=10",
    "ebay_com": f"https://www.ebay.com/sch/i.html?_nkw={Q}&_sop=10",
    "kleinanzeigen": f"https://www.kleinanzeigen.de/s-{Q.replace(' ', '-')}/k0",
    "blocket": f"https://www.blocket.se/annonser/hela_sverige?q={Q}",
    "finn": f"https://www.finn.no/bap/forsale/search.html?q={Q}",
    "dba": f"https://www.dba.dk/soeg/?soeg={Q}",
    "vinted_fi": f"https://www.vinted.fi/catalog?search_text={Q}",
    "yoox": f"https://www.yoox.com/fi/search?dept=men&textsearch={Q}",
    "theoutnet": f"https://www.theoutnet.com/en-fi/shop/search/{Q}",
    "secondstreet_eu": "https://2ndstreeteurope.com/",
}
SHOPIFY = ["emmy.fi", "relove.fi", "www.relove.fi", "kaartinenkuusela.fi", "www.beyondretro.com", "www.arkivet.se",
           "www.dagmarstore.se", "www.grandvintage.se", "archivepdx.com", "www.archivestore.co", "www.thegoodsdept.com",
           "www.nakedcph.com", "www.kirppu.fi", "www.uffshop.fi", "www.relovestore.com", "www.thefoundry.se",
           "www.grailpoint.com", "www.dot-comme.com", "www.ivoryshop.fi", "www.sweatshop.fi", "www.stylerunner.fi",
           "www.solebox.com", "www.antonia.it", "www.reseeshop.com", "www.vintagestore.fi", "www.archivio.store",
           "www.2ndstreeteurope.com", "us.2ndstreet.com", "www.rebag.com", "www.thereal-real.com", "www.thrifted.com"]

def show(name, url):
    try:
        r = requests.get(url, headers=UA, timeout=25)
        t = r.text
        hints = {k: len(re.findall(p, t)) for k, p in {
            "jsonld": r"application/ld\+json", "nextdata": r"__NEXT_DATA__", "price_yen": r"円", "price_eur": r"€",
            "captcha": r"(?i)captcha|cf-chl|challenge-platform|px-captcha|datadome"}.items()}
        extra = ""
        if "json" in r.headers.get("content-type", ""):
            try:
                j = r.json()
                extra = " keys=" + (",".join(list(j)[:8]) if isinstance(j, dict) else f"list[{len(j)}]")
            except Exception:
                pass
        print(f"{name:16} {r.status_code} {len(t):>8}B {r.headers.get('content-type','')[:30]:30} {hints}{extra}")
    except Exception as e:
        print(f"{name:16} ERR {e!r:.120}")
    time.sleep(1)

print("== pages ==")
for n, u in PAGES.items():
    show(n, u)
print("== shopify products.json ==")
for d in SHOPIFY:
    try:
        r = requests.get(f"https://{d}/products.json?limit=250", headers=UA, timeout=20)
        n = len(r.json().get("products", [])) if r.ok and "json" in r.headers.get("content-type", "") else -1
        vend = {}
        if n > 0:
            for p in r.json()["products"]:
                vend[p.get("vendor")] = vend.get(p.get("vendor"), 0) + 1
            vend = dict(sorted(vend.items(), key=lambda x: -x[1])[:12])
        print(f"{d:28} {r.status_code} products={n} {vend if n > 0 else ''}")
    except Exception as e:
        print(f"{d:28} ERR {e!r:.100}")
    time.sleep(0.5)
