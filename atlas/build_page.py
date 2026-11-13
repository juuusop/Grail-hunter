"""Build the Grail Atlas site from the repo's scan data. Usage: python build_page.py REPO OUT.html [ATLAS_IMAGES_DIR]

The page is atlas_template.html (markup + styles) with atlas_app.js (the app) and the data JSON inlined.

Thumbnails go to sprite sheets next to the page (img/s0.jpg, img/s1.jpg, ... 10x10 tiles of 120 px), not into
the HTML: the artifact's CSP blocks remote images, and ~9000 inline base64 thumbs would pass the 16 MB page limit.
Publish them with the page: files={"img/sN.jpg": "<outdir>/img/sN.jpg", ...}.

Sharp pictures: pass a checkout of the repo's `atlas-images` branch (made by hires.py in Actions) as the
3rd argument or ATLAS_IMAGES; its 360 px WebP sheets are copied to <outdir>/hi/ and must be published too.
Usage: python build_page.py REPO OUT.html [ATLAS_IMAGES_DIR]"""
import base64
import io
import json
import os
import re
import sys
from datetime import datetime, timezone

import yaml
from PIL import Image

sys.path.insert(0, sys.argv[1])
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import sniper as S  # noqa: E402
from notes import NOTES, LANES  # noqa: E402
try:
    from picks import PICKS  # noqa: E402  {id: "kuraattorin kommentti"}
except ImportError:
    PICKS = {}

REPO, OUT = sys.argv[1], sys.argv[2]
HIDIR = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("ATLAS_IMAGES")

# ---- lanes from brands.yaml section comments
lane_of = {}
cur = "Muut"
for line in open(f"{REPO}/brands.yaml", encoding="utf-8"):
    m = re.match(r"\s*# -+ (.+?) -+", line)
    if m:
        t = m.group(1)
        cur = next((v for k, v in LANES if t.startswith(k)), t)
        continue
    m = re.match(r"\s*- \{name: (\"?)(.+?)\1,", line)
    if m:
        lane_of[m.group(2)] = cur

cfg = yaml.safe_load(open(f"{REPO}/config.yaml", encoding="utf-8"))
brands = yaml.safe_load(open(f"{REPO}/brands.yaml", encoding="utf-8"))["brands"]
resolved = json.load(open(f"{REPO}/data/brands_resolved.json", encoding="utf-8"))
scan = json.load(open(f"{REPO}/data/scan.json", encoding="utf-8"))
try:
    _m = json.load(open(f"{REPO}/data/markets_scan.json", encoding="utf-8"))
    mscan, _mgen = _m["items"], _m.get("generated")
except FileNotFoundError:
    mscan, _mgen = [], None
scan["items"] = scan["items"] + mscan
ms = float(cfg["settings"].get("min_score", 2.0))


CELL, GRID = 120, 10  # sprite tile size and tiles per row/column


