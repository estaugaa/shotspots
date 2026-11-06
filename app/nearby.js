/* Outside the researched area (no ShotSpots spot within ~120 km of where you're planning from):
   pull named photo-worthy places from OpenStreetMap around you, so the planner, map and lists still work.
   They're marked "from OpenStreetMap" and get generic tips; light, sky and drive scoring is the same as for any spot. */
"use strict";
const COVER_KM = 120, OSM_KM = 40;
const OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"];
const OSM_TYPES = [
  // [test, cats, light, effort, tip]
  [t => t.tourism === "viewpoint", ["vista"], "both", "short", "A mapped viewpoint. Check which way it faces: facing east it's a sunrise spot, west a sunset spot. Arrive 30 minutes early to scout foreground."],
  [t => t.waterway === "waterfall", ["waterfall"], "overcast", "short", "Waterfalls look best under soft overcast or in shade, when highlights don't blow out. A slow shutter (1/4–1 s on a tripod) smooths the water."],
  [t => t.natural === "peak", ["mountain", "vista"], "sunset", "hike", "A named summit. Check the trail and road access first; the last and first light on high ground is the reason to go."],
  [t => t.natural === "beach", ["coast", "reflection"], "both", "short", "Low tide and wet sand give reflections at sunrise and sunset. Watch the tide times and the waves."],
  [t => t.man_made === "lighthouse", ["coast", "historic"], "sunset", "short", "Lighthouses make strong silhouettes at dusk and pair well with blue hour when the light is on."],
  [t => t.leisure === "nature_reserve" || t.boundary === "protected_area", ["wildlife", "birds"], "sunrise", "short", "Wildlife is most active in the first two hours after sunrise. Stay on trails and give animals space."],
  [t => t.leisure === "garden" && t["garden:type"] !== "residential", ["garden", "fallcolor"], "overcast", "short", "Gardens shine on soft overcast days and right after rain. Check opening hours."],
  [t => /^(castle|fort|monument|ruins|memorial)$/.test(t.historic || "") || t.man_made === "bridge", ["historic", "city"], "both", "road", "A landmark: try it at blue hour when lights come on, or with low side light that brings out texture."],
  [t => t.natural === "water" && t.name, ["reflection"], "sunrise", "short", "Still water early in the morning gives the best reflections, before the wind picks up."],
];
let NEARBY = { key: null, loading: false, n: 0, err: null };

function realSpots() { return SPOTS.filter(s => !s.osm); }
function outsideCoverage(p) { p = p || LOC; let best = 1e9; for (const s of realSpots()) { const d = km(p, s); if (d < best) best = d; } return best > COVER_KM; }

async function loadNearby(force) {
  const key = LOC.lat.toFixed(2) + "," + LOC.lon.toFixed(2);
  if (!outsideCoverage() || NEARBY.loading || (!force && NEARBY.key === key)) return;
  NEARBY.loading = true; NEARBY.err = null; render();
  const cache = store.get("osmNearby", null);
  let els = cache && cache.key === key && Date.now() - cache.at < 7 * 864e5 ? cache.els : null;
  if (!els) {
    const r = OSM_KM * 1000, a = `(around:${r},${LOC.lat},${LOC.lon})`;
    const q = `[out:json][timeout:40];(node${a}[tourism=viewpoint];node${a}[waterway=waterfall][name];node${a}[natural=peak][name];
      nwr${a}[natural=beach][name];nwr${a}[man_made=lighthouse];nwr${a}[leisure=nature_reserve][name];nwr${a}[leisure=garden][name];
      nwr${a}[historic~"^(castle|fort|monument|ruins)$"][name];way${a}[man_made=bridge][name];way${a}[natural=water][name][water~"^(lake|reservoir|pond)$"];);out center tags 400;`;
    for (const u of OVERPASS) {
      try { const res = await fetch(u, { method: "POST", body: new URLSearchParams({ data: q }) }); if (!res.ok) throw new Error("HTTP " + res.status);
        els = (await res.json()).elements; break; } catch (e) { NEARBY.err = e.message; }
    }
    if (els) { els = els.filter(e => e.tags && (e.tags.name || e.tags.tourism === "viewpoint" || e.tags.man_made === "lighthouse")).slice(0, 400);
      try { store.set("osmNearby", { key, at: Date.now(), els }); } catch (e) { } }
  }
  // drop earlier OSM spots, add the new ones
  for (let i = SPOTS.length - 1; i >= 0; i--) if (SPOTS[i].osm) { delete byId[SPOTS[i].id]; SPOTS.splice(i, 1); }
  let n = 0; const seen = new Set();
  for (const e of els || []) {
    const t = e.tags, ty = OSM_TYPES.find(([f]) => f(t)); if (!ty) continue;
    const lat = e.lat ?? (e.center && e.center.lat), lon = e.lon ?? (e.center && e.center.lon); if (lat == null) continue;
    const name = t.name || (t.tourism === "viewpoint" ? "Viewpoint" : "Lighthouse");
    const dk = name.toLowerCase() + "|" + lat.toFixed(2) + lon.toFixed(2); if (seen.has(dk)) continue; seen.add(dk);
    const s = { id: `osm-${e.type[0]}${e.id}`, name: t.name ? name : `${name} (${(t["addr:city"] || t.ele ? (t.ele ? Math.round(t.ele) + " m" : t["addr:city"]) : "unnamed")})`,
      region: "Nearby · from OpenStreetMap", cats: ty[1], lat, lon, light: ty[2], effort: ty[3], months: null, tip: ty[4], osm: true,
      src: [], osmUrl: `https://www.openstreetmap.org/${e.type}/${e.id}` };
    SPOTS.push(s); byId[s.id] = s; n++;
  }
  NEARBY = { key, loading: false, n, err: els ? null : NEARBY.err };
  if (MAP && n) MAP.setView([LOC.lat, LOC.lon], 10);
  render(); if (typeof renderMap === "function" && UI.view === "map") renderMap();
}

