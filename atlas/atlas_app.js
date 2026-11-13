// ================= Grail Atlas app =================
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const eur = n => (Math.round(n * 10) / 10).toLocaleString("fi-FI") + "\u202f€";
const eur0 = n => Math.round(n).toLocaleString("fi-FI") + "\u202f€";
const num = n => Number(n).toLocaleString("fi-FI");
const xs = s => "×" + (s >= 10 ? Math.round(s) : String(Math.round(s * 10) / 10).replace(".", ","));
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};
const sstore = {
  get(k) { try { return JSON.parse(sessionStorage.getItem(k) || "null"); } catch (e) { return null; } },
  set(k, v) { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};

const M = D.meta, ITEMS = D.items, GD = M.gd || {}, BG = M.bg || {};
const BYID = new Map(ITEMS.map(i => [i.id, i]));
const LOGIC = new Map(D.logic.map(b => [b.n, b]));
const TIERS = { S: "S · grail", A: "A · vahva", B: "B · hyvä", C: "C · vain halvalla", D: "D · ei katetta", "": "Ei tasoa" };
const TIER_ORD = { S: 0, A: 1, B: 2, C: 3, D: 4, "": 5 };

// ---------- derived fields
const LETTERS = ["XXS", "XS", "S", "S/M", "M", "M/L", "L", "L/XL", "XL", "XL/XXL", "XXL", "2XL", "XXXL", "3XL", "4XL", "5XL"];
function psz(sz) {
  sz = (sz || "").trim();
  if (!sz || sz === "-") return ["", ""];
  if (/^one ?size$/i.test(sz)) return ["One size", "Muut"];
  const m = sz.match(/^([A-Z]+)-([A-Z]+)(?:_([A-Z]+))?-(.+)$/);
  if (!m) return [sz, /^(\d?X*[SML]|X+L)(\/.*)?$/i.test(sz) ? "Kirjainkoot" : "Muut"];
  const [, who, sys, sub, v0] = m, v = v0.replace(".", ",");
  if (who === "SHOES") return [sys === "CM" ? v + " cm" : "EU " + v, "Kengät"];
  if (who === "HATS") return [sys === "CM" ? v + " cm" : v, "Päähineet"];
  if (who === "BELTS") return [sys === "CM" ? v + " cm" : v, "Vyöt"];
  if (who === "PANTS") return ["W" + v, "Housut, tuumat"];
  if (who === "SOCKS") return ["sukat " + v, "Muut"];
  if (who === "RINGS") return ["sormus " + v, "Muut"];
  if (who === "GLOVES") return ["hanskat " + v, "Muut"];
  if (sys === "INT") return [v.replace(/^(\d)XL/, "$1XL"), who === "WMN" ? "Kirjainkoot (naiset)" : "Kirjainkoot"];
  if (sub === "COLLAR") return [v, "Kauluspaidat, kaulus cm"];
  if (sub === "BRA") return [v, "Muut"];
  if (sub) return [v, "Puvut, pitkä/lyhyt"];
  return [v, who === "WMN" ? "EU-koot (naiset)" : "EU-koot (miehet)"];
}
const SZ_GROUPS = ["Kirjainkoot", "Kirjainkoot (naiset)", "EU-koot (miehet)", "EU-koot (naiset)", "Housut, tuumat", "Kauluspaidat, kaulus cm", "Puvut, pitkä/lyhyt", "Kengät", "Päähineet", "Vyöt", "Muut"];
const szRank = l => { const k = LETTERS.indexOf(l.toUpperCase()); if (k >= 0) return k; const n = parseFloat(l.replace(/^\D+/, "").replace(",", ".")); return isNaN(n) ? 999 : 100 + n; };
function labClass(l) { return l.includes("INSANE") ? "insane" : l.includes("KOVA") ? "kova" : l.includes("HARVINAINEN") ? "rare" : l.includes("📉") ? "drop" : "diili"; }
const cleanPf = s => s.replace(/[^\p{L}\p{N} .-]/gu, "").trim();
ITEMS.forEach(i => {
  i.lab = labClass(i.l); i.labt = i.l.replace(/^[^A-ZÄÖ📉]+/u, "").replace("📉", "").trim();
  i.tier = (GD[i.bn] || {}).t || "";
  const [pl, pg] = psz(i.sz); i.ps = pl; i.szk = pl ? pg + "|" + pl : "";
  i.pfn = cleanPf(i.pf);
  i.bd = i.b.split(" · ")[0];
});
const txt = i => i._t || (i._t = [i.b, i.rb, i.t, i.pf, i.bn, i.ps, i.c, i.cp.join(" "), i.why.join(" ")].join(" ").toLowerCase());

// ---------- "new since your last visit": ids this browser had not seen before
let NEW = new Set(), FIRST = false;
(function () {
  const cur = ITEMS.map(i => i.id), ses = sstore.get("atlas-new-v2");
  if (ses) { NEW = new Set(ses.ids.filter(id => BYID.has(id))); FIRST = !!ses.first; return; }
  const prev = store.get("atlas-seen-v2", null);
  if (prev && prev.ids) { const p = new Set(prev.ids.split(",")); cur.forEach(id => { if (!p.has(id)) NEW.add(id); }); }
  else FIRST = true;
  sstore.set("atlas-new-v2", { ids: [...NEW], first: FIRST });
  store.set("atlas-seen-v2", { at: Date.now(), ids: cur.join(",") });
})();

// ---------- saved finds (this browser only)
let SAVED = store.get("atlas-saved-v1", {}) || {};
function toggleSave(id) {
  const i = BYID.get(id);
  if (SAVED[id]) { delete SAVED[id]; toast("Poistettu tallennetuista"); }
  else if (i) { SAVED[id] = { b: i.bd, t: i.t, p: i.p, v: i.v, u: i.u, pf: i.pfn, at: Date.now() }; toast("Tallennettu, löytyy Tallessa-sivulta"); }
  store.set("atlas-saved-v1", SAVED);
  $$(`[data-save="${CSS.escape(id)}"]`).forEach(b => b.setAttribute("aria-pressed", !!SAVED[id]));
  savedBadge();
  if (UI.view === "saved") renderSaved();
}
function savedBadge() { const n = Object.keys(SAVED).length; $$("[data-savedn]").forEach(b => b.textContent = n || ""); }
let toastT;
function toast(m) { const t = $("#toast"); t.textContent = m; t.classList.add("on"); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("on"), 2200); }

// ---------- pictures: 120 px sprite tile at once, sharp 360 px WebP when it scrolls near
const G = M.grid || 10, H = M.hi && M.hi.grid;
const ppos = (n, g) => (n * 100 / (g - 1)).toFixed(4) + "%";
function pic(i, label) {
  let h = "";
  if (i.im) h += `<span class="spr" style="background-image:url(img/s${i.im[0]}.jpg);background-size:${G * 100}% ${G * 100}%;background-position:${ppos(i.im[1] % G, G)} ${ppos(Math.floor(i.im[1] / G), G)}"></span>`;
  if (i.hi && H) h += `<span class="spr hi" data-bg="hi/h${i.hi[0]}.webp" style="background-size:${H * 100}% ${H * 100}%;background-position:${ppos(i.hi[1] % H, H)} ${ppos(Math.floor(i.hi[1] / H), H)}"></span>`;
  return `<span class="pic" role="img" aria-label="${esc(label || i.bd + " " + i.t)}">${h || `<span class="noimg">ei kuvaa</span>`}</span>`;
}
const hiLoaded = new Set();
const hiIO = "IntersectionObserver" in window ? new IntersectionObserver(es => es.forEach(e => {
  if (!e.isIntersecting) return; hiIO.unobserve(e.target); loadHi(e.target);
}), { rootMargin: "500px 500px" }) : null;
function loadHi(el) {
  const u = el.dataset.bg; el.style.backgroundImage = `url(${u})`;
  if (hiLoaded.has(u)) { el.classList.add("on"); return; }
  const im = new Image();
  im.onload = () => { hiLoaded.add(u); $$(`.spr.hi[data-bg="${u}"]`).forEach(x => x.style.backgroundImage && x.classList.add("on")); };
  im.src = u;
}
function watchHi(root) { $$(".spr.hi:not(.on)", root).forEach(el => hiIO ? hiIO.observe(el) : loadHi(el)); }
function unwatchHi(root) { if (hiIO) $$(".spr.hi", root).forEach(el => hiIO.unobserve(el)); }

