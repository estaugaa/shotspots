/* ShotSpots live data: everything here is fetched straight from the phone, free, no Claude needed.
   iNaturalist (recent birds & mammals), eBird (rare birds, optional free key), NOAA SWPC (live Kp),
   NOAA tides, USGS river flow, Open-Meteo air quality (smoke), Open-Meteo past rain (waterfall flow). */
"use strict";
const LIVE = { inat: store.get("inat", null), ebird: store.get("ebird", null), kpNow: store.get("kpNow", null), aq: store.get("aq", null),
  tides: store.get("tides", {}), flow: store.get("flow", {}), status: {} };
let EBIRD_KEY = store.get("ebirdKey", "");
const TIDE_NAMES = { "9437540": "Garibaldi", "9439040": "Astoria" };
const GAUGE_NAMES = { "14143500": "Washougal River", "14222500": "East Fork Lewis River", "14142500": "Sandy River", "14144700": "Columbia at Vancouver" };
const ymd8 = t => laYMD(t).replace(/-/g, "");
const ago = ms => { const m = Math.round((Date.now() - ms) / 60000); return m < 60 ? m + " min ago" : m < 1440 ? Math.round(m / 60) + " h ago" : Math.round(m / 1440) + " d ago"; };
function mark(k, ok, note) { LIVE.status[k] = { ok, note, at: Date.now() }; }
async function getJson(url, opt) { const r = await fetch(url, opt); if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }

/* ---- iNaturalist: one regional call, binned to spots ---- */
async function loadInat() {
  if (LIVE.inat && Date.now() - LIVE.inat.at < 3 * 36e5 && LIVE.inat.key === locKey()) return;
  const d1 = laYMD(new Date(Date.now() - 10 * 864e5));
  const url = `https://api.inaturalist.org/v1/observations?lat=${LOC.lat.toFixed(3)}&lng=${LOC.lon.toFixed(3)}&radius=90&d1=${d1}&iconic_taxa=Aves,Mammalia&photos=true&geoprivacy=open&order=desc&order_by=observed_on&per_page=200`;
  try { const j = await getJson(url);
    const rows = (j.results || []).filter(o => o.geojson && o.taxon).map(o => ({ lat: o.geojson.coordinates[1], lon: o.geojson.coordinates[0], n: o.taxon.preferred_common_name || o.taxon.name,
      sci: o.taxon.name, rank: o.taxon.rank, cnt: o.taxon.observations_count || 0, d: o.observed_on, img: o.photos && o.photos[0] && o.photos[0].url ? o.photos[0].url.replace("square", "small") : "",
      url: o.uri, mam: o.taxon.iconic_taxon_name === "Mammalia" }));
    LIVE.inat = { at: Date.now(), key: locKey(), rows }; store.set("inat", LIVE.inat); mark("inat", true, rows.length + " sightings in 10 days");
  } catch (e) { mark("inat", false, String(e.message || e)); }
}
function inatNear(s, kmR) { return LIVE.inat ? LIVE.inat.rows.filter(o => km(s, o) <= (kmR || 2.5)) : []; }

/* ---- eBird notable (needs free key) ---- */
async function loadEbird() {
  if (!EBIRD_KEY) { mark("ebird", false, "add your free key to turn on"); return; }
  if (LIVE.ebird && Date.now() - LIVE.ebird.at < 60 * 60000 && LIVE.ebird.key === locKey()) return;
  try { const j = await getJson(`https://api.ebird.org/v2/data/obs/geo/recent/notable?lat=${LOC.lat.toFixed(2)}&lng=${LOC.lon.toFixed(2)}&dist=50&back=3&detail=simple`, { headers: { "X-eBirdApiToken": EBIRD_KEY } });
    const seen = new Set(), rows = j.filter(o => { const k = o.speciesCode + o.locId; if (seen.has(k)) return false; seen.add(k); return true; })
      .map(o => ({ n: o.comName, loc: o.locName, lat: o.lat, lon: o.lng, t: o.obsDt, cnt: o.howMany, sub: o.subId, ok: o.obsReviewed && o.obsValid }));
    LIVE.ebird = { at: Date.now(), key: locKey(), rows }; store.set("ebird", LIVE.ebird); mark("ebird", true, rows.length + " notable sightings in 3 days");
  } catch (e) { mark("ebird", false, /401|403/.test(e.message) ? "key not accepted" : String(e.message || e)); }
}

