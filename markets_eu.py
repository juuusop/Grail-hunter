"""Nordic + Benelux marketplaces for markets.py.

Sources (public pages only, honest User-Agent, robots.txt allows these paths, ~2.5 s between requests):
  finn         finn.no (Norway)      ┐ same Schibsted "recommerce" platform as tori.fi: the search page carries
  blocket      blocket.se (Sweden)   │ schema.org JSON-LD (name, price, currency, brand, image, url) and a
  dba          dba.dk (Denmark)      ┘ "Shipping" badge per card ("Fiks ferdig" / "Kan skickas" / "Fiks færdig")
  marktplaats  marktplaats.nl        ┐ public JSON search behind the site (structured brand, price type,
  2dehands     2dehands.be           ┘ delivery "Ophalen of Verzenden")

Checked 2026-11-11 from GitHub Actions and left out on purpose:
  kleinanzeigen.de  robots.txt disallows search pages
  subito.it         403 to non-browser clients
  trendsales.dk     TLS handshake refused
  plick.se          no public search URL (app only)
  vinted/depop/vestiaire/grailed/leboncoin  bot walls, not attempted

Realism for a buyer in Finland: these are cross-border private sales. Only listings whose seller already
offers shipping are kept (pickup in Oslo or Utrecht is worthless), and an estimated postage to Finland is added
to the price before scoring, so a find has to be a deal *after* shipping.
"""
from __future__ import annotations

import json
import re
import time

import requests

import sniper as S

# EUR per unit; refreshed from the ECB (frankfurter.app) once per run, these are the fallbacks
FX = {"EUR": 1.0, "SEK": 0.087, "NOK": 0.085, "DKK": 0.134}

RECOMMERCE = {
    "finn": ("www.finn.no", "Finn 🇳🇴"),
    "blocket": ("www.blocket.se", "Blocket 🇸🇪"),
    "dba": ("www.dba.dk", "DBA 🇩🇰"),
}
LRP = {
    "marktplaats": ("www.marktplaats.nl", "Marktplaats 🇳🇱"),
    "2dehands": ("www.2dehands.be", "2dehands 🇧🇪"),
}
# estimated postage of a parcel (~1 kg) to Finland, EUR; override in config.yaml markets.ship_eur
SHIP_EUR = {"finn": 22, "blocket": 15, "dba": 18, "marktplaats": 20, "2dehands": 20}
# Norway is outside the EU: Finnish import VAT 25.5 % on goods + postage, plus the carrier's clearance fee
NON_EU = {"finn": (0.255, 8)}


def landed(source: str, price: float, ship_cfg: dict | None = None) -> tuple[float, str]:
    """Price delivered to Finland and a short Finnish explanation."""
    ship = float((ship_cfg or {}).get(source, SHIP_EUR.get(source, 0)))
    total = price + ship
    note = f"+ ~{ship:.0f} € posti"
    if source in NON_EU:
        vat, fee = NON_EU[source]
        total = total * (1 + vat) + fee
        note += f" + ALV {vat * 100:.1f} % + {fee} € tullaus (Norja ei EU)"
    return round(total, 2), note


FLAG = {k: v[1] for k, v in {**RECOMMERCE, **LRP}.items()}
SOURCES = list(FLAG)

# extra apparel words in Norwegian / Swedish / Danish / Dutch (markets.APPAREL is FI/SE/EN)
APPAREL_EXTRA = ["jakke", "frakke", "kåpe", "dunjakke", "genser", "hettegenser", "hættetrøje", "trøje", "bluse",
                 "bukse", "bukser", "skjorte", "kjole", "skjørt", "nederdel", "sko", "støvler", "støvletter", "veske",
                 "taske", "belte", "bælte", "lue", "skjerf", "tørklæde", "sweater", "pullover", "sneaker",
                 "jas", "jasje", "colbert", "broek", "trui", "overhemd", "jurk", "rok", "schoenen", "laarzen",
                 "tas", "riem", "sjaal", "muts", "vest", "spijkerbroek", "rugzak", "portemonnee", "blazer"]
