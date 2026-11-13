#!/usr/bin/env python3
"""Sharp pictures for the Grail Atlas.

The Atlas artifact cannot load remote images (CSP), so its pictures ship with the page.
scan.py keeps a 120 px thumb for every candidate (instant placeholder); this script adds
HIRES_PX pictures for the finds people actually open: every other-marketplace find plus the
best Sellpy finds by score. They are packed 4x4 into WebP sheets so the artifact stays under
its 511-file limit.

  python hires.py OUTDIR    -> OUTDIR/h0.webp, h1.webp, ... + OUTDIR/index.json {id: [sheet, cell]}

The workflow "Atlas images" force-pushes OUTDIR to the orphan branch `atlas-images`
(one commit, no history), so the main branch does not grow by tens of MB per run.
"""
from __future__ import annotations

import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image

import sniper as S

HIRES_PX = 360   # a phone card is ~180 css px at 2x density, a desktop card ~250 css px
GRID = 4         # 4x4 = 16 pictures per sheet
QUALITY = 72


def fetch(session: requests.Session, url: str):
    try:
        r = session.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 grail-atlas"})
        if r.status_code != 200:
            return None
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        w, h = im.size
        m = min(w, h)
        im = im.crop(((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m))
        return im.resize((HIRES_PX, HIRES_PX), Image.LANCZOS) if m >= HIRES_PX else im.resize((HIRES_PX, HIRES_PX), Image.BICUBIC)
    except Exception:
        return None


def pick(cfg: dict) -> list[dict]:
    n = int(cfg["settings"].get("atlas_hires", 4000))
    scan = S.load_json(S.DATA / "scan.json", {"items": []})["items"]
    markets = S.load_json(S.DATA / "markets_scan.json", {"items": []})["items"]
    best = sorted(scan, key=lambda d: -d.get("score", 0))[:n]
    seen, out = set(), []
    for d in markets + best:  # markets first: few, and their 120 px source thumbs are the worst
        if d.get("image") and d["id"] not in seen:
            seen.add(d["id"])
            out.append(d)
    return out


def main(outdir: str):
    cfg = S.load_yaml("config.yaml")
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("h*.webp"):
        f.unlink()
    items = pick(cfg)
    S.log(f"hires: fetching {len(items)} pictures at {HIRES_PX}px")
    s = requests.Session()
    with ThreadPoolExecutor(16) as pool:
        ims = list(pool.map(lambda d: fetch(s, d["image"]), items))
    got = [(d, im) for d, im in zip(items, ims) if im is not None]
    per = GRID * GRID
    index, size = {}, 0
    for k in range(0, len(got), per):
        sheet = Image.new("RGB", (HIRES_PX * GRID, HIRES_PX * GRID), (220, 222, 220))
        for n, (d, im) in enumerate(got[k:k + per]):
            sheet.paste(im, ((n % GRID) * HIRES_PX, (n // GRID) * HIRES_PX))
            index[d["id"]] = [k // per, n]
        p = out / f"h{k // per}.webp"
        sheet.save(p, "WEBP", quality=QUALITY, method=6)
        size += p.stat().st_size
    (out / "index.json").write_text(json.dumps({"generated": S.now_ts(), "px": HIRES_PX, "grid": GRID,
                                                "items": index}, separators=(",", ":")))
    S.log(f"hires: {len(got)}/{len(items)} pictures in {(len(got) + per - 1) // per} sheets, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "atlas-images")
