"""Probe round 2: page structure of public search pages (Tori, Tradera) and Emmy's public product feed.
No logins, tokens or bot-protection workarounds: only what a normal browser visit returns."""
import json, re, time
import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; grail-hunter/1.0; personal use)", "Accept-Language": "fi-FI,fi;q=0.9"}
out = {}


def probe(name, fn):
    try:
        out[name] = fn()
    except Exception as e:
        out[name] = {"error": repr(e)[:300]}
    time.sleep(2)


def ctx(text, word, n=3, w=400):
    return [text[max(0, m.start() - w):m.end() + w] for m in list(re.finditer(re.escape(word), text))[:n]]


def scripts(text):
    return [(m.group(1) or "")[:120] + f" len={len(m.group(2))}" for m in re.finditer(r"<script([^>]*)>(.*?)</script>", text, re.S)
            if len(m.group(2)) > 2000][:15]


def robots(host):
    return requests.get(f"https://{host}/robots.txt", headers=UA, timeout=20).text[:1500]


def tori():
    t = requests.get("https://www.tori.fi/recommerce/forsale/search?q=margiela&sort=PUBLISHED_DESC", headers=UA, timeout=20).text
    return {"robots": robots("www.tori.fi"), "scripts": scripts(t), "ctx": ctx(t, "Margiela", 3, 600)}


def tradera():
    t = requests.get("https://www.tradera.com/search?q=margiela&sortBy=AddedOn", headers=UA, timeout=20).text
    return {"robots": robots("www.tradera.com"), "scripts": scripts(t), "ctx": ctx(t, "itemId", 2, 600)}


def emmy():
    r = requests.get("https://emmy.fi/collections/all/products.json?limit=250&page=1&sort_by=created-descending", headers=UA, timeout=20)
    p = r.json().get("products", [])
    return {"robots": robots("emmy.fi"), "status": r.status_code, "n": len(p),
            "first": [(x["vendor"], x["title"], x["created_at"], x["variants"][0]["price"], x["handle"]) for x in p[:8]],
            "variant_keys": list(p[0]["variants"][0].keys()) if p else [], "tags": p[0]["tags"] if p else []}


def huuto():
    r = requests.get("https://api.huuto.net/1.1/items?words=rick+owens&sort=newest", headers=UA, timeout=20)
    j = r.json()
    return {"total": j.get("totalCount"), "item": (j.get("items") or [None])[0]}


for n, f in [("tori", tori), ("tradera", tradera), ("emmy", emmy), ("huuto", huuto)]:
    probe(n, f)
json.dump(out, open("data/probe.json", "w"), ensure_ascii=False, indent=1)
print("done")
