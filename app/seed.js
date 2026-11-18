/* Starter spots: state-wide places from OpenStreetMap + Wikidata (built free by `python -m pipeline seed`),
   loaded in 1° tiles around where you're planning from. They're scored like any spot but carry general tips
   and a "Starter" tag; nightly research promotes the best ones to full researched spots.
   Where no tiles exist yet, nearby.js still falls back to a live OpenStreetMap lookup. */
"use strict";
const SEED = { idx: null, tiles: new Set(), n: 0 };
if (typeof D !== "undefined" && D.CATS && !D.CATS.landmark) D.CATS.landmark = { label: "Landmarks", color: (D.CATS.historic || {}).color || "var(--rust)" };
const SEED_KIND = { waterfall: "Waterfall", viewpoint: "Viewpoint", peak: "Summit", lighthouse: "Lighthouse", arch: "Arch", hotspring: "Hot spring", refuge: "Refuge", beach: "Beach", bridge: "Bridge", landmark: "Landmark", hotspot: "Birding hotspot", lake: "Lake", pass: "Mountain pass", lookout: "Lookout tower", cave: "Cave" };
SEED.ready = fetch("feed/seed/index.json", { cache: "no-cache" }).then(r => r.ok ? r.json() : null).then(j => { SEED.idx = j; }).catch(e => noteErr("spot tiles", e)).finally(() => { SEED.idxDone = true; });   // loaded or failed: the list may stop waiting for it
// which tiles have popularity / opening-hours files yet (both jobs fill in over time); null = unknown, so try all
SEED.has = { seedpop: null, seedhours: null, stands: null, seedviews: null, deep: null };
SEED.hasReady = Promise.all(["seedpop", "seedhours", "stands", "seedviews", "deep"].map(d => fetch(`feed/${d}/index.json`, { cache: "no-cache" }).then(r => r.ok ? r.json() : null).then(j => { if (Array.isArray(j)) SEED.has[d] = new Set(j); }).catch(e => noteErr("spot tiles", e))));
const seedHas = (d, k) => !SEED.has[d] || SEED.has[d].has(k);
const seedCovers = () => !!(SEED.idx && SEED.idx.tiles[`${Math.floor(LOC.lat)}_${Math.floor(LOC.lon)}`]);
async function loadSeed() {
  await SEED.ready; if (!SEED.idx) return;
  const R = Math.max(120, Math.min(260, (PREFS.travel === "walk" ? 5 : maxTravel()) * 1.2));   // km around you: roughly your drive limit
  const want = [];
  for (let la = Math.floor(LOC.lat - R / 111); la <= Math.floor(LOC.lat + R / 111); la++)
    for (let lo = Math.floor(LOC.lon - R / 75); lo <= Math.floor(LOC.lon + R / 75); lo++) { const k = `${la}_${lo}`; if (SEED.idx.tiles[k] && !SEED.tiles.has(k)) want.push(k); }
  if (!want.length) return;
  const real = SPOTS.filter(s => !s.seed && !s.osm);
  SEED.busy = true; setTimeout(() => { SEED.busy = false; }, 20000);
  await SEED.hasReady;   // so missing popularity/hours tiles aren't requested
  const [got, pops] = await Promise.all([Promise.all(want.map(k => fetch(`feed/seed/${k}.json`).then(r => r.ok ? r.json() : null).catch(e => noteErr("spot tiles", e)))),
    Promise.all(want.map(k => !seedHas("seedpop", k) ? null : fetch(`feed/seedpop/${k}.json`).then(r => r.ok ? r.json() : null).catch(e => noteErr("spot tiles", e))))]);
  // full research cards, nationwide (pipeline/deepnat.py): facing from 10 m terrain, walk from parking, horizon profile
  want.filter(k => SEED.has.deep && seedHas("deep", k)).forEach(k => fetch(`feed/deep/${k}.json`).then(r => r.ok ? r.json() : null).then(j => {
    if (!j || !j.spots) return; let c = 0;
    for (const [id, d] of Object.entries(j.spots)) { const s = byId[id]; if (!s) continue;
      if (d.light && !s._psLight) s.light = d.light; /* people's photos showing the light win */ if (d.eff) s.effort = d.eff; if (d.tip) s.tip = d.tip; if (d.hz) s.hzp = d.hz; s.deep = true; c++; }
    if (c && typeof render === "function" && typeof BOOT !== "undefined" && !BOOT.core) { clearTimeout(SEED._dt); SEED._dt = setTimeout(render, 400); } }).catch(e => noteErr("spot tiles", e)));   // after the first screen: next redraw
  // Wikipedia page views: how famous (pipeline/wikiviews.py)
  want.filter(k => SEED.has.seedviews && seedHas("seedviews", k)).forEach(k => fetch(`feed/seedviews/${k}.json`).then(r => r.ok ? r.json() : null).then(j => {
    if (!j) return; let c = 0; for (const [id, v] of Object.entries(j)) { const s = byId[id]; if (s && typeof v === "number") { s.views = v; c++; } }
    if (c && typeof render === "function" && typeof BOOT !== "undefined" && !BOOT.core) { clearTimeout(SEED._vt); SEED._vt = setTimeout(render, 400); } }).catch(e => noteErr("spot tiles", e)));   // after the first screen: next redraw
  // where photographers stand + classic direction (pipeline/stands.py)
  setTimeout(() => want.filter(k => seedHas("stands", k) && SEED.has.stands).forEach(k => fetch(`feed/stands/${k}.json`).then(r => r.ok ? r.json() : null).then(j => { if (j) { Object.assign(STANDS, j); applyStands(); } }).catch(e => noteErr("spot tiles", e))), 2500);   // not needed for the first list: let the spots load first
  setTimeout(() => want.filter(k => seedHas("seedhours", k)).forEach(k => fetch(`feed/seedhours/${k}.json`).then(r => r.ok ? r.json() : null).then(j => { if (j && typeof SEEDHOURS !== "undefined") Object.assign(SEEDHOURS, j); }).catch(e => noteErr("spot tiles", e))), 2500);   // photos & sightings per spot (pipeline/seedpop.py)
  let added = 0;
  got.forEach((t, i) => { if (!t) return; SEED.tiles.add(want[i]);
    for (const x of t.spots) { if (byId[x.id] || real.some(s => Math.abs(s.lat - x.lat) < 0.004 && Math.abs(s.lon - x.lon) < 0.006)) continue;
      const ps = ((fd("photostats") || {}).spots || {})[x.id];   // learned from when people photograph it
      if (/bridge|landmark/.test(x.kind) && x.cats) x.cats = x.cats.map(c => c === "historic" ? "landmark" : c);
      if ((x.kind === "peak" || x.kind === "lookout") && (x.light === "sunrise" || x.light === "sunset")) x.light = "both";   // summits see both ways; coarse terrain often says otherwise (Cadillac Mountain)
      const pp = pops[i] && pops[i][x.id]; if (pp) { x.pop = pp[0]; x.refs = { commons: pp[1], flickr: pp[2], inat: pp[3] }; }
      const dp = ((fd("deep") || {}).spots || {})[x.id];   // full research card (pipeline/deepspots.py): fine terrain facing, walk, tip
      if (dp) { if (dp.light && !(ps && ps.light && ps.n >= 8)) x.light = dp.light; if (dp.eff) x.effort = dp.eff; if (dp.tip) x.tip = dp.tip; if (dp.months && !(ps && ps.months)) x.months = dp.months; x.deep = true; }
      const s = { ...x, region: `${SEED_KIND[x.kind] || "Place"} · starter spot`, months: ps && ps.months || null, light: ps && ps.light || x.light, _psLight: !!(ps && ps.light && ps.n >= 8), osm: true, seed: true, src: [], osmUrl: `https://www.openstreetmap.org/${x.osm}`, ps };
      SPOTS.push(s); byId[s.id] = s; added++; } });
  SEED.n += added;
  SEED.busy = false;
  if (added) { if (typeof __topsKey !== "undefined") __topsKey = ""; render(); if (await loadWx(true)) { __topsKey = ""; render(); } }
}
/* seed spots count as coverage, so the live OSM fallback only runs where no tiles exist */
realSpots = function () { return SPOTS.filter(s => !s.osm || s.seed); };
const _setLocS = setLoc; setLoc = function () { const r = _setLocS.apply(this, arguments); loadSeed(); return r; };
setTimeout(loadSeed, 400);
/* the live OpenStreetMap lookup is only for places the starter tiles don't cover yet */
const _loadNearbyS = loadNearby;
loadNearby = async function (force) { await SEED.ready; if (seedCovers()) { await loadSeed(); return; } return _loadNearbyS(force); };
/* Plan banner where only starter spots are around */
const _renderNowSeed = renderNow;
renderNow = function () { _renderNowSeed(); if (!SEED.n) return; const v = $("#v-now"); if (!v || v.querySelector(".seedban")) return;
  const curated = SPOTS.filter(s => !s.osm); let best = 1e9; for (const s of curated) best = Math.min(best, km(LOC, s)); if (best < 80) return;
  const near = SPOTS.filter(s => s.seed && km(LOC, s) < 100).length; if (!near) return;
  const d = v.querySelector("#winDetail"); const h = `<div class="welcome seedban"><details><summary><b>${near} starter spots near you</b> <span class="muted">(what's that?)</span></summary><p>They come from OpenStreetMap and Wikidata, ranked by how notable they are. Tips are general and pins aren't checked yet; the best ones get researched first.</p></details></div>`;
  (d || v).insertAdjacentHTML(d ? "beforebegin" : "afterbegin", h); };
