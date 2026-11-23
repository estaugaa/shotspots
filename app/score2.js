/* Scoring v2: score = conditions x spot quality (x access, applied in rankFor via drive time).
   Conditions: the light/weather fit from the rest of the model, with fame left out (0-100).
   Quality (0-1): fame from Wikipedia links and views, photo and sighting counts and photographer stands, for every spot alike.
   Multiplier 0.5 + 0.625q: an unknown spot keeps half its light score, the most famous 112%.
   So an unknown spot in great light (90 -> 45) beats a famous one in poor light (30 -> 34) but not in fair light (50 -> 56).
   Access: inside the chosen travel range distance is only a tie-breaker: rankFor orders by score x (1 - 0.1 x share of the range used).
   Night and the Wildlife filter keep v1: darkness and animals decide those. Settings key ss2:scorev = "1" switches back. */
let SCORE_V = 2;
try { if (localStorage.getItem("ss2:scorev") === "1") SCORE_V = 1; } catch (e) { }
// Quality is measured the same way for every spot, hand-researched or not (photo and sighting counts, Wikipedia, photographer
// stands): how much research a spot has had must not decide its rank. Hand spots get their counts from feed/handpop.json.
let HANDPOP = null;
fetch("feed/handpop.json").then(r => r.ok ? r.json() : null).then(j => { HANDPOP = j || {}; for (const s of SPOTS) setHandPop(s); if (typeof lateRender === "function") lateRender(); }).catch(() => { HANDPOP = {}; });
function setHandPop(s) { const p = HANDPOP && HANDPOP[s.id]; if (p && !s.seed && s.pop == null) { s.pop = p[0]; s.refs = { commons: p[1], flickr: p[2], inat: p[3] }; } }
// Photo quality counts photos only: iNaturalist sightings measure naturalist activity, not how photogenic a view is
// (a rhododendron garden with 2,878 sightings and 6 photos looked as famous as Multnomah Falls). The Wildlife filter keeps v1.
function viewFame(s) {
  if (!s.refs) return seedFame(s);
  const pop = 1.5 * Math.log2(1 + (s.refs.commons || 0)) + 1.2 * Math.log2(1 + (s.refs.flickr || 0));
  const save = s.pop; s.pop = pop; const f = seedFame(s); s.pop = save; return f;
}
// A spot with no photo or Wikipedia record at all is unknown, not bad: it gets the median quality of recorded spots near you.
function hasRecord(s) { return !!(s.score || s.views || (s.refs && (s.refs.commons || s.refs.flickr)) || (s.pop != null && s.seed) || (s._stand && s._stand.u)); }
// frozen per place once 200 recorded spots are loaded: recomputing as each tile of spots arrived made near-ties flip and
// the top card swap back and forth while the page loaded (smoke test, Nov 17)
let __qMed = { k: "", v: 0.3, n: 0 };
function medianQuality() {
  const k = LOC ? LOC.lat.toFixed(1) + "," + LOC.lon.toFixed(1) : ""; if (__qMed.k === k && __qMed.n >= 200) return __qMed.v;
  const qs = SPOTS.filter(s => hasRecord(s) && !tooFar(s)).map(s => clamp((viewFame(s) + 2) / 12, 0, 1)).sort((a, b) => a - b);
  __qMed = { k, v: qs.length >= 20 ? Math.round(qs[qs.length >> 1] * 100) / 100 : 0.3, n: qs.length }; return __qMed.v;
}
// Photographers (feed/spotphotos.json, pipeline/spotphotos.py): distinct Commons photographers within 500 m (900 m for peaks),
// counted the same way for every spot. ~30 is fully famous (Multnomah 29, Vista House 24, Haystack Rock 18); city spots
// count fully only if they stand out from their surroundings (lift >= 15x the 5 km ring), so Times Square and a convention
// centre don't win on crowds. Not in the feed = nobody photographs the area: unknown, median of measured spots nearby.
// undefined: feed not loaded (old measure); null: unknown here; else 0..1. (Nov 23: replaced the hand-spot-only Commons
// counts, which put Haystack Rock level with an unknown waterfall.)
function photoQ(s) {
  const f = fd("spotphotos"); if (!f || !f.spots) return undefined;
  const v = f.spots[s.id]; if (!v) return null;
  const eff = v[0] * Math.min(1, v[1] / 150);
  return v[0] ? clamp(Math.log2(1 + eff) / Math.log2(31), 0.1, 1) : 0.05;
}
let __pqMed = { k: "", v: 0.3, n: 0 };
function photoMedian() {
  const k = LOC ? LOC.lat.toFixed(1) + "," + LOC.lon.toFixed(1) : ""; if (__pqMed.k === k && __pqMed.n >= 200) return __pqMed.v;
  const qs = SPOTS.filter(s => !tooFar(s)).map(photoQ).filter(q => q != null).sort((a, b) => a - b);
  __pqMed = { k, v: qs.length >= 20 ? Math.round(qs[qs.length >> 1] * 100) / 100 : 0.3, n: qs.length }; return __pqMed.v;
}
function spotQuality(s) {
  if (!s.seed && s.pop == null) setHandPop(s);
  const pq = photoQ(s);
  const q = pq === undefined ? (hasRecord(s) ? clamp((viewFame(s) + 2) / 12, 0, 1) : medianQuality()) : pq === null ? photoMedian() : pq;
  return /landmark|bridge/.test(s.kind || "") ? q * 0.75 : q;   // Wikipedia-famous buildings are not automatically photo spots
}
const _fitV1 = fitFor;
fitFor = function (s, w) {
  const f = _fitV1(s, w);
  if (!f || SCORE_V !== 2 || w.kind === "night" || UI.group === "life") return f;
  const q = spotQuality(s);
  const m = PREFS.fame === "lesser" ? 1.05 - 0.35 * q : TUNE.qMin + (TUNE.qMax - TUNE.qMin) * q;   // lesser-known: unknown 1.05, most photographed 0.70
  const life = lifeLed(s) ? TUNE.wildlifeOutside : 1;   // outside the Wildlife filter, lists lead with views: a refuge's sunset sky counts, a bit less (Eric, Nov 16)
  return { ...f, n: Math.round(clamp(f.n * m * life, 0, 100)), q, light: f.n, qm: m * life };
};

