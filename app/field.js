/* Field toolkit for spot pages and planning:
   - Sun & moon: the full twilight ladder (astronomical, nautical, civil, golden), rise/set azimuths, moon phase and
     interference, the Milky Way core's dark-sky window, and a compass that puts those directions next to the
     classic shot direction ("Where to stand")
   - My notes: private field notes per spot (parking, permits, gate codes), kept on this device and included in exports
   - Copy coordinates, for a GPS unit or another app
   - Export saved spots as GPX (Gaia, onX, Garmin, CalTopo) or KML (Google Earth)
   - Map layers: street, topographic, satellite */
"use strict";
const NOTES = store.get("notes", {});
const CW16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
const cw16 = a => CW16[Math.round(((a % 360) + 360) % 360 / 22.5) % 16];
const fdeg = a => `${Math.round(((a % 360) + 360) % 360)}° ${cw16(a)}`;

function fieldYmd() { return (typeof UI !== "undefined" && UI.day) || laYMD(new Date()); }

/* Milky Way core above 10° while the sky is fully dark (sun below −18°), sampled every 10 minutes from dusk to dawn */
function coreWindow(s, ymd, e) {
  const start = e.astroDusk, next = dayEvents(s, addDays(ymd, 1)), end = next.astroDawn;
  if (!start || !end || end <= start) return { none: "no full darkness" };
  let a = null, b = null, best = null;
  for (let t = start.getTime(); t <= end.getTime(); t += 600000) {
    const d = new Date(t), g = gcPos(d, s.lat, s.lon);
    if (g.alt >= 10) { if (!a) a = d; b = d; if (!best || g.alt > best.alt) best = { t: d, alt: g.alt, az: g.az }; }
  }
  if (!a) return { none: "core below 10° all night" };
  const m = moonPos(best.t, s.lat, s.lon);
  return { a, b, best, moonUp: m.alt > 0, illum: m.illum };
}

function compassSvg(items) {
  const R = 58, C = 70, pt = (az, r) => [C + r * Math.sin(az * Math.PI / 180), C - r * Math.cos(az * Math.PI / 180)];
  let g = `<circle cx="${C}" cy="${C}" r="${R}" class="cp-ring"/>`;
  [["N", 0], ["E", 90], ["S", 180], ["W", 270]].forEach(([l, a]) => { const [x, y] = pt(a, R + 9); g += `<text x="${x}" y="${y + 4}" text-anchor="middle" class="cp-l">${l}</text>`; });
  items.forEach(it => { const [x, y] = pt(it.az, it.len || R - 4);
    g += `<line x1="${C}" y1="${C}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" class="cp-${it.k}"${it.w ? ` stroke-width="${it.w}"` : ""}/><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4" class="cp-${it.k}d"/>`; });
  return `<svg viewBox="0 0 140 140" class="compass" role="img" aria-label="Directions of sunrise, sunset, moon and Milky Way from this spot">${g}<circle cx="${C}" cy="${C}" r="3" class="cp-c"/></svg>`;
}

