/* ShotSpots 2 — a personal field app for landscape & wildlife photography around Washougal.
   Everything runs on the phone: sun/moon math locally, weather from Open-Meteo, drive times from OSRM,
   aurora from NOAA SWPC, alerts from NWS, place search from OpenStreetMap. */
"use strict";
const D = window.SS, SPOTS = D.spots, byId = Object.fromEntries(SPOTS.map(s => [s.id, s]));
/* ---------- your setup (Settings): home, units, how you travel ---------- */
const PREFS = (() => { let p = {}; try { p = JSON.parse(localStorage.getItem("ss2:prefs") || "{}"); } catch (e) { }
  const us = /^en-US|^en$/.test(navigator.language || "en-US") || /^America\/(?!Toronto|Vancouver|Montreal|Edmonton|Winnipeg|Halifax|Regina)/.test(Intl.DateTimeFormat().resolvedOptions().timeZone || "");
  return { units: us ? "us" : "metric", travel: "drive", maxDrive: 120, maxWalk: 30, start: "gps", ...p }; })();
function savePrefs() { try { localStorage.setItem("ss2:prefs", JSON.stringify(PREFS)); } catch (e) { } }
let HOME = (() => { try { const h = JSON.parse(localStorage.getItem("ss2:home") || "null"); if (h && isFinite(h.lat)) return { ...h, src: "home" }; } catch (e) { } return { lat: 45.582, lon: -122.353, label: "Washougal (home)", src: "home" }; })();
const METRIC = () => PREFS.units === "metric";
function fmtKm(k) { if (k == null || !isFinite(k)) return ""; if (METRIC()) return k < 1 ? Math.round(k * 1000) + " m" : (k < 10 ? k.toFixed(1) : Math.round(k)) + " km";
  const mi = k / 1.60934; return mi < 0.2 ? Math.round(mi * 5280 / 10) * 10 + " ft" : (mi < 10 ? mi.toFixed(1) : Math.round(mi)) + " mi"; }
const fmtTemp = f => f == null ? "" : METRIC() ? Math.round((f - 32) * 5 / 9) + "°C" : Math.round(f) + "°F";
const fmtDeg = f => f == null ? "" : (METRIC() ? Math.round((f - 32) * 5 / 9) : Math.round(f)) + "°";
const fmtWind = mph => METRIC() ? Math.round(mph * 1.609) + " km/h" : Math.round(mph) + " mph";
const maxTravel = () => PREFS.travel === "walk" ? PREFS.maxWalk : PREFS.maxDrive;
const tooFar = s => driveMin(s) > maxTravel();
const GRID = [
  ["coast", "North Coast", 45.88, -123.96], ["coastrange", "Coast Range", 45.72, -123.35], ["willamette", "Willamette Valley", 45.05, -122.95],
  ["pdx", "Portland", 45.53, -122.68], ["home", "Camas–Washougal", 45.585, -122.37], ["wgorge", "West Gorge", 45.59, -122.10],
  ["mgorge", "Hood River", 45.70, -121.52], ["egorge", "East Gorge", 45.69, -120.90], ["plateau", "Columbia Plateau", 45.75, -120.10],
  ["hood", "Mt. Hood", 45.33, -121.75], ["adams", "Trout Lake & Adams", 46.00, -121.53], ["helens", "St. Helens", 46.25, -122.20],
  ["larch", "Larch Mountain", 45.53, -122.09], ["vanc", "Vancouver", 45.67, -122.55], ["southcoast", "Central Coast", 45.20, -123.95]
].map(([id, n, lat, lon]) => ({ id, n, lat, lon }));
const PRESETS = [["Washougal (home)", 45.582, -122.353], ["Camas", 45.587, -122.400], ["Fisher's Landing", 45.6116, -122.5068], ["Vancouver", 45.627, -122.672],
  ["Battle Ground", 45.781, -122.533], ["Portland", 45.52, -122.68], ["Troutdale", 45.539, -122.387], ["Gresham", 45.498, -122.431],
  ["Cascade Locks", 45.67, -121.89], ["Stevenson", 45.696, -121.885], ["Hood River", 45.71, -121.52], ["Government Camp", 45.30, -121.75], ["Cannon Beach", 45.89, -123.96]];
const FOG_ABOVE = ["cape-horn-lookout", "womens-forum", "vista-house", "jonsrud", "scout-cape-horn-uplands", "angels-rest", "larch-mtn", "scout-capehorn-foothill-sunset", "silver-star", "council-crest", "pittock", "scout-angels-hood", "scout-mt-norway-sunset"];
const WETCITY = new Set(["cathedral-park", "eastbank-esplanade", "hawthorne-bridge", "grant-street-pier", "portland-tram", "camas-mill", "scout-sandyhenge", "scout-burnsidehenge", "scout-evergreenhenge", "scout-camas-4th-moonset", "marine-park-vancouver", "downtown-ginkgos", "ladds-elms", "waterfront-cherries", "astoria-column"]);
const SKY = ["vista", "mountain", "reflection", "coast", "city", "alignment", "geology", "historic"];
const SOFT = ["waterfall", "fallcolor", "garden", "wildflowers"];
const LIFE = ["birds", "wildlife"];
const NIGHT = ["night", "aurora"];
const WALK = { road: 5, short: 15, hike: 45, hard: 90 };
const GROUPS = [["all", "All"], ["saved", "Saved"], ["land", "Landscape"], ["water", "Waterfalls"], ["life", "Birds & wildlife"], ["night", "Night sky"], ["city", "City"], ["align", "Alignments"]];
const groupTest = { all: () => true, saved: s => !!SAVED[s.id], land: s => s.cats.some(c => SKY.includes(c) && c !== "city"), water: s => s.cats.includes("waterfall"),
  life: s => s.cats.some(c => LIFE.includes(c)), night: s => s.cats.some(c => NIGHT.includes(c)), city: s => s.cats.includes("city"), align: s => s.cats.includes("alignment") };