/* ---- live Kp ---- */
async function loadKpNow() {
  if (LIVE.kpNow && Date.now() - LIVE.kpNow.at < 15 * 60000) return;
  try { const j = await getJson("https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"); const last = j[j.length - 1];
    LIVE.kpNow = { at: Date.now(), kp: +(last.estimated_kp != null ? last.estimated_kp : last.kp_index), t: last.time_tag }; store.set("kpNow", LIVE.kpNow); mark("kp", true, "Kp " + LIVE.kpNow.kp.toFixed(1) + " now");
  } catch (e) { mark("kp", false, String(e.message || e)); }
}

/* ---- smoke / haze ---- */
async function loadAq() {
  if (LIVE.aq && Date.now() - LIVE.aq.at < 60 * 60000 && LIVE.aq.key === locKey()) return;
  try { const j = await getJson(`https://air-quality-api.open-meteo.com/v1/air-quality?latitude=${LOC.lat.toFixed(3)}&longitude=${LOC.lon.toFixed(3)}&hourly=pm2_5,aerosol_optical_depth&forecast_days=3&timeformat=unixtime&timezone=GMT`);
    LIVE.aq = { at: Date.now(), key: locKey(), h: j.hourly }; store.set("aq", LIVE.aq); mark("aq", true, "smoke forecast loaded");
  } catch (e) { mark("aq", false, String(e.message || e)); }
}
function aqAt(t) { const h = LIVE.aq && LIVE.aq.h; if (!h) return null; const ts = t.getTime() / 1000; let bi = 0, bd = 1e12;
  h.time.forEach((x, i) => { const d = Math.abs(x - ts); if (d < bd) { bd = d; bi = i; } }); return bd > 5400 ? null : { pm: h.pm2_5[bi], aod: h.aerosol_optical_depth[bi] }; }

/* ---- tides (only fetched when a coast spot is opened or ranked) ---- */
async function loadTides(st) {
  const c = LIVE.tides[st]; if (c && Date.now() - c.at < 12 * 36e5) return c;
  try { const j = await getJson(`https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=predictions&interval=hilo&datum=MLLW&units=english&time_zone=gmt&format=json&application=ShotSpots&station=${st}&begin_date=${ymd8(new Date(Date.now() - 864e5))}&range=96`);
    const p = (j.predictions || []).map(x => ({ t: new Date(x.t.replace(" ", "T") + "Z").getTime(), v: +x.v, type: x.type }));
    LIVE.tides[st] = { at: Date.now(), p }; store.set("tides", LIVE.tides); mark("tides", true, "tides for " + (TIDE_NAMES[st] || st)); return LIVE.tides[st];
  } catch (e) { mark("tides", false, String(e.message || e)); return null; }
}
let TSTN = null;
async function tideStation(s) {
  const cur = (D.TIDES || {})[s.id]; if (cur) return cur; if (s.tide !== undefined) return s.tide;
  if (!(s.cats.includes("coast") || s.kind === "beach" || s.kind === "lighthouse" || /beach|bay|harbor|cove|pier|lighthouse|tide/i.test(s.name))) return (s.tide = null);
  if (!TSTN) TSTN = fetch("feed/tidestations.json").then(r => r.ok ? r.json() : { rows: [] }).catch(() => ({ rows: [] }));
  const rows = (await TSTN).rows || []; let best = null, bd = 30;
  for (const [id, n, lat, lon] of rows) { const d = km(s, { lat, lon }); if (d < bd) { bd = d; best = id; TIDE_NAMES[id] = TIDE_NAMES[id] || n; } }
  return (s.tide = best);
}
function lowTideNear(s, w) { const st = (D.TIDES || {})[s.id] || s.tide, c = st && LIVE.tides[st]; if (!c) return null;
  return c.p.filter(x => x.type === "L" && x.t >= w.start.getTime() - 60 * 60000 && x.t <= w.end.getTime() + 60 * 60000).sort((a, b) => a.v - b.v)[0] || null; }

