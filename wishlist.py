#!/usr/bin/env python3
"""Wishlist finder: any second-hand item, not only designer fashion.

jp adds an item by commenting on the issue "🛒 Toivelista" (or by editing wishlist.yaml). Every run searches
Tori, Huuto.net, Tradera and Blocket for each item, keeps listings whose text contains every word of one of the
item's queries, drops excluded words and anything over max_price, and comments new matches back on the same
issue with the numbers behind them (price vs new, vs the median of the other used ones found right now).

Comment format (one item per comment; lines in any order):
    twelve south curve, läppäriteline, laptop stand     <- first line: searches, comma separated (1st = name)
    max 60                                             <- optional: alert only at or under 60 €
    uusi 98                                            <- optional: new price, for the savings figure
    -ipad, -tabletti                                   <- optional: words that reject a listing
A comment "pois <name or first search>" removes an item.

Usage: python wishlist.py run
"""
from __future__ import annotations

import json
import os
import re
import statistics
import sys
import time

import requests

import markets as M
import markets_eu as EU
import sniper as S

STATE = S.DATA / "wishlist_state.json"
SCAN = S.DATA / "wishlist_scan.json"
MD = S.ROOT / "WISHLIST.md"
ISSUE_TITLE = "🛒 Toivelista"
ALL_SOURCES = ["tori", "huuto", "tradera", "blocket"]
FLAG = {"tori": "Tori", "huuto": "Huuto", "tradera": "Tradera 🇸🇪", "blocket": "Blocket 🇸🇪"}
SHIP = {"tradera": 15, "blocket": 15}  # small parcel from Sweden, EUR (estimate)
ISSUE_BODY = """Kirjoita tähän kommentti, niin skanneri etsii sitä Torista, Huudosta, Traderasta ja Blocketista
(tunnin välein) ja kommentoi tänne uudet osumat hintoineen. Paina **Subscribe**, niin saat ilmoituksen puhelimeen.

**Lisää** (yksi asia per kommentti, vain 1. rivi pakollinen):
```
twelve south curve, läppäriteline, laptop stand
max 60
uusi 98
-ipad, -tabletti
```
1. rivi = hakusanat pilkulla erotettuna (ensimmäinen on nimi). Osuma vaatii kaikki jonkin haun sanat.
`max` = hälytä vain tätä halvemmista, `uusi` = uushinta säästölaskua varten, `-sana` = hylkää jos sana löytyy.

**Poista:** `pois twelve south curve`

Kaikki nykyiset osumat: [WISHLIST.md](../blob/HEAD/WISHLIST.md)"""


# ---------------------------------------------------------------- items
def parse_comment(body: str) -> dict | None:
    """One wishlist item from a free-form comment, or {"remove": name}, or None."""
    lines = [l.strip() for l in (body or "").strip().splitlines() if l.strip() and not l.strip().startswith("```")]
    if not lines:
        return None
    m = re.match(r"(?i)^(pois|poista|remove)\s+(.+)$", lines[0])
    if m:
        return {"remove": m.group(2).strip()}
    item: dict = {"queries": [], "exclude": []}
    for i, line in enumerate(lines):
        if m := re.match(r"(?i)^(max|alle|maksimi)\s*:?\s*(\d+(?:[.,]\d+)?)\s*€?$", line):
            item["max_price"] = float(m.group(2).replace(",", "."))
        elif m := re.match(r"(?i)^(uusi|uutena|new)\s*:?\s*(\d+(?:[.,]\d+)?)\s*€?$", line):
            item["new_price"] = float(m.group(2).replace(",", "."))
        elif line.startswith("-"):
            item["exclude"] += [w.strip().lstrip("-").strip() for w in line.split(",") if w.strip().lstrip("-").strip()]
        elif i == 0:
            item["queries"] = [q.strip() for q in line.split(",") if q.strip()]
    if not item["queries"]:
        return None
    item["name"] = item["queries"][0]
    return item


def key(name: str) -> str:
    return S.norm(name).strip()


def load_items(comments: list[dict]) -> list[dict]:
    """wishlist.yaml items + items from human comments on the issue (oldest first, later ones win)."""
    items = {key(i["name"]): dict(i) for i in (S.load_yaml("wishlist.yaml").get("items") or [])}
    for c in comments:
        if (c.get("user") or {}).get("type") == "Bot":
            continue
        p = parse_comment(c.get("body", ""))
        if not p:
            continue
        if "remove" in p:
            r = key(p["remove"])
            for k in list(items):
                if k == r or any(key(q) == r for q in items[k].get("queries", [])) or r in k:
                    items.pop(k)
        else:
            items[key(p["name"])] = p
    return list(items.values())


