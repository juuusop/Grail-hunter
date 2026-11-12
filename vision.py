#!/usr/bin/env python3
"""Mislisted-item hunter: finds designer pieces Sellpy listed under the wrong brand.

Three-stage funnel, cheapest first:
  1. text signals (free)    newest men's/women's items whose brand is unknown/cheap but whose
                            data says quality: leather, cashmere, made in Italy/Japan, boots ...
  2. image match (free)     CLIP embeddings on CPU; compare against a gallery of correctly
                            listed grail-brand items + text prompts of signature pieces
  3. label check (cents)    Claude Haiku looks at all photos (Sellpy shoots the label) of the
                            top few and reads the real brand. Only runs if ANTHROPIC_API_KEY is set.

  python vision.py gallery   rebuild data/gallery.npz (weekly)
  python vision.py run       one pass (hourly)
"""
from __future__ import annotations

import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import sniper as S

VSTATE = S.DATA / "vision_state.json"
GALLERY = S.DATA / "gallery.npz"
LVL0 = [["categories.lvl0:Miehet", "categories.lvl0:Naiset"]]

# brands whose correctly listed items make up the reference gallery
GALLERY_BRANDS = [
    "Rick Owens", "Maison Margiela", "Guidi", "Carol Christian Poell", "Boris Bidjan Saberi",
    "Yohji Yamamoto", "Comme des Garçons", "Comme des Garçons Homme Plus", "Junya Watanabe",
    "Issey Miyake", "Homme Plissé Issey Miyake", "Ann Demeulemeester", "Raf Simons", "Helmut Lang",
    "Number (N)ine", "Undercover", "Kapital", "Visvim", "Julius_7", "Jean Paul Gaultier",
    "Vivienne Westwood", "Dries Van Noten", "Stone Island", "C.P. Company", "Arc'teryx", "Acronym",
    "Prada", "Burberry", "Barbour", "Max Mara", "Loro Piana", "Brunello Cucinelli", "Hermès",
    "Chrome Hearts", "Paraboot", "Alden", "Our Legacy", "Lemaire", "Needles", "Carhartt",
]
PROMPTS = {
    "Maison Margiela": ["a photo of split-toe tabi boots", "a photo of tabi ankle boots with a split toe"],
    "Rick Owens": ["a photo of Rick Owens geobasket high top sneakers", "an asymmetric black leather biker jacket, avant-garde",
                   "long draped black avant-garde tunic"],
    "Guidi": ["a photo of wrinkled horse leather back zip boots", "object dyed cracked leather boots"],
    "Carol Christian Poell": ["object dyed leather jacket with drip rubber details"],
    "Yohji Yamamoto": ["a long black draped wool coat, japanese avant-garde"],
    "Issey Miyake": ["a photo of pleated trousers, issey miyake homme plisse pleats"],
    "Kapital": ["a boro patchwork indigo jacket with sashiko stitching"],
    "Comme des Garçons": ["a deconstructed asymmetric blazer, comme des garcons"],
    "Burberry": ["a vintage beige trench coat with check lining"],
    "Barbour": ["a waxed cotton jacket with corduroy collar"],
    "Carhartt": ["a vintage brown duck canvas work jacket with corduroy collar"],
    "Stone Island": ["a jacket with a compass badge patch on the sleeve"],
    "Jean Paul Gaultier": ["a mesh top with tattoo print"],
}
QUALITY_WORDS = ["nahka", "nahkaa", "leather", "hevosennahka", "horse", "kashmir", "cashmere", "silkki", "silk",
                 "villa", "wool", "merino", "alpakka", "mohair", "pellava", "linen", "mokka", "suede"]
SHAPE_WORDS = ["asymmetrinen", "drapeerattu", "avantgarde", "avant", "gootti", "raakareuna", "raw", "kerroksellinen",
               "dekonstruoitu", "oversized", "pitkä", "laskostettu", "plisseerattu", "back zip", "vetoketju takana"]
TYPE_WORDS = ["saappaat", "nilkkurit", "nahkatakki", "bleiseri", "villakangastakki", "takki", "trenssi", "kengät",
              "mokkasiinit", "derbyt", "laukku", "neuletakki"]
GOOD_ORIGIN = {"IT": 2.0, "JP": 2.5, "BE": 2.0, "FR": 1.2, "GB": 1.2, "PT": 0.6, "US": 0.8, "CA": 0.8, "ES": 0.4}