/* ---- river flow (USGS) ---- */
async function loadFlow() {
  const sites = [...new Set(Object.values(D.GAUGES || {}))]; if (!sites.length) return;
  if (LIVE.flow.at && Date.now() - LIVE.flow.at < 60 * 60000) return;
  try { const j = await getJson(`https://waterservices.usgs.gov/nwis/iv/?format=json&sites=${sites.join(",")}&parameterCd=00060,00065&period=P7D&siteStatus=all`);
    const out = { at: Date.now(), s: {} };
    (j.value.timeSeries || []).forEach(ts => { const id = ts.sourceInfo.siteCode[0].value, p = ts.variable.variableCode[0].value, v = (ts.values[0].value || []).map(x => +x.value).filter(x => x >= 0);
      if (!v.length) return; const o = out.s[id] = out.s[id] || {}; o[p === "00060" ? "q" : "h"] = { now: v[v.length - 1], med: v.slice().sort((a, b) => a - b)[Math.floor(v.length / 2)], max: Math.max(...v) }; });
    LIVE.flow = out; store.set("flow", out); mark("flow", true, Object.keys(out.s).length + " river gauges");
  } catch (e) { mark("flow", false, String(e.message || e)); }
}
async function streamAt(s) {
  if (s._stream !== undefined) return s._stream;
  try { const q = `[out:json][timeout:15];way(around:60,${s.lat},${s.lon})[waterway~"^(river|stream)$"][name];out tags 3;`;
    const r = await fetch("https://overpass-api.de/api/interpreter?data=" + encodeURIComponent(q)); const j = await r.json();
    const w = (j.elements || []).sort((a, b) => (a.tags.waterway === "river" ? 0 : 1) - (b.tags.waterway === "river" ? 0 : 1))[0];
    return (s._stream = w ? w.tags.name : null);
  } catch (e) { return null; }
}
async function nearGauge(s) {
  if (s.gauge !== undefined) return s.gauge;
  if (!(s.cats.includes("waterfall") || s.kind === "waterfall" || /falls|river|creek|rapids/i.test(s.name))) return (s.gauge = null);
  const b = [s.lon - .2, s.lat - .15, s.lon + .2, s.lat + .15].map(x => x.toFixed(3)).join(",");
  try { const j = await getJson(`https://waterservices.usgs.gov/nwis/iv/?format=json&bBox=${b}&parameterCd=00060&siteType=ST&siteStatus=active&period=P7D`);
    // A gauge only says something about this spot if it's on the same stream: the stream's name has to appear in the
    // spot's name or description (then up to 20 km), or the gauge is right next to it (3 km). Big rivers like the
    // Columbia say nothing about side-creek waterfalls.
    let txt = (s.name + " " + (s.tip || "")).toLowerCase(); let best = null, bd = 1e9;
    // Waterfalls rarely say which river they're on: ask OpenStreetMap for the named stream under the pin
    if (!/\b(river|creek|fork)\b/.test(txt)) { const st = await streamAt(s); if (st) txt += " " + st.toLowerCase(); }
    for (const ts of j.value.timeSeries || []) { const g = ts.sourceInfo.geoLocation.geogLocation, d = km(s, { lat: g.latitude, lon: g.longitude });
      const stream = ts.sourceInfo.siteName.toLowerCase().split(/\s+(?:nr|near|at|abv|above|blw|below|bl|ab)\s+/)[0].replace(/\b(river|creek|cr|r|fork|ck)\b\.?/g, "").replace(/\s+/g, " ").trim();
      if (/columbia|willamette|snake/.test(stream)) continue;
      const same = stream.length >= 3 && new RegExp(`\\b${stream.replace(/[^a-z ]/g, "")}\\s+(river|creek|fork)\\b`).test(txt);
      const v = (ts.values[0].value || []).map(x => +x.value).filter(x => x >= 0); if (v.length && (same ? d < 20 : d < 1.5) && d < bd) { bd = d;
        best = { name: ts.sourceInfo.siteName.toLowerCase().replace(/\b\w/g, c => c.toUpperCase()).replace(/\b(Nr|Near|At|Above|Abv|Below|Blw|Bl|Of|And)\b/g, w => ({ Nr: "near", Abv: "above", Blw: "below", Bl: "below" })[w] || w.toLowerCase()).replace(/, ([A-Za-z]{2})\.?$/, (m, st) => ", " + st.toUpperCase()), km: d, now: v[v.length - 1], med: v.slice().sort((a, b) => a - b)[Math.floor(v.length / 2)] }; } }
    mark("flow", true, "nearest USGS gauge"); return (s.gauge = best);
  } catch (e) { mark("flow", false, String(e.message || e)); return null; }
}
async function spotNws(s) {
  if (km(LOC, s) < 25) return (NWS && NWS.items) || [];
  if (s._nws && Date.now() - s._nws.at < 30 * 60000) return s._nws.items;
  try { const r = await fetch(`https://api.weather.gov/alerts/active?point=${s.lat.toFixed(3)},${s.lon.toFixed(3)}`, { headers: { Accept: "application/geo+json" } });
    const j = await r.json(); s._nws = { at: Date.now(), items: (j.features || []).map(nwsItem) }; return s._nws.items; } catch (e) { return []; }
}
function rain48(s) { const pt = nearestPt(s, 60); if (!pt || !pt.h.precipitation) return null; const now = Date.now() / 1000;
  let mm = 0; pt.h.time.forEach((t, i) => { if (t <= now && t > now - 48 * 3600) mm += pt.h.precipitation[i] || 0; }); return mm / 25.4; }

