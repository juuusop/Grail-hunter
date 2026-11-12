#!/usr/bin/env python3
"""Grail Hunter: Sellpy sniper.

Commands:
  python sniper.py run        one polling pass (GitHub Actions runs this every ~10 min)
  python sniper.py discover   brand search + evaluation: finds Sellpy's exact brand
                              spellings and price levels, writes data/brands_resolved.json
                              and data/BRAND_REPORT.md
"""
from __future__ import annotations

import json
import math
import os
import re
import statistics
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin

import requests
import yaml

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATE_FILE = DATA / "state.json"
RESOLVED_FILE = DATA / "brands_resolved.json"
FINDS_FILE = DATA / "finds.json"
FINDS_MD = ROOT / "FINDS.md"
REPORT_MD = DATA / "BRAND_REPORT.md"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

# Verified in the earlier Grail-hunter project; used only if the live lookup fails.
FALLBACK_APP_ID = "50LBQU2I4A"
FALLBACK_API_KEY = "4e696a94df3469d5356870d63c118c87"
BRAND_ATTR = "metadata.brand"
CHUNK = 80          # brand facet values per Algolia query
BATCH = 40          # queries per HTTP request in discover
SEASON_RE = re.compile(r"(?<![a-z0-9])(?:aw|fw|ss)\s?(?:19|20)?(?:9\d|0\d|1[0-2])(?![0-9])")


def log(*a):
    print(*a, flush=True)


def now_ts() -> int:
    return int(time.time())


# ---------------------------------------------------------------- text helpers
def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    s = s.lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9&+'/\- ]+", " ", s)
    s = s.replace("'", "").replace("-", " ").replace("/", " ")
    return re.sub(r"\s+", " ", s).strip()


def has_word(text: str, word: str) -> bool:
    w = norm(word)
    if not w:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", text) is not None


def flatten_text(obj, skip=("images", "objectID")) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("_") or k in skip:
                continue
            out += flatten_text(v, skip)
    elif isinstance(obj, list):
        for v in obj:
            out += flatten_text(v, skip)
    elif isinstance(obj, str):
        out.append(obj)
    return out


def dig(obj, path: str, default=None):
    cur = obj
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def first_str(*vals) -> str:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for k in ("fi", "name", "value", "en", "sv"):
                if isinstance(v.get(k), str) and v[k].strip():
                    return v[k].strip()
    return ""


# ---------------------------------------------------------------- config
@dataclass
class Brand:
    name: str
    value: float
    aliases: list[str] = field(default_factory=list)
    boost: dict[str, float] = field(default_factory=dict)
    rare: bool = False
    max_price: float | None = None
    min_price: float | None = None