// ---------- hang-tag card
function meter(i) {
  const pct = Math.min(100, i.p / Math.max(i.v, 1) * 100);
  return `<div class="meter ${pct < 35 ? "" : pct < 60 ? "mid" : "hi"}" title="Hinta on ${Math.round(pct)} % arviosta"><i style="width:${Math.max(2, pct).toFixed(1)}%"></i></div>`;
}
function riskTags(i) {
  const r = i.rk; if (!r) return "";
  return (r[1] === "korkea" ? `<span class="rh">feikkiriski ${r[0]}</span>` : r[1] === "keski" ? `<span class="rm">feikkiriski ${r[0]}</span>` : "")
    + (r[2] === "kulunut" || r[2] === "huono" ? `<span class="rm">${esc(r[2])}</span>` : "");
}
function card(i) {
  return `<article class="card"><button type="button" class="open" data-open="${esc(i.id)}" aria-label="${esc(i.bd)}: ${esc(i.t)}, ${eur(i.p)}">${pic(i)}${NEW.has(i.id) ? `<span class="newp">UUSI</span>` : ""}<span class="stamp L-${i.lab}">${esc(i.labt)}</span></button>
<button type="button" class="heart" data-save="${esc(i.id)}" aria-pressed="${!!SAVED[i.id]}" aria-label="Tallenna"><svg viewBox="0 0 24 24"><use href="#i-heart"/></svg></button>
<div class="tagb"><h3 class="brand">${esc(i.bd)}</h3><div class="ttl">${esc(i.t)}</div>
<div class="pr"><b>${eur(i.p)}</b><s>${eur0(i.v)}</s><span class="x">${xs(i.s)}</span></div>${meter(i)}
<div class="meta">${i.ps ? `<span class="sz">${esc(i.ps)}</span>` : ""}<span>${esc(i.pfn)}</span>${i.pr > 0 ? `<span class="gain">+${Math.round(i.pr)} €</span>` : ""}${i.pick ? `<span class="pk">kuraattori</span>` : ""}${riskTags(i)}</div>
<a class="go" href="${esc(i.u)}" target="_blank" rel="noopener">Avaa ${esc(i.pfn)} ↗</a></div></article>`;
}

// ================= state =================
const DEF = () => ({ lanes: [], plats: [], brands: [], tiers: [], sizes: [], cat: [], g: "", pmin: "", pmax: "", fit: true,
  rare: false, strict: false, nofake: false, noworn: false, pick: false, fresh: false, profit: false, q: "", sort: "s" });
const SORTS = { s: "Paras diili ensin", ts: "Uusin ensin", p: "Halvin ensin", v: "Arvokkain ensin", pr: "Isoin kate ensin" };
const PAGE = 60;
let F = DEF();
const UI = { view: "home", n: PAGE, scroll: {}, bmode: "g", bd: { q: "", sort: "t", tiers: [] } };
const SKEY = "atlas-state-v2";
function save() { store.set(SKEY, { F, UI }); }
let restoring = true;
function saveScroll() { if (restoring) return; if (UI.view && !stack.length) UI.scroll[UI.view] = scrollY; save(); }
function restore() {
  let o = store.get(SKEY, null);
  if (!o) { // first visit to the new site: carry the old Atlas filters over
    const v1 = store.get("atlas-state-v1", null);
    if (v1 && v1.v) {
      const v = v1.v, f = DEF();
      if (v["#q"]) f.q = v["#q"]; if (v["#plat"]) f.plats = [v["#plat"]]; if (v["#gender"]) f.g = v["#gender"];
      if (v["#sort"] && SORTS[v["#sort"]]) f.sort = v["#sort"]; if (v["#maxp"]) f.pmax = v["#maxp"];
      ["fit", "rare", "strict", "nofake", "noworn"].forEach(k => { if (v["#" + k] !== undefined) f[k] = !!v["#" + k]; });
      if (v1.lane) f.lanes = [v1.lane]; if (Array.isArray(v1.brands)) f.brands = v1.brands;
      if (Array.isArray(v1.cat)) f.cat = v1.cat.filter(Boolean);
      o = { F: f, UI: { view: "finds" } };
    }
  }
  if (!o) return;
  const d = DEF(), f = o.F || {};
  for (const k in d) if (f[k] !== undefined && typeof f[k] === typeof d[k] && Array.isArray(f[k]) === Array.isArray(d[k])) F[k] = f[k];
  const has = (k, fn) => { F[k] = F[k].filter(x => ITEMS.some(i => fn(i, x))); };
  has("lanes", (i, x) => i.lane === x); has("plats", (i, x) => i.pf === x); has("brands", (i, x) => i.bn === x);
  has("sizes", (i, x) => i.szk === x); F.tiers = F.tiers.filter(t => t in TIERS);
  if (F.cat.length && !ITEMS.some(i => inCat(i, F.cat.join(" > ")))) F.cat = [];
  if (!SORTS[F.sort]) F.sort = "s";
  const u = o.UI || {};
  if (u.n > PAGE) UI.n = Math.min(u.n, 3000);
  if (u.scroll && typeof u.scroll === "object") UI.scroll = u.scroll;
  if (u.view) UI.view = u.view;
  if (u.bmode) UI.bmode = u.bmode;
  if (u.bd) UI.bd = { ...UI.bd, ...u.bd };
}
const inCat = (i, pre) => !pre || i.cp.some(p => p === pre || p.startsWith(pre + " > "));

// ================= finds: faceted filtering =================
let R = { res: [], near: {} };
function compute() {
  const S = k => new Set(F[k]), pre = F.cat.join(" > "), preds = [];
  if (F.lanes.length) { const s = S("lanes"); preds.push(["lanes", i => s.has(i.lane)]); }
  if (F.plats.length) { const s = S("plats"); preds.push(["plats", i => s.has(i.pf)]); }
  if (F.brands.length) { const s = S("brands"); preds.push(["brands", i => s.has(i.bn)]); }
  if (F.tiers.length) { const s = S("tiers"); preds.push(["tiers", i => s.has(i.tier)]); }
  if (F.sizes.length) { const s = S("sizes"); preds.push(["sizes", i => s.has(i.szk)]); }
  if (pre) preds.push(["cat", i => inCat(i, pre)]);
  if (F.g) preds.push(["g", i => !i.g || i.g === F.g]);
  const lo = parseFloat(F.pmin), hi = parseFloat(F.pmax);
  if (!isNaN(lo) || !isNaN(hi)) preds.push(["price", i => (isNaN(lo) || i.p >= lo) && (isNaN(hi) || i.p <= hi)]);
  if (F.fit) preds.push(["fit", i => i.fit]);
  if (F.rare) preds.push(["rare", i => i.rare]);
  if (F.strict) preds.push(["strict", i => i.s >= M.min_score || i.rare]);
  if (F.nofake) preds.push(["nofake", i => !i.rk || i.rk[1] !== "korkea"]);
  if (F.noworn) preds.push(["noworn", i => !i.rk || (i.rk[2] !== "kulunut" && i.rk[2] !== "huono")]);
  if (F.pick) preds.push(["pick", i => i.pick]);
  if (F.fresh) preds.push(["fresh", i => NEW.has(i.id)]);
  if (F.profit) preds.push(["profit", i => i.pr > 0]);
  const terms = F.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length) preds.push(["q", i => { const t = txt(i); return terms.every(w => t.includes(w)); }]);
  const res = [], near = {};
  for (const i of ITEMS) {
    let n = 0, fk = null;
    for (const [k, f] of preds) if (!f(i)) { if (++n > 1) break; fk = k; }
    if (!n) res.push(i); else if (n === 1) (near[fk] = near[fk] || []).push(i);
  }
  const key = { s: i => -i.s, p: i => i.p, v: i => -i.v, pr: i => -(i.pr || 0), ts: i => -i.ts }[F.sort];
  res.sort((a, b) => key(a) - key(b) || b.s - a.s);
  R = { res, near };
}
// items that pass every filter except facet k (so its options show honest counts)
const facetBase = k => R.near[k] ? R.res.concat(R.near[k]) : R.res;
function countBy(k, get) { const c = {}; facetBase(k).forEach(i => { const v = get(i); if (v !== "" && v != null) c[v] = (c[v] || 0) + 1; }); return c; }
const ALL = { lanes: {}, plats: {} };
ITEMS.forEach(i => { ALL.lanes[i.lane] = (ALL.lanes[i.lane] || 0) + 1; ALL.plats[i.pf] = (ALL.plats[i.pf] || 0) + 1; });
const byCount = o => Object.keys(o).sort((a, b) => o[b] - o[a]);