/* ---- scoring hooks ---- */
const _fitFor = fitFor;
fitFor = function (s, w) {
  const f = _fitFor(s, w); if (!f || w.kind === "night") return f;
  let n = f.n; const why = f.why;
  if (s.cats.includes("waterfall")) { const r = rain48(s); if (r != null && r >= 0.4) { if (DAYK.has(w.kind) || n >= 60) n += 8; why.unshift(`${r.toFixed(1)} in of rain in 2 days: falls running big`); } else if (r != null && r < 0.05 && +laYMD(w.peak).slice(5, 7) >= 7 && +laYMD(w.peak).slice(5, 7) <= 10) { n -= 6; why.push("dry spell: flow may be thin"); } }
  const lt = lowTideNear(s, w); if (lt) { n += 10; why.unshift(`low tide ${fmtT(new Date(lt.t))} (${lt.v.toFixed(1)} ft): wet-sand reflections`); }
  if (s.cats.some(c => LIFE.includes(c))) { const obs = inatNear(s, 2.5); if (obs.length >= 3) { n += Math.min(10, obs.length); why.push(`${obs.length} bird/mammal sightings logged here in 10 days`); } }
  const eb = LIVE.ebird && LIVE.ebird.rows.filter(o => km(s, o) <= 3); if (eb && eb.length) { n += 12; why.unshift(`rare bird: ${eb[0].n} reported ${eb[0].t.slice(5, 10)}`); }
  return { ...f, n: Math.round(clamp(n, 0, 100)), why };
};

