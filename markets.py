#!/usr/bin/env python3
"""Other second-hand marketplaces, scored with the same brand values and rules as the Sellpy sniper.

Sources (only public pages / public feeds, polite rate, robots.txt respected):
  emmy     emmy.fi public product feed (Shopify products.json), newest first
  tori     tori.fi search pages (schema.org data in the page), one brand query at a time
  huuto    huuto.net official public API
  tradera  tradera.com search pages (Sweden; check that the seller ships to Finland)

Usage: python markets.py run
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field

import requests

import sniper as S

STATE = S.DATA / "markets_state.json"
SCAN = S.DATA / "markets_scan.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; grail-hunter/1.0; personal use)", "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.7"}
SEK_EUR = 0.087
P2P = {"tori", "huuto", "tradera"}
APPAREL = ["takki", "jacket", "jacka", "parka", "anorakki", "bleiseri", "blazer", "kavaj", "kavaj", "liivi", "väst", "vest",
           "housut", "byxor", "pants", "trousers", "farkut", "jeans", "denim", "shortsit", "shorts", "cargo",
           "paita", "tröja", "skjorta", "shirt", "t-paita", "t-shirt", "tee", "huppari", "hoodie", "college", "sweatshirt",
           "neule", "neulepaita", "villapaita", "stickad", "knit", "cardigan", "neuletakki", "mekko", "klänning", "dress",
           "hame", "kjol", "skirt", "toppi", "topp", "top", "kengät", "skor", "shoes", "sneakers", "lenkkarit", "tennarit",
           "saappaat", "kängor", "stövlar", "boots", "derby", "loafer", "loaferit", "sandaalit", "sandaler", "sandals",
           "laukku", "väska", "bag", "reppu", "ryggsäck", "backpack", "olkalaukku", "lompakko", "plånbok", "wallet",
           "vyö", "bälte", "belt", "pipo", "mössa", "beanie", "lippis", "keps", "cap", "huivi", "halsduk", "scarf",
           "puku", "kostym", "suit", "haalari", "overall", "fleece", "untuvatakki", "dunjacka", "puffer", "kauluspaita",
           "geobasket", "ramones", "tabi", "runner", "trainer", "tossut"]
JUNK = ["beauty", "beaute", "beauté", "parfum", "parfums", "parfym", "hajuvesi", "tuoksu", "meikki", "smink", "huulipuna",
        "kynsilakka", "voide", "lotion", "blush", "puuteri", "necessär", "necessar", "sminkväska", "dustbag", "pölypussi",
        "kotelo", "rasia", "box", "laatikko", "kassi ostos", "paperikassi", "shopping bag", "kirja", "bok", "book", "lehti",
        "magazine", "rafzine", "vinyl", "lp", "dvd", "blu-ray", "city guide", "avaimenperä", "keychain", "nyckelring", "charm",
        "riipus", "tyyliset", "tyylinen", "tyylisen", "inspired", "kopio", "fake", "replika", "look alike", "lookalike",
        "sinivalolasit", "anti-blue", "antibluelight", "korvakorut", "kaulakoru", "sormus", "tarra", "sticker", "juliste",
        "poster", "kangaskassi ilmainen", "rpm", "7\"", "single"]
FLAG = {"emmy": "Emmy", "tori": "Tori", "huuto": "Huuto", "tradera": "Tradera 🇸🇪"}


@dataclass
class Listing:
    source: str
    id: str
    title: str
    price: float
    url: str
    image: str = ""
    brand: str = ""          # structured brand if the site has one
    size: str = ""
    condition: str = ""
    gender: str = ""
    text: str = ""
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------- brand finding in free text
class TextBrandFinder:
    """Finds a configured brand inside a free-text title (Tori/Huuto have no brand field)."""

    def __init__(self, brands: list[S.Brand]):
        pairs = []
        for b in brands:
            for a in [b.name, *b.aliases]:
                n = S.norm(a)
                if len(n) >= 3:
                    pairs.append((n, b))
        self.pairs = sorted(pairs, key=lambda p: -len(p[0]))

    def find(self, text: str) -> S.Brand | None:
        t = S.norm(text)
        for n, b in self.pairs:
            if S.has_word(t, n):
                return b
        return None


# ---------------------------------------------------------------- sources
def _get(url, **kw):
    r = requests.get(url, headers=UA, timeout=25, **kw)
    r.raise_for_status()
    return r


def emmy(state: dict, max_pages: int) -> list[Listing]:
    seen_top = state.get("emmy_top", 0)
    out, top = [], seen_top
    for page in range(1, max_pages + 1):
        prods = _get(f"https://emmy.fi/products.json?limit=250&page={page}").json().get("products", [])
        if not prods:
            break
        older = 0
        for p in prods:
            pid = int(p["id"])
            top = max(top, pid)
            if pid <= seen_top:
                older += 1
                continue
            tags = p.get("tags") or []
            tag = {}
            for t in tags:
                if ":" in t:
                    k, v = t.split(":", 1)
                    tag.setdefault(k, v)
            if tag.get("agegroup", "Adults") != "Adults" or "instock" not in tags:
                continue
            v0 = (p.get("variants") or [{}])[0]
            if not v0.get("available", True):
                continue
            gender = tag.get("gender", "")
            size = ""
            if tag.get("sizeshoes"):
                size = f"SHOES-EU-{tag['sizeshoes']}"
            elif tag.get("sizeinlabel"):
                lab = tag["sizeinlabel"].upper()
                if re.fullmatch(r"X*[SML]|X*L|\dXL", lab):
                    size = f"{'WMN' if gender == 'Naiset' else 'MEN'}-INT-{lab}"
                elif gender == "Naiset" and tag.get("sizewomen", "").isdigit():
                    size = f"WMN-EU-{tag['sizewomen']}"
                elif gender == "Miehet" and tag.get("sizemen", "").isdigit():
                    size = f"MEN-EU-{tag['sizemen']}"
            imgs = p.get("images") or []
            out.append(Listing(
                source="emmy", id=f"emmy-{pid}", title=f"{p.get('vendor', '')} {p.get('title', '')}".strip(),
                price=float(v0.get("price") or 0), url=f"https://emmy.fi/products/{p['handle']}",
                image=imgs[0]["src"] if imgs else "", brand=p.get("vendor", ""), size=size,
                condition=tag.get("eecondition", ""), gender=gender,
                text=" ".join([p.get("product_type", ""), re.sub("<[^>]+>", " ", p.get("body_html") or "")[:600],
                               tag.get("item_fi", ""), tag.get("eemaincategory", "")])))
        if older == len(prods):
            break
        time.sleep(2)
    state["emmy_top"] = top
    return out


def _rotation(state: dict, key: str, queries: list[str], n: int) -> list[str]:
    i = state.get(key, 0) % max(1, len(queries))
    pick = (queries[i:] + queries[:i])[:n]
    state[key] = i + n
    return pick


def tori(state: dict, queries: list[str], n: int) -> list[Listing]:
    out = []
    for q in _rotation(state, "tori_i", queries, n):
        try:
            t = _get("https://www.tori.fi/recommerce/forsale/search", params={"q": q}).text
        except Exception as e:
            S.log(f"tori {q}: {e}")
            continue
        m = re.search(r'<script type="application/ld\+json" id="seoStructuredData">(.*?)</script>', t, re.S)
        if not m:
            continue
        try:
            items = json.loads(m.group(1)).get("mainEntity", {}).get("itemListElement", [])
        except ValueError:
            continue
        for el in items:
            it = el.get("item") or {}
            url = it.get("url") or ""
            iid = url.rstrip("/").rsplit("/", 1)[-1]
            try:
                price = float((it.get("offers") or {}).get("price") or 0)
            except ValueError:
                price = 0
            if not iid or price <= 0:
                continue
            cond = "Uusi" if "NewCondition" in str(it.get("itemCondition")) else ""
            out.append(Listing(source="tori", id=f"tori-{iid}", title=it.get("name") or "", price=price, url=url,
                               image=it.get("image") or "", condition=cond, text=it.get("description") or ""))
        time.sleep(2.5)
    return out


def huuto(state: dict, queries: list[str], n: int) -> list[Listing]:
    out = []
    for q in _rotation(state, "huuto_i", queries, n):
        try:
            j = _get("https://api.huuto.net/1.1/items", params={"words": q, "sort": "newest", "status": "open"}).json()
        except Exception as e:
            S.log(f"huuto {q}: {e}")
            continue
        for it in j.get("items") or []:
            bn = it.get("buyNowPrice") or 0
            cur = it.get("currentPrice") or 0
            price = float(bn or cur or 0)
            if price <= 0:
                continue
            imgs = it.get("images") or []
            img = ((imgs[0].get("links") or {}).get("medium")) if imgs else ""
            auction = it.get("saleMethod") != "buy-now"
            out.append(Listing(source="huuto", id=f"huuto-{it['id']}", title=it.get("title") or "", price=price,
                               url=(it.get("links") or {}).get("alternative") or "", image=img or "",
                               text=it.get("category") or "",
                               extra={"auction": auction and not bn, "closes": it.get("closingTime")}))
        time.sleep(1.5)
    return out


TRADERA_ITEM = re.compile(r'"itemId":(\d+),"price":(\d+),"shortDescription":"((?:[^"\\]|\\.)*)",'
                          r'"imageUrlTemplate":"([^"]*)".*?"itemUrl":"([^"]*)","itemType":"(\w+)"(.*?)"isActive"', re.S)


def tradera(state: dict, queries: list[str], n: int) -> list[Listing]:
    out = []
    for q in _rotation(state, "tradera_i", queries, n):
        try:
            t = _get("https://www.tradera.com/search", params={"q": q}).text
        except Exception as e:
            S.log(f"tradera {q}: {e}")
            continue
        t = t.replace('\\"', '"').replace("\\\\", "\\")
        for m in TRADERA_ITEM.finditer(t):
            iid, price, desc, img, url, typ, rest = m.groups()
            bn = re.search(r'"buyNowPrice":(\d+)', rest)
            sek = float(bn.group(1)) if bn and int(bn.group(1)) > 0 else float(price)
            if typ == "Auction" and not (bn and int(bn.group(1)) > 0):
                continue  # pure auctions: the current bid is not the real price
            try:
                desc = json.loads(f'"{desc}"')
            except ValueError:
                pass
            out.append(Listing(source="tradera", id=f"tradera-{iid}", title=desc, price=round(sek * SEK_EUR, 2),
                               url=url, image=img.replace("{format}", "images"), extra={"sek": sek}))
        time.sleep(2.5)
    return out


# ---------------------------------------------------------------- scoring
class _PriceOnly:
    def price(self, hit):
        return hit["_price"]


def to_hit(L: Listing, brand_name: str) -> dict:
    return {"objectID": L.id, "_price": L.price, "title": L.title, "images": [L.image] if L.image else [],
            "metadata": {"brand": brand_name, "type": L.title, "size": L.size, "condition": L.condition},
            "categories": {"lvl0": L.gender}, "description": L.text}


def run(cfg: dict):
    st = cfg["settings"]
    mk = cfg.get("markets") or {}
    state = S.load_json(STATE, {})
    first = not state.get("seen")
    seen = state.setdefault("seen", {})
    brands = S.load_brands()
    matcher = S.BrandMatcher(brands)
    finder = TextBrandFinder(brands)
    resolved = S.load_json(S.RESOLVED_FILE, {"brands": {}})
    ev = S.Evaluator(cfg, matcher, resolved, "fi")
    sp = _PriceOnly()

    # queries: brands worth a free-text search (valuable or rare), most valuable first
    qmin = float(mk.get("query_min_value", 150))
    queries = [b.name for b in sorted(brands, key=lambda b: -b.value) if b.value >= qmin or b.rare]
    listings: list[Listing] = []
    plan = [("emmy", lambda: emmy(state, int(mk.get("emmy_pages", 6)))),
            ("tori", lambda: tori(state, queries, int(mk.get("tori_queries", 20)))),
            ("huuto", lambda: huuto(state, queries, int(mk.get("huuto_queries", 25)))),
            ("tradera", lambda: tradera(state, queries, int(mk.get("tradera_queries", 12))))]
    for name, fn in plan:
        if name not in (mk.get("sources") or ["emmy", "tori", "huuto", "tradera"]):
            continue
        try:
            got = fn()
        except Exception as e:
            S.log(f"{name}: failed {e!r}")
            got = []
        S.log(f"{name}: {len(got)} listings")
        listings += got

    fake_risk = {S.norm(x) for x in (mk.get("fake_risk") or [])}
    block = [S.norm(x) for x in (mk.get("text_block") or [])]
    found = []
    for L in listings:
        b = matcher.match(L.brand) if L.brand else None
        if b is None:
            b = finder.find(L.title)
        if b is None:
            continue
        t = S.norm(L.title + " " + L.text)
        if any(x in t for x in block):
            continue
        if L.source in P2P:
            if any(S.has_word(t, w) for w in JUNK):
                continue
            if not any(S.has_word(t, w) for w in APPAREL):
                continue
            # cheap "luxury" from private sellers is almost always fake
            if S.norm(b.name) in fake_risk and L.price < float(mk.get("fake_risk_floor", 0.3)) * b.value:
                continue
        ev.buy_source = L.source
        f = ev.evaluate(to_hit(L, b.name), sp)
        if not f:
            continue
        f.link, f.image, f.source = L.url, L.image or f.image, L.source
        f.title = L.title
        f.brand = f"{f.brand} · {FLAG[L.source]}"
        if L.extra.get("auction"):
            f.reasons.append("huutokauppa: hinta voi vielä nousta")
        if L.source == "tradera":
            f.reasons.append(f"{L.extra['sek']:.0f} SEK, Ruotsi: tarkista toimitus Suomeen")
        found.append(f)

    new = [f for f in found if f.id not in seen]
    for f in found:
        seen[f.id] = S.now_ts()
    cutoff = S.now_ts() - 30 * 86400
    state["seen"] = {k: v for k, v in seen.items() if v >= cutoff}

    scan = S.load_json(SCAN, {"items": []})
    keep = {d["id"]: d for d in scan.get("items", []) if d.get("ts", 0) >= cutoff}
    from scan import thumb
    for f in found:
        old = keep.get(f.id, {})
        d = {**old, **f.to_dict()}
        if not d.get("thumb") and f.image:
            d["thumb"] = thumb(requests.Session(), f.image)
        keep[f.id] = d
    S.save_json(SCAN, {"generated": S.now_ts(), "items": sorted(keep.values(), key=lambda d: -d["score"])[:3000]})

    if new:
        finds = S.load_json(S.FINDS_FILE, [])
        S.save_json(S.FINDS_FILE, ([n.to_dict() for n in new] + finds)[:1500])
        S.write_finds_md(S.load_json(S.FINDS_FILE, []))
        nstate = S.load_json(S.STATE_FILE, {})
        notifier = S.GitHubNotifier(st.get("notify_issue_title", "🦅 Löydöt"), nstate)
        if first:
            top = sorted(new, key=lambda f: -f.score)[:15]
            notifier.send(f"### 🌍 Muut alustat mukana: {len(new)} löytöä ensimmäisellä kierroksella, top {len(top)}", top)
        else:
            import resale
            notifier.send(f"### 🌍 {len(new)} uutta muilta alustoilta", sorted(new, key=resale.rank_key)[:30])
    S.save_json(STATE, state)
    S.log(f"markets: {len(listings)} listings, {len(found)} deals, {len(new)} new")


if __name__ == "__main__":
    S.DATA.mkdir(exist_ok=True)
    {"run": run}[sys.argv[1] if len(sys.argv) > 1 else "run"](S.load_yaml("config.yaml"))