// ---------- filter panel (built once; only the option lists re-render)
const TOGS = {
  fit: ["Vain mun koot", "L ja isommat, vyötärö ~100 cm, kengät 43–45. Laukut ja one size näkyy aina."],
  nofake: ["Piilota korkea feikkiriski", "Riskibrändit yksityisiltä myyjiltä ja epäilyttävän halvat."],
  noworn: ["Piilota kuluneet", "Kuntoarvio kulunut tai huono kuvauksen ja kuntoluokan perusteella."],
  rare: ["Vain harvinaiset", "Harvinaiset brändit tai sanat kuten runway, sample, artisanal."],
  strict: ["Vain hälytystaso", ""],
  profit: ["Vain kun kate plussalla", "Myyntiarvio Grailed/Vinted/Vestiaire miinus kulut ja posti."],
  fresh: ["Vain uudet", "Ilmestyneet sitten edellisen käyntisi tällä selaimella."],
  pick: ["Vain kuraattorin poiminnat", ""],
};
TOGS.strict[1] = `Pisteet vähintään ${String(M.min_score).replace(".", ",")}, eli hinta enintään puolet arviosta.`;
const tog = k => `<label class="tog"><span>${TOGS[k][0]}${TOGS[k][1] ? `<small>${esc(TOGS[k][1])}</small>` : ""}</span><input type="checkbox" class="sw" data-f="${k}"></label>`;
$("#fbody").innerHTML = `
<div class="fg"><h3>Kategoria <button type="button" data-clear="cat">tyhjennä</button></h3><div id="f-cat"></div></div>
<div class="fg"><h3>Brändit <button type="button" data-clear="brands">tyhjennä</button></h3><div class="selb" id="f-bsel"></div><button type="button" class="btn sm" id="bopen">Valitse brändejä</button></div>
<div class="fg"><h3>Koko <button type="button" data-clear="sizes">tyhjennä</button></h3>${tog("fit")}<div id="f-sizes"></div></div>
<div class="fg"><h3>Hinta</h3><div class="price2"><input type="number" id="pmin" inputmode="decimal" min="0" placeholder="min €" aria-label="Vähimmäishinta"><span class="mono">–</span><input type="number" id="pmax" inputmode="decimal" min="0" placeholder="max €" aria-label="Enimmäishinta"></div></div>
<div class="fg"><h3>Brändin taso <button type="button" data-clear="tiers">tyhjennä</button></h3><div class="chips" id="f-tiers"></div></div>
<div class="fg"><h3>Tyyli <button type="button" data-clear="lanes">tyhjennä</button></h3><div class="chips" id="f-lanes"></div></div>
<div class="fg"><h3>Alusta <button type="button" data-clear="plats">tyhjennä</button></h3><div class="chips" id="f-plats"></div></div>
<div class="fg"><h3>Osasto</h3><div class="chips" id="f-g"></div></div>
<div class="fg"><h3>Kunto ja aitous</h3>${tog("nofake")}${tog("noworn")}</div>
<div class="fg"><h3>Erikoiset</h3>${tog("rare")}${tog("strict")}${tog("profit")}${tog("fresh")}${tog("pick")}</div>
<div class="fg" style="border:0"><button type="button" class="btn" data-reset style="width:100%">Nollaa filtterit</button></div>`;

const chip = (fk, v, label, n, on) => `<button type="button" class="chip" data-fk="${fk}" data-fv="${esc(v)}" aria-pressed="${on}"${!n && !on ? " disabled" : ""}>${esc(label)}<small>${n || 0}</small></button>`;
function renderPanel() {
  // category tree
  const cc = {}, deeper = {}, d = F.cat.length, pre = F.cat.join(" > ");
  facetBase("cat").forEach(i => {
    const seen = new Set();
    i.cp.forEach(p => {
      if (pre && !p.startsWith(pre + " > ")) return;
      const seg = p.split(" > ");
      const s = seg[d]; if (!s || seen.has(s)) return;
      seen.add(s); cc[s] = (cc[s] || 0) + 1; if (seg.length > d + 1) deeper[s] = 1;
    });
  });
  const tot = facetBase("cat").filter(i => inCat(i, pre)).length;
  $("#f-cat").innerHTML = `<div class="crumbs">${d ? `<button type="button" data-cat="0">Kaikki</button>` : `<b>Kaikki</b>`}${F.cat.map((c, k) =>
    `<span>›</span>${k < d - 1 ? `<button type="button" data-cat="${k + 1}">${esc(c)}</button>` : `<b>${esc(c)}</b>`}`).join("")}<span class="count" style="margin-left:6px">${tot}</span></div>
    <div class="tree">${byCount(cc).map(s => `<button type="button" data-catin="${esc(s)}"><span>${esc(s)}${deeper[s] ? ` <span class="chev">›</span>` : ""}</span><small>${cc[s]}</small></button>`).join("")
    || `<p class="count" style="margin:4px 0">Alin taso. Palaa ylemmäs yläpuolen polusta.</p>`}</div>`;
  // brands
  $("#f-bsel").innerHTML = F.brands.map(b => `<button type="button" class="chip x" aria-pressed="true" data-fk="brands" data-fv="${esc(b)}">${esc(b)}</button>`).join("");
  $("#bopen").textContent = F.brands.length ? "Muokkaa valintaa" : "Valitse brändejä";
  // sizes grouped by sizing system
  const sc = countBy("sizes", i => i.szk), groups = {};
  new Set([...Object.keys(sc), ...F.sizes]).forEach(k => { const [g, l] = k.split("|"); (groups[g] = groups[g] || []).push(l); });
  $("#f-sizes").innerHTML = SZ_GROUPS.filter(g => groups[g]).map(g => `<div class="sizek">${esc(g)}</div><div class="chips">${groups[g].sort((a, b) => szRank(a) - szRank(b) || a.localeCompare(b, "fi"))
    .map(l => chip("sizes", g + "|" + l, l, sc[g + "|" + l], F.sizes.includes(g + "|" + l))).join("")}</div>`).join("") || `<p class="count">Ei kokotietoa näillä suodattimilla.</p>`;
  // tiers, lanes, platforms, gender
  const tc = countBy("tiers", i => i.tier || "-");
  $("#f-tiers").innerHTML = ["S", "A", "B", "C", "D"].map(t => chip("tiers", t, TIERS[t], tc[t], F.tiers.includes(t))).join("") + chip("tiers", "", "Ei tasoa", tc["-"], F.tiers.includes(""));
  const lc = countBy("lanes", i => i.lane);
  $("#f-lanes").innerHTML = byCount(ALL.lanes).map(l => chip("lanes", l, l.replace("Muut alustat: ", ""), lc[l], F.lanes.includes(l))).join("");
  const pc = countBy("plats", i => i.pf);
  $("#f-plats").innerHTML = byCount(ALL.plats).map(p => chip("plats", p, p, pc[p], F.plats.includes(p))).join("");
  const gc = countBy("g", i => i.g), gb = facetBase("g");
  $("#f-g").innerHTML = [["", "Kaikki", gb.length], ["Miehet", "Miehet", (gc.Miehet || 0) + gb.filter(i => !i.g).length], ["Naiset", "Naiset", (gc.Naiset || 0) + gb.filter(i => !i.g).length]]
    .map(([v, l, n]) => `<button type="button" class="chip" data-g="${v}" aria-pressed="${F.g === v}">${l}<small>${n}</small></button>`).join("");
  // toggles + price (don't touch an input while it's focused)
  $$("[data-f]").forEach(c => c.checked = !!F[c.dataset.f]);
  ["pmin", "pmax"].forEach(k => { const el = $("#" + k); if (document.activeElement !== el) el.value = F[k]; });
  $("#fshow").textContent = `Näytä ${num(R.res.length)} löytöä`;
}
const QUICK = [["fit", "Mun koot"], ["fresh", "Uudet"], ["rare", "Harvinaiset"], ["profit", "Kate plussalla"], ["nofake", "Ei feikkiriskiä"]];
function renderQuick() {
  const q = $("#quick");
  if (!q.firstChild) q.innerHTML = `<select id="sort" aria-label="Järjestys">${Object.entries(SORTS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>`
    + QUICK.map(([k, l]) => `<button type="button" class="chip" data-qt="${k}">${l}${k === "fresh" ? ` <small>${NEW.size}</small>` : ""}</button>`).join("")
    + `<span class="count" id="count" style="margin-left:auto;padding-left:8px"></span>`;
  $("#sort").value = F.sort;
  QUICK.forEach(([k]) => $(`[data-qt="${k}"]`).setAttribute("aria-pressed", !!F[k]));
  $('[data-qt="fresh"]').hidden = !NEW.size && !F.fresh;
  $("#count").textContent = `${num(R.res.length)} / ${num(ITEMS.length)}`;
  if (document.activeElement !== $("#q")) $("#q").value = F.q;
}
function activeList() {
  const a = [], d = DEF();
  if (F.q.trim()) a.push(["q", "", `”${F.q.trim()}”`]);
  if (F.cat.length) a.push(["cat", "", F.cat.join(" › ")]);
  F.brands.forEach(b => a.push(["brands", b, b]));
  F.sizes.forEach(s => a.push(["sizes", s, "koko " + s.split("|")[1]]));
  F.tiers.forEach(t => a.push(["tiers", t, t ? "taso " + t : "ei tasoa"]));
  F.lanes.forEach(l => a.push(["lanes", l, l.replace("Muut alustat: ", "")]));
  F.plats.forEach(p => a.push(["plats", p, p]));
  if (F.g) a.push(["g", "", F.g]);
  if (F.pmin !== "") a.push(["pmin", "", `vähintään ${F.pmin} €`]);
  if (F.pmax !== "") a.push(["pmax", "", `enintään ${F.pmax} €`]);
  Object.keys(TOGS).forEach(k => { if (F[k] !== d[k]) a.push(["tog", k, k === "fit" ? "kaikki koot" : TOGS[k][0].replace(/^Vain /, "").replace(/^Piilota /, "ei: ")]); });
  return a;
}
function renderActive() {
  const a = activeList();
  $("#active").innerHTML = a.length ? a.map(([k, v, l]) => `<button type="button" class="chip x" data-rm="${k}" data-rv="${esc(v)}" title="Poista suodatin">${esc(l)}</button>`).join("")
    + `<button type="button" class="chip" data-reset>Nollaa filtterit</button>` : "";
  $("#fcount").textContent = a.length || "";
}
let shown = 0;
function renderGrid(reset) {
  const g = $("#grid"), list = R.res;
  if (reset) {
    unwatchHi(g);
    g.innerHTML = list.length ? list.slice(0, UI.n).map(card).join("")
      : `<div class="empty" style="grid-column:1/-1"><b>Ei osumia näillä suodattimilla.</b><span>Kokeile poistaa joku suodatin yläpuolelta.</span><button type="button" class="btn sm" data-reset>Nollaa filtterit</button></div>`;
    shown = Math.min(UI.n, list.length);
  } else if (shown < Math.min(UI.n, list.length)) {
    g.insertAdjacentHTML("beforeend", list.slice(shown, UI.n).map(card).join(""));
    shown = Math.min(UI.n, list.length);
  }
  watchHi(g);
  $("#more").hidden = list.length <= UI.n;
}
function update(opts = {}) {
  compute();
  renderPanel(); renderQuick(); renderActive();
  UI.n = PAGE; renderGrid(true);
  if (!opts.keepScroll && UI.view === "finds") {
    const top = $("#v-finds").getBoundingClientRect().top + scrollY;
    if (scrollY > top) scrollTo(0, top);
  }
  save();
}
// infinite scroll + button fallback
function moreRows() { if (shown >= R.res.length) return; UI.n = shown + PAGE; renderGrid(false); save(); }
$("#more").addEventListener("click", moreRows);
if ("IntersectionObserver" in window) new IntersectionObserver(es => { if (es[0].isIntersecting && UI.view === "finds") moreRows(); }, { rootMargin: "900px 0px" }).observe($("#sentinel"));