def load_yaml(name: str) -> dict:
    with open(ROOT / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def brands_hash() -> str:
    import hashlib
    return hashlib.sha1((ROOT / "brands.yaml").read_bytes()).hexdigest()[:12]


def load_brands() -> list[Brand]:
    out = []
    for b in load_yaml("brands.yaml").get("brands", []):
        out.append(Brand(
            name=str(b["name"]), value=float(b["value"]),
            aliases=[str(a) for a in (b.get("aliases") or [])],
            boost={str(k): float(v) for k, v in (b.get("boost") or {}).items()},
            rare=bool(b.get("rare", False)),
            max_price=b.get("max_price"),
            min_price=b.get("min_price"),
        ))
    return out


INT_ORDER = ["xxxs", "xxs", "xs", "s", "m", "l", "xl", "xxl", "2xl", "3xl", "xxxl", "4xl", "5xl", "6xl"]
INT_RANK = {k: i for i, k in enumerate(INT_ORDER)}
INT_RANK.update({"2xl": INT_RANK["xxl"], "xxxl": INT_RANK["3xl"]})


def _num(x: str) -> float | None:
    m = re.match(r"(\d+(?:\.\d+)?)", x)
    return float(m.group(1)) if m else None


def size_fits(size: str, rules: dict | None) -> bool:
    """True if any part of a Sellpy size code (e.g. MEN-INT-M/L, SHOES-EU-43.5) is in jp's range.
    Codes the rules do not cover (one size, hats, bags, '-') always pass."""
    if not rules or not size or size.strip() in ("-", ""):
        return True
    for code in str(size).split(","):
        code = code.strip().upper()
        parts = code.split("-", 2)
        if len(parts) < 3:
            return True
        kind, system, val = parts
        key = f"{kind}-{system}".lower()
        rule = rules.get(key)
        if rule is None:
            return True  # unknown system: don't hide it
        for v in val.split("/"):
            v = v.strip().lower()
            if isinstance(rule, str):  # minimum INT size
                if INT_RANK.get(v, -1) >= INT_RANK.get(rule.lower(), 99):
                    return True
            else:  # [min, max] numeric
                n = _num(v)
                lo, hi = rule[0], (rule[1] if len(rule) > 1 else None)
                if n is not None and n >= lo and (hi is None or n <= hi):
                    return True
    return False


class BrandMatcher:
    """Maps any brand string (Sellpy facet value) to a configured brand.
    Longest alias wins, so 'Comme des Garçons Homme Plus' beats 'Comme des Garçons'."""

    def __init__(self, brands: list[Brand]):
        pairs = []
        for b in brands:
            for a in [b.name] + b.aliases:
                n = norm(a)
                if n:
                    pairs.append((n, b))
                    if " " in n:
                        pairs.append((n.replace(" ", ""), b))
        uniq: dict[str, Brand] = {}
        for n, b in pairs:
            uniq.setdefault(n, b)
        self.pairs = sorted(uniq.items(), key=lambda p: -len(p[0]))
        self.by_name = {b.name: b for b in brands}

    # A Sellpy brand string may extend an alias only with a known sub-line word
    # ("Comme des Garçons Homme Plus", "Rick Owens Lilies", "X x Supreme");
    # "Julius Zöllner", "Loewe Verlag" or "Chloe Ting" are different companies.
    SUFFIX_OK = {"homme", "plus", "man", "men", "mens", "black", "shirt", "noir", "pour", "deux",
                 "x", "archive", "mainline", "paris", "gold", "sport", "linea", "genius", "grenoble",
                 "gamme", "shadow", "lilies", "drkshdw", "play", "comme", "yohji", "denims", "studio"}

    def match(self, s) -> Brand | None:
        n = norm(s)
        if not n:
            return None
        for alias, b in self.pairs:
            if n == alias:
                return b
            if n.startswith(alias + " ") and n[len(alias) + 1:].split(" ")[0] in self.SUFFIX_OK:
                return b
        return None


# ---------------------------------------------------------------- state
def load_json(path: Path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=None if path == STATE_FILE else 1,
                  separators=(",", ":") if path == STATE_FILE else None)
    tmp.replace(path)


# ---------------------------------------------------------------- Sellpy / Algolia
class Sellpy:
    def __init__(self, market: str, state: dict):
        self.market = market
        self.state = state
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept": "application/json",
                               "Origin": f"https://www.sellpy.{market}",
                               "Referer": f"https://www.sellpy.{market}/"})
        self.price_attr = f"price_{market.upper()}"
        self.app_id = self.key = self.index = None
        self._load_creds()

    # Sellpy's public search key lives in its JS bundle; read it from there so
    # nobody has to paste keys, and so a rotated key fixes itself.
    def _scrape_creds(self) -> dict | None:
        m = self.market
        try:
            html = self.s.get(f"https://www.sellpy.{m}/search?query=x", timeout=20).text
            hit = re.search(r"""["']([^"']*market/index\.[A-Za-z0-9_-]+\.bundle\.js)""", html)
            if not hit:
                log("creds: bundle path not found in page")
                return None
            js = self.s.get(urljoin(f"https://www.sellpy.{m}/", hit.group(1)), timeout=30).text
            for block in re.findall(r"\b" + m + r"\s*:\s*\{([^{}]*)\}", js):
                app = re.search(r"""applicationId["']?\s*:\s*["']([A-Z0-9]+)""", block)
                key = re.search(r"""searchKey["']?\s*:\s*["']([a-f0-9]{20,})""", block)
                idx = re.search(r"""marketItemIndexSaleStartDescending["']?\s*:\s*["']([^"']+)""", block)
                if app and key:
                    return {"app_id": app.group(1), "key": key.group(1),
                            "index": idx.group(1) if idx else None, "ts": now_ts()}
            log("creds: locale block not found in bundle")
        except requests.RequestException as e:
            log(f"creds: scrape failed: {e}")
        return None

    def _load_creds(self, force=False):
        env = (os.getenv("SELLPY_ALGOLIA_APP_ID"), os.getenv("SELLPY_ALGOLIA_KEY"))
        c = self.state.get("creds") or {}
        if all(env):
            c = {"app_id": env[0], "key": env[1], "index": os.getenv("SELLPY_INDEX"), "ts": now_ts()}
        elif force or not c or now_ts() - c.get("ts", 0) > 24 * 3600:
            c = self._scrape_creds() or c or {}
        self.app_id = c.get("app_id") or FALLBACK_APP_ID
        self.key = c.get("key") or FALLBACK_API_KEY
        self.index = c.get("index") or f"prod_marketItem_{self.market}_saleStartedAt_desc"
        self.state["creds"] = {"app_id": self.app_id, "key": self.key, "index": self.index,
                               "ts": c.get("ts", now_ts())}

    def queries(self, reqs: list[dict]) -> list[dict]:
        """reqs: list of Algolia param dicts. Returns list of results (same order)."""
        if not reqs:
            return []
        body = {"requests": [{"indexName": self.index, "params": urlencode(
            {k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()})}
            for r in reqs]}
        url = f"https://{self.app_id.lower()}-dsn.algolia.net/1/indexes/*/queries"
        for attempt in range(4):
            try:
                resp = self.s.post(url, json=body, timeout=30, headers={
                    "x-algolia-application-id": self.app_id, "x-algolia-api-key": self.key})
            except requests.RequestException as e:
                log(f"algolia: {e}; retry")
                time.sleep(2 ** attempt * 2)
                continue
            if resp.status_code == 200:
                return resp.json().get("results", [])
            if resp.status_code in (401, 403) and attempt == 0:
                log("algolia: key rejected, re-reading key from Sellpy")
                self._load_creds(force=True)
                url = f"https://{self.app_id.lower()}-dsn.algolia.net/1/indexes/*/queries"
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(2 ** attempt * 5)
                continue
            raise RuntimeError(f"Algolia {resp.status_code}: {resp.text[:300]}")
        raise RuntimeError("Algolia: too many failures")

    def price(self, hit) -> float:
        amt = dig(hit, f"{self.price_attr}.amount")
        if amt is None:
            amt = dig(hit, "price.amount") or dig(hit, "pricing.amount") or 0
        try:
            return float(amt) / 100.0
        except (TypeError, ValueError):
            return 0.0