JUNK_EXTRA = ["parfyme", "boek", "boeken", "bok", "plakat", "nøkkelring", "sleutelhanger", "doos", "eske", "æske"]

# size tokens in free-text titles: "str L", "maat XL", "storlek M", "size 52"; bare XS/XL in caps
_SIZE_WORD = re.compile(r"\b(?:size|str|stl|strl|storlek|størrelse|maat|mt|koko|gr|größe)\.?\s*:?\s*"
                        r"(xxs|xs|s|m|l|xl|xxl|xxxl|[2-4]xl|\d{2})\b", re.I)
_SIZE_BARE = re.compile(r"(?<![\w-])(XXS|XS|XL|XXL|XXXL|[2-4]XL)(?![\w-])")


def title_size(title: str) -> str:
    """Best-effort size code (Sellpy style) from a free-text title, '' if unknown (unknown always passes)."""
    m = _SIZE_WORD.search(title)
    v = m.group(1) if m else None
    if not v:
        m = _SIZE_BARE.search(title)
        v = m.group(1) if m else None
    if not v:
        return ""
    v = v.upper()
    if v.isdigit():
        n = int(v)
        return f"MEN-EU-{n}" if 40 <= n <= 64 and n % 2 == 0 else ""  # 42..46 could be shoes; even = suit sizes
    return f"MEN-INT-{v}"


def refresh_fx(log=print):
    try:
        r = requests.get("https://api.frankfurter.app/latest", params={"from": "EUR", "to": "SEK,NOK,DKK"}, timeout=15)
        for cur, per_eur in (r.json().get("rates") or {}).items():
            if per_eur:
                FX[cur] = round(1 / float(per_eur), 5)
    except Exception as e:  # keep fallbacks
        log(f"fx: {e!r}")


# ---------------------------------------------------------------- Finn / Blocket / DBA
_LD = re.compile(r'<script type="application/ld\+json" id="seoStructuredData">(.*?)</script>', re.S)
_SHIP_ICON = 'name="Shipping"'


def parse_recommerce(html: str):
    """Yield dicts from a recommerce search page. ships=True/False per card, None if the page shows no badges at all."""
    m = _LD.search(html)
    if not m:
        return []
    try:
        els = json.loads(m.group(1)).get("mainEntity", {}).get("itemListElement", [])
    except ValueError:
        return []
    any_badge = _SHIP_ICON in html
    html = html[:m.start()] + html[m.end():]  # the JSON-LD repeats every item URL; only look at the cards
    # card boundaries: each card links to /recommerce/forsale/item/<id>; take the text up to the next card
    pos = [(mm.start(), mm.group(1)) for mm in re.finditer(r"/recommerce/forsale/item/(\d+)", html)]
    first_pos = {}
    for p, iid in pos:
        first_pos.setdefault(iid, p)
    ordered = sorted(first_pos.items(), key=lambda x: x[1])
    span = {}
    for i, (iid, p) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else len(html)
        span[iid] = html[p:end]
    out = []
    for el in els:
        it = el.get("item") or {}
        url = it.get("url") or ""
        iid = url.rstrip("/").rsplit("/", 1)[-1]
        off = it.get("offers") or {}
        try:
            price = float(off.get("price") or 0)
        except ValueError:
            price = 0
        if not iid or price <= 0:
            continue
        ships = (_SHIP_ICON in span.get(iid, "")) if any_badge else None
        out.append({"id": iid, "title": it.get("name") or "", "price": price, "cur": off.get("priceCurrency") or "EUR",
                    "url": url, "image": it.get("image") or "", "brand": ((it.get("brand") or {}).get("name") or ""),
                    "new": "NewCondition" in str(it.get("itemCondition")), "text": it.get("description") or "",
                    "ships": ships})
    return out


