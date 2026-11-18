/* Data depth and measured accuracy: how much a spot's score rests on measurements versus guesses. Display only:
   nothing here changes a score (tools/scoretest.py must pass unchanged).
   Four parts, each MEASURED or ESTIMATED:
     terrain  hand-researched, or a terrain horizon worked out from 10 m elevation (s.deep / s.hzp)
     facing   which light the spot faces: hand-researched, fine terrain (deep research) or people's photos; otherwise coarse terrain
     record   photo / Wikipedia counts behind the spot-quality factor (hasRecord); otherwise the median of recorded spots nearby
     drive    a routed drive time (DRIVES, or the researched drive from home); otherwise the straight-line estimate
   Cards show four small dots (filled = measured); the spot page's "Why this score" lists them in words.
   Where fog or low cloud is a main reason in a score or an alert, a note gives how those day-ahead forecasts actually did
   against airport reports (feed/verify_obs.json): the nearest verified airport with enough reports, else all of them,
   and nothing for spots more than 250 km from any verified airport. */
"use strict";
function dataDepth(s) {
  const hand = !s.seed && !s.osm, k = typeof locKey === "function" ? locKey() : "";
  const routed = PREFS.travel !== "walk" && ((DRIVES[k] && DRIVES[k].m[s.id] != null) || (atHome() && s.drive != null));
  return [
    { k: "terrain", on: hand || !!s.deep || !!s.hzp, yes: hand ? "terrain hand-researched" : "terrain horizon from 10 m elevation", no: "terrain not checked" },
    { k: "facing", on: hand || !!s.deep || !!s._psLight, yes: hand ? "facing hand-researched" : s._psLight ? "facing from people's photos" : "facing from fine terrain", no: s.seed ? "facing guessed from coarse terrain" : "facing guessed" },
    { k: "record", on: hasRecord(s), yes: "photo / Wikipedia record", no: "no photo record (quality is the local median)" },
    { k: "drive", on: routed, yes: "routed drive time", no: PREFS.travel === "walk" ? "walking time estimated from distance" : "drive time estimated from distance" },
  ];
}
function depthDots(s) {
  const d = dataDepth(s), n = d.filter(x => x.on).length;
  const tip = `Data depth, ${n} of 4 measured: ` + d.map(x => x.on ? x.yes : x.no).join("; ");
  return `<span class="depth" role="img" title="${esc(tip)}" aria-label="${esc(tip)}">${d.map(x => `<i class="${x.on ? "on" : ""}"></i>`).join("")}${n <= 1 ? `<em>estimated</em>` : ""}</span>`;
}
function depthLine(s) {
  const d = dataDepth(s), m = d.filter(x => x.on), e = d.filter(x => !x.on);
  return `<p class="depthline"><b>Data behind it</b> ${depthDots(s)}<br>`
    + (m.length ? `Measured: ${esc(m.map(x => x.yes).join(", "))}.` : "Nothing measured yet for this spot.")
    + (e.length ? ` Estimated: ${esc(e.map(x => x.no).join(", "))}.` : "") + `</p>`;
}

