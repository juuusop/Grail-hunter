"""Fake and condition risk for finds.

Rough, explainable heuristics (no photos needed). Each find gets
  risk = {"fake": 0-100, "fake_level": "matala|keski|korkea", "cond": "ok|kulunut|huono|?",
          "why": [...short Finnish reasons...]}

Fake risk = brand tier x category x platform x price signal x text signals.
  * brand tier: how big the counterfeit market for the brand is (config.yaml risk.tiers + markets.fake_risk).
  * category: bags, small leather goods, belts, sunglasses, jewellery, caps and sneakers are the most
    counterfeited product types (EUIPO/OECD seizure data); tailoring and knitwear barely.
  * platform: Sellpy sorts every item in-house and only sells authentic goods by policy (30 d returns);
    Tradera has mandatory buyer protection for "not as described"; Tori/Marktplaats/etc. are private sales.
  * price: a heavily faked brand at a fraction of its value from a private seller is the classic fake.
Condition comes from the platform grade (Sellpy: Acceptable = "used extensively and defects occur").

`python risk.py report` writes data/RISK.md with shares per platform / brand / category.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

import yaml

import sniper as S

ROOT = Path(__file__).resolve().parent

_cfg = None


def cfg() -> dict:
    global _cfg
    if _cfg is None:
        core = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
        r = dict(core.get("risk") or {})
        mk = core.get("markets") or {}
        try:
            import markets_eu as EU
            extra = EU.FAKE_RISK_EXTRA
        except Exception:  # pragma: no cover
            extra = []
        hi = set(r.get("tier_high") or []) | set(mk.get("fake_risk") or []) | set(extra)
        r["_high"] = {S.norm(x) for x in hi}
        r["_mid"] = {S.norm(x) for x in r.get("tier_mid") or []} - r["_high"]
        _cfg = r
    return _cfg


SUNGLASS = re.compile(r"silm.lasit|aurinkolasit|sunglass|solglas|zonnebril|solbrille|eyewear|glasses", re.I)
BAD_TEXT = re.compile(r"\b(1:1|aaa|replica|replika|kopio|copy|mirror|ua|unauthori[sz]ed|inspired|tyylinen|"
                      r"look ?alike|no tags|ilman kuittia|lahjaksi saatu|aitoutta ei taata|"
                      r"ei aitoustodistusta|not authentic)\b", re.I)
GOOD_TEXT = re.compile(r"\b(kuitti|receipt|kvitto|kvittering|bon|bonnetje|aitoustodistus|certificate|"
                       r"authenticity|entrupy|legit ?check|dust ?bag|p.lypussi|dustbag|alkuper.inen laatikko|"
                       r"original box|serial|sarjanumero|date code)\b", re.I)

PLATFORM = {  # multiplier on fake risk, and a short reason
    "sellpy": (0.45, "Sellpy lajittelee itse + myy vain aitoja (linjaus), palautus 30 pv"),
    "emmy": (0.5, "Emmy tarkastaa tuotteet itse"),
    "tradera": (0.8, "Traderan ostajansuoja kattaa 'ei vastaa kuvausta'"),
}
PRIVATE = (1.0, "yksityismyyjä, ei tarkastusta")


def _platform(src: str):
    return PLATFORM.get((src or "sellpy").lower(), PRIVATE)


def condition(cond: str, category: str = "") -> tuple[str, str]:
    n = S.norm(cond or "")
    if not n or n == "-":
        return "?", "kunto ei tiedossa, pyydä lisäkuvat"
    if any(S.has_word(n, w) for w in ("huono", "poor", "slecht", "dalig", "daarlig")):
        return "huono", "kunto huono"
    if any(S.has_word(n, w) for w in ("hyvaksyttava", "acceptable", "acceptabelt", "kohtalainen", "tyydyttava",
                                      "fair", "gedragen", "gebruikt", "brugt", "brukt", "anvand")):
        heavy = category in ("kengät", "laukku", "nahkatakki", "asuste")
        return "kulunut", ("selviä käytön jälkiä/vikoja" + (" (kengissä/laukuissa kuluma syö resale-hintaa)" if heavy else ""))
    return "ok", ""


def assess(brand: str, category: str, price: float, value: float, title: str = "", text: str = "",
           source: str = "sellpy", cond: str = "") -> dict:
    c = cfg()
    b = S.norm((brand or "").split(" · ")[0])
    why = []
    if b in c["_high"]:
        base = float(c.get("base_high", 40))
        why.append("paljon väärennetty brändi")
    elif b in c["_mid"]:
        base = float(c.get("base_mid", 18))
        why.append("jonkin verran väärennöksiä")
    else:
        base = float(c.get("base_low", 3))
    full = f"{title} {text}"
    cat = category
    if SUNGLASS.search(full):
        cat = "aurinkolasit"
    cm = float((c.get("category_mult") or {}).get(cat, 1.0))
    if cm >= 1.3 and base >= 15:
        why.append(f"{cat}: väärennetyimpiä tuotetyyppejä")
    pm, pwhy = _platform(source)
    ratio = price / value if value else 1.0
    prm = 1.0
    if base >= 15 and ratio < 0.15:
        prm = 1.6
        why.append(f"hinta vain {ratio:.0%} arvosta")
    elif base >= 15 and ratio < 0.3:
        prm = 1.25
    tm = 1.0
    bad = [m.group(0) for m in BAD_TEXT.finditer(full)
           if not (m.group(0).lower() == "replica" and "margiela" in b)]  # Margiela Replica = real line
    if bad:
        tm *= 2.0
        why.append(f"tekstissä '{bad[0]}'")
    if GOOD_TEXT.search(full):
        tm *= 0.6
        why.append(f"aitoustodiste mainittu ('{GOOD_TEXT.search(full).group(0)}')")
    score = max(0.0, min(100.0, base * cm * pm * prm * tm))
    if base >= 15:
        why.append(pwhy)
    lvl = "korkea" if score >= 45 else "keski" if score >= 20 else "matala"
    cl, cwhy = condition(cond, category)
    if cwhy:
        why.append(cwhy)
    return {"fake": round(score), "fake_level": lvl, "cond": cl, "why": why}


def annotate(f, text: str = "", source: str = "sellpy"):
    """Adds f.risk to a sniper.Find. Never fails the find."""
    try:
        f.risk = assess(f.brand, f.category, f.price, f.value, f.title, text, source, f.condition)
    except Exception as e:  # pragma: no cover
        S.log(f"risk: {e!r}")
    return f


def badge(r: dict | None) -> str:
    if not r:
        return ""
    parts = []
    if r.get("fake_level") == "korkea":
        parts.append(f"⚠️ feikkiriski {r['fake']}")
    elif r.get("fake_level") == "keski":
        parts.append(f"🟡 feikkiriski {r['fake']}")
    if r.get("cond") in ("kulunut", "huono"):
        parts.append(f"🩹 kunto: {r['cond']}")
    return " · ".join(parts)


def for_dict(d: dict) -> dict:
    src = d.get("source") or "sellpy"
    if src in ("brändi", "haku"):
        src = "sellpy"
    return assess(d.get("brand", ""), d.get("category", ""), float(d.get("price") or 0), float(d.get("value") or 0),
                  d.get("title", ""), "", src, d.get("condition", ""))


# ---------------------------------------------------------------- report
def _platform_of(d):
    host = (d.get("link") or "").split("/")[2] if "//" in (d.get("link") or "") else ""
    return host.replace("www.", "") or "?"


def report(paths=("data/finds.json",), out="data/RISK.md"):
    rows = []
    for p in paths:
        fp = ROOT / p
        if not fp.exists():
            continue
        data = json.loads(fp.read_text(encoding="utf-8"))
        rows += data["items"] if isinstance(data, dict) else data
    seen, items = set(), []
    for d in rows:
        if d.get("id") in seen:
            continue
        seen.add(d.get("id"))
        d = dict(d)
        d["_r"] = for_dict(d)
        items.append(d)
    n = len(items)

    def share(xs, pred):
        return f"{sum(1 for x in xs if pred(x)) / len(xs):.0%}" if xs else "-"

    hi = lambda x: x["_r"]["fake_level"] == "korkea"  # noqa: E731
    mid = lambda x: x["_r"]["fake_level"] == "keski"  # noqa: E731
    worn = lambda x: x["_r"]["cond"] in ("kulunut", "huono")  # noqa: E731
    unk = lambda x: x["_r"]["cond"] == "?"  # noqa: E731
    L = [f"# Feikki- ja kuntoriski löydöissä\n", f"{n} löytöä ({', '.join(paths)}). Heuristiikka: risk.py.\n",
         f"- korkea feikkiriski: **{share(items, hi)}**, keskitaso: {share(items, mid)}",
         f"- kulunut/huono kunto: **{share(items, worn)}**, kunto ei tiedossa: {share(items, unk)}\n",
         "## Alustoittain\n", "| alusta | n | feikki korkea | keski | kulunut/huono | kunto ? |", "|---|---|---|---|---|---|"]
    by = collections.defaultdict(list)
    for x in items:
        by[_platform_of(x)].append(x)
    for k, xs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        L.append(f"| {k} | {len(xs)} | {share(xs, hi)} | {share(xs, mid)} | {share(xs, worn)} | {share(xs, unk)} |")
    L += ["\n## Kategorioittain\n", "| kategoria | n | feikki korkea+keski | kulunut/huono |", "|---|---|---|---|"]
    by = collections.defaultdict(list)
    for x in items:
        by[x.get("category", "?")].append(x)
    for k, xs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        L.append(f"| {k} | {len(xs)} | {share(xs, lambda x: hi(x) or mid(x))} | {share(xs, worn)} |")
    L += ["\n## Brändit, joissa eniten feikkiriskiä (n ≥ 3)\n", "| brändi | n | feikki korkea+keski | kulunut/huono |",
          "|---|---|---|---|"]
    by = collections.defaultdict(list)
    for x in items:
        by[(x.get("brand") or "").split(" · ")[0]].append(x)
    ranked = sorted(((k, xs) for k, xs in by.items() if len(xs) >= 3),
                    key=lambda kv: -sum(1 for x in kv[1] if hi(x) or mid(x)) / len(kv[1]))
    for k, xs in ranked[:25]:
        L.append(f"| {k} | {len(xs)} | {share(xs, lambda x: hi(x) or mid(x))} | {share(xs, worn)} |")
    L += ["\n## Riskisimmät löydöt\n"]
    for x in sorted(items, key=lambda x: -x["_r"]["fake"])[:20]:
        L.append(f"- {x['_r']['fake']} · [{x.get('title')}]({x.get('link')}) {x.get('price', 0):.0f} € "
                 f"(arvio {x.get('value')} €) — {'; '.join(x['_r']['why'])}")
    (ROOT / out).write_text("\n".join(L) + "\n", encoding="utf-8")
    return items


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        report(tuple(sys.argv[2:]) or ("data/finds.json",))