# ---------------------------------------------------------------- helpers
def clip_models():
    from fastembed import ImageEmbedding, TextEmbedding
    return (ImageEmbedding(model_name="Qdrant/clip-ViT-B-32-vision"),
            TextEmbedding(model_name="Qdrant/clip-ViT-B-32-text"))


def fetch_images(session, urls):
    from PIL import Image

    def one(u):
        try:
            r = session.get(u, timeout=15)
            if r.status_code == 200:
                im = Image.open(io.BytesIO(r.content)).convert("RGB")
                im.thumbnail((336, 336))
                return im
        except Exception:
            return None
        return None
    with ThreadPoolExecutor(12) as pool:
        return list(pool.map(one, urls))


def unit(a):
    a = np.asarray(a, dtype=np.float32)
    return a / (np.linalg.norm(a, axis=-1, keepdims=True) + 1e-8)


def text_signal(hit) -> tuple[float, list[str]]:
    md = hit.get("metadata") or {}
    text = S.norm(" ".join(S.flatten_text([md, hit.get("keywords"), hit.get("style")])))
    score, why = 0.0, []
    q = [w for w in QUALITY_WORDS if S.has_word(text, w)]
    if q:
        score += 1.5 + 0.5 * (len(q) - 1)
        why.append("materiaali: " + ", ".join(q[:3]))
    sh = [w for w in SHAPE_WORDS if S.has_word(text, w)]
    if sh:
        score += 1.0 * len(sh[:2])
        why.append("muoto: " + ", ".join(sh[:2]))
    ty = [w for w in TYPE_WORDS if S.has_word(text, w)]
    if ty:
        score += 0.8
    origin = str(md.get("countryOfOrigin") or "").upper()
    if origin in GOOD_ORIGIN:
        score += GOOD_ORIGIN[origin]
        why.append(f"valmistettu: {origin}")
    pp = (hit.get("brandClassification") or {}).get("pricePoint")
    raw_brand = S.norm(S.first_str(md.get("brand")))
    if not raw_brand or raw_brand in ("tuntematon", "okand", "unknown", "no brand", "merkiton"):
        score += 1.0
        why.append("brändi tuntematon")
    elif pp is not None and pp <= 3 and (q or origin in ("IT", "JP", "BE")):
        score += 1.0
        why.append(f"Sellpyn hintaluokka {pp}/6 mutta laatusignaaleja")
    return score, why


# ---------------------------------------------------------------- gallery
def build_gallery(cfg):
    state = S.load_json(S.STATE_FILE, {})
    sp = S.Sellpy(cfg["settings"].get("market", "fi"), state)
    resolved = S.load_json(S.RESOLVED_FILE, None) or S.discover(cfg, state)
    reqs, names = [], []
    for b in GALLERY_BRANDS:
        vals = (resolved["brands"].get(b) or {}).get("values")
        if vals:
            names.append(b)
            reqs.append({"query": "", "hitsPerPage": 50, "facetFilters": LVL0 + [[f"{S.BRAND_ATTR}:{v}" for v in vals]],
                         "numericFilters": [f"{sp.price_attr}.amount>2000"],  # >20 €: real pieces, not keyrings
                         "attributesToRetrieve": ["images", "metadata.type"], "attributesToHighlight": []})
    urls, labels = [], []
    for i in range(0, len(reqs), 20):
        for b, r in zip(names[i:i + 20], sp.queries(reqs[i:i + 20])):
            for h in r.get("hits", []):
                if h.get("images"):
                    urls.append(h["images"][0])
                    labels.append(b)
    S.log(f"gallery: {len(urls)} reference photos from {len(names)} brands")
    imgs = fetch_images(sp.s, urls)
    keep = [(im, lab) for im, lab in zip(imgs, labels) if im is not None]
    img_model, txt_model = clip_models()
    emb = unit(list(img_model.embed([k[0] for k in keep], batch_size=32)))
    p_labels, p_texts = [], []
    for b, ps in PROMPTS.items():
        for p in ps:
            p_labels.append(b)
            p_texts.append(p)
    pemb = unit(list(txt_model.embed(p_texts)))
    np.savez_compressed(GALLERY, emb=emb.astype(np.float16), labels=np.array([k[1] for k in keep]),
                        pemb=pemb.astype(np.float16), plabels=np.array(p_labels), ptexts=np.array(p_texts))
    S.log(f"gallery: saved {len(keep)} photos + {len(p_texts)} prompts")