/* ---- measured forecast accuracy for fog and low cloud ---- */
const FOG_RX = /\bfog\b/i, LOW_RX = /low cloud|low deck|cloud deck/i;
function accStation(p) {   // nearest verified airport (coordinates from the live obs feed), its distance in km
  const v = fd("verify_obs"), o = fd("obs"); if (!v || !v.stations || !o || !o.stations) return null;
  let best = null, bd = 1e9; for (const x of o.stations) { if (!x.lat || !v.stations[x.id]) continue; const d = km(p, x); if (d < bd) { bd = d; best = x; } }
  return best ? { id: best.id, d: bd, st: v.stations[best.id] } : null;
}
// loadFeed's periodic refresh drops verify_obs and only the first load fetches it again: fetch it here when missing
let __accAsk = 0;
function accFeed() { const v = fd("verify_obs"); if (!v && Date.now() - __accAsk > 6e4 && typeof feedGet === "function") { __accAsk = Date.now(); feedGet("verify_obs").then(j => { if (j) setTimeout(render, 0); });   // rankings do not depend on it: no cache reset } return v; }
function accFor(p, ev) {   // stats for event "fog" or "low" near p: { e, where } or null
  const v = accFeed(); if (!v || !v.events) return null; const ns = accStation(p); if (!ns || ns.d > 250) return null;
  const se = ns.st[ev], ok = e => e && e.n >= 20 && e.hit + e.false_alarm >= 5 && e.hit + e.miss >= 5;
  if (ns.d <= 60 && ok(se)) return { e: se, where: `at ${ns.st.name || ns.id}` };
  return ok(v.events[ev]) ? { e: v.events[ev], where: `at ${Object.keys(v.stations).length} ${nwOnly(v) ? "Northwest" : "verified"} airports`, all: true } : null;
}
function nwOnly(v) { const o = fd("obs"), st = (o && o.stations || []).filter(x => v.stations[x.id] && x.lat); return st.length > 0 && st.every(x => x.lon < -115 && x.lat > 41); }
const oneIn = (a, b) => b > 0 && a > 0 ? `1 in ${Math.max(1, Math.round(b / a))}` : "never";
function accShort(p, why) {   // one short clause for a card or alert
  const top = why.join(" ");
  if (FOG_RX.test(top)) { const a = accFor(p, "fog"); if (a) return `Fog forecasts a day ahead came true ${oneIn(a.e.hit, a.e.hit + a.e.false_alarm)} times last month`; }
  if (LOW_RX.test(top)) { const a = accFor(p, "low"), b = fd("verify_obs").low_cloud_bias_pct;
    if (a) return `Low cloud forecasts a day ahead came true ${oneIn(a.e.hit, a.e.hit + a.e.false_alarm)} times last month${a.all && b > 5 ? `; they run about ${Math.round(b)} points high` : ""}`; }
  return "";
}
function accLong(p, why) {   // spot page: both figures, the sample and where it was measured
  const top = why.join(" "), out = [], pc = x => Math.round(x * 100) + "%";
  if (FOG_RX.test(top)) { const a = accFor(p, "fog"); if (a) out.push(`when fog was forecast a day ahead it came true ${pc(1 - a.e.false_alarm_ratio)} of the time, and the forecast caught ${pc(a.e.hit_rate)} of the fogs that happened`); }
  if (LOW_RX.test(top)) { const a = accFor(p, "low"), b = fd("verify_obs").low_cloud_bias_pct;
    if (a) out.push(`when a low cloud deck was forecast a day ahead it showed up ${pc(1 - a.e.false_alarm_ratio)} of the time${a.all && b > 5 ? `, and forecast low cloud averaged about ${Math.round(b)} points more than airports reported, so the sky is often more open than forecast` : ""}`); }
  if (!out.length) return "";
  const a = accFor(p, FOG_RX.test(top) ? "fog" : "low");
  return `<p class="accnote" role="note"><b>How these forecasts did</b> (MEASURED, airport reports at sunrise and sunset, last 30 days, ${esc(a.where)}): ${esc(out.join("; "))}.</p>`;
}
const accWin = w => w && w.kind !== "now" && !w.live && (w.peak || w.start) && (w.peak || w.start).getTime() - Date.now() >= 2 * 36e5;   // close in, live reports matter more

/* ---- cards ---- */
const _pickRowD = pickRow;
pickRow = function (x, w) {
  let h = _pickRowD(x, w); if (!x || !x.s) return h;
  h = h.replace(/(<small class="cat">[^<]*)(<\/small>)/, `$1${depthDots(x.s)}$2`);
  const why = (x.f && x.f.why || []).slice(0, 2), n = accWin(w) && why.length ? accShort(x.s, why) : "";
  return n ? h.replace(/(<\/small>)(<\/span>\s*<span class="drive">)/, `$1<small class="acc">${esc(n)}</small>$2`) : h;
};

/* ---- spot page: inside "Why this score" (ux.js has already lifted it out of its .scoremath box into plain sections) ---- */
const _openSpotD = openSpot;
openSpot = function (id) {
  _openSpotD(id);
  const s = byId[id], b = $("#sheetBody"); if (!s || !b || b.querySelector(".depthline")) return;
  const h = [...b.querySelectorAll("h3")].find(x => /^Why this score/.test(x.textContent.trim())); if (!h) return;
  h.insertAdjacentHTML("afterend", depthLine(s));
  const ws = allWindows(LOC, PLAN_HOURS), w = ws[UI.focus] || ws[0], f = w && fitFor(s, w); if (!f || !accWin(w)) return;
  const a = accLong(s, f.why.slice(0, 3)); if (!a) return;
  let el = h.nextElementSibling; while (el && !(el.tagName === "OL" && el.classList.contains("layers")) && el.tagName !== "H3") el = el.nextElementSibling;
  (el && el.tagName === "OL" ? el : h.nextElementSibling).insertAdjacentHTML(el && el.tagName === "OL" ? "beforebegin" : "afterend", a);
};

/* ---- alerts that rest on fog or low cloud ---- */
const _alertRowD = alertRow;
alertRow = function (a) {
  const h = _alertRowD(a); const sp = a && (a.spots || [])[0] && byId[a.spots[0]];
  const n = accShort(sp || HOME, [a.rule === "fog_above" ? "fog" : "", a.title || "", a.body || ""]);
  return n ? h.replace(/(<\/small>)(<\/span>)/, `$1<small class="acc">${esc(n)}</small>$2`) : h;
};