// panel events
$("#fbody").addEventListener("change", e => { const c = e.target.closest("[data-f]"); if (c) { F[c.dataset.f] = c.checked; update(); } });
let priceT;
["pmin", "pmax"].forEach(k => $("#" + k).addEventListener("input", e => { clearTimeout(priceT); priceT = setTimeout(() => { F[k] = e.target.value.trim(); update({ keepScroll: true }); }, 350); }));
let qT;
$("#q").addEventListener("input", e => { clearTimeout(qT); qT = setTimeout(() => { F.q = e.target.value; update(); }, 200); });
$("#q").addEventListener("keydown", e => { if (e.key === "Enter") e.target.blur(); });
$("#quick").addEventListener("change", e => { if (e.target.id === "sort") { F.sort = e.target.value; update(); } });
function openPanel() { $("#fpanel").classList.add("open"); lockScroll(true); pushLayer(closePanel); }
function closePanel() { $("#fpanel").classList.remove("open"); if (!stack.length) lockScroll(false); }
$("#fbtn").addEventListener("click", openPanel);
$("#fclose").addEventListener("click", () => popLayer());
$("#fshow").addEventListener("click", () => popLayer());

// ---------- brand picker (multi-select; grouped by style / tier / A–Ö)
function openBrandPicker() {
  const w = openSheet(`<div class="ctl"><input type="search" id="bq" placeholder="Hae brändiä…" aria-label="Hae brändiä" autocomplete="off">
    <select id="bgrp" aria-label="Ryhmittely"><option value="g">Tyylin mukaan</option><option value="t">Tason mukaan S–D</option><option value="a">A–Ö</option></select></div>
    <div id="blist"></div><div class="foot"><button type="button" class="btn" id="bnone">Tyhjennä</button><button type="button" class="btn ink" data-close>Valmis</button></div>`,
  { label: "Valitse brändit", cls: "bp" });
  $("#bgrp", w).value = UI.bmode;
  const draw = () => {
    const q = $("#bq", w).value.trim().toLowerCase(), mode = $("#bgrp", w).value, cnt = countBy("brands", i => i.bn), groups = {};
    new Set([...Object.keys(cnt), ...F.brands]).forEach(n => {
      if (q && !n.toLowerCase().includes(q)) return;
      const [g] = BG[n] || ["Muut"], t = (GD[n] || {}).t || "";
      const k = mode === "t" ? t : mode === "a" ? (n[0] || "#").toUpperCase() : g;
      (groups[k] = groups[k] || []).push(n);
    });
    const size = k => groups[k].reduce((x, n) => x + (cnt[n] || 0), 0);
    const order = mode === "t" ? ["S", "A", "B", "C", "D", ""] : Object.keys(groups).sort((a, b) => mode === "a" ? a.localeCompare(b, "fi") : size(b) - size(a));
    const keep = $(".sbody", w).scrollTop;
    $("#blist", w).innerHTML = order.filter(k => groups[k]).map(k => {
      const ns = groups[k].sort((a, b) => a.localeCompare(b, "fi")), all = ns.every(n => F.brands.includes(n));
      return `<div class="bgroup"><h4><span>${esc(mode === "t" ? TIERS[k] : k)}</span><button type="button" data-grp="${esc(JSON.stringify(ns))}">${all ? "poista kaikki" : "valitse kaikki"}</button></h4><div class="bopts">${ns.map(n => {
        const t = (GD[n] || {}).t;
        return `<label class="bopt"><input type="checkbox" value="${esc(n)}"${F.brands.includes(n) ? " checked" : ""}><span class="n">${esc(n)}</span>${t ? `<span class="tier sm T-${t}">${t}</span>` : ""}<small>${cnt[n] || 0}</small></label>`;
      }).join("")}</div></div>`;
    }).join("") || `<p class="empty">Ei brändiä haulla ”${esc(q)}”.</p>`;
    $(".sbody", w).scrollTop = keep;
    $("[data-close].btn", w).textContent = `Valmis · ${num(R.res.length)} löytöä`;
  };
  draw();
  $("#bq", w).addEventListener("input", draw);
  $("#bgrp", w).addEventListener("input", () => { UI.bmode = $("#bgrp", w).value; save(); draw(); });
  $("#blist", w).addEventListener("change", e => {
    const c = e.target.closest("input[type=checkbox]"); if (!c) return;
    F.brands = c.checked ? [...F.brands, c.value] : F.brands.filter(b => b !== c.value); update({ keepScroll: true }); draw();
  });
  $("#blist", w).addEventListener("click", e => {
    const b = e.target.closest("button[data-grp]"); if (!b) return;
    const ns = JSON.parse(b.dataset.grp), all = ns.every(n => F.brands.includes(n));
    F.brands = all ? F.brands.filter(n => !ns.includes(n)) : [...new Set([...F.brands, ...ns])]; update({ keepScroll: true }); draw();
  });
  $("#bnone", w).addEventListener("click", () => { F.brands = []; update({ keepScroll: true }); draw(); });
  if (matchMedia("(min-width:761px)").matches) $("#bq", w).focus({ preventScroll: true });
}
$("#bopen").addEventListener("click", openBrandPicker);

// ================= layers: sheets + mobile filter panel, closed by ✕, Esc or the phone's back gesture =================
const stack = []; let popSkip = 0;
function lockScroll(on) { document.documentElement.style.overflow = on ? "hidden" : ""; }
function pushLayer(close) {
  const L = { close, pushed: false };
  try { history.pushState({ atlasLayer: stack.length + 1 }, ""); L.pushed = true; } catch (e) {}
  stack.push(L); return L;
}
function popLayer(fromPop) {
  const L = stack.pop(); if (!L) return;
  L.close();
  if (!stack.length && !$("#fpanel").classList.contains("open")) lockScroll(false);
  if (!fromPop && L.pushed) { popSkip++; history.back(); }
}
addEventListener("popstate", () => {
  if (popSkip) { popSkip--; fixHash(); return; }
  if (stack.length) popLayer(true);
  fixHash();
});
// the entry we step back to may carry an older #view; keep the address on the view that is showing
function fixHash() { if (UI.view && location.hash.slice(1) !== UI.view) try { history.replaceState(history.state, "", "#" + UI.view); } catch (e) {} }
function openSheet(html, { label, cls } = {}) {
  const w = document.createElement("div");
  w.className = "sheetwrap " + (cls || ""); w.style.zIndex = 50 + stack.length * 2;
  w.innerHTML = `<div class="scrim" data-close></div><div class="sheet" role="dialog" aria-modal="true" aria-label="${esc(label)}">
    <div class="sbar"><button type="button" class="iconbtn" data-close aria-label="Sulje"><svg class="i"><use href="#i-x"/></svg></button><span class="eyebrow">${esc(label)}</span></div>
    <div class="sbody">${html}</div></div>`;
  $("#sheets").append(w); lockScroll(true);
  requestAnimationFrame(() => requestAnimationFrame(() => w.classList.add("in")));
  pushLayer(() => { unwatchHi(w); w.classList.remove("in"); setTimeout(() => w.remove(), 230); });
  watchHi(w);
  $(".sbar [data-close]", w).focus({ preventScroll: true });
  return w;
}
function closeAll() { while (stack.length) popLayer(); }
document.addEventListener("keydown", e => { if (e.key === "Escape" && stack.length) { e.preventDefault(); popLayer(); } });