# ---------------------------------------------------------------- matching
def matches(item: dict, title: str, text: str) -> bool:
    t = S.norm(f"{title} {text}")
    for w in item.get("exclude") or []:
        if S.norm(w).strip() and S.norm(w).strip() in t:
            return False
    need = [S.norm(w).strip() for w in item.get("require_any") or []]
    if need and not any(w and w in t for w in need):
        return False
    # every word of one query must appear (substring, so Finnish compounds/inflections still hit)
    return any(all(w in t for w in S.norm(q).split()) for q in item.get("queries") or [])


# ---------------------------------------------------------------- sources
def tori(q: str) -> list[M.Listing]:
    """Like markets.tori but keeps 0 € listings (giveaways are a great wishlist hit)."""
    t = M._get("https://www.tori.fi/recommerce/forsale/search", params={"q": q}).text
    m = re.search(r'<script type="application/ld\+json" id="seoStructuredData">(.*?)</script>', t, re.S)
    out = []
    if not m:
        return out
    try:
        els = json.loads(m.group(1)).get("mainEntity", {}).get("itemListElement", [])
    except ValueError:
        return out
    for el in els:
        it = el.get("item") or {}
        url = it.get("url") or ""
        iid = url.rstrip("/").rsplit("/", 1)[-1]
        try:
            price = float((it.get("offers") or {}).get("price") or 0)
        except ValueError:
            price = 0
        if not iid:
            continue
        out.append(M.Listing(source="tori", id=f"tori-{iid}", title=it.get("name") or "", price=price, url=url,
                             image=it.get("image") or "", text=it.get("description") or "",
                             condition="Uusi" if "NewCondition" in str(it.get("itemCondition")) else ""))
    return out


def fetch(source: str, q: str) -> list[M.Listing]:
    if source == "tori":
        return tori(q)
    if source == "huuto":
        return M.huuto({}, [q], 1)
    if source == "tradera":
        return M.tradera({}, [q], 1)
    if source == "blocket":
        return EU.recommerce("blocket", [q], M._get)
    return []


def search_all(items: list[dict]) -> dict[str, list[M.Listing]]:
    """Each (source, query) is fetched once even if several items share it."""
    cache: dict[tuple, list] = {}
    out = {}
    for it in items:
        got = {}
        for src in it.get("sources") or ALL_SOURCES:
            if src not in FLAG:
                continue
            for q in it["queries"]:
                k = (src, S.norm(q))
                if k not in cache:
                    try:
                        cache[k] = fetch(src, q)
                    except Exception as e:
                        S.log(f"{src} {q}: {e!r}")
                        cache[k] = []
                    time.sleep(2 if src == "tori" else 1.5)
                for L in cache[k]:
                    if L.source in SHIP:  # cross-border: score the price delivered to Finland
                        L.extra.setdefault("sticker", L.price)
                        L.extra["landed"] = round(L.extra["sticker"] + SHIP[L.source], 2)
                    if matches(it, L.title, L.text):
                        got[L.id] = L
        out[key(it["name"])] = list(got.values())
        S.log(f"{it['name']}: {len(got)} matches")
    return out


def eur(L: M.Listing) -> float:
    return L.extra.get("landed", L.price)


def preferred(item: dict, L: M.Listing) -> bool:
    t = S.norm(L.title)
    return any(S.norm(w).strip() in t for w in item.get("prefer") or [])


def order(item: dict, ls: list[M.Listing]) -> list[M.Listing]:
    """Quality brands first (they hold value and are what jp asked for), then cheapest."""
    return sorted(ls, key=lambda L: (not preferred(item, L), eur(L)))


# ---------------------------------------------------------------- report
def line(L: M.Listing, item: dict, med: float | None) -> str:
    p = eur(L)
    why = []
    if p == 0:
        why.append("ilmainen")
    if item.get("new_price") and p > 0:
        why.append(f"−{(1 - p / item['new_price']) * 100:.0f} % uushinnasta {item['new_price']:.0f} €")
    if med and p > 0:
        d = (1 - p / med) * 100
        why.append(f"{abs(d):.0f} % {'alle' if d >= 0 else 'yli'} käytettyjen mediaanin {med:.0f} €")
    if L.source in SHIP:
        why.append(f"{L.extra.get('sticker', p):.0f} € + ~{SHIP[L.source]} € posti, kysy lähettääkö Suomeen")
    if L.extra.get("auction"):
        why.append("huutokauppa, hinta voi nousta")
    if L.condition:
        why.append(L.condition.lower())
    title = L.title.replace("|", "/").replace("[", "(").replace("]", ")")[:90]
    star = "⭐ " if preferred(item, L) else ""
    return f"- {star}**{p:.0f} €** [{title}]({L.url}) · {FLAG[L.source]}" + (f" · {'; '.join(why)}" if why else "")


def median_price(ls: list[M.Listing]) -> float | None:
    ps = [eur(L) for L in ls if eur(L) > 0]
    return statistics.median(ps) if len(ps) >= 3 else None