/* ---------- storage ---------- */
const store = { get(k, d) { try { const v = localStorage.getItem("ss2:" + k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("ss2:" + k, JSON.stringify(v)); } catch (e) { } } };
let LOC = store.get("loc", null) || { ...HOME };
let WX = store.get("wx", null), KP = store.get("kp", null), NWS = store.get("nws", null);
let DRIVES = store.get("drives", {});
let SAVED = store.get("saved", {}), LOG = store.get("log", []);
const UI = { view: "now", focus: 0, more: false, group: store.get("group", "all"), q: "", sort: "best", inSeason: true };
if (!groupTest[UI.group]) UI.group = "all";
const inGroup = s => (groupTest[UI.group] || groupTest.all)(s);   // the app-wide filter in the header

/* ---------- small helpers ---------- */
const $ = s => document.querySelector(s);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
function km(a, b) { return geoTo(a, b).dist / 1000; }
function dest(p, az, kmD) { const R = 6371, d = kmD / R, la1 = p.lat * D2R, lo1 = p.lon * D2R, th = az * D2R;
  const la2 = Math.asin(Math.sin(la1) * Math.cos(d) + Math.cos(la1) * Math.sin(d) * Math.cos(th));
  const lo2 = lo1 + Math.atan2(Math.sin(th) * Math.sin(d) * Math.cos(la1), Math.cos(d) - Math.sin(la1) * Math.sin(la2));
  return { lat: la2 * R2D, lon: lo2 * R2D }; }
const atHome = () => km(LOC, HOME) < 4;
const locKey = () => LOC.lat.toFixed(2) + "," + LOC.lon.toFixed(2);
function fmtDur(min) { min = Math.round(min); if (min < 60) return min + " min"; const h = Math.floor(min / 60), m = min % 60; return h + " h" + (m ? " " + m + " m" : ""); }
function fmtIn(t) { const m = Math.round((t - Date.now()) / 60000); if (m <= 0) return "now"; return "in " + fmtDur(m); }
function dayWord(t) { const y = laYMD(new Date()), d = laYMD(t); if (d === y) return "Today"; if (d === addDays(y, 1)) return "Tomorrow"; return t.toLocaleDateString("en-US", { timeZone: TZ, weekday: "long" }); }
function fmtDate(t) { return t.toLocaleDateString("en-US", { timeZone: TZ, weekday: "short", month: "short", day: "numeric" }); }
function mmdd(t) { return laYMD(t).slice(5); }
function inRange(md, from, to) { return from <= to ? md >= from && md <= to : md >= from || md <= to; }
function toast(msg, ms) { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(toast._t); toast._t = setTimeout(() => t.hidden = true, ms || 3500); }
function haptic() { try { navigator.vibrate && navigator.vibrate(8); } catch (e) { } }

/* ---------- drive time ---------- */
function driveMin(s) {   // travel minutes: driving, or walking when Settings say you're on foot
  if (PREFS.travel === "walk") return Math.round(km(LOC, s) * 1.3 / 4.8 * 60);
  const k = locKey(); if (DRIVES[k] && DRIVES[k].m[s.id] != null) return DRIVES[k].m[s.id];
  if (atHome() && s.drive != null) return s.drive;
  return Math.round(6 + km(LOC, s) * 1.32 / 62 * 60);
}
async function loadDrives(ids) {
  const k = locKey(); const have = DRIVES[k] && Date.now() - DRIVES[k].at < 6 * 36e5 ? DRIVES[k] : { at: Date.now(), m: {} };
  const need = ids.filter(id => have.m[id] == null).slice(0, 90); if (!need.length) return false;
  const coords = [[LOC.lon, LOC.lat], ...need.map(id => byId[id].park ? [byId[id].park[1], byId[id].park[0]] : [byId[id].lon, byId[id].lat])].map(c => c[0].toFixed(5) + "," + c[1].toFixed(5)).join(";");
  try {
    const r = await fetch("https://router.project-osrm.org/table/v1/driving/" + coords + "?sources=0&annotations=duration");
    const j = await r.json(); if (j.code !== "Ok") return false;
    need.forEach((id, i) => { const sec = j.durations[0][i + 1]; if (sec != null) have.m[id] = Math.round(sec / 60 * 1.08); });
    DRIVES = { [k]: have }; store.set("drives", DRIVES); return true;
  } catch (e) { return false; }
}

/* ---------- weather (Open-Meteo) ---------- */
function wxPoints() { return [...GRID, { id: "me", n: "Here", lat: LOC.lat, lon: LOC.lon }]; }
async function loadWx(force) {
  if (!force && WX && Date.now() - WX.at < 30 * 60000 && WX.key === locKey()) return false;
  const pts = wxPoints();
  const url = "https://api.open-meteo.com/v1/forecast?latitude=" + pts.map(p => p.lat.toFixed(3)).join(",") + "&longitude=" + pts.map(p => p.lon.toFixed(3)).join(",") +
    "&hourly=cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,visibility,relative_humidity_2m,dew_point_2m,temperature_2m,wind_speed_10m,precipitation_probability,weather_code,precipitation" +
    "&past_days=2&forecast_days=5&timeformat=unixtime&wind_speed_unit=mph&temperature_unit=fahrenheit&timezone=GMT";
  try {
    const r = await fetch(url); if (!r.ok) throw new Error("HTTP " + r.status);
    let j = await r.json(); if (!Array.isArray(j)) j = [j];
    WX = { at: Date.now(), key: locKey(), pts: j.map((x, i) => ({ id: pts[i].id, n: pts[i].n, lat: pts[i].lat, lon: pts[i].lon, h: x.hourly })) };
    store.set("wx", WX); return true;
  } catch (e) { WX && (WX.err = String(e.message || e)); return false; }
}
function nearestPt(p, maxKm, exclude) {
  if (!WX) return null; let best = null, bd = 1e9;
  for (const q of WX.pts) { if (exclude && q.id === exclude) continue; const d = km(p, q); if (d < bd) { bd = d; best = q; } }
  return bd <= (maxKm || 60) ? best : null;
}
function hourAt(pt, t) {
  if (!pt) return null; const h = pt.h, ts = t.getTime() / 1000; let bi = -1, bd = 1e12;
  for (let i = 0; i < h.time.length; i++) { const d = Math.abs(h.time[i] - ts); if (d < bd) { bd = d; bi = i; } }
  if (bi < 0 || bd > 5400) return null;
  return { cc: h.cloud_cover[bi], low: h.cloud_cover_low[bi], mid: h.cloud_cover_mid[bi], high: h.cloud_cover_high[bi], vis: h.visibility[bi], rh: h.relative_humidity_2m[bi],
    dew: h.dew_point_2m[bi], tf: h.temperature_2m[bi], wind: h.wind_speed_10m[bi], pop: h.precipitation_probability[bi], code: h.weather_code[bi], precip: h.precipitation ? h.precipitation[bi] || 0 : 0 };
}

/* ---------- light windows ---------- */
function windows(p, n) {
  const out = [], now = Date.now(), y = laYMD(new Date());
  for (let k = 0; k < 3; k++) {
    const e = dayEvents(p, addDays(y, k));
    if (e.sunrise) out.push({ kind: "sunrise", start: e.civilDawn, peak: e.sunrise, end: e.goldEndAM || new Date(e.sunrise.getTime() + 40 * 60000) });
    if (e.sunset) out.push({ kind: "sunset", start: e.goldStartPM || new Date(e.sunset.getTime() - 40 * 60000), peak: e.sunset, end: e.civilDusk });
  }
  return out.filter(w => w.end.getTime() > now).sort((a, b) => a.peak - b.peak).slice(0, n || 3);
}
function nightWindow(p) {
  const y = laYMD(new Date()), now = new Date();
  for (let k = -1; k < 2; k++) {
    const e1 = dayEvents(p, addDays(y, k)), e2 = dayEvents(p, addDays(y, k + 1));
    if (!e1.astroDusk || !e2.astroDawn) continue;
    if (e2.astroDawn > now) {
      // moon-down part of the dark window
      const s = e1.astroDusk, e = e2.astroDawn, step = 15 * 60000; let best = null, cur = null;
      for (let t = s.getTime(); t <= e.getTime(); t += step) { const m = moonPos(new Date(t), p.lat, p.lon); const dark = m.alt < -2 || m.illum < 0.25;
        if (dark && !cur) cur = { s: t }; if (!dark && cur) { cur.e = t; if (!best || cur.e - cur.s > best.e - best.s) best = cur; cur = null; } }
      if (cur) { cur.e = e.getTime(); if (!best || cur.e - cur.s > best.e - best.s) best = cur; }
      const mm = moonPos(new Date((s.getTime() + e.getTime()) / 2), p.lat, p.lon);
      return { kind: "night", start: s, end: e, peak: new Date(best ? (best.s + best.e) / 2 : (s.getTime() + e.getTime()) / 2), dark: best ? { s: new Date(best.s), e: new Date(best.e) } : null, illum: mm.illum };
    }
  }
  return null;
}

const KNAME = { blueAM: "Morning blue hour", sunrise: "Sunrise", morning: "Morning", midday: "Midday", afternoon: "Afternoon", sunset: "Sunset", bluePM: "Evening blue hour", night: "Night sky" };
const KSHORT = { blueAM: "AM blue", sunrise: "Sunrise", morning: "Morning", midday: "Midday", afternoon: "Afternoon", sunset: "Sunset", bluePM: "PM blue", night: "Night" };
const KCAP = { blueAM: 0.95, sunrise: 1, morning: 0.8, midday: 0.62, afternoon: 0.74, sunset: 1, bluePM: 0.95, night: 0.95 };
const DAYK = new Set(["morning", "midday", "afternoon"]), BLUEK = new Set(["blueAM", "bluePM"]), GOLDK = new Set(["sunrise", "sunset"]);
const AMK = new Set(["blueAM", "sunrise", "morning"]), PMK = new Set(["afternoon", "sunset", "bluePM"]);
const mid = (a, b) => new Date((a.getTime() + b.getTime()) / 2);
const addMin = (t, m) => new Date(t.getTime() + m * 60000);
function nightFor(p, ymd) {
  const e1 = dayEvents(p, ymd), e2 = dayEvents(p, addDays(ymd, 1)); if (!e1.astroDusk || !e2.astroDawn) return null;
  const s = e1.astroDusk, e = e2.astroDawn, step = 15 * 60000; let best = null, cur = null;
  for (let t = s.getTime(); t <= e.getTime(); t += step) { const m = moonPos(new Date(t), p.lat, p.lon); const dark = m.alt < -2 || m.illum < 0.25;
    if (dark && !cur) cur = { s: t }; if (!dark && cur) { cur.e = t; if (!best || cur.e - cur.s > best.e - best.s) best = cur; cur = null; } }
  if (cur) { cur.e = e.getTime(); if (!best || cur.e - cur.s > best.e - best.s) best = cur; }
  const mm = moonPos(mid(s, e), p.lat, p.lon);
  return { kind: "night", start: s, end: e, peak: new Date(best ? (best.s + best.e) / 2 : (s.getTime() + e.getTime()) / 2), dark: best && best.e - best.s >= 45 * 60000 ? { s: new Date(best.s), e: new Date(best.e) } : null, illum: mm.illum };
}
const __winCache = {};
function allWindows(p, hours) {
  const now = Date.now(), key = p.lat.toFixed(2) + "," + p.lon.toFixed(2) + "," + Math.floor(now / 300000) + "," + (hours || 40);
  if (__winCache[key]) return __winCache[key];
  const out = [], y = laYMD(new Date());
  for (let k = -1; k < 5; k++) {
    const ymd = addDays(y, k), e = dayEvents(p, ymd); if (!e.sunrise || !e.sunset) continue;
    const civD = e.civilDawn || addMin(e.sunrise, -32), civK = e.civilDusk || addMin(e.sunset, 32);
    const astD = e.astroDawn || addMin(civD, -70), astK = e.astroDusk || addMin(civK, 70);
    const blueAMend = new Date(civD.getTime() + 0.35 * (e.sunrise - civD)), sunsetEnd = new Date(e.sunset.getTime() + 0.35 * (civK - e.sunset));
    const gEnd = e.goldEndAM || addMin(e.sunrise, 45), gStart = e.goldStartPM || addMin(e.sunset, -45);
    out.push({ kind: "blueAM", start: mid(astD, civD), peak: civD, end: blueAMend });
    out.push({ kind: "sunrise", start: blueAMend, peak: e.sunrise, end: gEnd });
    const t11 = laDate(ymd, 11 * 60), t15 = laDate(ymd, 15 * 60);
    const mEnd = new Date(Math.max(t11.getTime(), gEnd.getTime() + 60 * 60000)), dEnd = new Date(Math.min(Math.max(t15.getTime(), mEnd.getTime() + 60 * 60000), gStart.getTime() - 30 * 60000));
    out.push({ kind: "morning", start: gEnd, peak: mid(gEnd, mEnd), end: mEnd });
    if (dEnd > mEnd) out.push({ kind: "midday", start: mEnd, peak: mid(mEnd, dEnd), end: dEnd });
    const aStart = dEnd > mEnd ? dEnd : mEnd; if (gStart > aStart) out.push({ kind: "afternoon", start: aStart, peak: mid(aStart, gStart), end: gStart });
    out.push({ kind: "sunset", start: gStart, peak: e.sunset, end: sunsetEnd });
    out.push({ kind: "bluePM", start: sunsetEnd, peak: civK, end: mid(civK, astK) });
    const nf = nightFor(p, ymd); if (nf) out.push(nf);
  }
  const res = out.filter(w => w.end.getTime() > now && w.start.getTime() < now + (hours || 40) * 36e5).sort((a, b) => a.start - b.start)
    .map(w => (!GOLDK.has(w.kind) && w.kind !== "night" && w.start.getTime() < now) ? { ...w, peak: new Date(Math.max(w.peak.getTime(), now + 15 * 60000)), live: true } : (w.start.getTime() < now ? { ...w, live: true } : w));
  return (__winCache[key] = res);
}
function wTitle(w) {
  if (w.kind === "night") { const d = dayWord(w.start); return w.live ? "Tonight (now)" : d === "Today" ? "Tonight" : d + " night"; }
  return w.live ? `${KNAME[w.kind]} (now)` : `${dayWord(w.peak)} ${KNAME[w.kind].toLowerCase()}`; }

/* ---------- sky scoring ---------- */
const CMP = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
function cmp(az) { return CMP[Math.round(((az % 360) + 360) % 360 / 22.5) % 16]; }
function dayWindow(p) {
  const now = new Date(), e = dayEvents(p, laYMD(now)); if (!e.sunrise || !e.goldStartPM) return null;
  if (now < new Date(e.sunrise.getTime() + 30 * 60000) || now > new Date(e.goldStartPM.getTime() - 60 * 60000)) return null;
  const c = hourAt(nearestPt(p, 60), new Date(now.getTime() + 30 * 60000)); if (!c || (c.cc < 70 && c.pop < 40)) return null;
  return { kind: "day", start: now, peak: new Date(now.getTime() + 30 * 60000), end: e.goldStartPM };
}
let __skyMemo = {}, __skyMemoAt = 0;
function skyAt(p, w) {
  const pt = nearestPt(p, 60); if (!pt) return null;
  const sp = sunPos(w.peak, p.lat, p.lon), probeP = dest(p, sp.az, 90), probePt = nearestPt(probeP, 75, pt && pt.id);
  if (!WX || __skyMemoAt !== WX.at) { __skyMemo = {}; __skyMemoAt = WX ? WX.at : 0; }
  const mk = pt.id + "|" + (probePt ? probePt.id : "") + "|" + w.kind + "|" + w.peak.getTime();
  if (__skyMemo[mk] !== undefined) return __skyMemo[mk];
  return (__skyMemo[mk] = skyCalc(p, w, pt, sp, probePt));
}
function skyCalc(p, w, pt, sp, probePt) {
  const c = hourAt(pt, w.peak); if (!c) return null; const pc = hourAt(probePt, w.peak);
  const canvas = Math.max(c.mid, c.high * 0.9);
  let f = canvas < 10 ? 0.32 : canvas <= 70 ? 0.32 + 0.68 * Math.min(1, (canvas - 10) / 40) : Math.max(0.2, 1 - (canvas - 70) / 30 * 0.8);
  const lowF = c.low >= 75 ? 0.3 : c.low >= 45 ? 0.7 : 1;
  const block = pc ? Math.max(pc.low, pc.mid * 0.6) : null, g = block == null ? 1 : block <= 30 ? 1 : block <= 60 ? 0.72 : 0.38;
  let q = Math.round(100 * f * lowF * g); if (c.pop >= 60) q = 8;
  const fog = AMK.has(w.kind) && ((c.low >= 80 && c.vis < 3000) || (c.rh >= 96 && c.wind <= 3));
  const why = [];
  if (c.pop >= 60) why.push(`${c.pop}% chance of rain`);
  else {
    if (!GOLDK.has(w.kind)) why.push(c.cc >= 80 ? `overcast (${c.cc}%)` : c.cc >= 30 ? `${c.cc}% cloud` : `mostly clear (${c.cc}%)`); else if (canvas >= 15 && canvas <= 75) why.push(`${canvas}% mid/high cloud to catch color`); else if (canvas < 15) why.push(`mostly clear overhead (${c.cc}%)`); else why.push(`thick cloud overhead (${c.cc}%)`);
    if (c.low >= 45) why.push(`${c.low}% low cloud`);
    if (block != null && GOLDK.has(w.kind)) why.push(block <= 30 ? `clear horizon toward the ${w.kind === "sunset" ? "west" : "east"}` : `cloud on the ${w.kind === "sunset" ? "western" : "eastern"} horizon (${block}%)`);
  }
  const prev = [1, 2, 3].map(k => hourAt(pt, new Date(w.peak.getTime() - k * 36e5))).filter(Boolean);
  const prevPop = Math.max(0, ...prev.map(x => x.pop)), prevRain = prev.reduce((a, x) => a + (x.precip || 0), 0);
  const mode = c.pop >= 40 && c.tf <= 34 ? "snow" : c.pop >= 60 ? "rain" : (prevPop >= 60 || prevRain >= 1) && c.pop < 40 && c.cc < 90 ? "clearing" : fog ? "fog" : c.pop >= 30 ? "showers" : c.wind >= 18 ? "wind" : c.cc <= 15 ? "clear" : c.cc >= 85 ? "overcast" : "color";
  if (mode === "clearing") { q = Math.min(100, q + 20); why.unshift("rain clearing just before: light breaking through"); }
  const rainbow = (mode === "showers" || mode === "clearing") && sp.alt > -1 && sp.alt < 40 && c.cc < 90, rbDir = cmp((sp.az + 180) % 360);
  if (rainbow) why.push(`showers with a low sun: rainbow odds, look ${rbDir}`);
  if (mode === "snow") why.unshift(`snow likely (${fmtTemp(c.tf)})`);
  return { ...c, q, fog, canvas, block, why, probe: probePt && probePt.n, mode, rainbow, rbDir, kind: w.kind };
}
function verdict(sk) {
  if (!sk) return { cls: "poor", txt: "No forecast yet" };
  if (BLUEK.has(sk.kind)) {
    if (sk.fog) return { cls: "fog", txt: "Fog: glowing lights, silhouettes, go above it for a sea of cloud" };
    if (sk.mode === "rain" || sk.mode === "snow") return { cls: "mid", txt: "Wet: city lights doubled in the streets, light trails" };
    if (sk.cc <= 30) return { cls: "good", txt: `Clear: deep blue sky${sk.kind === "bluePM" ? " and the Belt of Venus to the east" : " and alpenglow on the peaks"}` };
    if (sk.cc >= 85) return { cls: "mid", txt: "Overcast: city lights, bridges and light trails" };
    return { cls: "good", txt: "Broken cloud: blue sky with texture over the lights" };
  }
  if (DAYK.has(sk.kind)) {
    if (sk.fog) return { cls: "fog", txt: "Fog burning off: forests, silhouettes and layers" };
    if (sk.mode === "snow") return { cls: "good", txt: "Snow: clean forests and falls" };
    if (sk.mode === "rain") return { cls: "mid", txt: "Rain: waterfalls, wet forest, moody mist" };
    if (sk.mode === "clearing") return { cls: "good", txt: "Clearing: dramatic clouds and light breaking through" };
    if (sk.rainbow) return { cls: "good", txt: `Showers and sun: rainbow odds, look ${sk.rbDir}` };
    if (sk.cc >= 75) return { cls: "mid", txt: "Overcast: even light for waterfalls, forests and birds" };
    if (sk.cc >= 30) return { cls: "mid", txt: "Broken cloud: cloud shadows on the ridges" };
    return { cls: "poor", txt: sk.kind === "midday" ? "Clear midday: hard light. Shade, forests, black and white" : "Clear: crisp side light, long shadows" };
  }
  if (sk.fog) return { cls: "fog", txt: "Fog likely in the lowlands: go above it" };
  if (sk.mode === "snow") return { cls: "good", txt: "Snow: fresh snow on forests and falls" };
  if (sk.mode === "rain") return sk.kind === "day" ? { cls: "mid", txt: "Rain: waterfalls, wet forest, moody mist" } : { cls: "poor", txt: `Rain at ${sk.kind}: little color. Wet city lights at blue hour are the best bet` };
  if (sk.mode === "clearing") return { cls: "good", txt: "Storm clearing: dramatic light odds" };
  if (sk.rainbow) return { cls: "good", txt: `Showers and low sun: rainbow odds, look ${sk.rbDir}` };
  if (sk.mode === "wind") return { cls: "mid", txt: `Windy (${fmtWind(sk.wind)}): skip reflections, try streaking clouds` };
  if (sk.q >= 70) return { cls: "good", txt: "Strong color odds" };
  if (sk.q >= 45) return { cls: "good", txt: "Good color odds" };
  if (sk.cc <= 15) return { cls: "mid", txt: "Clear: clean light, peaks and alignments" };
  if (sk.cc >= 85) return { cls: "mid", txt: "Overcast: soft light for waterfalls and birds" };
  return { cls: "mid", txt: "Fair: some color possible" };
}
function lowlandFog(w) { const sk = skyAt(HOME, w) || skyAt(LOC, w); return !!(sk && sk.fog && sk.pop < 40); }

/* ---------- events ---------- */
function wildlifeNow(s, t) {
  const md = mmdd(t || new Date()); const out = [];
  (D.WEVENTS || []).forEach(ev => { if (!ev.spots || !ev.spots.includes(s.id)) return;
    (ev.windows || []).forEach(win => { if (inRange(md, win.from, win.to)) out.push({ ev, peak: win.peak && inRange(md, win.peak[0], win.peak[1]) }); }); });
  return out;
}
let ALIGN_CACHE = null;
function alignEvents() {
  if (ALIGN_CACHE) return ALIGN_CACHE;
  const out = [];
  (D.ALIGN || []).forEach(a => { const v = D.VANT[a.v], tg = D.TARGETS[a.tk]; if (!v || !tg) return;
    out.push({ t: new Date(a.t), spot: v.spot, body: a.b, rising: !!a.r, illum: a.i, what: `${a.b === "sun" ? "Sun" : "Moon"} ${a.r ? "rises" : "sets"} behind ${tg.name}`, from: v.name }); });
  Object.entries(D.PEAKCAL || {}).forEach(([k, rows]) => { const [id, pk] = k.split("|"); const sid = Object.keys(D.PEAK_OF || {}).find(x => D.PEAK_OF[x] === id) || id;
    rows.forEach(r => out.push({ t: new Date(r[0]), spot: byId[sid] ? sid : id, body: r[1] === "s" ? "sun" : "moon", rising: !!r[2], illum: r[3], what: `${r[1] === "s" ? "Sun" : "Moon"} ${r[2] ? "rises" : "sets"} behind ${pk === "Hood" ? "Mt. Hood" : pk === "Adams" ? "Mt. Adams" : "Mt. St. Helens"}`, from: (byId[sid] || byId[id] || {}).name })); });
  Object.entries(D.STREET_OF || {}).forEach(([sid, list]) => list.forEach(([k, lbl]) => (D.STREETCAL[k] || []).forEach(r =>
    out.push({ t: new Date(r[0]), spot: sid, body: r[1] === "s" ? "sun" : "moon", rising: !!r[2], illum: r[3], what: `${r[1] === "s" ? "Sun" : "Moon"} ${r[2] ? "rises" : "sets"} straight down the street`, from: lbl }))));
  const seen = new Set();
  ALIGN_CACHE = out.filter(e => byId[e.spot] && (e.body === "sun" || (e.illum || 0) >= 40)).sort((a, b) => a.t - b.t).filter(e => { const k = e.spot + laYMD(e.t) + e.what; if (seen.has(k)) return false; seen.add(k); return true; });
  return ALIGN_CACHE;
}
function alignOn(s, w) { if (DAYK.has(w.kind)) return null; const d0 = w.start.getTime() - 40 * 60000, d1 = w.end.getTime() + 40 * 60000; return alignEvents().find(e => e.spot === s.id && e.t >= d0 && e.t <= d1); }
function roadStatus(s, t) {
  const md = mmdd(t || new Date()); const r = (D.SEASONAL_ROADS || []).find(x => x.spots.includes(s.id) && inRange(md, x.from, x.to)); return r || null;
}
function showersSoon(days) {
  const now = new Date(), out = [];
  (D.SHOWERS || []).forEach(sh => { for (let k = 0; k <= days; k++) { const t = new Date(now.getTime() + k * 864e5); if (mmdd(t) === sh.peak) out.push({ sh, t }); } });
  return out;
}

/* ---------- spot scoring ---------- */
const FLOODLIT = new Set(["multnomah", "willamette-falls-overlook", "vista-house", "bridge-of-gods", "hood-river-bridge", "astoria-column", "maryhill-museum"]);
const LIGHTTRAILS = new Set(["cape-horn-lookout", "womens-forum", "rocky-butte", "pittock", "council-crest", "scout-broughton-bridge-hood", "hawthorne-bridge", "eastbank-esplanade", "portland-tram", "rowena", "maryhill-loops", "cascade-locks"]);
function sessionFits(ses, kind) {
  if (ses === "both") return true;
  if (ses === "dusk") return kind === "sunset" || kind === "bluePM";
  if (ses === "owl") return kind === "sunset" || kind === "bluePM" || kind === "afternoon";
  if (ses === "dawn") return kind === "blueAM" || kind === "sunrise";
  if (ses === "morning") return kind === "sunrise" || kind === "morning";
  if (ses === "day" || ses === "tide") return DAYK.has(kind);
  return false;
}
function moonEvent(s, w) {
  const e = dayEvents(s, laYMD(w.peak)), lo = w.start.getTime() - 20 * 60000, hi = w.end.getTime() + 25 * 60000;
  for (const [t, rise] of [[e.moonrise, true], [e.moonset, false]]) { if (!t || t.getTime() < lo || t.getTime() > hi) continue;
    const m = moonPos(rise ? addMin(t, 20) : addMin(t, -20), s.lat, s.lon); if (m.illum < 0.45) continue; return { t, rise, az: m.az, illum: m.illum }; }
  return null;
}
function blueParts(s, w, sk, parts, why) {
  const m = sk.mode, wet = m === "rain" || m === "snow", has = k => s.cats.includes(k);
  if (has("city") || has("historic")) { let v = has("city") ? 70 : 48;
    if (WETCITY.has(s.id) && (wet || sk.precip > 0 || m === "clearing")) { v += 14; why.push("wet pavement doubles the lights"); }
    else if (wet && !WETCITY.has(s.id)) { v = 46; why.push("rain softens the distant lights"); }
    if (sk.cc <= 40 && !wet) { v += 5; why.push("deep blue sky behind the lights"); }
    parts.push(v); }
  if (LIGHTTRAILS.has(s.id)) { parts.push(wet ? 60 : 72); why.push("car light trails against the blue"); }
  if (FLOODLIT.has(s.id)) { parts.push(76); why.push("floodlights balance with the sky now"); }
  if (has("reflection")) { const calm = sk.wind <= 4; parts.push(wet ? 30 : calm ? 72 : 46); if (calm && !wet) why.push("calm water mirrors the blue"); }
  if ((has("mountain") || has("vista")) && !wet) { const v = sk.cc <= 30 ? 66 : sk.cc <= 70 ? 50 : 26; parts.push(v); if (sk.cc <= 30) why.push(w.kind === "bluePM" ? "Belt of Venus and earth shadow opposite the sunset" : "alpenglow on the peaks before sunrise"); }
  if (has("coast") && !wet) { parts.push(60); why.push("long exposures turn the surf to mist"); }
  if (has("waterfall") && !FLOODLIT.has(s.id)) parts.push(24);
  if (has("night") || has("aurora")) parts.push(sk.cc <= 30 ? 52 : 30);
  if (s.cats.some(c => LIFE.includes(c))) { let v = 30; const wl = wildlifeNow(s, w.peak);
    const f = wl.find(x => sessionFits(x.ev.session, w.kind)); if (f) { v = f.peak ? 78 : 64; why.unshift(`${f.ev.icon || ""} ${f.ev.name}: ${w.kind === "bluePM" ? "fly-in at dusk" : "fly-out at first light"}`.trim()); }
    if (FOG_ABOVE.includes(s.id)) v = Math.max(v, 30);
    parts.push(wet ? v - 12 : v); }
  if (FOG_ABOVE.includes(s.id) && w.kind === "blueAM" && sk.pop < 50 && lowlandFog(w)) { parts.push(88); why.unshift("above the fog: a blue sea of cloud"); }
  const me = moonEvent(s, w);
  if (me && !wet && sk.cc < 80 && s.cats.some(c => ["mountain", "vista", "coast", "reflection", "city", "alignment"].includes(c))) {
    const faces = me.rise ? s.light !== "sunset" : s.light !== "sunrise";
    if (faces) { parts.push(Math.max(...parts, 55) + 14); why.unshift(`${Math.round(me.illum * 100)}% moon ${me.rise ? "rises" : "sets"} ${fmtT(me.t)}, ${cmp(me.az)}`); } }
  const al = alignOn(s, w); if (al && al.body === "moon" && !wet && sk.cc < 80) { parts.push(Math.max(...parts, 60) + 15); why.unshift(`${al.what} ${fmtT(al.t)}`); }
  if (!parts.length) parts.push(22);
}
function dayParts(s, w, sk, parts, why) {
  const m = sk.mode, wet = m === "rain" || m === "snow", has = k => s.cats.includes(k), k = w.kind, cc = sk.cc;
  const over = cc >= 75 || m === "overcast" || m === "fog" || m === "showers", broken = cc >= 30 && cc < 75, clear = cc < 30 && !wet;
  if (has("waterfall")) { const v = wet ? 86 : over ? 84 : broken ? 56 : 30; parts.push(v); why.push(wet ? "rain: no glare, saturated moss" : over ? "overcast: no harsh highlights on the water" : clear ? "harsh sun on the water; look for a shaded canyon" : "patchy sun: wait for a cloud"); }
  if (has("fallcolor")) { const v = wet ? 74 : over ? 78 : clear && k !== "midday" ? 64 : 46; parts.push(v); why.push(over || wet ? "wet or overcast leaves glow" : clear && k !== "midday" ? "side light through the leaves" : "flat overhead light on the leaves"); }
  if (has("garden") || has("wildflowers")) { let v = wet ? 52 : over ? 70 : k === "morning" ? 62 : k === "midday" ? 40 : 50; if (sk.wind >= 12) { v -= 15; why.push("wind will blur flowers"); } else if (k === "morning" && !wet) why.push("calm morning: dew and still flowers"); parts.push(v); }
  if (s.cats.some(c => LIFE.includes(c))) { let v = k === "morning" ? 60 : k === "midday" ? 36 : 46; if (wet) v -= 15; if (over && !wet) v += 4;
    const wl = wildlifeNow(s, w.peak), f = wl.find(x => sessionFits(x.ev.session, k));
    if (f) { v += f.peak ? 26 : 14; why.unshift(`${f.ev.icon || ""} ${f.ev.name}${f.peak ? " at peak" : " in season"}`.trim()); }
    else if (k === "morning") why.push("morning: birds still active");
    if (s.id === "bonney-butte" && k !== "morning" && !wet) { v = Math.max(v, 70); why.unshift("midday thermals: raptors stream past the ridge"); }
    parts.push(v); }
  if (has("mountain") || has("vista")) { let v;
    if (wet) v = 14; else if (m === "clearing") { v = 72; why.unshift("clearing after rain: clouds breaking around the ridges"); }
    else if (broken && sk.pop < 40) { v = 56; why.push("cloud shadows sweep the ridges"); }
    else if (clear) { v = k === "midday" ? 30 : 48; why.push(k === "midday" ? "flat overhead light; try black and white" : "crisp, low-haze side light"); }
    else v = 26;
    if (has("mountain") && clear && sk.vis > 30000 && k === "morning") { v += 6; why.push("clear, dry air: peaks sharp"); }
    if (sk.rainbow) { v += 20; why.unshift(`showers and sun: rainbow odds, look ${sk.rbDir}`); }
    parts.push(v); }
  if (has("reflection")) { const v = !wet && sk.wind <= 3 ? (k === "morning" ? 62 : 44) : 26; parts.push(v); if (v >= 44) why.push(`calm (${fmtWind(sk.wind)}): clouds mirrored`); }
  if (has("coast")) { let v = wet ? (sk.wind >= 18 ? 64 : 36) : over ? 54 : 40; if (wet && sk.wind >= 18) why.push(`${fmtWind(sk.wind)}: storm surf`); parts.push(v); }
  if (has("geology")) { const v = clear ? (k === "midday" ? 34 : 58) : over ? 42 : 46; if (clear && k !== "midday") why.push("raking side light on the rock"); parts.push(v); }
  if (has("historic")) parts.push(over ? 48 : 38);
  if (has("city")) parts.push(over ? 30 : 24);
  if (FOG_ABOVE.includes(s.id) && k === "morning" && sk.pop < 50 && lowlandFog(w)) { parts.push(80); why.unshift("fog burning off below: layers and rays"); }
  if (!parts.length) parts.push(22);
}
function fitFor(s, w) {
  if (s.closed) return null;
  const road = roadStatus(s, w.peak); if (road && road.level === "closed") return null;
  const why = [], sk = skyAt(s, w), month = +laYMD(w.peak).slice(5, 7);
  const has = list => s.cats.some(c => list.includes(c));
  let parts = [];
  if (w.kind === "night") {
    if (!has(NIGHT) && !s.cats.includes("mountain")) return null;
    const pt = nearestPt(s, 60), c = hourAt(pt, w.peak); let v = c ? (c.cc <= 15 ? 92 : c.cc <= 40 ? 62 : c.cc <= 70 ? 30 : 10) : 40;
    if (c) why.push(c.cc <= 15 ? "clear sky" : c.cc <= 40 ? "some cloud" : "cloudy");
    if (w.dark) why.push(`moon-free ${fmtT(w.dark.s)}–${fmtT(w.dark.e)}`); else { v *= 0.6; why.push(`${Math.round(w.illum * 100)}% moon up all night`); }
    parts.push(has(NIGHT) ? v : v * 0.7);
    if (!w.dark && w.illum >= 0.7 && c && c.cc <= 30 && c.pop < 40 && s.cats.some(k => ["mountain", "waterfall", "vista", "coast"].includes(k))) { parts.push(56); why.unshift("bright moon: moonlit landscape with stars"); }
  } else if (BLUEK.has(w.kind)) {
    if (!sk) return { n: 40, why: ["forecast loading"], sk: null };
    blueParts(s, w, sk, parts, why);
  } else if (DAYK.has(w.kind)) {
    if (!sk) return { n: 40, why: ["forecast loading"], sk: null };
    if (has(NIGHT) && !s.cats.some(k => !NIGHT.includes(k))) return null;
    dayParts(s, w, sk, parts, why);
  } else {
    if (!sk) return { n: 40, why: ["forecast loading"], sk: null };
    const m = sk.mode, wet = m === "rain" || m === "snow", dayW = false;
    if (has(SKY)) { let v = sk.q;
      if (wet) { v = 12;
        if (WETCITY.has(s.id)) { v = dayW ? 34 : 66; why.push("wet streets mirror city lights at blue hour"); }
        if (s.cats.includes("coast") && sk.wind >= 15) { v = Math.max(v, 68); why.push(`${fmtWind(sk.wind)} wind: storm surf`); }
        if (m === "snow" && (s.cats.includes("mountain") || s.cats.includes("vista"))) { v = Math.max(v, 58); why.push("fresh snow on the trees"); }
      } else {
        if (s.cats.includes("mountain")) { if (sk.cc <= 40) { v += 12; why.push("peaks likely out"); } else if (sk.low + sk.mid >= 120) { v -= 18; why.push("peaks may be in cloud"); } }
        if (s.cats.includes("reflection")) { if (sk.wind <= 3) { v += 8; why.push(`calm (${fmtWind(sk.wind)}): reflections`); } else if (sk.wind >= 15) { v -= 15; why.push("too windy for reflections"); } }
        if (sk.rainbow && s.cats.some(c => ["vista", "mountain", "coast", "reflection"].includes(c))) { v += 12; why.push(`rainbow odds: look ${sk.rbDir}`); }
      }
      if (dayW && m !== "clearing") v = Math.min(v, 30);
      parts.push(v); }
    if (has(SOFT)) { const wf = s.cats.includes("waterfall"), fc = s.cats.includes("fallcolor"), gd = s.cats.includes("garden"); let v;
      if (m === "rain") { v = wf ? 88 : fc ? 76 : gd ? 60 : 42; why.push(wf ? "rain: no glare, saturated moss (bring a lens cloth)" : fc ? "wet leaves glow under overcast" : "rain"); }
      else if (m === "snow") { v = wf ? 76 : fc ? 62 : 40; why.push(wf ? "snow on the rocks around the falls" : "snow"); }
      else if (["showers", "overcast", "fog"].includes(m) || sk.cc >= 70) { v = wf ? 84 : 74; why.push("soft overcast light"); }
      else v = sk.cc >= 40 ? 60 : 38;
      if (w.kind === "sunrise" || w.kind === "sunset") {
        if (fc && !wet && sk.cc < 70) { v = Math.max(v, 66); why.push("low sun backlights the leaves"); }
        else if (s.cats.includes("wildflowers") && !wet && sk.cc < 70) { v = Math.max(v, 64); why.push("low warm light on the flowers"); }
        else { v = Math.min(v, wf ? 42 : 50); if (!s.cats.some(c => LIFE.includes(c) || (SKY.includes(c) && c !== "city"))) why.unshift(wet ? (w.kind === "sunrise" ? "rain at dawn: wait for full daylight" : "light fades fast in the rain; go earlier in the day") : wf ? "waterfalls shoot best in daytime shade or overcast, not at " + w.kind : "soft-light subject: better in daytime"); }
      }
      if (sk.wind >= 15 && (s.cats.includes("wildflowers") || fc)) { v -= 10; why.push("wind will blur leaves and flowers"); }
      parts.push(v); }
    if (has(LIFE)) { let v = 48 + (w.kind === "sunrise" ? 8 : 3); if (sk.wind <= 6) v += 4; if (sk.pop >= 60) v -= 18;
      const wl = wildlifeNow(s, w.peak); if (sk.mode === "snow") v -= 5; if (dayW) v -= 4;
      if (wl.length) { const pk = wl.find(x => x.peak), ses = wl[0].ev.session;
        const fits = ses === "both" || ses === "owl" && w.kind === "sunset" || (ses === "dawn" || ses === "morning") && w.kind === "sunrise" || ses === "dusk" && w.kind === "sunset";
        v += (pk ? 24 : 12) * (fits ? 1 : 0.3); why.unshift(`${wl[0].ev.icon || ""} ${wl[0].ev.name}${pk ? " at peak" : " in season"}${fits ? "" : " (better at another time of day)"}`.trim()); }
      if (w.kind === "sunrise" && s.cats.includes("birds") && sk.tf <= 38 && sk.wind <= 4) { v += 6; why.push(`${fmtTemp(sk.tf)} and calm: breath plumes on singing birds`); }
      parts.push(v); }
    if (FOG_ABOVE.includes(s.id) && sk.pop < 50 && lowlandFog(w)) { parts.push(93); why.unshift("should be above the fog"); }
    else { const fa = ((fd("fogabove") || {}).spots || {})[s.id], hit = fa && fa.find(x => Math.abs(new Date(x.t) - w.peak) < 100 * 6e4);
      if (hit && sk.pop < 50) { const m = v => METRIC() ? `${v} m` : `${Math.round(v * 3.281 / 10) * 10} ft`; parts.push(hit.p + 10); why.unshift(`should be above the fog: tops near ${m(hit.top)}, you're at ${m(hit.elev)}`); } }
    const al = alignOn(s, w);
    if (al) { if (wet || m === "overcast" || (sk.block != null && sk.block > 60)) why.push(`${al.what} ${fmtT(al.t)}, likely hidden by cloud`);
      else { parts.push(Math.max(...parts, 60) + 18); why.unshift(`${al.what} ${fmtT(al.t)}`); } }
    if (!parts.length) parts.push(40);
  }
  let n = Math.max(...parts);
  if (s.months && !s.months.includes(month)) { n *= 0.45; why.push("out of season"); }
  const side = AMK.has(w.kind) ? "sunrise" : PMK.has(w.kind) ? "sunset" : null;
  if (side && (GOLDK.has(w.kind) || (BLUEK.has(w.kind) && !s.cats.some(c => LIFE.includes(c)))) && (s.light === "sunrise" || s.light === "sunset") && s.light !== side) { n -= GOLDK.has(w.kind) ? 12 : 6; why.push(`faces ${s.light === "sunrise" ? "east: a sunrise spot" : "west: a sunset spot"}`); }
  if (w.kind !== "night" && !BLUEK.has(w.kind) && s.light === "night") n -= 25;
  n *= KCAP[w.kind] || 1;
  if (road) { n -= 10; why.push(road.short || road.title); }
  return { n: Math.round(clamp(n, 0, 100)), why, sk };
}
function rankFor(w, filter) {
  const now = Date.now(), list = [];
  for (const s of SPOTS) { if ((filter && !filter(s)) || !inGroup(s) || tooFar(s)) continue;
    const f = fitFor(s, w); if (!f) continue;
    const d = driveMin(s), walk = WALK[s.effort] || 15, leave = new Date((w.kind === "night" ? (w.dark ? w.dark.s : w.start) : w.peak).getTime() - (d + walk) * 60000);
    const reachable = now + (d + walk * 0.5) * 60000 < w.end.getTime();
    if (!reachable) continue;
    list.push({ s, f, d, leave, r: f.n - d * 0.28 });
  }
  return list.sort((a, b) => b.r - a.r);
}

/* ---------- rendering: light strip ---------- */
function stripSvg(p, wins) {
  const t0 = Date.now() - 1 * 36e5, span = 36 * 36e5, W = 360, H = 46, x = t => (t - t0) / span * W;
  let rects = "", prev = null, px = 0;
  for (let i = 0; i <= 144; i++) { const t = t0 + i * span / 144, a = sunPos(new Date(t), p.lat, p.lon).alt;
    const c = a > 6 ? "var(--day)" : a > -1 ? "var(--golden)" : a > -6 ? "var(--blue)" : "var(--night)";
    if (c !== prev) { if (prev) rects += `<rect x="${px.toFixed(1)}" y="8" width="${(x(t) - px + .6).toFixed(1)}" height="20" fill="${prev}"/>`; prev = c; px = x(t); } }
  rects += `<rect x="${px.toFixed(1)}" y="8" width="${(W - px).toFixed(1)}" height="20" fill="${prev}"/>`;
  let marks = ""; wins.forEach((w, i) => {
    if (i === UI.focus) { const a = clamp(x(w.start.getTime()), 0, W), b = clamp(x(w.end.getTime()), 0, W); if (b > a) marks += `<rect x="${a.toFixed(1)}" y="5" width="${(b - a).toFixed(1)}" height="26" fill="none" stroke="var(--ink)" stroke-width="2" rx="3"/>`; }
    if (!GOLDK.has(w.kind)) return; const xx = x(w.peak.getTime()); if (xx < 0 || xx > W) return;
    marks += `<text class="lbl" x="${clamp(xx, 22, W - 22)}" y="44" text-anchor="middle">${w.kind === "sunrise" ? "↑" : "↓"} ${fmtT(w.peak).replace(" ", "")}</text>`; });
  const nx = x(Date.now());
  return `<div class="strip" aria-hidden="true"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="height:56px">${rects}${marks}<line class="now" x1="${nx}" x2="${nx}" y1="2" y2="34"/><text class="lbl" x="${nx + 3}" y="6" style="font-size:10px">now</text></svg></div>`;
}
function skyBars(sk) {
  if (!sk) return "";
  const row = (lbl, v, cls) => `<span>${lbl}</span><span class="bar ${cls || ""}"><i style="width:${clamp(v, 0, 100)}%"></i></span><span>${Math.round(v)}%</span>`;
  return `<div class="sky">${row("High cloud", sk.high)}${row("Mid cloud", sk.mid)}${row("Low cloud", sk.low, "low")}${sk.block != null ? row("Horizon", sk.block, "low") : ""}</div>`;
}
function scoreCls(n) { return n >= 70 ? "s-hi" : n >= 45 ? "s-mid" : "s-lo"; }
function pickRow(x, w) {
  const leave = x.leave, soon = leave - Date.now() < 3 * 36e5;
  return `<button class="pick" data-spot="${x.s.id}"><span class="score ${scoreCls(x.f.n)}">${x.f.n}</span>
    <span><b>${esc(x.s.name)}</b><small class="cat">${esc(((D.CATS || {})[primaryCat(x.s)] || {}).label || "")}</small><small>${esc(x.f.why.slice(0, 2).join("; ") || x.s.region)}</small></span>
    <span class="drive">${fmtDur(x.d)}<small>${soon ? (leave < Date.now() ? "leave now" : "leave " + fmtT(leave)) : esc(x.s.region.split(" · ")[0])}</small></span></button>`;
}

/* ---------- Now ---------- */
function primaryCat(s) { return s.cats.find(c => c !== "alignment") || s.cats[0]; }
function diversify(list, n) { const out = [], used = new Set();
  for (const x of list) { if (out.length >= n) break; const c = primaryCat(x.s);
    if (!used.has(c) || !out.length || x.r < out[0].r - 15) { out.push(x); used.add(c); } }
  for (const x of list) { if (out.length >= n) break; if (!out.includes(x)) out.push(x); }
  return out.sort((a, b) => b.r - a.r); }
const PLAN_HOURS = 112;   // ~4.5 days: covers the whole weekend from Thursday
const KSHORT2 = { blueAM: "Blue hour", sunrise: "Sunrise", morning: "Morning", midday: "Midday", afternoon: "Afternoon", sunset: "Sunset", bluePM: "Blue hour", night: "Night" };
function winDay(w) { return laYMD(w.kind === "night" ? w.start : w.peak); }
function dayTab(ymd) { const y = laYMD(new Date()); if (ymd === y) return "Today"; if (ymd === addDays(y, 1)) return "Tomorrow";
  return new Date(ymd + "T12:00:00").toLocaleDateString("en-US", { weekday: "short" }); }
let __topsKey = "", __tops = [];
function windowTops(all) {   // best spot per window, cached per forecast/feed state
  const k = all.length + "|" + SPOTS.length + "|" + (all[0] && all[0].start.getTime()) + "|" + (WX ? WX.at : 0) + "|" + (window.FEED && FEED.m ? FEED.m.gen : "") + "|" + Object.keys(SAVED).length + "|" + LOC.lat + "|" + UI.group + "|" + PREFS.travel + maxTravel();
  if (k !== __topsKey) { __tops = all.map(x => rankFor(x)[0] || null); __topsKey = k; }
  return __tops;
}
function chipTime(w) { return w.kind === "night" ? (w.dark ? fmtT(w.dark.s) : "all night") : w.live ? "now" : fmtT(GOLDK.has(w.kind) ? w.peak : w.start); }
function plannerHtml(all, tops) {
  const days = [...new Set(all.map(winDay))];
  if (!UI.day || !days.includes(UI.day)) UI.day = winDay(all[UI.focus]);
  const dayBest = d => Math.max(0, ...all.map((w, i) => winDay(w) === d && tops[i] ? tops[i].f.n : 0));
  const alertAt = (window.upcoming ? upcoming() : []).map(a => new Date(a.at).getTime());
  let h = `<div class="planner" id="planner"><div class="daytabs" role="tablist">${days.map(d => { const n = dayBest(d);
    return `<button class="daytab" role="tab" data-day="${d}" aria-selected="${d === UI.day}"><span>${dayTab(d)}</span><small class="${scoreCls(n)}">${n || "–"}</small></button>`; }).join("")}</div>`;
  const idx = all.map((w, i) => i).filter(i => winDay(all[i]) === UI.day);
  const best = Math.max(0, ...idx.map(i => tops[i] ? tops[i].f.n : 0));
  h += `<div class="winchips">${idx.map(i => { const w = all[i], t = tops[i], n = t ? t.f.n : 0;
    const flag = alertAt.some(x => x >= w.start.getTime() && x < w.end.getTime());
    return `<button class="winchip${i === UI.focus ? " on" : ""}" data-focus="${i}" aria-pressed="${i === UI.focus}"><span class="wk">${KSHORT2[w.kind]}${flag ? ` <i class="adot" title="alert"></i>` : ""}</span><span class="wt">${chipTime(w)}</span><span class="score sm ${scoreCls(n)}">${n || "–"}</span>${n && n === best ? `<span class="wbest">best</span>` : ""}</button>`; }).join("")}</div></div>`;
  return h;
}
function renderNow() {
  const el = $("#v-now"); const all = allWindows(LOC, PLAN_HOURS);
  if (!all.length) { el.innerHTML = `<p class="empty">Working out the light…</p>`; return; }
  UI.focus = clamp(UI.focus, 0, all.length - 1);
  const w = all[UI.focus], tops = windowTops(all);
  const sk = w.kind === "night" ? null : skyAt(LOC, w), v = w.kind === "night" ? null : verdict(sk);
  const ranked = rankFor(w); const top = diversify(ranked, 3), more = ranked.filter(x => !top.includes(x)).slice(0, 7);
  const timeTxt = !GOLDK.has(w.kind) && w.kind !== "night" ? `${fmtT(w.start)}–${fmtT(w.end)}` : w.kind === "night" ? (w.dark ? `${fmtT(w.dark.s)}–${fmtT(w.dark.e)} moon-free` : `Moon ${Math.round(w.illum * 100)}% all night`) : `${fmtT(w.peak)} · golden ${fmtT(w.start)}–${fmtT(w.end)}`;
  let h = plannerHtml(all, tops);
  h += `<div class="window" id="winDetail"><div class="wtitle"><h2>${wTitle(w)}</h2><span class="when">${w.live ? "until " + fmtT(w.end) : fmtIn(w.kind === "night" && w.dark ? w.dark.s : w.start)}</span></div>
    <p class="muted" style="margin:2px 0 0">${timeTxt}</p>`;
  if (v) h += `<p class="verdict ${v.cls}">${v.txt}</p><p class="why">${esc(sk ? sk.why.join(", ") : (WX ? "No forecast for this place." : "Loading the forecast…"))}</p>${skyBars(sk)}`;
  else { const c = hourAt(nearestPt(LOC, 60), w.peak); h += `<p class="verdict ${c && c.cc <= 20 ? "good" : "mid"}">${c ? (c.cc <= 20 ? "Clear and dark enough for stars" : c.cc <= 50 ? "Partly cloudy: gaps for stars" : "Cloudy: skip the stars") : "Forecast doesn't reach this far yet"}</p>
    <button class="chip" data-v="sky" style="margin:4px 0 8px">Night sky details: Milky Way, moon, planets ›</button>`; }
  h += top.length ? `<ul class="picks">${top.map(x => `<li>${pickRow(x, w)}</li>`).join("")}</ul>` : `<p class="empty">No spots you can reach in time. Pick a later window above.</p>`;
  if (more.length) h += UI.more ? `<ul class="picks" style="border-top:0">${more.map(x => `<li>${pickRow(x, w)}</li>`).join("")}</ul>` : `<button class="more" id="moreBtn">${more.length} more options</button>`;
  h += `</div>`;
  h += `<p class="muted scorenote">Scores compare across windows: a midday 50 is a decent midday, a sunset 50 is a weak sunset. Days 3–5 use a single forecast model, so treat them as rough.</p>`;
  h += specialsHtml();
  el.innerHTML = h;
  const ids = ranked.slice(0, 40).map(x => x.s.id);
  if (!atHome() || LOC.src === "gps") loadDrives(SPOTS.filter(s => km(LOC, s) < 160).sort((a, b) => km(LOC, a) - km(LOC, b)).slice(0, 80).map(s => s.id).concat(ids)).then(ch => ch && render());
  const on = el.querySelector(".winchip.on"); if (on && on.scrollIntoView) on.scrollIntoView({ block: "nearest", inline: "center" });
}
function specialsHtml() {
  const items = [], now = new Date();
  // aurora
  if (KP && KP.max != null && KP.max >= 5) items.push(["🌌", `Aurora possible: Kp ${KP.max.toFixed(1)} forecast`, `${KP.when || ""}. Washougal needs about Kp 6 on camera; Trout Lake or Satus Pass about 5.5.`]);
  // rainy-day playbook
  { const w0 = allWindows(LOC, 40)[0], s0 = w0 && skyAt(LOC, w0), mo = +laYMD(now).slice(5, 7);
    if (s0 && ["rain", "showers", "snow"].includes(s0.mode)) {
      const best = (cat) => { const r = rankFor(w0, s => s.cats.includes(cat))[0]; return r ? r.s : null; };
      const wf = best("waterfall"), ct = best("city"), fc = mo >= 9 && mo <= 11 ? best("fallcolor") : null;
      const ideas = [wf && `Waterfalls run biggest now; ${wf.name} is your best bet. Use 1/4–1 s and wipe the lens between frames.`,
        fc && `Wet leaves are at their most saturated: ${fc.name}. A polarizer cuts the glare off wet leaves.`,
        ct && `At blue hour, puddles and wet pavement mirror the lights. Shoot low at ${ct.name}.`,
        mo >= 10 && mo <= 11 ? "Mushroom season: look on mossy logs along Gorge falls trails. The 70–300 focuses close enough for raindrop details." : "Use the 70–300 at minimum focus for raindrops on leaves, spider webs and lichen.",
        typeof outsideCoverage === "function" && outsideCoverage() ? "When the rain lifts, mist often hangs on hills and over water: the half hour after a shower is worth being out." : "When the rain lifts, mist hangs on the Gorge cliffs. Crown Point and Cape Horn are the classic views of it.",
        s0.mode === "snow" ? "Snow plus overcast gives the evergreens clean, graphic shapes. Overexpose +1 so the snow stays white." : ""].filter(Boolean);
      items.push(["☔", s0.mode === "snow" ? "Snow-day ideas" : "Rainy-day ideas", ideas.join(" ")]); } }
  // NWS alerts
  (NWS && NWS.items || []).slice(0, 2).forEach(a => items.push(["⚠️", a.headline, a.area || ""]));
  // meteors
  showersSoon(10).forEach(({ sh, t }) => { const m = moonPos(new Date(t.getTime()), LOC.lat, LOC.lon); items.push(["☄️", `${sh.n} peak ${fmtDate(t)}`, `Up to ${sh.zhr}/hr in a dark sky. ${sh.note || ""} Moon ${Math.round(m.illum * 100)}% lit.`]); });
  // alignments within 14 days, nearest first
  const soon = alignEvents().filter(e => e.t > now && e.t - now < 14 * 864e5).map(e => ({ e, d: driveMin(byId[e.spot]) })).filter(x => x.d <= 90).sort((a, b) => a.e.t - b.e.t).slice(0, 4);
  soon.forEach(({ e, d }) => items.push(["🎯", `${fmtDate(e.t)} ${fmtT(e.t)}: ${e.what}`, `${e.from || byId[e.spot].name} · ${fmtDur(d)}`, e.spot]));
  // wildlife at peak
  const md = mmdd(now); (D.WEVENTS || []).forEach(ev => (ev.windows || []).forEach(win => { if (win.peak && inRange(md, win.peak[0], win.peak[1])) items.push([ev.icon || "🦅", `${ev.name}: peak now`, ev.what || "", ev.spots && ev.spots[0]]); }));
  if (!items.length) return "";
  return `<div class="sect"><h3>Also worth knowing</h3>${items.map(([ic, t, p, sid]) => `<div class="item"${sid ? ` data-spot="${sid}" role="button" tabindex="0"` : ""}><b>${ic} ${esc(t)}</b>${p ? `<p>${esc(p)}</p>` : ""}</div>`).join("")}</div>`;
}

/* ---------- Spots ---------- */
function renderSpots() {
  const el = $("#v-spots"), allW = allWindows(LOC, PLAN_HOURS), w = allW[UI.focus] || allW[0]; const month = +laYMD(new Date()).slice(5, 7);
  let list = SPOTS.filter(s => !s.closed && inGroup(s)); const farN = UI.showFar ? 0 : list.filter(tooFar).length; if (!UI.showFar) list = list.filter(s => !tooFar(s));
  if (UI.inSeason && UI.group !== "saved" && UI.group !== "new") list = list.filter(s => !s.months || s.months.includes(month));
  if (UI.q) { const q = UI.q.toLowerCase(); list = list.filter(s => (s.name + " " + s.region + " " + s.cats.join(" ") + " " + (s.tip || "")).toLowerCase().includes(q)); }
  let rows = list.map(s => ({ s, f: w ? fitFor(s, w) || { n: 0, why: [] } : { n: 0, why: [] }, d: driveMin(s) }));
  if ((UI.group === "new" || UI.sort === "new") && typeof newestRank === "function") rows.sort((a, b) => newestRank(b.s) - newestRank(a.s)); else rows.sort(UI.sort === "near" ? (a, b) => a.d - b.d : UI.sort === "az" ? (a, b) => a.s.name.localeCompare(b.s.name) : (a, b) => (b.f.n - b.d * 0.28) - (a.f.n - a.d * 0.28));
  const shown = rows.slice(0, UI.limit || 40);
  el.innerHTML = `${filtNote()}<form class="search" id="spotSearch"><input id="spotQ" type="search" placeholder="Search spots, subjects, places" value="${esc(UI.q)}" aria-label="Search spots"></form>
   <div class="sortrow"><label>For <select id="whenSel" aria-label="Which light window">${whenOpts(allW)}</select></label></div>
   <div class="sortrow"><label><input type="checkbox" id="inSeason" ${UI.inSeason ? "checked" : ""}> In season</label>
     <label>Sort <select id="sortSel"><option value="best"${UI.sort === "best" ? " selected" : ""}>Best match</option><option value="near"${UI.sort === "near" ? " selected" : ""}>Closest</option><option value="az"${UI.sort === "az" ? " selected" : ""}>A–Z</option>${typeof newestRank === "function" ? `<option value="new"${UI.sort === "new" ? " selected" : ""}>Newest added</option>` : ""}</select></label></div>
   ${farN ? `<p class="filtnote">${farN} spot${farN === 1 ? "" : "s"} more than ${fmtDur(maxTravel())} ${PREFS.travel === "walk" ? "on foot" : "by car"} hidden <button class="chip" id="showFar">Show them</button></p>` : ""}
   ${shown.length ? `<ul class="picks">${shown.map(x => `<li>${pickRow({ ...x, leave: new Date(8.64e15) }, w)}</li>`).join("")}</ul>` : `<p class="empty">${UI.group === "saved" ? "Nothing saved yet. Open a spot and tap Save." : "No spots match. Clear the search or turn off In season."}</p>`}
   ${rows.length > shown.length ? `<button class="more" id="moreSpots">Show ${Math.min(40, rows.length - shown.length)} more</button>` : ""}
   ${LOG.length ? `<div class="sect"><h3>Your shot log</h3>${LOG.slice(0, 12).map(l => `<div class="item" data-spot="${l.id}" role="button" tabindex="0"><b>${esc((byId[l.id] || {}).name || l.id)}</b><p>${fmtDate(new Date(l.t))} ${fmtT(new Date(l.t))}${l.c ? " · " + esc(l.c) : ""}</p></div>`).join("")}</div>` : ""}`;
}

/* ---------- Calendar ---------- */
function renderCal() {
  const el = $("#v-cal"), now = new Date(), days = 45, ev = [];
  alignEvents().filter(e => e.t > now && e.t - now < days * 864e5).forEach(e => { const d = driveMin(byId[e.spot]); if (d <= 120) ev.push({ t: e.t, ic: e.body === "sun" ? "☀️" : "🌕", title: `${e.what}`, sub: `${e.from || byId[e.spot].name} · ${fmtT(e.t)} · ${fmtDur(d)}${e.illum ? " · " + e.illum + "% lit" : ""}`, spot: e.spot }); });
  showersSoon(days).forEach(({ sh, t }) => ev.push({ t, ic: "☄️", title: `${sh.n} meteor shower peak`, sub: `Up to ${sh.zhr}/hr. ${sh.note || ""}` }));
  for (let k = 0; k < days; k++) { const t = new Date(now.getTime() + k * 864e5), md = mmdd(t), mdPrev = mmdd(new Date(t.getTime() - 864e5));
    (D.WEVENTS || []).forEach(e => (e.windows || []).forEach(win => {
      if (md === win.from) ev.push({ t, ic: e.icon || "🦅", title: `${e.name} season starts`, sub: e.what || "", spot: e.spots && e.spots[0] });
      if (win.peak && md === win.peak[0]) ev.push({ t, ic: e.icon || "🦅", title: `${e.name}: peak begins`, sub: e.count || e.what || "", spot: e.spots && e.spots[0] });
    }));
    const m0 = moonPos(new Date(t.getTime()), LOC.lat, LOC.lon), m1 = moonPos(new Date(t.getTime() + 864e5), LOC.lat, LOC.lon);
    if (m0.illum < 0.985 && m1.illum >= 0.985 || (m0.illum >= 0.985 && m0.illum > m1.illum && moonPos(new Date(t.getTime() - 864e5), LOC.lat, LOC.lon).illum < m0.illum)) ev.push({ t, ic: "🌕", title: "Full moon", sub: "Moonrise at sunset: big moon over the Gorge from a high spot." });
    if (m0.illum > 0.015 && m1.illum <= 0.015) ev.push({ t, ic: "🌑", title: "New moon", sub: "Darkest nights of the month for stars." });
  }
  ev.sort((a, b) => a.t - b.t);
  const by = {}; ev.forEach(e => { const k = laYMD(e.t); (by[k] = by[k] || []).push(e); });
  el.innerHTML = `<h2 style="font-size:26px;margin:8px 0 0">Next ${days} days</h2><p class="muted" style="margin:2px 0 0">Alignments within 2 hours of ${esc(LOC.label)}, meteor showers, wildlife seasons and moon phases.</p>` +
    (Object.keys(by).length ? Object.entries(by).map(([k, list]) => `<div class="day"><h4>${fmtDate(list[0].t)}</h4>${list.map(e => `<button class="ev"${e.spot ? ` data-spot="${e.spot}"` : ""}><span class="ic">${e.ic}</span><span><b>${esc(e.title)}</b><small>${esc(e.sub)}</small></span></button>`).join("")}</div>`).join("") : `<p class="empty">Nothing scheduled.</p>`);
}

/* ---------- Map ---------- */
let MAP = null, MAPLAYER = null;
function renderMap() {
  if (!window.L) { $("#map").innerHTML = `<p class="empty" style="padding:20px">The map needs a connection the first time it loads.</p>`; return; }
  const w = allWindows(LOC, PLAN_HOURS)[UI.focus] || allWindows(LOC, PLAN_HOURS)[0];   // the window picked in the planner
  if (!MAP) { MAP = L.map("map", { zoomControl: false }).setView([LOC.lat, LOC.lon], 9);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 17, attribution: "© OpenStreetMap" }).addTo(MAP);
    L.control.zoom({ position: "topright" }).addTo(MAP); }
  setTimeout(() => MAP.invalidateSize(), 50);
  if (MAPLAYER) MAPLAYER.remove(); MAPLAYER = L.layerGroup().addTo(MAP);
  L.circleMarker([LOC.lat, LOC.lon], { radius: 7, color: "#fff", weight: 2, fillColor: "#C98A1E", fillOpacity: 1 }).addTo(MAPLAYER).bindTooltip("You");
  const month = +laYMD(new Date()).slice(5, 7);
  SPOTS.forEach(s => { if (s.closed || !inGroup(s) || (s.months && !s.months.includes(month))) return; const f = w ? fitFor(s, w) : null; const n = f ? f.n : 0;
    const far = tooFar(s), col = far ? "#B4BEBF" : n >= 70 ? "#3D6A49" : n >= 45 ? "#C98A1E" : "#7B8A8C";
    L.circleMarker([s.lat, s.lon], { radius: far ? 4 : n >= 70 ? 8 : 6, color: "#fff", weight: far ? 1 : 1.5, fillColor: col, fillOpacity: far ? .7 : .95 }).addTo(MAPLAYER)
      .on("click", () => openSpot(s.id)); });
  $("#mapLegend").innerHTML = (UI.group !== "all" ? `${esc((GROUPS.find(g => g[0] === UI.group) || [, ""])[1])} only · ` : "") + (w ? `Colored for ${esc(wTitle(w).toLowerCase())}: <span style="color:#3D6A49">●</span> great <span style="color:#C98A1E">●</span> good <span style="color:#7B8A8C">●</span> fair` : "");
}