/* ---- Now screen additions ---- */
const _specials = specialsHtml;
specialsHtml = function () {
  let extra = "";
  const k = LIVE.kpNow; if (k && k.kp >= 4.67) extra += `<div class="item"><b>🌌 Aurora active now: Kp ${k.kp.toFixed(1)}</b><p>${k.kp >= 6 ? "Strong enough to show on camera from Washougal looking north." : "Try a dark north view: Trout Lake, Satus Pass or Larch Mountain."} Updated ${ago(new Date(k.t + "Z").getTime())}.</p></div>`;
  const w = allWindows(LOC, 40)[0], a = w && aqAt(w.peak);
  if (a && (a.aod >= 0.35 || a.pm >= 35)) extra += `<div class="item"><b>🔥 Smoke haze, ${KNAME[w.kind].toLowerCase()} (PM2.5 ${Math.round(a.pm)})</b><p>Expect a red-orange sun disc and muted distant ridges. Use the 70–300 on the sun near the horizon; skip big vistas.</p></div>`;
  if (LIVE.ebird && LIVE.ebird.rows.length) extra += `<div class="item"><b>🐦 Rare birds within 50 km</b><p>${LIVE.ebird.rows.slice(0, 5).map(o => `<a href="https://ebird.org/checklist/${o.sub}" target="_blank" rel="noopener">${esc(o.n)}</a> at ${esc(o.loc)} (${o.t.slice(5, 10)})`).join("<br>")}</p></div>`;
  const base = _specials();
  if (!extra) return base;
  return base ? base.replace("<h3>Also worth knowing</h3>", "<h3>Also worth knowing</h3>" + extra) : `<div class="sect"><h3>Also worth knowing</h3>${extra}</div>`;
};