function sunMoonHtml(s) {
  const ymd = fieldYmd(), e = dayEvents(s, ymd);
  const sf = t => sunPos(t, s.lat, s.lon).alt, pick = (arr, dir) => { const x = arr.find(c => c.dir === dir); return x ? x.t : null; };
  const n12 = crossings(ymd, sf, -12), nDawn = pick(n12, "up"), nDusk = pick(n12, "down");
  const T = t => t ? fmtT(t) : "—";
  const az = t => t ? ` <span class="muted">${fdeg(sunPos(t, s.lat, s.lon).az)}</span>` : "";
  const noon = new Date(Date.parse(`${ymd}T12:00:00Z`) - s.lon / 15 * 3600000);   // local solar noon
  const polar = !e.sunrise && !e.sunset ? (sunPos(noon, s.lat, s.lon).alt > 0 ? "The sun doesn't set today (midnight sun)." : "The sun doesn't rise today (polar night).") : "";
  const rows = [
    ["Astronomical dawn", e.astroDawn, "sky fully dark until now"], ["Nautical dawn", nDawn, "horizon line appears"], ["Civil dawn", e.civilDawn, "blue hour"],
    ["Sunrise", e.sunrise, "", true], ["Golden hour ends", e.goldEndAM, "sun 6° up"], ["Golden hour starts", e.goldStartPM, ""],
    ["Sunset", e.sunset, "", true], ["Civil dusk", e.civilDusk, "blue hour ends"], ["Nautical dusk", nDusk, ""], ["Astronomical dusk", e.astroDusk, "full darkness"]];
  let h = `<h3>Sun & moon</h3><p class="muted" style="font-size:14px;margin-top:-4px">${dayWord(e.sunrise || noon)}, ${fmtDate(e.sunrise || noon)}, at this spot (${TZ.replace(/_/g, " ").split("/").pop()} time).</p>`;
  if (polar) h += `<p><b>${polar}</b></p>`;
  if (!e.astroDusk && e.sunset) h += `<p class="muted">No full astronomical darkness tonight: the sun stays within 18° of the horizon.</p>`;
  if (e.sunrise && !e.goldEndAM) h += `<p class="muted">The sun never climbs above 6° today: low, golden light all day.</p>`;
  h += `<div class="sm-grid"><table class="twl">${rows.map(([l, t, note, sun]) => `<tr${sun ? ' class="sunrow"' : ""}><th>${l}</th><td>${T(t)}${sun ? az(t) : ""}${note && t ? ` <small class="muted">${note}</small>` : ""}</td></tr>`).join("")}</table>`;
  // moon
  const mref = e.sunset || noon, mp = moonPos(mref, s.lat, s.lon), illum = Math.round(mp.illum * 100);
  const mAz = t => t ? fdeg(moonPos(t, s.lat, s.lon).az) : "";
  let moon = `<p><b>Moon:</b> ${phaseName(mp.age)}, ${illum}% lit. ${e.moonrise ? `Rises ${T(e.moonrise)} (${mAz(e.moonrise)})` : "No moonrise today"}, ${e.moonset ? `sets ${T(e.moonset)} (${mAz(e.moonset)})` : "no moonset today"}.`;
  moon += illum >= 60 ? " Bright enough to wash out faint stars while it's up; good for moonlit landscapes." : illum <= 15 ? " Dark-sky friendly." : "";
  moon += `</p>`;
  // Milky Way
  const cw = coreWindow(s, ymd, e);
  const core = cw.none ? `<p><b>Milky Way core:</b> not visible tonight (${cw.none}).</p>`
    : `<p><b>Milky Way core:</b> above 10° from ${T(cw.a)} to ${T(cw.b)}; highest ${Math.round(cw.best.alt)}° at ${T(cw.best.t)}, toward ${fdeg(cw.best.az)}.${cw.moonUp && cw.illum > 0.3 ? ` The moon (${Math.round(cw.illum * 100)}%) is up then, so faint detail will be washed out.` : ""}</p>`;
  // compass
  const st = s._stand || (typeof STANDS !== "undefined" && STANDS[s.id]), items = [], key = [];
  if (e.sunrise) { items.push({ k: "sr", az: sunPos(e.sunrise, s.lat, s.lon).az }); key.push(`<span class="k sr"></span>sunrise`); }
  if (e.sunset) { items.push({ k: "ss", az: sunPos(e.sunset, s.lat, s.lon).az }); key.push(`<span class="k ss"></span>sunset`); }
  if (e.moonrise) { items.push({ k: "mr", az: moonPos(e.moonrise, s.lat, s.lon).az, len: 44 }); key.push(`<span class="k mr"></span>moonrise`); }
  if (!cw.none) { items.push({ k: "gc", az: cw.best.az, len: 44 }); key.push(`<span class="k gc"></span>Milky Way core`); }
  if (st && st.f != null) { items.push({ k: "shot", az: st.f, w: 4 }); key.push(`<span class="k shot"></span>classic shot`); }
  h += `<div class="sm-side">${compassSvg(items)}<p class="cp-key">${key.join(" ")}</p></div></div>${moon}${core}`;
  return `<div class="sunmoon">${h}</div>`;
}

/* ---- my notes ---- */
function notesHtml(s) {
  return `<div class="mynotes"><h3>My notes</h3><textarea id="noteBox" data-id="${esc(s.id)}" rows="3" placeholder="Parking, permits, gate codes, where the good rock is…" aria-label="My notes for ${esc(s.name)}">${esc(NOTES[s.id] || "")}</textarea><p class="muted" style="font-size:13px" id="noteMsg">Private: kept on this device and included when you export saved spots.</p></div>`;
}
let __noteT = null;
document.addEventListener("input", e => {
  const t = e.target; if (t.id !== "noteBox") return;
  clearTimeout(__noteT); __noteT = setTimeout(() => {
    const v = t.value.trim(); if (v) NOTES[t.dataset.id] = v.slice(0, 2000); else delete NOTES[t.dataset.id];
    store.set("notes", NOTES); const m = $("#noteMsg"); if (m) m.textContent = "Saved on this device.";
  }, 400);
});

/* ---- copy coordinates ---- */
document.addEventListener("click", async e => {
  const b = e.target.closest("[data-copyll]"); if (!b) return;
  const txt = b.dataset.copyll; let ok = false;
  try { await navigator.clipboard.writeText(txt); ok = true; } catch (er) { }
  b.textContent = ok ? "Copied" : txt; setTimeout(() => { b.textContent = "Copy coordinates"; }, 2500);
});