/* ---- "Why this score": the arithmetic, on the spot page, and on every card in test mode (#math in the URL) ---- */
let SCORE_MATH = false; try { SCORE_MATH = localStorage.getItem("ss2:math") === "1"; } catch (e) { }
(function () { if (/#math\b/.test(location.hash)) { const on = !SCORE_MATH; SCORE_MATH = on; try { localStorage.setItem("ss2:math", on ? "1" : "0"); } catch (e) { }
  history.replaceState(null, "", location.pathname); setTimeout(() => typeof toast === "function" && toast(on ? "Score math shown on cards" : "Score math hidden"), 900); } })();
function qualityText(s) {
  const bits = [], r = s.refs || {};
  if (r.commons) bits.push(`${r.commons} Wikimedia photos`); if (r.flickr) bits.push(`${r.flickr} Flickr photos`);
  if (s.views) bits.push(`${s.views >= 1000 ? Math.round(s.views / 1000) + "k" : s.views} Wikipedia views a year`);
  if (s.score) bits.push("Wikipedia/Wikidata links"); if (s._stand && s._stand.u) bits.push(`${s._stand.u} photographers' positions`);
  if (/landmark|bridge/.test(s.kind || "")) bits.push("buildings count 25% less");
  return bits.length ? bits.join(", ") + (PREFS.fame === "lesser" ? " (you favor lesser-known spots, so this counts against it)" : "") : "no photo or Wikipedia record: counted as a typical spot nearby";
}
function distFactor(s) { const d = driveMin(s); return 1 - TUNE.distance * Math.min(1, d / Math.max(1, maxTravel())); }
function mathLine(f, s) {
  if (f.light == null) return "";
  return `Light ${Math.round(f.light)} × spot ${f.qm.toFixed(2)} = ${f.n}; list order × ${distFactor(s).toFixed(2)} for distance`;
}
const _pickRowM = pickRow;
pickRow = function (x, w) {
  let h = _pickRowM(x, w); if (!x.f || x.f.light == null) return h.replace(/(<span class="score [^"]*">)(\d+)(<\/span>)/, `$1$2<small class="lt">&nbsp;</small>$3`);   // same height either way
  // the light score under the overall number, so "good light, little-known spot" doesn't read as a bad evening
  h = h.replace(/(<span class="score [^"]*">)(\d+)(<\/span>)/, `$1$2<small class="lt" title="Light and weather score">light ${Math.round(x.f.light)}</small>$3`);
  if (!SCORE_MATH) return h;
  return h.replace(/<\/small><\/span>\s*<span class="drive">/, `</small><small class="math">${esc(mathLine(x.f, x.s))}</small></span><span class="drive">`);
};
const _openSpotM = openSpot;
openSpot = function (id) {
  _openSpotM(id);
  const s = byId[id], b = $("#sheetBody"); if (!s || !b || b.querySelector(".scoremath")) return;
  const ws = allWindows(LOC, PLAN_HOURS), w = ws[UI.focus] || ws[0]; if (!w) return;
  const f = fitFor(s, w); if (!f) return;
  const wl = (w.label || w.kind).replace(/^\w/, c => c.toUpperCase());
  const parts = f.light == null ? `<p>${f.n} for ${esc(wl)}. Night and the Wildlife filter score on conditions alone.</p>`
    : `<p><b>${f.n}</b> for ${esc(wl)} = light and weather <b>${Math.round(f.light)}</b> × spot <b>${f.qm.toFixed(2)}</b></p>
       <p class="muted">Spot ${f.qm.toFixed(2)} (${PREFS.fame === "lesser" ? "1.05 little-known to 0.70 most photographed" : "0.50 least to 1.12 most photographed"}): ${esc(qualityText(s))}. In the list, distance trims up to 10% (× ${distFactor(s).toFixed(2)} here).</p>`;
  const L = scoreLayers(s, w).filter((x, i) => i === 0 || (x.delta != null && (x.delta !== 0 || x.add.length)));
  const steps = L.map((x, i) => `<li><b>${x.n == null ? "-" : x.n}</b> ${esc(x.label)}${i && x.delta ? ` <span class="${x.delta > 0 ? "up" : "dn"}">(${x.delta > 0 ? "+" : ""}${x.delta}${x.mult ? `, ×${x.mult.toFixed(2)}` : ""})</span>` : ""}${x.add.length ? `<br><small>${x.add.map(esc).join("; ")}</small>` : ""}</li>`).join("");
  b.insertAdjacentHTML("beforeend", `<div class="scoremath"><h3>Why this score</h3>${parts}<ol class="layers">${steps}</ol></div>`);
  if (typeof orderSpotPage === "function") { b._ordered = false; orderSpotPage(); }
};

/* ---- Score layers, in one place. Each file that adjusts the score wraps fitFor; the function each file captured is the
   score up to that point. SCORE_LAYERS names them in order, so the breakdown, tests and tuning can see what each layer
   did to a spot's score. Add new layers here when a file wraps fitFor. ---- */
const SCORE_LAYERS = [
  ["Light and weather for this kind of spot", () => _fitFor],
  ["Wildlife sightings, tides, live reports", () => _fitSky],
  ["Night sky", () => _fitFeed],
  ["Hourly colour model, fog, satellite, terrain sun times", () => _fitAl],
  ["Alerts and closures", () => _fitAc],
  ["Access: roads, trails, permits", () => _fitExtras],
  ["Smoke, haze, surf, peaks hidden", () => _fitHours],
  ["Opening hours", () => _fitNC],
  ["Live airport report", () => _fitV1],
  ["Spot quality (photographers here)", () => _fitQ],
  ["When photographers shoot here", () => fitFor],
];
function scoreLayers(s, w) {
  const out = []; let prevN = null, prevWhy = [];
  for (const [label, get] of SCORE_LAYERS) {
    let f = null; try { f = get()(s, w); } catch (e) { noteErr("why this score: a layer", e); }
    if (!f) { out.push({ label, n: null, delta: null, add: [] }); continue; }
    const add = f.why.filter(x => !prevWhy.includes(x));
    out.push({ label, n: f.n, delta: prevN == null ? null : f.n - prevN, add, mult: label.startsWith("Spot quality") && f.qm ? f.qm : null });
    prevN = f.n; prevWhy = f.why;
  }
  return out;
}
