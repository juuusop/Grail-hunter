#!/usr/bin/env python3
"""One-off deep scans (no notifications, no change to the sniper's memory).

  python scan.py universe   every brand Sellpy has in men's/women's, grouped by
                            Sellpy's own brand groups + price points
                            -> data/brand_universe.json
  python scan.py deep       every listed item of every configured brand + text hunts,
                            scored with relaxed limits, with small thumbnails
                            -> data/scan.json
"""
from __future__ import annotations

import base64
import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import sniper as S

LVL0 = [["categories.lvl0:Miehet", "categories.lvl0:Naiset"]]


def universe(cfg):
    state = S.load_json(S.STATE_FILE, {})
    sp = S.Sellpy(cfg["settings"].get("market", "fi"), state)
    base = sp.queries([{"query": "", "hitsPerPage": 0, "facetFilters": LVL0,
                        "facets": ["brandGroups", S.BRAND_ATTR], "maxValuesPerFacet": 1000}])[0]
    groups = (base.get("facets") or {}).get("brandGroups", {})
    top_brands = (base.get("facets") or {}).get(S.BRAND_ATTR, {})
    S.log(f"universe: {len(groups)} brand groups, {len(top_brands)} top brands")
    names = list(groups)
    group_brands, brand_meta = {}, {}
    for i in range(0, len(names), 30):
        chunk = names[i:i + 30]
        res = sp.queries([{"query": "", "hitsPerPage": 200, "facetFilters": LVL0 + [[f"brandGroups:{g}"]],
                           "facets": [S.BRAND_ATTR], "maxValuesPerFacet": 1000,
                           "attributesToRetrieve": ["metadata.brand", "brandClassification", "brandGroups", "price_FI"],
                           "attributesToHighlight": []} for g in chunk])
        for g, r in zip(chunk, res):
            group_brands[g] = (r.get("facets") or {}).get(S.BRAND_ATTR, {})
            for h in r.get("hits", []):
                b = S.dig(h, "metadata.brand")
                bc = h.get("brandClassification") or {}
                if b and b not in brand_meta:
                    brand_meta[b] = {"pricePoint": bc.get("pricePoint"), "ethos": bc.get("ethos"),
                                     "tone": bc.get("aestheticTone"), "styles": bc.get("styles"),
                                     "groups": h.get("brandGroups")}
        time.sleep(1)
    # price point for the biggest brands we have not sampled yet
    missing = [b for b in list(top_brands)[:1000] if b not in brand_meta]
    for i in range(0, len(missing), 50):
        chunk = missing[i:i + 50]
        res = sp.queries([{"query": "", "hitsPerPage": 1, "facetFilters": [[f"{S.BRAND_ATTR}:{b}"]],
                           "attributesToRetrieve": ["brandClassification", "brandGroups"],
                           "attributesToHighlight": []} for b in chunk])
        for b, r in zip(chunk, res):
            h = (r.get("hits") or [{}])[0]
            bc = h.get("brandClassification") or {}
            brand_meta[b] = {"pricePoint": bc.get("pricePoint"), "ethos": bc.get("ethos"),
                             "tone": bc.get("aestheticTone"), "styles": bc.get("styles"),
                             "groups": h.get("brandGroups")}
        time.sleep(0.5)
    S.save_json(S.DATA / "brand_universe.json", {"generated": S.now_ts(), "groups": groups,
                                                "top_brands": top_brands, "group_brands": group_brands,
                                                "brand_meta": brand_meta})
    S.log(f"universe: {len(brand_meta)} brands with metadata")