# ---------------------------------------------------------------- evaluation
@dataclass
class Find:
    id: str
    brand: str
    title: str
    price: float
    value: float
    score: float
    label: str
    category: str
    condition: str
    size: str
    link: str
    image: str
    reasons: list[str]
    source: str
    old_price: float | None = None
    ts: int = 0
    # resale.py: realistic sale price, best exit platform and expected profit after fees
    resale: float | None = None
    profit: float | None = None
    roi: float | None = None
    exit: str = ""
    resale_why: list[str] = field(default_factory=list)

    def to_dict(self):
        return self.__dict__.copy()


class Evaluator:
    def __init__(self, cfg: dict, matcher: BrandMatcher, resolved: dict, market: str):
        self.cfg = cfg
        self.st = cfg.get("settings", {})
        self.matcher = matcher
        self.resolved = resolved.get("brands", {}) if resolved else {}
        self.market = market
        self.min_score = float(self.st.get("min_score", 2.0))
        self.rare_min = float(self.st.get("rare_min_score", 0.9))
        self.max_price = self.st.get("max_price")
        self.excl = [w for w in cfg.get("exclude_words", [])]
        self.rare_words = cfg.get("rare_words", [])
        self.gboost = {k: float(v) for k, v in (cfg.get("global_boost") or {}).items()}
        self.buy_source = "sellpy"   # markets.py sets this per listing (delivery cost differs)
        # real sold prices from Japan (comps.py); shown in reasons, not used for scoring
        self.comps = (load_json(DATA / "comps.json", {}) or {}).get("brands", {})
        # Name collisions: if Sellpy's own median for a brand is under 10 % of the value we
        # assume (e.g. "Casablanca", "Bless", "Tao"), most of its stock is a different,
        # cheap label. Cap the value at 3x the Sellpy median so those stop looking like deals.
        self.collisions = {}
        for b in {id(x): x for x in matcher.by_name.values()}.values():
            stt = self.resolved.get(b.name) or {}
            med, cnt = stt.get("median"), stt.get("count", 0)
            if med and cnt >= int(self.st.get("collision_min_count", 20)) and med < 0.1 * b.value:
                self.collisions[b.name] = (b.value, med)
                b.value = round(med * 3, 1)

    def _image(self, hit, oid):
        imgs = hit.get("images") or []
        if imgs:
            i0 = imgs[0]
            if isinstance(i0, str) and i0.startswith("http"):
                return i0
            if isinstance(i0, dict):
                for k in ("url", "src", "large", "medium"):
                    if isinstance(i0.get(k), str) and i0[k].startswith("http"):
                        return i0[k]
        return f"https://img.sellpy.net/photo/{oid}/1.jpg"

    def _category(self, text_cat: str, text_all: str):
        for c in self.cfg.get("categories", []):
            if any(has_word(text_cat, w) for w in c["words"]):
                return c["name"], float(c["mult"])
        for c in self.cfg.get("categories", []):
            if any(has_word(text_all, w) for w in c["words"]):
                return c["name"], float(c["mult"])
        return "muu", float(self.cfg.get("default_category_mult", 0.8))

    def _condition(self, cond: str):
        n = norm(cond)
        best = None
        for c in self.cfg.get("conditions", []):
            for w in c["words"]:
                if has_word(n, w) and (best is None or len(norm(w)) > best[0]):
                    best = (len(norm(w)), float(c["mult"]))
        return best[1] if best else 0.95

    def _size_ok(self, size: str, cat: str) -> bool:
        return size_fits(size, self.st.get("sizes"))

    def evaluate(self, hit: dict, sp: Sellpy, hunt: dict | None = None) -> Find | None:
        oid = str(hit.get("objectID", ""))
        price = sp.price(hit)
        if not oid or price <= 0:
            return None
        if hit.get("isReserved") or hit.get("isForSale") is False:
            return None
        raw_brand = first_str(dig(hit, BRAND_ATTR), hit.get("brand"), hit.get("brandName"))
        brand = self.matcher.match(raw_brand)
        cats = hit.get("categories") or {}
        cat_text = norm(" ".join(flatten_text(cats)) + " " + first_str(hit.get("title"), dig(hit, "metadata.type"), hit.get("type")))
        # brandClassification/brandGroups describe the brand, not this item: their style words
        # ("rock", "knitwear"...) made ~360 dresses, caps and sunglasses score as a coat (×1.6)
        text = norm(" ".join(flatten_text(hit, skip=("images", "objectID", "brandClassification", "brandGroups"))))
        title = first_str(hit.get("title"), hit.get("name")) or " ".join(
            x for x in [raw_brand, first_str(dig(hit, "metadata.type"), hit.get("type")),
                        first_str(dig(hit, "metadata.model"), hit.get("model"))] if x)
        cond = first_str(hit.get("condition"), dig(hit, "metadata.condition"))
        size = first_str(hit.get("size"), dig(hit, "metadata.size"))

        for w in self.excl:
            if has_word(text, w):
                return None
        reasons: list[str] = []
        if hunt:
            if brand is not None:
                return None  # the brand feed covers it
            # the term must be in the item's own details, not in its brand name
            # ("Laura Guidi", "Tabi International" are not grails)
            md = dict(hit.get("metadata") or {})
            md.pop("brand", None)
            own = norm(" ".join(flatten_text([md, hit.get("keywords"), hit.get("title"), hit.get("description")])))
            terms = hunt.get("must") or [hunt["q"]]
            hitword = next((t for t in terms if has_word(own, t)), None)
            if not hitword or any(norm(t) in norm(raw_brand) for t in terms + [hunt["q"]]):
                return None
            value = float(hunt["value"]) * 0.85
            name = f"{raw_brand or 'Tuntematon'} (haku: {hunt['q']})"
            boosts = dict(self.gboost)
            rare = False
            hmax = hunt.get("max_price")
            if hmax is not None and price > float(hmax):
                return None
            reasons.append(f"tiedoissa '{hitword}', brändiksi listattu '{raw_brand or '-'}'")
        else:
            if brand is None:
                return None
            value = brand.value
            name = brand.name
            boosts = {**self.gboost, **brand.boost}
            rare = brand.rare
            if rare:
                reasons.append("harvinainen brändi")
            if brand.max_price is not None and price > float(brand.max_price):
                return None
            floor = brand.min_price if brand.min_price is not None else self.st.get("min_price", 0)
            if floor and price < float(floor):
                return None

        cat, cmult = self._category(cat_text, text)
        if norm(size).startswith("child") or not self._size_ok(size, cat):
            return None
        kmult = self._condition(cond)
        bmult = 1.0
        for w, m in boosts.items():
            if has_word(text, w):
                bmult *= m
                reasons.append(f"{w} ×{m:g}")
        bmult = max(0.2, min(bmult, 3.0))
        for w in self.rare_words:
            if has_word(text, w):
                rare = True
                reasons.append(f"harvinainen: {w}")
                break
        if SEASON_RE.search(text):
            rare = True
            bmult *= 1.2
            reasons.append(f"sesonkikoodi {SEASON_RE.search(text).group(0).upper()}")

        est = value * cmult * kmult * bmult
        if not hunt:
            import resale
            mv = resale.model_value(name, text, kmult, cat)
            if mv:  # a known model has its own resale level (Kelly vs. scarf, Geobasket vs. tee)
                est = mv[0]
                reasons.append(f"malli '{mv[1]['_hit']}' ~{mv[1]['price']:.0f} €")
        stats = self.resolved.get(name) if not hunt else None
        if stats and stats.get("median") and stats.get("count", 0) >= 30:
            # Sellpy prices common brands sensibly, so a deal must also be cheap
            # compared with what Sellpy usually asks for this brand and item type.
            cap = stats["median"] * float(self.st.get("sellpy_median_factor", 0.8)) * cmult
            if price > cap and not rare:
                return None
            reasons.append(f"Sellpyn mediaani tälle brändille {stats['median']:.0f} €")
        comp = self.comps.get(name) if not hunt else None
        if comp:
            cc = (comp.get("cats") or {}).get(cat)
            if cc:
                reasons.append(f"Japanissa myyty ({cat}) mediaani {cc['median']} € (n={cc['n']})")
            else:
                reasons.append(f"Japanissa myyty mediaani {comp['median']} € (n={comp['n']})")
        score = est / price
        if self.max_price is not None and price > float(self.max_price):
            return None
        if score >= 4:
            label = "🚨 INSANE"
        elif score >= max(self.min_score, 2.5):
            label = "🔥 KOVA DIILI"
        elif score >= self.min_score:
            label = "✅ DIILI"
        elif rare and score >= self.rare_min:
            label = "💎 HARVINAINEN"
        else:
            # expensive pieces (Kelly at auction) can leave real money at a low value/price ratio
            import resale
            rp = None if hunt else resale.evaluate(name, cat, price, est, text, kmult, self.buy_source)
            if not rp or not resale.big_profit(rp):
                return None
            label = "💰 KATE"
        f = Find(id=oid, brand=name, title=title, price=round(price, 2), value=round(est),
                 score=round(score, 2), label=label, category=cat, condition=cond or "-",
                 size=size or "-", link=f"https://www.sellpy.{self.market}/item/{oid}",
                 image=self._image(hit, oid), reasons=reasons,
                 source="haku" if hunt else "brändi", ts=now_ts())
        if not hunt:
            import resale
            resale.annotate(f, text, kmult, self.buy_source)
        return f