/* ---- spot sheet additions ---- */
const _openSpot = openSpot;
openSpot = function (id) {
  _openSpot(id); const s = byId[id]; if (!s) return;
  const box = document.createElement("div"); box.className = "live"; box.id = "liveBox";
  const body = $("#sheetBody"), firstDetails = body.querySelector("details"); firstDetails ? body.insertBefore(box, firstDetails) : body.appendChild(box);
  fillLive(s);
};
async function fillLive(s) {
  const box = $("#liveBox"); if (!box) return; let h = "";
  // conditions
  const gid = (D.GAUGES || {})[s.id], g = gid && LIVE.flow.s && LIVE.flow.s[gid];
  const r = rain48(s);
  if (g && g.q) h += `<h3>River now</h3><div class="kv"><span>${GAUGE_NAMES[gid] || "Gauge " + gid}</span><span>${Math.round(g.q.now).toLocaleString()} cfs (${g.q.now > g.q.med * 1.3 ? "rising, above this week's normal" : g.q.now < g.q.med * 0.8 ? "below this week's normal" : "near this week's normal"})</span></div>`;
  else if (g && g.h) h += `<h3>River now</h3><div class="kv"><span>${GAUGE_NAMES[gid] || "Gauge " + gid}</span><span>${g.h.now.toFixed(1)} ft stage</span></div>`;
  else { const ng = await nearGauge(s); if (ng) h += `<h3>River now</h3><div class="kv"><span>${esc(ng.name)} (${fmtKm(ng.km)} away)</span><span>${Math.round(ng.now).toLocaleString()} cfs (${ng.now > ng.med * 1.3 ? "running high: falls will be full" : ng.now < ng.med * 0.8 ? "below this week's normal" : "near this week's normal"})</span></div><p class="muted" style="font-size:13px">USGS stream gauge. Higher flow usually means fuller waterfalls nearby.</p>`; }
  const al = await spotNws(s); if (al.length) h += `<h3>Weather alerts here</h3><ul class="plain">${al.slice(0, 4).map(a => `<li>${a.ic || "⚠️"} <b>${esc(a.headline)}</b>${a.tip ? ". " + esc(a.tip) : ""}</li>`).join("")}</ul>`;
  const fa = typeof fogAdvisoryAt === "function" && fogAdvisoryAt(s); if (fa && !al.some(a => /Fog/.test(a.headline))) h += `<p>🌫️ <b>${esc(fa.event)}</b> covers this spot until ${fmtT(new Date(fa.ends))}. Expect fog at ground level; look for a viewpoint above it.</p>`;
  if (s.cats.includes("waterfall") && r != null) h += `<div class="kv"><span>Rain, past 48 h</span><span>${r.toFixed(2)} in</span></div>`;
  const st = await tideStation(s);
  if (st) { const c = await loadTides(st); if (c) { const up = c.p.filter(x => x.t > Date.now() - 2 * 36e5).slice(0, 5);
      h += `<h3>Tides (${TIDE_NAMES[st] || st})</h3><div class="kv">${up.map(x => `<span>${x.type === "L" ? "Low" : "High"}</span><span>${fmtDate(new Date(x.t))} ${fmtT(new Date(x.t))}, ${x.v.toFixed(1)} ft</span>`).join("")}</div>`; } }
  // sightings
  const eb = LIVE.ebird ? LIVE.ebird.rows.filter(o => km(s, o) <= 3) : [];
  if (eb.length) h += `<h3>Rare birds reported here</h3><ul class="plain">${eb.map(o => `<li><a href="https://ebird.org/checklist/${o.sub}" target="_blank" rel="noopener">${esc(o.n)}</a>${o.cnt ? " ×" + o.cnt : ""}, ${o.t.slice(5, 16)}</li>`).join("")}</ul>`;
  if (s.cats.some(c => LIFE.includes(c)) || inatNear(s, 2.5).length) {
    const obs = inatNear(s, 2.5), uniq = []; const seen = new Set(); obs.forEach(o => { if (!seen.has(o.sci)) { seen.add(o.sci); uniq.push(o); } });
    h += `<h3>Seen here in the last 10 days</h3>` + (uniq.length ? `<div class="obs">${uniq.slice(0, 9).map(o => `<a href="${o.url}" target="_blank" rel="noopener">${o.img ? `<img src="${o.img}" alt="" loading="lazy">` : ""}${esc(o.n)}<small>${o.d ? o.d.slice(5) : ""}${o.cnt && o.cnt < 2000 ? " · uncommon" : ""}</small></a>`).join("")}</div><p class="muted" style="font-size:13px">From iNaturalist observations within 2.5 km.</p>`
      : `<p class="muted">${LIVE.inat ? "No iNaturalist photos logged within 2.5 km lately." : "Loading recent sightings…"}</p>`);
    h += `<p><a href="https://ebird.org/hotspots?env.minX=${(s.lon - .03).toFixed(3)}&env.maxX=${(s.lon + .03).toFixed(3)}&env.minY=${(s.lat - .02).toFixed(3)}&env.maxY=${(s.lat + .02).toFixed(3)}" target="_blank" rel="noopener">eBird hotspots here</a></p>`;
  }
  // access links
  const wa = /Washington|Camas|Close to home|Helens|Adams|Rainier|Lewis|WA\b|Yakima|Cascades/.test(s.region);
  if (s.osm) h += `<h3>Check before you go</h3><ul class="plain"><li><a href="https://www.google.com/maps/search/?api=1&query=${s.lat},${s.lon}" target="_blank" rel="noopener">Map, traffic and opening hours</a></li><li><a href="${s.osmUrl}" target="_blank" rel="noopener">OpenStreetMap details</a></li></ul>`;
  else h += `<h3>Check before you go</h3><ul class="plain">${wa ? `<li><a href="https://wsdot.com/travel/real-time/map/" target="_blank" rel="noopener">WSDOT roads & closures</a></li>` : `<li><a href="https://www.tripcheck.com/" target="_blank" rel="noopener">ODOT TripCheck roads & closures</a></li>`}
    ${/Hood|Gorge · Oregon/.test(s.region) ? `<li><a href="https://www.fs.usda.gov/alerts/mthood/alerts-notices" target="_blank" rel="noopener">Mt. Hood National Forest alerts</a></li>` : ""}
    ${/Gorge/.test(s.region) ? `<li><a href="https://www.fs.usda.gov/alerts/crgnsa/alerts-notices" target="_blank" rel="noopener">Columbia Gorge Scenic Area alerts</a></li>` : ""}
    ${/Helens|Adams|Trout/.test(s.region + s.name) ? `<li><a href="https://www.fs.usda.gov/alerts/giffordpinchot/alerts-notices" target="_blank" rel="noopener">Gifford Pinchot NF alerts</a></li>` : ""}
    <li><a href="https://www.alltrails.com/search?q=${encodeURIComponent(s.name.split("(")[0].replace(/^Scout pick: |^Experimental: /, ""))}" target="_blank" rel="noopener">AllTrails</a></li></ul>`;
  if ($("#liveBox") === box) box.innerHTML = h;
}