# ---------------------------------------------------------------- Claude label check
LABEL_PROMPT = """Kuvat ovat yhdestä Sellpy-myynti-ilmoituksesta. Sellpy on listannut brändiksi: "{brand}".
Tyyppi: {type}. Hinta: {price} €. Kuvavertailu muistuttaa brändiä: {guess}.

Katso erityisesti merkkilappu- ja hoito-ohjelappukuvat. Vastaa VAIN JSON-objektilla:
{{"label_brand": "lapussa lukeva brändi tai null", "is_designer": true/false,
  "designer": "todennäköinen designer-brändi tai null", "confidence": 0-1,
  "resale_eur": "arvioitu jälleenmyyntihinta euroina (numero) tai null",
  "fake_signs": "näkyvät väärennöksen merkit (lapun fontti/ompeleet, logo, laatu) lyhyesti tai null",
  "defects": "näkyvät viat (tahrat, reiät, nyppyyntyminen, kuluneet pohjat/kulmat) lyhyesti tai null",
  "reason": "yksi lyhyt lause suomeksi"}}"""


def claude_check(item):
    import anthropic
    client = anthropic.Anthropic()
    content = [{"type": "image", "source": {"type": "url", "url": u}} for u in item["images"][:6]]
    content.append({"type": "text", "text": LABEL_PROMPT.format(
        brand=item["raw_brand"] or "tuntematon", type=item["type"], price=item["price"], guess=item["clip_guess"])})
    try:
        resp = client.messages.create(model="claude-haiku-5-5", max_tokens=400,
                                      output_config={"effort": "low"},
                                      messages=[{"role": "user", "content": content}])
    except anthropic.APIStatusError as e:
        S.log(f"claude: {e.status_code} {e.message[:120]}")
        return None
    except anthropic.APIConnectionError:
        return None
    if resp.stop_reason == "refusal":
        return None
    txt = "".join(b.text for b in resp.content if b.type == "text")
    try:
        return json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
    except ValueError:
        return None


