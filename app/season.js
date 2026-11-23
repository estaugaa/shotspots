/* Seasonal planner on the spot page: clear sky at sunrise and sunset by week of the year, from the nearest airport's
   10 years of reports (national climatology, pipeline/climonat.py; loader in feed.js). MEASURED history, not a forecast.
   Not a scoring layer: it only shows the record, so it does not wrap fitFor. */
"use strict";
const SEASON_MIN_N = 20;   // pooled days below this: the week is left blank
const SEASON_FOG = 25;     // % of mornings with fog or mist that marks a fog-prone week (15% flagged 39 weeks at Bar Harbor)
function seasonFogSpot(s) { return s.cats.includes("waterfall") || (typeof FOG_ABOVE !== "undefined" && FOG_ABOVE.includes(s.id)); }
// first day of week w (weekIdx counts 7-day blocks from Jan 1; week 52 takes the year's last 1-2 days)
function seasonWeekDate(w) { return new Date(new Date().getFullYear(), 0, 1 + 7 * w); }
function seasonFmt(d) { return d.toLocaleDateString("en-US", { month: "short", day: "numeric" }); }
function seasonRows(v) {
  const rows = [];
  for (let w = 0; w < 52; w++) {
    const r = climoPool(v, "r", w), s = climoPool(v, "s", w), pc = (x, n) => Math.round(x / n * 100);
    rows.push({ w, r: r[0] >= SEASON_MIN_N ? { n: r[0], clear: pc(r[1], r[0]), ovc: pc(r[3], r[0]), fog: pc(r[4], r[0]) } : null,
      s: s[0] >= SEASON_MIN_N ? { n: s[0], clear: pc(s[1], s[0]), ovc: pc(s[3], s[0]), fog: pc(s[4], s[0]) } : null });
  }
  return rows;
}
// the 3 weeks with the most clear evenings (or mornings), as week indices
function seasonBest(rows, ev) { return rows.filter(x => x[ev]).sort((a, b) => b[ev].clear - a[ev].clear).slice(0, 3).map(x => x.w); }
// "Jun 18 – Jul 8" for a set of weeks (first to last of the best run around the top week)
function seasonSpan(ws) { const a = Math.min(...ws), b = Math.max(...ws); return b - a > 3 ? ws.map(w => seasonFmt(seasonWeekDate(w))).join(", ") : `${seasonFmt(seasonWeekDate(a))} – ${seasonFmt(new Date(seasonWeekDate(b).getTime() + 6 * 864e5))}`; }
function seasonHtml(s, b) {
  const [id, v, dk] = b, rows = seasonRows(v); if (!rows.some(x => x.s || x.r)) return "";
  const fogSpot = seasonFogSpot(s), now = weekIdx(new Date()), best = { r: seasonBest(rows, "r"), s: seasonBest(rows, "s") };
  // shade within this station's own range (stated under the strip), so a 35% and a 70% week look different
  const cl = rows.flatMap(x => [x.r, x.s]).filter(Boolean).map(c => c.clear), lo = Math.min(...cl), hi = Math.max(...cl), sp = Math.max(10, hi - lo);
  const cell = (x, ev) => { const c = x[ev]; const cls = `${x.w === now ? " cur" : ""}${best[ev].includes(x.w) ? " best" : ""}`;
    if (!c) return `<i class="none${cls}" data-w="${x.w}"></i>`;
    return `<i class="${cls.trim()}" data-w="${x.w}" style="--a:${(0.12 + 0.88 * Math.max(0, c.clear - lo) / sp).toFixed(2)}"></i>`; };
  const fogRow = fogSpot ? `<div class="seasrow"><span>Fog</span><div class="seascells">${rows.map(x => !x.r ? `<i class="none${x.w === now ? " cur" : ""}" data-w="${x.w}"></i>` :
    `<i class="fog${x.r.fog >= SEASON_FOG ? " best" : ""}${x.w === now ? " cur" : ""}" data-w="${x.w}" style="--a:${(0.1 + 0.9 * Math.min(1, x.r.fog / 50)).toFixed(2)}"></i>`).join("")}</div></div>` : "";
  const ticks = "JFMAMJJASOND".split("").map((m, i) => { const w = weekIdx(new Date(new Date().getFullYear(), i, 1, 12)); return `<b style="left:${(w / 52 * 100).toFixed(1)}%">${m}</b>`; }).join("");
  const top = ev => { const ws = best[ev]; if (!ws.length) return ""; const pct = rows[ws[0]][ev].clear; return `${seasonSpan(ws)} (${pct}%)`; };
  const fogW = rows.filter(x => x.r && x.r.fog >= SEASON_FOG).map(x => x.w);
  const fogTxt = fogSpot ? (fogW.length ? ` Fog or mist on ${SEASON_FOG}%+ of mornings in ${fogW.length} week${fogW.length > 1 ? "s" : ""} (outlined in the grey row; darker = foggier).` : ` Fog or mist stays under ${SEASON_FOG}% of mornings at the airport every week (darker grey = more).`) : "";
  const y = v.y || [], ns = rows.map(x => x.s && x.s.n).filter(Boolean), el = spotElev(s.id), elNote = el != null && v.el != null && el - v.el > 600 ? ` The station is ${Math.round(el - v.el)} m lower than the spot: valley cloud there may be below you.` : el != null && v.el != null && v.el - el > 600 ? ` The station is ${Math.round(v.el - el)} m higher than the spot.` : "";
  const farNote = dk > 40 ? ` The station is ${Math.round(dk)} km away, so local cloud (mountains, coast, valleys) can differ.` : "";
  return `<details open class="seasbox"><summary>Clear-sky odds by week <span class="prov p-measured" title="Counted from 10 years of airport reports, not modeled">measured</span></summary>
    <div class="seas" data-spot="${esc(s.id)}">
      <div class="seasrow"><span>Sunrise</span><div class="seascells">${rows.map(x => cell(x, "r")).join("")}</div></div>
      <div class="seasrow"><span>Sunset</span><div class="seascells">${rows.map(x => cell(x, "s")).join("")}</div></div>
      ${fogRow}<div class="seasrow"><span></span><div class="seasticks">${ticks}</div></div>
    </div>
    <p class="seasdetail muted" style="font-size:13px;margin:4px 0" aria-live="polite">Tap a week for its numbers. Palest ${lo}% clear, darkest ${hi}%; outlined = the 3 clearest weeks; blue tick = this week.</p>
    <p class="muted" style="font-size:13px;margin:4px 0">Clearest sunsets: <b>${top("s") || "not enough data"}</b>. Clearest sunrises: <b>${top("r") || "not enough data"}</b>.${fogTxt}</p>
    <p class="muted" style="font-size:12px;margin:4px 0">${esc(v.name)} (${esc(id)}), ${Math.round(dk)} km away, ${y[0]}–${y[1]}: the report nearest each sunrise and sunset (within 45 min), each week pooled with the weeks either side, ${Math.min(...ns)}–${Math.max(...ns)} evenings a week; weeks with under ${SEASON_MIN_N} days left blank. Airport ceilometers see cloud only below 12,000 ft, so "clear" can still have high cloud (often the colourful kind).${elNote}${farNote} History, not a forecast.</p></details>`;
}
function seasonDetail(box, b, w) {
  const v = b[1], r = climoPool(v, "r", w), s = climoPool(v, "s", w), p = box.parentNode.querySelector(".seasdetail");
  const f = (x, word) => x[0] >= SEASON_MIN_N ? `${word} clear ${Math.round(x[1] / x[0] * 100)}%, overcast ${Math.round(x[3] / x[0] * 100)}%, fog or mist ${Math.round(x[4] / x[0] * 100)}% (${x[0]} days)` : `${word}: under ${SEASON_MIN_N} days of reports`;
  if (p) p.innerHTML = `<b>Week of ${seasonFmt(seasonWeekDate(w))}</b>: ${f(s, "sunset")}; ${f(r, "sunrise")}.`;
}
let __seasOpen = null;
function seasonPlanner(s) {
  __seasOpen = s.id;
  climoLoad(s).then(() => {
    const body = $("#sheetBody"); if (__seasOpen !== s.id || !body || body.querySelector(".seasbox")) return;
    const b = climoNear(s); if (!b) return; const h = seasonHtml(s, b); if (!h) return;
    const anchor = body.querySelector("details"); anchor ? anchor.insertAdjacentHTML("beforebegin", h) : body.insertAdjacentHTML("beforeend", h);
    const box = body.querySelector(".seas");
    box.addEventListener("click", e => { const c = e.target.closest("i[data-w]"); if (c) seasonDetail(box, b, +c.dataset.w); });
  }).catch(e => noteErr("seasonal planner", e));
}
const _openSeason = openSpot;
openSpot = function (id) { _openSeason(id); const s = byId[id]; if (s) seasonPlanner(s); };