/* ---- GPX / KML export of saved spots ---- */
const xmlEsc = v => String(v == null ? "" : v).replace(/[<>&'"]/g, c => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" }[c]));
function exportPoints() {
  const out = [];
  for (const id of Object.keys(SAVED)) { const s = byId[id]; if (!s) continue;
    const st = s._stand || (typeof STANDS !== "undefined" && STANDS[s.id]);
    const desc = [s.region, NOTES[id] ? "Notes: " + NOTES[id] : "", s.tip || ""].filter(Boolean).join("\n");
    out.push({ name: s.name, lat: s.lat, lon: s.lon, desc, url: `https://estaugaa.github.io/shotspots/#spot=${encodeURIComponent(id)}` });
    if (st && st.st && st.d >= 25) out.push({ name: `${s.name}: where to stand`, lat: st.st[0], lon: st.st[1], desc: st.f != null ? `Classic shot faces ${fdeg(st.f)}` : "" });
  }
  return out;
}
function download(name, text, type) {
  const a = document.createElement("a"), url = URL.createObjectURL(new Blob([text], { type }));
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
}
function exportSaved(fmt) {
  const pts = exportPoints(), msg = $("#expMsg");
  if (!pts.length) { if (msg) msg.textContent = "Save a few spots first (☆ Save on a spot page), then export them."; return; }
  const day = new Date().toISOString().slice(0, 10);
  if (fmt === "gpx") download(`shotspots-${day}.gpx`, `<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="ShotSpots" xmlns="http://www.topografix.com/GPX/1/1">\n` +
    pts.map(p => `  <wpt lat="${p.lat.toFixed(6)}" lon="${p.lon.toFixed(6)}"><name>${xmlEsc(p.name)}</name>${p.desc ? `<desc>${xmlEsc(p.desc)}</desc>` : ""}${p.url ? `<link href="${xmlEsc(p.url)}"/>` : ""}<sym>Scenic Area</sym></wpt>`).join("\n") + `\n</gpx>\n`, "application/gpx+xml");
  else download(`shotspots-${day}.kml`, `<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>ShotSpots saved spots</name>\n` +
    pts.map(p => `<Placemark><name>${xmlEsc(p.name)}</name>${p.desc ? `<description>${xmlEsc(p.desc)}</description>` : ""}<Point><coordinates>${p.lon.toFixed(6)},${p.lat.toFixed(6)},0</coordinates></Point></Placemark>`).join("\n") + `\n</Document></kml>\n`, "application/vnd.google-earth.kml+xml");
  if (msg) msg.textContent = `Exported ${pts.length} points. Open the file in Gaia GPS, onX, CalTopo, Garmin or Google Earth.`;
}
document.addEventListener("click", e => { const b = e.target.closest("[data-export]"); if (b) exportSaved(b.dataset.export); });
function exportBlock() {
  return `<div class="exportbox" id="exportBox"><h3>Take your saved spots offline</h3><p class="muted" style="font-size:14px">Waypoints for every saved spot (plus "where to stand" points and your notes).</p>
    <div class="chips"><button class="chip" data-export="gpx">Export GPX</button><button class="chip" data-export="kml">Export KML</button></div><p class="muted" style="font-size:13px" id="expMsg" role="status"></p></div>`;
}

/* ---- hook into the spot page and the Spots tab ---- */
{ const _oF = openSpot; openSpot = function (id) { _oF.apply(this, arguments); const s = byId[id], b = $("#sheetBody"); if (!s || !b || b.querySelector(".sunmoon")) return;
  b.insertAdjacentHTML("beforeend", sunMoonHtml(s) + notesHtml(s));
  const act = b.querySelector(".actions");
  if (act && !b.querySelector("[data-copyll]")) act.insertAdjacentHTML("beforeend", `<button class="btn" data-copyll="${s.lat.toFixed(5)}, ${s.lon.toFixed(5)}">Copy coordinates</button>`);
}; }
{ const _rF = render; render = function () { _rF.apply(this, arguments); const v = $("#v-spots"); if (v && !v.hidden && !v.querySelector("#exportBox")) v.insertAdjacentHTML("beforeend", exportBlock()); }; }

/* ---- map layers: street, topo, satellite ---- */
(function mapLayers() {
  const tick = setInterval(() => {
    if (typeof MAP === "undefined" || !MAP || typeof L === "undefined") return;
    clearInterval(tick);
    let street = null; MAP.eachLayer(l => { if (l instanceof L.TileLayer && !street) street = l; });
    const topo = L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", { maxZoom: 17, attribution: "© OpenTopoMap (CC-BY-SA), © OpenStreetMap" });
    const sat = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { maxZoom: 18, attribution: "Imagery © Esri, Maxar, Earthstar Geographics" });
    const base = { "Map": street, "Topo": topo, "Satellite": sat };
    if (!street) delete base.Map;
    L.control.layers(base, null, { position: "topright", collapsed: true }).addTo(MAP);
    const pref = store.get("maplayer", "Map"); if (pref !== "Map" && base[pref]) { if (street) MAP.removeLayer(street); base[pref].addTo(MAP); }
    MAP.on("baselayerchange", ev => store.set("maplayer", ev.name));
  }, 1000);
})();

/* ---- #spot=<id> links (from exported waypoints) open that spot; starter spots may take a few seconds to load ---- */
(function spotLink() {
  const m = location.hash.match(/^#spot=([^&]+)/); if (!m) return;
  const id = decodeURIComponent(m[1]); let n = 0;
  const t = setInterval(() => { if (byId[id] && typeof openSpot === "function") { clearInterval(t); history.replaceState(null, "", location.pathname); openSpot(id); } else if (++n > 20) clearInterval(t); }, 500);
})();
