/* Opening hours (OpenStreetMap opening_hours, gathered by pipeline/hours.py) and what they mean for each light window.
   Reads the common forms: "24/7", "Mo-Fr 09:00-17:00; Sa,Su 10:00-18:00", "Apr-Oct: 10:00-19:00; Nov-Mar 10:00-16:00",
   "sunrise-sunset", "dawn-dusk", "off". Anything it can't read counts as unknown, never as closed. */
"use strict";
const OH_DAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"], OH_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const SEEDHOURS = {};

function ohHours(s) { const h = (fd("hours") || { spots: {} }).spots[s.id]; return h ? h.oh : SEEDHOURS[s.id] || null; }

// returns true (open), false (closed) or null (can't tell) for spot s at time t
function ohOpenAt(oh, s, t) {
  if (!oh) return null; oh = oh.trim(); if (oh === "24/7") return true;
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "short", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(t);
  const g = k => (parts.find(p => p.type === k) || {}).value, wd = OH_DAYS.indexOf(g("weekday").slice(0, 2)), mo = OH_MON.indexOf(g("month")), mins = +g("hour") * 60 + +g("minute");
  const ev = dayEvents(s, laYMD(t)), toMin = d => { if (!d) return null; const p = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(d); return +p.find(x => x.type === "hour").value * 60 + +p.find(x => x.type === "minute").value; };
  const word = { sunrise: toMin(ev.sunrise), sunset: toMin(ev.sunset), dawn: toMin(ev.civilDawn), dusk: toMin(ev.civilDusk) };
  const tmin = x => x in word ? word[x] : /^\d{1,2}:\d{2}$/.test(x) ? +x.split(":")[0] * 60 + +x.split(":")[1] : NaN;
  const inRange = (list, i, names) => list.split(",").some(r => { const [a, b] = r.split("-").map(x => names.indexOf(x.trim().slice(0, names === OH_DAYS ? 2 : 3)));
    if (a < 0) return false; if (b === undefined || b < 0) return a === i; return a <= b ? i >= a && i <= b : i >= a || i <= b; });
  let state = null, understood = false;
  for (let rule of oh.split(";")) {
    rule = rule.trim().replace(/^"[^"]*"\s*/, ""); if (!rule) continue;
    let m = /^((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?:\s*-\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))?(?:\s*,\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?:\s*-\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))?)*)\s*:?\s*/.exec(rule);
    if (m) { if (!inRange(m[1].replace(/\s/g, ""), mo, OH_MON)) { understood = true; continue; } rule = rule.slice(m[0].length); }
    m = /^((?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?(?:,(?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?)*)(?:,PH)?\s*/.exec(rule);
    if (m) { if (!inRange(m[1], wd, OH_DAYS)) { understood = true; continue; } rule = rule.slice(m[0].length); }
    if (/^(off|closed)$/i.test(rule)) { state = false; understood = true; continue; }
    if (/^24\/7$|^00:00-24:00$/.test(rule)) { state = true; understood = true; continue; }
    const spans = rule.split(",").map(x => x.trim().split("-")).filter(x => x.length === 2).map(([a, b]) => [tmin(a), tmin(b)]);
    if (!spans.length || spans.some(([a, b]) => isNaN(a) || isNaN(b))) continue;   // a form we don't read: leave it unknown
    understood = true; state = spans.some(([a, b]) => b > a ? mins >= a - 10 && mins <= b + 10 : mins >= a - 10 || mins <= b + 10);
  }
  return understood ? state : null;
}
function ohShort(oh) { return oh.replace(/;\s*PH[^;]*/g, "").replace(/sunrise-sunset/g, "sunrise to sunset").replace(/dawn-dusk/g, "dawn to dusk").slice(0, 70); }

// score: closed during the window = mostly out
const _fitHours = fitFor;
fitFor = function (s, w) {
  const f = _fitHours(s, w); if (!f) return f; const oh = ohHours(s); if (!oh) return f;
  const open = ohOpenAt(oh, s, w.peak); if (open !== false) return f;
  return { ...f, n: Math.round(f.n * 0.25), why: [...(f.why || []), `closed then (hours: ${ohShort(oh)})`] };
};
// spot page: show the hours
const _openSpotHours = openSpot;
openSpot = function (id) {
  const r = _openSpotHours.apply(this, arguments);
  setTimeout(() => { const s = byId[id], oh = s && ohHours(s), body = document.querySelector("#sheetBody"); if (!oh || !body || body.querySelector(".ohline")) return;
    const now = ohOpenAt(oh, s, new Date());
    body.insertAdjacentHTML("afterbegin", `<p class="ohline muted" style="font-size:14px;margin:0 0 8px">🕘 Hours: ${esc(ohShort(oh))}${now === true ? " · <b>open now</b>" : now === false ? " · <b>closed now</b>" : ""} <span style="font-size:12px">(OpenStreetMap)</span></p>`); }, 50);
  return r;
};