def thumb(session, url):
    try:
        from PIL import Image
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            return None
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        w, h = im.size  # centre-crop to square: the Atlas shows square tiles
        m = min(w, h)
        im = im.crop(((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m))
        im.thumbnail((120, 120))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=55, optimize=True, progressive=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def deep(cfg):
    st = cfg["settings"]
    market = st.get("market", "fi")
    state = S.load_json(S.STATE_FILE, {})
    resolved = S.load_json(S.RESOLVED_FILE, None)
    if not resolved or resolved.get("brands_hash") != S.brands_hash():
        resolved = S.discover(cfg, state)
    sp = S.Sellpy(market, state)
    matcher = S.BrandMatcher(S.load_brands())
    # relaxed limits so "designer basics at a fair price" show up too
    relaxed = {**cfg, "settings": {**st, "min_score": float(st.get("scan_min_score", 1.4)),
                                   "sellpy_median_factor": float(st.get("scan_median_factor", 1.0))}}
    ev = S.Evaluator(relaxed, matcher, resolved, market)
    # Sellpy's search returns at most 1000 hits per query, so slice the catalogue until
    # every slice fits: brands are packed into groups of <=900 items, big brands are
    # split by price band, and any slice still over 1000 is halved again.
    lvl0 = [[f"categories.lvl0:{c}" for c in st.get("scan_lvl0", ["Miehet", "Naiset", "Muut tuotteet"])]]
    pa = f"{sp.price_attr}.amount"
    groups, cur, cur_n = [], [], 0
    for n, b in sorted(resolved["brands"].items(), key=lambda kv: kv[1].get("count", 0)):
        if n not in matcher.by_name or not b.get("values"):
            continue
        c = int(b.get("count") or 0)
        if c > 900:
            groups.append((b["values"], c))
            continue
        if cur_n + c > 900 or len(cur) + len(b["values"]) > 80:
            groups.append((cur, cur_n))
            cur, cur_n = [], 0
        cur += b["values"]
        cur_n += c
    if cur:
        groups.append((cur, cur_n))
    bands = [0, 800, 1200, 1600, 2000, 2500, 3000, 4000, 5000, 7000, 10000, 15000, 25000, 10 ** 8]
    pending = []
    for vals, c in groups:
        if c > 900:
            pending += [(vals, lo, hi) for lo, hi in zip(bands, bands[1:])]
        else:
            pending.append((vals, 0, 10 ** 8))
    keep = ["objectID", "metadata", sp.price_attr, "categories", "images", "keywords", "isReserved", "isForSale",
            "saleStartedAt", f"priceDrop_{market.upper()}", "brandClassification", "brandGroups", "title", "size"]
    hits, nq = [], 0
    while pending:
        batch, pending = pending[:8], pending[8:]
        res = sp.queries([{"query": "", "hitsPerPage": 1000, "facetFilters": lvl0 + [[f"{S.BRAND_ATTR}:{v}" for v in vals]],
                           "numericFilters": [f"{pa}>={max(lo, 1)}", f"{pa}<{hi}"], "attributesToRetrieve": keep,
                           "attributesToHighlight": [], "attributesToSnippet": []} for vals, lo, hi in batch])
        nq += len(batch)
        for (vals, lo, hi), r in zip(batch, res):
            if r.get("nbHits", 0) > 1000 and hi - lo > 50:
                mid = (lo + hi) // 2 if hi < 10 ** 7 else lo * 2
                pending += [(vals, lo, mid), (vals, mid, hi)]
            else:
                hits += [(h, None) for h in r.get("hits", [])]
        time.sleep(0.6)
    S.log(f"deep: {nq} slice queries, {len(hits)} brand hits")
    num = [f"{pa}>0"]
    hunts = cfg.get("hunts") or []
    res = sp.queries([{"query": h["q"], "hitsPerPage": 1000, "numericFilters": num, "facetFilters": lvl0,
                       "typoTolerance": "min"} for h in hunts])
    for h, r in zip(hunts, res):
        hits += [(x, h) for x in r.get("hits", [])]
    S.log(f"deep: {len(hits)} hits")

    out, seen = [], set()
    for hit, hunt in hits:
        oid = str(hit.get("objectID"))
        if oid in seen:
            continue
        f = ev.evaluate(hit, sp, hunt)
        if not f:
            continue
        seen.add(oid)
        md = hit.get("metadata") or {}
        d = f.to_dict()
        d.update({
            "raw_brand": S.first_str(md.get("brand")), "type": S.first_str(md.get("type")),
            "model": S.first_str(md.get("model")), "material": md.get("material") or md.get("fabric"),
            "color": md.get("color"), "demography": md.get("demography"), "season": md.get("season"),
            "country": md.get("countryOfOrigin"), "details": md.get("details"),
            "keywords": hit.get("keywords"), "categories": hit.get("categories"),
            "pricePoint": (hit.get("brandClassification") or {}).get("pricePoint"),
            "saleStartedAt": hit.get("saleStartedAt"), "priceDrop": hit.get("priceDrop_FI"),
            "images": (hit.get("images") or [])[:3],
        })
        out.append(d)
    out.sort(key=lambda d: -d["score"])
    S.log(f"deep: {len(out)} candidates in total")
    # every candidate gets a thumbnail: the Atlas can filter down to any of them,
    # and the artifact cannot load remote images (CSP), so a missing thumb = no picture
    nthumb = int(st.get("scan_thumbs") or len(out))
    S.log(f"deep: {len(out)} candidates, fetching thumbnails")
    with ThreadPoolExecutor(8) as pool:
        thumbs = list(pool.map(lambda d: thumb(sp.s, d["image"]), out[:nthumb]))
    thumbs += [None] * (len(out) - len(thumbs))
    for d, t in zip(out, thumbs):
        d["thumb"] = t
    S.save_json(S.DATA / "scan.json", {"generated": S.now_ts(), "items": out})
    S.log("deep: done")


if __name__ == "__main__":
    cfg = S.load_yaml("config.yaml")
    S.DATA.mkdir(exist_ok=True)
    {"universe": universe, "deep": deep}[sys.argv[1]](cfg)