document.addEventListener("change", e => { if (e.target.id === "maxTravel") setTimeout(loadSeed, 50); });
/* spot page: say what a starter spot is */
const _openSeed = openSpot;
openSpot = function (id) { _openSeed(id); const s = byId[id]; if (!s || !s.seed) return; const b = $("#sheetBody"); if (!b || b.querySelector(".seednote")) return;
  const a = b.querySelector(".prose") || b.querySelector("h2");
  const ps = s.ps ? ` From ${s.ps.n} photos taken here, people shoot it mostly ${({ sunrise: "at sunrise", sunset: "at sunset", both: "at sunrise and sunset", night: "at night", day: "in daylight" })[s.ps.light]}${s.ps.months ? `, busiest in ${s.ps.months.map(m => ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][m - 1]).join(", ")}` : ""}.` : "";
  const h = `<p class="seednote muted" style="font-size:14px"><span class="seasontag">Starter spot</span>${ps} From <a href="${safeUrl(s.osmUrl)}" target="_blank" rel="noopener">OpenStreetMap</a>${s.wd ? ` and <a href="https://www.wikidata.org/wiki/${s.wd}" target="_blank" rel="noopener">Wikidata</a>` : ""}. The tip is general and the pin isn't checked yet; ShotSpots researches the most notable starter spots first. Scores, light and drive times work the same as for any spot.</p>`;
  a ? a.insertAdjacentHTML("afterend", h) : b.insertAdjacentHTML("afterbegin", h); };