/* ---------- Spot sheet ---------- */
function hashStr(t) { let x = 2166136261; for (const ch of t) { x ^= ch.charCodeAt(0); x = Math.imul(x, 16777619); } return x >>> 0; }
function sentences(t) { return String(t || "").split(/(?<=[.!?])\s+(?=[A-Z0-9“"(])/).filter(Boolean); }
function pickRun(t, n, seed) { const ss = sentences(t); if (ss.length <= n) return ss.join(" "); if (n === 1) return ss[seed % ss.length];
  const i = seed % ss.length, j = (i + 1 + (seed >>> 4) % (ss.length - 1)) % ss.length; return [Math.min(i, j), Math.max(i, j)].map(k => ss[k]).join(" "); }
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function monthsTxt(ms) { if (!ms || ms.length >= 12) return "any month"; const runs = []; let st = null, pv = null;
  const sorted = ms.slice().sort((a, b) => a - b);
  sorted.forEach(m => { if (st == null) { st = pv = m; } else if (m === pv + 1) pv = m; else { runs.push([st, pv]); st = pv = m; } }); runs.push([st, pv]);
  if (runs.length > 1 && runs[0][0] === 1 && runs[runs.length - 1][1] === 12) { const f = runs.shift(); runs[runs.length - 1][1] = f[1]; }
  return runs.map(([a, b]) => a === b ? MON[a - 1] : `${MON[a - 1]}–${MON[b - 1]}`).join(", "); }
function planLine(s) {
  const bits = [], L = { sunrise: "a sunrise spot", sunset: "a sunset spot", both: "works at sunrise or sunset", overcast: "an overcast-day spot", night: "a night spot" }[s.light];
  bits.push(`${L ? L[0].toUpperCase() + L.slice(1) : "A flexible spot"}, best ${monthsTxt(s.months)}.`);
  bits.push({ road: "It's roadside, so it works on short notice when conditions line up.", short: "A short walk, so you can wait for the forecast and still make it.", hike: "It's a real hike: commit only when the forecast is solid and allow time to get there before the light.", hard: "It's strenuous: pick your day carefully and carry a headlamp for the walk out." }[s.effort] || "");
  const pv = (D.PEAKVIS || {})[(D.PEAK_OF || {})[s.id] || s.id];
  if (pv) { const vis = pv.filter(r => r[3] >= 0.3); if (vis.length) bits.push(`From here ${vis.map(r => `${r[0] === "Hood" ? "Mt. Hood" : r[0] === "Adams" ? "Mt. Adams" : r[0] === "St. Helens" ? "St. Helens" : r[0]} sits ${cmp(r[1])} at ${r[2].toFixed(1)}° up`).join(", ")}; at 300 mm that's a big peak in the frame.`); }
  const ev = (D.WEVENTS || []).filter(e => e.spots && e.spots.includes(s.id)); if (ev.length) bits.push(`Wildlife timing: ${ev.map(e => e.name + " (" + e.windows.map(w => w.from.replace("-", "/") + "–" + w.to.replace("-", "/")).join(", ") + ")").join("; ")}.`);
  if ((D.GAUGES || {})[s.id]) bits.push("Check the river gauge below: flow changes the look more than the light.");
  if ((D.TIDES || {})[s.id]) bits.push("Plan around the tide table below. A falling tide near sunset leaves wet sand that mirrors the sky.");
  return bits.filter(Boolean).join(" ");
}
function proNotes(s) {
  const P = (D.PRO || {})[s.id] || {}, seed = hashStr(s.id), cats = s.cats.filter(k => D.CRAFT && D.CRAFT[k]);
  const landCats = cats.filter(k => !LIFE.includes(k)), lifeCats = cats.filter(k => LIFE.includes(k));
  let land = P.land && P.land.length >= 90 ? P.land : (P.land ? P.land + " " : "");
  if (land.length < 90 && landCats.length) { const base = land; land = "";  { land = pickRun(D.CRAFT[landCats[0]].land, 2, seed); if (landCats[1]) land += " " + pickRun(D.CRAFT[landCats[1]].land, 1, seed >>> 3); land = base + land; } }
  let bird = P.bird && P.bird.length >= 70 ? P.bird : "";
  if (!bird && P.bird) bird = P.bird + " ";
  if (bird.length < 70 && lifeCats.length) bird = bird + pickRun(D.CRAFT[lifeCats[0]].bird, 2, seed >>> 5) + (lifeCats[1] ? " " + pickRun(D.CRAFT[lifeCats[1]].bird, 1, seed >>> 7) : "");
  else if (!bird && landCats.length && seed % 3 === 0) bird = pickRun(D.CRAFT[landCats[0]].bird, 1, seed >>> 9);
  const pool = cats.flatMap(k => D.CRAFT[k].idea || []), ideas = [...(P.idea || [])];
  for (let i = 0; i < pool.length && ideas.length < (P.idea ? 4 : 2); i++) { const x = pool[(seed + i * 7) % pool.length]; if (!ideas.includes(x)) ideas.push(x); }
  (D.IDEAS || []).filter(x => x[3] === s.id).forEach(x => ideas.unshift(`${x[1]}: ${x[2]}`));
  const longThink = P.think && P.think.length >= 90;
  return { think: longThink ? P.think : ((P.think ? P.think + " " : "") + planLine(s)), plan: longThink ? planLine(s) : "", land, bird, ideas, own: !!P.land };
}
function wxIcon(c, t, p) { const up = sunPos(t, p.lat, p.lon).alt > 0;
  if (c.pop >= 50 && c.tf <= 34) return "🌨"; if (c.pop >= 50) return "🌧"; if (c.vis < 1500) return "🌫"; if (c.cc >= 85) return "☁️"; if (c.cc >= 40) return up ? "⛅" : "☁️"; return up ? "☀️" : "🌙"; }
function hours12(s) {
  const pt = nearestPt(s, 60); if (!pt) return ""; const t0 = Math.ceil(Date.now() / 36e5) * 36e5; let cells = "";
  for (let k = 0; k < 12; k++) { const t = new Date(t0 + k * 36e5), c = hourAt(pt, t); if (!c) continue;
    cells += `<div><small>${t.toLocaleTimeString("en-US", { timeZone: TZ, hour: "numeric" }).replace(" ", "").toLowerCase()}</small><span>${wxIcon(c, t, s)}</span><small>${fmtDeg(c.tf)}</small>${c.pop >= 30 ? `<small class="pop">${c.pop}%</small>` : ""}</div>`; }
  return cells ? `<div class="hours" aria-label="Next 12 hours here">${cells}</div>` : "";
}
function nightHelp(s) {
  const e = dayEvents(s, laYMD(new Date())), m = moonPos(new Date(), s.lat, s.lon), nw = nightWindow(s);
  const npf = (f, N) => Math.round((35 * N + 30 * 3.03) / f);
  return `<details open><summary>Night settings for your X-T5</summary><ul class="plain">
    <li>Moon ${Math.round(m.illum * 100)}% lit${e.moonrise ? ", rises " + fmtT(e.moonrise) : ""}${e.moonset ? ", sets " + fmtT(e.moonset) : ""}.${nw && nw.dark ? ` Moon-free dark ${fmtT(nw.dark.s)}–${fmtT(nw.dark.e)}.` : ""}</li>
    <li>Pinpoint stars: 16 mm f/2.8 → ${npf(16, 2.8)} s max; 27 mm f/2.8 → ${npf(27, 2.8)} s (NPF rule at the X-T5's pixel size). ISO 3200–6400.</li>
    <li>Focus: magnify a bright star or planet in live view, focus by hand, then tape the ring.</li>
    <li>Turn on Long Exposure NR for single frames; turn it off when stacking.</li></ul></details>`;
}
function openSpot(id) {
  const s = byId[id]; if (!s) return; haptic();
  const wins = allWindows(s, 40), month = +laYMD(new Date()).slice(5, 7);
  const d = driveMin(s), pro = proNotes(s), road = roadStatus(s), pv = (D.PEAKVIS || {})[(D.PEAK_OF || {})[s.id] || s.id];
  const al = alignEvents().filter(e => e.spot === s.id && e.t > new Date()).slice(0, 4);
  const srcs = [...new Set(s.src || [])].map(k => D.SRC[k]).filter(Boolean);
  const also = (D.ALSO || {})[s.id] || [];
  const la = s.lat.toFixed(5), lo = s.lon.toFixed(5);
  const n3 = wins.map(w => { const f = fitFor(s, w); const dw = w.kind === "night" ? dayWord(w.start) : dayWord(w.peak); return `<div><small>${w.kind === "night" && dw === "Today" ? "Tonight" : ({ Today: "Today", Tomorrow: "Tmrw" })[dw] || dw.slice(0, 3)}</small><small><b class="k">${KSHORT[w.kind]}</b></small><b style="color:var(${f && f.n >= 70 ? "--moss" : f && f.n >= 45 ? "--gold" : "--muted"})">${f ? f.n : "–"}</b><small>${fmtT(GOLDK.has(w.kind) ? w.peak : w.start)}</small></div>`; }).join("");
  const wl = wildlifeNow(s);
  let h = `<h2 id="sheetTitle">${esc(s.name)}</h2><p class="sub">${esc(s.region)} · ${fmtDur(d)} drive${s.effort ? " · " + ({ road: "roadside", short: "short walk", hike: "hike", hard: "strenuous" }[s.effort]) : ""}${s.approx ? " · approximate pin" : ""}</p>
    <div class="actions"><a class="btn primary" href="https://maps.apple.com/?daddr=${s.park ? s.park[0] : la},${s.park ? s.park[1] : lo}&dirflg=d">Directions${s.park ? " to trailhead" : ""}</a>
      <button class="btn" id="saveBtn" data-id="${s.id}">${SAVED[s.id] ? "★ Saved" : "☆ Save"}</button>
      <button class="btn" id="shotBtn" data-id="${s.id}">📷 Shot it</button>${navigator.share ? `<button class="btn" id="shareBtn" data-id="${s.id}">Share</button>` : ""}</div>
    ${hours12(s)}
    <p class="label" style="margin-bottom:0">Scores here, every window</p><div class="next3 nextw">${n3}</div>`;
  if (road) h += `<div class="alertbox"><b>${esc(road.title)}</b><br>${esc(road.text || road.short || "")}</div>`;
  if (s.alert) h += `<div class="alertbox">${esc(s.alert)}</div>`;
  if (wl.length) h += wl.map(x => `<div class="item"><b>${x.ev.icon || ""} ${esc(x.ev.name)}${x.peak ? " — peak now" : " — in season"}</b><p>${esc(x.ev.tips || x.ev.what || "")}</p></div>`).join("");
  h += `<div class="prose">${s.why ? `<p>${esc(s.why)}</p>` : ""}<p>${esc(s.tip || "")}</p>${s.lens ? `<p><b>Lens:</b> ${esc(s.lens)}</p>` : ""}${s.pass ? `<p><b>Pass:</b> ${esc(s.pass)}</p>` : ""}</div>`;
  if (s.cats.some(c => NIGHT.includes(c))) h += nightHelp(s);
  if (s.months) h += `<p class="label">Best months</p><div class="months">${"JFMAMJJASOND".split("").map((m, i) => `<span class="${s.months.includes(i + 1) ? "on" : ""} ${i + 1 === month ? "cur" : ""}">${m}</span>`).join("")}</div>`;
  if (pro.think || pro.land || pro.bird) h += `<details open><summary>How a pro would work it</summary><div class="prose">${pro.think ? `<p>${esc(pro.think)}</p>` : ""}${pro.plan ? `<p class="muted">${esc(pro.plan)}</p>` : ""}${pro.land ? `<p><b>Landscape:</b> ${esc(pro.land)}</p>` : ""}${pro.bird ? `<p><b>Birds & wildlife:</b> ${esc(pro.bird)}</p>` : ""}</div></details>`;
  if (pro.ideas.length) h += `<details><summary>Experimental ideas</summary><ul class="plain">${pro.ideas.map(x => `<li>${esc(x)}</li>`).join("")}</ul></details>`;
  if (al.length) h += `<details open><summary>Upcoming alignments here</summary><ul class="plain">${al.map(e => `<li>${fmtDate(e.t)} ${fmtT(e.t)}: ${esc(e.what)}${e.illum ? ` (${e.illum}% lit)` : ""}</li>`).join("")}</ul></details>`;
  if (pv) h += `<details><summary>Volcanoes visible from here</summary><ul class="plain">${pv.map(([pk, az, alt, show, vm, bkm]) => `<li>${show >= 0.3 ? "✓" : show >= 0.05 ? "◐" : "✗"} ${pk}: ${show >= 0.05 ? `${Math.round(az)}°, ${alt.toFixed(1)}° up${show < 0.3 ? ", summit tip only" : ""}` : `hidden by terrain ${bkm} km out`}</li>`).join("")}</ul><p class="muted" style="font-size:14px">From 30 m terrain profiles; trees and buildings not modeled.</p></details>`;
  h += `<details><summary>See others' photos here</summary><ul class="plain"><li><a href="https://www.flickr.com/search/?lat=${la}&lon=${lo}&radius=0.5&has_geo=1&sort=interestingness-desc" target="_blank" rel="noopener">Flickr</a></li><li><a href="https://www.google.com/maps/search/?api=1&query=${la},${lo}" target="_blank" rel="noopener">Google Maps photos</a></li>${also.map(([n, u]) => `<li><a href="${u}" target="_blank" rel="noopener">${esc(n)}</a></li>`).join("")}</ul></details>`;
  if (srcs.length) h += `<details><summary>Sources (${srcs.length})</summary><ul class="plain">${srcs.map(([n, u]) => `<li><a href="${u}" target="_blank" rel="noopener">${esc(n)}</a></li>`).join("")}</ul></details>`;
  h += `<p class="muted" style="font-size:13px;margin-top:14px">${la}, ${lo}</p>`;
  $("#sheetBody").innerHTML = h; $("#sheet").hidden = false; $("#sheetBody").scrollTop = 0;
  history.pushState({ sheet: id }, "");
}
function closeSheet() { $("#sheet").hidden = true; }

/* ---------- location ---------- */
function setLoc(l, quiet) {
  LOC = { ...l, at: Date.now() }; store.set("loc", LOC); ALIGN_CACHE = ALIGN_CACHE;
  updLoc(); if (!quiet) toast(`Planning from ${l.label}`);
  loadWx(true).then(render); render();
}
function updLoc() { $("#locName").textContent = LOC.label + (LOC.src === "gps" ? "" : ""); $(".pin").classList.toggle("est", LOC.src !== "gps"); }
function gps(timeout) {
  return new Promise(res => { if (!navigator.geolocation) return res(false);
    navigator.geolocation.getCurrentPosition(async p => { const l = { lat: p.coords.latitude, lon: p.coords.longitude, label: "Here", src: "gps" };
      l.label = await revName(l) || "Current location"; setLoc(l, true); res(true); }, () => res(false), { enableHighAccuracy: false, timeout: timeout || 10000, maximumAge: 5 * 60000 }); });
}
async function revName(l) {
  if (km(l, HOME) < 1.5) return "Home"; const pr = PRESETS.map(p => ({ n: p[0], d: km(l, { lat: p[1], lon: p[2] }) })).sort((a, b) => a.d - b.d)[0];
  try { const r = await fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=14&lat=${l.lat}&lon=${l.lon}`); const j = await r.json(); const a = j.address || {};
    return a.neighbourhood || a.suburb || a.hamlet || a.village || a.town || a.city || (pr && pr.d < 6 ? "Near " + pr.n : null); } catch (e) { return pr && pr.d < 8 ? "Near " + pr.n : null; }
}
async function searchPlace(q) {
  const msg = $("#locMsg"), hits = $("#locHits"); msg.textContent = "Searching…"; hits.innerHTML = "";
  const pre = PRESETS.filter(p => p[0].toLowerCase().includes(q.toLowerCase())).map(p => ({ label: p[0], lat: p[1], lon: p[2] }));
  let list = [...pre];
  try { const r = await fetch(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=6&countrycodes=us&viewbox=-124.3,46.9,-120.0,44.5&bounded=0&q=${encodeURIComponent(q)}`);
    const j = await r.json(); list = list.concat(j.map(x => ({ label: x.name || x.display_name.split(",")[0], sub: x.display_name.split(",").slice(1, 3).join(","), lat: +x.lat, lon: +x.lon }))); } catch (e) { }
  if (!list.length) { msg.textContent = "No match. Try a town, park or address."; return; }
  msg.textContent = ""; hits.innerHTML = list.slice(0, 7).map((x, i) => `<button class="lrow" data-hit="${i}"><span><b>${esc(x.label)}</b><small>${esc(x.sub || "")}</small></span><span class="muted">${fmtKm(km(LOC, x))}</span></button>`).join("");
  hits._list = list;
}

/* ---------- aurora + alerts ---------- */
async function loadKp() {
  if (KP && Date.now() - KP.at < 2 * 36e5) return;
  try { const r = await fetch("https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"); const j = await r.json();
    const rows = j.slice(1).map(x => ({ t: new Date(x[0].replace(" ", "T") + "Z"), kp: +x[1] })).filter(x => x.t > new Date() && x.t - Date.now() < 36 * 36e5);
    const night = rows.filter(x => { const h = +x.t.toLocaleString("en-US", { timeZone: TZ, hour: "numeric", hourCycle: "h23" }); return h >= 19 || h <= 4; });
    const best = night.sort((a, b) => b.kp - a.kp)[0];
    KP = { at: Date.now(), max: best ? best.kp : null, when: best ? `${dayWord(best.t)} around ${fmtT(best.t)}` : "" }; store.set("kp", KP);
  } catch (e) { }
}
async function loadNws() {
  if (NWS && Date.now() - NWS.at < 30 * 60000 && NWS.key === locKey()) return;
  try { const r = await fetch(`https://api.weather.gov/alerts/active?point=${LOC.lat.toFixed(3)},${LOC.lon.toFixed(3)}`, { headers: { Accept: "application/geo+json" } });
    const j = await r.json(); NWS = { at: Date.now(), key: locKey(), items: (j.features || []).map(f => ({ headline: f.properties.event + (f.properties.ends ? " until " + fmtT(new Date(f.properties.ends)) : ""), area: f.properties.areaDesc })) }; store.set("nws", NWS);
  } catch (e) { }
}

/* ---------- shell ---------- */
function fresh() {
  const f = $("#fresh"); if (!WX) { f.textContent = navigator.onLine ? "Loading weather…" : "Offline"; return; }
  const m = Math.round((Date.now() - WX.at) / 60000); f.textContent = (navigator.onLine ? "" : "Offline · ") + (m < 2 ? "Updated now" : `Updated ${fmtDur(m)} ago`);
}
function filtNote() { if (UI.group === "all") return ""; const l = (GROUPS.find(g => g[0] === UI.group) || [, ""])[1];
  return `<p class="filtnote">Showing only ${esc(l.toLowerCase())} spots <button class="chip" data-group="all">Show all</button></p>`; }
const addFiltNote = () => { const v = $("#v-now"), n = filtNote(); if (!v || !n || v.querySelector(".filtnote")) return; const pl = v.querySelector(".planner"); pl ? pl.insertAdjacentHTML("afterend", n) : v.insertAdjacentHTML("afterbegin", n); };
/* the one "when" for the whole app: the window picked on Plan also ranks Spots and colours the map */
function whenLabel(w) { if (w.live) return `Right now (${KNAME[w.kind].toLowerCase()})`;
  const d = dayWord(w.kind === "night" ? w.start : w.peak), day = d === "Today" ? "today" : d === "Tomorrow" ? "tomorrow" : d;
  return w.kind === "night" ? `${d === "Today" ? "Tonight" : d + " night"} · from ${chipTime(w)}` : `${KNAME[w.kind]} ${day} · ${chipTime(w)}`; }
function whenOpts(all) { return all.map((w, i) => [w, i]).filter(([w, i]) => i === UI.focus || i === 0 || ["sunrise", "sunset", "night"].includes(w.kind)).slice(0, 11)
  .map(([w, i]) => `<option value="${i}" ${i === UI.focus ? "selected" : ""}>${esc(whenLabel(w))}</option>`).join(""); }
function focusKind(kind) { const all = allWindows(LOC, PLAN_HOURS), i = all.findIndex(w => w.kind === kind && w.end > new Date()); if (i < 0) return false; UI.focus = i; UI.day = winDay(all[i]); UI.more = false; return true; }
function fbar() { const el = $("#fbar"); if (!el) return;
  el.innerHTML = `<button class="chip travelchip" id="travelChip" aria-label="How far you'll go">${PREFS.travel === "walk" ? "🚶" : "🚗"} ≤ ${fmtDur(maxTravel())}</button>` + GROUPS.map(([k, l]) => `<button class="chip" data-group="${k}" aria-pressed="${UI.group === k}">${l}</button>`).join(""); setStick(); }
function render() {
  updLoc(); fresh(); if ($("#fbar") && !$("#fbar").children.length) fbar();
  if (UI.view === "now") renderNow(); else if (UI.view === "spots") renderSpots(); else if (UI.view === "cal") renderCal(); else if (UI.view === "map") renderMap();
}
const PLAN_VIEWS = ["now", "sky", "cal"];   // Sky and Calendar live inside the Plan tab
function show(v) { UI.view = v; document.querySelectorAll(".view").forEach(x => x.hidden = x.id !== "v-" + v);
  const tab = PLAN_VIEWS.includes(v) ? "now" : v;
  document.querySelectorAll(".tabs button").forEach(b => { if (b.dataset.v === tab) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
  window.scrollTo(0, 0); render(); }
async function refresh(force) { await Promise.all([loadWx(force), loadKp(), loadNws()]); render(); }

document.addEventListener("click", e => {
  const t = e.target.closest("[data-spot],[data-focus],[data-group],[data-hit],[data-v],#moreBtn,#moreSpots,#saveBtn,#shotBtn,#shareBtn,#nightBtn,#locBtn,#locClose,#sheetClose,#useGps,#fresh");
  if (!t) return;
  if (t.dataset.v) return show(t.dataset.v);
  if (t.dataset.spot) return openSpot(t.dataset.spot);
  if (t.dataset.focus != null) { UI.focus = +t.dataset.focus; UI.more = false; render(); showDetail(); return; }
  if (t.dataset.group) { UI.group = t.dataset.group === UI.group && UI.group !== "all" ? "all" : t.dataset.group; store.set("group", UI.group); UI.limit = 40; __topsKey = "";
    const cur = allWindows(LOC, PLAN_HOURS)[UI.focus]; if (UI.group === "night" && (!cur || cur.kind !== "night") && focusKind("night")) toast("Showing tonight's night-sky window");
    fbar(); return render(); }
  if (t.dataset.hit != null) { const x = $("#locHits")._list[+t.dataset.hit]; $("#locSheet").hidden = true; return setLoc({ lat: x.lat, lon: x.lon, label: x.label, src: "search" }); }
  if (t.id === "moreBtn") { UI.more = true; return renderNow(); }
  if (t.id === "moreSpots") { UI.limit = (UI.limit || 40) + 40; return renderSpots(); }
  if (t.id === "saveBtn") { const id = t.dataset.id; if (SAVED[id]) delete SAVED[id]; else SAVED[id] = Date.now(); store.set("saved", SAVED); t.textContent = SAVED[id] ? "★ Saved" : "☆ Save"; haptic(); return; }
  if (t.id === "shotBtn") { const id = t.dataset.id, s = byId[id], w = windows(s, 1)[0], c = hourAt(nearestPt(s, 60), new Date());
    LOG.unshift({ id, t: Date.now(), c: c ? `${fmtTemp(c.tf)}, ${c.cc}% cloud, wind ${fmtWind(c.wind)}` : "" }); store.set("log", LOG.slice(0, 300)); toast(`Logged ${s.name}`); haptic(); return; }
  if (t.id === "shareBtn") { const s = byId[t.dataset.id]; navigator.share({ title: s.name, text: `${s.name}: ${s.tip || ""}`.slice(0, 280), url: `https://maps.apple.com/?ll=${s.lat},${s.lon}&q=${encodeURIComponent(s.name)}` }).catch(() => { }); return; }
  if (t.id === "nightBtn") { const on = document.documentElement.dataset.night !== "on"; document.documentElement.dataset.night = on ? "on" : "off"; t.setAttribute("aria-pressed", on); store.set("night", on); return; }
  if (t.id === "locBtn") { $("#locSheet").hidden = false; $("#locPresets").innerHTML = PRESETS.map((p, i) => `<button class="chip" data-preset="${i}">${esc(p[0])}</button>`).join(""); setTimeout(() => $("#locQ").focus(), 200); return; }
  if (t.id === "locClose") { $("#locSheet").hidden = true; return; }
  if (t.id === "sheetClose") { history.back(); return; }
  if (t.id === "fresh") { toast("Refreshing…", 1500); return refresh(true); }
  if (t.id === "useGps") { $("#locMsg").textContent = "Finding you…"; gps(12000).then(ok => { if (ok) { $("#locSheet").hidden = true; toast(`Planning from ${LOC.label}`); } else $("#locMsg").textContent = "Location is off for ShotSpots. Turn it on in Settings › Privacy › Location Services, or search for a place."; }); }
});
document.addEventListener("click", e => { const p = e.target.closest("[data-preset]"); if (!p) return; const x = PRESETS[+p.dataset.preset]; $("#locSheet").hidden = true;
  setLoc(x[0].startsWith("Washougal") ? { ...HOME } : { lat: x[1], lon: x[2], label: x[0], src: "preset" }); });
document.addEventListener("submit", e => { e.preventDefault(); if (e.target.id === "locForm") searchPlace($("#locQ").value.trim()); });
document.addEventListener("input", e => { if (e.target.id === "spotQ") { UI.q = e.target.value; clearTimeout(UI._qt); UI._qt = setTimeout(() => { renderSpots(); const q = $("#spotQ"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 250); } });
document.addEventListener("change", e => { if (e.target.id === "whenSel") { const all = allWindows(LOC, PLAN_HOURS); UI.focus = +e.target.value; UI.day = winDay(all[UI.focus]); UI.more = false; renderSpots(); }
  if (e.target.id === "sortSel") { UI.sort = e.target.value; renderSpots(); } if (e.target.id === "inSeason") { UI.inSeason = e.target.checked; renderSpots(); } });
document.addEventListener("keydown", e => { if (e.key === "Enter" && e.target.matches(".item[data-spot]")) openSpot(e.target.dataset.spot); if (e.key === "Escape") { if (!$("#sheet").hidden) history.back(); $("#locSheet").hidden = true; } });
window.addEventListener("popstate", () => closeSheet());
document.addEventListener("visibilitychange", () => { if (!document.hidden) { if (!WX || Date.now() - WX.at > 15 * 60000) refresh(); else render(); if (LOC.src === "gps" && Date.now() - (LOC.at || 0) > 20 * 60000) gps(8000); } });
window.addEventListener("online", () => refresh(true)); window.addEventListener("offline", fresh);
setInterval(() => { if (!document.hidden) { if (Date.now() - (WX ? WX.at : 0) > 30 * 60000) refresh(); else render(); } }, 5 * 60000);

/* ---------- boot ---------- */
(function boot() {
  if (store.get("night", false)) { document.documentElement.dataset.night = "on"; $("#nightBtn").setAttribute("aria-pressed", "true"); }
  render(); refresh();
  // Use GPS when we haven't been told a place in the last 2 hours
  if (PREFS.start === "home") { if (LOC.src !== "home" && (LOC.src !== "search" && LOC.src !== "preset" || Date.now() - (LOC.at || 0) > 2 * 36e5)) setLoc({ ...HOME }, true); }
  else if (LOC.src !== "search" && LOC.src !== "preset" || Date.now() - (LOC.at || 0) > 2 * 36e5) gps(10000);
  if ("serviceWorker" in navigator && location.protocol === "https:") { navigator.serviceWorker.register("sw.js").catch(() => { });
    // when an update takes over, reload once so the page and its scripts are the same version
    const had = !!navigator.serviceWorker.controller; let done = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => { if (had && !done) { done = true; location.reload(); } }); }
})();
/* after picking a window, bring its details up just under the pinned planner (only if they're out of view) */
function showDetail() {
  const d = $("#winDetail"), p = $("#planner"); if (!d || !p) return;
  const desk = matchMedia("(min-width:1100px)").matches, view = d.closest(".view");
  const top0 = desk && view ? view.getBoundingClientRect().top : (parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--stick")) || 0);
  const off = top0 + p.getBoundingClientRect().height + 14, r = d.getBoundingClientRect();
  d.style.scrollMarginTop = (off - (desk && view ? top0 : 0)) + "px";
  if (r.top < off - 4 || r.top > innerHeight * 0.55) d.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion:reduce)").matches ? "auto" : "smooth" });
}
/* planner: day tabs pick that day's best window (or the first one still ahead) */
document.addEventListener("click", e => {
  const t = e.target.closest("[data-day]"); if (!t || !t.closest("#planner")) return;
  const all = allWindows(LOC, PLAN_HOURS), tops = windowTops(all); UI.day = t.dataset.day; UI.more = false;
  const idx = all.map((w, i) => i).filter(i => winDay(all[i]) === UI.day);
  UI.focus = idx.reduce((b, i) => (tops[i] ? tops[i].f.n : -1) > (tops[b] ? tops[b].f.n : -1) ? i : b, idx[0] ?? UI.focus);
  render(); showDetail();
});
/* keep the pinned planner just under the header (phone); on desktop the column scrolls on its own */
function setStick() { const t = document.querySelector(".top"); document.documentElement.style.setProperty("--stick", matchMedia("(min-width:1100px)").matches || !t ? "0px" : t.offsetHeight + "px"); }
addEventListener("resize", setStick); setTimeout(setStick, 0);
{ const _rnF = renderNow; renderNow = function () { _rnF.apply(this, arguments); addFiltNote(); }; }
