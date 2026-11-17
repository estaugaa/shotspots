/* Nowcast: for the next 3 hours, what airports are reporting beats what the forecast models said.
   Nearby airport reports (feed/obsnow, refreshed with every satellite scan) replace the forecast's low and mid cloud for
   the forecast point they sit near; high cloud stays the forecast's (automated stations see only to 12,000 ft).
   Weight: full now, fading to 30% three hours ahead. Nov 16 2026: forecast said 100% overcast at Washougal, the
   airports said scattered-to-broken and the sky was partly cloudy. */
"use strict";
let OBSNOW = null;
function obsTileKey(lat, lon) { return `${5 * Math.floor(lat / 5)}_${5 * Math.floor(lon / 5)}`; }
async function loadObsNow() {
  if (typeof LOC === "undefined" || !LOC) return;
  const keys = new Set(); for (const dl of [-1.5, 0, 1.5]) for (const dn of [-2, 0, 2]) keys.add(obsTileKey(LOC.lat + dl, LOC.lon + dn));
  const rows = [];
  await Promise.all([...keys].map(k => fetch(`feed/obsnow/${k}.json`, { cache: "no-cache" }).then(r => r.ok ? r.json() : null).then(j => { if (j && j.s) rows.push(...j.s); }).catch(() => { })));
  OBSNOW = rows.map(([id, lat, lon, t, low, mid, cover]) => ({ id, lat, lon, t: t * 1000, low, mid, cover }));
  if (typeof __skyMemoAt !== "undefined") __skyMemoAt = -1;   // re-score with the reports
  if (typeof render === "function") render();
}
setTimeout(loadObsNow, 300); setInterval(loadObsNow, 15 * 60e3);
function obsFor(pt) {
  if (!OBSNOW || !OBSNOW.length) return null;
  let best = null, bd = 40;
  for (const o of OBSNOW) { if (Date.now() - o.t > 100 * 60e3) continue; const d = km(pt, o); if (d < bd) { bd = d; best = o; } }
  return best;
}
const NOWTXT = c => c >= 95 ? "overcast" : c >= 70 ? "broken cloud" : c >= 35 ? "scattered cloud" : c > 0 ? "a few clouds" : "clear";
const _hourAtNC = hourAt;
hourAt = function (pt, t) {
  const c = _hourAtNC(pt, t); if (!c || !pt) return c;
  const ahead = (t.getTime() - Date.now()) / 36e5; if (ahead < -1 || ahead > 3) return c;
  const o = obsFor(pt); if (!o) return c;
  const wgt = ahead <= 0 ? 1 : 1 - 0.7 * ahead / 3;
  const low = Math.round(c.low * (1 - wgt) + o.low * wgt), mid = Math.round(c.mid * (1 - wgt) + o.mid * wgt);
  const cc = Math.round(Math.min(100, Math.max(low, mid, c.high * 0.8, low + (100 - low) * mid / 100 * 0.6)));
  return { ...c, low, mid, cc, nc: { id: o.id, t: o.t, low: o.low, mid: o.mid, model: c.cc } };
};
const _fitNC = fitFor;
fitFor = function (s, w) {
  const f = _fitNC(s, w); if (!f) return f;
  const c = hourAt(nearestPt(s, 60), w.peak);
  if (c && c.nc) { const t = new Date(c.nc.t).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    f.why = [`live airport report (${c.nc.id}, ${t}): ${NOWTXT(Math.max(c.nc.low, c.nc.mid))} below 12,000 ft (forecast said ${c.nc.model}%)`, ...f.why]; }
  return f;
};