/* ---- where to stand ---- */
const STANDS = {};
fetch("feed/stands/researched.json").then(r => r.ok ? r.json() : null).then(j => { if (j) { Object.assign(STANDS, j); applyStands(); } }).catch(e => noteErr("spot tiles", e));
const CONFIDENT = new Set(["photos", "feature", "agree"]);
// a confident classic direction replaces the terrain guess for starter spots (researched spots keep their hand-checked light)
function applyStands() {
  let changed = 0;
  for (const s of SPOTS) { const st = STANDS[s.id]; if (!st || s._stand) continue; s._stand = st; changed++;
    if (s.seed && st.f != null && CONFIDENT.has(st.fs)) { const e = Math.abs(((st.f - 90) + 540) % 360 - 180), w = Math.abs(((st.f - 270) + 540) % 360 - 180);
      s.light = e <= 55 ? "sunrise" : w <= 55 ? "sunset" : "side"; s.hz = s.light !== "side"; }
    if (st.u >= 4) s.standFame = Math.min(4, Math.log2(st.u) - 1);   // many photographers in one spot = a known view
  }
  if (changed && typeof render === "function") { clearTimeout(applyStands.t); applyStands.t = setTimeout(render, 300); }
}
function standHtml(s) {
  const st = s._stand || STANDS[s.id]; if (!st || (!st.st && st.f == null)) return "";
  const CW = b => ["north", "north-northeast", "northeast", "east-northeast", "east", "east-southeast", "southeast", "south-southeast", "south", "south-southwest", "southwest", "west-southwest", "west", "west-northwest", "northwest", "north-northwest"][Math.round(((b % 360) + 360) % 360 / 22.5) % 16];
  const br = (a, b) => { const y = Math.sin((b.lon - a.lon) * Math.PI / 180) * Math.cos(b.lat * Math.PI / 180), x = Math.cos(a.lat * Math.PI / 180) * Math.sin(b.lat * Math.PI / 180) - Math.sin(a.lat * Math.PI / 180) * Math.cos(b.lat * Math.PI / 180) * Math.cos((b.lon - a.lon) * Math.PI / 180); return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360; };
  let h = `<h3>Where to stand</h3>`;
  if (st.st) { const p = { lat: st.st[0], lon: st.st[1] };
    h += st.d >= 25 ? `<p>${st.u ? `Most photographers (${st.u} in shared photos)` : "The mapped viewpoint"} stand <b>${st.d} m ${CW(br(s, p))}</b> of this pin.</p>` : `<p>${st.u ? `Most photographers (${st.u} in shared photos) stand` : "The mapped viewpoint is"} right at this pin.</p>`;
    if (st.d >= 25) h += `<div class="actions"><a class="btn" href="${safeUrl(mapsUrl(p.lat, p.lon))}" target="_blank" rel="noopener">Directions to the spot</a></div>`; }
  if (st.f != null) h += CONFIDENT.has(st.fs) ? `<p>The classic shot faces <b>${CW(st.f)}</b>${st.fs === "photos" ? ", from the compass in people’s photos" : st.fs === "feature" ? ", toward the feature" : ", where two sources agree"}.</p>`
    : `<p class="muted">Street-level photos here often point ${CW(st.f)}. Unconfirmed: road traffic can skew this.</p>`;
  if (st.ex && st.ex.length) h += `<p class="muted" style="font-size:13px">Examples: ${st.ex.map(e => `<a href="${safeUrl(e[1])}" target="_blank" rel="noopener">${esc(e[0])}</a>`).join(", ")} (Wikimedia Commons)</p>`;
  return h;
}