def write_md(items: list[dict], found: dict[str, list[M.Listing]]):
    out = ["# 🛒 Toivelista: nykyiset osumat", "",
           f"Päivitetty {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. Lisää asioita kommentoimalla issueen "
           f"\"{ISSUE_TITLE}\". Hinnat perillä Suomessa (Ruotsi + ~15 € posti).", ""]
    for it in items:
        ls = sorted(found.get(key(it["name"]), []), key=eur)
        med = median_price(ls)
        mx = it.get("max_price")
        hdr = f"## {it['name']}"
        meta = [f"{len(ls)} osumaa"]
        if med:
            meta.append(f"mediaani {med:.0f} €")
        if mx:
            meta.append(f"hälytysraja {mx:.0f} €")
        if it.get("new_price"):
            meta.append(f"uutena {it['new_price']:.0f} €")
        out += [hdr, "", " · ".join(meta), ""]
        out += [line(L, it, med) for L in order(it, ls)[:60]] or ["_Ei osumia nyt._"]
        out.append("")
    MD.write_text("\n".join(out), encoding="utf-8")


# ---------------------------------------------------------------- GitHub issue
class Issue:
    def __init__(self, state: dict):
        self.token, self.repo, self.state = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY"), state
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"})
        self.api = f"https://api.github.com/repos/{self.repo}"

    @property
    def enabled(self):
        return bool(self.token and self.repo)

    def number(self) -> int | None:
        if self.state.get("issue"):
            return self.state["issue"]
        r = self.s.get(f"{self.api}/issues", params={"state": "open", "per_page": 100})
        for i in (r.json() if r.ok else []):
            if i.get("title") == ISSUE_TITLE and "pull_request" not in i:
                self.state["issue"] = i["number"]
                return i["number"]
        r = self.s.post(f"{self.api}/issues", json={"title": ISSUE_TITLE, "body": ISSUE_BODY})
        if r.ok:
            self.state["issue"] = r.json()["number"]
            return self.state["issue"]
        S.log(f"issue: {r.status_code} {r.text[:200]}")
        return None

    def comments(self) -> list[dict]:
        n = self.number()
        out, page = [], 1
        while n:
            r = self.s.get(f"{self.api}/issues/{n}/comments", params={"per_page": 100, "page": page})
            if not r.ok:
                S.log(f"comments: {r.status_code}")
                break
            out += r.json()
            if len(r.json()) < 100:
                break
            page += 1
        return out

    def post(self, body: str):
        n = self.number()
        if n:
            r = self.s.post(f"{self.api}/issues/{n}/comments", json={"body": body[:65000]})
            if not r.ok:
                S.log(f"post: {r.status_code} {r.text[:200]}")
            time.sleep(1)


# ---------------------------------------------------------------- run
def run():
    state = S.load_json(STATE, {})
    seen: dict = state.setdefault("seen", {})
    gh = Issue(state)
    items = load_items(gh.comments() if gh.enabled else [])
    found = search_all(items)
    write_md(items, found)
    S.save_json(SCAN, {"generated": S.now_ts(), "items": {
        it["name"]: [{"id": L.id, "source": L.source, "title": L.title, "price": eur(L), "url": L.url,
                      "image": L.image} for L in sorted(found.get(key(it["name"]), []), key=eur)] for it in items}})

    known = set(state.get("items", []))
    for it in items:
        k = key(it["name"])
        ls = sorted(found.get(k, []), key=eur)
        med = median_price(ls)
        mx = it.get("max_price")
        ok = order(it, [L for L in ls if mx is None or eur(L) <= mx])
        new = [L for L in ok if L.id not in seen.get(k, {})]
        if k not in known:  # first run for this item: a snapshot of what is out there now
            body = (f"### 🛒 {it['name']}: {len(ls)} osumaa nyt" + (f", {len(ok)} alle {mx:.0f} €" if mx else "")
                    + (f" · käytettyjen mediaani {med:.0f} €" if med else "") + "\n\n"
                    + ("\n".join(line(L, it, med) for L in ok[:20]) or "_Ei vielä osumia, ilmoitan kun tulee._"))
        elif new:
            body = f"### 🛒 {len(new)} uutta: {it['name']}\n\n" + "\n".join(line(L, it, med) for L in new[:15])
        else:
            body = ""
        if body and gh.enabled:
            gh.post(body)
        seen.setdefault(k, {}).update({L.id: S.now_ts() for L in ok})
    cutoff = S.now_ts() - 60 * 86400
    state["seen"] = {k: {i: t for i, t in v.items() if t >= cutoff} for k, v in seen.items() if k in {key(i["name"]) for i in items}}
    state["items"] = [key(i["name"]) for i in items]
    S.save_json(STATE, state)


if __name__ == "__main__":
    S.DATA.mkdir(exist_ok=True)
    {"run": run}[sys.argv[1] if len(sys.argv) > 1 else "run"]()