def recommerce(source: str, queries: list[str], get) -> list:
    from markets import Listing
    host = RECOMMERCE[source][0]
    out = []
    for q in queries:
        try:
            html = get(f"https://{host}/recommerce/forsale/search", params={"q": q}).text
        except Exception as e:
            S.log(f"{source} {q}: {e}")
            continue
        for d in parse_recommerce(html):
            if d["ships"] is False:
                continue  # pickup only
            eur = round(d["price"] * FX.get(d["cur"], 0), 2)
            if eur <= 0:
                continue
            out.append(Listing(source=source, id=f"{source}-{d['id']}", title=d["title"], price=eur, url=d["url"],
                               image=d["image"], brand=d["brand"], size=title_size(d["title"]),
                               condition="Uusi" if d["new"] else "", text=d["text"],
                               extra={"orig": f"{d['price']:.0f} {d['cur']}", "ships": d["ships"]}))
        time.sleep(2.5)
    return out


# ---------------------------------------------------------------- Marktplaats / 2dehands
OK_PRICE = {"FIXED", "MIN_BID", "FAST_BID"}  # MIN_BID = "bieden vanaf": seller's floor, flagged in reasons
FASHION_VERTICAL = re.compile(r"cloth|shoe|bag|accessor|fashion|kleding|schoen|tassen|sieraden|watches", re.I)


def parse_lrp(j: dict, host: str):
    out = []
    for x in j.get("listings") or []:
        pi = x.get("priceInfo") or {}
        if pi.get("priceType") not in OK_PRICE or not pi.get("priceCents"):
            continue
        attrs = {a.get("key"): a.get("value") for a in (x.get("extendedAttributes") or x.get("attributes") or [])}
        delivery = (attrs.get("delivery") or "").lower()
        if delivery and "verzend" not in delivery:
            continue  # "Ophalen" = pickup only
        brand = next((v for k, v in attrs.items() if k and k.startswith("brand")), "") or ""
        size = next((v for k, v in attrs.items() if k and "size" in k), "") or ""
        vip = x.get("vipUrl") or ""
        url = f"https://{host}{vip}" if vip.startswith("/") else (vip or f"https://{host}/v/{x.get('itemId')}")
        pics = x.get("pictures") or []
        img = (pics[0].get("largeUrl") or pics[0].get("mediumUrl") or "") if pics else ""
        if not img and x.get("imageUrls"):
            img = "https:" + x["imageUrls"][0] if x["imageUrls"][0].startswith("//") else x["imageUrls"][0]
        out.append({"id": str(x.get("itemId")), "title": x.get("title") or "", "price": pi["priceCents"] / 100,
                    "ptype": pi.get("priceType"), "url": url, "image": img, "brand": brand, "size": str(size),
                    "condition": attrs.get("condition") or "", "text": x.get("description") or "",
                    "fashion": any(FASHION_VERTICAL.search(v or "") for v in (x.get("verticals") or [])),
                    "country": (x.get("location") or {}).get("countryName") or ""})
    return out


def _lrp_size(raw: str, title: str) -> str:
    v = raw.strip().upper()
    if re.fullmatch(r"X*[SML]|[2-4]XL|X+L", v):
        return f"MEN-INT-{v}"
    if v.isdigit() and 40 <= int(v) <= 64:
        return f"MEN-EU-{v}"
    return title_size(title)


def lrp(source: str, queries: list[str], get) -> list:
    from markets import Listing
    host = LRP[source][0]
    out = []
    for q in queries:
        try:
            j = get(f"https://{host}/lrp/api/search", params={"query": q, "limit": 50, "offset": 0,
                                                              "sortBy": "SORT_INDEX", "sortOrder": "DECREASING"}).json()
        except Exception as e:
            S.log(f"{source} {q}: {e}")
            continue
        for d in parse_lrp(j, host):
            out.append(Listing(source=source, id=f"{source}-{d['id']}", title=d["title"], price=d["price"], url=d["url"],
                               image=d["image"], brand=d["brand"], size=_lrp_size(d["size"], d["title"]),
                               condition=d["condition"], text=d["text"],
                               extra={"orig": f"{d['price']:.0f} EUR", "min_bid": d["ptype"] == "MIN_BID",
                                      "fashion": d["fashion"]}))
        time.sleep(2.5)
    return out


def fetch(source: str, queries: list[str], get) -> list:
    return recommerce(source, queries, get) if source in RECOMMERCE else lrp(source, queries, get)
