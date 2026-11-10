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
let MTN = null, AIR = null;

async function loadExtras(force) {
  const key = locKey(); if (!force && MTN && MTN.key === key && Date.now() - MTN.at < 60 * 60000) return false;
  const near = PEAKS.filter(p => km(LOC, p) < 170).sort((a, b) => km(LOC, a) - km(LOC, b)).slice(0, 6);
  let changed = false;
  try {
    if (near.length) {
      const r = await omFetch("https://api.open-meteo.com/v1/forecast?latitude=" + near.map(p => p.lat).join(",") + "&longitude=" + near.map(p => p.lon).join(",") +
        "&hourly=" + LEVELS.map(([l]) => `cloud_cover_${l}hPa`).join(",") + "&forecast_days=8&timeformat=unixtime&timezone=GMT");
      let j = await r.json(); if (!Array.isArray(j)) j = [j];
      MTN = { key, at: Date.now(), peaks: near.map((p, i) => ({ ...p, re: undefined, h: j[i].hourly })) }; changed = true;
    } else MTN = { key, at: Date.now(), peaks: [] };
  } catch (e) { MTN = MTN || null; }
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
  const P = MTN && MTN.peaks.find(x => x.name === peak.name); if (!P) return null; const i = _idx(P.h, t); if (i < 0) return null;
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
  return PEAKS.filter(p => { const d = km(s, p); return d < 160 && (p.re.test(txt) || (d < 60 && s.cats.some(c => c === "vista" || c === "mountain"))); });
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
