/* Starter spots: state-wide places from OpenStreetMap + Wikidata (built free by `python -m pipeline seed`),
   loaded in 1° tiles around where you're planning from. They're scored like any spot but carry general tips
   and a "Starter" tag; nightly research promotes the best ones to full researched spots.
   Where no tiles exist yet, nearby.js still falls back to a live OpenStreetMap lookup. */
"use strict";
const SEED = { idx: null, tiles: new Set(), n: 0 };
const SEED_KIND = { waterfall: "Waterfall", viewpoint: "Viewpoint", peak: "Summit", lighthouse: "Lighthouse", arch: "Arch", hotspring: "Hot spring", refuge: "Refuge", beach: "Beach", bridge: "Bridge", landmark: "Landmark" };
SEED.ready = fetch("feed/seed/index.json", { cache: "no-cache" }).then(r => r.ok ? r.json() : null).then(j => { SEED.idx = j; }).catch(() => { });
const seedCovers = () => !!(SEED.idx && SEED.idx.tiles[`${Math.floor(LOC.lat)}_${Math.floor(LOC.lon)}`]);
async function loadSeed() {
  await SEED.ready; if (!SEED.idx) return;
  const R = Math.max(120, Math.min(260, (PREFS.travel === "walk" ? 5 : maxTravel()) * 1.2));   // km around you: roughly your drive limit
  const want = [];
  for (let la = Math.floor(LOC.lat - R / 111); la <= Math.floor(LOC.lat + R / 111); la++)
    for (let lo = Math.floor(LOC.lon - R / 75); lo <= Math.floor(LOC.lon + R / 75); lo++) { const k = `${la}_${lo}`; if (SEED.idx.tiles[k] && !SEED.tiles.has(k)) want.push(k); }
  if (!want.length) return;
  const real = SPOTS.filter(s => !s.seed && !s.osm);
  const got = await Promise.all(want.map(k => fetch(`feed/seed/${k}.json`).then(r => r.ok ? r.json() : null).catch(() => null)));
  let added = 0;
  got.forEach((t, i) => { if (!t) return; SEED.tiles.add(want[i]);
    for (const x of t.spots) { if (byId[x.id] || real.some(s => Math.abs(s.lat - x.lat) < 0.004 && Math.abs(s.lon - x.lon) < 0.006)) continue;
      const s = { ...x, region: `${SEED_KIND[x.kind] || "Place"} · starter spot`, months: null, osm: true, seed: true, src: [], osmUrl: `https://www.openstreetmap.org/${x.osm}` };
      SPOTS.push(s); byId[s.id] = s; added++; } });
  SEED.n += added;
  if (added) { if (typeof __topsKey !== "undefined") __topsKey = ""; render(); }
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
  const d = v.querySelector("#winDetail"); const h = `<div class="welcome seedban"><p><b>${near} starter spots near you.</b> They come from OpenStreetMap and Wikidata, ranked by how notable they are. Tips are general and pins aren't checked yet; the best ones get researched first.</p></div>`;
  (d || v).insertAdjacentHTML(d ? "beforebegin" : "afterbegin", h); };
document.addEventListener("change", e => { if (e.target.id === "maxTravel") setTimeout(loadSeed, 50); });
/* spot page: say what a starter spot is */
const _openSeed = openSpot;
openSpot = function (id) { _openSeed(id); const s = byId[id]; if (!s || !s.seed) return; const b = $("#sheetBody"); if (!b || b.querySelector(".seednote")) return;
  const a = b.querySelector(".prose") || b.querySelector("h2");
  const h = `<p class="seednote muted" style="font-size:14px"><span class="seasontag">Starter spot</span> From <a href="${s.osmUrl}" target="_blank" rel="noopener">OpenStreetMap</a>${s.wd ? ` and <a href="https://www.wikidata.org/wiki/${s.wd}" target="_blank" rel="noopener">Wikidata</a>` : ""}. The tip is general and the pin isn't checked yet; ShotSpots researches the most notable starter spots first. Scores, light and drive times work the same as for any spot.</p>`;
  a ? a.insertAdjacentHTML("afterend", h) : b.insertAdjacentHTML("afterbegin", h); };