/* ---- settings / status sheet ---- */
const SRCNAMES = { inat: "iNaturalist sightings", ebird: "eBird rare birds", kp: "Live aurora (NOAA)", aq: "Smoke forecast", tides: "Tides (NOAA)", flow: "River flow (USGS)", seven: "Seeing & transparency (7Timer)" };
function renderSettings() {
  const st = LIVE.status, wxOk = WX && !WX.err;
  $("#setBody").innerHTML = `<div class="statusbox"><p class="label">Phone data sources</p><ul class="plain status">
    <li class="${wxOk ? "ok" : "bad"}">${wxOk ? "✓" : "✗"} Weather (Open-Meteo)${WX ? ", updated " + ago(WX.at) : ""}</li>
    ${Object.entries(SRCNAMES).map(([k, n]) => { const x = st[k]; return `<li class="${x ? (x.ok ? "ok" : "bad") : ""}">${x ? (x.ok ? "✓" : "✗") : "·"} ${n}${x ? ": " + esc(x.note) : ": not checked yet"}</li>`; }).join("")}</ul></div>
    <p class="label">eBird rare-bird alerts</p>
    <p class="muted" style="font-size:15px">Free. <a href="https://ebird.org/api/keygen" target="_blank" rel="noopener">Get a key from eBird</a> (sign in, accept the terms, copy the key), then paste it here.</p>
    <form class="field" id="ebForm"><input id="ebKey" placeholder="eBird API key" value="${esc(EBIRD_KEY)}" autocomplete="off"><button class="btn" type="submit">Save</button></form>
    <p class="label">Data</p>
    <p class="muted" style="font-size:15px">Saved spots: ${Object.keys(SAVED).length}. Shot log: ${LOG.length} entries. Stored only on this phone.</p>
    <button class="btn" id="exportLog">Export shot log</button> <button class="btn" id="moveOpen">Move my data to another device</button>`;
}
document.addEventListener("click", e => {
  const t = e.target.closest("#setBtn,#setClose,#exportLog"); if (!t) return;
  if (t.id === "setBtn") { renderSettings(); $("#setSheet").hidden = false; }
  if (t.id === "setClose") $("#setSheet").hidden = true;
  if (t.id === "exportLog") { const rows = [["spot", "time", "conditions"], ...LOG.map(l => [(byId[l.id] || {}).name || l.id, new Date(l.t).toISOString(), l.c || ""])];
    const blob = new Blob([rows.map(r => r.map(x => `"${String(x).replace(/"/g, '""')}"`).join(",")).join("\n")], { type: "text/csv" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "shotspots-log.csv"; a.click(); }
});
document.addEventListener("submit", e => { if (e.target.id !== "ebForm") return; e.preventDefault(); EBIRD_KEY = $("#ebKey").value.trim(); store.set("ebirdKey", EBIRD_KEY);
  LIVE.ebird = null; toast(EBIRD_KEY ? "Checking eBird…" : "eBird off"); loadEbird().then(() => { renderSettings(); render(); }); });

/* ---- load cycle ---- */
async function loadLive() {
  await Promise.all([loadInat(), loadEbird(), loadKpNow(), loadAq(), loadFlow()]);
  // pre-load tides for coast spots so they can rank
  const coast = SPOTS.filter(s => !tooFar(s) && km(LOC, s) < 250).slice(0, 400);
  const st = await Promise.all(coast.map(s => (D.TIDES || {})[s.id] ? (D.TIDES || {})[s.id] : (s.cats.includes("coast") || s.kind === "beach" ? tideStation(s) : null)));
  await Promise.all([...new Set(st.filter(Boolean))].slice(0, 8).map(loadTides));
  render();
}
const _refresh = refresh;
refresh = async function (force) { await _refresh(force); loadLive(); };
loadLive();
document.addEventListener("visibilitychange", () => { if (!document.hidden) loadLive(); });
setInterval(() => { if (!document.hidden) loadLive(); }, 10 * 60000);