/* banner on the Plan screen explaining what you're seeing */
function nearbyBanner() {
  if (!outsideCoverage()) return "";
  if (NEARBY.loading) return `<div class="welcome nearby"><p><b>Finding photo spots near you…</b> ShotSpots' researched spots are in the Pacific Northwest, so it's looking up viewpoints, waterfalls, beaches and landmarks around you on OpenStreetMap.</p></div>`;
  if (!NEARBY.n) return `<div class="welcome nearby"><p><b>No researched spots near here yet.</b> ShotSpots' spot list covers the Pacific Northwest. The light windows and sky forecast above still work for where you are.${NEARBY.err ? " Couldn't reach OpenStreetMap just now." : ""}</p><div class="chips"><button class="chip" id="nearbyRetry">Look for spots near me</button></div></div>`;
  return `<div class="welcome nearby"><p><b>${NEARBY.n} places near you from OpenStreetMap.</b> These aren't researched like the Northwest spots: tips are general and pins aren't checked, so scout before you rely on them. Light, sky and drive scoring work the same.</p></div>`;
}
const _renderNowN = renderNow;
renderNow = function () { _renderNowN(); const v = $("#v-now"), h = nearbyBanner(); if (v && h && !v.querySelector(".nearby")) { const d = v.querySelector("#winDetail"); (d || v).insertAdjacentHTML(d ? "beforebegin" : "afterbegin", h); } };
document.addEventListener("click", e => { if (e.target.closest("#nearbyRetry")) loadNearby(true); });
/* OSM spots: say where they came from on the spot page */
const _openN = openSpot;
openSpot = function (id) { _openN(id); const s = byId[id]; if (!s || !s.osm) return; const b = $("#sheetBody");
  b && b.insertAdjacentHTML("afterbegin", `<div class="alertbox research">From OpenStreetMap, not yet researched: the tip is general and the pin is unchecked. <a href="${s.osmUrl}" target="_blank" rel="noopener">See it on OpenStreetMap</a>.</div>`); };
/* times follow the planning location: the device's own zone when you're there, else a US/Canada zone by position */
const DEVICE_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || "America/Los_Angeles";
function tzFor(p) {
  if (p.src === "gps" || p.src === "here") return DEVICE_TZ;
  const { lat, lon } = p;
  if (lat > 18 && lat < 23 && lon < -154 && lon > -161) return "Pacific/Honolulu";
  if (lat > 51 && lon < -130) return "America/Anchorage";
  if (lat < 24 || lat > 70 || lon < -141 || lon > -52) return DEVICE_TZ;           // outside the US/Canada: trust the device
  if (lat > 31 && lat < 37.1 && lon > -114.8 && lon < -109.05) return "America/Phoenix";
  if (lon < -117 || (lat < 42 && lon < -114.05) || (lat > 45.5 && lat < 49 && lon < -116)) return "America/Los_Angeles";   // WA/OR/CA/NV, Idaho panhandle
  if (lon < -102 || (lat > 49 && lon < -101.5)) return "America/Denver";
  if (lon < -86.5 || (lat > 49 && lon < -90)) return "America/Chicago";
  if (lon > -67 && lat > 43) return "America/Halifax";
  return "America/New_York";
}
/* re-check whenever the planning location changes */
let __nearKey = ""; const _renderNear = render;
render = function () { const tz = tzFor(LOC); if (tz !== TZ) TZ = tz; _renderNear(); const k = LOC.lat.toFixed(2) + "," + LOC.lon.toFixed(2); if (k !== __nearKey) { __nearKey = k; setTimeout(() => loadNearby(), 0); } };