def small(uri):
    """Square CELL-px PIL image from a data: URI thumbnail, or None."""
    if not uri:
        return None
    try:
        raw = base64.b64decode(uri.split(",", 1)[1])
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = im.size
        m = min(w, h)
        im = im.crop(((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m))
        return im.resize((CELL, CELL), Image.LANCZOS)
    except Exception:
        return None


def platform_size(it):
    """Market listings: size parsed from the title when the scan stored none (older rows)."""
    sz = it.get("size") or "-"
    if sz.strip() in ("", "-") and " · " in it["brand"]:
        try:
            import markets_eu
            sz = markets_eu.title_size(it.get("title") or "") or "-"
        except Exception:
            pass
    return sz


# ---- Sellpy's own category tree (Vaatteet > Housut ja farkut > Farkut), gender prefix dropped so men's and
# women's merge. Other platforms have no tree: their titles are matched to the same leaves (fi/sv/no/da/nl/en).
V, A, K = "Vaatteet", "Asusteet", "Kengät"
TITLE_TREE = [  # first match wins, so specific words come before generic ones
    (f"{V} > Housut ja farkut > Farkut", r"jeans|farkut|farkku|spijkerbroek|denim pant|selvedge"),
    (f"{V} > Housut ja farkut > Chinot", r"chinos?\b"),
    (f"{V} > Housut ja farkut > Puvunhousut", r"kostymbyxor|dressbukser|pantalon|suit trousers|puvunhousut|pressveck"),
    (f"{V} > Shortsit", r"shorts|shortsit|bermuda"),
    (f"{V} > Housut ja farkut > Housut", r"legging"),
    (f"{V} > Housut ja farkut > Housut", r"housut|byxor|bukser|broek|trousers|\bpants\b|cargo"),
    (f"{V} > Takit ja ulkoilutakit > Farkkutakit", r"farkkutakki|jeansjacka|denim jacket|jeansjakke"),
    (f"{V} > Takit ja ulkoilutakit > Toppatakit", r"untuva|toppatakki|dunjacka|dunjakke|donsjas|puffer|down jacket|parkas?\b"),
    (f"{V} > Takit ja ulkoilutakit > Päällystakit", r"päällystakki|kappa\b|\bcoat\b|\brock\b|kåpa|frakk|\bmantel|overcoat|trench|trenssi"),
    (f"{V} > Bleiserit ja puvut > Puvut", r"\bpuku\b|kostym\b|\bsuit\b|\bdress suit|\bpak\b"),
    (f"{V} > Bleiserit ja puvut > Bleiserit", r"blazer|kavaj|bleiseri|colbert|dressjakke|sportcoat"),
    (f"{V} > Villapaidat ja neuletakit > Neuletakit", r"cardigan|neuletakki|kofta"),
    (f"{V} > Villapaidat ja neuletakit > Hupparit ja collegepaidat", r"hoodie|huppari|huvtröja|hettegenser|sweatshirt|college|svetari|sweater hood"),
    (f"{V} > Villapaidat ja neuletakit > Neuleet", r"neule|villapaita|sweater|\bknit|stickad|tröja|genser|\btrui|pullover|jumper"),
    (f"{V} > Takit ja ulkoilutakit > Takit", r"takki|jacka|jakke|\bjas\b|jacket|anorak|bomber|shell|vindjacka"),
    (f"{V} > T-paidat ja hihattomat > Lyhythihaiset", r"t-?shirt|t-paita|t-tröja|\btee\b|t-skjorte"),
    (f"{V} > Paidat ja puserot > Paidat", r"kauluspaita|skjorta|skjorte|overhemd|\bshirt|\bpaita|polo|pikee|flanell"),
    (f"{V} > Yläosat", r"\btop\b|topje|tank ?top|toppi|linne|singlet"),
    (f"{V} > Mekot > Mekot", r"mekko|klänning|kjole\b|\bjurk|\bdress\b"),
    (f"{V} > Hameet", r"\bhame|kjol|skjørt|\brok\b|skirt"),
    (f"{K} > Saappaat", r"boots?\b|saappaat|saapas|kängor|känga|stövlar|støvler|laarzen|nilkkuri|chelsea"),
    (f"{K} > Sandaalit", r"sandaali|sandal|slides\b|tofflor"),
    (f"{K} > Juhlakengät", r"loafer|derby|oxford|brogue|pumps|juhlakengät|mocka sko"),
    (f"{K} > Tennarit", r"sneaker|tennari|lenkkari|trainer|runner|\bskor\b|\bsko\b|schoenen|kengät|kenkä|blazer low|dunk|samba"),
    (f"{A} > Laukut", r"laukku|väska|veske|tas\b|tassen\b|\bbag\b|reppu|ryggsäck|ryggsekk|rugzak|backpack|tote|olkalaukku|handbag"),
    (f"{A} > Lompakot ja korttikotelot", r"lompakko|pasjeshouder|plånbok|lommebok|wallet|portemonnee|card ?holder|korttikotelo|kortholder"),
    (f"{A} > Vyöt", r"\bvyö|bälte|belte\b|\bbelt\b|\briem\b"),
    (f"{A} > Lasit ja optiikka > Aurinkolasit", r"aurinkolasi|solglasögon|solbriller|sunglasses|zonnebril"),
    (f"{A} > Päähineet", r"pipo|mössa|lue\b|beanie|\bcap\b|lippis|keps|caps\b|hattu|\bhatt?\b|\bmuts\b|\bpet\b"),
    (f"{A} > Huivit ja kaulaliinat", r"huivi|kaulaliina|halsduk|skjerf|sjaal|scarf"),
    (f"{A} > Rannekellot", r"rannekello|\bkello\b|klocka|\bklokke|horloge|\bwatch\b"),
    (f"{A} > Korut", r"sormus|\bring\b|kaulakoru|halsband|necklace|armband|bracelet|rannekoru|örhängen|earring"),
    (f"{A} > Solmiot ja rusetit", r"solmio|\bslips|\btie\b|stropdas|rusetti|fluga"),
]
TITLE_TREE = [(p, re.compile(rx, re.I)) for p, rx in TITLE_TREE]


def cat_paths(it):
    """Deepest Sellpy category paths without the gender prefix, or a title-matched leaf for other platforms."""
    cats = it.get("categories") or {}
    for lvl in ("lvl3", "lvl2", "lvl1"):
        v = cats.get(lvl)
        if v:
            v = v if isinstance(v, list) else [v]
            out = []
            for x in v:
                p = " > ".join(x.split(" > ")[1:])
                if p and p not in out:
                    out.append(p)
            if out:
                return out
    t = it.get("title") or ""
    for p, rx in TITLE_TREE:
        if rx.search(t):
            return [p]
    return ["Muut"]


def lvl0(it):
    c = (it.get("categories") or {}).get("lvl0")
    if isinstance(c, list):
        c = c[0] if c else ""
    return c or ""


items = []
_ex = [S.norm(w) for w in cfg.get("exclude_words", [])]
_hq = {h["q"] for h in cfg.get("hunts", [])}
_coll = S.Evaluator(cfg, S.BrandMatcher(S.load_brands()), resolved, "fi").collisions
for it in scan["items"]:
    _t = S.norm((it.get("title") or "") + " " + (it.get("raw_brand") or ""))
    if any(S.has_word(_t, w) for w in _ex):
        continue
    if "(haku: " in it["brand"] and it["brand"].split("(haku: ", 1)[1].rstrip(")") not in _hq:
        continue
    _b0 = it["brand"].split(" · ")[0]
    if _b0 in _coll:
        old, med = _coll[_b0]
        it = {**it, "value": round(it["value"] * med * 3 / old), "score": round(it["score"] * med * 3 / old, 2)}
        if it["score"] < 1.4:
            continue
    if it["brand"] == "Claude Montana" and "claude" not in _t and "montana" in _t:
        continue
    base = it["brand"].split(" (haku")[0].split(" · ")[0]
    market = it["brand"].split(" · ", 1)[1] if " · " in it["brand"] else None
    if any(w in (it.get("title") or "") for w in ("Nännisuoja", "Osoitekirja")):
        continue
    if market:
        lane = "Muut alustat: " + market
    elif it["source"] == "haku":
        lane = "Kashmir & kangas" if ("kashmir" in it["brand"] or "loro piana" in it["brand"]) else "Väärin listatut"
    else:
        lane = lane_of.get(base, "Muut")
    why = []
    hq = it["brand"].split("(haku: ", 1)[1].rstrip(")") if "(haku: " in it["brand"] else None
    if hq:
        why.append(f"Löytyi tekstihaulla \"{hq}\", vaikka Sellpy listaa brändiksi {base or 'tuntemattoman'}. Avaa kuvat ja katso lappu.")
    if it["id"] in PICKS:
        why.append(PICKS[it["id"]])
    note = NOTES.get(base)
    if note:
        why.append(note)
    why += it.get("reasons") or []
    why += [w for w in (it.get("resale_why") or []) if w not in why]
    sz = platform_size(it)
    try:
        import risk as _R
        _rk = _R.for_dict({**it, "brand": base, "source": (market or "sellpy").lower()})
        why += [f"Riski: {w}" for w in _rk["why"] if w]
        rk = [_rk["fake"], _rk["fake_level"], _rk["cond"]]
    except Exception:
        rk = None
    items.append({
        "id": it["id"], "b": (f"{base} → {hq}" if hq else it["brand"]), "rb": it.get("raw_brand") or "", "t": it.get("title") or "",
        "p": it["price"], "v": it["value"], "s": it["score"], "l": it["label"], "c": it["category"],
        "sz": sz, "cd": it["condition"], "u": it["link"], "_th": it.get("thumb"),
        "pr": it.get("profit"), "rs": it.get("resale"), "ex": it.get("exit") or "",
        "lane": lane, "pf": (market or "Sellpy"), "g": lvl0(it), "o": it.get("country") or "", "why": why,
        "pick": it["id"] in PICKS, "fit": S.size_fits(sz, cfg["settings"].get("sizes")), "rare": "HARVINAINEN" in it["label"],
        "cp": cat_paths(it), "bn": (base or "Tuntematon"), "ts": int((it.get("saleStartedAt") or 0) / 1000) or int(it.get("ts") or 0), "rk": rk,
    })

# ---- sprite sheets, best finds first so the first screen needs one or two sheets
imgdir = os.path.join(os.path.dirname(os.path.abspath(OUT)), "img")
os.makedirs(imgdir, exist_ok=True)
for f in os.listdir(imgdir):
    if re.fullmatch(r"s\d+\.jpg", f):
        os.remove(os.path.join(imgdir, f))
withimg = []
for i in sorted(items, key=lambda i: -i["s"]):
    im = small(i.pop("_th"))
    if im is not None:
        withimg.append((i, im))
    i["im"] = None
sheets = 0
for k in range(0, len(withimg), GRID * GRID):
    sheet = Image.new("RGB", (CELL * GRID, CELL * GRID), (200, 204, 200))
    for n, (i, im) in enumerate(withimg[k:k + GRID * GRID]):
        sheet.paste(im, ((n % GRID) * CELL, (n // GRID) * CELL))
        i["im"] = [sheets, n]
    sheet.save(os.path.join(imgdir, f"s{sheets}.jpg"), "JPEG", quality=70, optimize=True, progressive=True)
    sheets += 1

# ---- sharp 360 px sheets from the atlas-images branch (lazy-loaded over the 120 px placeholder)
import shutil  # noqa: E402
hidir_out = os.path.join(os.path.dirname(os.path.abspath(OUT)), "hi")
shutil.rmtree(hidir_out, ignore_errors=True)
hi_meta, nhi = None, 0
if HIDIR and os.path.exists(os.path.join(HIDIR, "index.json")):
    hix = json.load(open(os.path.join(HIDIR, "index.json"), encoding="utf-8"))
    os.makedirs(hidir_out)
    used = set()
    for i in items:
        c = hix["items"].get(i["id"])
        i["hi"] = c
        if c:
            used.add(c[0])
            nhi += 1
    for n in used:
        shutil.copy(os.path.join(HIDIR, f"h{n}.webp"), hidir_out)
    hi_meta = {"grid": hix["grid"], "sheets": len(used)}
else:
    for i in items:
        i["hi"] = None

# ---- brand picker groups: the brand's style section in brands.yaml + resale tier from brand_guide.yaml
try:
    _guide = yaml.safe_load(open(f"{REPO}/brand_guide.yaml", encoding="utf-8")) or {}
except FileNotFoundError:
    _guide = {}
brand_groups = {}
for i in items:
    n = i["bn"]
    if n not in brand_groups:
        g = lane_of.get(n) or ("Väärin listatut" if "(haku" in i["b"] or " → " in i["b"] else "Muut")
        brand_groups[n] = [g, ((_guide.get(n) or {}).get("tier") or "")]

logic = []
for b in brands:
    st = resolved["brands"].get(b["name"], {})
    logic.append({
        "n": b["name"], "lane": lane_of.get(b["name"], "Muut"), "v": b["value"], "lim": round(b["value"] / ms),
        "r": bool(b.get("rare")), "mn": b.get("min_price"), "a": b.get("aliases") or [],
        "bo": b.get("boost") or {}, "cnt": st.get("count"), "med": st.get("median"),
        "sp": st.get("values") or [], "note": NOTES.get(b["name"], ""),
    })

meta = {
    "generated": datetime.fromtimestamp(scan["generated"], timezone.utc).strftime("%d.%m.%Y %H:%M UTC"),
    "n": len(items), "brands": len(brands), "found": len(resolved["brands"]),
    "min_score": ms, "scan_min": 1.4, "median_factor": cfg["settings"].get("sellpy_median_factor", 0.8),
    "categories": cfg["categories"], "conditions": cfg["conditions"], "gboost": cfg["global_boost"],
    "rare_words": cfg["rare_words"], "exclude": cfg["exclude_words"], "hunts": cfg["hunts"], "sizes": cfg["settings"].get("sizes") or {},
    "lanes": sorted({i["lane"] for i in items}),
    "markets_generated": (datetime.fromtimestamp(_mgen, timezone.utc).strftime("%d.%m.%Y %H:%M UTC") if _mgen else ""),
    "grid": GRID, "sheets": sheets, "hi": hi_meta, "bg": brand_groups,
    # brand guide (brand_guide.yaml): tier, hype/quality 1-5, fake 0-3 and the buying notes, for brand pages
    "gd": {n: {"t": g.get("tier") or "", "h": g.get("hype") or 0, "q": g.get("quality") or 0, "f": g.get("fake") or 0,
               **{k: g[k] for k in ("status", "good", "bad", "buy", "avoid", "tells") if g.get(k)},
               **({"kw": g["kw"]} if g.get("kw") else {})}
           for n, g in _guide.items() if isinstance(g, dict)},
}
data = json.dumps({"items": items, "logic": logic, "meta": meta}, ensure_ascii=False, separators=(",", ":"))
HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
tpl = open(HERE + "/atlas_template.html", encoding="utf-8").read()
app = open(HERE + "/atlas_app.js", encoding="utf-8").read()
data = data.replace("</", "<\\/")  # never close the <script> early
html = tpl.replace("/*__APP__*/", app)
open(OUT, "w", encoding="utf-8").write(html.replace("/*__DATA__*/null", data, 1))
print(OUT, len(items), "items", round(len(data) / 1e6, 2), "MB;", len(withimg), "thumbs in", sheets, "sprite sheets at", imgdir, ";", nhi, "sharp pictures in", (hi_meta or {}).get("sheets", 0), "sheets at", hidir_out)