// ---------- item page
function scaleHTML(i) {
  const max = Math.max(i.v, i.p) * 1.02, lim = i.v / M.min_score, P = x => Math.min(100, x / max * 100);
  const pp = P(i.p), anchor = pp < 14 ? "l" : pp > 86 ? "r" : "";
  return `<div class="scale" aria-label="Hinta ${eur(i.p)}, hälytysraja ${eur0(lim)}, arvio ${eur0(i.v)}">
    <div class="lbl"><span class="${anchor}" style="left:${pp}%;color:var(--ink);font-weight:600">maksat ${eur(i.p)}</span></div>
    <div class="track"><div class="base"></div><div class="fill" style="width:${pp}%"></div><div class="mk lim" style="left:${P(lim)}%"></div><div class="mk" style="left:${pp}%"></div><div class="mk lim" style="left:${P(i.v)}%"></div></div>
    <div class="lbl"><span class="l" style="left:0">0 €</span><span style="left:${P(lim)}%">hälytysraja ${eur0(lim)}</span><span class="r" style="left:${P(i.v)}%">arvio ${eur0(i.v)}</span></div></div>`;
}
const dots = (n, max, cls = "") => `<span class="dots ${cls}">${Array.from({ length: max }, (_, k) => `<i class="${k < n ? "on" : ""}"></i>`).join("")}</span>`;
function ratings(g) {
  return `<div class="ratings"><span>hype ${dots(g.h || 0, 5)}</span><span>laatu ${dots(g.q || 0, 5)}</span><span>feikkiriski ${dots(g.f || 0, 3, "f")}</span></div>`;
}
function guideFields(g) {
  return [["status", "Tilanne nyt"], ["good", "Vahvuudet"], ["bad", "Heikkoudet"], ["buy", "Osta näitä"], ["avoid", "Vältä"], ["tells", "Tunnista aito ja koko"]]
    .filter(([k]) => g[k]).map(([k, l]) => `<div class="gfield ${k}"><b>${l}</b><p>${esc(g[k])}</p></div>`).join("");
}
const fmtDate = ts => { if (!ts) return "–"; const d = new Date(ts * 1000), days = Math.floor((Date.now() - d) / 864e5);
  return d.toLocaleDateString("fi-FI") + (days <= 0 ? " (tänään)" : days === 1 ? " (eilen)" : days < 60 ? ` (${days} pv sitten)` : ""); };
