/* Forecast confidence: how much four weather models (GFS, ECMWF, ICON, GEM) disagree about cloud at the selected
   window's peak. Backtested on 30,000 Northwest sunrises and sunsets (Feb 2024 to Nov 2026, day-ahead forecasts vs
   ERA5): disagreement tracks error closely (rank correlation 0.73), with typical cloud errors by spread of
   <=5 pts: 3, 5-10: 10, 10-20: 17, 20-30: 23, >30: 30 (and 44% of those miss by more than 30 points).
   One extra request per location, cached for an hour. tools/confbt.py has the backtest. */
"use strict";
const CONF = { key: null, at: 0, t: null, m: null, busy: false };
const CONF_MODELS = ["gfs_seamless", "ecmwf_ifs025", "icon_seamless", "gem_seamless"];
async function loadConf() {
  const k = LOC.lat.toFixed(2) + "," + LOC.lon.toFixed(2);
  if (CONF.busy || (CONF.key === k && Date.now() - CONF.at < 36e5)) return;
  CONF.busy = true;
  try {
    const r = await omFetch(`https://api.open-meteo.com/v1/forecast?latitude=${LOC.lat.toFixed(3)}&longitude=${LOC.lon.toFixed(3)}&hourly=cloud_cover&models=${CONF_MODELS.join(",")}&forecast_days=8&timezone=UTC`);
    const j = r && r.ok ? await r.json() : null, h = j && j.hourly;
    if (h && h.time) {
      CONF.t = h.time.map(t => Date.parse(t + "Z"));
      CONF.m = CONF_MODELS.map(m => h["cloud_cover_" + m] || null).filter(Boolean);
      CONF.key = k; CONF.at = Date.now();
      if (typeof renderNow === "function" && UI.view === "now") renderNow();
    }
  } catch (e) { } finally { CONF.busy = false; }
}
function confAt(t) {
  if (!CONF.t || !CONF.m || CONF.m.length < 3) return null;
  const ms = t.getTime(); let i = CONF.t.findIndex(x => x >= ms - 18e5); if (i < 0) return null;
  const v = CONF.m.map(a => a[i]).filter(x => x != null); if (v.length < 3) return null;
  const mean = v.reduce((a, b) => a + b, 0) / v.length, sd = Math.sqrt(v.reduce((a, b) => a + (b - mean) ** 2, 0) / (v.length - 1));
  const err = sd <= 5 ? 3 : sd <= 10 ? 10 : sd <= 20 ? 17 : sd <= 30 ? 23 : 30;
  return { mean, sd, err, lo: Math.round(Math.min(...v)), hi: Math.round(Math.max(...v)), lvl: sd <= 10 ? "agree" : sd <= 25 ? "mixed" : "disagree" };
}
function confHtml(w) {
  if (!w || w.kind === "now") return "";
  const at = w.kind === "night" ? (w.dark ? w.dark.s : w.start) : (w.peak || w.start);
  if (at.getTime() - Date.now() < 2 * 36e5) return "";   // close in, the live data matters more than model spread
  const c = confAt(at); if (!c) return "";
  const txt = c.lvl === "agree" ? `Models agree on the sky (${c.lo}–${c.hi}% cloud): this forecast is usually within about ${c.err} points.`
    : c.lvl === "mixed" ? `Models partly disagree (${c.lo}–${c.hi}% cloud): typical miss about ${c.err} points. Check again closer to the time.`
    : `Models disagree (${c.lo}–${c.hi}% cloud): the sky could go either way. Check again the evening before you commit to a long drive.`;
  return `<p class="conf conf-${c.lvl}" role="note"><span class="conf-dot"></span>${txt}</p>`;
}
{ const _rC = renderNow; renderNow = function () { _rC.apply(this, arguments); loadConf();
  const d = $("#winDetail"); if (!d || d.querySelector(".conf")) return;
  const all = allWindows(LOC, PLAN_HOURS), w = all[UI.focus]; const h = confHtml(w); if (!h) return;
  const sky = d.querySelector(".skyd"); if (sky) sky.insertAdjacentHTML("afterend", h); else d.insertAdjacentHTML("beforeend", h);
}; }