# ---------------------------------------------------------------- notifications (GitHub issue)
class GitHubNotifier:
    def __init__(self, title: str, state: dict):
        self.token = os.getenv("GITHUB_TOKEN")
        self.repo = os.getenv("GITHUB_REPOSITORY")
        self.title = title
        self.state = state
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {self.token}",
                               "Accept": "application/vnd.github+json"})

    @property
    def enabled(self):
        return bool(self.token and self.repo)

    def _issue(self) -> int | None:
        num = self.state.get("issue")
        if num:
            return num
        api = f"https://api.github.com/repos/{self.repo}"
        r = self.s.get(f"{api}/issues", params={"state": "open", "per_page": 100})
        if r.ok:
            for i in r.json():
                if i.get("title") == self.title and "pull_request" not in i:
                    self.state["issue"] = i["number"]
                    return i["number"]
        r = self.s.post(f"{api}/issues", json={"title": self.title, "body":
                        "Grail Hunter kommentoi tähän jokaisen uuden löydön. "
                        "Paina **Subscribe**, niin GitHub-sovellus ilmoittaa puhelimeen.\n\n"
                        "Kaikki löydöt yhdessä paikassa: [FINDS.md](../blob/HEAD/FINDS.md)"})
        if r.ok:
            self.state["issue"] = r.json()["number"]
            return self.state["issue"]
        log(f"notify: cannot create issue: {r.status_code} {r.text[:200]}")
        return None

    def send(self, header: str, finds: list[Find]):
        if not self.enabled or not finds:
            return
        num = self._issue()
        if not num:
            return
        for i in range(0, len(finds), 10):
            body = header + "\n\n" + "\n\n---\n\n".join(find_md(f) for f in finds[i:i + 10])
            for attempt in range(3):
                r = self.s.post(f"https://api.github.com/repos/{self.repo}/issues/{num}/comments",
                                json={"body": body[:65000]})
                if r.status_code in (403, 429) and attempt < 2:
                    time.sleep(int(r.headers.get("retry-after", 30)))
                    continue
                if r.status_code == 404 or r.status_code == 410:
                    self.state.pop("issue", None)
                if not r.ok:
                    log(f"notify: {r.status_code} {r.text[:200]}")
                break
            time.sleep(1)


