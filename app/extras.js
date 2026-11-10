/* Three things the forecast can tell us that the score didn't use yet:
   1. "Is the mountain out?"  summit-level cloud at nearby big peaks (Open-Meteo pressure levels) + low cloud between you
      and the peak + visibility. Spots that view a named peak gain when it's out and drop when it's hidden.
   2. Haze and dust: aerosol optical depth, dust and PM2.5 (Open-Meteo air quality). Light haze reddens sunrise and
      sunset; heavy haze or smoke washes out distant views.
   3. Rainbows: showers with sun breaks while the sun is under 42 degrees. Look away from the sun. */
"use strict";
const PEAKS = [
  ["Mt. Hood", 45.3736, -121.6959, 3426, /\bhood\b/i], ["Mt. St. Helens", 46.1914, -122.1956, 2549, /st\.? helens/i], ["Mt. Adams", 46.2024, -121.4909, 3743, /\badams\b/i],
  ["Mt. Rainier", 46.8529, -121.7604, 4392, /rainier|tahoma/i], ["Mt. Jefferson", 44.6744, -121.7997, 3199, /jefferson/i], ["Mt. Baker", 48.7768, -121.8145, 3286, /\bbaker\b/i],
  ["Glacier Peak", 48.1125, -121.1139, 3213, /glacier peak/i], ["Mt. Olympus", 47.8013, -123.7108, 2432, /olympus|olympics/i], ["South Sister", 44.1034, -121.7693, 3157, /sisters/i],
  ["Mt. Bachelor", 43.979, -121.6884, 2764, /bachelor/i], ["Mt. Shasta", 41.4092, -122.1949, 4322, /shasta/i], ["Lassen Peak", 40.4882, -121.5049, 3187, /lassen/i],
  ["Mt. Whitney", 36.5785, -118.2923, 4421, /whitney/i], ["Grand Teton", 43.7411, -110.8024, 4199, /teton/i], ["Longs Peak", 40.2549, -105.6151, 4346, /longs peak/i],
  ["Pikes Peak", 38.8409, -105.0423, 4302, /pikes/i], ["Mt. Blue Sky", 39.5883, -105.6438, 4348, /blue sky|mt\.? evans/i], ["Mt. Timpanogos", 40.3908, -111.6458, 3582, /timpanogos/i],
  ["Humphreys Peak", 35.3464, -111.6779, 3852, /humphreys|san francisco peaks/i], ["Wheeler Peak", 36.5569, -105.4167, 4013, /wheeler/i], ["Mt. Washington", 44.2706, -71.3033, 1917, /mt\.? washington/i],
  ["Denali", 63.0692, -151.007, 6190, /denali/i], ["Mauna Kea", 19.8207, -155.4681, 4207, /mauna kea/i], ["Mt. Mitchell", 35.7648, -82.2652, 2037, /mitchell/i],
].map(([name, lat, lon, elev, re]) => ({ name, lat, lon, elev, re }));
const LEVELS = [[850, 1500], [700, 3000], [600, 4200], [500, 5600]];
// the big peaks you can see from here: the named list plus tall, well-known starter peaks (elevation from their tip)
function peaksNear(p) {
  const named = PEAKS.filter(x => km(p, x) < 170);
  const east = p.lon > -103, minE = east ? 1300 : 2300;
  const seedPk = SPOTS.filter(s => s.seed && s.kind === "peak" && km(p, s) < 140).map(s => { const m = /Summit ([\d,]+) m/.exec(s.tip || ""); return m ? { s, elev: +m[1].replace(/,/g, "") } : null; })
    .filter(x => x && x.elev >= minE && (x.s.score || 0) >= 8 && !named.some(n => km(n, x.s) < 15))
    .map(({ s, elev }) => ({ name: s.name, lat: s.lat, lon: s.lon, elev, re: new RegExp("\\b" + s.name.replace(/^(mount|mt\.?)\s+/i, "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b", "i") }));
  // biggest-looking first: height over distance
  return [...named, ...seedPk].sort((a, b) => b.elev / Math.max(5, km(p, b)) - a.elev / Math.max(5, km(p, a))).slice(0, 6);
}
let MTN = null, AIR = null, LOCAL = null, SEA = null;

async function loadExtras(force) {
  const key = locKey(); if (!force && MTN && MTN.key === key && Date.now() - MTN.at < 60 * 60000) return false;
  const near = peaksNear(LOC);
  let changed = false;
  try {
    if (near.length) {
      const r = await omFetch("https://api.open-meteo.com/v1/forecast?latitude=" + near.map(p => p.lat).join(",") + "&longitude=" + near.map(p => p.lon).join(",") +
        "&hourly=" + LEVELS.map(([l]) => `cloud_cover_${l}hPa`).join(",") + ",snowfall&past_days=2&forecast_days=8&timeformat=unixtime&timezone=GMT");
      let j = await r.json(); if (!Array.isArray(j)) j = [j];
      MTN = { key, at: Date.now(), peaks: near.map((p, i) => ({ ...p, h: j[i].hourly })) }; changed = true;
    } else MTN = { key, at: Date.now(), peaks: [] };
  } catch (e) { MTN = MTN || null; }
  try {
    const r = await omFetch(`https://api.open-meteo.com/v1/forecast?latitude=${LOC.lat.toFixed(3)}&longitude=${LOC.lon.toFixed(3)}&minutely_15=precipitation&forecast_minutely_15=12&past_minutely_15=2` +
      `&hourly=cape,snowfall,snow_depth,temperature_2m,relative_humidity_2m,wind_speed_10m&past_days=2&forecast_days=3&timeformat=unixtime&timezone=GMT`);
    LOCAL = { key, at: Date.now(), ...(await r.json()) }; changed = true;
  } catch (e) { }
  const coast = SPOTS.filter(x => (x.cats.includes("coast") || x.kind === "beach" || x.kind === "lighthouse") && km(LOC, x) < 50).sort((a, b) => km(LOC, a) - km(LOC, b))[0];
  if (coast) try {
    const r = await omFetch(`https://marine-api.open-meteo.com/v1/marine?latitude=${coast.lat.toFixed(3)}&longitude=${coast.lon.toFixed(3)}&hourly=wave_height,wave_period&forecast_days=3&timeformat=unixtime&timezone=GMT`);
    const j = await r.json(); if (j.hourly) { SEA = { key, at: Date.now(), h: j.hourly, near: coast.name }; changed = true; }
  } catch (e) { }
  try {
    const r = await omFetch(`https://air-quality-api.open-meteo.com/v1/air-quality?latitude=${LOC.lat.toFixed(2)}&longitude=${LOC.lon.toFixed(2)}&hourly=aerosol_optical_depth,dust,pm2_5&forecast_days=5&timeformat=unixtime&timezone=GMT`);
    const j = await r.json(); AIR = { key, at: Date.now(), h: j.hourly }; changed = true;
  } catch (e) { }
  return changed;
}
function _idx(h, t) { if (!h || !h.time) return -1; const ts = t.getTime() / 1000; let bi = -1, bd = 1e12;
  for (let i = 0; i < h.time.length; i++) { const d = Math.abs(h.time[i] - ts); if (d < bd) { bd = d; bi = i; } } return bd <= 5400 ? bi : -1; }

// is this peak visible from p at time t? {out: true/false/null, summit %, why}
function peakOut(peak, p, t) {
  const P = MTN && MTN.peaks.find(x => x.name === peak.name) || peak; if (!P.h) return null; const i = _idx(P.h, t); if (i < 0) return null;
  const lv = LEVELS.filter(([, z]) => z >= P.elev * 0.45 && z <= P.elev + 600).map(([l]) => P.h[`cloud_cover_${l}hPa`][i]).filter(v => v != null);
  if (!lv.length) return null; const summit = Math.max(...lv);
  const mid = { lat: (p.lat + P.lat) / 2, lon: (p.lon + P.lon) / 2 }, between = hourAt(nearestPt(mid, 60), t), here = hourAt(nearestPt(p, 60), t);
  const dist = km(p, P), low = between ? between.low : 0, vis = here && here.vis != null ? here.vis / 1000 : 50;
  const out = summit < 35 && low < 60 && vis > dist * 0.5, hidden = summit >= 65 || low >= 80 || vis < dist * 0.25;
  return { out, hidden, summit: Math.round(summit), low: Math.round(low), dist };
}
// peaks a spot looks at: named in its name/tip, or a big peak close by from a viewpoint or summit
function peaksFor(s) {
  const txt = s.name + " " + (s.tip || "");
  return (MTN ? MTN.peaks : PEAKS).filter(p => { const d = km(s, p); return d < 160 && (p.re.test(txt) || (d < 60 && s.cats.some(c => c === "vista" || c === "mountain"))); });
}
function airAt(t) { if (!AIR) return null; const i = _idx(AIR.h, t); if (i < 0) return null; return { aod: AIR.h.aerosol_optical_depth[i], dust: AIR.h.dust[i], pm: AIR.h.pm2_5[i] }; }
function rainbowAt(p, t) {   // showers with sun breaks and the sun low enough (under 42 degrees) for the bow to be above the horizon
  const sp = sunPos(t, p.lat, p.lon); if (sp.alt < 3 || sp.alt > 40) return null;
  const c = hourAt(nearestPt(p, 60), t); if (!c) return null;
  const showers = [80, 81, 82].includes(c.code) || (c.pop >= 40 && c.precip >= 0.1 && c.precip < 4);
  if (!showers || c.cc < 30 || c.cc > 88) return null;
  const az = (sp.az + 180) % 360, dir = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"][Math.round(az / 45) % 8];
  return { dir, alt: Math.round(sp.alt) };
}


// ---------- the local landscape decides which opportunities are worth telling you about ----------
function landscape() {
  const near = SPOTS.filter(x => km(LOC, x) < 60), c = k => near.filter(k).length;
  return {
    coast: c(x => x.cats.includes("coast") || x.kind === "beach" || x.kind === "lighthouse") >= 3,
    mountains: !!(MTN && MTN.peaks.length),
    desert: c(x => x.kind === "arch" || /canyon|slot|wash|butte|mesa/i.test(x.name)) >= 3 || (LOC.lat < 38.5 && LOC.lon > -120 && LOC.lon < -103),
    lakes: c(x => x.kind === "lake" || x.cats.includes("reflection")) >= 3,
    plains: !(MTN && MTN.peaks.length) && LOC.lon > -105 && LOC.lon < -94,
  };
}
const _L = (h, k, t) => { if (!h || !h.time) return null; const i = _idx(h, t); return i < 0 ? null : h[k][i]; };
function snowSince(h, hours, at) { if (!h || !h.snowfall) return 0; const t1 = (at || new Date()).getTime() / 1000, t0 = t1 - hours * 3600; let sum = 0;
  h.time.forEach((t, i) => { if (t >= t0 && t <= t1) sum += h.snowfall[i] || 0; }); return sum; }   // cm
function freshSnowOn(P) { return P && P.h ? snowSince(P.h, 48) : 0; }
// 15-minute rain for the next 3 hours (HRRR-based, nudged by radar every hour)
function rainSoon() {
  const m = LOCAL && LOCAL.minutely_15; if (!m) return null; const now = Date.now() / 1000;
  const pts = m.time.map((t, i) => ({ t, p: m.precipitation[i] || 0 })).filter(x => x.t >= now - 900);
  if (!pts.length) return null; const wet = x => x.p >= 0.1, nowWet = wet(pts[0]);
  const change = pts.find(x => wet(x) !== nowWet);
  return { nowWet, at: change ? new Date(change.t * 1000) : null, max: Math.max(...pts.map(x => x.p)) };
}

const _fitExtras = fitFor;
fitFor = function (s, w) {
  const f = _fitExtras(s, w); if (!f || w.kind === "night") return f;
  let n = f.n; const why = f.why ? [...f.why] : [];
  if (MTN) for (const pk of peaksFor(s).slice(0, 2)) { const o = peakOut(pk, s, w.peak); if (!o) continue; const named = pk.re.test(s.name + " " + (s.tip || ""));
    if (o.out) { n += named ? 6 : 3; why.push(`${pk.name} should be out (summit ${o.summit}% cloud)`); }
    else if (o.hidden && named) { n -= 10; why.push(`${pk.name} likely hidden in cloud`); } }
  const a = airAt(w.peak);
  if (a && a.aod != null) {
    const far = s.cats.some(c => c === "vista" || c === "mountain");
    if (a.aod >= 0.5 || a.pm >= 35) { if (far) { n *= 0.85; why.push("heavy haze or smoke: distant views wash out"); } if (GOLDK.has(w.kind)) why.push("the sun will look deep red through the haze"); }
    else if (a.aod >= 0.15 && GOLDK.has(w.kind)) { n += 4; why.push("light haze: warmer, redder light"); }
  }
  const rb = rainbowAt(s, w.peak); if (rb) { n += 5; why.push(`rainbow chance: showers with sun breaks, look ${rb.dir}`); }
  if (MTN) for (const pk of peaksFor(s).slice(0, 1)) { const P = MTN.peaks.find(x => x.name === pk.name), o = P && peakOut(P, s, w.peak), sn = freshSnowOn(P);
    if (o && o.out && sn >= 3) { n += 5; why.push(`fresh snow on ${pk.name} (${Math.round(sn)} cm in 2 days)`); }
    if (o && o.out && w.kind === "sunset" && s.light !== "sunset" && pk.re.test(s.name + " " + (s.tip || ""))) why.push(`alpenglow on ${pk.name} just after sunset`); }
  if (LOCAL && LOCAL.hourly) { const sd = _L(LOCAL.hourly, "snow_depth", w.peak), sf = snowSince(LOCAL.hourly, 24, w.peak);
    if (sd >= 0.02 && sf >= 1 && s.cats.some(c => ["forest", "waterfall", "city", "historic", "landmark"].includes(c))) { n += 4; why.push("fresh snow on the ground: go before it melts or gets tracked"); } }
  if (SEA && (s.cats.includes("coast") || s.kind === "beach" || s.kind === "lighthouse")) { const wv = _L(SEA.h, "wave_height", w.peak);
    if (wv >= 3.5) { n += 5; why.push(`big surf: ${wv.toFixed(1)} m waves; stay well back from the water`); } }
  return { ...f, n: Math.max(0, Math.min(100, Math.round(n))), why };
};

// Now tab: which big mountains are out for the window you're looking at, and the next rainbow chance
function extrasHtml() {
  const all = allWindows(LOC, PLAN_HOURS), w = all[clamp(UI.focus, 0, all.length - 1)]; if (!w || w.kind === "night") return "";
  const items = [];
  if (MTN && MTN.peaks.length) { const st = MTN.peaks.slice(0, 4).map(p => { const o = peakOut(PEAKS.find(x => x.name === p.name), LOC, w.peak); return o ? `${p.name} ${o.out ? "✓" : o.hidden ? "✗" : "?"}` : null; }).filter(Boolean);
    if (st.length) items.push(`<div class="item"><b>🏔️ Mountains at ${wTitle(w).toLowerCase()}</b><p>${esc(st.join(" · "))} <span class="muted">(✓ likely out, ✗ likely in cloud)</span></p></div>`); }
  for (let k = 1; k <= 36; k++) { const t = new Date(Date.now() + k * 36e5), rb = rainbowAt(LOC, t);
    if (rb) { items.push(`<div class="item"><b>🌈 Rainbow chance ${dayTab(laYMD(t)).toLowerCase()} around ${fmtT(t)}</b><p>Showers with breaks of sun while it's low (${rb.alt}°). Face ${rb.dir}, away from the sun; the bow sits 42° from the shadow of your head.</p></div>`); break; } }
  const L = landscape(), rs = rainSoon();
  if (rs && (rs.nowWet || rs.at)) items.unshift(`<div class="item"><b>${rs.nowWet ? "☔ Raining now" : "🌦️ Rain on the way"}</b><p>${rs.nowWet ? (rs.at ? `Should ease around ${fmtT(rs.at)}.` : "Steady for the next 3 hours.") : `Starting around ${fmtT(rs.at)}.`} <span class="muted">15-minute forecast, updated hourly from radar.</span></p></div>`);
  if (MTN) MTN.peaks.slice(0, 3).forEach(P => { const sn = freshSnowOn(P), o = peakOut(P, LOC, w.peak);
    if (sn >= 3) items.push(`<div class="item"><b>❄️ Fresh snow on ${esc(P.name)}</b><p>${Math.round(sn)} cm in the last 2 days. ${o && o.out ? `It should be out at ${wTitle(w).toLowerCase()}: the first clear look after a storm is the classic shot.` : "Watch for the first clear window: that's the shot."}</p></div>`);
    if (w.kind === "sunset" && o && o.out && L.mountains) items.push(`<div class="item"><b>🌄 Alpenglow on ${esc(P.name)}</b><p>With the summit clear, it can turn pink for about 10 minutes after sunset. Shoot it from a spot that faces it, not the sunset.</p></div>`); });
  if (L.coast && SEA) { let best = null; for (let k = 0; k < 48; k += 3) { const t = new Date(Date.now() + k * 36e5), wv = _L(SEA.h, "wave_height", t); if (wv != null && (!best || wv > best.wv)) best = { wv, t }; }
    if (best && best.wv >= 3.5) items.push(`<div class="item"><b>🌊 Big surf ${dayTab(laYMD(best.t)).toLowerCase()}</b><p>Waves up to ${best.wv.toFixed(1)} m near ${esc(SEA.near)} around ${fmtT(best.t)}. Headlands and jetties make the shot; sneaker waves are real, so stay well back.</p></div>`); }
  if (LOCAL && LOCAL.hourly) { const H = LOCAL.hourly; let storm = null;
    for (let k = 1; k < 36; k++) { const t = new Date(Date.now() + k * 36e5), cape = _L(H, "cape", t), hr = +new Date(t).toLocaleString("en-US", { hour: "numeric", hour12: false, timeZone: TZ });
      if (cape >= 1000 && hr >= 12 && hr <= 20) { storm = { t, cape }; break; } }
    if (storm) items.push(`<div class="item"><b>⛈️ Storms building ${dayTab(laYMD(storm.t)).toLowerCase()} afternoon</b><p>Unstable air (CAPE ${Math.round(storm.cape)}) from about ${fmtT(storm.t)}: towering clouds, shafts of rain, maybe lightning. Shoot from a distance${L.desert ? " and stay out of slot canyons and washes: flash floods come from storms you can't see" : ""}.</p></div>`);
    const dawn = allWindows(LOC, 30).find(x => x.kind === "sunrise");
    if (dawn) { const tf = _L(H, "temperature_2m", dawn.peak), rh = _L(H, "relative_humidity_2m", dawn.peak), wd = _L(H, "wind_speed_10m", dawn.peak);
      if (tf != null && tf <= -2 && rh >= 85 && wd < 8) items.push(`<div class="item"><b>🥶 Frost at sunrise</b><p>${Math.round(tf)}°C, calm and damp: hoarfrost on grass and branches. Backlight it with the low sun.${L.lakes && tf <= -6 ? " On lakes, look for steam fog rising off the water." : ""}</p></div>`); } }
  if (L.desert) { const mo = new Date().getMonth() + 1, sky = skyAt(LOC, { kind: "day", peak: new Date(new Date().setHours(12, 0, 0, 0)) });
    if (mo >= 4 && mo <= 9 && sky && sky.cc < 30) items.push(`<div class="item"><b>🔦 Slot canyon light beams</b><p>On clear days from April to September the sun gets high enough to drop beams into slot canyons, roughly 11 am to 1:30 pm. Toss a little sand in the air to make them show.</p></div>`); }
  const a = airAt(w.peak); if (a && (a.aod >= 0.5 || a.pm >= 35)) items.push(`<div class="item"><b>🌫️ Hazy air</b><p>Aerosol ${a.aod.toFixed(2)}, PM2.5 ${Math.round(a.pm)}: long views will be soft, but the sun turns deep red near the horizon.</p></div>`);
  return items.length ? `<div class="sect extras">${items.join("")}</div>` : "";
}
const _renderNowExtras = renderNow;
renderNow = function () {
  const r = _renderNowExtras.apply(this, arguments);
  try { const box = document.querySelector("#v-now .sect h3"); const h = extrasHtml(); if (h) { const el = document.querySelector("#v-now .extras"); if (el) el.outerHTML = h; else { const also = [...document.querySelectorAll("#v-now .sect")].find(x => /Also worth knowing/.test(x.textContent)); (also || document.querySelector("#v-now")).insertAdjacentHTML(also ? "beforebegin" : "beforeend", h); } } } catch (e) { }
  return r;
};
setTimeout(() => loadExtras().then(ch => { if (ch) { __topsKey = ""; render(); } }).catch(() => { }), 2500);
setInterval(() => loadExtras().then(ch => { if (ch) { __topsKey = ""; render(); } }).catch(() => { }), 30 * 60000);