# ---------------------------------------------------------------- run
def run(cfg):
    st = cfg["settings"]
    market = st.get("market", "fi")
    vs = S.load_json(VSTATE, {"seen": {}})
    state = S.load_json(S.STATE_FILE, {})
    sp = S.Sellpy(market, state)
    matcher = S.BrandMatcher(S.load_brands())
    if not GALLERY.exists():
        build_gallery(cfg)
    g = np.load(GALLERY)
    gemb, glab = g["emb"].astype(np.float32), g["labels"]
    pemb, plab = g["pemb"].astype(np.float32), g["plabels"]

    # 1) newest items, text funnel
    max_price = float(st.get("vision_max_price", 80))
    cands = []
    for page in range(int(st.get("vision_pages", 6))):
        r = sp.queries([{"query": "", "hitsPerPage": 1000, "page": page, "facetFilters": LVL0,
                         "numericFilters": [f"{sp.price_attr}.amount>0", f"{sp.price_attr}.amount<={int(max_price * 100)}"],
                         "attributesToHighlight": [], "attributesToSnippet": []}])[0]
        hs = r.get("hits", [])
        new = 0
        for h in hs:
            oid = str(h.get("objectID"))
            if oid in vs["seen"]:
                continue
            new += 1
            vs["seen"][oid] = S.now_ts()
            if matcher.match(S.dig(h, S.BRAND_ATTR)) or not h.get("images") or h.get("isReserved"):
                continue
            if S.norm(S.first_str(S.dig(h, "metadata.size"))).startswith("child") or not S.size_fits(S.first_str(S.dig(h, "metadata.size")), st.get("sizes")):
                continue
            sc, why = text_signal(h)
            if sc >= float(st.get("vision_text_min", 2.5)):
                cands.append((sc, why, h))
        if new == 0 or len(hs) < 1000:
            break
    cands.sort(key=lambda c: -c[0])
    cands = cands[:int(st.get("vision_max_candidates", 250))]
    S.log(f"vision: {len(cands)} candidates after text funnel")

    # 2) CLIP
    found = []
    if cands:
        imgs = fetch_images(sp.s, [c[2]["images"][0] for c in cands])
        ok = [(c, im) for c, im in zip(cands, imgs) if im is not None]
        img_model, _ = clip_models()
        emb = unit(list(img_model.embed([im for _, im in ok], batch_size=32)))
        # Raw CLIP similarities are ~0.95 for any product photo, so centre each gallery
        # image / prompt column on this batch: what counts is looking MORE like a grail
        # brand than the other candidates do.
        sims = emb @ gemb.T
        psims = emb @ pemb.T
        sims = sims - sims.mean(axis=0, keepdims=True)
        psims = psims - psims.mean(axis=0, keepdims=True)
        vstd = float(np.std(sims.max(axis=1))) or 1.0
        pstd = float(np.std(psims.max(axis=1))) or 1.0
        for (sc, why, h), srow, prow in zip([c for c, _ in ok], sims, psims):
            top = np.argsort(-srow)[:7]
            votes = {}
            for t in top:
                votes[glab[t]] = votes.get(glab[t], 0) + float(srow[t])
            guess, vote = max(votes.items(), key=lambda kv: kv[1])
            pbest = int(np.argmax(prow))
            visual = float(srow[top[0]])
            prompt_hit = float(prow[pbest])
            combined = sc * 0.15 + visual / vstd * 0.6 + prompt_hit / pstd * 0.6
            md = h.get("metadata") or {}
            found.append({
                "id": str(h["objectID"]), "raw_brand": S.first_str(md.get("brand")), "type": S.first_str(md.get("type")),
                "price": sp.price(h), "images": h.get("images", []), "text_score": round(sc, 2), "why": why,
                "clip_guess": guess, "clip_sim": round(visual, 3), "prompt": str(plab[pbest]),
                "prompt_sim": round(prompt_hit, 3), "combined": round(combined, 2),
                "link": f"https://www.sellpy.{market}/item/{h['objectID']}",
                "size": S.first_str(md.get("size")), "condition": S.first_str(md.get("condition")),
            })
    found.sort(key=lambda f: -f["combined"])

    # 3) Claude label check for the top few
    alerts = []
    use_claude = bool(os.getenv("ANTHROPIC_API_KEY"))
    for f in found[:int(st.get("vision_claude_top", 15))]:
        if use_claude:
            v = claude_check(f)
            f["claude"] = v
            if not v:
                continue
            try:
                resale = float(v.get("resale_eur") or 0)
            except (TypeError, ValueError):
                resale = 0.0
            if v.get("is_designer") and float(v.get("confidence") or 0) >= 0.6 and resale >= 2 * f["price"]:
                alerts.append((f, v, resale))
        elif f["combined"] >= float(st.get("vision_clip_alert", 99)):
            alerts.append((f, None, 0.0))

    hist = S.load_json(S.DATA / "vision_candidates.json", [])
    S.save_json(S.DATA / "vision_candidates.json", (found[:60] + hist)[:400])

    finds = S.load_json(S.FINDS_FILE, [])
    new_finds = []
    for f, v, resale in alerts:
        brand = (v or {}).get("label_brand") or (v or {}).get("designer") or f["clip_guess"]
        reasons = f["why"] + [f"kuva muistuttaa: {f['clip_guess']} ({f['clip_sim']})"]
        if v:
            reasons.insert(0, f"Claude: {v.get('reason', '')}")
            if v.get("fake_signs"):
                reasons.insert(1, f"⚠️ feikkimerkit kuvissa: {v['fake_signs']}")
            if v.get("defects"):
                reasons.insert(1, f"🩹 viat kuvissa: {v['defects']}")
        nf = S.Find(id=f["id"], brand=f"{brand} (Sellpy: {f['raw_brand'] or '-'})", title=f["type"], price=f["price"],
                    value=round(resale) if resale else 0, score=round(resale / f["price"], 2) if resale else f["combined"],
                    label="🔎 VÄÄRIN LISTATTU" if v else "🔎 KUVAEHDOKAS", category=f["type"] or "-",
                    condition=f["condition"] or "-", size=f["size"] or "-", link=f["link"], image=f["images"][0],
                    reasons=reasons, source="kuva", ts=S.now_ts())
        new_finds.append(nf)
    if new_finds:
        S.save_json(S.FINDS_FILE, ([n.to_dict() for n in new_finds] + finds)[:1500])
        S.write_finds_md(S.load_json(S.FINDS_FILE, []))
        S.GitHubNotifier(st.get("notify_issue_title", "🦅 Löydöt"), state).send(
            f"### 🔎 {len(new_finds)} mahdollisesti väärin listattua", new_finds)
        S.save_json(S.STATE_FILE, state)
    cutoff = S.now_ts() - 14 * 86400
    vs["seen"] = {k: t for k, t in vs["seen"].items() if t >= cutoff}
    S.save_json(VSTATE, vs)
    S.log(f"vision: {len(found)} image-checked, {len(alerts)} alerts, claude={'on' if use_claude else 'off'}")


if __name__ == "__main__":
    cfg = S.load_yaml("config.yaml")
    S.DATA.mkdir(exist_ok=True)
    {"gallery": build_gallery, "run": run}[sys.argv[1] if len(sys.argv) > 1 else "run"](cfg)