/* ---- famous places the starter data misses (pipeline/icons.py): added once as starter spots ---- */
fetch("feed/icons.json").then(r => r.ok ? r.json() : null).then(j => {
  if (!j || !j.spots) return; let c = 0;
  const words = n => new Set((n.toLowerCase().match(/[a-z]{4,}/g) || []).filter(w => !/^(state|park|national|scenic|viewpoint|point|area)$/.test(w)));
  for (const x of j.spots) { if (byId[x.id]) continue;
    const xw = words(x.name);   // a hand-researched spot of the same place wins (Smith Rock)
    if (SPOTS.some(s => !s.seed && Math.abs(s.lat - x.lat) < 0.03 && Math.abs(s.lon - x.lon) < 0.04 && [...words(s.name)].some(w => xw.has(w)))) continue;
    const s = { ...x, seed: true, icon: true, region: x.state || "", hz: false, score: 20, standFame: 3 };
    const dp = ((fd("deep") || {}).spots || {})[x.id]; if (dp) { if (dp.light) s.light = dp.light; if (dp.eff) s.effort = dp.eff; if (dp.tip) s.tip = dp.tip; if (dp.months) s.months = dp.months; s.deep = true; }   // curated classics: famous by definition
    SPOTS.push(s); byId[s.id] = s; c++; }
  if (c && typeof render === "function" && typeof BOOT !== "undefined" && !BOOT.core) { clearTimeout(SEED._it); SEED._it = setTimeout(render, 600); }   // after the first screen: next redraw
}).catch(e => noteErr("spot tiles", e));
