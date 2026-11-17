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
fetch("feed/handpop.json").then(r => r.ok ? r.json() : null).then(j => { HANDPOP = j || {}; for (const s of SPOTS) setHandPop(s); if (typeof render === "function") render(); }).catch(() => { HANDPOP = {}; });
function setHandPop(s) { const p = HANDPOP && HANDPOP[s.id]; if (p && !s.seed && s.pop == null) { s.pop = p[0]; s.refs = { commons: p[1], flickr: p[2], inat: p[3] }; } }
// Photo quality counts photos only: iNaturalist sightings measure naturalist activity, not how photogenic a view is
// (a rhododendron garden with 2,878 sightings and 6 photos looked as famous as Multnomah Falls). The Wildlife filter keeps v1.
function viewFame(s) {
  if (!s.refs) return seedFame(s);
  const pop = 1.5 * Math.log2(1 + (s.refs.commons || 0)) + 1.2 * Math.log2(1 + (s.refs.flickr || 0));
  const save = s.pop; s.pop = pop; const f = seedFame(s); s.pop = save; return f;
}
function spotQuality(s) {
  if (!s.seed && s.pop == null) setHandPop(s);
  const q = clamp((viewFame(s) + 2) / 12, 0, 1);
  return /landmark|bridge/.test(s.kind || "") ? q * 0.75 : q;   // Wikipedia-famous buildings are not automatically photo spots
}
const _fitV1 = fitFor;
fitFor = function (s, w) {
  const f = _fitV1(s, w);
  if (!f || SCORE_V !== 2 || w.kind === "night" || UI.group === "life") return f;
  const q = spotQuality(s);
  const m = 0.5 + 0.625 * q;
  return { ...f, n: Math.round(clamp(f.n * m, 0, 100)), q, light: f.n, qm: m };
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
  return bits.length ? bits.join(", ") : "no photo or Wikipedia record found (an unknown spot)";
}
function distFactor(s) { const d = driveMin(s); return 1 - 0.1 * Math.min(1, d / Math.max(1, maxTravel())); }
function mathLine(f, s) {
  if (f.light == null) return "";
  return `Light ${Math.round(f.light)} × spot ${f.qm.toFixed(2)} = ${f.n}; list order × ${distFactor(s).toFixed(2)} for distance`;
}
const _pickRowM = pickRow;
pickRow = function (x, w) {
  const h = _pickRowM(x, w); if (!SCORE_MATH || !x.f || x.f.light == null) return h;
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
       <p class="muted">Spot ${f.qm.toFixed(2)} (0.50 unknown to 1.12 most photographed): ${esc(qualityText(s))}. In the list, distance trims up to 10% (× ${distFactor(s).toFixed(2)} here).</p>`;
  b.insertAdjacentHTML("beforeend", `<div class="scoremath"><h3>Why this score</h3>${parts}<ul>${f.why.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>`);
  if (typeof orderSpotPage === "function") { b._ordered = false; orderSpotPage(); }
};