function openItem(id) {
  const i = BYID.get(id); if (!i) return;
  const g = GD[i.bn], rk = i.rk, lim = i.v / M.min_score;
  const sim = ITEMS.filter(x => x.bn === i.bn && x.id !== i.id).sort((a, b) => b.s - a.s).slice(0, 10);
  const facts = [
    ["Koko", i.ps ? `${esc(i.ps)} <span class="${i.fit ? "c-ok" : "c-bad"}">${i.fit ? "· sopii sulle" : "· ei sun koko"}</span>` : "ei kokoa (näkyy aina)"],
    ["Kunto (myyjä)", esc(i.cd !== "-" ? i.cd : "ei kerrottu")],
    ["Kuntoarvio", rk ? `<span class="${rk[2] === "ok" ? "c-ok" : rk[2] === "?" ? "c-meh" : "c-bad"}">${esc(rk[2] === "?" ? "ei tiedossa" : rk[2])}</span>` : "–"],
    ["Feikkiriski", rk ? `<span class="${rk[1] === "korkea" ? "c-bad" : rk[1] === "keski" ? "c-meh" : "c-ok"}">${rk[0]}/100 · ${esc(rk[1])}</span>` : "–"],
    ["Kategoria", esc(i.cp[0].replace(/ > /g, " › "))],
    ["Osasto", esc(i.g || "–")],
    ["Alusta", esc(i.pf)],
    ["Listattu", fmtDate(i.ts)],
    ["Pisteet", `${xs(i.s)} <span class="${i.s >= M.min_score ? "c-ok" : "c-meh"}">${i.s >= M.min_score ? "· hälytystaso" : "· alle hälytysrajan"}</span>`],
    ...(i.o ? [["Valmistettu", esc(i.o)]] : []),
    ...(i.rb && i.rb !== i.bn ? [["Myyjän brändi", esc(i.rb)]] : []),
  ];
  const w = openSheet(`
  <div class="ihead">${pic(i)}
    <div class="info"><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><span class="stamp L-${i.lab}">${esc(i.labt)}</span>${NEW.has(i.id) ? `<span class="newp" style="position:static">UUSI</span>` : ""}${i.tier ? `<span class="tier T-${i.tier}" title="Brändin taso">${i.tier}</span>` : ""}</div>
      <h2><button type="button" data-brand="${esc(i.bn)}">${esc(i.bd)}</button></h2><p class="t">${esc(i.t)}</p>
      <div class="bigprice"><b>${eur(i.p)}</b><s>arvio ${eur0(i.v)}</s><span class="x">${xs(i.s)}</span></div>
      ${scaleHTML(i)}
      <div class="acts"><a class="btn pri" href="${esc(i.u)}" target="_blank" rel="noopener">Avaa ${esc(i.pfn)} <svg class="i"><use href="#i-ext"/></svg></a>
        <button type="button" class="btn heart-btn" data-save="${esc(i.id)}" aria-pressed="${!!SAVED[i.id]}"><svg class="i"><use href="#i-heart"/></svg>Tallenna</button></div>
    </div></div>
  ${i.pr != null ? `<div class="panelc"><h3>Jälleenmyynti</h3><p style="margin:0">${i.pr > 0 ? `<b class="c-ok">Kate noin ${eur0(i.pr)}</b>` : `<b class="c-meh">Ei katetta myyntiin (${eur0(i.pr)})</b>`}${i.rs ? `, kun myyt ${esc(i.ex || "eteenpäin")} noin ${eur0(i.rs)} hintaan.` : "."} Laskelmassa on mukana alustan kulut, tinkimisvara ja posti. Pidät itse? Silloin ratkaisee hinta suhteessa arvioon: maksat ${Math.round(i.p / i.v * 100)} % arviosta, hälytysraja on ${eur0(lim)}.</p></div>` : ""}
  <div class="panelc"><h3>Tiedot</h3><dl class="facts">${facts.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl></div>
  ${i.why.length ? `<div class="panelc"><h3>Miksi tämä nousi</h3><ul class="why">${i.why.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
  ${g ? `<div class="panelc"><h3><span class="tier T-${g.t}">${g.t}</span>${esc(i.bn)}: brändiopas</h3>${ratings(g)}${guideFields(g)}<div><button type="button" class="btn sm" data-brand="${esc(i.bn)}">Koko brändisivu</button></div></div>` : ""}
  ${sim.length ? `<div class="sec" style="padding:0"><div class="sechead"><h2>Muut ${esc(i.bn)}-löydöt</h2><button type="button" class="link" data-showbrand="${esc(i.bn)}">Näytä kaikki →</button></div><div class="rail">${sim.map(card).join("")}</div></div>` : ""}`,
  { label: `${i.labt} · ${i.pfn}`, cls: "item" });
  return w;
}
// ---------- brand page
function brandStats(n) {
  const f = ITEMS.filter(i => i.bn === n).sort((a, b) => b.s - a.s);
  return { f, top: f.find(i => i.hi) || f[0] };
}
function openBrand(n) {
  const g = GD[n], L = LOGIC.get(n), { f } = brandStats(n), lane = (BG[n] || [])[0] || (L && L.lane) || "";
  const kw = { ...(g && g.kw || {}), ...(L && L.bo || {}) };
  const facts = [["Löytöjä nyt", num(f.length)], ...(f.length ? [["Paras diili", xs(f[0].s)], ["Halvin", eur(Math.min(...f.map(i => i.p)))]] : []),
    ...(L ? [["Arvio (perus)", eur0(L.v)], ["Diiliraja", eur0(L.lim)], ["Sellpyssä myynnissä", L.cnt != null ? num(L.cnt) + " kpl" : "–"], ["Sellpy-mediaani", L.med != null ? eur(L.med) : "–"]] : []),
    ...(L && L.mn ? [["Minimihinta", eur0(L.mn)]] : [])];
  openSheet(`<div class="bhead"><span class="eyebrow">${esc(lane)}${L && L.r ? " · harvinainen" : ""}</span>
    <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">${g ? `<span class="tier T-${g.t}" style="width:40px;height:40px;font-size:22px">${g.t}</span>` : ""}<h2>${esc(n)}</h2></div>
    ${g ? ratings(g) : ""}
    ${f.length ? `<div class="acts"><button type="button" class="btn ink" data-showbrand="${esc(n)}">Näytä kaikki ${num(f.length)} löytöä</button></div>` : ""}</div>
    <div class="panelc"><h3>Numerot</h3><dl class="facts">${facts.map(([k, v]) => `<div><dt>${k}</dt><dd class="mono">${v}</dd></div>`).join("")}</dl>
      <p class="count" style="margin:0">Diiliraja = arvo ÷ ${String(M.min_score).replace(".", ",")}. Yleisillä brändeillä hinnan pitää myös olla alle Sellpy-mediaani × ${String(M.median_factor).replace(".", ",")}.</p></div>
    ${g || (L && L.note) ? `<div class="panelc"><h3>Brändiopas</h3>${L && L.note ? `<div class="gfield"><b>Kuraattorin huomio</b><p>${esc(L.note)}</p></div>` : ""}${g ? guideFields(g) : ""}</div>` : ""}
    ${Object.keys(kw).length || (L && (L.a.length || L.sp.length)) ? `<div class="panelc"><h3>Haku ja kertoimet</h3>
      ${Object.keys(kw).length ? `<div class="gfield"><b>Mallisanat, jotka nostavat arviota</b><div class="kw">${Object.entries(kw).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<span>${esc(k)} ×${String(v).replace(".", ",")}</span>`).join("")}</div></div>` : ""}
      ${L && L.a.length ? `<div class="gfield"><b>Aliakset</b><p>${esc(L.a.join(", "))}</p></div>` : ""}
      ${L && L.sp.length ? `<div class="gfield"><b>Sellpyn kirjoitusasut</b><p>${esc(L.sp.slice(0, 14).join(", "))}</p></div>` : ""}</div>` : ""}
    ${f.length ? `<div class="sec" style="padding:0"><div class="sechead"><h2>Parhaat löydöt</h2>${f.length > 12 ? `<button type="button" class="link" data-showbrand="${esc(n)}">Kaikki ${num(f.length)} →</button>` : ""}</div><div class="grid">${f.slice(0, 12).map(card).join("")}</div></div>`
      : `<p class="empty">Tältä brändiltä ei ole löytöjä juuri nyt. Skanneri hälyttää, kun hinta alittaa diilirajan.</p>`}`,
  { label: "Brändi", cls: "brand" });
}

// ================= views =================
const VIEWS = ["home", "finds", "brands", "picks", "saved", "logic"];
const rendered = {};
function go(v, { scroll = "restore" } = {}) {
  if (!VIEWS.includes(v)) v = "home";
  closeAll();
  if (UI.view && !$("#v-" + UI.view).hidden) UI.scroll[UI.view] = scrollY;
  UI.view = v;
  VIEWS.forEach(x => $("#v-" + x).hidden = x !== v);
  $$("nav [data-nav]").forEach(b => (b.getAttribute("data-nav") === v ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")));
  if (v === "home" && !rendered.home) renderHome();
  if (v === "brands" && !rendered.brands) renderBrands();
  if (v === "picks" && !rendered.picks) renderPicks();
  if (v === "logic" && !rendered.logic) renderLogic();
  if (v === "saved") renderSaved();
  watchHi($("#v-" + v));
  if (location.hash.slice(1) !== v) try { history.replaceState(history.state, "", "#" + v); } catch (e) {}
  const y = scroll === "top" ? 0 : (UI.scroll[v] || 0);
  requestAnimationFrame(() => scrollTo(0, y));
  save();
}
addEventListener("hashchange", () => { const h = location.hash.slice(1); if (VIEWS.includes(h) && h !== UI.view) go(h); });

// jump into finds with a preset (keeps sort and size filter, clears the rest)
function preset(p) {
  const keep = { sort: F.sort, fit: F.fit };
  F = { ...DEF(), ...keep, ...p };
  update({ keepScroll: true });
  go("finds", { scroll: "top" });
}

// ---------- home
function rail(list) { return `<div class="rail">${list.map(card).join("")}</div>`; }
function renderHome() {
  rendered.home = 1;
  const fitOk = i => i.fit && (!i.rk || i.rk[1] !== "korkea");
  const top = ITEMS.filter(fitOk).sort((a, b) => b.s - a.s).slice(0, 14);
  const fresh = NEW.size ? ITEMS.filter(i => NEW.has(i.id)).sort((a, b) => b.s - a.s).slice(0, 14) : ITEMS.filter(fitOk).sort((a, b) => b.ts - a.ts).slice(0, 14);
  const prof = ITEMS.filter(i => fitOk(i) && i.pr > 0).sort((a, b) => b.pr - a.pr).slice(0, 14);
  const rare = ITEMS.filter(i => i.rare && fitOk(i)).sort((a, b) => b.s - a.s).slice(0, 14);
  const picks = ITEMS.filter(i => i.pick);
  const insane = ITEMS.filter(i => i.lab === "insane").length;
  // category tiles: 2nd level for clothes/accessories, top level for the rest
  const cats = {};
  ITEMS.forEach(i => { const seen = new Set(); i.cp.forEach(p => { const s = p.split(" > "), k = (s[0] === "Vaatteet" || s[0] === "Asusteet") && s[1] ? s.slice(0, 2).join(" > ") : s[0];
    if (k === "Muut" || seen.has(k)) return; seen.add(k); (cats[k] = cats[k] || []).push(i); }); });
  const tiles = Object.entries(cats).sort((a, b) => b[1].length - a[1].length).slice(0, 12);
  const plats = byCount(ALL.plats), pmax = ALL.plats[plats[0]];
  const sbr = Object.keys(GD).filter(n => GD[n].t === "S").map(n => [n, ITEMS.filter(i => i.bn === n)]).filter(x => x[1].length).sort((a, b) => b[1].length - a[1].length).slice(0, 12);
  const sz = M.sizes || {};
  $("#v-home").innerHTML = `
  <div class="hero">
    <span class="eyebrow">Sellpy skannattu ${esc(M.generated)}${M.markets_generated ? ` · muut alustat ${esc(M.markets_generated)}` : ""}</span>
    <h1>Grail <em>Atlas</em></h1>
    <p class="lede">Skanneri käy läpi Sellpyn, Torin, Huuto.netin, Traderan ja viisi muuta pohjoismaista second hand -alustaa ja nostaa esiin designer-kappaleet, joiden hinta on selvästi alle jälleenmyyntiarvon. <b>${num(ITEMS.length)} ehdokasta</b> on pisteytetty arviota vasten, ja sun koot on suodatettu valmiiksi.</p>
    <div class="kpis">
      <div class="kpi"><b class="mono">${num(ITEMS.length)}</b><span>löytöä nyt</span></div>
      <div class="kpi"><b class="mono" style="color:var(--risk)">${num(insane)}</b><span>INSANE-diiliä (arvio ≥ 4 × hinta)</span></div>
      <div class="kpi"><b class="mono">${num(new Set(ITEMS.map(i => i.bn)).size)}</b><span>brändiä, ${num(M.brands)} seurannassa</span></div>
      <div class="kpi"><b class="mono" style="color:var(--accent)">${num(NEW.size)}</b><span>${FIRST ? "uutta (1. käynti)" : "uutta sitten viime käynnin"}</span></div>
    </div>
    <div class="cta"><button type="button" class="btn ink" data-nav="finds">Selaa löytöjä</button><button type="button" class="btn" data-preset='{"sort":"s","strict":true,"nofake":true}'>Vain hälytystason diilit</button>${NEW.size ? `<button type="button" class="btn" data-preset='{"fresh":true}'>Uudet (${num(NEW.size)})</button>` : ""}</div>
  </div>
  <div class="sec"><div class="sechead"><div><h2>${NEW.size ? "Uutta sitten viime käynnin" : "Uusimmat ilmoitukset"}</h2><p>${NEW.size ? "Löydöt, joita tämä selain ei ole ennen nähnyt, parhaat ensin." : FIRST ? "Ensimmäinen käynti tällä selaimella. Ensi kerralla tässä näkyy vain se, mikä on tullut lisää." : "Ei uusia löytöjä viime käynnin jälkeen. Tässä tuoreimmat listaukset."}</p></div>
    <button type="button" class="link" data-preset='${NEW.size ? '{"fresh":true}' : '{"sort":"ts"}'}'>Näytä kaikki →</button></div>${rail(fresh)}</div>
  <div class="sec"><div class="sechead"><div><h2>Kovimmat diilit</h2><p>Korkein arvio ÷ hinta, sun koot, korkea feikkiriski karsittu.</p></div><button type="button" class="link" data-preset='{"sort":"s","nofake":true}'>Näytä kaikki →</button></div>${rail(top)}</div>
  ${prof.length ? `<div class="sec"><div class="sechead"><div><h2>Isoin kate</h2><p>Myyntiarvio Grailedissa, Vintedissä tai Vestiairessa miinus kulut, tinkiminen ja posti.</p></div><button type="button" class="link" data-preset='{"sort":"pr","profit":true}'>Näytä kaikki →</button></div>${rail(prof)}</div>` : ""}
  <div class="sec"><div class="sechead"><div><h2>Kategoriat</h2><p>Sellpyn oma kategoriapuu. Muiden alustojen ilmoitukset on sovitettu samaan puuhun otsikon perusteella.</p></div></div>
    <div class="tiles">${tiles.map(([k, arr]) => { const t = arr.filter(i => i.hi).sort((a, b) => b.s - a.s)[0] || arr[0]; const nm = k.split(" > ").pop();
      return `<button type="button" class="tile" data-preset='${esc(JSON.stringify({ cat: k.split(" > ") }))}'>${pic(t, nm)}<span class="t"><b>${esc(nm)}</b><small>${num(arr.length)}</small></span></button>`; }).join("")}</div></div>
  ${rare.length ? `<div class="sec"><div class="sechead"><div><h2>Harvinaiset</h2><p>Harvinaiset brändit ja sanat (runway, sample, artisanal, object dyed…) hälyttävät jo, kun hinta on suunnilleen arvon verran.</p></div><button type="button" class="link" data-preset='{"rare":true}'>Näytä kaikki →</button></div>${rail(rare)}</div>` : ""}
  ${sbr.length ? `<div class="sec"><div class="sechead"><div><h2>S-tason brändit</h2><p>Grail-taso: likvidi jälleenmyynti ja vahva kysyntä. Avaa brändi nähdäksesi mitä ostaa ja miten aidon tunnistaa.</p></div><button type="button" class="link" data-nav="brands">Kaikki brändit →</button></div>
    <div class="bdir">${sbr.map(([n, arr]) => bcard(n, arr)).join("")}</div></div>` : ""}
  ${picks.length ? `<div class="sec"><div class="sechead"><div><h2>Kuraattorin poiminnat</h2><p>Käsin valitut, perustelu jokaisen kortin takana.</p></div><button type="button" class="link" data-nav="picks">Kaikki →</button></div>${rail(picks)}</div>` : ""}
  <div class="sec"><div class="sechead"><div><h2>Alustat</h2><p>Mistä löydöt tulevat. Ulkomaisten hinnoissa on mukana arvioitu posti Suomeen.</p></div></div>
    <div class="plats">${plats.map(p => `<button type="button" class="plat" data-preset='${esc(JSON.stringify({ plats: [p] }))}'><b>${esc(p)}</b><i>${num(ALL.plats[p])}</i><span class="bar"><u style="width:${(ALL.plats[p] / pmax * 100).toFixed(1)}%"></u></span><span>${p === "Sellpy" ? "skannattu " + esc(M.generated) : "skannattu " + esc(M.markets_generated || "–")}</span></button>`).join("")}</div></div>
  <div class="sec"><div class="sechead"><div><h2>Sun koot</h2><p>”Vain mun koot” on päällä oletuksena. Tuotteet ilman kokoa (laukut, korut, one size) näkyvät aina.</p></div></div>
    <div class="sizebox"><b>Yläosat L+</b><span>miesten INT ${esc(sz["men-int"] || "L")}+, naisten ${esc(sz["wmn-int"] || "XL")}+, EU ${esc((sz["men-eu"] || []).join("–"))}</span>
      <b>Vyötärö ~100 cm</b><span>W${esc((sz["pants-inch"] || []).join("–"))}</span>
      <b>Kengät 43–45</b><span>EU ${esc(String((sz["shoes-eu"] || []).join("–")).replace(".", ","))}, UK ${esc((sz["shoes-uk"] || []).join("–"))}</span></div></div>`;
  watchHi($("#v-home"));
}
function bcard(n, f) {
  const g = GD[n] || {}, L = LOGIC.get(n), t = g.t || "", top = f.filter(i => i.hi).sort((a, b) => b.s - a.s)[0] || f[0];
  const lane = (BG[n] || [])[0] || (L && L.lane) || "";
  return `<button type="button" class="bcard" data-brand="${esc(n)}">${top ? pic(top, n) : `<span class="pic"></span>`}<span style="display:grid;min-width:0">
    <span class="n"><b>${esc(n)}</b>${t ? `<span class="tier sm T-${t}" title="${esc(TIERS[t])}">${t}</span>` : ""}</span>
    <span class="l">${esc(lane)} · ${f.length ? num(f.length) + " löytöä" : "ei löytöjä nyt"}</span>
    ${g.h ? `<span style="margin-top:4px">${ratings(g)}</span>` : ""}
    ${g.status || (L && L.note) ? `<p>${esc(g.status || L.note)}</p>` : ""}</span></button>`;
}

// ---------- brands directory
const BRANDS = (() => {
  const m = new Map();
  D.logic.forEach(b => m.set(b.n, []));
  ITEMS.forEach(i => { if (!m.has(i.bn)) m.set(i.bn, []); m.get(i.bn).push(i); });
  return [...m.entries()].filter(([n]) => n !== "Tuntematon");
})();
function renderBrands() {
  rendered.brands = 1;
  const withF = BRANDS.filter(b => b[1].length).length;
  $("#bintro").textContent = `${num(BRANDS.length)} brändiä, joista ${num(withF)}:lla on löytöjä nyt. Taso kertoo jälleenmyyntiarvon (S grail … D ei katetta). Hype ja laatu 1–5, feikkiriski 0–3.`;
  $("#bdq").value = UI.bd.q; $("#bdsort").value = UI.bd.sort;
  drawBrands();
}
function drawBrands() {
  const q = UI.bd.q.trim().toLowerCase(), ts = new Set(UI.bd.tiers);
  const tc = {}; BRANDS.forEach(([n]) => { const t = (GD[n] || {}).t || ""; tc[t] = (tc[t] || 0) + 1; });
  $("#bdtier").innerHTML = ["S", "A", "B", "C", "D"].map(t => `<button type="button" class="chip" data-bt="${t}" aria-pressed="${ts.has(t)}">${TIERS[t]}<small>${tc[t] || 0}</small></button>`).join("");
  const sk = { f: ([, a], [, b]) => b.length - a.length, a: ([a], [b]) => a.localeCompare(b, "fi"),
    t: ([a, x], [b, y]) => TIER_ORD[(GD[a] || {}).t || ""] - TIER_ORD[(GD[b] || {}).t || ""] || y.length - x.length,
    h: ([a], [b]) => ((GD[b] || {}).h || 0) - ((GD[a] || {}).h || 0) || ((GD[b] || {}).q || 0) - ((GD[a] || {}).q || 0),
    v: ([a], [b]) => ((LOGIC.get(b) || {}).v || 0) - ((LOGIC.get(a) || {}).v || 0) }[UI.bd.sort] || (() => 0);
  const list = BRANDS.filter(([n]) => (!q || n.toLowerCase().includes(q) || ((LOGIC.get(n) || {}).a || []).some(a => a.toLowerCase().includes(q)))
    && (!ts.size || ts.has((GD[n] || {}).t || ""))).sort((a, b) => sk(a, b) || a[0].localeCompare(b[0], "fi"));
  unwatchHi($("#bdir"));
  $("#bdir").innerHTML = list.map(([n, f]) => bcard(n, f)).join("") || `<p class="empty" style="grid-column:1/-1">Ei brändiä haulla.</p>`;
  watchHi($("#bdir"));
}
$("#bdq").addEventListener("input", e => { UI.bd.q = e.target.value; drawBrands(); save(); });
$("#bdsort").addEventListener("input", e => { UI.bd.sort = e.target.value; drawBrands(); save(); });
$("#bdtier").addEventListener("click", e => { const b = e.target.closest("[data-bt]"); if (!b) return; const t = b.dataset.bt;
  UI.bd.tiers = UI.bd.tiers.includes(t) ? UI.bd.tiers.filter(x => x !== t) : [...UI.bd.tiers, t]; drawBrands(); save(); });

// ---------- picks
function renderPicks() {
  rendered.picks = 1;
  const p = ITEMS.filter(i => i.pick), by = {};
  p.forEach(i => (by[i.lane] = by[i.lane] || []).push(i));
  $("#v-picks").innerHTML = `<div class="sec"><div class="sechead"><div><h2>Kuraattorin poiminnat</h2><p>Käsin valitut löydöt. Avaa kortti, niin näet perustelun, kuntoriskin ja brändioppaan.</p></div></div></div>`
    + (p.length ? Object.entries(by).map(([lane, arr]) => `<div class="sec"><div class="sechead"><h2 style="font-size:22px">${esc(lane)}</h2></div><div class="grid">${arr.sort((a, b) => b.s - a.s).map(card).join("")}</div></div>`).join("")
      : `<p class="empty">Ei poimintoja tällä hetkellä.</p>`);
}
// ---------- saved
function renderSaved() {
  const ids = Object.keys(SAVED).sort((a, b) => SAVED[b].at - SAVED[a].at);
  const live = ids.filter(id => BYID.has(id)), gone = ids.filter(id => !BYID.has(id));
  unwatchHi($("#v-saved"));
  $("#v-saved").innerHTML = `<div class="sec"><div class="sechead"><div><h2>Tallessa</h2><p>Sydämellä merkityt löydöt. Ne pysyvät tässä selaimessa, myös kun Atlas päivittyy.</p></div></div></div>`
    + (ids.length ? `<div class="grid">${live.map(id => card(BYID.get(id))).join("")}</div>`
      + (gone.length ? `<div class="sec"><div class="sechead"><div><h2 style="font-size:22px">Poistuneet skannauksesta</h2><p>Myyty tai hinta noussut. Linkki voi vielä toimia.</p></div></div><div class="grid">${gone.map(id => { const s = SAVED[id];
        return `<article class="card"><div class="tagb" style="border-top:0"><h3 class="brand">${esc(s.b)}</h3><div class="ttl">${esc(s.t)}</div><div class="pr"><b>${eur(s.p)}</b>${s.v ? `<s>${eur0(s.v)}</s>` : ""}</div>
          <div class="meta"><span>${esc(s.pf)}</span><span>tallennettu ${new Date(s.at).toLocaleDateString("fi-FI")}</span></div>
          <div style="display:flex;gap:12px;align-items:center"><a class="go" href="${esc(s.u)}" target="_blank" rel="noopener">Avaa ↗</a><button type="button" class="link" data-unsave="${esc(id)}">Poista</button></div></div></article>`; }).join("")}</div></div>` : "")
      : `<div class="empty"><b>Ei vielä tallennettuja.</b><span>Paina kortin sydäntä, niin löytö jää talteen tänne.</span><button type="button" class="btn sm" data-nav="finds">Selaa löytöjä</button></div>`);
  watchHi($("#v-saved"));
}
// ---------- logic
function renderLogic() {
  rendered.logic = 1;
  const tag = s => `<span>${s}</span>`;
  $("#lintro").innerHTML = `
    <h2>Miten löytö pisteytetään</h2>
    <div class="formula">arvio = brändin arvo × tuotetyyppi × kunto × mallisanat<br>pisteet = arvio ÷ hinta</div>
    <p>Hälytys tulee, kun pisteet ovat vähintään <b>${M.min_score}</b>, eli hinta on enintään puolet arviosta. Atlaksessa raja on löysempi (<b>${M.scan_min}</b>), jotta myös hyvähintaiset designer-perusvaatteet näkyvät. Harvinaiset brändit ja harvinaisuussanat hälyttävät jo, kun hinta on suunnilleen arvon verran.</p>
    <p>Yleisillä brändeillä (yli 30 kpl Sellpyssä) hinnan pitää lisäksi olla alle Sellpyn mediaani × ${M.median_factor} × tuotetyypin kerroin. Sellpy hinnoittelee tunnetut brändit järkevästi, joten tämä karsii normaalihintaiset.</p>
    <p>Brändi tunnistetaan tarkasti: Sellpyn kirjoitusasun pitää olla nimi tai alias, tai jatkua tunnetulla alalinjalla (Homme, Plus, Black, x-kollabi). Siksi esim. Julius Zöllner, Loewe Verlag tai Chloe Ting eivät mene läpi.</p>
    <h3>Leimat</h3><div class="kw"><span class="L-insane">INSANE: pisteet 4+</span><span class="L-kova">KOVA DIILI: 2,5+</span><span class="L-diili">DIILI: hälytysrajan tuntumassa</span><span class="L-rare">HARVINAINEN: harvinainen, hinta noin arvon verran</span></div>
    <h3>Feikki- ja kuntoriski</h3><p>Jokainen löytö saa feikkiriskin 0–100 (brändin väärennösaste, alusta, yksityinen myyjä, epäilyttävän halpa hinta, kuvauksen sanat) ja kuntoarvion. Sellpy tarkastaa tuotteet, joten siellä riski on pienin.</p>
    <h3>Tuotetyyppi</h3><div class="kw">${M.categories.map(c => tag(`${esc(c.name)} ×${c.mult}`)).join("")}</div>
    <h3>Kunto</h3><div class="kw">${M.conditions.map(c => tag(`${esc(c.words[0])} ×${c.mult}`)).join("")}</div>
    <h3>Avainsanat kaikille brändeille</h3><div class="kw">${Object.entries(M.gboost).map(([k, v]) => tag(`${esc(k)} ×${v}`)).join("")}</div>
    <h3>Harvinaisuussanat</h3><div class="kw">${M.rare_words.map(w => tag(esc(w))).join("")}${tag("sesonkikoodit AW/SS/FW 90–2012")}</div>
    <h3>Aina pois</h3><div class="kw">${M.exclude.map(w => tag(esc(w))).join("")}${tag("lasten koot")}${tag("alle 10 € brändihaussa")}</div>
    <h3>Väärin listattujen tekstihaut</h3><p>Haetaan ilman brändifiltteriä. Osuma hyväksytään vain, jos sana on tuotteen omissa tiedoissa eikä brändin nimessä. Arvoa kerrotaan 0,85:llä epävarmuuden takia.</p>
    <div class="kw">${M.hunts.map(h => tag(`${esc(h.q)}${h.must ? " (vaatii: " + esc(h.must.join(", ")) + ")" : ""} · ${h.value} €`)).join("")}</div>
    <h3>Brändit (${D.logic.length})</h3><p>Klikkaa sarakkeen otsikkoa järjestääksesi, brändin nimeä avataksesi brändisivun.</p>`;
  const ll = {}; D.logic.forEach(b => ll[b.lane] = 1);
  $("#llane").innerHTML += Object.keys(ll).sort((a, b) => a.localeCompare(b, "fi")).map(l => `<option>${esc(l)}</option>`).join("");
  lrender();
}
let lsk = "lane", lsd = 1;
function lrender() {
  const q = $("#lq").value.trim().toLowerCase(), la = $("#llane").value;
  const val = (b, k) => k === "t" ? TIER_ORD[(GD[b.n] || {}).t || ""] : b[k];
  const r = D.logic.filter(b => (!la || b.lane === la) && (!q || (b.n + " " + b.a.join(" ") + " " + b.sp.join(" ")).toLowerCase().includes(q)))
    .sort((a, b) => { const x = val(a, lsk) ?? -1, y = val(b, lsk) ?? -1; return (x > y ? 1 : x < y ? -1 : a.n.localeCompare(b.n, "fi")) * lsd; });
  $("#lcount").textContent = `${r.length} brändiä`;
  $("#ltable tbody").innerHTML = r.map(b => {
    const t = (GD[b.n] || {}).t || "";
    const rules = [b.r && "harvinainen", b.mn && `min ${b.mn} €`, b.a.length && "aliakset: " + b.a.join(", "),
      Object.keys(b.bo).length && "kertoimet: " + Object.entries(b.bo).map(([k, v]) => `${k} ×${v}`).join(", ")].filter(Boolean);
    return `<tr><td><button type="button" class="link" data-brand="${esc(b.n)}">${esc(b.n)}</button>${b.note ? `<br><small>${esc(b.note)}</small>` : ""}</td>
      <td>${t ? `<span class="tier sm T-${t}">${t}</span>` : "–"}</td><td>${esc(b.lane)}</td>
      <td class="num">${b.v}</td><td class="num">${b.lim}</td><td class="num">${b.cnt ?? "–"}</td><td class="num">${b.med ?? "–"}</td>
      <td><small>${esc(rules.join(" · ")) || "–"}</small></td><td><small>${esc(b.sp.slice(0, 8).join(", ")) || "ei löytynyt"}</small></td></tr>`;
  }).join("");
}
$$("#ltable th button").forEach(th => th.addEventListener("click", () => { const k = th.dataset.k; lsd = lsk === k ? -lsd : 1; lsk = k; lrender(); }));
["#lq", "#llane"].forEach(s => $(s).addEventListener("input", lrender));

// ================= global click handling =================
document.addEventListener("click", e => {
  if (e.target.classList.contains("scrim")) { popLayer(); return; }
  const t = e.target.closest("button,a"); if (!t) return;
  const d = t.dataset;
  if (d.close !== undefined && t.closest(".sheetwrap")) { popLayer(); return; }
  if (d.save) { e.preventDefault(); toggleSave(d.save); return; }
  if (d.unsave) { delete SAVED[d.unsave]; store.set("atlas-saved-v1", SAVED); savedBadge(); renderSaved(); return; }
  if (d.open) { openItem(d.open); return; }
  if (d.brand) { openBrand(d.brand); return; }
  if (d.showbrand) { preset({ brands: [d.showbrand] }); toast(`Näytetään: ${d.showbrand}`); return; }
  if (d.preset) { preset(JSON.parse(d.preset)); return; }
  if (d.nav) { go(d.nav, { scroll: d.nav === UI.view ? "top" : "restore" }); return; }
  if (d.reset !== undefined) { F = { ...DEF(), sort: F.sort }; update(); toast("Filtterit nollattu"); return; }
  if (d.fk) { const k = d.fk, v = d.fv; F[k] = F[k].includes(v) ? F[k].filter(x => x !== v) : [...F[k], v]; update({ keepScroll: t.closest("#fpanel") }); return; }
  if (d.g !== undefined) { F.g = d.g; update({ keepScroll: true }); return; }
  if (d.catin) { F.cat = [...F.cat, d.catin]; update({ keepScroll: true }); return; }
  if (d.cat !== undefined && t.closest("#f-cat")) { F.cat = F.cat.slice(0, +d.cat); update({ keepScroll: true }); return; }
  if (d.clear) { F[d.clear] = []; update({ keepScroll: true }); return; }
  if (d.qt) { F[d.qt] = !F[d.qt]; update(); return; }
  if (d.rm) {
    const k = d.rm, v = d.rv;
    if (k === "q") F.q = ""; else if (k === "cat") F.cat = []; else if (k === "g") F.g = ""; else if (k === "pmin" || k === "pmax") F[k] = "";
    else if (k === "tog") F[v] = DEF()[v]; else F[k] = F[k].filter(x => x !== v);
    update(); return;
  }
});

// ================= boot =================
let scrollT;
addEventListener("scroll", () => { clearTimeout(scrollT); scrollT = setTimeout(saveScroll, 250); }, { passive: true });
addEventListener("pagehide", saveScroll);
document.addEventListener("visibilitychange", () => { if (document.hidden) saveScroll(); });
try { history.scrollRestoration = "manual"; } catch (e) {}
savedBadge();
$("#upd").textContent = M.generated.split(" ")[0];
$("#foot").innerHTML = `<span>Sellpy ${esc(M.generated)}</span>${M.markets_generated ? `<span>muut alustat ${esc(M.markets_generated)}</span>` : ""}<span>${num(ITEMS.length)} löytöä · ${num(M.brands)} brändiä seurannassa</span><span>Arviot ovat skannerin laskelmia. Katso aina kuvat ja lappu ennen ostoa.</span>`;
restore();
compute(); renderPanel(); renderQuick(); renderActive(); renderGrid(true);
const h0 = location.hash.slice(1);
const startView = VIEWS.includes(h0) ? h0 : UI.view;
UI.view = null;
const savedY = UI.scroll[startView] || 0;
go(startView);
// fonts can shift heights a little after the first paint; put the list back where it was if nobody has scrolled yet
setTimeout(() => { if (savedY && scrollY < 50) scrollTo(0, savedY); restoring = false; }, 350);
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { if (restoring && savedY) scrollTo(0, savedY); });