def find_md(f: Find) -> str:
    drop = f" ~~{f.old_price:.0f} €~~" if f.old_price else ""
    why = "; ".join(f.reasons) if f.reasons else ""
    return (f"<a href=\"{f.link}\"><img src=\"{f.image}\" width=\"140\" align=\"left\"></a>\n\n"
            f"**{f.label} · [{f.brand}]({f.link})**  \n"
            f"{f.title}  \n"
            f"**{f.price:.0f} €**{drop} · arvio ~{f.value} € · pisteet {f.score}"
            + (f" · **kate ~{f.profit:.0f} €** ({f.exit})" if f.profit is not None else "") + "  \n"
            f"{f.category} · koko {f.size} · {f.condition}"
            + (f"  \n_{why}_" if why else "") + "<br clear=\"left\">")


def write_finds_md(finds: list[dict]):
    week = now_ts() - 7 * 86400
    best = sorted([f for f in finds if f["ts"] >= week], key=lambda f: -f["score"])[:40]
    newest = sorted(finds, key=lambda f: -f["ts"])[:60]

    def row(f):
        t = datetime.fromtimestamp(f["ts"], timezone.utc).strftime("%d.%m. %H:%M")
        drop = f" (oli {f['old_price']:.0f})" if f.get("old_price") else ""
        title = (f.get("title") or "").replace("|", "/")[:60]
        return (f"| <a href=\"{f['link']}\"><img src=\"{f['image']}\" width=\"90\"></a> | "
                f"{f['label']}<br>**[{f['brand']}]({f['link']})**<br>{title} | "
                f"**{f['price']:.0f} €**{drop}<br>arvio ~{f['value']} €"
                + (f"<br>kate ~{f['profit']:.0f} €" if f.get("profit") is not None else "") + f" | {f['score']} | "
                f"{f['category']}<br>{f['size']} | {t} |")

    head = "| | Löytö | Hinta | Pisteet | Tyyppi / koko | Löydetty (UTC) |\n|---|---|---|---|---|---|"
    md = ["# 🦅 Grail Hunter: löydöt", "",
          f"Päivitetty {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC. "
          "Pisteet = arvioitu arvo / hinta. Tuote voi olla jo myyty.", "",
          "## 🔥 Viikon parhaat", "", head] + [row(f) for f in best] + [
          "", "## 🕒 Uusimmat", "", head] + [row(f) for f in newest]
    FINDS_MD.write_text("\n".join(md) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- discover
def pct(vals, q):
    if not vals:
        return None
    vals = sorted(vals)
    k = (len(vals) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def discover(cfg: dict, state: dict) -> dict:
    market = cfg["settings"].get("market", "fi")
    sp = Sellpy(market, state)
    brands = load_brands()
    matcher = BrandMatcher(brands)
    log(f"discover: index {sp.index}, {len(brands)} brands")

    sample = sp.queries([{"query": "", "hitsPerPage": 2, "facets": ["*"], "maxValuesPerFacet": 5}])[0]
    save_json(DATA / "discover_sample.json", {
        "facets": {k: v for k, v in (sample.get("facets") or {}).items()},
        "hit_keys": sorted((sample.get("hits") or [{}])[0].keys()),
        "hit": (sample.get("hits") or [{}])[0], "nbHits": sample.get("nbHits")})

    # 1) brand spellings: text-search every name/alias, read the brand facet
    qs = []
    for b in brands:
        for a in dict.fromkeys([b.name] + b.aliases):
            if len(norm(a)) >= 3:
                qs.append(a)
    values: dict[str, dict[str, int]] = {b.name: {} for b in brands}
    unmatched: dict[str, int] = {}
    for i in range(0, len(qs), BATCH):
        res = sp.queries([{"query": q, "hitsPerPage": 0, "facets": [BRAND_ATTR],
                           "maxValuesPerFacet": 40, "typoTolerance": "min"} for q in qs[i:i + BATCH]])
        for q, r in zip(qs[i:i + BATCH], res):
            for val, cnt in ((r.get("facets") or {}).get(BRAND_ATTR) or {}).items():
                b = matcher.match(val)
                if b:
                    values[b.name][val] = max(values[b.name].get(val, 0), cnt)
                elif norm(q) in norm(val) or norm(val) in norm(q):
                    unmatched[val] = max(unmatched.get(val, 0), cnt)
        time.sleep(1)

    # 2) price levels per brand
    names = [b.name for b in brands if values[b.name]]
    stats: dict[str, dict] = {}
    for i in range(0, len(names), BATCH):
        chunk = names[i:i + BATCH]
        res = sp.queries([{"query": "", "hitsPerPage": 300,
                           "facetFilters": [[f"{BRAND_ATTR}:{v}" for v in values[n]]],
                           "attributesToRetrieve": [sp.price_attr], "attributesToHighlight": []}
                          for n in chunk])
        for n, r in zip(chunk, res):
            prices = [p for p in (sp.price(h) for h in r.get("hits", [])) if p > 0]
            stats[n] = {"count": r.get("nbHits", 0),
                        "p25": round(pct(prices, 0.25), 2) if prices else None,
                        "median": round(statistics.median(prices), 2) if prices else None}
        time.sleep(1)

    resolved = {"generated": now_ts(), "brands_hash": brands_hash(), "index": sp.index, "brand_attr": BRAND_ATTR,
                "price_attr": sp.price_attr,
                "brands": {n: {"values": sorted(values[n]), **stats.get(n, {})} for n in names},
                "not_found": [b.name for b in brands if not values[b.name]],
                "similar_unlisted": dict(sorted(unmatched.items(), key=lambda x: -x[1])[:80])}
    save_json(RESOLVED_FILE, resolved)
    write_report(resolved, brands, cfg)
    log(f"discover: {len(names)} brands found on Sellpy, {len(resolved['not_found'])} not found")
    return resolved


def write_report(resolved: dict, brands: list[Brand], cfg: dict):
    ms = float(cfg["settings"].get("min_score", 2.0))
    lines = ["# Brändiraportti", "",
             f"Luotu {datetime.fromtimestamp(resolved['generated'], timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC, indeksi `{resolved['index']}`.", "",
             "**Diiliraja** = hinta, jonka alle peruskappale (kerroin 1.0) hälyttää. "
             "Jos Sellpyn mediaani on jo diilirajan alla, brändin `value` on luultavasti liian korkea, "
             "ja se kannattaa laskea, ettei tule spämmiä.", "",
             "| Brändi | Sellpyssä nyt | Mediaani € | Halvin 25 % € | Diiliraja € | Huom | Sellpyn kirjoitusasut |",
             "|---|---|---|---|---|---|---|"]
    by = {b.name: b for b in brands}
    rows = []
    for n, s in resolved["brands"].items():
        b = by.get(n)
        if not b:
            continue
        lim = b.value / ms
        med = s.get("median")
        note = "⚠️ value liian korkea?" if med and med < lim else ""
        rows.append((s.get("count", 0), f"| {n} | {s.get('count', 0)} | {med or '-'} | {s.get('p25') or '-'} | "
                     f"{lim:.0f} | {note} | {', '.join(s['values'][:6])} |"))
    lines += [r for _, r in sorted(rows, key=lambda x: -x[0])]
    lines += ["", "## Ei löytynyt Sellpystä nyt", "", ", ".join(resolved["not_found"]) or "-", "",
              "## Samankaltaisia brändejä, joita ei ole listalla", "",
              "Näitä löytyi hakujen sivutuotteena. Lisää `brands.yaml`iin, jos kiinnostaa.", ""]
    lines += [f"- {k} ({v})" for k, v in resolved.get("similar_unlisted", {}).items()]
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- run
def run(cfg: dict):
    st = cfg.get("settings", {})
    market = st.get("market", "fi")
    state = load_json(STATE_FILE, {})
    resolved = load_json(RESOLVED_FILE, None)
    if not resolved or now_ts() - resolved.get("generated", 0) > 8 * 86400 \
            or resolved.get("brands_hash") != brands_hash():
        log("run: brand data missing or stale, running discover first")
        resolved = discover(cfg, state)

    sp = Sellpy(market, state)
    brands = load_brands()
    matcher = BrandMatcher(brands)
    ev = Evaluator(cfg, matcher, resolved, market)
    seen: dict = state.setdefault("seen", {})
    first_run = not state.get("initialized")

    all_vals = [v for n, b in resolved["brands"].items() for v in b["values"] if n in matcher.by_name]
    chunks = [all_vals[i:i + CHUNK] for i in range(0, len(all_vals), CHUNK)]
    base_filters = []
    if st.get("categories_lvl0"):
        base_filters.append([f"categories.lvl0:{c}" for c in st["categories_lvl0"]])
    num = [f"{sp.price_attr}.amount>0"]
    if st.get("max_price"):
        num.append(f"{sp.price_attr}.amount<={int(float(st['max_price']) * 100)}")

    hits: list[tuple[dict, dict | None]] = []
    # 1) newest per brand chunk, paging until we reach items seen last time
    open_chunks = list(range(len(chunks)))
    for page in range(int(st.get("max_pages", 5))):
        if not open_chunks:
            break
        res = sp.queries([{"query": "", "hitsPerPage": 100, "page": page,
                           "facetFilters": base_filters + [[f"{BRAND_ATTR}:{v}" for v in chunks[c]]],
                           "numericFilters": num} for c in open_chunks])
        still = []
        for c, r in zip(open_chunks, res):
            hs = r.get("hits", [])
            hits += [(h, None) for h in hs]
            reached_old = any(str(h.get("objectID")) in seen for h in hs)
            if not reached_old and not first_run and r.get("nbPages", 0) > page + 1:
                still.append(c)
        open_chunks = still
    # 2) hourly sweep of everything listed, catches price drops
    sweep_min = int(st.get("sweep_every_minutes", 60))
    if now_ts() - state.get("last_sweep", 0) >= sweep_min * 60:
        for i in range(0, len(chunks), 10):
            res = sp.queries([{"query": "", "hitsPerPage": 1000,
                               "facetFilters": base_filters + [[f"{BRAND_ATTR}:{v}" for v in ch]],
                               "numericFilters": num,
                               "attributesToHighlight": [], "attributesToSnippet": []}
                              for ch in chunks[i:i + 10]])
            for r in res:
                hits += [(h, None) for h in r.get("hits", [])]
        state["last_sweep"] = now_ts()
    # 3) misattributed / unbranded text hunts
    hunts = cfg.get("hunts") or []
    if hunts:
        res = sp.queries([{"query": h["q"], "hitsPerPage": 60, "numericFilters": num,
                           "facetFilters": base_filters, "typoTolerance": "min"} for h in hunts])
        for h, r in zip(hunts, res):
            hits += [(x, h) for x in r.get("hits", [])]

    alerts: list[Find] = []
    done = set()
    for hit, hunt in hits:
        oid = str(hit.get("objectID", ""))
        if not oid or oid in done:
            continue
        price = sp.price(hit)
        f = ev.evaluate(hit, sp, hunt)
        if f is None and hunt is not None:
            continue  # unrelated text-search hit; don't remember it
        done.add(oid)
        prev = seen.get(oid)
        rec = prev or {"t": now_ts()}
        if prev and price and prev.get("p") and price < prev["p"] - 0.5:
            if f:
                f.old_price = prev["p"]
                f.label = "📉 " + f.label
                f.reasons.insert(0, f"hinta laski {prev['p']:.0f} → {price:.0f} €")
        rec["p"] = price
        if f and (rec.get("a") is None or price < rec["a"] - 0.5):
            rec["a"] = price
            alerts.append(f)
        seen[oid] = rec

    # prune memory older than 60 days
    cutoff = now_ts() - 60 * 86400
    for k in [k for k, v in seen.items() if v.get("t", 0) < cutoff]:
        del seen[k]

    finds = load_json(FINDS_FILE, [])
    finds = ([f.to_dict() for f in alerts] + finds)[:1500]
    save_json(FINDS_FILE, finds)
    if alerts or not FINDS_MD.exists():
        write_finds_md(finds)

    import resale
    alerts.sort(key=resale.rank_key)   # expected profit first, then score
    notifier = GitHubNotifier(st.get("notify_issue_title", "🦅 Löydöt"), state)
    if first_run:
        if alerts:
            notifier.send(f"### Ensimmäinen ajo: {len(alerts)} löytöä jo myynnissä. "
                          f"Parhaat 15 alla, kaikki FINDS.md:ssä.", alerts[:15])
        state["initialized"] = True
    else:
        notifier.send(f"### {len(alerts)} uutta löytöä", alerts[:30])
    for f in alerts[:20]:
        log(f"{f.label} {f.brand} {f.price:.0f}€ ~{f.value}€ s={f.score} {f.link}")
    log(f"run: {len(hits)} hits checked, {len(alerts)} alerts, memory {len(seen)} items")
    save_json(STATE_FILE, state)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    cfg = load_yaml("config.yaml")
    DATA.mkdir(exist_ok=True)
    if cmd == "discover":
        state = load_json(STATE_FILE, {})
        discover(cfg, state)
        save_json(STATE_FILE, state)
    elif cmd == "run":
        run(cfg)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
